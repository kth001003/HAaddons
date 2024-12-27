ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21
# # S6 오버레이 설치
# ARG S6_OVERLAY_VERSION=3.1.5.0

# # 아키텍처 매핑
# RUN case "${BUILD_ARCH}" in \
#         amd64)  S6_ARCH='x86_64'  ;; \
#         arm64)  S6_ARCH='aarch64' ;; \
#         arm/v7) S6_ARCH='arm'     ;; \
#         arm/v6) S6_ARCH='armhf'   ;; \
#         *)      S6_ARCH='x86_64'  ;; \
#     esac && \
#     curl -L -s "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" -o /tmp/s6-overlay-noarch.tar.xz && \
#     curl -L -s "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" -o /tmp/s6-overlay-arch.tar.xz && \
#     tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz && \
#     tar -C / -Jxpf /tmp/s6-overlay-arch.tar.xz

# # bashio 설치
# RUN apt-get update && apt-get install -y jq curl && \
#     curl -J -L -o /tmp/bashio.tar.gz \
#         "https://github.com/hassio-addons/bashio/archive/v0.14.3.tar.gz" && \
#     mkdir /tmp/bashio && \
#     tar zxvf /tmp/bashio.tar.gz --strip 1 -C /tmp/bashio && \
#     mv /tmp/bashio/lib /usr/lib/bashio && \
#     ln -s /usr/lib/bashio/bashio /usr/bin/bashio

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
