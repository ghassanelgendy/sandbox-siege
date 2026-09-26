FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and source code
COPY pyproject.toml .
COPY siege ./siege

# Install python dependencies and package
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

EXPOSE 18000

ENV PORT=18000
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/runs

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD curl -f http://localhost:18000/api/health || exit 1

CMD ["uvicorn", "siege.main:app", "--host", "0.0.0.0", "--port", "18000"]
