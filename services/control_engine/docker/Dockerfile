FROM python:3.9-slim

WORKDIR /app


COPY services/control_engine/docker/requirements.txt .

# Install python libraries for the control_engine requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code and models into the container at /app
COPY . .


ENTRYPOINT ["sh", "services/control_engine/docker/run_control_engine.sh"]