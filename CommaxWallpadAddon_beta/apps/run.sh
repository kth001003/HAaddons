#!/usr/bin/with-contenv bashio
MQTT_HOST=$(bashio::services mqtt "host")
MQTT_USER=$(bashio::services mqtt "username")
MQTT_PASSWORD=$(bashio::services mqtt "password")

echo "MQTT_HOST: $MQTT_HOST"
echo "MQTT_USER: $MQTT_USER"
echo "MQTT_PASSWORD: $MQTT_PASSWORD"

python3 -m apps.main
