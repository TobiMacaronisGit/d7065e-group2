# Build context = repository root (see docker-compose.yml) so that common/ and config/ are available.
FROM python:3.12-slim
WORKDIR /app
COPY physics/requirements.txt ./physics/requirements.txt
RUN pip install --no-cache-dir -r physics/requirements.txt
COPY common/ ./common/
COPY config/ ./config/
COPY physics/ ./physics/
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"
CMD ["python", "-m", "physics.main"]
