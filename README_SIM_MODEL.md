Simulation engine
=================

# About
The simulation engine is a relatively simple tool providing a testing environment for Open Controller. In essence this tool runs SUMO simulation model and updates it in real time while reading and writing input/output data into the model. 

# Using the engine

## Running the testmodel with docker-compose
The easiest way to use the model is to launch it by using docker-compose

    docker-compose up

After this one should be able to access the NATS messsages sent by the SUMO by lostening the NATS channels in the localhost (mapped from the NATS-container)m by commanding:

    nats sub ">"

## Running the model with a single container
NOTE: DOES NOT WORK ANYMORE, DOCKERFILE IS IN THE WRONG PLACE
Create the image:

    docker build -t sumotest .

Or if running with some private repos:

    docker build --ssh default=$HOME/.ssh/id_rsa -t sumotest .

Run it:

    docker run -p 4222:4222 sumotest

After this the messages can be insptected with NATS by issuing:

    nats sub ">"



## Setting up and running the model without docker
### Prequisities
Before one can run this model without container you need:
- Operational sumo installation and
- Python and some libraries
- NATS

### Running the model
One can run the model by simply issuing a command:
    
    python src/simengine.py --nats-server localhost --sumo-conf=models/testmodel/JS270_med_traffic.sumocfg
    


## Command line parameters
This should work with the nats for only starting once: 

    docker-compose up  --no-recreate.

## The configuration file

### Outputs
#### det_outputs
"topic_prefix" the topic for nats channel, default: "detector.status" 



#### Triggers

##### General
Modes for triggering are "update", "change" and "never" 
###### Update 
Sends the output every time the model is updated, i.e. ten timed per second in normal opreation

###### Change
Sends the output every there is a chenge of it status (e.g. the controller 

###### Never
A placeholder mode, that is these outputs are not sent.

# Known issues

# Lisence

# Background material

How to set up the ssh keys for pivate repos:
https://medium.com/datamindedbe/how-to-access-private-data-and-git-repositories-with-ssh-while-building-a-docker-image-a-ea283c0b4272

