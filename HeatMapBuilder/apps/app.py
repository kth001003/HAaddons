import threading
import json
import time
import os

from map_generator import MapGenerator
from config_manager import ConfigManager
from sensor_manager import SensorManager
from custom_logger import CustomLogger
from webserver import WebServer

class BackgroundTaskManager:
    def __init__(self, logger, config_manager, sensor_manager, map_generator):
        self.config_manager = config_manager
        self.sensor_manager = sensor_manager
        self.map_generator = map_generator
        self.logger = logger
        self.thread = None
        self.running = False
        self.map_lock = threading.Lock()  # 락 메커니즘 추가
        self.map_timers = {}  # 각 맵별 마지막 생성 시간을 저장

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
                # 모든 맵 정보를 가져옴
                maps = self.config_manager.db.load()
                current_time = time.time()

                for map_id, map_data in maps.items():
                    try:
                        # 맵의 생성 설정 가져오기
                        gen_config = map_data.get('gen_config', {})
                        gen_interval = gen_config.get('gen_interval', 5) * 60  # 기본값 5분

                        # 마지막 생성 시간 확인
                        last_gen_time = self.map_timers.get(map_id, 0)
                        
                        # 생성 간격이 지났는지 확인
                        if current_time - last_gen_time >= gen_interval:
                            self.logger.debug(f"맵 {map_id} 열지도 생성 시작")
                            
                            # 현재 맵으로 설정
                            self.config_manager.current_map_id = map_id
                            self.map_generator.load_map_config(map_id)
                            
                            # 열지도 생성
                            if self.generate_map(map_id):
                                self.logger.info(f"맵 {map_id} 열지도 생성 완료 (소요시간: {self.map_generator.generation_duration})")
                                # 생성 시간 업데이트
                                self.map_timers[map_id] = current_time
                            else:
                                self.logger.error(f"맵 {map_id} 열지도 생성 실패")
                    except Exception as e:
                        self.logger.error(f"맵 {map_id} 열지도 생성 중 오류 발생: {str(e)}")

                # 최소 1분 대기
                time.sleep(60)
            except Exception as e:
                self.logger.error(f"백그라운드 작업 중 오류 발생: {str(e)}")
                time.sleep(60)

    def generate_map(self, map_id):
        """열지도 생성 로직"""
        if self.map_lock.acquire(blocking=False):  # 락 획득 시도
            try:
                _output_path = self.config_manager.get_output_path(map_id)
                return self.map_generator.generate(_output_path)
            except Exception as e:
                self.logger.error(f"열지도 생성 실패: {str(e)}")
                raise e
            finally:
                self.map_lock.release()  # 락 해제
        else:
            self.logger.info("다른 프로세스가 열지도를 생성 중입니다. 이번 생성은 건너뜁니다.")
            return False

if __name__ == '__main__':
    is_local = False
    try:
        with open('/data/options.json') as file:
            CONFIG = json.load(file)
    except:
        is_local = True
        CONFIG = {"img_generation_interval_in_minutes": 5}
    config_manager = ConfigManager(is_local, CONFIG)
    log_level = str(CONFIG.get('log_level', 'info')).upper()
    # 로그 디렉토리 생성 
    log_dir = os.path.dirname(config_manager.paths['log'])
    os.makedirs(log_dir, exist_ok=True)

    # 로거 초기화 (디버그 모드 활성화)
    logger = CustomLogger(log_file=config_manager.paths['log'], log_level=str(log_level))
    logger.info("애플리케이션 시작")

    supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
    try:
        sensor_manager = SensorManager(is_local, config_manager, logger, supervisor_token)
        map_generator = MapGenerator(config_manager, sensor_manager, logger)
        server = WebServer(config_manager,sensor_manager,map_generator,logger)
        background_task_manager = BackgroundTaskManager(logger,config_manager,sensor_manager,map_generator)

        background_task_manager.start()
        logger.info("백그라운드 작업 시작됨")

        try:
            server.run()
        finally:
            background_task_manager.stop()
            logger.info("백그라운드 작업 중지됨")
    except Exception as e:
        logger.error(f"애플리케이션 실행 중 오류 발생: {str(e)}")
        raise
