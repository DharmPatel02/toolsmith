FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir pandas openpyxl

RUN useradd --create-home --shell /usr/sbin/nologin sandbox
WORKDIR /work
USER sandbox

ENTRYPOINT ["python", "/runner/bootstrap.py"]
