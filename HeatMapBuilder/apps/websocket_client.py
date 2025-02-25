import websockets # type: ignore
import json
from typing import Optional, Dict, Any, List
import asyncio
import logging
import time

class WebSocketClient:
    def __init__(self, supervisor_token: str, logger: logging.Logger):
        self.supervisor_token = supervisor_token
        self.logger = logger
        self.message_id = 1
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.reconnect_attempt = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self._connection_lock = None  # 초기에는 Lock을 생성하지 않고 None으로 설정
        self._event_loop = None       # 이벤트 루프 참조 저장
        self._keepalive_tasks = set()  # keepalive 태스크 추적용
        self.logger.info(f"WebSocketClient 초기화: message_id={self.message_id}")

    async def _get_connection_lock(self):
        """현재 이벤트 루프에 맞는 connection lock을 반환합니다."""
        current_loop = asyncio.get_running_loop()
        
        # 이벤트 루프가 변경되었거나 lock이 없는 경우 새로 생성
        if self._connection_lock is None or self._event_loop != current_loop:
            self.logger.debug("현재 이벤트 루프에 맞는 새 connection lock 생성")
            self._connection_lock = asyncio.Lock()
            self._event_loop = current_loop
            
        return self._connection_lock

    def _truncate_log_message(self, message: str, max_length: int = 100) -> str:
        """로그 메시지를 지정된 길이로 잘라서 반환합니다."""
        if len(message) <= max_length:
            return message
        return message[:max_length] + "..."

    async def _cleanup_keepalive_tasks(self):
        """keepalive 태스크들을 정리합니다."""
        for task in list(self._keepalive_tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._keepalive_tasks.discard(task)

    async def close(self):
        """웹소켓 연결을 안전하게 종료합니다."""
        lock = await self._get_connection_lock()
        
        async with lock:
            # keepalive 태스크들 정리
            await self._cleanup_keepalive_tasks()
            
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception as e:
                    self.logger.error(f"웹소켓 연결 종료 중 오류 발생: {str(e)}")
                finally:
                    self.websocket = None

    async def ensure_connected(self) -> bool:
        """연결 상태를 확인하고 필요한 경우 재연결합니다."""
        # 현재 이벤트 루프에 맞는 lock 가져오기
        lock = await self._get_connection_lock()
        
        async with lock:
            try:
                if self.websocket:
                    # open 속성이 있는지 확인하고 안전하게 접근
                    is_open = getattr(self.websocket, 'open', None)
                    if is_open is not None and is_open:
                        self.logger.debug("웹소켓 연결 상태: 열려있음")
                        return True
                    # 웹소켓이 있지만 open 속성이 없거나 False라면 연결 상태 확인 시도
                    try:
                        # 간단한 ping 메시지를 보내 연결 상태 확인
                        self.logger.debug("웹소켓 연결 상태 확인 중: ping 시도")
                        pong_waiter = await self.websocket.ping()
                        await asyncio.wait_for(pong_waiter, timeout=2.0)
                        self.logger.debug("웹소켓 ping 성공")
                        return True
                    except asyncio.TimeoutError:
                        self.logger.info("웹소켓 ping 타임아웃, 연결 재시도 필요")
                    except Exception as e:
                        self.logger.info(f"웹소켓 ping 실패, 연결 재시도 필요: {str(e)}")
            except Exception as e:
                self.logger.info(f"웹소켓 연결 상태 확인 중 오류: {str(e)}")

            # 이 지점에 도달하면 연결이 끊어진 것으로 간주하고 재연결 시도
            self.logger.info("웹소켓 연결 없음 또는 끊어짐, 재연결 시도 시작")
            await self.close()

            self.reconnect_attempt = 0  # 재연결 시도 카운터 초기화
            max_reconnect_time = 30  # 최대 재연결 시도 시간 (초)
            start_time = time.time()
            
            while self.reconnect_attempt < self.max_reconnect_attempts:
                # 최대 재연결 시간 체크
                if time.time() - start_time > max_reconnect_time:
                    self.logger.error(f"최대 재연결 시간 초과: {max_reconnect_time}초")
                    return False
                    
                self.reconnect_attempt += 1
                self.logger.info(f"웹소켓 재연결 시도 {self.reconnect_attempt}/{self.max_reconnect_attempts}")
                
                try:
                    # 연결 시도 시간 측정
                    connect_start = time.time()
                    self.logger.info("_connect 메서드 호출 시작")
                    
                    # 웹소켓 연결 시도 (타임아웃 10초)
                    self.websocket = await asyncio.wait_for(self._connect(), timeout=10.0)
                    
                    connect_time = time.time() - connect_start
                    
                    if self.websocket:
                        self.logger.info(f"웹소켓 재연결 성공 (소요시간: {connect_time:.3f}초)")
                        self.reconnect_attempt = 0
                        
                        # 연결 성공 확인 - 인증 상태 확인
                        self.logger.info("웹소켓 연결 후 상태 확인:")
                        is_open = getattr(self.websocket, 'open', None)
                        self.logger.info(f"웹소켓 open 속성: {is_open}")
                        
                        return True
                    
                    self.logger.warning(f"웹소켓 재연결 실패: _connect()에서 None 반환 (시도 {self.reconnect_attempt})")
                    delay = self.reconnect_delay * (1.5 ** (self.reconnect_attempt - 1))  # 지수 백오프
                    self.logger.info(f"{delay:.1f}초 후 재시도...")
                    await asyncio.sleep(delay)
                    
                except asyncio.TimeoutError:
                    connect_time = time.time() - connect_start
                    self.logger.error(f"웹소켓 연결 타임아웃 (소요시간: {connect_time:.3f}초, 시도 {self.reconnect_attempt})")
                    delay = self.reconnect_delay * (1.5 ** (self.reconnect_attempt - 1))  # 지수 백오프
                    self.logger.info(f"{delay:.1f}초 후 재시도...")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    self.logger.error(f"웹소켓 재연결 시도 중 오류 발생 (시도 {self.reconnect_attempt}): {str(e)}")
                    # 오류 상세 정보 출력
                    import traceback
                    self.logger.error(traceback.format_exc())
                    
                    delay = self.reconnect_delay * (1.5 ** (self.reconnect_attempt - 1))  # 지수 백오프
                    self.logger.info(f"{delay:.1f}초 후 재시도...")
                    await asyncio.sleep(delay)

            self.logger.error("최대 재연결 시도 횟수 초과")
            return False

    async def _connect(self) -> Optional[websockets.WebSocketClientProtocol]:
        websocket = None
        try:
            uri = "ws://supervisor/core/api/websocket"
            self.logger.info(f"웹소켓 연결 시도: {uri}")
            connect_start = time.time()
            
            # 연결 시도
            self.logger.info("웹소켓 물리적 연결 시도 중...")
            try:
                websocket = await websockets.connect(uri, 
                                                   max_size=2**24,
                                                   max_queue=2**10,
                                                   compression=None)
                connect_time = time.time() - connect_start
                self.logger.info(f"웹소켓 연결 수립 성공 (소요시간: {connect_time:.3f}초)")
                
                # 웹소켓 상태 로깅
                if hasattr(websocket, 'open'):
                    self.logger.info(f"웹소켓 open 상태: {websocket.open}")
                else:
                    self.logger.info("웹소켓에 open 속성이 없음")
            except Exception as conn_err:
                self.logger.error(f"웹소켓 물리적 연결 실패: {str(conn_err)}")
                import traceback
                self.logger.error(traceback.format_exc())
                return None
            
            # keepalive 태스크 추적 시작
            if hasattr(websocket, '_keepalive_ping') and websocket._keepalive_ping is not None:
                self._keepalive_tasks.add(websocket._keepalive_ping)
                self.logger.debug("keepalive_ping 태스크 추적 시작")
            if hasattr(websocket, '_keepalive_pong') and websocket._keepalive_pong is not None:
                self._keepalive_tasks.add(websocket._keepalive_pong)
                self.logger.debug("keepalive_pong 태스크 추적 시작")
            
            # 서버로부터 초기 메시지 수신 대기
            self.logger.info("인증 요청 메시지 수신 대기 중...")
            try:
                auth_required = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                auth_required_data = json.loads(auth_required)
                self.logger.info(f"수신 메시지: {self._truncate_log_message(auth_required)}")
                
                if auth_required_data.get('type') != 'auth_required':
                    self.logger.error(f"예상치 못한 초기 메시지 타입: {auth_required_data.get('type', '알 수 없음')}")
                    await websocket.close()
                    return None
            except asyncio.TimeoutError:
                self.logger.error("인증 요청 메시지 수신 타임아웃")
                await websocket.close()
                return None
            except Exception as auth_req_err:
                self.logger.error(f"인증 요청 메시지 수신 중 오류: {str(auth_req_err)}")
                import traceback
                self.logger.error(traceback.format_exc())
                await websocket.close()
                return None
            
            # 인증 메시지 보내기
            try:
                auth_message = {
                    "type": "auth",
                    "access_token": self.supervisor_token
                }
                auth_message_str = json.dumps(auth_message)
                self.logger.info(f"인증 메시지 전송: {self._truncate_log_message(auth_message_str)}")
                await websocket.send(auth_message_str)
            except Exception as auth_send_err:
                self.logger.error(f"인증 메시지 전송 중 오류: {str(auth_send_err)}")
                import traceback
                self.logger.error(traceback.format_exc())
                await websocket.close()
                return None
            
            # 인증 응답 대기
            try:
                self.logger.info("인증 응답 대기 중...")
                auth_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                self.logger.info(f"인증 응답 수신: {self._truncate_log_message(auth_response)}")
                auth_response_data = json.loads(auth_response)
                
                if auth_response_data.get('type') == 'auth_ok':
                    self.logger.info("웹소켓 인증 성공")
                    return websocket
                else:
                    self.logger.error(f"웹소켓 인증 실패: {auth_response_data.get('type', '알 수 없음')}")
                    await websocket.close()
                    return None
            except asyncio.TimeoutError:
                self.logger.error("인증 응답 대기 타임아웃")
                await websocket.close()
                return None
            except Exception as auth_resp_err:
                self.logger.error(f"인증 응답 처리 중 오류: {str(auth_resp_err)}")
                import traceback
                self.logger.error(traceback.format_exc())
                await websocket.close()
                return None
                
        except asyncio.TimeoutError as e:
            self.logger.error(f"웹소켓 연결 또는 인증 타임아웃: {str(e)}")
            if websocket:
                await websocket.close()
            return None
        except Exception as e:
            self.logger.error(f"웹소켓 연결 실패: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            if websocket:
                await websocket.close()
            return None

    async def send_message(self, message_type: str, **kwargs) -> Optional[Any]:
        # message_id 확인 및 0 또는 음수일 경우 리셋
        if self.message_id <= 0:
            self.logger.warning(f"message_id가 유효하지 않음: {self.message_id}, 1로 리셋합니다")
            self.message_id = 1
        
        # 중요 요청에 대한 재시도 로직
        max_retries = 3  # 최대 재시도 횟수
        retry_count = 0
        
        # 중요 요청인지 확인
        is_critical_request = message_type in ["config/entity_registry/list", "config/label_registry/list"]
        
        while retry_count <= max_retries:
            # 재시도 중인 경우 로깅
            if retry_count > 0 and is_critical_request:
                self.logger.warning(f"{message_type} 요청 재시도 중 ({retry_count}/{max_retries})...")
                await asyncio.sleep(2)  # 재시도 전 잠시 대기
            
            # 먼저 연결 확인
            connection_success = await self.ensure_connected()
            if not connection_success or not self.websocket:
                self.logger.error(f"웹소켓 연결 실패로 메시지를 보낼 수 없습니다: {message_type}")
                # 중요 메시지 유형의 경우 연결 없음을 더 자세히 로깅
                if message_type in ["get_states", "config/entity_registry/list", "config/label_registry/list"]:
                    self.logger.error(f"중요 메시지 {message_type} 전송 실패: 웹소켓 연결 없음")
                
                # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                if is_critical_request and retry_count < max_retries:
                    retry_count += 1
                    continue
                return None
                
            # 메시지 ID 할당 전에 현재 값 로깅
            current_id = self.message_id
            self.logger.info(f"메시지 ID 할당: current_id={current_id}, 타입={message_type}")
                
            message = {
                "id": current_id,
                "type": message_type,
                **kwargs
            }
            
            # 다음 메시지를 위해 ID 증가
            self.message_id += 1
            self.logger.info(f"메시지 ID 증가: 새 message_id={self.message_id}")
            
            try:
                message_str = json.dumps(message)
                self.logger.info(f"송신 메시지 (ID: {message['id']}, 타입: {message_type}): {self._truncate_log_message(message_str)}")
                
                # 특별히 get_states 요청인 경우 더 자세한 로깅
                if message_type == "get_states":
                    self.logger.info(f"===== get_states 요청 전송 시작 (ID: {message['id']}) =====")
                elif message_type == "config/entity_registry/list":
                    self.logger.info(f"===== Entity Registry 요청 전송 시작 (ID: {message['id']}) =====")
                elif message_type == "config/label_registry/list":
                    self.logger.info(f"===== Label Registry 요청 전송 시작 (ID: {message['id']}) =====")
                
                # 메시지 전송 전 연결 상태 한번 더 확인
                if not self.websocket or not getattr(self.websocket, 'open', False):
                    self.logger.error(f"메시지 전송 직전 웹소켓 연결이 끊어짐 (ID: {message['id']}, 타입: {message_type})")
                    await self.ensure_connected()
                    if not self.websocket:
                        self.logger.error(f"재연결 실패, 메시지 전송 불가 (ID: {message['id']}, 타입: {message_type})")
                        
                        # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                        if is_critical_request and retry_count < max_retries:
                            retry_count += 1
                            continue
                        return None
                
                # 메시지 전송
                send_start_time = time.time()
                await self.websocket.send(message_str)
                send_time = time.time() - send_start_time
                
                self.logger.info(f"메시지 전송 완료 (ID: {message['id']}, 타입: {message_type}, 소요시간: {send_time:.3f}초)")
                
                # 응답 대기 시간 설정 (메시지 타입별로 다르게 설정)
                timeout = 30.0  # 기본 타임아웃
                if message_type == "get_states":
                    # get_states는 데이터가 많을 수 있으므로 타임아웃을 더 길게 설정
                    timeout = 60.0
                elif message_type == "config/entity_registry/list":
                    # Entity Registry는 중요한 요청이므로 충분한 타임아웃 설정
                    timeout = 45.0
                elif message_type == "config/label_registry/list":
                    # Label Registry는 중요한 요청이므로 충분한 타임아웃 설정
                    timeout = 45.0
                    
                start_time = time.time()
                
                # 응답 대기 시작 로깅
                self.logger.info(f"응답 대기 시작 (ID: {message['id']}, 타입: {message_type}, 제한시간: {timeout}초)")
                
                # 최대 메시지 처리 시도 횟수 설정
                max_message_attempts = 15  # 최대 15번의 다른 메시지를 처리할 수 있음
                message_attempts = 0
                
                # 상태 확인 간격 (초)
                check_interval = 5.0
                last_check_time = start_time
                
                # 응답 수신 대기 루프
                while True:
                    # 타임아웃 체크
                    elapsed_time = time.time() - start_time
                    if elapsed_time > timeout:
                        self.logger.error(f"응답 타임아웃 (ID: {message['id']}, 타입: {message_type}, 제한시간: {timeout}초)")
                        
                        # 메시지 타입별 타임아웃 처리
                        if message_type in ["get_states", "config/entity_registry/list", "config/label_registry/list"]:
                            self.logger.warning(f"{message_type} 요청 타임아웃으로 연결을 재설정합니다")
                            await self.close()
                        
                        # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                        if is_critical_request and retry_count < max_retries:
                            self.logger.warning(f"{message_type} 요청 타임아웃으로 재시도합니다 ({retry_count + 1}/{max_retries})")
                            retry_count += 1
                            break  # while True 루프 빠져나가서 재시도
                        
                        # 메시지 ID는 증가된 상태로 유지 (다음 요청을 위해)
                        return None
                    
                    # 연결 상태 주기적 확인 (5초마다)
                    current_time = time.time()
                    if current_time - last_check_time >= check_interval:
                        last_check_time = current_time
                        try:
                            if not self.websocket or not getattr(self.websocket, 'open', False):
                                self.logger.error(f"응답 대기 중 웹소켓 연결이 끊어짐 (ID: {message['id']}, 타입: {message_type})")
                                
                                # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                                if is_critical_request and retry_count < max_retries:
                                    self.logger.warning(f"{message_type} 요청 중 연결 끊김으로 재시도합니다 ({retry_count + 1}/{max_retries})")
                                    retry_count += 1
                                    await self.close()
                                    break  # while True 루프 빠져나가서 재시도
                                
                                await self.close()
                                return None
                        except Exception as e:
                            self.logger.error(f"웹소켓 상태 확인 중 오류: {str(e)}")
                        
                        # 진행 상황 로깅
                        self.logger.debug(f"응답 대기 중... (ID: {message['id']}, 타입: {message_type}, 경과시간: {elapsed_time:.1f}초/{timeout}초)")
                        
                    try:
                        # 응답 대기 (짧은 타임아웃으로 여러 번 시도)
                        wait_start_time = time.time()
                        response = await asyncio.wait_for(self.websocket.recv(), 3.0)
                        wait_time = time.time() - wait_start_time
                        
                        self.logger.info(f"메시지 수신 (소요시간: {wait_time:.3f}초): {self._truncate_log_message(response)}")
                        
                        try:
                            response_data = json.loads(response)
                        except json.JSONDecodeError as json_err:
                            self.logger.error(f"JSON 파싱 오류: {str(json_err)}, 원본: {self._truncate_log_message(response)}")
                            continue
                        
                        # 현재 처리 중인 요청에 대한 응답인지 확인
                        if 'id' in response_data:
                            # 응답 ID 확인
                            if response_data.get('id') == message['id']:
                                total_time = time.time() - start_time
                                
                                if response_data.get('success', True):  # success 필드가 없으면 기본적으로 성공으로 간주
                                    result = response_data.get('result')
                                    result_size = len(result) if isinstance(result, list) else "N/A"
                                    
                                    self.logger.info(f"요청 성공 (ID: {message['id']}, 타입: {message_type}, 총 소요시간: {total_time:.3f}초, 결과 크기: {result_size})")
                                    
                                    # 메시지 타입별 상세 로깅
                                    if message_type == "get_states" and isinstance(result, list):
                                        temp_sensors = [s for s in result if s.get('entity_id', '').startswith('sensor.temperature')]
                                        self.logger.info(f"get_states 결과: 전체 {len(result)}개 항목, 온도 센서 {len(temp_sensors)}개")
                                        
                                        # 온도 센서 값 확인
                                        zero_temp_count = sum(1 for s in temp_sensors if s.get('state') == '0' or s.get('state') == '0.0')
                                        if zero_temp_count > 0:
                                            self.logger.warning(f"주의: {zero_temp_count}개 온도 센서가 0°C를 보고하고 있습니다")
                                    elif message_type == "config/entity_registry/list" and isinstance(result, list):
                                        self.logger.info(f"Entity Registry 결과: {len(result)}개 항목")
                                    elif message_type == "config/label_registry/list" and isinstance(result, list):
                                        self.logger.info(f"Label Registry 결과: {len(result)}개 항목")
                                    
                                    return result
                                else:
                                    error_msg = response_data.get('error', {}).get('message', '알 수 없는 오류')
                                    self.logger.error(f"웹소켓 요청 실패 (ID: {message['id']}, 타입: {message_type}, 총 소요시간: {total_time:.3f}초): {error_msg}")
                                    
                                    # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                                    if is_critical_request and retry_count < max_retries:
                                        self.logger.warning(f"{message_type} 요청 실패로 재시도합니다 ({retry_count + 1}/{max_retries})")
                                        retry_count += 1
                                        break  # while True 루프 빠져나가서 재시도
                                    
                                    return None
                            else:
                                # 다른 메시지에 대한 응답인 경우 로깅
                                other_id = response_data.get('id')
                                self.logger.info(f"다른 메시지 응답 수신 (요청 ID: {message['id']}, 응답 ID: {other_id})")
                                
                                # 다른 메시지가 너무 많이 수신되면 타임아웃 처리
                                message_attempts += 1
                                if message_attempts >= max_message_attempts:
                                    self.logger.error(f"너무 많은 다른 메시지 수신으로 응답 포기 (ID: {message['id']}, 타입: {message_type})")
                                    
                                    # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                                    if is_critical_request and retry_count < max_retries:
                                        self.logger.warning(f"{message_type} 요청을 너무 많은 다른 메시지로 재시도합니다 ({retry_count + 1}/{max_retries})")
                                        retry_count += 1
                                        break  # while True 루프 빠져나가서 재시도
                                    
                                    return None
                        else:
                            # ID가 없는 응답 (이벤트 등)은 로깅만 하고 계속 대기
                            msg_type = response_data.get('type', 'unknown')
                            if msg_type == 'event':
                                event_type = response_data.get('event', {}).get('event_type', '알 수 없음')
                                self.logger.debug(f"이벤트 메시지 수신: {event_type}")
                            else:
                                self.logger.info(f"ID 없는 메시지 수신 (타입: {msg_type})")
                            
                    except asyncio.TimeoutError:
                        # 응답 대기 타임아웃은 오류가 아님 (계속 대기)
                        continue
                        
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.error(f"웹소켓 연결이 닫힘: {str(e)}")
                await self.close()
                
                # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                if is_critical_request and retry_count < max_retries:
                    self.logger.warning(f"{message_type} 요청 중 연결 닫힘으로 재시도합니다 ({retry_count + 1}/{max_retries})")
                    retry_count += 1
                    continue
                
                return None
            except Exception as e:
                import traceback
                self.logger.error(f"웹소켓 통신 중 오류 발생: {str(e)}")
                self.logger.error(traceback.format_exc())
                await self.close()
                
                # 중요 요청이고 아직 재시도 횟수가 남아있으면 재시도
                if is_critical_request and retry_count < max_retries:
                    self.logger.warning(f"{message_type} 요청 중 오류로 재시도합니다 ({retry_count + 1}/{max_retries})")
                    retry_count += 1
                    continue
                
                return None
                
        # 최대 재시도 횟수를 초과한 경우
        if is_critical_request and retry_count > max_retries:
            self.logger.error(f"{message_type} 요청 최대 재시도 횟수 ({max_retries})를 초과했습니다")
            
        return None

class MockWebSocketClient:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.websocket = True  # 연결된 것으로 간주
        self._event_loop = None
        self._connection_lock = None
        self._mock_data = None
        self.message_id = 1
        self.reconnect_attempt = 0
        self.logger = logging.getLogger("MockWebSocketClient")
        self.logger.info(f"MockWebSocketClient 초기화: message_id={self.message_id}")

    def _truncate_log_message(self, message: str, max_length: int = 100) -> str:
        """로그 메시지를 지정된 길이로 잘라서 반환합니다."""
        if len(message) <= max_length:
            return message
        return message[:max_length] + "..."

    async def _get_connection_lock(self):
        """현재 이벤트 루프에 맞는 connection lock을 반환합니다."""
        current_loop = asyncio.get_running_loop()
        
        # 이벤트 루프가 변경되었거나 lock이 없는 경우 새로 생성
        if self._connection_lock is None or self._event_loop != current_loop:
            self.logger.debug("모의 웹소켓: 현재 이벤트 루프에 맞는 새 connection lock 생성")
            self._connection_lock = asyncio.Lock()
            self._event_loop = current_loop
            
        return self._connection_lock

    async def ensure_connected(self) -> bool:
        """웹소켓 연결 상태를 확인합니다. 모의 클라이언트는 항상 연결된 것으로 간주합니다."""
        self.logger.debug("모의 웹소켓 연결 상태 확인 (항상 True 반환)")
        # 가끔 재연결 과정을 시뮬레이션
        if self.reconnect_attempt > 0:
            self.logger.info(f"모의 웹소켓 재연결 시도 중 (시도: {self.reconnect_attempt})")
            await asyncio.sleep(0.2)
            self.reconnect_attempt = 0
            self.logger.info("모의 웹소켓 재연결 성공")
        
        # 간단한 지연 추가
        await asyncio.sleep(0.05)
        return True

    def _get_mock_data(self):
        """mock 데이터를 가져오고 필요한 경우 초기화합니다."""
        if self._mock_data is None:
            self.logger.info("모의 데이터 초기화 중...")
            self._mock_data = self.config_manager.get_mock_data()
            
            # 온도 센서 데이터가 없거나 모든 값이 0인 경우 기본값 설정
            temp_sensors = self._mock_data.get('temperature_sensors', [])
            if not temp_sensors or all(float(sensor.get('state', '0')) == 0 for sensor in temp_sensors):
                # 기본 온도값 범위 설정 (20°C ~ 25°C)
                import random
                for sensor in temp_sensors:
                    sensor['state'] = str(round(random.uniform(20, 25), 1))
                    if 'attributes' not in sensor:
                        sensor['attributes'] = {}
                    sensor['attributes']['unit_of_measurement'] = '°C'
                self._mock_data['temperature_sensors'] = temp_sensors
                self.logger.info(f"기본 온도 센서 데이터 생성: {len(temp_sensors)}개")
        
        return self._mock_data

    async def send_message(self, message_type: str, **kwargs) -> Optional[Any]:
        try:
            # message_id 확인 및 0 또는 음수일 경우 리셋
            if self.message_id <= 0:
                self.logger.warning(f"모의 message_id가 유효하지 않음: {self.message_id}, 1로 리셋합니다")
                self.message_id = 1
            
            # 현재 이벤트 루프에 맞는 lock 가져오기
            lock = await self._get_connection_lock()
            if not lock:
                self.logger.error(f"락을 획득할 수 없어 모의 메시지를 보낼 수 없습니다: {message_type}")
                return None
            
            async with lock:
                # 연결 상태 시뮬레이션 (약간의 지연)
                await self.ensure_connected()
                
                # 메시지 ID 할당 전에 현재 값 로깅
                current_id = self.message_id
                self.logger.info(f"모의 메시지 ID 할당: current_id={current_id}, 타입={message_type}")
                
                message_data = {"id": current_id, "type": message_type, **kwargs}
                message_str = json.dumps(message_data)
                
                # 다음 메시지를 위해 ID 증가
                self.message_id += 1
                self.logger.info(f"모의 메시지 ID 증가: 새 message_id={self.message_id}")
                
                self.logger.info(f"모의 송신 메시지 (ID: {current_id}, 타입: {message_type}): {self._truncate_log_message(message_str)}")
                
                # 메시지 타입별 로깅
                if message_type == "get_states":
                    self.logger.info(f"===== 모의 get_states 요청 처리 시작 (ID: {current_id}) =====")
                elif message_type == "config/entity_registry/list":
                    self.logger.info(f"===== 모의 Entity Registry 요청 처리 시작 (ID: {current_id}) =====")
                elif message_type == "config/label_registry/list":
                    self.logger.info(f"===== 모의 Label Registry 요청 처리 시작 (ID: {current_id}) =====")
                
                # 의도적으로 약간의 지연 추가 (실제 네트워크 통신 시뮬레이션)
                start_time = time.time()
                
                # 메시지 타입별 처리 지연 시간
                delay = 0.1  # 기본 지연
                if message_type == "get_states":
                    delay = 0.5  # 더 긴 지연
                elif message_type in ["config/entity_registry/list", "config/label_registry/list"]:
                    delay = 0.3  # 중간 정도 지연
                
                await asyncio.sleep(delay)
                
                mock_data = self._get_mock_data()
                
                if message_type == 'auth':
                    response = {"type": "auth_ok", "id": current_id}
                    self.logger.info(f"모의 인증 응답 (ID: {current_id}): {self._truncate_log_message(json.dumps(response))}")
                    return response
                elif message_type == 'get_states':
                    result = mock_data.get('temperature_sensors', [])
                    elapsed_time = time.time() - start_time
                    
                    # 온도 센서 값 확인
                    zero_temp_count = sum(1 for s in result if s.get('state') == '0' or s.get('state') == '0.0')
                    
                    self.logger.info(f"모의 상태 조회 결과 (ID: {current_id}, 타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 센서 데이터")
                    
                    if zero_temp_count > 0:
                        self.logger.warning(f"주의: 모의 데이터에 {zero_temp_count}개 온도 센서가 0°C를 보고하고 있습니다")
                    
                    return result
                elif message_type == 'config/entity_registry/list':
                    result = mock_data.get('entity_registry', [])
                    elapsed_time = time.time() - start_time
                    self.logger.info(f"모의 엔티티 레지스트리 조회 결과 (ID: {current_id}, 타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 항목")
                    return result
                elif message_type == 'config/label_registry/list':
                    result = mock_data.get('label_registry', [])
                    elapsed_time = time.time() - start_time
                    self.logger.info(f"모의 레이블 레지스트리 조회 결과 (ID: {current_id}, 타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 항목")
                    return result
                    
                self.logger.info(f"모의 응답 없음 (ID: {current_id}, 타입: {message_type})")
                return None
        except Exception as e:
            import traceback
            self.logger.error(f"모의 웹소켓 통신 중 오류 발생 (타입: {message_type}): {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
            
    async def _connect(self):
        """웹소켓 연결을 시도합니다. MockWebSocketClient의 경우 항상 성공으로 처리합니다."""
        self.logger.info("모의 웹소켓 _connect 호출됨")
        
        # 모의 연결 지연 시뮬레이션
        await asyncio.sleep(0.1)
        
        # 연결 확인
        await self.ensure_connected()
        
        # 모의 웹소켓은 항상 True를 웹소켓 객체로 사용
        self.websocket = True
        self.logger.info("모의 웹소켓 연결 수립 성공")
        
        return self.websocket

    async def close(self):
        self.logger.info("모의 웹소켓 연결 종료")
        self.websocket = None
        
        # 현재 이벤트 루프에 맞는 lock 가져오기
        try:
            lock = await self._get_connection_lock()
            async with lock:
                self._event_loop = None
                self._connection_lock = None
                self.logger.debug("모의 웹소켓 자원 정리 완료")
        except Exception as e:
            self.logger.error(f"모의 웹소켓 연결 종료 중 오류 발생: {str(e)}")
            pass 