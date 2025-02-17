import requests
import websockets # type: ignore
import json
from typing import Optional, Dict, Any, List

class SensorManager:
    """센서 상태 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, config_manager, logger, supervisor_token):
        self.is_local = is_local
        self.config_manager = config_manager
        self.logger = logger
        self.supervisor_token = supervisor_token
        self.message_id = 1

    async def websocket_connect(self):
        """WebSocket 연결 설정"""
        if self.is_local:
            return None
            
        websocket = None
        try:
            uri = "ws://supervisor/core/api/websocket"
            websocket = await websockets.connect(uri)
            
            # 인증 단계
            auth_required = await websocket.recv()
            auth_required_data = json.loads(auth_required)
            if auth_required_data.get('type') != 'auth_required':
                self.logger.error("예상치 못한 초기 메시지 타입")
                await websocket.close()
                return None
            
            self.logger.debug(f"Auth required message: {auth_required}")
            
            auth_message = {
                "type": "auth",
                "access_token": self.supervisor_token
            }
            await websocket.send(json.dumps(auth_message))
            
            auth_response = await websocket.recv()
            auth_response_data = json.loads(auth_response)
            self.logger.debug(f"Auth response: {auth_response}")
            
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

    async def get_entity_registry(self) -> List[Dict]:
        """Entity Registry 조회"""
        if self.is_local:
            return []
            
        try:
            websocket = await self.websocket_connect()
            if not websocket:
                return []
                
            message = {
                "id": self.message_id,
                "type": "config/entity_registry/list"
            }
            self.message_id += 1
            
            await websocket.send(json.dumps(message))
            
            # 응답 대기 및 처리
            while True:
                response = await websocket.recv()
                response_data = json.loads(response)
                
                # 응답의 id가 요청한 id와 일치하는지 확인
                if response_data.get('id') == message['id']:
                    await websocket.close()
                    if response_data.get('success'):
                        return response_data.get('result', [])
                    else:
                        self.logger.error(f"Entity Registry 조회 실패: {response_data}")
                        return []
                        
        except Exception as e:
            self.logger.error(f"Entity Registry 조회 중 오류 발생: {str(e)}")
            if websocket is not None:
                await websocket.close()
            return []

    def get_ha_api(self) -> Optional[Dict[str, Any]]:
        """Home Assistant API 설정"""
        if self.is_local:
            return {
                'base_url': 'mock_url',
                'headers': {'Content-Type': 'application/json'}
            }
        if not self.supervisor_token:
            self.logger.error("Supervisor Token is not configured")
            return None
        return {
            'base_url': 'http://supervisor/core/api',
            'headers': {
                'Authorization': f'Bearer {self.supervisor_token}',
                'Content-Type': 'application/json'
            }
        }
    
    def get_sensor_state(self, entity_id: str) -> Dict[str, Any]:
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
            
            api = self.get_ha_api()
            if not api:
                self.logger.error("Home Assistant API 설정을 가져올 수 없습니다")
                return {'state': '0', 'entity_id': entity_id}
            
            response = requests.get(
                f"{api['base_url']}/states/{entity_id}",
                headers=api['headers']
            )
            return response.json()
        except Exception as e:
            self.logger.error(f"센서 상태 조회 실패: {str(e)}")
            return {'state': '0', 'entity_id': entity_id}
    
    async def get_all_states(self) -> List[Dict]:
        """모든 센서 상태 조회"""
        if self.is_local:
            mock_data = self.config_manager.get_mock_data()
            self.logger.debug(f"가상 센서 상태 조회: {mock_data}")
            return mock_data.get('temperature_sensors', [])
        
        api = self.get_ha_api()
        if not api:
            self.logger.error("Home Assistant API 설정을 가져올 수 없습니다")
            return []

        try:
            # Entity Registry 정보 가져오기
            entity_registry = await self.get_entity_registry()
            entity_registry_dict = {
                entry['entity_id']: entry 
                for entry in entity_registry
            }
            
            # 상태 정보 가져오기
            response = requests.get(f"{api['base_url']}/states", headers=api['headers'])
            response.raise_for_status()
            states = response.json()
            
            # 온도 센서 필터링 및 레이블 정보 추가
            filtered_states = []
            for state in states:
                if (state.get('attributes', {}).get('device_class') == 'temperature' and
                    state.get('attributes', {}).get('state_class') == 'measurement'):
                    
                    # Entity Registry 정보 추가
                    entity_id = state['entity_id']
                    if entity_id in entity_registry_dict:
                        registry_info = entity_registry_dict[entity_id]
                        state['labels'] = registry_info.get('labels', [])
                        state['area_id'] = registry_info.get('area_id')
                    
                    filtered_states.append(state)
            
            return filtered_states
            
        except Exception as e:
            self.logger.error(f"센서 상태 조회 실패: {str(e)}")
            if 'response' in locals():
                self.logger.error(f"응답 내용: {response.text}")
            return []


