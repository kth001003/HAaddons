import logging
from logging.handlers import RotatingFileHandler

class CustomLogger:
    def __init__(self, log_file='app.log', debug=False):
        self.logger = logging.getLogger('CustomLogger')
        
        # 기존 핸들러 제거
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 로그 레벨 설정
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        
        # 파일 핸들러 추가
        try:
            handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5, encoding='utf-8')
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
            # 콘솔 핸들러 추가
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            self.logger.info('로거가 성공적으로 초기화되었습니다.')
        except Exception as e:
            print(f'로거 초기화 중 오류 발생: {str(e)}')
            raise

    def info(self, message):
        self.logger.info(message)

    def debug(self, message):
        self.logger.debug(message)

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)