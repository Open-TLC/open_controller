#nats-server &

python -m services.simengine.src.simengine --nats-server nats --conf models/testmodel/simsource.json --sumo-conf=models/testmodel/JS270_med_traffic.sumocfg
