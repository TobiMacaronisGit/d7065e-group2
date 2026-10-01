FROM python:3.12-slim
WORKDIR /app
COPY planner/requirements.txt ./planner/requirements.txt
RUN pip install --no-cache-dir -r planner/requirements.txt
COPY common/ ./common/
COPY config/ ./config/
COPY physics/model.py ./physics/model.py
COPY physics/__init__.py ./physics/__init__.py
COPY planner/ ./planner/
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"
CMD ["python", "-m", "planner.main"]
