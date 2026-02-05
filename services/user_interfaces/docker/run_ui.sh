#!/bin/sh
# This is used if we need local nats (for testing)
# Running the clockwork. Note: server must be mapped by docker
python services/user_interfaces/src/clockwork_ui.py --nats-server nats