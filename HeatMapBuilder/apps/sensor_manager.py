import json
from typing import Optional, Dict, Any, List, Union
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

    async def get_all_states(self) -> List[Dict]:
        """모든 센서 상태 조회"""
        try:
            self.logger.debug("센서 상태 조회 시작")
            
            # Entity Registry 정보 가져오기
            self.logger.debug("Entity Registry 정보 요청 중...")
            entity_registry = await self.get_entity_registry()
            self.logger.debug(f"Entity Registry 정보 수신 완료: {len(entity_registry)}개 항목")
            
            entity_registry_dict = {
                entry['entity_id']: entry 
                for entry in entity_registry
            }
            
            # 상태 정보 가져오기
            self.logger.debug("get_states 요청 시작")
            states = await self.websocket_client.send_message("get_states")
            
            if states is None:
                self.logger.error("get_states 요청 실패: 응답이 None입니다")
                return []
                
            self.logger.debug(f"get_states 응답 수신 완료: {len(states)}개 항목")

            # 센서 필터링 및 처리
            filtered_states = []
            sensor_count = 0
            valid_sensor_count = 0
            
            for state in states:
                entity_id = state['entity_id']
                if not entity_id.startswith('sensor.'):
                    continue
                    
                sensor_count += 1
                
                try:
                    # 숫자 값인지 확인
                    float(state['state'])
                    valid_sensor_count += 1
                    
                    # Entity Registry 정보 추가
                    if entity_id in entity_registry_dict:
                        state.update({
                            'labels': entity_registry_dict[entity_id].get('labels', []),
                            'area_id': entity_registry_dict[entity_id].get('area_id')
                        })
                        filtered_states.append(state)
                except (ValueError, TypeError):
                    # 숫자가 아닌 상태값은 무시
                    continue
                    
            self.logger.debug(f"센서 상태 조회 완료: 전체 {sensor_count}개 중 {valid_sensor_count}개 유효, {len(filtered_states)}개 필터링됨")
            return filtered_states
            
        except Exception as e:
            import traceback
            self.logger.error(f"센서 상태 조회 중 오류 발생: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []