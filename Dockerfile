"""Dockerfile for containerized deployment of travel planning agent."""

FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.13 \
    python3.13-venv \
    python3.13-dev \
    pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3.13 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY main.py .
COPY stategraph.py .
COPY agents/ ./agents/
COPY observability/ ./observability/
COPY evaluation/ ./evaluation/
COPY deployment/ ./deployment/
COPY keys.env .env

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ENABLE_PHOENIX_TRACING=true
ENV PHOENIX_ENDPOINT=http://phoenix:6006

# Expose ports
EXPOSE 8000 6006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command
CMD ["python", "main.py", "Plan a city trip", "--duration", "3"]
