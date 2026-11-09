# The backend: the API under uvicorn on port 8000. The same image applies the migrations
# with `alembic upgrade head`, which is how compose.yaml uses it.
# Base images are pinned by digest, so a build gets exactly the image that was checked.

# The uv that CI uses. It only builds the virtualenv: the image that runs has no uv.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# The same Python as the image that runs, because the virtualenv links to its interpreter.
FROM python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS build
COPY --from=uv /uv /usr/local/bin/uv
# Compiled here, because the app can't write to its own files when it runs. Copied
# rather than linked from uv's cache, which is a cache mount and not in the image. And
# the image's Python rather than one uv would download.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# The dependencies first, in a layer that is built again only when uv.lock or
# pyproject.toml change, not whenever the code does.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock ./
COPY src ./src
# Installs the app itself, as a link to /app/src, which is why src/ is copied below.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
# A user of its own, so the app doesn't run as root. It owns none of the files, so it
# can't change the code either.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/src ./src
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8000
# With Python, because the slim image has no curl. urlopen raises on anything but a 2xx.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["uvicorn", "context_lens.main:app", "--host", "0.0.0.0", "--port", "8000"]
