"""
This test script simulates concurrent clients accessing a stock trading system to evaluate
frontend cache behavior—specifically testing for cache hits, invalidation after order placement,
and LRU-based eviction. It sends GET and POST requests to the frontend API and logs responses.
"""

import threading
import time
import requests
import random
import os

# Use this URL for local testing — update if testing on AWS
FRONTEND_URL = "http://localhost:8081"

# Helper function to print the status and response (if available)
def log_response(response):
    print(f"[{threading.current_thread().name}] Status Code: {response.status_code}")
    try:
        print(f"[{threading.current_thread().name}] Response:", response.json())
    except Exception as e:
        print(f"[{threading.current_thread().name}] Error reading response:", e)

# Check if the cache actually stores results after the first request
def test_cache_hit_miss(stock_name):
    print(f"\n[{threading.current_thread().name}] TEST: Cache HIT and MISS")
    
    # First call — should be a miss (i.e., fetched from backend)
    r1 = requests.get(f"{FRONTEND_URL}/stocks/{stock_name}")
    log_response(r1)
    
    time.sleep(1)  # wait a bit
    
    # Second call — should be a hit (i.e., returned from cache)
    r2 = requests.get(f"{FRONTEND_URL}/stocks/{stock_name}")
    log_response(r2)

# Make a request and then place an order to see if the cache gets invalidated
def test_cache_invalidation(stock_name):
    print(f"\n[{threading.current_thread().name}] TEST: Cache Invalidation on Order")
    
    # Cache gets populated
    requests.get(f"{FRONTEND_URL}/stocks/{stock_name}")
    
    # Placing an order — this should invalidate the cache entry
    order_payload = {"name": stock_name, "type": "buy", "quantity": 1}
    resp = requests.post(f"{FRONTEND_URL}/orders", json=order_payload)
    log_response(resp)
    
    time.sleep(1)
    
    # After the order, this should *not* be a cache hit
    r = requests.get(f"{FRONTEND_URL}/stocks/{stock_name}")
    log_response(r)

# Fill up the cache with dummy stock names and check if older entries get evicted (LRU)
def test_cache_eviction():
    print(f"\n[{threading.current_thread().name}] TEST: Cache LRU Eviction")
    
    # Hit the cache with 12 different stocks (assuming cache can only hold 10)
    stocks = [f"STOCK{i}" for i in range(12)]
    for stock in stocks:
        requests.get(f"{FRONTEND_URL}/stocks/{stock}")
        time.sleep(0.2)  # small delay
    
    # Now request the first stock again — it should have been evicted if LRU is working
    r = requests.get(f"{FRONTEND_URL}/stocks/STOCK0")
    log_response(r)

# What each client does — run all the tests with a random stock
def client_worker(client_id):
    stock = random.choice(["AAPL", "GOOGL", "AMZN", "META"])
    test_cache_hit_miss(stock)
    test_cache_invalidation(stock)
    test_cache_eviction()

if __name__ == "__main__":
    # Launch two clients at the same time to test concurrency
    client1 = threading.Thread(target=client_worker, args=(1,), name="Client-1")
    client2 = threading.Thread(target=client_worker, args=(2,), name="Client-2")

    client1.start()
    client2.start()

    client1.join()
    client2.join()

    print("\nConcurrent cache tests completed.")
