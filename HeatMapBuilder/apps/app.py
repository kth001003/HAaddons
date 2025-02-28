import threading
import json
import time
import os
import asyncio
import glob
import shutil
from PIL import Image  # Pillow 라이브러리 추가

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
        self.map_lock = threading.Lock()
        self.map_timers = {}
        self._main_loop = None
        self._task = None

    def start(self):
        self.running = True
        self._main_loop = asyncio.get_event_loop()
        self.logger.debug(f"백그라운드 작업 이벤트 루프 ID: {id(self._main_loop)}")
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self._task is not None:
            self._task.cancel()
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
            
            # 현재 존재하는 파일들의 목록을 미리 확보
            existing_files = []
            if os.path.exists(output_path):
                existing_files.append((output_path, 0))
            for i in range(1, rotation_count):
                file_path = f"{base_path}-{i}{ext}"
                if os.path.exists(file_path):
                    existing_files.append((file_path, i))
            
            # 가장 오래된 백업 파일 삭제
            old_file = f"{base_path}-{rotation_count-1}{ext}"
            try:
                if os.path.exists(old_file):
                    os.remove(old_file)
            except Exception as e:
                self.logger.warning(f"오래된 파일 삭제 실패: {str(e)}")

            # 기존 백업 파일들의 번호를 하나씩 증가
            for old_path, index in reversed(existing_files):
                try:
                    new_name = f"{base_path}-{index+1}{ext}"
                    if os.path.exists(old_path):  # 한번 더 확인
                        shutil.move(old_path, new_name)
                except Exception as e:
                    self.logger.warning(f"파일 이동 실패 ({old_path} -> {new_name}): {str(e)}")

            # GIF 생성
            try:
                images = []
                opened_images = []  # 리소스 정리를 위한 리스트
                
                try:
                    # 가장 오래된 이미지부터 최신 순으로 GIF에 추가
                    for i in range(rotation_count-1, 0, -1):
                        img_path = f"{base_path}-{i}{ext}"
                        if os.path.exists(img_path):
                            try:
                                img = Image.open(img_path)
                                images.append(img)
                                opened_images.append(img)
                            except Exception as e:
                                self.logger.warning(f"이미지 열기 실패 ({img_path}): {str(e)}")
                    
                    # 마지막으로 현재 이미지 추가
                    if os.path.exists(output_path):
                        try:
                            img = Image.open(output_path)
                            images.append(img)
                            opened_images.append(img)
                        except Exception as e:
                            self.logger.warning(f"현재 이미지 열기 실패: {str(e)}")

                    if images:
                        # GIF 파일 경로
                        gif_path = f"{base_path}_animation.gif"
                        # 이미지들을 저장 (이미 오래된 순서부터 정렬되어 있음)
                        try:
                            images[0].save(
                                gif_path,
                                save_all=True,
                                append_images=images[1:],
                                duration=1000,  # 각 프레임 간 시간 간격 (밀리초)
                                loop=0  # 무한 반복
                            )
                            self.logger.debug(f"GIF 애니메이션 생성 완료: {gif_path}")
                        except Exception as e:
                            self.logger.error(f"GIF 저장 실패: {str(e)}")
                finally:
                    # 열린 이미지 리소스 정리
                    for img in opened_images:
                        try:
                            img.close()
                        except Exception:
                            pass
                            
            except Exception as e:
                self.logger.error(f"GIF 생성 중 오류 발생: {str(e)}")

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
                
                # 맵 생성 실행
                result = await self.map_generator.generate(map_id, _output_path)
                if not result['success']:
                    raise Exception(result['error'])
                return result['success']
            except Exception as e:
                self.logger.error(f"열지도 생성 실패: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                raise e
            finally:
                self.map_lock.release()  # 락 해제
                self.logger.trace(f"맵 생성 락 해제: {map_id}")
        else:
            self.logger.debug("다른 프로세스가 열지도를 생성 중입니다. 이번 생성은 건너뜁니다.")
            return False

    async def _run_async(self):
        """비동기 백그라운드 작업 실행"""
        # 메서드 실행 시 즉시 로그 출력
        self.logger.debug(f"백그라운드 루프 실행 중 (스레드 ID: {threading.current_thread().ident})")
        
        # 초기 상태 확인
        try:
            maps = self.config_manager.db.load()
            if maps:
                map_count = len(maps)
                auto_gen_maps = []
                for map_id, map_data in maps.items():
                    gen_config = map_data.get('gen_config', {})
                    auto_generation = gen_config.get('auto_generation', False)
                    if auto_generation:
                        auto_gen_maps.append(map_id)
                
                self.logger.debug(f"초기 맵 상태: 총 {map_count}개 맵, {len(auto_gen_maps)}개 자동 생성 활성화")
            else:
                self.logger.debug("초기 맵 상태: 등록된 맵 없음")
        except Exception as e:
            self.logger.error(f"초기 맵 상태 확인 중 오류: {str(e)}")
        
        # 실행 중인 태스크 확인을 위한 카운터
        check_counter = 0
        
        while self.running:
            try:
                current_time = time.time()
                check_counter += 1
                
                # 주기적으로 실행 상태 로깅 (약 5분마다)
                if check_counter % 5 == 0:
                    self.logger.debug(f"백그라운드 작업 확인: 실행 중 (카운터: {check_counter})")
                    
                # 모든 맵 정보를 가져옴
                maps = self.config_manager.db.load()
                if not maps:
                    self.logger.debug("등록된 맵이 없습니다. 다음 검사를 기다립니다.")
                    await asyncio.sleep(60)
                    continue
                    
                map_count = len(maps)
                auto_gen_maps = []
                
                for map_id, map_data in maps.items():
                    if not self.running:  # 실행 중지 확인
                        break
                        
                    try:
                        # 맵의 생성 설정 가져오기
                        gen_config = map_data.get('gen_config', {})
                        gen_interval = gen_config.get('gen_interval', 5) * 60  # 기본값 5분
                        map_name = map_data.get('name', '이름 없음')
                            
                        # 자동 맵 생성 설정 확인
                        auto_generation = gen_config.get('auto_generation', False)  # 기본값은 비활성화
                        
                        if auto_generation:
                            auto_gen_maps.append(map_id)
                        
                        self.logger.trace("백그라운드 작업 목록 확인: 맵 이름:%s, 맵 ID:%s, 자동생성:%s, 생성주기:%s", 
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

                            # 마지막 생성 시간과 현재 시간의 차이 계산
                            time_diff = current_time - last_gen_time
                            self.logger.debug("백그라운드 맵 생성 실행 조건 충족: %s (%s) - 마지막 생성 후 %d초 경과 (설정: %d초)",
                                            self.logger._colorize(map_name, "blue"), 
                                            map_id,
                                            int(time_diff),
                                            gen_interval)

                            self.logger.debug("백그라운드 맵 생성 시작 %s (%s)",
                                            self.logger._colorize(map_name, "blue"), map_id)
                                                            
                            try:
                                # 맵 생성 실행
                                if await self.generate_map(map_id):
                                    self.logger.info("백그라운드 맵 생성 완료 %s (%s) (소요시간: %s)",
                                                    self.logger._colorize(map_name, "blue"),
                                                    map_id,
                                                    self.logger._colorize(self.config_manager.db.get_map(map_id).get('last_generation', {}).get('duration', ''), "green"))
                                    # 현재 시간으로 타이머 업데이트
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
                        else:
                            # 다음 생성까지 남은 시간 계산
                            if auto_generation and check_counter % 5 == 0:  # 로그 과다 방지를 위해 5회 주기로만 출력
                                next_gen_time = last_gen_time + gen_interval - current_time
                                self.logger.trace("맵 %s (%s): 다음 생성까지 %d초 남음",
                                                self.logger._colorize(map_name, "blue"),
                                                map_id,
                                                int(next_gen_time))

                    except Exception as e:
                        self.logger.error(f"맵 {map_name} ({map_id}) 처리 중 오류 발생: {str(e)}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                        continue

                # 다음 실행 전 대기
                await asyncio.sleep(60)  # 10초 대기
                
                
            except Exception as e:
                self.logger.error(f"백그라운드 작업 중 오류 발생: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                await asyncio.sleep(60)

    def run(self):
        """백그라운드 작업 실행"""
        self.logger.trace("백그라운드 작업 스레드 시작")
        
        try:
            # 현재 스레드 정보 로깅
            current_thread = threading.current_thread()
            self.logger.debug(f"현재 백그라운드 스레드 ID: {current_thread.ident}, 이름: {current_thread.name}")
            
            # 이벤트 루프가 None이 아닌지 확실히 확인
            if self._main_loop is None:
                self.logger.error("백그라운드 작업 실행 실패: 이벤트 루프가 설정되지 않았습니다.")
                return
            
            # 이벤트 루프가 실행 중인지 확인
            main_loop = self._main_loop  # 타입 검사 이후 로컬 변수에 할당
            
            # 이벤트 루프가 실행 중인지 확인 - 몇 번 재시도
            MAX_RETRIES = 5
            RETRY_DELAY = 1.0  # 초
            
            for retry in range(MAX_RETRIES):
                if main_loop.is_running():
                    self.logger.debug(f"이벤트 루프 실행 중 확인됨: 시도 {retry+1}/{MAX_RETRIES}")
                    break
                    
                if retry < MAX_RETRIES - 1:
                    self.logger.debug(f"이벤트 루프가 아직 실행 중이 아님, {RETRY_DELAY}초 후 재시도 ({retry+1}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY)
            else:
                self.logger.error(f"백그라운드 작업 실행 실패: 이벤트 루프가 {MAX_RETRIES}번 시도 후에도 실행 중이 아닙니다.")
                return
                
            self.logger.debug(f"백그라운드 작업 등록 시작 - 메인 루프 ID: {id(main_loop)}")
            
            # 이벤트 루프에 코루틴 등록
            try:
                self._task = asyncio.run_coroutine_threadsafe(self._run_async(), main_loop)
                self.logger.debug(f"백그라운드 작업이 메인 이벤트 루프에 등록되었습니다 - 태스크 ID: {id(self._task)}")
                
                # 즉시 태스크 상태 확인
                if self._task.done():
                    if self._task.exception():
                        self.logger.error(f"백그라운드 작업이 즉시 실패했습니다: {self._task.exception()}")
                    else:
                        self.logger.warning("백그라운드 작업이 이미 완료되었습니다.")
                else:
                    self.logger.debug("백그라운드 작업이 실행 중입니다.")
                
                def done_callback(future):
                    try:
                        future.result()
                    except asyncio.CancelledError:
                        self.logger.debug("백그라운드 작업이 취소되었습니다.")
                    except Exception as e:
                        self.logger.error(f"백그라운드 작업 실행 중 오류: {str(e)}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                        
                        # 오류 발생 시 작업 재시작 시도
                        if self.running and self._main_loop is not None:
                            self.logger.info("백그라운드 작업 재시작 시도")
                            new_loop = self._main_loop  # 다시 타입 검사
                            self._task = asyncio.run_coroutine_threadsafe(self._run_async(), new_loop)
                            self._task.add_done_callback(done_callback)
                
                self._task.add_done_callback(done_callback)
                
            except RuntimeError as e:
                self.logger.error(f"이벤트 루프에 코루틴 등록 실패: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                return
                
        except Exception as e:
            self.logger.error(f"백그라운드 작업 시작 중 오류: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

if __name__ == '__main__':
    is_local = False
    try:
        with open('/data/options.json') as file:
            CONFIG = json.load(file)
    except:
        CONFIG = {'log_level': 'debug'}
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
        logger.trace("메인 이벤트 루프 생성 시작")
        try:
            # 이미 실행 중인 이벤트 루프가 있는지 확인
            loop = asyncio.get_running_loop()
            logger.trace("기존 이벤트 루프 사용")
        except RuntimeError:
            # 실행 중인 이벤트 루프가 없으면 새로 생성
            logger.trace("새 이벤트 루프 생성")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # 이벤트 루프 정책 설정 (운영체제에 맞게 최적화된 정책 사용)
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy') and os.name == 'nt':
            # Windows 환경인 경우
            logger.trace("Windows 환경에 맞는 이벤트 루프 정책 설정")
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        logger.trace("메인 이벤트 루프 ID: %s", id(loop))
        logger.debug("메인 이벤트 루프 설정 완료")
        
        logger.trace("SensorManager 및 웹소켓 클라이언트 초기화 시작")
        sensor_manager = SensorManager(is_local, config_manager, logger, supervisor_token)
        logger.trace("SensorManager 및 웹소켓 클라이언트 초기화 완료")
        
        logger.trace("MapGenerator 초기화 시작")
        map_generator = MapGenerator(config_manager, sensor_manager, logger)
        logger.trace("MapGenerator 초기화 완료")
        
        logger.trace("WebServer 초기화 시작")
        server = WebServer(config_manager,sensor_manager,map_generator,logger)
        logger.trace("WebServer 초기화 완료")
        
        # BackgroundTaskManager는 모든 초기화가 끝난 후 시작
        logger.trace("BackgroundTaskManager 초기화 시작")
        background_task_manager = BackgroundTaskManager(logger,config_manager,sensor_manager,map_generator)
        logger.trace("BackgroundTaskManager 초기화 완료")

        try:
            # 웹서버 시작 시 BackgroundTaskManager를 전달하여 
            # 이벤트 루프가 실행된 후 백그라운드 작업을 시작하도록 함
            logger.info("웹서버 시작")
            server.run(background_task_manager=background_task_manager)
        finally:
            # 백그라운드 작업 중지
            background_task_manager.stop()
            logger.info("백그라운드 작업 중지됨")
            
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
                        logger.trace("태스크가 취소되었습니다")
                    except Exception as gather_error:
                        logger.error(f"태스크 정리 중 gather 오류: {str(gather_error)}")
                
                # 이벤트 루프 종료
                loop.stop()
                loop.close()
                logger.trace("메인 이벤트 루프 종료")
            except Exception as loop_cleanup_error:
                logger.error(f"이벤트 루프 정리 중 오류: {str(loop_cleanup_error)}")
                
    except Exception as e:
        logger.error(f"애플리케이션 실행 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
