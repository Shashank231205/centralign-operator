# Mock company apps (vendor portal + ERP). Build context: repository root.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY sandbox sandbox
RUN uv sync --frozen --no-dev --package operator-sandbox \
    && useradd --create-home --uid 10001 sandbox \
    && mkdir -p var && chown -R sandbox var
USER sandbox
ENV PATH="/srv/.venv/bin:$PATH"
CMD ["uvicorn", "sandbox.vendor_portal.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8101"]
