FROM ghcr.io/eclipse-sumo/sumo:main

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

# Try to run a simulation with Open Controller. Test fails if program crashes.
CMD ["uv", "run", "-m", "services.simengine.src.simengine_integrated", "--conf-file", "/app/models/test/simple/contr.json"]
