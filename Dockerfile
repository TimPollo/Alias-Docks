FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system aliasdock && useradd --system --gid aliasdock --home-dir /app aliasdock \
    && mkdir -p /data && chown aliasdock:aliasdock /data
COPY server/ ./server/
COPY static/ ./static/
USER aliasdock
EXPOSE 8000 2525
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=4)' || exit 1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
