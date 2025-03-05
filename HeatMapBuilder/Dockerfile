ARG BUILD_ARCH=amd64
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG=C.UTF-8
ENV TZ=Asia/Seoul
# s6-rc 로그 비활성화
ENV S6_LOGGING=0
ENV S6_VERBOSITY=0

RUN apk add --no-cache tzdata git musl-locales gcc musl-dev fontconfig ninja gcc g++ jpeg-dev zlib-dev libjpeg make freetype-dev

# 나눔고딕 폰트 설치
COPY fonts/NanumGothic.ttf /tmp/NanumGothic.ttf
RUN mkdir -p /usr/share/fonts/truetype/nanum && \
    cp /tmp/NanumGothic.ttf /usr/share/fonts/truetype/nanum/ && \
    fc-cache -f -v

# 타임존 설정
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone

# #Auto update on rebuild
# RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
#     cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
#     rm -rf /tmp/repo
COPY apps /apps

COPY requirements.txt /requirements.txt
RUN python -m pip install -r /requirements.txt


# 개발 환경 관련 패키지 설치
RUN pip install watchdog

WORKDIR /apps
ENV PYTHONPATH=/apps

RUN chmod a+x /apps/run.sh
CMD ["/apps/run.sh"]
# CMD ["python3", "app.py"]