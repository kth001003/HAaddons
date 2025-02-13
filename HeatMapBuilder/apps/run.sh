#!/usr/bin/with-contenv bashio
FLASK_ENV=development 
FLASK_DEBUG=1 

# TZ=$(bashio::supervisor.timezone)
if [ -n "$TZ" ]; then
    echo Timezone: $TZ
    cp /usr/share/zoneinfo/$TZ /etc/localtime
    echo $TZ > /etc/timezone
else
    echo "Timezone 정보가 없습니다."
fi

exec python app.py