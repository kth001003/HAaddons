import websockets # type: ignore
import json
from typing import Optional, Dict, Any, List
import asyncio  # type: ignore

class SensorManager:
    """센서 상태 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, config_manager, logger, supervisor_token):
        self.is_local = is_local
        self.config_manager = config_manager
        self.logger = logger
        self.supervisor_token = supervisor_token
        self.message_id = 1
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.reconnect_attempt = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # 초단위

    async def ensure_websocket_connected(self):
        """웹소켓 연결이 활성 상태인지 확인하고, 필요시 재연결"""
        if self.is_local:
            return True

        try:
            if self.websocket and self.websocket.open:
                return True
        except Exception:
            self.websocket = None

        while self.reconnect_attempt < self.max_reconnect_attempts:
            try:
                self.websocket = await self.websocket_connect()
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

    async def websocket_connect(self):
        """WebSocket 연결 설정"""
        if self.is_local:
            return None
            
        websocket = None
        try:
            uri = "ws://supervisor/core/api/websocket"
            websocket = await websockets.connect(uri, 
                                               max_size=2**24,  # 16MB
                                               max_queue=2**10,  # 1024 messages
                                               compression=None
                                               )
            
            # 인증 단계
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

    async def _send_websocket_message(self, message_type: str, **kwargs) -> Optional[Any]:
        """WebSocket 메시지 전송 및 응답 처리를 위한 공통 메서드"""
        if not await self.ensure_websocket_connected() or not self.websocket:
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
            self.websocket = None
            return None
        except Exception as e:
            self.logger.error(f"WebSocket 통신 중 오류 발생: {str(e)}")
            self.websocket = None
            return None

    async def get_entity_registry(self) -> List[Dict]:
        """Entity Registry 조회"""
        if self.is_local:
            return []
            
        result = await self._send_websocket_message("config/entity_registry/list")
        return result if result is not None else []

    async def get_label_registry(self) -> List[Dict]:
        """Label Registry 조회"""
        if self.is_local:
            return []
            
        result = await self._send_websocket_message("config/label_registry/list")
        return result if result is not None else []

    async def get_sensor_state(self, entity_id: str) -> Dict[str, Any]:
        """센서 상태 조회"""
        try:
            if self.is_local:
                mock_data = self.config_manager.get_mock_data()
                for sensor in mock_data.get('temperature_sensors', []):
                    if sensor['entity_id'] == entity_id:
                        return {
                            'entity_id': entity_id,
                            'state': sensor.get('state', '0'),
                            'attributes': sensor.get('attributes', {})
                        }
                self.logger.warning(f"Mock 센서 데이터를 찾을 수 없음: {entity_id}")
                return {'state': '20', 'entity_id': entity_id}
            
            states = await self._send_websocket_message("get_states")
            if states is None:
                return {'state': '0', 'entity_id': entity_id}
                
            for state in states:
                if state.get('entity_id') == entity_id:
                    return state
            
            self.logger.warning(f"센서 상태를 찾을 수 없음: {entity_id}")
            return {'state': '0', 'entity_id': entity_id}
                
        except Exception as e:
            self.logger.error(f"센서 상태 조회 중 오류 발생: {str(e)}")
            return {'state': '0', 'entity_id': entity_id}
    
    async def get_all_states(self) -> List[Dict]:
        """모든 센서 상태 조회"""
        if self.is_local:
            mock_data = self.config_manager.get_mock_data()
            self.logger.debug(f"가상 센서 상태 조회: {mock_data}")
            return mock_data.get('temperature_sensors', [])

        try:
            # Entity Registry 정보 가져오기
            entity_registry = await self.get_entity_registry()
            entity_registry_dict = {
                entry['entity_id']: entry 
                for entry in entity_registry
            }
            
            # 상태 정보 가져오기
            states = await self._send_websocket_message("get_states")
            if states is None:
                return []

            filtered_states = []
            for state in states:
                entity_id = state['entity_id']
                if not entity_id.startswith('sensor.'):
                    continue
                if entity_id in entity_registry_dict:
                    state.update({
                        'labels': entity_registry_dict[entity_id].get('labels', []),
                        'area_id': entity_registry_dict[entity_id].get('area_id')
                    })
                    filtered_states.append(state)
            return filtered_states
            
        except Exception as e:
            self.logger.error(f"센서 상태 조회 중 오류 발생: {str(e)}")
            return []