FROM python:3.13-slim

WORKDIR /app

COPY . .


# Install the python libraries for the sim_engine requirements
RUN pip install --no-cache-dir -r services/indicators/docker/requirements.txt



ENTRYPOINT ["sh", "services/indicators/docker/run_indicators.sh"]