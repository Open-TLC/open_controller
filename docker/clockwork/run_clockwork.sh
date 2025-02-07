#!/bin/sh
# This is used if we need local nats (for testing)
#nats-server &
python src/clockwork/clockwork.py --conf-file=models/testmodel/oc_demo_full_features.json