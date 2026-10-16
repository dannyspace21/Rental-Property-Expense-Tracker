#!/bin/bash
cd "$(dirname "$0")"
docker compose up -d --build && open http://localhost:8080
