import threading
import json
import time
import os
import asyncio
import glob
import shutil

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

    def rotate_images(self, map_id, output_path):
        """이미지 로테이션 처리"""
        try:
            # 맵 설정에서 로테이션 수 가져오기
            map_data = self.config_manager.db.load().get(map_id, {})
            gen_config = map_data.get('gen_config', {})
            rotation_count = gen_config.get('rotation_count', 20)  # 기본값 20

            # 기존 이미지 파일 경로
            base_path = os.path.splitext(output_path)[0]
            ext = os.path.splitext(output_path)[1]
            
            # 가장 오래된 백업 파일 삭제
            old_file = f"{base_path}-{rotation_count-1}{ext}"
            if os.path.exists(old_file):
                os.remove(old_file)

            # 기존 백업 파일들의 번호를 하나씩 증가
            for i in range(rotation_count-2, -1, -1):
                old_name = f"{base_path}-{i}{ext}" if i > 0 else output_path
                new_name = f"{base_path}-{i+1}{ext}"
                if os.path.exists(old_name):
                    shutil.move(old_name, new_name)

        except Exception as e:
            self.logger.error(f"이미지 로테이션 처리 중 오류 발생: {str(e)}")

    async def generate_map(self, map_id):
        """열지도 생성 로직"""
        if self.map_lock.acquire(blocking=False):  # 락 획득 시도
            try:
                self.logger.debug(f"맵 생성 시작: {map_id}")
                
                # 웹소켓 클라이언트 상태 로깅
                websocket_client = self.sensor_manager.websocket_client
                _output_path = self.config_manager.get_output_path(map_id)
                # 기존 이미지가 있다면 로테이션 수행
                if os.path.exists(_output_path):
                    self.rotate_images(map_id, _output_path)
                
                # 맵 생성 시작 시간 기록
                start_time = time.time()
                
                # 맵 생성 실행
                success, error_msg = await self.map_generator.generate(map_id, _output_path)
                
                # 소요 시간 계산
                elapsed_time = time.time() - start_time
                self.logger.info(f"맵 생성 완료: {map_id}, 성공 여부: {success}, 소요시간: {elapsed_time:.3f}초")
                if not success:
                    raise Exception(error_msg)
                return success
            except Exception as e:
                self.logger.error(f"열지도 생성 실패: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                raise e
            finally:
                self.map_lock.release()  # 락 해제
                self.logger.debug(f"맵 생성 락 해제: {map_id}")
        else:
            self.logger.debug("다른 프로세스가 열지도를 생성 중입니다. 이번 생성은 건너뜁니다.")
            return False

    def run(self):
        """백그라운드 작업 실행"""
        self.logger.debug("백그라운드 작업 스레드 시작")
        
        # 이벤트 루프 생성 (스레드당 하나의 이벤트 루프 사용)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 생성된 이벤트 루프의 ID 로깅 (디버깅 목적)
        loop_id = id(loop)
        self.logger.debug(f"백그라운드 작업용 이벤트 루프 생성 (ID: {loop_id})")
        
        try:
            while self.running:
                try:
                    current_time = time.time()
                    
                    # 모든 맵 정보를 가져옴
                    maps = self.config_manager.db.load()
                    for map_id, map_data in maps.items():
                        try:
                            # 맵의 생성 설정 가져오기
                            gen_config = map_data.get('gen_config', {})
                            gen_interval = gen_config.get('gen_interval', 5) * 60  # 기본값 5분
                            map_name = map_data.get('name', '이름 없음')
                                
                            # 자동 맵 생성 설정 확인
                            auto_generation = gen_config.get('auto_generation', False)  # 기본값은 비활성화
                            self.logger.debug("---맵 이름:%s, 맵 ID:%s, 자동생성:%s, 생성주기:%s", 
                                            self.logger._colorize(map_name, "blue"),
                                            map_id,
                                            self.logger._colorize(auto_generation, "green"),
                                            self.logger._colorize(gen_interval, "yellow"))
                            
                            if not auto_generation:
                                continue
                                
                            # 마지막 생성 시간 확인
                            last_gen_time = self.map_timers.get(map_id, 0)
                            
                            # 생성 간격이 지났는지 확인
                            if current_time - last_gen_time >= gen_interval:
                                walls = map_data.get('walls', '')
                                sensors = map_data.get('sensors', [])
                                if not walls or not sensors: # 벽 또는 센서 데이터가 없으면 건너뜀
                                    self.logger.debug(f"맵 {map_name} ({map_id}): 벽 또는 센서 데이터 없음, 생성 건너뜀")
                                    continue 

                                self.logger.debug("백그라운드 맵 생성 시작 %s (%s)",
                                                self.logger._colorize(map_name, "blue"), map_id)
                                                                
                                # 맵 생성 전 연결 상태 확인 (현재 이벤트 루프 확인)
                                try:
                                    current_loop = asyncio.get_running_loop()
                                    if current_loop != loop:
                                        self.logger.warning(f"맵 생성 전 이벤트 루프가 변경됨: 원래={loop_id}, 현재={id(current_loop)}")
                                        # 다시 원래 루프 설정
                                        asyncio.set_event_loop(loop)
                                except RuntimeError:
                                    # 실행 중인 이벤트 루프가 없으면 기존 루프 설정
                                    asyncio.set_event_loop(loop)
                                    self.logger.debug("맵 생성 전 이벤트 루프 재설정됨")
                                                                
                                try:
                                    # 맵 생성 태스크 실행 (기존 이벤트 루프 사용)
                                    if loop.run_until_complete(self.generate_map(map_id)):
                                        self.logger.info("백그라운드 맵 생성 완료 %s (%s) (소요시간: %s)",
                                                        self.logger._colorize(map_name, "blue"),
                                                        map_id,
                                                        self.logger._colorize(self.map_generator.generation_duration, "green"))
                                        self.map_timers[map_id] = current_time
                                    else:
                                        self.logger.error("백그라운드 맵 생성 실패 %s (%s)",
                                                        self.logger._colorize(map_name, "blue"),
                                                        map_id)
                                except Exception as e:
                                    self.logger.error("맵 생성 중 오류 발생: %s",
                                                    self.logger._colorize(str(e), "red"))
                                    import traceback
                                    self.logger.error(traceback.format_exc())

                        except Exception as e:
                            self.logger.error(f"맵 {map_name} ({map_id}) 처리 중 오류 발생: {str(e)}")
                            import traceback
                            self.logger.error(traceback.format_exc())
                            continue

                    # 다음 실행 전 대기
                    time.sleep(60)  # 1분 대기
                    
                except Exception as e:
                    self.logger.error(f"백그라운드 작업 중 오류 발생: {str(e)}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    time.sleep(60)
        finally:
            # 스레드 종료 시 이벤트 루프 정리
            try:
                # 웹소켓 연결 종료
                loop.run_until_complete(self.sensor_manager.websocket_client.close())
                
                # 실행 중인 모든 태스크 가져오기
                pending = asyncio.all_tasks(loop)
                
                # 태스크 취소
                for task in pending:
                    task.cancel()
                
                # 취소된 태스크들이 완료될 때까지 대기
                if pending:
                    try:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    except asyncio.CancelledError:
                        self.logger.debug("태스크가 취소되었습니다")
                    except Exception as gather_error:
                        self.logger.error(f"태스크 정리 중 gather 오류: {str(gather_error)}")
            except Exception as cleanup_error:
                self.logger.error(f"태스크 정리 중 오류 발생: {str(cleanup_error)}")
                import traceback
                self.logger.error(traceback.format_exc())
            finally:
                try:
                    # 이벤트 루프 종료 전에 모든 태스크가 완료되었는지 확인
                    pending = asyncio.all_tasks(loop)
                    if pending:
                        self.logger.warning(f"아직 {len(pending)}개의 태스크가 남아있습니다")
                        
                    loop.run_until_complete(asyncio.sleep(0.1))  # 잠시 대기하여 태스크 정리 시간 제공
                    loop.stop()
                    loop.close()
                    self.logger.debug(f"백그라운드 작업용 이벤트 루프 종료 (ID: {loop_id})")
                except Exception as close_error:
                    self.logger.error(f"이벤트 루프 종료 중 오류 발생: {str(close_error)}")
                    import traceback
                    self.logger.error(traceback.format_exc())

if __name__ == '__main__':
    is_local = False
    try:
        with open('/data/options.json') as file:
            CONFIG = json.load(file)
    except:
        is_local = True
    config_manager = ConfigManager(is_local, CONFIG)
    log_level = str(CONFIG.get('log_level', 'debug')).upper()
    # 로그 디렉토리 생성 
    log_dir = os.path.dirname(config_manager.paths['log'])
    os.makedirs(log_dir, exist_ok=True)

    # 로거 초기화
    logger = CustomLogger(log_file=config_manager.paths['log'], log_level=str(log_level))
    logger.info("애플리케이션 시작 (로그 레벨: " + log_level + ")")

    supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
    try:
        # 메인 스레드에서 이벤트 루프 생성 및 설정
        logger.debug("메인 이벤트 루프 생성 시작")
        try:
            # 이미 실행 중인 이벤트 루프가 있는지 확인
            loop = asyncio.get_running_loop()
            logger.debug("기존 이벤트 루프 사용")
        except RuntimeError:
            # 실행 중인 이벤트 루프가 없으면 새로 생성
            logger.debug("새 이벤트 루프 생성")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # 이벤트 루프 정책 설정 (운영체제에 맞게 최적화된 정책 사용)
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy') and os.name == 'nt':
            # Windows 환경인 경우
            logger.debug("Windows 환경에 맞는 이벤트 루프 정책 설정")
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        logger.debug("메인 이벤트 루프 ID: %s", id(loop))
        
        logger.debug("SensorManager 및 웹소켓 클라이언트 초기화 시작")
        sensor_manager = SensorManager(is_local, config_manager, logger, supervisor_token)
        logger.debug("SensorManager 및 웹소켓 클라이언트 초기화 완료")
        
        logger.debug("MapGenerator 초기화 시작")
        map_generator = MapGenerator(config_manager, sensor_manager, logger)
        logger.debug("MapGenerator 초기화 완료")
        
        logger.debug("WebServer 초기화 시작")
        server = WebServer(config_manager,sensor_manager,map_generator,logger)
        logger.debug("WebServer 초기화 완료")
        
        logger.debug("BackgroundTaskManager 초기화 시작")
        background_task_manager = BackgroundTaskManager(logger,config_manager,sensor_manager,map_generator)
        logger.debug("BackgroundTaskManager 초기화 완료")

        # 백그라운드 작업 시작
        background_task_manager.start()
        logger.debug("백그라운드 작업 시작됨")

        try:
            server.run()
        finally:
            background_task_manager.stop()
            logger.debug("백그라운드 작업 중지됨")
            
            # 메인 이벤트 루프 정리
            try:
                # 실행 중인 모든 태스크 가져오기
                pending = asyncio.all_tasks(loop)
                
                # 태스크 취소
                for task in pending:
                    task.cancel()
                
                # 취소된 태스크들이 완료될 때까지 대기
                if pending:
                    try:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    except asyncio.CancelledError:
                        logger.debug("태스크가 취소되었습니다")
                    except Exception as gather_error:
                        logger.error(f"태스크 정리 중 gather 오류: {str(gather_error)}")
                
                # 이벤트 루프 종료
                loop.stop()
                loop.close()
                logger.debug("메인 이벤트 루프 종료")
            except Exception as loop_cleanup_error:
                logger.error(f"이벤트 루프 정리 중 오류: {str(loop_cleanup_error)}")
                
    except Exception as e:
        logger.error(f"애플리케이션 실행 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
