#!/usr/bin/with-contenv bashio
source /usr/lib/bashio/bashio.sh

# Supervisor token 환경 변수 설정
export SUPERVISOR_TOKEN=${SUPERVISOR_TOKEN:-$(bashio::supervisor.token)}

function=$1
shift

case $function in
    config)
        bashio::config "$@"
        ;;
    log.info)
        bashio::log.info "$@"
        ;;
    services)
        bashio::services "$@"
        ;;
    addon.option)
        bashio::addon.option "$@"
        ;;
    addon.restart)
        bashio::addon.restart
        ;;
    # 필요한 다른 bashio 함수들을 여기에 추가
    *)
        echo "Unknown function: $function"
        exit 1
        ;;
esac
