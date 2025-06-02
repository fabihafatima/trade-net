#!/bin/bash

# Ensure logs directory exists
mkdir -p logs

# Kill previously running services
echo "Stopping any previous Python services..."
pkill -f catalog.py
pkill -f order.py
pkill -f front_end.py

echo "Clearing old logs..."
rm -f logs/*.log

# Start catalog service
echo "Starting catalog service..."
python3 service/catalog.py > logs/catalog.log 2>&1 &

# Start order service replicas
echo "Starting order service replica 1..."
python3 service/order.py --replica_id=1 > logs/order_replica1.log 2>&1 &

echo "Starting order service replica 2..."
python3 service/order.py --replica_id=2 > logs/order_replica2.log 2>&1 &

echo "Starting order service replica 3..."
python3 service/order.py --replica_id=3 > logs/order_replica3.log 2>&1 &

# Start front end
echo "Starting front-end service..."
python3 service/front_end.py > logs/frontend.log 2>&1 &

echo "All services started. Check logs/ for output."
