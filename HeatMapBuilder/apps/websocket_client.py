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
        self._connection_lock = asyncio.Lock()
        self._keepalive_tasks = set()  # keepalive 태스크 추적용
        self.logger.info(f"WebSocketClient 초기화: message_id={self.message_id}")

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
        async with self._connection_lock:
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
        async with self._connection_lock:
            try:
                if self.websocket and self.websocket.open:
                    return True
            except Exception:
                await self.close()

            while self.reconnect_attempt < self.max_reconnect_attempts:
                try:
                    self.websocket = await self._connect()
                    if self.websocket:
                        self.reconnect_attempt = 0
                        return True
                    
                    self.reconnect_attempt += 1
                    await asyncio.sleep(self.reconnect_delay)
                except Exception as e:
                    self.logger.error(f"웹소켓 재연결 시도 실패 ({self.reconnect_attempt}): {str(e)}")
                    self.reconnect_attempt += 1
                    await asyncio.sleep(self.reconnect_delay)

            self.logger.error("최대 재연결 시도 횟수 초과")
            return False

    async def _connect(self) -> Optional[websockets.WebSocketClientProtocol]:
        websocket = None
        try:
            uri = "ws://supervisor/core/api/websocket"
            self.logger.debug(f"웹소켓 연결 시도: {uri}")
            websocket = await websockets.connect(uri, 
                                               max_size=2**24,
                                               max_queue=2**10,
                                               compression=None)
            
            # keepalive 태스크 추적 시작
            if hasattr(websocket, '_keepalive_ping') and websocket._keepalive_ping is not None:
                self._keepalive_tasks.add(websocket._keepalive_ping)
            if hasattr(websocket, '_keepalive_pong') and websocket._keepalive_pong is not None:
                self._keepalive_tasks.add(websocket._keepalive_pong)
            
            auth_required = await websocket.recv()
            auth_required_data = json.loads(auth_required)
            self.logger.debug(f"수신 메시지: {self._truncate_log_message(auth_required)}")
            
            if auth_required_data.get('type') != 'auth_required':
                self.logger.error("예상치 못한 초기 메시지 타입")
                await websocket.close()
                return None
            
            auth_message = {
                "type": "auth",
                "access_token": self.supervisor_token
            }
            auth_message_str = json.dumps(auth_message)
            self.logger.debug(f"송신 메시지: {self._truncate_log_message(auth_message_str)}")
            await websocket.send(auth_message_str)
            
            auth_response = await websocket.recv()
            self.logger.debug(f"수신 메시지: {self._truncate_log_message(auth_response)}")
            auth_response_data = json.loads(auth_response)
            
            if auth_response_data.get('type') == 'auth_ok':
                self.logger.debug("웹소켓 인증 성공")
                return websocket
            else:
                self.logger.error("웹소켓 인증 실패")
                await websocket.close()
                return None
                
        except Exception as e:
            self.logger.error(f"웹소켓 연결 실패: {str(e)}")
            if websocket:
                await websocket.close()
            return None

    async def send_message(self, message_type: str, **kwargs) -> Optional[Any]:
        if not await self.ensure_connected() or not self.websocket:
            self.logger.error(f"웹소켓 연결이 없어 메시지를 보낼 수 없습니다: {message_type}")
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
            
            # 메시지 전송
            send_start_time = time.time()
            await self.websocket.send(message_str)
            send_time = time.time() - send_start_time
            
            self.logger.info(f"메시지 전송 완료 (ID: {message['id']}, 타입: {message_type}, 소요시간: {send_time:.3f}초)")
            
            # 응답 대기 시간 설정 (기본 30초)
            timeout = 30.0
            if message_type == "get_states":
                # get_states는 데이터가 많을 수 있으므로 타임아웃을 더 길게 설정
                timeout = 60.0
                
            start_time = time.time()
            
            # 응답 대기 시작 로깅
            self.logger.info(f"응답 대기 시작 (ID: {message['id']}, 타입: {message_type}, 제한시간: {timeout}초)")
            
            while True:
                # 타임아웃 체크
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    self.logger.error(f"응답 타임아웃 (ID: {message['id']}, 타입: {message_type}, 제한시간: {timeout}초)")
                    
                    # get_states 요청이 타임아웃된 경우 연결 재설정 시도
                    if message_type == "get_states":
                        self.logger.warning(f"get_states 요청 타임아웃으로 연결을 재설정합니다")
                        await self.close()
                        
                    return None
                    
                try:
                    # 응답 대기 (5초 타임아웃으로 여러 번 시도)
                    wait_start_time = time.time()
                    response = await asyncio.wait_for(self.websocket.recv(), 5.0)
                    wait_time = time.time() - wait_start_time
                    
                    self.logger.info(f"메시지 수신 (소요시간: {wait_time:.3f}초): {self._truncate_log_message(response)}")
                    response_data = json.loads(response)
                    
                    # 응답 ID 확인
                    if response_data.get('id') == message['id']:
                        total_time = time.time() - start_time
                        
                        if response_data.get('success'):
                            result = response_data.get('result')
                            result_size = len(result) if isinstance(result, list) else "N/A"
                            
                            self.logger.info(f"요청 성공 (ID: {message['id']}, 타입: {message_type}, 총 소요시간: {total_time:.3f}초, 결과 크기: {result_size})")
                            
                            # get_states 요청인 경우 추가 정보 로깅
                            if message_type == "get_states" and isinstance(result, list):
                                temp_sensors = [s for s in result if s.get('entity_id', '').startswith('sensor.temperature')]
                                self.logger.info(f"get_states 결과: 전체 {len(result)}개 항목, 온도 센서 {len(temp_sensors)}개")
                                
                                # 온도 센서 값 확인
                                zero_temp_count = sum(1 for s in temp_sensors if s.get('state') == '0' or s.get('state') == '0.0')
                                if zero_temp_count > 0:
                                    self.logger.warning(f"주의: {zero_temp_count}개 온도 센서가 0°C를 보고하고 있습니다")
                            
                            return result
                        else:
                            error_msg = response_data.get('error', {}).get('message', '알 수 없는 오류')
                            self.logger.error(f"웹소켓 요청 실패 (ID: {message['id']}, 타입: {message_type}, 총 소요시간: {total_time:.3f}초): {error_msg}")
                            return None
                except asyncio.TimeoutError:
                    # 5초 타임아웃이 발생했지만 전체 타임아웃은 아직 안 됨
                    elapsed_time = time.time() - start_time
                    self.logger.info(f"응답 대기 중... (ID: {message['id']}, 타입: {message_type}, 경과시간: {elapsed_time:.1f}초/{timeout}초)")
                    continue
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"웹소켓 연결이 닫힘: {str(e)}")
            await self.close()
            return None
        except Exception as e:
            import traceback
            self.logger.error(f"웹소켓 통신 중 오류 발생: {str(e)}")
            self.logger.error(traceback.format_exc())
            await self.close()
            return None

