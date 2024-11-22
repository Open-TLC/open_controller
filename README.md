![Open Controller Logo](https://github.com/Open-TLC/open_controller/blob/main/ui/assets/OC_logo_green_horizontal.jpg)

# Open Controller

## About 

This is the main repository of Open Controller, an open source traffic light controller.

## Quickstart

In order to run the basic system you need to have [docker](https://docs.docker.com/get-started/get-docker/) installed into your system. 

After this you can setup the full Open Controller system and run it with a relatively simple test model by issuing command:

    docker-compose up

This script will in essence install four separate docker containers and run them, they are:

- Nats server, a standard [NATS](https://nats.io) message broker
- Clockwork, the open source traffic light controller
- Simengine, a [SUMO](https://eclipse.dev/sumo/) simulation platform with interfaces to access the open controller
- UI, an user interface for the system

After this you should be able to see the user interface via [http://127.0.0.1:8050](http://127.0.0.1:8050)

## Documentation

To be added...

    nats pub "group.control.270_Tyyn_Vali.1" "{ \"id\”: \"group.control.270_Tyyn_Vali.1\”, \"tstamp\”: \"2023-10-30T12:01:09.453+00:00\”, \"substate\”: \"5\”, \"green\”: true }"

    

## License

The sofware is released unde the EUPL-1.2 licence, click [here](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12) for more details.
