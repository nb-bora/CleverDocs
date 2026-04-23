FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./

# Install dependencies (simple pip install to keep Dockerfile minimal)
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e . || true

COPY app ./app

COPY start_hf.sh /app/start_hf.sh
RUN chmod +x /app/start_hf.sh

EXPOSE 7860

CMD ["/app/start_hf.sh"]

