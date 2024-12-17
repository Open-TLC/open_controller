# Shell script ffor sending a pulse for a given channel
# Read value from the command line
detector_id=$1

nats pub -s localhost detector.status.$detector_id '{"id":"detector.status.R3PY","tstamp":"2024-12-16T15:33:17.645960773","loop_on":false}'
# wait for a second
#sleep 1
nats pub -s localhost detector.status.$detector_id '{"id":"detector.status.R3PY","tstamp":"2024-12-16T15:33:17.645960773","loop_on":true}'

#wait for a second
#sleep 1
nats pub -s localhost detector.status.$detector_id '{"id":"detector.status.R3PY","tstamp":"2024-12-16T15:33:17.645960773","loop_on":false}'


