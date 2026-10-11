FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "httpx>=0.27"
COPY common/ ./common/
COPY config/ ./config/
COPY scripts/ ./scripts/
ENV PYTHONUNBUFFERED=1
CMD ["python", "scripts/seed.py"]
