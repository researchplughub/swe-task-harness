# Use a official lightweight Python base image
FROM python:3.10-slim

# Install system dependencies, including Git and compilation tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up the workspace directory
WORKDIR /app

# Copy the harness source files and configuration
COPY pyproject.toml .
COPY harness/ ./harness/
COPY README.md .

# Install the swe-task-harness package and development dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Create volume mount points for cloning repositories and writing logs
RUN mkdir -p /app/workspace /app/venv_cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV WORKSPACE_DIR=/app/workspace
ENV VENV_CACHE_DIR=/app/venv_cache

# Define the entrypoint to run the cli tool directly
ENTRYPOINT ["swe-harness"]
CMD ["--help"]
