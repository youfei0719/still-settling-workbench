FROM python:3.14

ENV PYTHONUNBUFFERED=1

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

WORKDIR /app/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy manifests first so dependency installation remains cacheable on source edits.
# This avoids BuildKit-only mount syntax and works with Docker Desktop's legacy builder.
COPY pyproject.toml uv.lock /app/
COPY ./backend/pyproject.toml /app/backend/pyproject.toml
RUN uv sync --frozen --no-install-workspace --package app

COPY ./backend/scripts /app/backend/scripts
COPY ./backend/alembic.ini /app/backend/alembic.ini

COPY ./backend/app /app/backend/app

# Sync the project
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN uv sync --frozen --package app

WORKDIR /app/backend/

# Video upload and extraction state is process-local while the workbench runs.
# Keep one worker until these tasks are moved to a shared queue/store.
CMD ["fastapi", "run", "--workers", "1"]
