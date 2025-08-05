# Production Dockerfile for Loan Army Backend - Azure Container App Ready
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including curl for health checks)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ src/

# Copy documentation (optional)
COPY API_SECURITY.md .
COPY AZURE_DEPLOYMENT.md .

# Create non-root user for security (Azure Container Apps recommendation)
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port (Azure Container Apps will use this)
EXPOSE 5001

# Health check for Azure Container Apps health probes
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/api/auth/status || exit 1

# Run the application
CMD ["python", "src/main.py"]

# Environment variables will be set by Azure Container Apps:
# ADMIN_API_KEY - Your secure admin API key
# DB_HOST, DB_USER, DB_PASSWORD, DB_NAME - Database connection
# ADMIN_IP_WHITELIST - Optional IP restrictions
# API_FOOTBALL_KEY - Optional for real API data