class MockWebSocketClient:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.open = True
        self._loop = None
        self._lock = None
        self._mock_data = None
        self.message_id = 1
        self.logger = logging.getLogger("MockWebSocketClient")
        self.logger.info(f"MockWebSocketClient 초기화: message_id={self.message_id}")

    def _truncate_log_message(self, message: str, max_length: int = 100) -> str:
        """로그 메시지를 지정된 길이로 잘라서 반환합니다."""
        if len(message) <= max_length:
            return message
        return message[:max_length] + "..."

    async def _ensure_loop_and_lock(self):
        """현재 이벤트 루프와 락을 확인하고 필요한 경우 초기화합니다."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._loop, self._lock

    async def ensure_connected(self) -> bool:
        """웹소켓 연결 상태를 확인합니다. 모의 클라이언트는 항상 연결된 것으로 간주합니다."""
        self.logger.debug("모의 웹소켓 연결 상태 확인 (항상 True 반환)")
        return True

    def _get_mock_data(self):
        """mock 데이터를 가져오고 필요한 경우 초기화합니다."""
        if self._mock_data is None:
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
                
        return self._mock_data

    async def send_message(self, message_type: str, **kwargs) -> Optional[Any]:
        try:
            loop, lock = await self._ensure_loop_and_lock()
            if not lock:
                self.logger.error(f"락을 획득할 수 없어 메시지를 보낼 수 없습니다: {message_type}")
                return None
            
            async with lock:
                # 메시지 ID 할당 전에 현재 값 로깅
                current_id = self.message_id
                self.logger.info(f"모의 메시지 ID 할당: current_id={current_id}, 타입={message_type}")
                
                message_data = {"id": current_id, "type": message_type, **kwargs}
                message_str = json.dumps(message_data)
                
                # 다음 메시지를 위해 ID 증가
                self.message_id += 1
                self.logger.info(f"모의 메시지 ID 증가: 새 message_id={self.message_id}")
                
                self.logger.info(f"모의 송신 메시지 (ID: {current_id}, 타입: {message_type}): {self._truncate_log_message(message_str)}")
                
                # 특별히 get_states 요청인 경우 더 자세한 로깅
                if message_type == "get_states":
                    self.logger.info(f"===== 모의 get_states 요청 처리 시작 =====")
                
                # 의도적으로 약간의 지연 추가 (실제 네트워크 통신 시뮬레이션)
                start_time = time.time()
                await asyncio.sleep(0.1)
                
                mock_data = self._get_mock_data()
                
                if message_type == 'auth':
                    response = {"type": "auth_ok"}
                    self.logger.info(f"모의 수신 응답 (타입: {message_type}): {self._truncate_log_message(json.dumps(response))}")
                    return response
                elif message_type == 'get_states':
                    result = mock_data.get('temperature_sensors', [])
                    elapsed_time = time.time() - start_time
                    
                    # 온도 센서 값 확인
                    zero_temp_count = sum(1 for s in result if s.get('state') == '0' or s.get('state') == '0.0')
                    
                    self.logger.info(f"모의 상태 조회 결과 (타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 센서 데이터")
                    
                    if zero_temp_count > 0:
                        self.logger.warning(f"주의: 모의 데이터에 {zero_temp_count}개 온도 센서가 0°C를 보고하고 있습니다")
                    
                    return result
                elif message_type == 'config/entity_registry/list':
                    result = mock_data.get('entity_registry', [])
                    elapsed_time = time.time() - start_time
                    self.logger.info(f"모의 엔티티 레지스트리 조회 결과 (타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 항목")
                    return result
                elif message_type == 'config/label_registry/list':
                    result = mock_data.get('label_registry', [])
                    elapsed_time = time.time() - start_time
                    self.logger.info(f"모의 레이블 레지스트리 조회 결과 (타입: {message_type}, 소요시간: {elapsed_time:.3f}초): {len(result)}개 항목")
                    return result
                    
                self.logger.info(f"모의 응답 없음 (타입: {message_type})")
                return None
        except Exception as e:
            import traceback
            self.logger.error(f"모의 웹소켓 통신 중 오류 발생 (타입: {message_type}): {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    async def close(self):
        self.logger.debug("모의 웹소켓 연결 종료")
        self.open = False
        if self._lock:
            try:
                async with self._lock:
                    self._loop = None
                    self._lock = None
            except Exception as e:
                self.logger.error(f"모의 웹소켓 연결 종료 중 오류 발생: {str(e)}")
                pass 