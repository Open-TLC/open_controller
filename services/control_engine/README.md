# Controller engine

This service manages traffic controller operations.

Configuration documentation can be found in [doc/configuration](./doc/configuration).

## Running Clockwork

To run Clockwork locally, you need to first copy a valid Clockwork configuration to `open_controller/configuration/` and name it `clockwork.yaml`. This is the default file that Clockwork will look for. You should stick to the default name, unless you have a good reason to do otherwise.

Running Clockwork is easy. You need to have `make`, `docker` and `docker-compose` installed. Then you just run `make up` in the project root. This will start all necessary containers for running a local simulation and Open Controller. Clockwork will start with the configuration file specified earlier, and send signal states to the NATS server.
