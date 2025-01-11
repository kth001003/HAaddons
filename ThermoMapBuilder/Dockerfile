ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install tzdata and git for timezone support and source control
RUN apk add --no-cache tzdata git && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone
    
# Python 패키지 설치
COPY requirements.txt /
RUN pip3 install -r requirements.txt

# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/ThermoMapBuilder/apps / && \
    rm -rf /tmp/repo

# 실행 권한 설정
RUN chmod a+x /run.sh

CMD [ "/run.sh" ] 