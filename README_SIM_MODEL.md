Simulation engine
=================

# About
The simulation engine is a relatively simple tool providing a testing environment for Open Controller. In essence this tool runs SUMO simulation model and updates it in real time while reading and writing input/output data into the model. 

# Using the engine

## Running the test model with the container stack
The easiest way to use the model is to launch the full stack:

    make up

After this one should be able to access the NATS messages sent by the SUMO by listening to the NATS channels on the localhost (mapped from the NATS container) by commanding:

    nats sub ">"

## Setting up and running the model without docker
### Prerequisites
Before one can run this model without a container you need:
- Operational SUMO installation
- Python and the project dependencies (`uv sync`)
- A NATS server (e.g. `docker compose up nats`)

### Running the model
One can run the independent engine by issuing a command:
    
    uv run python -m services.simengine.src.simengine --nats-server localhost --conf models/dual/simsource.json --sumo-conf models/dual/dual.sumocfg

The `--conf` file is the engine's JSON configuration (see
[services/simengine/doc/configuration.md](services/simengine/doc/configuration.md));
`--sumo-conf` points at the SUMO scenario to run.

## The configuration file

The independent engine's JSON configuration is described in
[services/simengine/doc/configuration.md](services/simengine/doc/configuration.md).
A summary of the output triggers:

### Outputs
#### det_outputs
"topic_prefix" the topic for nats channel, default: "detector.status" 

#### Triggers

##### General
Modes for triggering are "update", "change" and "never" 
###### Update 
Sends the output every time the model is updated, i.e. ten times per second in normal operation

###### Change
Sends the output every time there is a change of its status

###### Never
A placeholder mode, that is, these outputs are not sent.
