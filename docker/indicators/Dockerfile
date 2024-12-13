FROM python:3.9-slim

WORKDIR /app

COPY . .


# Install the python libraries for the sim_engine requirements
RUN pip install --no-cache-dir -r docker/indicators/requirements.txt



ENTRYPOINT ["sh", "docker/indicators/start.sh"]
