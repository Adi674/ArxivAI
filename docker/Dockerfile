# Multi-stage build for ArxivAI backend

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /tmp

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Pre-download ML models into the image so they are NEVER re-downloaded at runtime.
# cross-encoder/ms-marco-MiniLM-L-6-v2 (~22MB)  — reranker
# cross-encoder/nli-deberta-v3-small   (~170MB)  — hallucination checker
RUN python -c "\
from sentence_transformers import CrossEncoder; \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', max_length=512); \
CrossEncoder('cross-encoder/nli-deberta-v3-small', num_labels=3, max_length=512); \
print('Models cached successfully')"

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies (including downloaded spaCy model) from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/

# Set environment variables
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PYTHONWARNINGS="ignore::UserWarning:pydantic"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000