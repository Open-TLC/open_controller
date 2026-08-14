# The WebSUMO viewer image. Self-contained: the build clones the public
# websumo repository at the pinned commit and builds its frontend, so
# plain "docker compose up" needs nothing outside this repository.
#
# Bump WEBSUMO_REF deliberately to take a newer viewer, then rebuild:
#   docker compose build --no-cache websumo

FROM node:20-slim AS frontend
ARG WEBSUMO_REF=11c3b62fbb687e992b52729ac56ced6de3c6244d
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git init -q /src \
    && git -C /src fetch --depth 1 https://github.com/Open-TLC/websumo.git $WEBSUMO_REF \
    && git -C /src checkout -q FETCH_HEAD
WORKDIR /src/frontend
RUN npm ci && npm run build

FROM python:3.11-slim
WORKDIR /app
COPY --from=frontend /src/backend backend
COPY --from=frontend /src/frontend/dist frontend/dist
RUN pip install --no-cache-dir -r backend/requirements.txt sumolib pyproj
RUN mkdir -p /app/scenarios-empty
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8775"]
