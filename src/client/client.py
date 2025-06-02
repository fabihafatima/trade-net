"""
Client script to simulate concurrent requests to a stock trading system.

- Sends concurrent GET/POST requests to the frontend (either local or AWS).
- Measures latency of lookup, trade, and order lookup operations.
- Varies trade probability `p` (0-80%) and logs performance for each setting.
- Results are saved as CSV files in `../tests/output/` for each `p` value.
"""

import requests
import random
import time
import threading
import csv
import os

# for local testing uncomment the line below
# FRONTEND_URL = "http://localhost:8081"

# for AWS testing, use the public IP of your EC2 instance FRONTEND_URL = "http://<Public DNS for EC2>:8081 e.g:"
FRONTEND_URL = "http://13.218.239.0:8081"

CATALOG_FILE = "../data/catalog_database.csv"
NUM_CLIENTS = 5
NUM_ITERATIONS = 20
P_VALUES = [0.0, 0.2,  0.4, 0.6, 0.8]  # Trade probabilities
OUTPUT_DIR = "../../tests/output"

# Lock to avoid write collisions when multiple threads append results
lock = threading.Lock()

#  Reads the stock names from the catalog CSV file and returns them as a list.
def load_catalog(file_path):
    stocks = []
    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)  
        for row in reader:
            if row:
                stocks.append(row[0].strip())
    return stocks

def run_client(p_value, client_id, catalog, result_list):
    """
    Each client thread simulates a mix of stock lookups and trades based on the given p-value.
    Records latency for each operation and stores the results in a shared list.
    """
    local_results = []

    for _ in range(NUM_ITERATIONS):
        stock = random.choice(catalog)

        # --- Stock Lookup ---
        start = time.time()
        try:
            r = requests.get(f"{FRONTEND_URL}/stocks/{stock}")
            r.raise_for_status()
            print(f"[Client {client_id}] Lookup successful for {stock}")
        except Exception as e:
            print(f"[Client {client_id}] Lookup failed: {e}")
        latency = round(time.time() - start, 4)
        local_results.append([client_id, p_value, "lookup", stock, latency])

        # --- Conditional Trade ---
        if random.random() < p_value:
            payload = {"name": stock, "type": "buy", "quantity": 1}
            start = time.time()
            try:
                r = requests.post(f"{FRONTEND_URL}/orders", json=payload)
                r.raise_for_status()
                txn_id = r.json()["data"].get("transaction_id")
            except Exception as e:
                print(f"[Client {client_id}] Trade failed: {e}")
                txn_id = None
            latency = round(time.time() - start, 4)
            local_results.append([client_id, p_value, "trade", stock, latency])

            # --- Order Lookup ---
            if txn_id:
                start = time.time()
                try:
                    r = requests.get(f"{FRONTEND_URL}/orders/{txn_id}")
                    r.raise_for_status()
                except Exception as e:
                    print(f"[Client {client_id}] Order lookup failed: {e}")
                latency = round(time.time() - start, 4)
                local_results.append([client_id, p_value, "order_lookup", stock, latency])

        time.sleep(0.2)  # brief pause to simulate realistic gaps

    # Append results to shared list safely
    with lock:
        result_list.extend(local_results)

def run_experiment(p_value, catalog):
    """
    Launches multiple threads to simulate concurrent clients performing operations 
    with a specific trade probability (p_value).
    Once done, writes the latency results to a CSV file.
    """
    print(f"\n=== Running with p = {p_value} ===")
    threads = []
    results = []

    for i in range(NUM_CLIENTS):
        t = threading.Thread(target=run_client, args=(p_value, i, catalog, results))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # Make sure the output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Write the collected results to a CSV file
    filename = f"latency_lru_{int(p_value * 100)}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["client_id", "p_value", "operation", "stock", "latency_seconds"])
        writer.writerows(results)

    print(f"Saved results to {filepath}")

def main():
    """
    Loads the stock catalog and runs the experiment for each specified p-value.
    """
    catalog = load_catalog(CATALOG_FILE)
    if not catalog:
        print("Error: No stock names found in catalog file.")
        return

    print(f"Loaded {len(catalog)} stocks from catalog.")
    for p in P_VALUES:
        run_experiment(p, catalog)

if __name__ == "__main__":
    main()
