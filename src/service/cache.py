from collections import OrderedDict
import threading

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

class Cache:
    def __init__(self, max_size):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = ReadWriteLock()

    def get_cache(self, stock_name):
        """Check if stock is present in cache it will return it"""
        self.lock.acquire_read()
        try:
            if stock_name in self.cache:
                print(f"[Cache HIT] {stock_name}")
                self.cache.move_to_end(stock_name) 
                return self.cache[stock_name]
            print(f"[Cache MISS] {stock_name}")
            return None
        finally:
            self.lock.release_read()

    def update_cache(self, stock_name, stock_details):
        """Add stock data to cache and apply eviction if needed."""
        self.lock.acquire_write()
        try:
         if stock_details is not None:
            if stock_name in self.cache:
                self.cache.move_to_end(stock_name)
                print(f"[Cache UPDATE] Added {stock_name}, Cache Keys: {list(self.cache.keys())}")
            self.cache[stock_name] = stock_details
        
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
        finally:
            self.lock.release_write()
        

    def invalidate_stock(self, stock_name):
        """Remove stock from cache (invalidated)."""
        self.lock.acquire_write()
        try:
            if stock_name in self.cache:
                del self.cache[stock_name]
                print(f"[Cache INVALIDATE] Removed {stock_name}")
        finally:
            self.lock.release_write()