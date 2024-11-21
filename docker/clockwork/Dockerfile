FROM python:3.9-slim

WORKDIR /app


COPY docker/clockwork/requirements.txt .

# Install python libraries for the clockwork requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code and models into the container at /app
COPY . .


ENTRYPOINT ["sh", "docker/clockwork/run_clockwork.sh"]