ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install tzdata and git for timezone support and source control
RUN apk add --no-cache tzdata git && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

# Install requirements for add-on
RUN pip3 install \
    paho-mqtt==1.6.1 \
    PyYAML==6.0.1 \
    flask==2.3.3 \
    telnetlib3 \
    requests==2.31.0 \
    gevent

WORKDIR /share

# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/CommaxWallpadAddon/apps /apps && \
    rm -rf /tmp/repo

ENV PYTHONPATH=/
RUN chmod a+x /apps/run.sh
CMD ["/apps/run.sh"]
