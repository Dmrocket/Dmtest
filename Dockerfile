# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 1. Install system dependencies for Postgres and building C-extensions
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy requirements first (improves build speed via caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy only the backend code
# Since the Docker context in docker-compose is './backend', 
# '.' here refers to the contents of the backend folder.
COPY . .

# 4. Ensure the port is dynamic for Railway
# Note: We run main:app because the Dockerfile is now inside the backend folder
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}