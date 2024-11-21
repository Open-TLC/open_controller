FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install sumo sumo-tools sumo-doc -y

# Copy the current directory contents into the container at /app
COPY . .


# Install the python libraries for the sim_engine requirements
RUN pip install --no-cache-dir -r docker/simengine/requirements.txt


# setup the SUMO_HOME environment variable
ENV SUMO_HOME=/usr/share/sumo

ENTRYPOINT ["sh", "docker/simengine/sim_start.sh"]
