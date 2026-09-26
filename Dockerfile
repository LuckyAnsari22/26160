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

# Start the application
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
