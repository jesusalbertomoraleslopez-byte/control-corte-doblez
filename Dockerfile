FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
ENV GCS_BUCKET=sigrama-corte-doblez-storage
EXPOSE 8080

HEALTHCHECK CMD curl --fail http://localhost:${PORT}/_stcore/health || exit 1

ENTRYPOINT ["sh", "-c", "streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false --server.fileWatcherType=none --browser.gatherUsageStats=false"]
