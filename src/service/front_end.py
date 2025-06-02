from cache import Cache
import json
import http.server
import socketserver
import grpc
import concurrent.futures
import urllib.parse
import os  
import time
import threading

import catalog_pb2 as catalog_pb2
import catalog_pb2_grpc as catalog_pb2_grpc
import order_pb2 as order_pb2
import order_pb2_grpc as order_pb2_grpc

# Thread pool for handling requests
executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)

ENABLE_CACHE = True  # Set to False to test without cache
catalog_ip = os.environ.get("CATALOG_IP") if os.environ.get("CATALOG_IP") else "localhost"
order_ip = os.environ.get("ORDER_IP") if os.environ.get("ORDER_IP") else "localhost"

REPLICAS = [
    {"replica_id": 1, "address": "localhost:50054", "status":False},
    {"replica_id": 2, "address": "localhost:50055", "status":False},
    {"replica_id": 3, "address": "localhost:50056", "status":False}
]

global_cache = Cache(max_size=10)

class FrontendHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Extract the replicas and cache_size from kwargs
        self.replicas = kwargs.pop('replicas', None)

        # Initialize the cache with the cache_size
        self.cache = global_cache
        self.leader = None
        self.followers = []
        self.faulty_replicas = {}
        self.elect_leader()
        self.update_followers()
        # Call the parent class' constructor to set up the request handler
        super().__init__(*args, **kwargs)

        self.fault_check_thread = threading.Thread(target=self.periodic_faulty_replica_check, daemon=True)
        self.fault_check_thread.start()
        
    
    def elect_leader(self):
        """
            Elects a leader from the available replicas based on their health status.
            
            The replicas are sorted by replica_id in descending order. The leader is chosen from the first healthy replica.
            If no healthy replica is found, the election fails.
        """

        sorted_replicas = sorted(self.replicas, key=lambda x: x["replica_id"], reverse=True)
        for each_replica in sorted_replicas:
            print(each_replica)
            if self.health_check(each_replica):
                self.leader = each_replica
                each_replica["status"] = True
                print(f"Elected Leader - {each_replica['replica_id']}")
                return
        print("All the Order Service Replicas are unresponsive, cannot select the leader")
        
    def update_followers(self):
        """
        Updates the list of follower replicas by checking the health of each replica.
        
        This function iterates through all the replicas (except the leader) and checks their health status.
        If the replica is healthy, it is added to the followers list. If not, the replica's status is marked as False.
        """
        self.followers = []
        for each_replica in self.replicas:
             if each_replica["replica_id"] != self.leader["replica_id"]:
                if self.health_check(each_replica):
                    self.followers.append(each_replica)
                    each_replica["status"] = True
                else:
                    each_replica["status"] = False
        print(self.replicas)

    def periodic_faulty_replica_check(self):
        while True:
            self.check_and_update_faulty_replicas()

    def check_and_update_faulty_replicas(self):   
        """
        Checks the status of faulty replicas and attempts to sync them with the leader if they become healthy.

        This function identifies inactive replicas (faulty) from the list of replicas and checks if they are healthy again.
        If a replica becomes healthy, it is synced with the leader using the sync function. If syncing is successful, 
        the replica's status is updated to active, and the followers list is refreshed.
        """ 
        inactive_replicas = [replica for replica in REPLICAS if not replica["status"]]
        
        for each_inactive_replica in inactive_replicas:
            if(self.health_check(each_inactive_replica)):
                if self.sync_faulty_replica(each_inactive_replica):
                    print(f" Faulty Replica {each_inactive_replica['replica_id']} synced successfully.")
                    each_inactive_replica['status']  = True
                    self.update_followers()
                else:
                    print(f"Failed to sync faulty replica {each_inactive_replica['replica_id']}.")
            else:
                print(f"Replica {each_inactive_replica['replica_id']} is unresponsive.")

    def sync_faulty_replica(self, replica):
        """
        Attempts to sync a faulty replica with the leader's data.

        Args:
            replica: The replica to be synced.

        Returns:
            bool: True if the replica was successfully synced, False otherwise.
        """
        try:
            latest_transaction_id = self.get_latest_transaction_id(replica)
            if latest_transaction_id is not None:
                orders_to_sync = self.get_orders_to_sync(latest_transaction_id)
                return self.bulk_upsert_to_replica(replica, orders_to_sync)
            else:
                return False
        except grpc.RpcError as e:
            print(f"Error syncing replica {replica['replica_id']}: {e.details()}")
            return False
    
    def get_latest_transaction_id(self, replica):
        """
        Retrieves the latest transaction ID from a given replica.

        Args:
            replica (dict): The replica from which the latest transaction ID is to be retrieved.

        Returns:
            int or None: The latest transaction ID if the request is successful, None if the request fails.
        """
        with grpc.insecure_channel(replica["address"]) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel)
            request = order_pb2.LookUpByIdRequest()
            response = stub.LatesttId(request)
            if response.success:
                return response.transaction_id
            else:
                print(f"Failed to get latest transaction ID from replica {replica['replica_id']}.")
                return None

    def get_orders_to_sync(self, latest_transaction_id):
        """
        Retrieves the orders that need to be synced with the replica, starting from the given transaction ID.

        Args:
            latest_transaction_id (int): The transaction ID after which the orders need to be synced.

        Returns:
            list: A list of orders that need to be synced with the replica. An empty list is returned if no new orders are found.
        """
        with grpc.insecure_channel(self.leader["address"]) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel)
            update_request = order_pb2.LookUpByIdRequest(transaction_id=latest_transaction_id)
            response = stub.LookUpOrdersById(update_request)
            if response.exists:
                return response.data
            else:
                print(f"No orders to sync after transaction ID {latest_transaction_id}.")
                return []

    def bulk_upsert_to_replica(self, replica, orders_to_sync):
        """
        Syncs the orders to a given replica by performing a bulk upsert operation.

        Args:
            replica (dict): The replica to which the orders will be synced. 
            orders_to_sync (list): A list of orders that need to be synced to the replica.

        Returns:
            bool: Returns `True` if the orders were successfully synced, `False` otherwise.
        """
        try:
            with grpc.insecure_channel(replica["address"]) as channel:
                stub = order_pb2_grpc.OrderServiceStub(channel)
                update_request = order_pb2.BulkUpsertRequest(data=orders_to_sync)
                response = stub.BulkUpsert(update_request)
                return response.success
        except grpc.RpcError as e:
            print(f"Failed to bulk upsert orders to replica {replica['replica_id']}: {e.details()}")
            return False
    
    def health_check(self, replica):
        """
        Performs a health check on the given replica by sending a HealthCheck request.

        Args:
            replica (dict): The replica to be checked. It contains the replica's address.

        Returns:
            bool: Returns `True` if the replica is healthy, `False` otherwise.
        """
        address = replica['address'] if replica else "localhost:50054"
        try:
            with grpc.insecure_channel(address) as channel:
                stub = order_pb2_grpc.OrderServiceStub(channel)
                health_check_request = order_pb2.HealthCheckRequest()
                response = stub.HealthCheck(health_check_request)
                return response.success
        except grpc.RpcError as e:
            print(f"Order Service error {e.details()}")
            return False

    def do_GET(self):
        """
            GET API for lookUp based on a stock name

            API Args:
                stock_name: The name of stock for which information is needed

            Returns:
                json of data i.e. name, price, quantity of stock
                example of data -
                "data": {
                    "name": "GameStart",
                    "price": 15.99,
                    "quantity": 100
                }
            
            GET API for lookUp based on a order id

            API Args:
                order_id: The id of order for which information is needed

            Returns:
                json of data i.e. number, prinamece, type, quantity
                example of data -
                "data": {
                    "number":5,
                    "name": "NFLX",
                    "type": "buy",
                    "quantity": 20
                }
        """
        
        try:
            path_parts = self.path.split('/')
            if "/stocks" in self.path:
                if len(path_parts) == 3 and path_parts[1] == 'stocks':
                    # Decode the URL-encoded string (e.g., converts 'Stock%20A' to 'Stock A')
                    stock_name = urllib.parse.unquote(path_parts[2]) 
                    
                    self.handle_cache(stock_name)

                else:
                    self.send_error_response(404, "Stock not found")
            elif  "/orders" in self.path: 
                if len(path_parts) == 3:
                    try:
                        order_id = int(path_parts[2])
                        print(order_id)
                        self.handle_order_lookup(order_id)
                    except ValueError:
                        self.send_error_response(400, "Order ID must be an integer")
                    
                else:
                    self.send_error_response(404, "Order Id variable not found")


            else: 
               self.send_error_response(404, "Endpoint not found") 
        except Exception as e:
            self.send_error_response(500, f"Internal server error: {str(e)}")
    
    def do_POST(self):
        """
        POST API to update stock in database(csv sheet)
            API payload: 
                {
                    "name": "GameStart", 
                    "quantity": 1,
                    "type": "sell"
                }
            Returns:
                {
                    "data": {
                        "transaction_number": 10
                    }
                } 

        """
        try:
            if self.path == "/orders":
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                order_request = json.loads(post_data)

                stock_name = order_request.get("name")
                quantity = order_request.get("quantity")
                type = order_request.get("type")

                if not stock_name or not isinstance(quantity, int) or quantity <= 0:
                    self.send_error_response(400, "Invalid order request")
                    return

                self.handle_order(stock_name, quantity, type)
            else:
                self.send_error_response(404, "Endpoint not found")
        except Exception as e:
            self.send_error_response(500, f"Internal server error: {str(e)}")
    
    def handle_stock_lookup(self, stock_name):
        """
            Connect to the catalog service using gRPC and fetches data

            Args:
                stock_name: The name of stock for which information is needed

            Returns:
                stock details needed in json format
        """
        with grpc.insecure_channel(f'localhost:50052') as channel:
            stub = catalog_pb2_grpc.CatalogServiceStub(channel)
            request = catalog_pb2.LookupRequest(name=stock_name)
            
            try:
                response = stub.LookupStock(request)
                if response.exists:
                    # Stock found, return details
                    return {
                        "data": {
                            "name": response.name,
                            "price": response.price,
                            "quantity": response.quantity
                        }
                    }
                else:
                    # Stock not found
                    self.send_error_response(404, "Stock not found")
            except grpc.RpcError as e:
                self.send_error_response(500, f"Catalog service error: {e.details()}")


    def handle_cache(self, stock_name):
        """
            Handles stock lookup, either returning the cached data or performing a fresh lookup.

            Args:
                stock_name (str): The name of the stock for which data is needed.

            Returns:
                dict: The stock details in JSON format, sent back in a successful response.
        """
        print(f"[DEBUG] Handle cache called for {stock_name}")
        if ENABLE_CACHE and stock_name in self.cache.cache:
            print(f"[DEBUG] Cache HIT for {stock_name}")
        else:
            print(f"[DEBUG] Cache MISS for {stock_name}")

        start_time = time.time()
        stock_details = self.cache.get_cache(stock_name)
        if stock_details:
            print(f"[DEBUG] Returning cached data for {stock_name}")
            return self.send_success_response(stock_details)

        stock_details = self.handle_stock_lookup(stock_name)
        print(f"[DEBUG] gRPC catalog call for {stock_name} took {time.time() - start_time:.2f}s")
        self.cache.update_cache(stock_name, stock_details)
        return self.send_success_response(stock_details)



    def handle_order_lookup(self, transaction_id):
        """
            Connect to the order service using gRPC and fetches data

            Args:
                transaction_id: The order_id of order for which information is needed

            Returns:
                order details needed in json format
        """
        address = self.leader["address"] if self.leader else "localhost:50054"
        print(address)
        with grpc.insecure_channel(address) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel)
            request = order_pb2.OrderLookUpRequest(transaction_id=transaction_id)

            try:
                response = stub.LookUpOrder(request)
                print(response)
                if response.exists:
                    self.send_success_response({"data" : {
                        "transaction_id": response.transaction_id,
                        "name": response.stock_name,
                        "type": response.order_type, 
                        "quantity": response.quantity
                    }})
                else:
                    self.send_error_response(404, getattr(response, "message", "Order not found"))
            except grpc.RpcError as e:
                print(f"gRPC error during order lookup: {e.details()} (code: {e.code()})")

                if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]:
                    print("Leader appears unavailable — triggering leader election.")
                    self.elect_leader()
                    self.update_followers()

                    if self.leader:
                        self.handle_order_lookup(transaction_id)
                    else:
                        self.send_error_response(500, "Leader election failed")
                else:
                    # This means the leader is alive but returned some gRPC error (e.g., internal logic issue)
                    self.send_error_response(500, f"Order service error: {e.details()}")

                
    def handle_order(self, stock_name, quantity, type):
        """
            Connects to the order service using gRPC and processes the order.

            Args: 
                stock_name: name of the stock for which order is placed

                quantity: quantity of the stock

                type: action to take for the stock either buy it or sell it 

            Returns:
                transaction_id as needed in json format
        """
        # Use the order_ip in the connection string
        address = self.leader["address"] if self.leader else "localhost:50054"
        with grpc.insecure_channel(address) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel)
            request = order_pb2.OrderRequest(stock_name=stock_name, quantity=quantity, order_type=type)
            try:
                response = stub.PlaceOrder(request)
                if response.success:
                    print(f"Cache - {dict(self.cache.cache)}")
                    print("Invalidating Cache...")
                    self.cache.invalidate_stock(stock_name)
                    print(f"Cache - {dict(self.cache.cache)}")
                    self.update_order_followers(response.transaction_id, stock_name, quantity, type)
                    self.send_success_response({
                        "data": {
                            "transaction_id": response.transaction_id
                        }
                    })
                else:
                    self.send_error_response(400, response.message)
            except grpc.RpcError as e:
                print(f"gRPC error during place order: {e.details()}")
                if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]:
                    self.elect_leader()
                    self.update_followers()
                    if self.leader:
                        self.handle_order(stock_name, quantity, type)
                    else:
                        self.send_error_response(500, "Leader election failed")
                else:
                    # This means the leader is alive but returned some gRPC error (e.g., internal logic issue)
                    self.send_error_response(500, f"Order service error: {e.details()}")


    def update_order_followers(self, transaction_id, stock_name, quantity, type):
        """
        Updates the order information on all follower replicas after a new order is placed.

        Args:
            transaction_id (int): The unique ID of the order that was just placed.
            stock_name (str): The name of the stock that was involved in the order.
            quantity (int): The quantity of the stock that was traded.
            type (str): The type of the order (either "buy" or "sell").

        Returns:
            None: This function does not return a value but sends error responses as needed.
        """
        for each_follower in self.followers:
            if(self.health_check(each_follower)):
                with grpc.insecure_channel(each_follower["address"]) as channel:
                    stub = order_pb2_grpc.OrderServiceStub(channel)
                    request = order_pb2.OrderSyncRequest(transaction_id= transaction_id, stock_name=stock_name, quantity=quantity, order_type=type)
                    try:
                        response = stub.SyncOrder(request)
                        if response.success:
                            print(f"Order service replica {each_follower['replica_id']} updated")
                        else:
                            print(f"Order service replica {each_follower['replica_id']} updatation failed")

                    except grpc.RpcError as e:
                        self.send_error_response(500, f"Order service replica {each_follower['replica_id']} error: {e.details()}")
            else:
                for each_replica in self.replicas:
                    if(each_replica["replica_id"] ==  each_follower["replica_id"]):
                        each_replica["status"] = False

    def send_success_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response = {
            "error": {
                "code": code,
                "message": message
            }
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

def run_server(port):
    handler = lambda *args, **kwargs: FrontendHandler(*args, replicas=REPLICAS, **kwargs)
    server = ThreadedHTTPServer(("", port), handler)
    print(f"Front-end service started on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    SERVER_PORT = 8081
    run_server(SERVER_PORT)


