# The WebSUMO viewer image. Self-contained: the build clones the public
# websumo repository at the pinned commit and builds its frontend, so
# plain "docker compose up" needs nothing outside this repository.
#
# Bump WEBSUMO_REF deliberately to take a newer viewer, then rebuild:
#   docker compose build --no-cache websumo

FROM node:26-slim AS frontend
ARG WEBSUMO_REF=11c3b62fbb687e992b52729ac56ced6de3c6244d
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git init -q /src \
    && git -C /src fetch --depth 1 https://github.com/Open-TLC/websumo.git $WEBSUMO_REF \
    && git -C /src checkout -q FETCH_HEAD
WORKDIR /src/frontend
RUN npm ci && npm run build

FROM python:3.13-slim
WORKDIR /app
COPY --from=frontend /src/backend backend
COPY --from=frontend /src/frontend/dist frontend/dist
# requirements.txt comes from the websumo repository; requirements-oc.txt
# holds the extra packages the OC deployment needs on top of it
COPY services/websumo/docker/requirements-oc.txt requirements-oc.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r requirements-oc.txt
# Deliberately empty and non-persistent: the viewer is file-free and
# fetches scenario files live over NATS request-reply (see
# services/simengine/doc/websumo.md); no volume is needed here
RUN mkdir -p /app/scenarios-empty
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8775"]
