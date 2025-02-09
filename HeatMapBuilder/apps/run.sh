#!/usr/bin/with-contenv bashio
# 필요한 디렉토리 생성
mkdir -p /data
mkdir -p /media
# 웹 애플리케이션 실행 (개발 모드)
FLASK_ENV=development 
FLASK_DEBUG=1 

python3 app.py