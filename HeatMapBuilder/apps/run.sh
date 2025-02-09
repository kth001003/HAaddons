#!/usr/bin/with-contenv bashio

# 웹 애플리케이션 실행 (개발 모드)
FLASK_ENV=development 
FLASK_DEBUG=1 

TZ=$(bashio::supervisor.timezone)
if [ -n "$TZ" ]; then
    echo Timezone: $TZ
    cp /usr/share/zoneinfo/$TZ /etc/localtime
    echo $TZ > /etc/timezone
fi

exec python app.py