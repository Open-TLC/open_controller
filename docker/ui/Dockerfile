# Only if we want to run the NATS-server in the same container (i.e. not using docker-compose)
#FROM nats:latest as nats

FROM python:3.9-slim

WORKDIR /app


COPY docker/ui/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#yay nats-server

COPY . .

# We test the private repo
# Install the ssh and git
#RUN apt-get update && \
#    apt-get install \
#
#        openssh-client \
#        git \
#    --yes --no-install-recommends &&\ 
#    apt-get clean

# Uncomment this for setting up the known hosts (when running the docker create by hand)
#RUN mkdir -p -m 0600 ~/.ssh && \
#    ssh-keyscan -H github.com bitbucket.org >> ~/.ssh/known_hosts



# Docker build with ssh key, some examples:
#RUN --mount=type=ssh git clone git@bitbucket.org:conveqs/clockwork_tc.git
# RUN --mount=type=ssh git clone git@github.com:Open-TLC/sim_engine.git
# Note: in order for this to work, one has to run the bild with:
# docker build --ssh default=$HOME/.ssh/id_rsa -t simtest .
# docker build --ssh default=$HOME/.ssh/id_rsa -t simtest -f docker/simengine/Dockerfile .

# Copy NATS server binary from the first stage
# Only if we want to run the NATS-server in the same container (i.e. not using docker-compose)
#COPY --from=nats /nats-server /usr/local/bin

# We expose the nats port
#EXPOSE 4222

# setup the SUMO_HOME environment variable
#ENV SUMO_HOME /usr/share/sumo

CMD ["sh", "docker/ui/run_ui.sh"]