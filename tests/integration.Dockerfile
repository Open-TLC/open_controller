FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive

# Install necessary system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates software-properties-common libatomic1

# Install uv using the installation script
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Add SUMO PPA and install
RUN add-apt-repository ppa:sumo/stable && \
	apt-get update && apt-get install -y --no-install-recommends \
	sumo sumo-tools sumo-doc

# Export SUMO_HOME so traci and libsumo can be found in python
ENV SUMO_HOME="/usr/share/sumo"

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install project dependencies
COPY pyproject.toml /app
RUN	uv sync --no-dev

# Copy rest of the project
COPY . /app
RUN uv sync --no-dev

# Send python output directly to stdout or stderr
# instead of writing to an intermediate buffer.
# This can prevent "ghost" logs not showing up
# when running int Docker
ENV PYTHONUNBUFFERED=1

# Try to run a simulation with Open Controller. Test fails if program crashes.
CMD ["uv", "run", "-m", "services.simengine.src.simengine_integrated", "--conf-file", "/app/models/test/simple/contr.json"]
