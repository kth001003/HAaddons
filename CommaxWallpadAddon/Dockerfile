FROM python:3.10-slim-buster

# S6 오버레이 설치
ARG S6_OVERLAY_VERSION=3.1.5.0
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz

# bashio 설치
RUN apt-get update && apt-get install -y jq curl && \
curl -J -L -o /tmp/bashio.tar.gz \
    "https://github.com/hassio-addons/bashio/archive/v0.14.3.tar.gz" && \
mkdir /tmp/bashio && \
tar zxvf /tmp/bashio.tar.gz --strip 1 -C /tmp/bashio && \
mv /tmp/bashio/lib /usr/lib/bashio && \
ln -s /usr/lib/bashio/bashio /usr/bin/bashio

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install requirements for add-on
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    paho-mqtt==1.6.1 \
    PyYAML==6.0.1 \
    flask==2.3.3
#RUN pip install --no-cache-dir telnetlib

WORKDIR /share
# Copy data for add-on
COPY apps /apps
RUN chmod +x /apps/bashio_wrapper.sh

CMD ["python3", "/apps/main.py"]
