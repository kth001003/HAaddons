ARG BUILD_ARCH
FROM python:3

ENV LANG C.UTF-8
ENV TZ=Asia/Seoul

WORKDIR /
# Auto update on rebuild
RUN git clone -b beta https://github.com/wooooooooooook/HAaddons.git /tmp/repo && \
    cp -r /tmp/repo/HeatMapBuilder/apps /apps && \
    rm -rf /tmp/repo
    
# Python 패키지 설치
RUN pip3 install --no-cache-dir \
    flask==2.0.1 \
    numpy==1.21.0 \
    pillow==8.3.1 \
    requests==2.26.0 \
    websockets==10.0 \
    scipy==1.7.1 

# 실행 권한 설정
RUN chmod a+x /apps/run.sh

CMD [ "/apps/run.sh" ] 