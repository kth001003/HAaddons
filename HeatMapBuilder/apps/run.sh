#!/usr/bin/with-contenv bashio
set -e

# 웹 애플리케이션 실행 (개발 모드)
FLASK_ENV=development 
FLASK_DEBUG=1 

# 최대 대기 시간 (초 단위)
TIMEOUT=30

# SUPERVISOR_TOKEN 환경변수가 설정될 때까지 대기
while [ $TIMEOUT -gt 0 ] && [ -z "$SUPERVISOR_TOKEN" ]; do
  echo "Waiting for SUPERVISOR_TOKEN environment variable to be set..."
  sleep 1
  TIMEOUT=$(( TIMEOUT - 1 ))
done

# 환경변수가 없으면 에러 처리
if [ -z "$SUPERVISOR_TOKEN" ]; then
  echo "Error: SUPERVISOR_TOKEN environment variable not set after waiting."
  exit 1
fi

echo "SUPERVISOR_TOKEN is set, starting app..."
exec python app.py