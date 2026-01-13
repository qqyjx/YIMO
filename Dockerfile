# YIMO Web Application Dockerfile
FROM python:3.11-slim

LABEL maintainer="YIMO Project"
LABEL description="YIMO - Universal Lifecycle Ontology Manager"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV HF_HOME=/app/models

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY webapp/ ./webapp/
COPY scripts/ ./scripts/
COPY mysql-local/ ./mysql-local/
COPY DATA/ ./DATA/

# Create directories
RUN mkdir -p /app/models /app/outputs

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command
WORKDIR /app/webapp
CMD ["python", "app.py"]
