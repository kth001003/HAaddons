# Dockerfile 수정 내용
# ... (기존 내용)

RUN apk add --no-cache \
    tzdata \
    git \
    **python3-dev** \
    **g++** \
    **linux-headers** \
    && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

# ... (기존 내용)
# Dockerfile 수정 내용
ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul
# s6-rc 로그 비활성화
ENV S6_LOGGING=0
ENV S6_VERBOSITY=0

# Dockerfile 수정 내용
# ... (생략)
# Install build tools, tzdata and git for timezone support and source control
RUN apk add --no-cache \
    tzdata \
    git \
    **g++** \
    **python3-dev** \
    **linux-headers** \
    && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

# ... (생략)

# Install requirements for add-on
RUN pip3 install \
    paho-mqtt==1.6.1 \
    PyYAML==6.0.1 \
    flask[async]==2.3.3 \
    telnetlib3 \
    requests==2.31.0 \
    gevent

WORKDIR /share
# Copy data for add-on
COPY apps /apps

ENV PYTHONPATH=/
RUN chmod a+x /apps/run.sh
CMD ["/apps/run.sh"]
