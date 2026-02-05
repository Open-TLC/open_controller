#nats-server &

python services/simengine/src/simengine.py --nats-server nats --conf models/testmodel/simsource.json --sumo-conf=models/testmodel/JS270_med_traffic.sumocfg
