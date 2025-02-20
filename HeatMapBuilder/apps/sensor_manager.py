import json
from typing import Optional, Dict, Any, List
from websocket_client import WebSocketClient, MockWebSocketClient

class SensorManager:
    """센서 상태 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, config_manager, logger, supervisor_token):
        self.is_local = is_local
        self.config_manager = config_manager
        self.logger = logger
        self.websocket_client = (
            MockWebSocketClient(config_manager) if is_local 
            else WebSocketClient(supervisor_token, logger)
        )

    async def close(self):
        """웹소켓 연결을 종료합니다."""
        if hasattr(self.websocket_client, 'close'):
            await self.websocket_client.close()

    async def debug_websocket(self, message_type: str, **kwargs) -> Optional[Any]:
        """WebSocket 디버깅 메시지 전송"""
        return await self.websocket_client.send_message(message_type, **kwargs)

    async def get_entity_registry(self) -> List[Dict]:
        """Entity Registry 조회"""
        result = await self.websocket_client.send_message("config/entity_registry/list")
        return result if result is not None else []

    async def get_label_registry(self) -> List[Dict]:
        """Label Registry 조회"""
        result = await self.websocket_client.send_message("config/label_registry/list")
        return result if result is not None else []

    async def get_sensor_state(self, entity_id: str) -> Dict[str, Any]:
        """센서 상태 조회"""
        try:
            states = await self.websocket_client.send_message("get_states")
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
        try:
            # Entity Registry 정보 가져오기
            entity_registry = await self.get_entity_registry()
            entity_registry_dict = {
                entry['entity_id']: entry 
                for entry in entity_registry
            }
            
            # 상태 정보 가져오기
            states = await self.websocket_client.send_message("get_states")
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