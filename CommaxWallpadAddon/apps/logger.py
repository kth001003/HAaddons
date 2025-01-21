import logging
import sys
from logging.handlers import RotatingFileHandler
from queue import Queue
from logging.handlers import QueueHandler, QueueListener

class Logger:
    def __init__(self, debug=False, elfin_log=False, mqtt_log=False, log_file='/share/commax_wallpad.log'):
        self.logger = logging.getLogger('ComMaxWallpad')
        level = logging.DEBUG if debug else logging.INFO
        self.logger.setLevel(level)

        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %p %I:%M:%S'
        )

        # 파일 핸들러 설정 (로그 회전 포함)
        file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5)
        file_handler.setFormatter(formatter)

        # 스트림 핸들러 설정
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.DEBUG)

        # 큐 핸들러 설정
        log_queue = Queue(-1)
        queue_handler = QueueHandler(log_queue)
        self.logger.addHandler(queue_handler)

        # 리스너 설정 및 시작
        self.listener = QueueListener(log_queue, file_handler, stream_handler)
        self.listener.start()

        self.enable_elfin_log = elfin_log
        self.enable_mqtt_log = mqtt_log

    def __del__(self):
        self.listener.stop()

    def _log(self, level, message):
        try:
            getattr(self.logger, level)(message)
        except Exception as e:
            print(f"Logging error: {e}")

    def info(self, message):
        self._log('info', message)

    def error(self, message):
        self._log('error', message)

    def warning(self, message):
        self._log('warning', message)

    def debug(self, message):
        self._log('debug', message)

    def signal(self, message):
        if self.enable_elfin_log:
            self._log('debug', f'[RS485] {message}')

    def mqtt(self, message):
        if self.enable_mqtt_log:
            self._log('debug', f'[MQTT] {message}')

    def set_level(self, level):
        self.logger.setLevel(level)
