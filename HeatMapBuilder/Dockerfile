ARG BUILD_ARCH
FROM python:3

ENV LANG C.UTF-8
ENV TZ Asia/Seoul

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
    tk-dev \
    fonts-nanum && \
    rm -rf /var/lib/apt/lists/*

# 타임존 설정
RUN cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

WORKDIR /
# Auto update on rebuild
# RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
#     cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
#     rm -rf /tmp/repo

COPY apps /apps


# pip 업그레이드 및 Python 패키지 설치
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir \
        "flask==3.1.0" \
        "numpy==2.2.1" \
        "pillow==11.1.0" \
        "requests==2.32.3" \
        "websockets==14.1" \
        "scipy==1.15.1" \
        "matplotlib==3.10.0" \
        "shapely==2.0.6" \
        "svgpath2mpl==1.0.0" \
        "pykrige==1.7.2" 

# 실행 권한 설정
RUN chmod a+x /apps/run.sh

# 개발 환경 관련 패키지 설치
RUN pip install watchdog

# 볼륨 마운트 시 파일 변경 감지를 위한 환경변수
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1

# CMD [ "/apps/run.sh" ] 
CMD ["python3","/apps/webapps/app.py"]