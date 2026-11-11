FROM python:3.15-slim

# Copy the uv binary from its official image instead of installing it with pip.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv

# The virtualenv lives outside /app on purpose: in dev we bind-mount ./backend over /app,
# and a venv inside /app would be hidden by that mount.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, source later: this layer is rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . .

# Do not run the server as root inside the container.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
