FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
ARG ASDOS_INSTALL_MODEL=0
RUN if [ "$ASDOS_INSTALL_MODEL" = "1" ]; then uv sync --frozen --no-dev --extra model; else uv sync --frozen --no-dev; fi
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 asdos && mkdir -p /app/data/private /app/models && chown -R asdos:asdos /app
USER asdos
EXPOSE 8000
CMD ["uvicorn", "apps.api.asdos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
