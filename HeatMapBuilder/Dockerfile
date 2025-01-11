ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install tzdata and git for timezone support and source control
RUN apk add --no-cache tzdata git && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

WORKDIR /
# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/HeatMapBuilder/apps / && \
    rm -rf /tmp/repo
    
# 필요한 시스템 라이브러리 설치
RUN apk add --no-cache \
    build-base \
    python3-dev \
    py3-pip \
    jpeg-dev \
    zlib-dev \
    lapack-dev \
    gfortran \
    musl-dev \
    linux-headers

# Python 패키지 설치
RUN pip3 install --no-cache-dir \
    flask==2.0.1 \
    numpy==1.21.0 \
    pillow==8.3.1 \
    requests==2.26.0 \
    websockets==10.0 \
    scipy==1.7.1 

# 실행 권한 설정
RUN chmod a+x /run.sh

CMD [ "/run.sh" ] 