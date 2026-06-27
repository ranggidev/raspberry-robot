#!/bin/bash
# Start robot-eyes with display + audio access
xhost +local:docker 2>/dev/null
docker compose up "$@"
