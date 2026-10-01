FROM python:3.12-slim
WORKDIR /app
COPY pipeline/requirements.txt ./pipeline/requirements.txt
RUN pip install --no-cache-dir -r pipeline/requirements.txt
COPY common/ ./common/
COPY config/ ./config/
COPY pipeline/ ./pipeline/
ENV PYTHONUNBUFFERED=1 PORT=8000 DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"
CMD ["python", "-m", "pipeline.main"]
