
# 💹 Trade-Net Distributed Stock Exchange

## 💼 Project Overview

The Trade-Net Distributed Stock Exchange is a fault-tolerant, scalable trading platform designed to simulate a modern stock exchange system. Developed using microservices and cloud-native principles, Trade-Net supports real-time stock lookups, trade order placement, and robust failure handling.

This project includes:

* ⚡ Efficient stock lookups with **in-memory LRU caching**
* 🔁 Consistent order processing using **leader-follower replication**
* 💥 Crash resilience with **automatic failover and replica recovery**
* ☁️ Seamless deployment on **AWS cloud infrastructure**
---

## 🧱 System Architecture

### Core Microservices:

1. **Frontend Service**

   * Exposes REST APIs for clients:

     * `GET /stocks/<stock_name>`
     * `POST /orders`
     * `GET /orders/<order_number>`
   * Manages cache and leader coordination.

2. **Catalog Service**

   * Stores stock data with initial volume = 100 units for each of the 10+ stocks.

3. **Order Service**

   * Runs in 3 replicas: 1 leader, 2 followers.
   * Handles trade/order processing and synchronization.

All services communicate over gRPC or REST and support concurrent requests.

---

## 🚀 Features

### ✅ Caching

* Frontend uses an **LRU cache** for stock lookups.
* Invalidated via server-push from the catalog on updates.
* Cache size is configurable and intentionally smaller than the stock set.

### ✅ Replication

* Three order service replicas run in parallel.
* **Leader is selected based on highest available ID.**
* Only the leader handles requests; followers sync after every successful order.

### ✅ Fault Tolerance

* Leader crash triggers automatic **re-election** by frontend.
* Recovered replicas pull missed orders from other replicas.
* Crash-recovery ensures **no data loss** and **continued availability**.

### ✅ Cloud Deployment & Evaluation

* All microservices run as **containers/processes on a single AWS EC2 instance**.
* Clients simulate trades from local machines.
* Performance evaluated for varying trade probabilities (`p` from 0 to 0.8).
* Latency plotted with and without caching.
* Crash recovery and **cache replacement behavior** (via LRU) tested and logged.

---

## 🧪 How to Run

```bash
# 1. Start catalog service
cd services/catalog
python3 catalog_server.py

# 2. Start order replicas
cd ../order
python3 order_server.py --id=1
python3 order_server.py --id=2
python3 order_server.py --id=3

# 3. Start frontend service
cd ../frontend
python3 frontend_server.py --cache_size=10

# 4. Run client with trade probability p
cd ../../client
python3 client.py --p=0.6 --iterations=20
```

---

## 📁 Directory Structure

```
├── client/               # Client logic for testing trades
├── frontend/             # REST API + cache + leader coordination
├── catalog/              # Stock catalog service
├── order/                # Replicated order services            
├── docs/                 # Design, output, and evaluation documents
│   ├── design_doc.pdf
│   ├── output_screenshots.pdf
│   ├── evaluation.pdf
└── README.md
```

---

## 📊 Evaluation Summary

* **Latency vs p (0 to 0.8)**: Plots included in `evaluation.pdf`
* **Caching Results**: Up to 40% latency reduction with cache enabled
* **LRU Cache Behavior**: Demonstrated with replacement logs
* **Crash Recovery**: Transparent to clients; leader failover successful

---

## 📚 References

* [Flask Web Framework](https://flask.palletsprojects.com/en/2.2.x/)
* [Model-View-Controller (MVC)](https://en.wikipedia.org/wiki/Model–view–controller)
* [Asterix Universe](https://en.wikipedia.org/wiki/Asterix)

