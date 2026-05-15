FROM python:3.12-slim

WORKDIR /app

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests
COPY pyproject.toml .
COPY uv.lock* ./

# Install production dependencies only
RUN uv sync --no-dev --locked

# Copy application source and prompt templates
COPY src/ src/
COPY prompts/ prompts/

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "stocktopus.main:app", "--host", "0.0.0.0", "--port", "8000"]
