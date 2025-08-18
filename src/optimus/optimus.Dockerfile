FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (Python, curl, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
	python3 python3-pip python3-venv \
	curl ca-certificates software-properties-common \
	&& rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -fsSL https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin/:$PATH"

# Add SUMO PPA and install
RUN add-apt-repository ppa:sumo/stable && \
	apt-get update && apt-get install -y --no-install-recommends \
	sumo sumo-tools sumo-doc \
	&& rm -rf /var/lib/apt/lists/*

ENV SUMO_HOME="/usr/share/sumo"

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies (use BuildKit!)
RUN --mount=type=cache,target=/root/.cache/uv \
	--mount=type=bind,source=uv.lock,target=uv.lock \
	--mount=type=bind,source=pyproject.toml,target=pyproject.toml \
	uv sync --locked --no-install-project --no-dev

# Copy rest of the project and install
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --locked --no-dev

# Use project venv path
ENV PATH="/app/.venv/bin:$PATH"

# Ensures better logging while training model
ENV PYTHONUNBUFFERED=1

# Run the app
CMD ["uv", "run", "-m", "optimus.optimus"]

