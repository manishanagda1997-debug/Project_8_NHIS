# Application server image: the Flask app served by Gunicorn (decision D-038).
#
# Docker builds the Linux runtime from the same pinned project environment
# specification (environment.yml) used for local development and CI. The
# image holds code and environment only: data/processed is mounted read-only
# at run time (see docker-compose.yml), so a new data build never needs a new
# image. Build from the project root:  docker compose build
FROM mambaorg/micromamba:1.5.10-bookworm-slim

ENV JOB_MARKET_ROOT=/app \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The project folder and the data mount points belong to the non-root user.
USER root
RUN mkdir -p /app/data/raw /app/data/labels /app/data/interim /app/data/processed /app/reports /app/notebooks \
    && chown -R $MAMBA_USER:$MAMBA_USER /app
USER $MAMBA_USER
WORKDIR /app

# 1. The pinned environment (cached until environment.yml changes).
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /app/environment.yml
# Gunicorn, the production server, is added here, pinned and from the same
# conda-forge channel: it exists for Linux and macOS only, so it cannot be in
# environment.yml, which must also install on Windows (decision D-038).
RUN micromamba install --yes --name base --file /app/environment.yml \
    && micromamba install --yes --name base --channel conda-forge --override-channels gunicorn=23.0.0 \
    && micromamba clean --all --yes

# 2. The project: code, settings and SQL (no data, notebooks or tests; see .dockerignore).
COPY --chown=$MAMBA_USER:$MAMBA_USER config /app/config
COPY --chown=$MAMBA_USER:$MAMBA_USER sql /app/sql
COPY --chown=$MAMBA_USER:$MAMBA_USER src /app/src

# Runs as the image's non-root user (mambauser); nothing at run time needs root.
EXPOSE 8000

# One worker with threads: the recommender's read-only search index is large,
# and each extra worker process would hold its own copy.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", \
     "--timeout", "180", "--access-logfile", "-", "job_market_web.wsgi:app"]
