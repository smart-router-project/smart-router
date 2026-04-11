FROM python:3.13-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency metadata first to keep this layer cacheable.
COPY pyproject.toml uv.lock ./

# Install locked dependencies into the project's default virtualenv.
# Set INSTALL_BENCHMARK=true at build time to include benchmark extras.
ARG INSTALL_BENCHMARK=false
RUN if [ "$INSTALL_BENCHMARK" = "true" ]; then \
        uv sync --frozen --no-install-project --extra benchmark; \
    else \
        uv sync --frozen --no-install-project; \
    fi
RUN uv pip install --python /app/.venv/bin/python uvloop

FROM python:3.13-slim

WORKDIR /app


# Copy the populated virtualenv into a stable runtime path.
COPY --from=builder /app/.venv /opt/venv
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"

COPY smart_router ./smart_router

CMD ["python", "-m", "smart_router", "serve"]
