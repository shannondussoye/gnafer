# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies for psycopg2-binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ src/
COPY sql/ sql/
COPY data/Authority_Code_STREET_TYPE_AUT_psv.psv data/

# Default port
EXPOSE 8000

# Run the API server
CMD ["uv", "run", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
