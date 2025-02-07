import logging
from logging.handlers import RotatingFileHandler

class CustomLogger:
    def __init__(self, log_file='app.log', debug=False):
        self.logger = logging.getLogger('CustomLogger')
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)

        handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def info(self, message):
        self.logger.info(message)

    def debug(self, message):
        self.logger.debug(message)

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)