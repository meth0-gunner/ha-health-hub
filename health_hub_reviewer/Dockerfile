ARG BUILD_FROM
FROM ${BUILD_FROM}

# Pinned to the release verified on Nick's HA Green (via the Claude Code add-on).
ARG CLAUDE_CODE_VERSION=2.1.311

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 USE_BUILTIN_RIPGREP=0

RUN apk add --no-cache nodejs npm libstdc++ ca-certificates ripgrep \
    && npm install -g --no-fund --no-audit "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && timeout 60 claude --version < /dev/null \
    && echo "${CLAUDE_CODE_VERSION}" > /etc/claude-code-version

COPY reviewer.py /usr/local/bin/reviewer.py

ENTRYPOINT []
CMD ["python3", "-u", "/usr/local/bin/reviewer.py"]
