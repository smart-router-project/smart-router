FROM python:3.13-slim AS builder

RUN pip install uv

WORKDIR /app

# Copy dependency metadata first to keep this layer cacheable.
COPY pyproject.toml uv.lock ./

# Install locked dependencies into the project's default virtualenv.
RUN uv sync --frozen --no-install-project
RUN uv add uvloop

FROM python:3.13-slim

WORKDIR /smart-router

# Copy the populated virtualenv into a stable runtime path.
COPY --from=builder /app/.venv /opt/venv
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"

COPY smart_router /smart_router

CMD ["python", "-m", "smart_router.entrypoints.serve.api_server"]
