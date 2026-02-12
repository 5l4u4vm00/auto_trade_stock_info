FROM python:3.11-slim

ARG CLAUDE_INSTALL_URL

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        nodejs \
        npm \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex

RUN test -n "${CLAUDE_INSTALL_URL}" \
    && curl -fsSL "${CLAUDE_INSTALL_URL}" | bash

COPY scheduler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY scheduler /app/scheduler

RUN mkdir -p /app/logs /app/outputs /app/strategy /app/.claude

CMD ["python", "-u", "scheduler/main.py"]
