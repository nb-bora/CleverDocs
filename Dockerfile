FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./

# Install dependencies (simple pip install to keep Dockerfile minimal)
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e . || true

COPY app ./app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.interfaces.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

