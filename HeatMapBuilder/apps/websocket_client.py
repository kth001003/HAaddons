import websockets # type: ignore
import json
from typing import Optional, Dict, Any, List
import asyncio
import logging

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
            if auth_required_data.get('type') != 'auth_required':
                self.logger.error("예상치 못한 초기 메시지 타입")
                await websocket.close()
                return None
            
            auth_message = {
                "type": "auth",
                "access_token": self.supervisor_token
            }
            await websocket.send(json.dumps(auth_message))
            
            auth_response = await websocket.recv()
            auth_response_data = json.loads(auth_response)
            
            if auth_response_data.get('type') == 'auth_ok':
                return websocket
            else:
                self.logger.error("WebSocket 인증 실패")
                await websocket.close()
                return None
                
        except Exception as e:
            self.logger.error(f"WebSocket 연결 실패: {str(e)}")
            if websocket:
                await websocket.close()
            return None

    async def send_message(self, message_type: str, **kwargs) -> Optional[Any]:
        if not await self.ensure_connected() or not self.websocket:
            return None
            
        message = {
            "id": self.message_id,
            "type": message_type,
            **kwargs
        }
        self.message_id += 1
        
        try:
            await self.websocket.send(json.dumps(message))
            
            while True:
                response = await self.websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get('id') == message['id']:
                    if response_data.get('success'):
                        return response_data.get('result')
                    else:
                        self.logger.error(f"WebSocket 요청 실패: {response_data}")
                        return None
                        
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"WebSocket 연결이 닫힘: {str(e)}")
            await self.close()
            return None
        except Exception as e:
            self.logger.error(f"WebSocket 통신 중 오류 발생: {str(e)}")
            await self.close()
            return None

class MockWebSocketClient:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.open = True
        self._loop = None
        self._lock = None
        self._mock_data = None

    async def _ensure_loop_and_lock(self):
        """현재 이벤트 루프와 락을 확인하고 필요한 경우 초기화합니다."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._loop, self._lock

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
                return None
                
            async with lock:
                message_data = {"type": message_type, **kwargs}
                mock_data = self._get_mock_data()
                
                if message_type == 'auth':
                    return {"type": "auth_ok"}
                elif message_type == 'get_states':
                    return mock_data.get('temperature_sensors', [])
                elif message_type == 'config/entity_registry/list':
                    return mock_data.get('entity_registry', [])
                elif message_type == 'config/label_registry/list':
                    return mock_data.get('label_registry', [])
                    
                return None
        except Exception as e:
            print(f"Error in send_message: {str(e)}")
            return None

    async def close(self):
        self.open = False
        if self._lock:
            try:
                async with self._lock:
                    self._loop = None
                    self._lock = None
            except Exception:
                pass 