# One image for the API and the worker (different commands). Build context: repository root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv

FROM base AS deps
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY sandbox/pyproject.toml sandbox/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package operator-backend

FROM deps AS runtime
COPY backend backend
COPY company_context company_context
RUN uv sync --frozen --no-dev --package operator-backend \
    && uv run --no-sync playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 operator \
    && mkdir -p var && chown -R operator var
USER operator
ENV PATH="/srv/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
