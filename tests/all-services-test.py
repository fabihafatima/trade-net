'''This script runs a basic end-to-end test for the stock trading system.
   It checks if stock info can be retrieved, an order can be placed,
   and if that order can be looked up by transaction ID.
'''

import requests
import time
import os

# Set the frontend URL (change this for AWS testing)
FRONTEND_URL = "http://localhost:8081"

# Try to fetch info for a specific stock (e.g., AAPL)
def test_query_stock(stock_name):
    print(f"\n[TEST] Query Stock: {stock_name}")
    resp = requests.get(f"{FRONTEND_URL}/stocks/{stock_name}")
    print(f"GET /stocks/{stock_name} - Status Code:", resp.status_code)
    print("Response:", resp.json())
    return resp.status_code == 200  # return True if successful

# Try to place a buy order for the stock
def test_place_order(stock_name, quantity):
    print(f"\n[TEST] Place Order: Buy {quantity} of {stock_name}")
    payload = {
        "name": stock_name,
        "type": "buy",
        "quantity": quantity
    }
    resp = requests.post(f"{FRONTEND_URL}/orders", json=payload)
    print("POST /orders - Status Code:", resp.status_code)
    print("Response:", resp.json())

    # If order is successful, return the transaction ID
    if resp.status_code == 200 and "data" in resp.json():
        return resp.json()["data"]["transaction_id"]
    return None  # return None if the order failed

# Lookup the order using its transaction ID
def test_lookup_order(txn_id):
    print(f"\n[TEST] Lookup Order: transaction_id={txn_id}")
    resp = requests.get(f"{FRONTEND_URL}/orders/{txn_id}")
    print(f"GET /orders/{txn_id} - Status Code:", resp.status_code)
    print("Response:", resp.json())

# Runs all tests in sequence: stock lookup → place order → lookup order
def run_all():
    stock = "AAPL"  # we’ll test using Apple stock
    if test_query_stock(stock):
        txn_id = test_place_order(stock, 2)
        if txn_id is not None:
            time.sleep(1)  # small wait to make sure the order gets registered
            test_lookup_order(txn_id)
            time.sleep(5)
            test_lookup_order("1200")  # test lookup with a dummy ID
        else:
            print("Order placement failed. Skipping order lookup.")
    else:
        print("Stock query failed. Skipping further tests.")

# Run everything when the script is executed
if __name__ == "__main__":
    run_all()
