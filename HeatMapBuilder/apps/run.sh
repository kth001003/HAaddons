#!/usr/bin/with-contenv bashio
set -e

# 웹 애플리케이션 실행 (개발 모드)
FLASK_ENV=development 
FLASK_DEBUG=1 

export SUPERVISOR_TOKEN=$(bashio::supervisor.token)

exec python app.py