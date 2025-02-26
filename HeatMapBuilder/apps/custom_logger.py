import logging
from logging.handlers import RotatingFileHandler
import colorlog # type: ignore

class CustomLogger:
    # ANSI 색상 코드
    COLORS = {
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'reset': '\033[0m'
    }

    def __init__(self, log_file='app.log', log_level='DEBUG'):
        self.logger = logging.getLogger('CustomLogger')
        
        # 기존 핸들러 제거
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 로그 레벨 설정
        self.logger.setLevel(log_level)
        
        # 컬러 포맷터 설정 - reset 코드를 추가하여 색상이 다음 줄에 영향을 주지 않도록 함
        color_formatter = colorlog.ColoredFormatter(
            '%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s %(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            },
            reset=True
        )

        # 파일 핸들러 추가 (파일에는 일반 포맷터 사용)
        try:
            file_handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5, encoding='utf-8')
            file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            
            # 콘솔 핸들러 추가 (컬러 포맷터 사용)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(color_formatter)
            self.logger.addHandler(console_handler)
            
        except Exception as e:
            print(f'로거 초기화 중 오류 발생: {str(e)}')
            raise

    def _colorize(self, text: str, color: str) -> str:
        """텍스트에 색상을 적용하는 헬퍼 메서드"""
        color_code = self.COLORS.get(color.lower(), '')
        if color_code:
            return f"{color_code}{text}{self.COLORS['reset']}"
        return text

    def info(self, message, *args, **kwargs):
        """
        사용 예:
        logger.info("테스트 메시지 with %s", logger._colorize("colored text", "red"))
        """
        self.logger.info(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)