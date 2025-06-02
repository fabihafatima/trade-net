## Code Setup

We configured our system with the following microservices all are in `src/service` folder:

* A **front_end service** exposing REST APIs and managing request routing.
* A **catalog service** managing stock metadata.
* An **order service**, replicated across three instances (replica1, replica2, replica3) for fault tolerance.

The **front_end service** also integrates an **LRU cache** to reduce latency during repeated stock lookups. This cache is automatically invalidated on stock updates (buys/sells).

## Note
We implemented a `service/` directory from the beginning to group the `front_end.py`, `catalog.py`, and `order.py` services together for simpler development and organization. The `client` code is placed separately in its own folder, aligning with the lab’s modularity guidelines (`src/client` folder). Since each service is fully modular within this structure as well, thus we did not attempt to restructure the code as per instructions of separate folder for `frontend`. 

## Prerequisites
- python version >=3.8
- pip/pip3 version compatible with python (20 or higher)
  
```bash
cd src/service  
pip install -r requirements.txt
```


## Start bash Script
To start all services simultaneously, we use the provided startup script:

```bash
cd src  
./run.sh  
```

This script:

* Starts the catalog service on port `50052`
* Launches three order replicas on ports `50054`, `50055`, and `50056`
* Starts the frontend service on port `8081`

*Figure 1: Terminal output during service initialization*
![Startup Screenshot](../docs/media/start-run.png)

---

## Stopping All Services

To cleanly shut down all running services, use the stop script:

```bash
cd src  
./stop.sh  
```

This script terminates:

* The frontend
* The catalog
* All three order replicas

*Figure 2: Terminal output after stopping services*
![Stop Screenshot](../docs/media/stop-terminal.png)

## AI Usage:

In this code:
- Few logs/print statements are added by Copilot
- Structuring of docs/Evaluation.md and docs/Output.md is through ChatGPT 
