FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
