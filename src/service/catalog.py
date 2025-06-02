import os

import csv
import threading
import time
import grpc
from concurrent import futures

import catalog_pb2 as catalog_pb2
import catalog_pb2_grpc as catalog_pb2_grpc


# Read-Write Lock implementation
class ReadWriteLock:
    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0
        
    def acquire_read(self):
        with self._read_ready:
            self._readers += 1
            
    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if not self._readers:
                self._read_ready.notify_all()
                
    def acquire_write(self):
        with self._read_ready:
            while self._readers > 0:
                self._read_ready.wait()
                
    def release_write(self):
        self._read_ready.acquire()
        self._read_ready.release()

class CatalogServiceImpl(catalog_pb2_grpc.CatalogServiceServicer):
    def __init__(self, catalog_file):
        self.catalog_file = catalog_file
        self.stocks = {}
        self.lock = ReadWriteLock()
        self.load_catalog()
        # Start periodic flushing to disk
        self.flush_thread = threading.Thread(target=self.periodic_flush, daemon=True)
        self.flush_thread.start()
    
    def load_catalog(self):
        """
        Load the catalog from disk file i.e. catalog_database.csv file
        In the code the following data fields have been used:
        name: name of the stock
        price: currrent price of the stock
        quantity: represents the number of shares of a particular stock that are currently available for trading. When someone buys shares, the quantity decreases and when someone sells shares, the quantity increases.
        volume: its a running counter that tracks the total number of shares that have been traded (both bought and sold) over time.
        """
        try:
            self.lock.acquire_write()
            if os.path.exists(self.catalog_file):
                with open(self.catalog_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.stocks[row['name']] = {
                            'name': row['name'],
                            'price': float(row['price']),
                            'quantity': int(row['quantity']),
                            'volume': int(row['volume'])
                        }
            else:
                with open(self.catalog_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=['name', 'price', 'quantity', 'volume'])
                    writer.writeheader()
                
                self.flush_to_disk()
        finally:
            self.lock.release_write()
        
    def flush_to_disk(self):
        """Write the catalog to disk"""
        try:
            self.lock.acquire_read()
            with open(self.catalog_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['name', 'price', 'quantity', 'volume'])
                writer.writeheader()
                for stock in self.stocks.values():
                    writer.writerow(stock)
        finally:
            self.lock.release_read()
            
    def periodic_flush(self):
        """Periodically flush data to disk"""
        while True:
            time.sleep(5)  # Flush every 5 seconds
            self.flush_to_disk()
    
    def LookupStock(self, request, context):
        """Looks up the stock in the catalog based on the provided stock name."""
        try:
            self.lock.acquire_read()
            stock_name = request.name
            if stock_name in self.stocks:
                stock = self.stocks[stock_name]
                return catalog_pb2.LookupResponse(
                    exists=True,
                    name=stock['name'],
                    price=stock['price'],
                    quantity=stock['quantity']
                )
            else:
                return catalog_pb2.LookupResponse(exists=False)
        finally:
            self.lock.release_read()
    
    def UpdateStock(self, request, context):
        """Updates the quantity of a stock in the catalog."""
        try:
            self.lock.acquire_write()
            stock_name = request.name
            quantity_change = request.quantity_change
            
            if stock_name not in self.stocks:
                return catalog_pb2.UpdateResponse(
                    success=False,
                    message="Stock not found",
                    new_quantity=0
                )
            
            stock = self.stocks[stock_name]
            new_quantity = stock['quantity'] + quantity_change
            
            if new_quantity < 0:
                return catalog_pb2.UpdateResponse(
                    success=False,
                    message="Insufficient stock",
                    new_quantity=stock['quantity']
                )
            
            # Update stock quantity
            stock['quantity'] = new_quantity
            
            # Update trading volume if buying or selling
            if quantity_change != 0:
                stock['volume'] += abs(quantity_change)
            
            # Immediate flush to disk after update
            self.flush_to_disk()
            
            return catalog_pb2.UpdateResponse(
                success=True,
                message="Stock updated successfully",
                new_quantity=new_quantity
            )
        finally:
            self.lock.release_write()


def serve():
    """
    Server code
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=50))
     # for local run update to ./data/catalog_database.csv 
    catalog_pb2_grpc.add_CatalogServiceServicer_to_server(
        CatalogServiceImpl('./data/catalog_database.csv'), server)
    server.add_insecure_port('0.0.0.0:50052')
    server.start()
    print("Catalog Service started on port 50052")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()