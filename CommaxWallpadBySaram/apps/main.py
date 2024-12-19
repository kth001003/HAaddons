import sys
print("Starting...", file=sys.stderr)
import paho.mqtt.client as mqtt
import json
import time
import asyncio
import telnetlib
import re
import os
from logger import Logger
from typing import Any, Dict, Union, List, Optional, Set, Tuple, Literal, TypedDict

class CollectData(TypedDict):
    data: Set[str]
    last_recv_time: int

class QueueItem(TypedDict):
    sendcmd: str
    count: int

class WallpadController:
    def __init__(self, config: Dict[str, Any], logger: Logger) -> None:
        self.config: Dict[str, Any] = config
        self.logger: Logger = logger
        self.share_dir: str = '/share'
        self.ELFIN_TOPIC: str = 'ew11'
        self.HA_TOPIC: str = config['mqtt_TOPIC']
        self.STATE_TOPIC: str = self.HA_TOPIC + '/{}/{}/state'
        self.HOMESTATE: Dict[str, str] = {}
        self.QUEUE: List[QueueItem] = []
        self.COLLECTDATA: CollectData = {
            'data': set(),
            'last_recv_time': time.time_ns()
        }
        self.mqtt_client: Optional[mqtt.Client] = None
        self.device_list: Optional[Dict[str, Any]] = None
        self.DEVICE_STRUCTURE: Optional[Dict[str, Any]] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.load_devices_and_packets_structures() # 기기 정보와 패킷 정보를 로드 to self.DEVICE_STRUCTURE

    @staticmethod
    def checksum(input_hex: str) -> Optional[str]:
        """
        input_hex에 checksum을 붙여주는 함수
        
        Args:
            input_hex (str): 기본 16진수 명령어 문자열
        
        Returns:
            str: 체크섬이 포함된 수정된 16진수 명령어. 실패시 None 반환
        """
        try:
            input_hex = input_hex[:14]
            s1 = sum([int(input_hex[val], 16) for val in range(0, 14, 2)])
            s2 = sum([int(input_hex[val + 1], 16) for val in range(0, 14, 2)])
            s1 = s1 + int(s2 // 16)
            s1 = s1 % 16
            s2 = s2 % 16
            return input_hex + format(s1, 'X') + format(s2, 'X')
        except:
            return None

    @staticmethod
    def pad(value: Union[int, str]) -> str:
        value = int(value)
        return '0' + str(value) if value < 10 else str(value)

    # def insert_device_index_to_hex(self, device_index: int, base_hex: str, position: int) -> Optional[str]:
    #     """
    #     기본 16진수 명령어에 기기 인덱스를 삽입하는 함수
        
    #     Args:
    #         device_index (int): 기기의 인덱스 번호 (0부터 시작)
    #         base_hex (str): 기본 16진수 명령어 문자열
    #         position (int): 기기 인덱스를 삽입할 위치 (1부터 시작)
        
    #     Returns:
    #         str: 체크섬이 포함된 수정된 16진수 명령어. 실패시 None 반환
    #     """
    #     if base_hex:
    #         try:
    #             position = int(position)
    #             # position-1 위치의 숫자에 device_index를 더해 새로운 명령 생성
    #             base_hex = f'{base_hex[:position - 1]}{int(base_hex[position - 1]) + device_index}{base_hex[position:]}'
    #         except (ValueError, IndexError) as e:
    #             self.logger.error(f'insert_device_index_to_hex 오류: {str(e)}')
    #             pass
    #     return self.checksum(base_hex)

    def make_climate_command(self, device_id: int, current_temp: int, target_temp: int, command_type: str) -> Union[str, None]:
        """
        온도 조절기의 16진수 명령어를 생성하는 함수
        
        Args:
            device_id (int): 온도 조절기 장치 id
            current_temp (int): 현재 온도 값
            target_temp (int): 설정하고자 하는 목표 온도 값
            command_type (str): 명령어 타입
                - 'commandOFF': 전원 끄기 명령
                - 'commandON': 전원 켜기 명령
                - 'commandCHANGE': 온도 변경 명령
        
        Returns:
            Union[str, None]: 
                - 성공 시: 체크섬이 포함된 16진수 명령어 문자열
                - 실패 시: None
        
        Examples:
            >>> make_climate_command(0, 22, 24, 'commandON')  # 온도절기 1번 켜기
            >>> make_climate_command(1, 25, 26, 'commandCHANGE')  # 온도조절기 2번 온도 변경
        """
        try:
            if self.DEVICE_STRUCTURE is None:
                self.logger.error("DEVICE_STRUCTURE이 초기화되지 않았습니다.")
                return None
            
            thermo_structure = self.DEVICE_STRUCTURE["Thermo"]
            command = thermo_structure["command"]
            
            # 패킷 초기화
            packet = bytearray([0] * 7)

            # 헤더 설정
            packet[0] = int(command["header"], 16)
            
            # 기기 번호 설정
            packet[command["fieldPositions"]["deviceId"]] = device_id
            
            # 명령 타입 및 값 설정
            if command_type == 'commandOFF':
                packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["OFF"], 16)
            elif command_type == 'commandON':
                packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["ON"], 16)
            elif command_type == 'commandCHANGE':
                packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["CHANGE"], 16)
                packet[command["fieldPositions"]["value"]] = target_temp
            else:
                self.logger.error(f'잘못된 명령 타입: {command_type}')
                return None  # 잘못된 명령 타입
            
            # 패킷을 16진수 문자열로 변환
            packet_hex = ''.join([f'{b:02X}' for b in packet])
            
            # 체크섬 추가하여 return
            return self.checksum(packet_hex)
        
        except KeyError as e:
            # DEVICE_STRUCTURE에 필요한 키가 없는 경우
            self.logger.error(f'DEVICE_STRUCTURE에 필요한 키가 없습니다: {e}')
            return None
        except Exception as e:
            # 기타 예외 처리
            self.logger.error(f'예외 발생: {e}')
            return None
        
    
    def find_device(self) -> Dict[str, Any]:
        """
        MQTT에 발행되는 RS485신호에서 기기를 찾는 함수입니다.
        
        Returns:
            Dict[str, Any]: 검색된 기기 타입별 갯수 정보
        """
        if self.DEVICE_STRUCTURE is None:
            self.logger.error("DEVICE_STRUCTURE이 초기화되지 않았습니다.")
            return {}
        try:
            
            if not os.path.exists(self.share_dir):
                os.makedirs(self.share_dir)
                self.logger.info(f'{self.share_dir} 디렉토리를 생성했습니다.')
            
            save_path = os.path.join(self.share_dir, 'commax_found_device.json')
            
            # 헤더로 기기 타입 매핑
            state_prefixes = {
                self.DEVICE_STRUCTURE[name]["state"]["header"]: name 
                for name in self.DEVICE_STRUCTURE 
                if "state" in self.DEVICE_STRUCTURE[name]
            }
            
            # 기기별 최대 인덱스 저장
            device_count = {name: 0 for name in state_prefixes.values()}

            target_time = time.time() + 20

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self.logger.info("MQTT broker 접속 완료")
                    self.logger.info("20초동안 기기를 검색합니다.")
                    client.subscribe(f'{self.ELFIN_TOPIC}/#', 0)
                else:
                    self.logger.error(f"Connection failed with code {rc}")

            def on_message(client, userdata, msg):
                if self.DEVICE_STRUCTURE is None:
                    self.logger.error("DEVICE_STRUCTURE이 초기화되지 않았습니다.")
                    return {}
                raw_data = msg.payload.hex().upper()
                for k in range(0, len(raw_data), 16):
                    data = raw_data[k:k + 16]
                    if data == self.checksum(data) and data[:2] in state_prefixes:
                        name = state_prefixes[data[:2]]
                        device_structure = self.DEVICE_STRUCTURE[name]
                        device_id_position = next(
                            item["position"] 
                            for item in device_structure["state"]["structure"] 
                            if item["name"] == "deviceId"
                        )
                        device_count[name] = max(
                            device_count[name], 
                            int(data[device_id_position*2:device_id_position*2+2], 16)
                        )

            mqtt_client = mqtt.Client('cwbs')
            mqtt_client.username_pw_set(self.config['mqtt_id'], self.config['mqtt_password'])
            mqtt_client.on_connect = on_connect
            mqtt_client.on_message = on_message
            mqtt_client.connect_async(self.config['mqtt_server'])
            mqtt_client.loop_start()

            while time.time() < target_time:
                pass

            mqtt_client.loop_stop()

            self.logger.info('다음의 기기들을 찾았습니다...')
            self.logger.info('======================================')

            device_list = {}
            
            for name, count in device_count.items():
                if count > 0:
                    device_list[name] = {
                        "type": self.DEVICE_STRUCTURE[name]["type"],
                        "count": count
                    }
                    self.logger.info(f'DEVICE: {name}')
                    self.logger.info(f'Count: {count}')
                    self.logger.info('-------------------')

            self.logger.info('======================================')
            
            try:
                with open(save_path, 'w', encoding='utf-8') as make_file:
                    json.dump(device_list, make_file, indent="\t")
                    self.logger.info(f'기기리스트 저장 완료: {save_path}')
            except IOError as e:
                self.logger.error(f'기기리스트 저장 실패: {str(e)}')
            
            return device_list
            # device_list 내용 예시:
            # {"light":
            #   "type":"light",
            #   "count":0
            # }
            
        except Exception as e:
            self.logger.error(f'기기 검색 중 오류 발생: {str(e)}')
            return {}
        
    def make_command_packet(self, name, device_id, command_type):
        try:
            if self.DEVICE_STRUCTURE is None:
                self.logger.error("DEVICE_STRUCTURE이 초기화되지 않았습니다.")
                return None
            
            device_structure = self.DEVICE_STRUCTURE[name]
            command = device_structure["command"]
            
            # 패킷 초기화 (7바이트)
            packet = bytearray(7)
            
            # 헤더 설정
            packet[0] = int(command["header"], 16)
            
            # 기기 번호 설정
            packet[1] = device_id
            
            # 명령 타입 및 값 설정
            if command_type in command["types"]:
                packet[2] = int(command["types"][command_type]["code"], 16)
                if "values" in command["types"][command_type]:
                    if command_type == "power":
                        packet[3] = int(command["types"][command_type]["values"]["on"], 16)
                    elif command_type == "setTemp":
                        packet[3] = 0  # 온도 변경 명령의 경우 기본값 0으로 설정
                else:
                    packet[3] = 0  # 기본값
            else:
                self.logger.error(f'잘못된 명령 타입: {command_type}')
                return None
            
            # 패킷을 16진수 문자열로 변환
            packet_hex = ''.join([f'{b:02X}' for b in packet])
            
            # 체크섬 계산 및 추가
            final_packet = self.checksum(packet_hex)
            
            return final_packet

        except KeyError:
            self.logger.error(f'알 수 없는 기기 또는 명령 구조: {name}, {command_type}')
            return None
        except Exception as e:
            self.logger.error(f'명령 패킷 생성 중 오류 발생: {str(e)}')
            return None

    def publish_mqtt(self, topic: str, value: str, retain: bool = False) -> None:
        if self.mqtt_client:
            self.mqtt_client.publish(topic, value.encode(), retain=retain)
            self.logger.mqtt(f'{topic} >> {value}')
        else:
            self.logger.error('MQTT 클라이언트가 초기화되지 않았습니다.')

    async def update_light(self, idx: int, onoff: str) -> None:
        state = 'power'
        deviceID = 'Light' + str(idx)

        topic = self.STATE_TOPIC.format(deviceID, state)
        self.publish_mqtt(topic, onoff)

    async def update_temperature(self, idx: int, mode_text: str, curTemp: int, setTemp: int) -> None:
        """
        온도 조절기 상태를 업데이트하는 함수입니다.

        Args:
            idx (int): 온도 조절기 장치의 인덱스 번호.
            mode_text (str): 온도 조절기의 모드 텍스트 (예: 'heat', 'off').
            curTemp (int): 현재 온도 값.
            setTemp (int): 설정하고자 하는 목표 온도 값.

        Raises:
            Exception: 온도 업데이트 중 오류가 발생하면 예외를 발생시킵니다.
        """
        try:
            deviceID = 'Thermo' + str(idx)
            
            # 온도 상태 업데이트
            temperature = {
                'curTemp': self.pad(curTemp),
                'setTemp': self.pad(setTemp)
            }
            for state in temperature:
                # key = deviceID + state
                val = temperature[state]
                topic = self.STATE_TOPIC.format(deviceID, state)
                self.publish_mqtt(topic, val)
                self.HOMESTATE[deviceID + state] = val
            
            power_state = mode_text
            power_topic = self.STATE_TOPIC.format(deviceID, 'power')
            self.publish_mqtt(power_topic, power_state)
            
            self.logger.mqtt(f'->> HA : {deviceID} 온도={curTemp}°C, 설정={setTemp}°C, 상태={power_state}')
        except Exception as e:
            self.logger.error(f"온도 업데이트 중 오류 발생: {str(e)}")
 
    # async def update_fan(self, idx, value):
    #     try:
    #         deviceID = 'Fan' + str(idx + 1)
    #         if value == 'OFF':
    #             topic = self.STATE_TOPIC.format(deviceID, 'power')
    #             self.publish_mqtt(topic,'OFF')
    #         else:
    #             speed_map = {1: 'low', 2: 'medium', 3: 'high'}
    #             topic = self.STATE_TOPIC.format(deviceID, 'speed')
    #             speed = speed_map.get(int(value), 'low')
    #             self.publish_mqtt(topic, speed)
                
    #             topic = self.STATE_TOPIC.format(deviceID, 'power')
    #             self.publish_mqtt(topic, 'ON')
                
    #     except Exception as e:
    #         self.logger.error(f"팬 상태 업데이트 중 오류 발생: {str(e)}")

    # async def update_outlet_value(self, idx, val):
    #     deviceID = 'Outlet' + str(idx + 1)
    #     try:
    #         val = '%.1f' % float(int(val) / 10)
    #         topic = self.STATE_TOPIC.format(deviceID, 'watt')
    #         self.publish_mqtt(topic, val)
    #     except:
    #         pass

    # async def update_ev_value(self, idx, val):
    #     deviceID = 'EV' + str(idx + 1)
    #     if self.device_list is not None:
    #         try:
    #             BF = self.device_list['EV']['BasementFloor']
    #             val = str(int(val) - BF + 1) if val >= BF else 'B' + str(BF - int(val))
    #             topic = self.STATE_TOPIC.format(deviceID, 'floor')
    #             self.publish_mqtt(topic, val)
    #         except:
    #             pass
    #     else:
    #         self.logger.error("device_list가 초기화되지 않았습니다.")

    async def reboot_elfin_device(self):
        try:
            ew11 = telnetlib.Telnet(self.config['elfin_server'])
            ew11.read_until(b"login:")
            ew11.write(self.config['elfin_id'].encode('utf-8') + b'\n')
            ew11.read_until(b"password:")
            ew11.write(self.config['elfin_password'].encode('utf-8') + b'\n')
            ew11.write('Restart'.encode('utf-8') + b'\n')
            await asyncio.sleep(10)
        except Exception as err:
            self.logger.error(f'기기 재시작 오류: {str(err)}')

    def setup_mqtt(self) -> None:
        """MQTT 클라이언트를 설정합니다."""
        self.mqtt_client = mqtt.Client(self.HA_TOPIC)
        self.mqtt_client.username_pw_set(
            self.config['mqtt_id'], self.config['mqtt_password']
        )
        
        # on_connect 콜백 타입 수정
        def on_connect_callback(client: mqtt.Client, userdata: Any, flags: Dict[str, int], rc: int) -> None:
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.on_mqtt_connect(client, userdata, flags, rc), 
                    self.loop
                )
        
        self.mqtt_client.on_connect = on_connect_callback  # type: ignore
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.connect_async(self.config['mqtt_server'])
        self.mqtt_client.loop_start()

    async def on_mqtt_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int) -> None:
        if rc == 0:
            self.logger.info("MQTT broker 접속 완료")
            self.logger.info("구독 시작")
            topics = [
                (f'{self.HA_TOPIC}/+/+/command', 0),
                (f'{self.ELFIN_TOPIC}/recv', 0),
                (f'{self.ELFIN_TOPIC}/send', 0)
            ]
            client.subscribe(topics)
            # MQTT Discovery 메시지 발행
            await self.publish_discovery_message()
        else:
            errcode = {
                1: 'Connection refused - incorrect protocol version',
                2: 'Connection refused - invalid client identifier',
                3: 'Connection refused - server unavailable',
                4: 'Connection refused - bad username or password',
                5: 'Connection refused - not authorised'
            }
            self.logger.error(f"MQTT 연결 실패: {errcode.get(rc, '알 수 없는 오류')}")

    def on_mqtt_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            topics = msg.topic.split('/')
            
            if topics[0] == self.ELFIN_TOPIC:
                if topics[1] == 'recv':
                    raw_data = msg.payload.hex().upper()
                    self.logger.signal(f'->> 수신: {raw_data}')                    
                    # 수신 간격 계산
                    current_time = time.time_ns()
                    if 'last_recv_time' in self.COLLECTDATA:
                        interval = current_time - self.COLLECTDATA['last_recv_time']
                        self.logger.signal(f'RS485 수신 간격: {interval/1_000_000} ms')
                    self.COLLECTDATA['last_recv_time'] = current_time
                    
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.process_elfin_data(raw_data),
                            self.loop
                        )
                elif topics[1] == 'send':
                    raw_data = msg.payload.hex().upper()
                    self.logger.signal(f'<<- 송신: {raw_data}')
                    
            elif topics[0] == self.HA_TOPIC:
                value = msg.payload.decode()
                self.logger.mqtt(f'->> 수신: {"/".join(topics)} -> {value}')
                
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.process_ha_command(topics, value),
                        self.loop
                    )
                
        except Exception as err:
            self.logger.error(f'MQTT 메시지 처리 중 오류 발생: {str(err)}')

    async def process_queue_and_monitor(self, elfin_reboot_interval: float) -> bool:
        """
        메시지 큐를 주기적으로 처리하고 기기 상태를 모니터링하는 함수입니다.

        1ms 간격으로 다음 작업들을 수행합니다:
        1. 큐에 있는 메시지 처리 (100ms 이상 통신이 없을 때)
        2. ew11 기기 상태 모니터링 및 필요시 재시작

        Args:
            elfin_reboot_interval (float): ew11 기기 재시작 판단을 위한 통신 제한 시간 (초)

        Raises:
            Exception: 큐 처리 또는 기기 재시작 중 오류 발생시 예외를 발생시킵니다.
        """
        while True:
            try:
                current_time = time.time_ns()
                last_recv = self.COLLECTDATA['last_recv_time']
                signal_interval = (current_time - last_recv)/1_000_000 #ns to ms
                
                if signal_interval > elfin_reboot_interval * 1_000:  # seconds
                    self.logger.warning(f'{elfin_reboot_interval}초간 신호를 받지 못했습니다.')
                    if (self.config.get("elfin_auto_reboot",True)):
                        self.logger.warning('EW11 재시작을 시도합니다.')
                        await self.reboot_elfin_device()
                        self.COLLECTDATA['last_recv_time'] = time.time_ns()
                if signal_interval > 150: #150ms이상 여유있을 때 큐 실행
                    await self.process_queue()
                
            except Exception as err:
                self.logger.error(f'process_queue_and_monitor() 오류: {str(err)}')
                return True
            
            await asyncio.sleep(self.config.get("queue_interval_in_second",0.01)) #100ms

    async def process_queue(self) -> None:
        """
        큐에 있는 모든 데이터를 처리합니다.
        
        이 함수는 큐에 있는 모든 데이터를 처리합니다. 각 데이터는 전송 횟수를 포함합니다. 
        전송 횟수가 설정된 최대 횟수 미만인 경우, 데이터는 큐에 다시 추가됩니다. 
        전송 횟수가 최대 횟수 이상인 경우, 데이터는 큐에서 제거됩니다.
        """
        max_send_count = self.config.get("max_send_count",10)  # 최대 전송 횟수 설정
        if self.QUEUE:
            send_data = self.QUEUE.pop(0)
            if isinstance(send_data['sendcmd'], str):
                cmd_bytes = bytes.fromhex(send_data['sendcmd'])
                self.publish_mqtt(f'{self.ELFIN_TOPIC}/send', cmd_bytes.hex())
                if isinstance(send_data['count'], int):
                    if send_data['count'] < max_send_count:
                        send_data['count'] += 1
                        self.QUEUE.append(send_data)
        await asyncio.sleep(0.1) #100ms 휴식

    async def process_elfin_data(self, raw_data: str) -> None:
        """
        Elfin 장치에서 전송된 raw_data를 분석합니다.
        
        Args:
            raw_data (str): Elfin 장치에서 전송된 raw_data.
        """
        if self.DEVICE_STRUCTURE is None:
            self.logger.error("DEVICE_STRUCTURE가 초기화되지 않았습니다.")
            return
        
        try:
            for k in range(0, len(raw_data), 16):
                data = raw_data[k:k + 16]
                if data == self.checksum(data):
                    self.COLLECTDATA['data'].add(data)
                    byte_data = bytearray.fromhex(data)
                    
                    for device_name, structure in self.DEVICE_STRUCTURE.items():
                        if byte_data[0] == int(structure['state']['header'], 16):
                            if device_name == 'Thermo':
                                device_id = byte_data[structure['state']['fieldPositions']['deviceId']]
                                power = byte_data[structure['state']['fieldPositions']['power']]
                                mode_text = 'off' if power == structure['state']['fieldPositions']['power']['values']['off'] else 'heat'
                                current_temp = byte_data[structure['state']['fieldPositions']['currentTemp']]
                                target_temp = byte_data[structure['state']['fieldPositions']['targetTemp']]
                                
                                self.logger.signal(f'{byte_data.hex()}: 온도조절기 ### {device_id}번, 모드: {mode_text}, 현재 온도: {current_temp}°C, 설정 온도: {target_temp}°C')
                                await self.update_temperature(device_id, mode_text, current_temp, target_temp)
                            
                            elif device_name == 'Light':
                                device_id = byte_data[structure['state']['fieldPositions']['deviceId']]
                                power = byte_data[structure['state']['fieldPositions']['power']]
                                state = "ON" if power == structure['state']['fieldPositions']['power']['values']['on'] else "OFF"
                                
                                self.logger.signal(f'{byte_data.hex()}: 조명 ### {device_id}번, 상태: {state}')
                                await self.update_light(device_id, state)
                            #TODO: 다른 기기타입들 추가
                            
                            break
                else:
                    self.logger.signal(f'체크섬 불일치: {data}')
        
        except Exception as e:
            self.logger.error(f"Elfin 데이터 처리 중 오류 발생: {str(e)}")


    # TODO
    def generate_expected_state_packet(self, command_str):
        if self.DEVICE_STRUCTURE is None:
            self.logger.error("DEVICE_STRUCTURE가 초기화되지 않았습니다.")
            return
        
        packet_structure = self.DEVICE_STRUCTURE
        if len(command_str) != 16:
            self.logger.error("잘못된 입력 길이입니다. 16자를 예상했습니다.")

        # 문자열을 바이트로 변환
        try:
            command_packet = bytes.fromhex(command_str)
        except ValueError:
            self.logger.error(f"잘못된 16진수 문자열입니다.")

        # 명령 세부사항 추출
        command_header = int(packet_structure['command']['header'], 16)
        if command_packet[0] != command_header:
            self.logger.error("알 수 없는 명령 패킷입니다.")

        # 예상 상태 패킷 초기화
        state_structure = packet_structure['state']['structure']
        status_packet = bytearray([0]*8)
        status_packet[0] = int(packet_structure['state']['header'], 16)  # 상태 패킷 시작 바이트

        # 명령을 기반으로 상태 패킷 채우기
        for field in state_structure:
            position = field['position']
            if field['name'] == 'power':
                command_type = command_packet[packet_structure['command']['structure'][1]['position']]
                command_value = command_packet[packet_structure['command']['structure'][2]['position']]
                if command_type == int(packet_structure['command']['types']['power']['code'], 16):
                    if command_value == int(packet_structure['command']['types']['power']['values']['on'], 16):
                        status_packet[position] = int(field['values']['on'], 16)
                    elif command_value == int(packet_structure['command']['types']['power']['values']['off'], 16):
                        status_packet[position] = int(field['values']['off'], 16)
                elif command_type == int(packet_structure['command']['types']['setTemp']['code'], 16):
                    status_packet[position] = int(field['values']['on'], 16)  # 온도 설정 시 기기가 켜져 있다고 가정
            elif field['name'] == 'deviceId':
                status_packet[position] = command_packet[packet_structure['command']['structure'][0]['position']]
            elif field['name'] == 'currentTemp' or field['name'] == 'targetTemp':
                if command_type == int(packet_structure['command']['types']['setTemp']['code'], 16):
                    status_packet[position] = command_value

        # 체크섬 계산
        checksum = sum(status_packet[:-1]) & 0xFF
        status_packet[7] = checksum

        # 상태 패킷을 16진수 문자열로 변환
        return ''.join([f'{b:02x}' for b in status_packet])
    
    async def process_ha_command(self, topics: List[str], value: str) -> None:
        try:
            self.logger.debug(f'HA 명령 처리 시작: {topics}, 값: {value}')
            
            device = ''.join(re.findall('[a-zA-Z]', topics[1]))
            device_id = int(''.join(re.findall('[0-9]', topics[1])))
            state = topics[2]

            if self.DEVICE_STRUCTURE is None:
                self.logger.error("DEVICE_STRUCTURE가 초기화되지 않았습니다.")
                return

            if device not in self.DEVICE_STRUCTURE:
                self.logger.error(f'장치 {device}가 DEVICE_STRUCTURE에 존재하지 않습니다.')
                return

            # 패킷 초기화 (7바이트)
            packet = bytearray(7)
            device_structure = self.DEVICE_STRUCTURE[device]
            command = device_structure["command"]
            
            # 헤더 설정
            packet[0] = int(command["header"], 16)
            
            # 기기 ID 설정
            packet[command["fieldPositions"]["deviceId"]] = device_id

            if device == 'Light':
                power_value = command["structure"][command["fieldPositions"]["power"]]["values"]["on" if value == "ON" else "off"]
                packet[command["fieldPositions"]["power"]] = int(power_value, 16)
                self.logger.debug(f'조명 {value} 명령 생성')
            elif device == 'Thermo':
                cur_temp_str = self.HOMESTATE.get(topics[1] + 'curTemp')
                set_temp_str = self.HOMESTATE.get(topics[1] + 'setTemp')
                if cur_temp_str is None or set_temp_str is None:
                    self.logger.error('현재 온도 또는 설정 온도가 존재하지 않습니다.')
                    return
                
                cur_temp = int(float(cur_temp_str))
                set_temp = int(float(set_temp_str))
                
                if state == 'power':
                    if value == 'heat':
                        self.logger.debug(f'온도조절기 켜기 명령: {device_id}, {cur_temp}, {set_temp}')
                        sendcmd = self.make_climate_command(device_id, cur_temp, set_temp, 'commandON')
                    else:
                        self.logger.debug(f'온도조절기 끄기 명령: {device_id}')
                        sendcmd = self.make_climate_command(device_id, cur_temp, set_temp, 'commandOFF')
                elif state == 'setTemp':
                        sendcmd = self.make_climate_command(device_id, cur_temp, set_temp, 'commandCHANGE')
                        self.logger.debug(f'온도조절기 설정 온도 변경 명령: {sendcmd}')
            elif device == 'Fan':
                packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["power"], 16)
                
                if state == 'power':
                    packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["power"], 16)
                    packet[command["fieldPositions"]["value"]] = int(command[command["fieldPositions"]["value"]]["on" if value == "ON" else "off"], 16)
                    self.logger.debug(f'환기장치 {value} 명령 생성')
                elif state == 'speed':
                    if value not in ["low", "medium", "high"]:
                        self.logger.error(f"잘못된 팬 속도입니다: {value}")
                        return
                    packet[command["fieldPositions"]["commandType"]] = int(command[command["fieldPositions"]["commandType"]]["values"]["setSpeed"], 16)
                    packet[command["fieldPositions"]["value"]] = int(command[command["fieldPositions"]["value"]]["values"][value], 16)
                    self.logger.debug(f'환기장치 속도 {value} 명령 생성')
                
                # 패킷을 16진수 문자열로 변환
                sendcmd = ''.join([f'{b:02X}' for b in packet])
                # 체크섬 추가
                sendcmd = self.checksum(sendcmd)

            if sendcmd:
                if isinstance(sendcmd, list):
                    for cmd in sendcmd:
                        self.QUEUE.append({'sendcmd': cmd, 'count': 0})
                else:
                    self.QUEUE.append({'sendcmd': sendcmd, 'count': 0})
        except Exception as e:
            self.logger.error(f"HA 명령 처리 중 오류 발생: {str(e)}")

    async def publish_discovery_message(self):
        """홈어시스턴트 MQTT Discovery 메시지 발행"""
        try:
            # Discovery 접두사
            discovery_prefix = "homeassistant"
            
            # 공통 디바이스 정보
            device_base_info = {
                "identifiers": ["commax_wallpad"],
                "name": "코맥스 월패드",
                "model": "코맥스 월패드",
                "manufacturer": "Commax"
            }
            
            if self.device_list is None:
                self.logger.error("device_list가 초기화되지 않았습니다.")
                return
            
            for device_name, device_info in self.device_list.items():
                device_type = device_info['type']
                device_count = device_info['count']
                
                for idx in range(device_count + 1):  # 0부터 count까지
                    device_id = f"{device_name}{idx}"
                    
                    if device_type == 'switch':  # 조명
                        config_topic = f"{discovery_prefix}/switch/{device_id}/config"
                        payload = {
                            "name": f"{device_name} {idx}",
                            "unique_id": f"commax_{device_id}",
                            "state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            "command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "payload_on": "ON",
                            "payload_off": "OFF",
                            "device": device_base_info
                        }
                        
                    elif device_type == 'fan':  # 환기장치
                        config_topic = f"{discovery_prefix}/fan/{device_id}/config"
                        payload = {
                            "name": f"{device_name} {idx}",
                            "unique_id": f"commax_{device_id}",
                            "state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            "command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "speed_state_topic": self.STATE_TOPIC.format(device_id, "speed"),
                            "speed_command_topic": f"{self.HA_TOPIC}/{device_id}/speed/command",
                            "speeds": ["low", "medium", "high"],
                            "payload_on": "ON",
                            "payload_off": "OFF",
                            "device": device_base_info
                        }
                        
                    elif device_type == 'climate':  # 온도조절기
                        config_topic = f"{discovery_prefix}/climate/{device_id}/config"
                        payload = {
                            "name": f"{device_name} {idx}",
                            "unique_id": f"commax_{device_id}",
                            "device": device_base_info,
                            "current_temperature_topic": self.STATE_TOPIC.format(device_id, "curTemp"),
                            "temperature_command_topic": f"{self.HA_TOPIC}/{device_id}/setTemp/command",
                            "temperature_state_topic": self.STATE_TOPIC.format(device_id, "setTemp"),
                            "mode_command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "mode_state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            "modes": ["off", "heat"],
                            "temperature_unit": "C",
                            "min_temp": 10,
                            "max_temp": 30,
                            "temp_step": 1,
                            "precision": 0.1
                        }
                    
                    if 'payload' in locals():
                        self.publish_mqtt(config_topic, json.dumps(payload), retain=True)

            self.logger.info("MQTT Discovery 설정 완료")
            
        except Exception as e:
            self.logger.error(f"MQTT Discovery 설정 중 오류 발생: {str(e)}")


    # def generate_device_packets(self, dev_name: str) -> Optional[Dict[str, Any]]:
    #     """
    #     /share/commax_found_device.json로부터 각 기기의 패킷을 만드는 함수
        
    #     Args:
    #         dev_name (str): 기기 이름
        
    #     Returns:
    #         dict: 기기별 패킷 정보
    #     """
    #     if self.device_list is None:
    #         return None
            
    #     num = self.device_list[dev_name].get('Number', 0)
    #     if num > 0:
    #         arr: List[Dict[str, Any]] = [{
    #             cmd + onoff: self.insert_device_index_to_hex(k, 
    #                 str(self.device_list[dev_name].get(cmd + onoff, '')),
    #                 self.device_list[dev_name].get(cmd + 'NUM', 0)
    #             )
    #             for cmd in ['command', 'state']
    #             for onoff in ['ON', 'OFF']
    #         } for k in range(num)]
            
    #         if dev_name == 'fan':
    #             tmp_hex = arr[0].get('stateON')
    #             change = self.device_list[dev_name].get('speedNUM')
    #             if tmp_hex and change:
    #                 arr[0]['stateON'] = self.insert_device_index_to_hex(0, str(tmp_hex), change)
    #                 tmp_hex = self.device_list[dev_name].get('commandCHANGE')
    #                 if tmp_hex:
    #                     arr[0]['CHANGE'] = self.insert_device_index_to_hex(0, str(tmp_hex), change)

    #         return {'type': self.device_list[dev_name]['type'], 'list': arr}
    #     return None

    # def make_device_lists(self) -> Dict[str, Any]:
    #     """
    #     기기 목록을 생성하는 함수
        
    #     Returns:
    #         dict: 기기 목록
    #     """
    #     if self.device_list is None:
    #         raise Exception("device_list가 초기화되지 않았습니다.")
    #     device_lists = {}
    #     for device in self.device_list:
    #         result = self.generate_device_packets(device)
    #         if result:
    #             device_lists[device] = result
    #     return device_lists
    
    def run(self) -> None:
        self.logger.info("'Commax Wallpad Addon'을 시작합니다.")
        self.logger.info("저장된 기기정보가 있는지 확인합니다. (/share/commax_found_device.json)")
        try:
            with open(self.share_dir + '/commax_found_device.json') as file:
                self.device_list = json.load(file)
            if not self.device_list:
                self.logger.info('기기 목록이 비어있습니다. 기기 찾기를 시도합니다.')
                self.device_list = self.find_device()
            else:
                self.logger.info(f'기기정보를 찾았습니다. \n{json.dumps(self.device_list, ensure_ascii=False, indent=4)}')
        except IOError:
            self.logger.info('저장된 기기 정보가 없습니다. mqtt에 접속하여 기기 찾기를 시도합니다.')
            self.device_list = self.find_device()

        self.setup_mqtt()
        
        self.loop = asyncio.get_event_loop()
        tasks = [
            self.process_queue_and_monitor(self.config.get('elfin_reboot_interval', 10)),
        ]
        try:
            self.loop.run_until_complete(asyncio.gather(*tasks))
        except Exception as e:
            self.logger.error(f"실행 중 오류 발생: {str(e)}")
        finally:
            self.loop.close()
            self.mqtt_client.loop_stop() # type: ignore

    def __del__(self):
        """클래스 인스턴스가 삭제될 때 리소스 정리"""
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
        if self.loop and not self.loop.is_closed():
            self.loop.close()
            
    def load_devices_and_packets_structures(self) -> None:
        try:
            with open('/apps/devices_and_packets_structures.json') as file:
                self.DEVICE_STRUCTURE = json.load(file)
        except FileNotFoundError:
            self.logger.error('기기 및 패킷 구조 파일을 찾을 수 없습니다.')
        except json.JSONDecodeError:
            self.logger.error('기기 및 패킷 구조 파일의 JSON 형식이 잘못되었습니다.')

if __name__ == '__main__':
    with open('/data/options.json') as file:
        CONFIG = json.load(file)
    logger = Logger(debug=CONFIG['DEBUG'], elfin_log=CONFIG['elfin_log'], mqtt_log=CONFIG['mqtt_log'])
    controller = WallpadController(CONFIG, logger)
    controller.run()
