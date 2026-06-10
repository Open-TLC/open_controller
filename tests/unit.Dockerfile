FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive

# Install necessary system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates software-properties-common \
	&& rm -rf /var/lib/apt/lists/*

# Install uv using the installation script
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Add SUMO PPA and install
RUN add-apt-repository ppa:sumo/stable && \
	apt-get update && apt-get install -y --no-install-recommends \
	sumo sumo-tools sumo-doc \
	&& rm -rf /var/lib/apt/lists/*

# Export SUMO_HOME so traci and libsumo can be found in python
ENV SUMO_HOME="/usr/share/sumo"

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install project dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
	--mount=type=bind,source=uv.lock,target=uv.lock \
	--mount=type=bind,source=pyproject.toml,target=pyproject.toml \
	uv sync --frozen --no-install-project --no-dev

# Copy rest of the project and install rest of the dependencies
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

# Send python output directly to stdout or stderr
# instead of writing to an intermediate buffer.
# This can prevent "ghost" logs not showing up
# when running int Docker
ENV PYTHONUNBUFFERED=1

# Run all unit tests inside "open_controller/tests"
CMD ["uv", "run", "-m", "unittest", "discover", "-s", "tests"]
