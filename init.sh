#!/bin/bash

sleep 5
if [ ! "$(ls -A /app/alembic/versions)" ]; then
    echo "no files"
    alembic revision --autogenerate -m "Start"
    alembic upgrade head
fi


uvicorn main:app --host 0.0.0.0 --port 8000 --reload
