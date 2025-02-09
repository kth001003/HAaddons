#!/usr/bin/with-contenv bashio

# 웹 애플리케이션 실행 (개발 모드)
FLASK_ENV=development 
FLASK_DEBUG=1 
export SUPERVISOR_TOKEN=$SUPERVISOR_TOKEN

exec python3 app.py