from typing import Any, Dict, List, Optional, TypedDict
import re
from .utils import byte_to_hex_str, checksum

class ExpectedStatePacket(TypedDict):
    required_bytes: List[int]
    possible_values: List[List[str]]

class MessageProcessor:
    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.logger = controller.logger
        self.DEVICE_STRUCTURE = controller.DEVICE_STRUCTURE
        self.COLLECTDATA = controller.COLLECTDATA
        self.QUEUE = controller.QUEUE
        self.HA_TOPIC = controller.HA_TOPIC
        self.ELFIN_TOPIC = controller.ELFIN_TOPIC
        self.config = controller.config

    async def process_elfin_data(self, raw_data: str) -> None:
        """Elfin 장치에서 전송된 raw_data를 분석합니다."""
        try:
            assert isinstance(self.DEVICE_STRUCTURE, dict), "DEVICE_STRUCTURE must be a dictionary"
            
            for k in range(0, len(raw_data), 16):
                data = raw_data[k:k + 16]
                if data == checksum(data):
                    self.COLLECTDATA['recv_data'].append(data)
                    if len(self.COLLECTDATA['recv_data']) > 300:
                        self.COLLECTDATA['recv_data'] = self.COLLECTDATA['recv_data'][-300:]
                    
                    byte_data = bytearray.fromhex(data)
                    
                    for device_name, structure in self.DEVICE_STRUCTURE.items():
                        state_structure = structure['state']
                        field_positions = state_structure['fieldPositions']
                        if byte_data[0] == int(state_structure['header'], 16):
                            try:
                                device_id_pos = field_positions['deviceId']
                                device_id = byte_data[int(device_id_pos)]
                            except KeyError:
                                # Gas같은 deviceId가 없는 기기 처리 여기에..
                                if device_name == 'Gas':
                                    power_pos = field_positions.get('power', 1)
                                    power = byte_data[int(power_pos)]
                                    power_hex = byte_to_hex_str(power)
                                    power_values = state_structure['structure'][power_pos]['values']
                                    power_text = "ON" if power_hex == power_values.get('on', '').upper() else "OFF"
                                    self.logger.signal(f'{byte_data.hex()}: 가스차단기 ### 상태: {power_text}')
                                    # TODO: 가스차단기 상태 업데이트 추가
                                    # await self.update_gas(power_text)
                                break
                            except IndexError:
                                self.logger.error(f"{device_name}의 deviceId 위치({device_id_pos})가 패킷 범위를 벗어났습니다.")
                                break
                            if device_name == 'Thermo':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                # 온도값을 10진수로 직접 해석
                                current_temp = int(format(byte_data[int(field_positions.get('currentTemp', 3))], '02x'))
                                target_temp = int(format(byte_data[int(field_positions.get('targetTemp', 4))], '02x'))
                                power_hex = byte_to_hex_str(power)
                                power_values = state_structure['structure'][power_pos]['values']
                                power_off_hex = power_values.get('off', '').upper()
                                power_heating_hex = power_values.get('heating', '').upper()
                                mode_text = 'off' if power_hex == power_off_hex else 'heat'
                                action_text = 'heating' if power_hex == power_heating_hex else 'idle'
                                self.logger.signal(f'{byte_data.hex()}: 온도조절기 ### {device_id}번, 모드: {mode_text}, 현재 온도: {current_temp}°C, 설정 온도: {target_temp}°C')
                                await self.controller.state_updater.update_temperature(device_id, mode_text, action_text, current_temp, target_temp)
                            
                            elif device_name == 'Light':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                power_values = state_structure['structure'][power_pos]['values']
                                power_hex = byte_to_hex_str(power)
                                state = "ON" if power_hex == power_values.get('on', '').upper() else "OFF"
                                
                                self.logger.signal(f'{byte_data.hex()}: 조명 ### {device_id}번, 상태: {state}')
                                await self.controller.state_updater.update_light(device_id, state)

                            elif device_name == 'LightBreaker':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                power_values = state_structure['structure'][power_pos]['values']
                                power_hex = byte_to_hex_str(power)
                                state = "ON" if power_hex == power_values.get('on', '').upper() else "OFF"
                                
                                self.logger.signal(f'{byte_data.hex()}: 조명차단기 ### {device_id}번, 상태: {state}')
                                await self.controller.state_updater.update_light_breaker(device_id, state)
                                
                            elif device_name == 'Outlet':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                power_values = state_structure['structure'][power_pos]['values']
                                power_hex = byte_to_hex_str(power)
                                power_text = "ON" if power_hex == power_values.get('on', '').upper() else "OFF"
                                
                                state_type_pos = field_positions.get('stateType', 3)
                                state_type = byte_data[int(state_type_pos)]
                                state_type_values = state_structure['structure'][state_type_pos]['values']
                                state_type_hex = byte_to_hex_str(state_type)
                                state_type_text = state_type_values.get(state_type_hex, 'wattage')
                                if state_type_text == 'wattage':
                                    consecutive_bytes = byte_data[4:7]
                                    try:
                                        watt = int(consecutive_bytes.hex())
                                    except ValueError:
                                        self.logger.error(f"콘센트 {device_id} 전력값 변환 중 오류 발생: {consecutive_bytes.hex()}")
                                        watt = 0
                                    self.logger.signal(f'{byte_data.hex()}: 콘센트 ### {device_id}번, 상태: {power_text}, 전력: {watt * 0.1}W')
                                    await self.controller.state_updater.update_outlet(device_id, power_text, watt, None)
                                #TODO: 절전모드 (대기전력차단모드) 로직을 알 수 없음..
                                # elif state_type_text == 'ecomode':
                                #     consecutive_bytes = byte_data[4:7]
                                #     ecomode = consecutive_bytes.hex()
                                #     self.logger.signal(f'{byte_data.hex()}: 콘센트 ### {device_id}번, 상태: {power_text}, 절전모드: {ecomode}')
                                #     await self.controller.update_outlet(device_id, power_text, None, ecomode)

                            elif device_name == 'Fan':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                power_values = state_structure['structure'][power_pos]['values']
                                power_hex = byte_to_hex_str(power)
                                power_text = "OFF" if power_hex == power_values.get('off', '').upper() else "ON"
                                speed_pos = field_positions.get('speed', 3)  
                                speed = byte_data[int(speed_pos)]
                                speed_values = state_structure['structure'][speed_pos]['values']
                                speed_hex = byte_to_hex_str(speed)
                                speed_text = speed_values.get(speed_hex, 'low')
                                
                                self.logger.signal(f'{byte_data.hex()}: 환기장치 ### {device_id}번, 상태: {power_text}, 속도: {speed_text}')
                                await self.controller.state_updater.update_fan(device_id, power_text, speed_text)
                            
                            elif device_name == 'EV':
                                power_pos = field_positions.get('power', 1)
                                power = byte_data[int(power_pos)]
                                power_values = state_structure['structure'][power_pos]['values']
                                power_hex = byte_to_hex_str(power)
                                power_text = "ON" if power_hex == power_values.get('on', '').upper() else "OFF"
                                floor_pos = field_positions.get('floor', 3)
                                floor = byte_data[int(floor_pos)]
                                floor_values = state_structure['structure'][floor_pos]['values']
                                floor_hex = byte_to_hex_str(floor)
                                floor_text = floor_values.get(floor_hex, 'B')
                                self.logger.signal(f'{byte_data.hex()}: 엘리베이터 ### {device_id}번, 상태: {power_text}, 층: {floor_text}')
                                await self.controller.state_updater.update_ev(device_id, power_text, floor_text)

                            break
                else:
                    self.logger.signal(f'체크섬 불일치: {data}')
        
        except Exception as e:
            self.logger.error(f"Elfin 데이터 처리 중 오류 발생: {str(e)}")
            self.logger.debug(f"오류 상세 - raw_data: {raw_data}, device_name: {device_name if 'device_name' in locals() else 'N/A'}")

    async def process_ha_command(self, topics: List[str], value: str) -> None:
        try:
            device = ''.join(re.findall('[a-zA-Z]', topics[1]))
            device_id = int(''.join(re.findall('[0-9]', topics[1])))
            action = topics[2]

            assert isinstance(self.DEVICE_STRUCTURE, dict), "DEVICE_STRUCTURE must be a dictionary"

            if device not in self.DEVICE_STRUCTURE:
                self.logger.error(f'장치 {device}가 DEVICE_STRUCTURE에 존재하지 않습니다.')
                return

            packet_hex = None
            packet = bytearray(7)
            device_structure = self.DEVICE_STRUCTURE[device]
            command = device_structure["command"]
            field_positions = command["fieldPositions"]
            
            packet[0] = int(device_structure["command"]["header"], 16)
            packet[int(field_positions["deviceId"])] = device_id

            if device == 'Light':
                if action == 'power':
                    power_value = command["structure"][str(field_positions["power"])]["values"]["on" if value == "ON" else "off"]
                    packet[int(field_positions["power"])] = int(power_value, 16)
                    self.logger.debug(f'조명 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')
                #TODO: dimmer 추가
            elif device == 'LightBreaker':
                command_type_value = command["structure"][str(field_positions["commandType"])]["values"]["power"]
                packet[int(field_positions["commandType"])] = int(command_type_value, 16)
                power_value = command["structure"][str(field_positions["power"])]["values"]["on" if value == "ON" else "off"]
                packet[int(field_positions["power"])] = int(power_value, 16)
                self.logger.debug(f'조명차단기 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')
            elif device == 'Outlet':
                if action == 'power':
                    command_type_value = command["structure"][str(field_positions["commandType"])]["values"]["power"]
                    packet[int(field_positions["commandType"])] = int(command_type_value, 16)
                    power_value = command["structure"][str(field_positions["power"])]["values"]["on" if value == "ON" else "off"]
                    packet[int(field_positions["power"])] = int(power_value, 16)
                    self.logger.debug(f'콘센트 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')
                #TODO: 절전모드 (대기전력차단모드) 추가
            elif device == 'Gas':
                # off만 가능함.
                power_value = command["structure"][str(field_positions["power"])]["values"]["off"]
                packet[int(field_positions["power"])] = int(power_value, 16)
                self.logger.debug(f'가스차단기 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')
            elif device == 'Thermo':                
                if action == 'power':
                    if value == 'heat':
                        packet_hex = self.controller.make_climate_command(device_id, 0, 'commandON')
                    else:
                        packet_hex = self.controller.make_climate_command(device_id, 0, 'commandOFF')
                elif action == 'setTemp':
                    try:
                        set_temp = int(float(value))
                        min_temp = int(self.config['climate_settings'].get('min_temp', 5))
                        max_temp = int(self.config['climate_settings'].get('max_temp', 40))
                        
                        if not min_temp <= set_temp <= max_temp:
                            self.logger.error(f"설정 온도가 허용 범위를 벗어났습니다: {set_temp}°C (허용범위: {min_temp}~{max_temp}°C)")
                            return
                    except ValueError as e:
                        self.logger.error(f"온도 값이 올바르지 않습니다: {value}")
                        return
                    packet_hex = self.controller.make_climate_command(device_id, set_temp, 'commandCHANGE')
                self.logger.debug(f'온도조절기 {device_id} {action} {value} 명령 생성 {packet_hex}')
            elif device == 'Fan':
                if action == 'power':
                    command_type_value = command["structure"][str(field_positions["commandType"])]["values"]["power"]
                    packet[int(field_positions["commandType"])] = int(command_type_value, 16)
                    power_value = command["structure"][str(field_positions["value"])]["values"]["on" if value == "ON" else "off"]
                    packet[int(field_positions["value"])] = int(power_value, 16)
                    self.logger.debug(f'환기장치 {value} 명령 생성')
                elif action == 'speed':
                    if value not in ["low", "medium", "high"]:
                        self.logger.error(f"잘못된 팬 속도입니다: {value}")
                        return
                    command_type_value = command["structure"][str(field_positions["commandType"])]["values"]["setSpeed"]
                    packet[int(field_positions["commandType"])] = int(command_type_value, 16)
                    value_value = command["structure"][str(field_positions["value"])]["values"][value]
                    packet[int(field_positions["value"])] = int(value_value, 16)
                    self.logger.debug(f'환기장치 속도 {value} 명령 생성')
                self.logger.debug(f'환기장치 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')
            elif device == 'EV':
                #EV 헤더 A0가 중복이라 따로 처리함..
                packet[0] = int("A0", 16)
                #호출(power on)만 가능함.
                packet[int(field_positions["power"])] = int(command["structure"][str(field_positions["power"])]["values"]["on"], 16)
                packet[int(field_positions["unknown1"])] = int(command["structure"][str(field_positions["unknown1"])]["values"]["fixed"], 16)
                packet[int(field_positions["unknown2"])] = int(command["structure"][str(field_positions["unknown2"])]["values"]["fixed"], 16)
                packet[int(field_positions["unknown3"])] = int(command["structure"][str(field_positions["unknown3"])]["values"]["fixed"], 16)
                self.logger.debug(f'엘리베이터 {device_id} {action} {value} 명령 생성 {packet.hex().upper()}')

            if packet_hex is None:
                packet_hex = packet.hex().upper()
                packet_hex = checksum(packet_hex)

            if packet_hex:
                expected_state = self.controller.generate_expected_state_packet(packet_hex)
                if expected_state:
                    self.logger.debug(f'예상 상태: {expected_state}')
                    self.QUEUE.append({
                        'sendcmd': packet_hex, 
                        'count': 0, 
                        'expected_state': expected_state,
                        'received_count': 0
                    })
                else:
                    self.logger.error('예상 상태 패킷 생성 실패')
                    self.QUEUE.append({
                        'sendcmd': packet_hex, 
                        'count': 0, 
                        'expected_state': None,
                        'received_count': 0
                    })
        except Exception as e:
            self.logger.error(f"HA 명령 처리 중 오류 발생: {str(e)}") 