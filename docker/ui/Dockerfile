FROM python:3.9-slim

WORKDIR /app

# Installl the python libraries for the UI requirements
COPY docker/ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code and models into the container at /app
COPY . .

CMD ["sh", "docker/ui/run_ui.sh"]