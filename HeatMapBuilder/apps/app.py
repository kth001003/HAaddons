import threading
import json
import time


from map_generator import MapGenerator
from config_manager import ConfigManager
from sensor_manager import SensorManager
from custom_logger import CustomLogger
from webserver import WebServer


class BackgroundTaskManager:
    def __init__(self, app, logger, config_manager, sensor_manager):
        self.app = app
        self.config_manager = config_manager
        self.sensor_manager = sensor_manager
        self.logger = logger
        self.thread = None
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()

    def run(self):
        while self.running:
            try:
                with self.app.app_context():
                    self.logger.info("백그라운드 열지도 생성 시작")
                    result = self.generate_map()
                    self.logger.info(f"백그라운드 열지도 생성 완료: {result}")
            except Exception as e:
                self.logger.error(f"백그라운드 열지도 생성 실패: {str(e)}")
            
            time.sleep(self.config_manager.gen_config.get("gen_interval",5) * 60)

    def generate_map(self):
        """열지도 생성 로직"""
        try:
            with self.app.app_context():
                result = self.app.view_functions['generate_map']()
                if isinstance(result, tuple):
                    return result[0]  # 에러 응답의 경우
                return result
        except Exception as e:
            self.logger.error(f"백그라운드 열지도 생성 실패: {str(e)}")
            raise e

if __name__ == '__main__':
    is_local = False
    try:
        with open('/data/options.json') as file:
            CONFIG = json.load(file)
    except:
        is_local = True
        CONFIG = {"img_generation_interval_in_minutes": 5}

    config_manager = ConfigManager(is_local, CONFIG)
    logger = CustomLogger(log_file=config_manager.paths['log'])
    sensor_manager = SensorManager(is_local, config_manager, logger)
    map_generator = MapGenerator(config_manager,sensor_manager, logger)
    server = WebServer(is_local,
                       config_manager,
                       sensor_manager,
                       map_generator,
                       logger)
    background_task_manager = BackgroundTaskManager(
        server.app,
        logger,
        config_manager,sensor_manager
    )

    background_task_manager.start()

    try:
        server.run()
    finally:
        background_task_manager.stop()
