#!/bin/bash

echo "Stopping microservices running on specified ports..."

# List of ports to check and kill
ports=(8081 50052 50054 50055 50056)

for port in "${ports[@]}"; do
    pid=$(lsof -ti :"$port")
    if [ -n "$pid" ]; then
        echo "Killing process on port $port (PID: $pid)"
        kill -9 "$pid"
    else
        echo "No process running on port $port"
    fi
done
echo "All microservices have been stopped."
