# Anonrep services

This directory contain services and components needed for anonoymous reputation implementation

# Components


## The simulation engine
### About

### Running the docker


### Running the command line
For test purposes we can run:

    python simengine.py --nats-server localhost --conf ../../models/testmodel/simsource.json --sumo-conf ../../models/testmodel/JS270_med_traffic.sumocfg




## The Registration Authority
### About
This rervice will sing (blindly) the messages it reveives from the vehicle(s)

### Running the docker
We bould the image (as ra-container)

    docker build -t ra-container -f docker/ra/Dockerfile .

Run it connecting to the local nats:

    docker run --rm --name ra-container --network host ra-container

## The Reputation server
### About
This service determines the reputation level for the a sender based on accuracy of the measurement proviced.


### Running the docker

We bould the image (as rs-container)

    docker build -t rs-container -f docker/rs/Dockerfile .

Run it connecting to the local nats:

    docker run --rm --name rs-container --network host rs-container