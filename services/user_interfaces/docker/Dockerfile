FROM python:3.9-slim

WORKDIR /app

# Installl the python libraries for the UI requirements
COPY services/user_interfaces/docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code and models into the container at /app
COPY . .

CMD ["sh", "services/user_interfaces/docker/run_ui.sh"]