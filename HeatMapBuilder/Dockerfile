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
    py3-numpy \
    py3-scipy \
    jpeg-dev \
    zlib-dev \
    lapack-dev \
    gfortran \
    musl-dev \
    linux-headers \
    freetype-dev \
    fribidi-dev \
    harfbuzz-dev \
    lcms2-dev \
    openjpeg-dev \
    tcl-dev \
    tiff-dev \
    tk-dev

# pip 업그레이드
RUN python3 -m pip install --upgrade pip

# Python 패키지 설치
RUN pip3 install --no-cache-dir \
    flask==2.0.1 \
    requests==2.26.0 \

# 실행 권한 설정
RUN chmod a+x /run.sh

CMD [ "/run.sh" ] 