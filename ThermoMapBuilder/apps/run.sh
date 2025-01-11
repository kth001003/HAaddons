#!/usr/bin/with-contenv bashio

# 필요한 디렉토리 생성
mkdir -p /data
mkdir -p /media

# 웹 애플리케이션 실행
cd /usr/share/webapps
python3 app.py 