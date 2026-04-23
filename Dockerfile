FROM python:3.11-slim

# Hugging Face Spaces Docker expectations (uid=1000, non-root)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies from requirements.txt (HF template style)
COPY --chown=user ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy the whole backend (includes alembic.ini + alembic/ + app/)
COPY --chown=user . /app

RUN chmod +x /app/start_hf.sh

# HF Spaces requires listening on 7860
EXPOSE 7860
CMD ["/app/start_hf.sh"]

