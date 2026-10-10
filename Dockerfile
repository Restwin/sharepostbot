FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml README.md ./
COPY bot ./bot
RUN pip install --upgrade pip && pip install .

FROM python:3.12-slim AS final
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY bot ./bot
RUN mkdir -p /app/data /app/logs
EXPOSE 8080 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3).status==200 else 1)"
CMD ["python", "-m", "bot"]
