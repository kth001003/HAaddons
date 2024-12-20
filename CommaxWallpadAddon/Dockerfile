FROM python:3.10-slim-buster
  
ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

# Install requirements for add-on
# RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir paho-mqtt==1.6.1
RUN pip install --no-cache-dir PyYAML==6.0.1
#RUN pip install --no-cache-dir telnetlib

WORKDIR /share
# Copy data for add-on
COPY apps /apps
COPY apps/devices_and_packets_structures.yaml /share/commax_devices_and_packets_structures.yaml

CMD ["python3", "/apps/main.py"]
