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
  vim \
  fish \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex

RUN if [ -n "${CLAUDE_INSTALL_URL}" ]; then \
  curl -fsSL "${CLAUDE_INSTALL_URL}" | bash; \
  fi

COPY scheduler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY scheduler /app/scheduler
COPY .claude /root/.claude
COPY .codex /root/.codex

CMD ["/bin/fish"]
