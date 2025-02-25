import json
from typing import Optional, Dict, Any, List, Union
from websocket_client import WebSocketClient, MockWebSocketClient
import time

class SensorManager:
    """센서 상태 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, config_manager, logger, supervisor_token):
        self.is_local = is_local
        self.config_manager = config_manager
        self.logger = logger
        
        # 웹소켓 클라이언트 초기화 로깅
        self.logger.debug("SensorManager: 웹소켓 클라이언트 초기화 시작")
        
        self.websocket_client = (
            MockWebSocketClient(config_manager) if is_local 
            else WebSocketClient(supervisor_token, logger)
        )
        
        self.logger.debug(f"SensorManager: 웹소켓 클라이언트 초기화 완료 (타입: {'모의' if is_local else '실제'})")

    async def initialize_connection(self) -> bool:
        """웹소켓 연결을 초기화합니다."""
        self.logger.info("SensorManager: 웹소켓 연결 초기화 시작")
        start_time = time.time()
        
        try:
            # 실제 WebSocketClient인 경우에만 _connect 메서드 직접 호출
            if not self.is_local:
                self.logger.info("SensorManager: 실제 웹소켓 클라이언트 - _connect 메서드 호출")
                self.websocket_client.websocket = await self.websocket_client._connect()
                
                if self.websocket_client.websocket:
                    self.logger.info("SensorManager: _connect 메서드 호출 성공, 웹소켓 연결됨")
                else:
                    self.logger.error("SensorManager: _connect 메서드 호출 실패")
            else:
                self.logger.info("SensorManager: 모의 웹소켓 클라이언트 - _connect 메서드 호출 생략")
            
            # 공통 코드: 모든 클라이언트 타입에 적용
            connection_success = await self.websocket_client.ensure_connected()
            elapsed_time = time.time() - start_time
            
            if connection_success:
                self.logger.info(f"SensorManager: 웹소켓 연결 성공 (소요시간: {elapsed_time:.3f}초)")
                
                # 연결 성공 후 현재 message_id 로깅
                if hasattr(self.websocket_client, 'message_id'):
                    self.logger.info(f"SensorManager: 현재 message_id: {self.websocket_client.message_id}")
                
                # 웹소켓 상태 추가 확인
                if hasattr(self.websocket_client, 'websocket') and self.websocket_client.websocket:
                    is_open = getattr(self.websocket_client.websocket, 'open', None)
                    self.logger.info(f"SensorManager: 연결 성공 후 웹소켓 open 상태: {is_open}")
                
                return True
            else:
                self.logger.error(f"SensorManager: 웹소켓 연결 실패 (소요시간: {elapsed_time:.3f}초)")
                return False
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.logger.error(f"SensorManager: 웹소켓 연결 초기화 중 오류 발생: {str(e)} (소요시간: {elapsed_time:.3f}초)")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    async def check_connection(self) -> bool:
        """
        현재 웹소켓 연결 상태를 확인합니다.
        """
        self.logger.info("SensorManager: 웹소켓 연결 상태 확인 중")
        
        try:
            # 웹소켓 객체 존재 확인
            if not hasattr(self.websocket_client, 'websocket') or not self.websocket_client.websocket:
                self.logger.info("SensorManager: 웹소켓 연결 없음")
                return False
            
            # message_id 확인
            if hasattr(self.websocket_client, 'message_id'):
                self.logger.info(f"SensorManager: 현재 message_id: {self.websocket_client.message_id}")
            
            # 웹소켓 상태 직접 확인
            is_open = getattr(self.websocket_client.websocket, 'open', None)
            if is_open is not None:
                self.logger.info(f"SensorManager: 웹소켓 open 상태: {is_open}")
                if is_open:
                    self.logger.info("SensorManager: 웹소켓이 open 속성으로 연결됨")
                    return True
            else:
                self.logger.info("SensorManager: 웹소켓에 open 속성 없음, ping 확인 필요")
            
            # ensure_connected 호출로 상태 확인
            self.logger.info("SensorManager: ensure_connected 호출하여 상태 확인")
            is_connected = await self.websocket_client.ensure_connected()
            
            if is_connected:
                self.logger.info("SensorManager: 웹소켓 연결 활성화 상태")
                return True
            else:
                self.logger.warning("SensorManager: 웹소켓 연결 비활성화 상태")
                return False
        except Exception as e:
            self.logger.error(f"SensorManager: 웹소켓 연결 상태 확인 중 오류: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    async def close(self):
        """웹소켓 연결을 종료합니다."""
        self.logger.info("SensorManager: 웹소켓 연결 종료 시작")
        if hasattr(self.websocket_client, 'close'):
            await self.websocket_client.close()
        self.logger.info("SensorManager: 웹소켓 연결 종료 완료")

    async def debug_websocket(self, message_type: str, **kwargs) -> Optional[Any]:
        """WebSocket 디버깅 메시지 전송"""
        self.logger.info(f"SensorManager: 디버깅 메시지 전송 - {message_type}")
        return await self.websocket_client.send_message(message_type, **kwargs)

    async def get_entity_registry(self) -> List[Dict]:
        """Entity Registry 조회"""
        # 요청 전 message_id 확인
        if hasattr(self.websocket_client, 'message_id'):
            self.logger.info(f"Entity Registry 요청 전 message_id: {self.websocket_client.message_id}")
            
        self.logger.debug("Entity Registry 조회 요청 시작")
        start_time = time.time()
        result = await self.websocket_client.send_message("config/entity_registry/list")
        elapsed_time = time.time() - start_time
        
        # 요청 후 message_id 확인
        if hasattr(self.websocket_client, 'message_id'):
            self.logger.info(f"Entity Registry 요청 후 message_id: {self.websocket_client.message_id}")
        
        if result is not None:
            self.logger.debug(f"Entity Registry 조회 성공: {len(result)}개 항목 (소요시간: {elapsed_time:.3f}초)")
        else:
            self.logger.error(f"Entity Registry 조회 실패 (소요시간: {elapsed_time:.3f}초)")
            
        return result if result is not None else []

    async def get_label_registry(self) -> List[Dict]:
        """Label Registry 조회"""
        # 요청 전 message_id 확인
        if hasattr(self.websocket_client, 'message_id'):
            self.logger.info(f"Label Registry 요청 전 message_id: {self.websocket_client.message_id}")
            
        self.logger.debug("Label Registry 조회 요청 시작")
        start_time = time.time()
        result = await self.websocket_client.send_message("config/label_registry/list")
        elapsed_time = time.time() - start_time
        
        # 요청 후 message_id 확인
        if hasattr(self.websocket_client, 'message_id'):
            self.logger.info(f"Label Registry 요청 후 message_id: {self.websocket_client.message_id}")
        
        if result is not None:
            self.logger.debug(f"Label Registry 조회 성공: {len(result)}개 항목 (소요시간: {elapsed_time:.3f}초)")
        else:
            self.logger.error(f"Label Registry 조회 실패 (소요시간: {elapsed_time:.3f}초)")
            
        return result if result is not None else []

    async def get_all_states(self) -> List[Dict]:
        """모든 센서 상태 조회"""
        try:
            self.logger.info("===== 센서 상태 조회 시작 =====")
            overall_start_time = time.time()
            
            # Entity Registry 정보 가져오기
            self.logger.info("Entity Registry 정보 요청 중...")
            entity_registry_start = time.time()
            entity_registry = await self.get_entity_registry()
            entity_registry_time = time.time() - entity_registry_start
            
            if not entity_registry:
                self.logger.error(f"Entity Registry 정보 수신 실패 (소요시간: {entity_registry_time:.3f}초)")
            else:
                self.logger.info(f"Entity Registry 정보 수신 완료: {len(entity_registry)}개 항목 (소요시간: {entity_registry_time:.3f}초)")
            
            entity_registry_dict = {
                entry['entity_id']: entry 
                for entry in entity_registry
            }
            
            # 상태 정보 가져오기
            self.logger.info("===== get_states 요청 시작 =====")
            states_start = time.time()
            
            # 웹소켓 연결 상태 확인
            connection_check_start = time.time()
            is_connected = await self.websocket_client.ensure_connected()
            connection_check_time = time.time() - connection_check_start
            
            if not is_connected:
                self.logger.error(f"웹소켓 연결 실패 (소요시간: {connection_check_time:.3f}초)")
                return []
            else:
                self.logger.info(f"웹소켓 연결 확인 완료 (소요시간: {connection_check_time:.3f}초)")
            
            # get_states 요청 전 message_id 확인
            if hasattr(self.websocket_client, 'message_id'):
                self.logger.info(f"get_states 요청 전 message_id: {self.websocket_client.message_id}")
            
            # get_states 요청 전송
            self.logger.info("get_states 요청 전송 중...")
            states = await self.websocket_client.send_message("get_states")
            states_time = time.time() - states_start
            
            # get_states 요청 후 message_id 확인
            if hasattr(self.websocket_client, 'message_id'):
                self.logger.info(f"get_states 요청 후 message_id: {self.websocket_client.message_id}")
            
            if states is None:
                self.logger.error(f"get_states 요청 실패: 응답이 None입니다 (소요시간: {states_time:.3f}초)")
                return []
                
            self.logger.info(f"get_states 응답 수신 완료: {len(states)}개 항목 (소요시간: {states_time:.3f}초)")

            # 센서 필터링 및 처리
            self.logger.info("센서 데이터 필터링 시작...")
            filtering_start = time.time()
            
            filtered_states = []
            sensor_count = 0
            valid_sensor_count = 0
            zero_temp_count = 0
            
            for state in states:
                entity_id = state['entity_id']
                if not entity_id.startswith('sensor.'):
                    continue
                    
                sensor_count += 1
                
                try:
                    # 숫자 값인지 확인
                    temp_value = float(state['state'])
                    valid_sensor_count += 1
                    
                    # 0도 센서 카운트
                    if temp_value == 0:
                        zero_temp_count += 1
                    
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
            
            filtering_time = time.time() - filtering_start
            overall_time = time.time() - overall_start_time
            
            self.logger.info(f"센서 필터링 완료 (소요시간: {filtering_time:.3f}초)")
            self.logger.info(f"센서 상태 조회 결과: 전체 {sensor_count}개 중 {valid_sensor_count}개 유효, {len(filtered_states)}개 필터링됨")
            
            if zero_temp_count > 0:
                self.logger.warning(f"주의: {zero_temp_count}개 센서가 0°C 온도를 보고하고 있습니다")
            
            self.logger.info(f"===== 센서 상태 조회 완료 (총 소요시간: {overall_time:.3f}초) =====")
            
            return filtered_states
            
        except Exception as e:
            import traceback
            self.logger.error(f"센서 상태 조회 중 오류 발생: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []