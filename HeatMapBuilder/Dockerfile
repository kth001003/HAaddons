ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-debian:bookworm

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install tzdata and git for timezone support and source control
RUN apt-get update && apt-get install -y tzdata git && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

WORKDIR /
# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
    rm -rf /tmp/repo
    
# 필요한 시스템 라이브러리 설치 (Debian 패키지명으로 수정)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-pip \
    libjpeg-dev \
    zlib1g-dev \
    liblapack-dev \
    gfortran \
    linux-headers-generic \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    tcl-dev \
    libtiff-dev \
    tk-dev

# pip 업그레이드
RUN python3 -m pip install --upgrade pip

# Python 패키지 설치
RUN pip3 install --no-cache-dir \
    flask==2.0.1 \
    numpy==1.21.0 \
    pillow==8.3.1 \
    requests==2.26.0 \
    websockets==10.0 \
    scipy==1.7.1 

# 실행 권한 설정
RUN chmod a+x /apps/run.sh

CMD [ "/apps/run.sh" ] 