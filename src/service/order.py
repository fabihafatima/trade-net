import os
import csv
import threading
import time
import grpc
from concurrent import futures
import argparse

import catalog_pb2 as catalog_pb2
import catalog_pb2_grpc as catalog_pb2_grpc
import order_pb2 as order_pb2
import order_pb2_grpc as order_pb2_grpc

catalog_ip = os.environ.get("CATALOG_IP") if os.environ.get("CATALOG_IP") else "localhost"

# Read-Write Lock for synchronization
class ReadWriteLock: 
    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False

    def acquire_read(self):
        with self._read_ready:
            while self._writer:
                self._read_ready.wait()
            self._readers += 1

    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self):
        with self._read_ready:
            while self._writer or self._readers > 0:
                self._read_ready.wait()
            self._writer = True

    def release_write(self):
        with self._read_ready:
            self._writer = False
            self._read_ready.notify_all()


class OrderServiceImpl(order_pb2_grpc.OrderServiceServicer):
    def __init__(self, order_file, replica_id):
        self.order_file = order_file
        self.replica_id = replica_id
        print(f"Order service running as Replica {self.replica_id} with database {self.order_file}")
        self.orders = []
        self.orders_map = {}
        self.transaction_id = 0
        self.lock = ReadWriteLock()
        self.load_orders()

        # Start periodic flushing to disk
        self.flush_thread = threading.Thread(target=self.periodic_flush, daemon=True)
        self.flush_thread.start()

    def load_orders(self):
        """
        Loads order data from the CSV file into memory and initializes the transaction ID.

        This function reads from the `order_file` (CSV file) and loads all existing orders into the `orders` list
        and `orders_map` dictionary. 
        In the code the following data fields have been used:
        `transaction_id`: Unique identifier for each order transaction.
        `stock_name`: The name of the stock involved in the order (e.g., "AAPL", "GOOGL").
        `order_type`: Type of the order (either "buy" or "sell").
        `quantity`: The number of stocks involved in the order.
        """
        try:
            self.lock.acquire_write()
            if os.path.exists(self.order_file):
                with open(self.order_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.orders.append({
                            'transaction_id': int(row['transaction_id']),
                            'stock_name': row['stock_name'],
                            'order_type': row['order_type'],
                            'quantity': int(row['quantity'])
                        })
                        self.orders_map[row['transaction_id']] = {
                            'transaction_id': int(row['transaction_id']),
                            'stock_name': row['stock_name'],
                            'order_type': row['order_type'],
                            'quantity': int(row['quantity'])
                        }
                    if self.orders:
                        self.transaction_id = max(order['transaction_id'] for order in self.orders) + 1
            else:
                with open(self.order_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=['transaction_id', 'stock_name', 'order_type', 'quantity'])
                    writer.writeheader()
        finally:
            self.lock.release_write()

    def flush_to_disk(self):
        """Write the order to disk"""
        with open(self.order_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['transaction_id', 'stock_name', 'order_type', 'quantity'])
            writer.writeheader()
            for order in self.orders:
                writer.writerow(order)

    def safe_flush_to_disk(self):
        try:
            self.lock.acquire_write()
            self.flush_to_disk()
        finally:
            self.lock.release_write()

    def periodic_flush(self):
        """Periodically flush data to disk"""
        try:
            while True:
                time.sleep(5)
                self.safe_flush_to_disk()
        except Exception as e:
            print(f"Exception in periodic_flush: {str(e)}")

    def HealthCheck(self, request, context):
        """Health check for the Order Service."""
        try:
            return order_pb2.HealthCheckResponse(success=True)                
        except Exception as e:
            return order_pb2.HealthCheckResponse(success=False)                
    
    def LookUpOrder(self, request, context):
        """
        Looks up an order by its transaction ID.

        Args:
            request: The incoming request containing the transaction ID.

        Returns:
            - A response containing the order details 
            - exists (bool): True if the order is found, False otherwise.
            - message (str): A message providing details about the result of the lookup.
        """
        try:
            self.lock.acquire_read()
            transactoin_id = request.transaction_id
            print(f"Order trancsaction Id {transactoin_id}")
            print(self.orders_map)
            print(str(transactoin_id) in self.orders_map)
            if str(transactoin_id) in self.orders_map:
                order = self.orders_map[str(transactoin_id)]
                print(order)
                return order_pb2.OrderLookUpResponse(
                    exists=True,
                    transaction_id=order['transaction_id'],
                    stock_name=order['stock_name'],
                    order_type = order['order_type'],
                    quantity=order['quantity']
                )
            else:
                return order_pb2.OrderLookUpResponse(exists=False, message="Order not found")
        except Exception as e:
            print(f"Error occurred during lookup: {str(e)}")
            return order_pb2.OrderLookUpResponse(exists=False, message=f"Error occurred during lookup: {str(e)}")
        finally:
            self.lock.release_read()
    
    def LatesttId(self, request, context):
        """Retrieves the latest transaction ID."""
        try: 
            return order_pb2.LatestOrderResponse(success=True, transaction_id=self.transaction_id)
        except Exception as e:
            return order_pb2.LatestOrderResponse(success=False)

    def BulkUpsert(self, request, context):
        """
        Performs a bulk upsert of orders into the system.

        Args:
            request: The incoming request containing the list of orders to upsert.

        Returns:
            - success (bool): True if the bulk upsert was successful, False otherwise.
            - message (str): A message providing more details about the operation.
        """
        try:
            data = request.data
            self.lock.acquire_write()

            for order in data:
                if str(order.transaction_id) not in self.orders_map:
                    self.orders.append({
                        'transaction_id': order.transaction_id,
                        'stock_name': order.stock_name,
                        'order_type': order.order_type,
                        'quantity': order.quantity
                    })
                    self.orders_map[str(order.transaction_id)] = order
            self.flush_to_disk()
            if data:
                self.transaction_id = max(self.transaction_id, data[-1].transaction_id)
            return order_pb2.BulkUpsertResponse(success=True, message=f"Replica {self.replica_id} updated successfully")
        except Exception as e:
            print(f"Error occurred during bulk upsert: {str(e)}")
            return order_pb2.BulkUpsertResponse(success=False, message=f"Error occurred during bulk upsert: {str(e)}")

        finally:
            # Ensure the write lock is always released
            self.lock.release_write()

    def LookUpOrdersById(self, request, context):
        """Fetches all orders with transaction IDs greater than the provided transaction ID."""
        try:
            transaction_id = request.transaction_id
            orders_after = []

            self.lock.acquire_read()

            for order in self.orders:
                if order['transaction_id'] > transaction_id:
                    orders_after.append(order_pb2.OrderSyncRequest(
                        transaction_id=order['transaction_id'],
                        stock_name=order['stock_name'],
                        order_type=order['order_type'],
                        quantity=order['quantity']
                    ))

            self.lock.release_read()

            if not orders_after:
                return order_pb2.LookUpByIdResponse(exists=False, message = f"No new order present after {transaction_id}")

            return order_pb2.LookUpByIdResponse(exists=True, data=orders_after)
        except Exception as e:
            return order_pb2.LookUpByIdResponse(exists=False, message = f"Error while fetching orders after transaction_id {transaction_id}: {str(e)}")

    def SyncOrder(self, request, context):
        """
        Syncs a new order to the replica if it's not already present.
        
        Args:
            request : The request containing order details (transaction ID, stock name, order type, and quantity) to be synchronized.

        Returns:
            success (bool): True if the order was synced successfully or was already in sync.
            message (str): A message describing the outcome.
        """
        
        transaction_id = request.transaction_id
        stock_name = request.stock_name
        order_type = request.order_type
        quantity = request.quantity

        if str(transaction_id) not in self.orders_map:
            try:
                self.lock.acquire_write()
                new_order = {
                    'transaction_id': transaction_id,
                    'stock_name': stock_name,
                    'order_type': order_type,
                    'quantity': quantity
                }
                self.orders.append(new_order)
                self.orders_map[str(transaction_id)] = new_order
                self.transaction_id = transaction_id
                self.flush_to_disk()
            finally:
                self.lock.release_write()
            return order_pb2.OrderSyncResponse(success=True, message=f"Order Replica {self.replica_id} synced successfully")
        else:
            return order_pb2.OrderSyncResponse(success=True, message=f"Order Replica {self.replica_id} was already in sync")
        
    def PlaceOrder(self, request, context):
        """
        Processes a stock order (buy/sell), verifies stock availability, and updates the Catalog service.
        
        Args:
            request: The request containing stock details (name, order type, quantity).

        Returns:
            transaction_id (int): The unique identifier for the order transaction.
            success (bool): Indicates whether the order was successfully placed.
            message (str): A message describing the outcome.
            
        """
        stock_name = request.stock_name
        order_type = request.order_type
        quantity = request.quantity

        try:
            with grpc.insecure_channel(f'localhost:50052') as channel:
                catalog_stub = catalog_pb2_grpc.CatalogServiceStub(channel)
                stock_request = catalog_pb2.LookupRequest(name=stock_name)
                stock_response = catalog_stub.LookupStock(stock_request)

                if not stock_response.exists:
                    return order_pb2.OrderResponse(success=False, message="Stock not found", transaction_id=-1)

                if order_type == "buy" and stock_response.quantity < quantity:
                    return order_pb2.OrderResponse(success=False, message="Insufficient stock", transaction_id=-1)

                update_request = catalog_pb2.UpdateRequest(
                    name=stock_name,
                    quantity_change=(-quantity if order_type == "buy" else quantity)
                )
                update_response = catalog_stub.UpdateStock(update_request)
                if not update_response.success:
                    return order_pb2.OrderResponse(success=False, message=update_response.message, transaction_id=-1)

            # Proceed with placing order
            try:
                self.lock.acquire_write()
                transaction_id = self.transaction_id
                self.transaction_id += 1

                new_order = {
                    'transaction_id': transaction_id,
                    'stock_name': stock_name,
                    'order_type': order_type,
                    'quantity': quantity
                }
                self.orders.append(new_order)
                self.orders_map[str(new_order['transaction_id'])] = new_order
                self.flush_to_disk()
            finally:
                self.lock.release_write()

            return order_pb2.OrderResponse(success=True, message="Order placed successfully", transaction_id=transaction_id)

        except grpc.RpcError as e:
            return order_pb2.OrderResponse(success=False, message=f"gRPC error: {e.details()}", transaction_id=-1)


def serve():
    try:
        parser = argparse.ArgumentParser(description="Order Service Replica")
        parser.add_argument("--replica_id", type=int, required=True, help="Replica ID")

        args = parser.parse_args()
          # for local run from service folder (not bash script) update to ../data/order_database.csv 
        order_file = f'data/order_database_{args.replica_id}.csv'
        print(order_file)

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=50))
      
        order_pb2_grpc.add_OrderServiceServicer_to_server(OrderServiceImpl(order_file, args.replica_id), server)

        server.add_insecure_port(f'0.0.0.0:500{args.replica_id + 53}')  # For each replica, use a unique port
        server.start()
        print(f"Order service Replica {args.replica_id} started on port 500{args.replica_id + 53}")
        
        server.wait_for_termination()
    except Exception as e:
        print(f"Server failed to start: {str(e)}")
        raise

if __name__ == '__main__':
    serve()
