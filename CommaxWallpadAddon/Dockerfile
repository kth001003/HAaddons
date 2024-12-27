ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.21

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install requirements for add-on
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    paho-mqtt==1.6.1 \
    PyYAML==6.0.1 \
    flask==2.3.3

WORKDIR /share
# Copy data for add-on
COPY apps /apps
RUN chmod +x /apps/bashio_wrapper.sh

CMD ["python3", "/apps/main.py"]
