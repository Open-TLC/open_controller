FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install sumo sumo-tools sumo-doc -y

# Copy the current directory contents into the container at /app
COPY . .


# Install the python libraries for the sim_engine requirements
RUN pip install --no-cache-dir -r services/simengine/docker/requirements.txt


# setup the SUMO_HOME environment variable
ENV SUMO_HOME=/usr/share/sumo

# Send python output directly to stdout or stderr
# instead of writing to an intermediate buffer.
# This can prevent "ghost" logs not showing up
# when running int Docker
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["sh", "services/simengine/docker/run_simengine.sh"]
