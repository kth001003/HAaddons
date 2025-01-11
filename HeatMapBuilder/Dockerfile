ARG BUILD_ARCH
FROM python:3

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# 기본 시스템 업데이트 및 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    tzdata \
    libjpeg-dev \
    zlib1g-dev \
    liblapack-dev \
    gfortran \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    tcl-dev \
    libtiff-dev \
    tk-dev && \
    rm -rf /var/lib/apt/lists/*

# 타임존 설정
RUN cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

WORKDIR /
# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
    rm -rf /tmp/repo

# pip 업그레이드 및 Python 패키지 설치
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        flask==2.0.1 \
        numpy==1.21.0 \
        pillow==8.3.1 \
        requests==2.26.0 \
        websockets==10.0 \
        scipy==1.7.1

# 실행 권한 설정
RUN chmod a+x /apps/run.sh

CMD [ "/apps/run.sh" ] 