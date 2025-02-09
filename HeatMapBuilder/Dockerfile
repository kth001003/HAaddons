# ARG BUILD_ARCH
ARG BUILD_ARCH=amd64

FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG=C.UTF-8
ENV TZ=Asia/Seoul
# s6-rc 로그 비활성화
ENV S6_LOGGING=0
ENV S6_VERBOSITY=0

RUN apk add --no-cache tzdata git musl-locales gcc musl-dev fontconfig

# 나눔고딕 폰트 설치
COPY fonts/NanumGothic.ttf /tmp/NanumGothic.ttf
RUN mkdir -p /usr/share/fonts/truetype/nanum && \
    cp /tmp/NanumGothic.ttf /usr/share/fonts/truetype/nanum/ && \
    fc-cache -f -v

# 타임존 설정
RUN cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

#Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
    rm -rf /tmp/repo
# COPY apps /apps

# # pip 업그레이드 및 Python 패키지 설치
# RUN python -m pip install --no-cache-dir --upgrade pip && \
#     python -m pip install --no-cache-dir \
RUN python -m pip install \
        "flask==3.1.0" \
        "numpy==2.2.1" \
        # "pillow==11.1.0" \
        "requests==2.32.3" \
        # "websockets==14.1" \
        "scipy==1.15.1" \
        "matplotlib==3.10.0" \
        "shapely==2.0.6" \
        # "svgpath2mpl==1.0.0" \
        "pykrige==1.7.2" \
        "filelock==3.17.0"

# 실행 권한 설정
RUN chmod a+x /apps/run.sh

# 개발 환경 관련 패키지 설치
RUN pip install watchdog

WORKDIR /apps
ENV PYTHONPATH=/apps

#기본 db 복사
COPY default_maps.json /data/maps.json

CMD ["sh", "run.sh"]