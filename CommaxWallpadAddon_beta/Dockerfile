ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21
ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install tzdata for timezone support
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone

# Install requirements for add-on
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir \
RUN pip3 install \
    paho-mqtt==1.6.1 \
    PyYAML==6.0.1 \
    flask==2.3.3 \
    telnetlib3 \
    requests==2.31.0 \
    gevent

WORKDIR /share
# Copy data for add-on
COPY apps /apps

ENV PYTHONPATH=/
CMD ["/run.sh"]
CMD ["/run.sh"]
