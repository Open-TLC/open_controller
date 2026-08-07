FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive

# Install necessary system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates \
	software-properties-common \
	libx11-6 \
	libxext6 \
	libxrender1 \
	libxtst6 \
	libgl1 \
	libatomic1\
	&& rm -rf /var/lib/apt/lists/*

# Install uv using the installation script
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install project dependencies
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev --no-install-project

# Copy rest of the project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

# Send python output directly to stdout or stderr
# instead of writing to an intermediate buffer.
# This can prevent "ghost" logs not showing up
# when running int Docker
ENV PYTHONUNBUFFERED=1

CMD [ "uv", "run", "-m", "services.control_engine.src.clockwork", "--conf-file", "./configuration/clockwork.yaml" ]

