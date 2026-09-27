# Stage 1: build the landing page (static output in /landing/dist)
FROM node:20-slim AS landing-build
WORKDIR /landing
COPY landing/package*.json ./
RUN npm ci
COPY landing/ ./
RUN npm run build

# Stage 2: the application image
FROM python:3.11-slim

WORKDIR /app

# Install OS dependencies for scapy
RUN apt-get update && \
    apt-get install -y libpcap-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy required application directories
COPY backend/ backend/
COPY frontend/ frontend/
COPY parser/ parser/
COPY ml_pipeline/ ml_pipeline/
COPY models/ models/
COPY data/ data/
COPY docs/assets/ docs/assets/
COPY --from=landing-build /landing/dist landing_dist/

# Start the application
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
