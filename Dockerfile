FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -m -u 1000 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8080
# One worker on purpose: git commits and indexing are serialized with DB advisory locks,
# so you can raise --workers later, but start simple.
CMD ["sh", "-c", "uvicorn app.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8080}"]
