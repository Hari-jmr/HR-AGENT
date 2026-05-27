FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies from lock file for reproducible builds
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Copy application files
COPY app.py .
COPY backend/ backend/

EXPOSE 5000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "5000"]
