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
from typing import Any, Dict, Union, List

class WallpadController:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.share_dir = '/share'
        self.ELFIN_TOPIC = 'ew11'
        self.HA_TOPIC = config['mqtt_TOPIC']
        self.STATE_TOPIC = self.HA_TOPIC + '/{}/{}/state'
        self.HOMESTATE = {}
        self.QUEUE = []
        self.COLLECTDATA = {'data': set(), 'EVtime': time.time(), 'LastRecv': time.time_ns()}
        self.mqtt_client = None
        self.device_list = None
        self.OPTION = config.get('OPTION', {})
        self.device_info = None
        self.loop = None
        self.load_device_structures()

    @staticmethod
    def checksum(input_hex):
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
    def pad(value):
        value = int(value)
        return '0' + str(value) if value < 10 else str(value)

    def insert_device_index_to_hex(self, device_index, base_hex, position):
        """
        기본 16진수 명령어에 기기 인덱스를 삽입하는 함수
        
        Args:
            device_index (int): 기기의 인덱스 번호 (0부터 시작)
            base_hex (str): 기본 16진수 명령어 문자열
            position (int): 기기 인덱스를 삽입할 위치 (1부터 시작)
        
        Returns:
            str: 체크섬이 포함된 수정된 16진수 명령어. 실패시 None 반환
        """
        if base_hex:
            try:
                position = int(position)
                # position-1 위치의 숫자에 device_index를 더해 새로운 명령 생성
                base_hex = f'{base_hex[:position - 1]}{int(base_hex[position - 1]) + device_index}{base_hex[position:]}'
            except (ValueError, IndexError) as e:
                self.logger.error(f'insert_device_index_to_hex 오류: {str(e)}')
                pass
        return self.checksum(base_hex)

    def make_climate_command(self, device_index: int, current_temp: int, target_temp: int, command_type: str) -> Union[str, None]:
        """
        온도 조절기의 16진수 명령어를 생성하는 함수
        
        Args:
            device_index (int): 온도 조절기 장치 인덱스 (0부터 시작)
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
            thermo_structure = self.DEVICE_STRUCTURE["Thermo"]
            command = thermo_structure["command"]
            
            # 패킷 초기화
            packet = bytearray([0] * 7)            

            # 헤더 설정
            packet[0] = int(command["header"], 16)
            
            # 기기 번호 설정 (1부터 시작하므로 device_index에 1을 더함)
            packet[command["structure"][0]["position"]] = device_index + 1
            
            # 명령 타입 및 값 설정
            if command_type == 'commandOFF':
                packet[command["structure"][1]["position"]] = int(command["types"]["power"]["code"], 16)
                packet[command["structure"][2]["position"]] = int(command["types"]["power"]["values"]["off"], 16)
            elif command_type == 'commandON':
                packet[command["structure"][1]["position"]] = int(command["types"]["power"]["code"], 16)
                packet[command["structure"][2]["position"]] = int(command["types"]["power"]["values"]["on"], 16)
            elif command_type == 'commandCHANGE':
                packet[command["structure"][1]["position"]] = int(command["types"]["setTemp"]["code"], 16)
                packet[command["structure"][2]["position"]] = target_temp
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
        
    #TODO commandPower를 만들고있음.. commandON commandOFF를 만들어야함
    def find_device(self) -> Dict[str, Any]:
        """
        MQTT에 발행되는 RS485신호에서 기기를 찾는 함수입니다.
        
        Returns:
            Dict[str, Any]: 검색된 기기 정보가 포함된 딕셔너리
        """
        try:
            if not os.path.exists(self.share_dir):
                os.makedirs(self.share_dir)
                self.logger.info(f'{self.share_dir} 디렉토리를 생성했습니다.')
            
            save_path = os.path.join(self.share_dir, 'cwbs_found_device.json')
            
            state_prefixes = {self.DEVICE_STRUCTURE[name]["state"]["header"]: name 
                              for name in self.DEVICE_STRUCTURE if "state" in self.DEVICE_STRUCTURE[name]}
            device_count = {name: 0 for name in state_prefixes.values()}
            collect_data = {name: set() for name in state_prefixes.values()}

            target_time = time.time() + 20

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self.logger.info("MQTT broker 접속 완료")
                    self.logger.info("20초동안 기기를 검색합니다.")
                    client.subscribe(f'{self.ELFIN_TOPIC}/#', 0)
                else:
                    self.logger.error(f"Connection failed with code {rc}")

            def on_message(client, userdata, msg):
                raw_data = msg.payload.hex().upper()
                for k in range(0, len(raw_data), 16):
                    data = raw_data[k:k + 16]
                    if data == self.checksum(data) and data[:2] in state_prefixes:
                        name = state_prefixes[data[:2]]
                        collect_data[name].add(data)
                        device_structure = self.DEVICE_STRUCTURE[name]
                        device_id_position = next(item["position"] for item in device_structure["state"]["structure"] if item["name"] == "deviceId")
                        device_count[name] = max(device_count[name], int(data[device_id_position*2:device_id_position*2+2], 16))

            mqtt_client = mqtt.Client('cwbs')
            mqtt_client.username_pw_set(self.config['mqtt_id'], self.config['mqtt_password'])
            mqtt_client.on_connect = on_connect
            mqtt_client.on_message = on_message
            mqtt_client.connect_async(self.config['mqtt_server'])
            mqtt_client.loop_start()

            while time.time() < target_time:
                pass

            mqtt_client.loop_stop()

            self.logger.info('다음의 데이터를 찾았습니다...')
            self.logger.info('======================================')

            device_list = {}
            for name, data in collect_data.items():
                if data:
                    device_structure = self.DEVICE_STRUCTURE[name]
                    device_list[name] = {
                        "type": device_structure["type"],
                        "list": []
                    }
                    for i in range(1, device_count[name] + 1):
                        device_info = {}
                        for command_type, command_info in device_structure["command"]["types"].items():
                            command_packet = self.make_command_packet(name, i, command_type)
                            if command_packet:
                                device_info[f"command{command_type.capitalize()}"] = command_packet
                        for state in ["ON", "OFF"]:
                            state_packet = next((packet for packet in data if int(packet[2:4], 16) == i and 
                                                 int(packet[2:4], 16) == (int(device_structure["state"]["structure"][0]["values"][state.lower()], 16) if state == "ON" else 
                                                                          int(device_structure["state"]["structure"][0]["values"][state.lower()], 16))), None)
                            if state_packet:
                                device_info[f"state{state}"] = state_packet
                        device_list[name]["list"].append(device_info)
                    
                    self.logger.info(f'DEVICE: {name}')
                    self.logger.info(f'Count: {device_count[name]}')
                    self.logger.info('-------------------')

            self.logger.info('======================================')
            
            try:
                with open(save_path, 'w', encoding='utf-8') as make_file:
                    json.dump(device_list, make_file, indent="\t")
                    self.logger.info(f'기기리스트 저장 완료: {save_path}')
            except IOError as e:
                self.logger.error(f'기기리스트 저장 실패: {str(e)}')
            
            return device_list
            
        except Exception as e:
            self.logger.error(f'기기 검색 중 오류 발생: {str(e)}')
            return {}
        
    def make_command_packet(self, name, device_id, command_type):
        try:
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

    async def publish_mqtt(self, topic, value, retain = False):
        if self.mqtt_client:
            self.mqtt_client.publish(topic, value.encode(),retain=retain)
            self.logger.mqtt(f'{topic} >> {value}')
        else:
            self.logger.error('MQTT 클라이언트가 초기화되지 않았습니다.')

    async def update_light(self, idx, onoff):
        state = 'power'
        deviceID = 'Light' + str(idx)

        topic = self.STATE_TOPIC.format(deviceID, state)
        await self.publish_mqtt(topic,onoff)
        
    async def update_fan(self, idx, value):
        try:
            deviceID = 'Fan' + str(idx + 1)
            if value == 'OFF':
                topic = self.STATE_TOPIC.format(deviceID, 'power')
                await self.publish_mqtt(topic,'OFF')
            else:
                speed_map = {1: 'low', 2: 'medium', 3: 'high'}
                topic = self.STATE_TOPIC.format(deviceID, 'speed')
                speed = speed_map.get(int(value), 'low')
                await self.publish_mqtt(topic, speed)
                
                topic = self.STATE_TOPIC.format(deviceID, 'power')
                await self.publish_mqtt(topic, 'ON')
                
        except Exception as e:
            self.logger.error(f"팬 상태 업데이트 중 오류 발생: {str(e)}")

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
                await self.publish_mqtt(topic, val)
                self.HOMESTATE[deviceID + state] = val
            
            power_state = mode_text
            power_topic = self.STATE_TOPIC.format(deviceID, 'power')
            await self.publish_mqtt(power_topic, power_state)
            
            self.logger.mqtt(f'->> HA : {deviceID} 온도={curTemp}°C, 설정={setTemp}°C, 상태={power_state}')
        except Exception as e:
            self.logger.error(f"온도 업데이트 중 오류 발생: {str(e)}")

    async def update_outlet_value(self, idx, val):
        deviceID = 'Outlet' + str(idx + 1)
        try:
            val = '%.1f' % float(int(val) / 10)
            topic = self.STATE_TOPIC.format(deviceID, 'watt')
            await self.publish_mqtt(topic, val)
        except:
            pass

    async def update_ev_value(self, idx, val):
        deviceID = 'EV' + str(idx + 1)
        if self.device_list is not None:
            try:
                BF = self.device_list['EV']['BasementFloor']
                val = str(int(val) - BF + 1) if val >= BF else 'B' + str(BF - int(val))
                topic = self.STATE_TOPIC.format(deviceID, 'floor')
                await self.publish_mqtt(topic, val)
            except:
                pass
        else:
            self.logger.error("device_list가 초기화되지 않았습니다.")

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

    def setup_mqtt(self):
        self.mqtt_client = mqtt.Client(self.HA_TOPIC)
        self.mqtt_client.username_pw_set(
            self.config['mqtt_id'], self.config['mqtt_password']
        )
        self.mqtt_client.on_connect = lambda client, userdata, flags, rc: \
            asyncio.create_task(self.on_mqtt_connect(client, userdata, flags, rc))
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.connect_async(self.config['mqtt_server'])
        self.mqtt_client.loop_start()

    async def on_mqtt_connect(self, client, userdata, flags, rc):
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

    def on_mqtt_message(self, client, userdata, msg):
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

    async def process_queue_and_monitor(self, elfin_reboot_interval):
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
                last_recv = self.COLLECTDATA['LastRecv']
                signal_interval = (current_time - last_recv)/1_000_000 #ns to ms
                
                if signal_interval > elfin_reboot_interval * 1_000:  # seconds
                    self.logger.warning(f'{elfin_reboot_interval}초간 신호를 받지 못했습니다.')
                    if (self.config.get("elfin_auto_reboot",True)):
                        self.logger.warning('EW11 재시작을 시도합니다.')
                        await self.reboot_elfin_device()
                        self.COLLECTDATA['LastRecv'] = time.time_ns()
                if signal_interval > 150: #150ms이상 여유있을 때 큐 실행
                    await self.process_queue()
                
            except Exception as err:
                self.logger.error(f'process_queue_and_monitor() 오류: {str(err)}')
                return True
            
            await asyncio.sleep(self.config.get("queue_interval_in_second",0.01)) #100ms

    async def process_queue(self):
        """
        큐에 있는 모든 데이터를 처리합니다.
        
        이 함수는 큐에 있는 모든 데이터를 처리합니다. 각 데이터는 전송 횟수를 포함합니다. 
        전송 횟수가 설정된 최대 횟수 미만인 경우, 데이터는 큐에 다시 추가됩니다. 
        전송 횟수가 최대 횟수 이상인 경우, 데이터는 큐에서 제거됩니다.
        """
        max_send_count = self.config.get("max_send_count",10)  # 최대 전송 횟수 설정
        if self.QUEUE:
            send_data = self.QUEUE.pop(0)
            await self.publish_mqtt(f'{self.ELFIN_TOPIC}/send', bytes.fromhex(send_data['sendcmd']))
            if send_data['count'] < max_send_count:
                send_data['count'] += 1
                self.QUEUE.append(send_data)
        await asyncio.sleep(0.1) #100ms 휴식

    async def process_elfin_data(self, raw_data):
        """
        Elfin 장치에서 전송된 raw_data를 분석합니다.
        
        Args:
            raw_data (str): Elfin 장치에서 전송된 raw_data.
        """
        try:
            for k in range(0, len(raw_data), 16):
                data = raw_data[k:k + 16]
                if data == self.checksum(data):
                    self.COLLECTDATA['data'].add(data)
                    byte_data = bytearray.fromhex(data)
                    
                    for device_name, structure in self.DEVICE_STRUCTURE.items():
                        if byte_data[0] == int(structure['state']['header'], 16):
                            device_info = {}
                            for field in structure['state']['structure']:
                                position = field['position']
                                device_info[field['name']] = byte_data[position]
                            
                            if device_name == 'Thermo':
                                sub_id = device_info['deviceId']
                                mode = device_info['power']
                                mode_text = 'off' if mode == 0x80 else 'heat'
                                current_temp = device_info['currentTemp']
                                set_temp = device_info['targetTemp']
                                self.logger.signal(f'{byte_data.hex()}: 온도조절기 ### {sub_id}번, 모드: {mode_text}, 현재 온도: {current_temp}°C, 설정 온도: {set_temp}°C')
                                await self.update_temperature(sub_id, mode_text, current_temp, set_temp)
                            
                            elif device_name == 'Light':
                                sub_id = device_info['deviceId']
                                state = "ON" if device_info['power'] == 0x01 else "OFF"
                                self.logger.signal(f'{byte_data.hex()}: 조명 ### {sub_id}번, 상태: {state}')
                                await self.update_light(sub_id, state)
                            
                            # elif device_name == 'Fan':
                            #     speed = device_info['speed']
                            #     state = 'OFF' if speed == 0 else str(speed)
                            #     self.logger.debug(f'환기장치 속도: {state}')
                            #     await self.update_fan(0, state)
                            
                            # elif device_name == 'EV':
                            #     if time.time() - self.COLLECTDATA['EVtime'] > 0.5:
                            #         self.COLLECTDATA['EVtime'] = time.time()
                            #         floor = device_info['floor']
                            #         self.logger.debug(f'엘리베이터 층수 업데이트: {floor}')
                            #         await self.update_ev_value(0, floor)
                            
                            # elif device_name == 'Outlet':
                            #     usage = device_info['usage']
                            #     self.logger.debug(f'전기 사용량 데이터 감지: {usage}')
                            #     await self.update_outlet_value(0, usage)
                            
                            # elif device_name == 'Gas':
                            #     usage = device_info['usage']
                            #     self.logger.debug(f'가스 사용량 데이터 감지: {usage}')
                            #     await self.update_outlet_value(1, usage)
                            break
                else:
                    self.logger.signal(f'체크섬 불일치: {data}')
        
        except Exception as e:
            self.logger.error(f"Elfin 데이터 처리 중 오류 발생: {str(e)}")


    # TODO
    def generate_expected_state_packet(self, command_str):
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
    
    async def process_ha_command(self, topics, value):
        try:
            self.logger.debug(f'HA 명령 처리 시작: {topics}, 값: {value}')
            
            device = ''.join(re.findall('[a-zA-Z]', topics[1]))
            num = int(''.join(re.findall('[0-9]', topics[1]))) - 1
            state = topics[2]

            # DEVICE_LISTS에서 장치가 존재하는지 확인
            if device not in self.DEVICE_LISTS:
                self.logger.error(f'장치 {device}가 DEVICE_LISTS에 존재하지 않습니다.')
                return

            if num < 0 or num >= len(self.DEVICE_LISTS[device]['list']):
                self.logger.error(f'장치 번호 {num}가 유효하지 않습니다. 범위: 0-{len(self.DEVICE_LISTS[device]["list"]) - 1}')
                return

            if device == 'Light':
                if value == 'ON':
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandON']
                    self.logger.debug(f'조명 켜기 명령: {sendcmd}')
                else:
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandOFF']
                    self.logger.debug(f'조명 끄기 명령: {sendcmd}')
            elif device == 'Fan':
                if state == 'power':
                    if value == 'ON':
                        sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandON']
                        self.logger.debug(f'팬 켜기 명령: {sendcmd}')
                    else:
                        sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandOFF']
                        self.logger.debug(f'팬 끄기 명령: {sendcmd}')
                else:
                    speed = {'low': 0, 'medium': 1, 'high': 2}
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['CHANGE'][speed[value]]
                    self.logger.debug(f'팬 속도 변경 명령: {sendcmd}')
            elif device == 'Thermo':
                if state == 'power':
                    if value == 'heat':  # heat는 ON으로 처리
                        cur_temp = self.HOMESTATE.get(topics[1] + 'curTemp')
                        set_temp = self.HOMESTATE.get(topics[1] + 'setTemp')
                        
                        if cur_temp is None or set_temp is None:
                            self.logger.error(f'현재 온도 또는 설정 온도가 존재하지 않습니다: curTemp={cur_temp}, setTemp={set_temp}')
                            return
                        
                        sendcmd = self.make_climate_command(num, cur_temp, set_temp, 'commandON')
                        self.logger.debug(f'온도조절기 켜기 명령: {sendcmd}')
                    else:  # off는 OFF로 처리
                        cur_temp = self.HOMESTATE.get(topics[1] + 'curTemp')
                        set_temp = self.HOMESTATE.get(topics[1] + 'setTemp')
                        
                        if cur_temp is None or set_temp is None:
                            self.logger.error(f'현재 온도 또는 설정 온도가 존재하지 않습니다: curTemp={cur_temp}, setTemp={set_temp}')
                            return
                        
                        sendcmd = self.make_climate_command(num, cur_temp, set_temp, 'commandOFF')
                        self.logger.debug(f'온도조절기 끄기 명령: {sendcmd}')
                elif state == 'setTemp':
                    # 문자열을 float로 변환한 후 int로 변환
                    set_temp_value = int(float(value))
                    
                    # HOMESTATE에서 현재 온도와 설정 온도가 존재하는지 확인
                    cur_temp = self.HOMESTATE.get(topics[1] + 'curTemp')
                    
                    if cur_temp is None:
                        self.logger.error(f'현재 온도가 존재하지 않습니다: {topics[1] + "curTemp"}')
                        return
                    
                    sendcmd = self.make_climate_command(num, cur_temp, set_temp_value, 'commandCHANGE')
                    self.logger.debug(f'온도조절기 설정 온도 변경 명령: {sendcmd}')

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
            device_info = {
                "identifiers": ["cwbs_wallpad"],
                "name": "코맥스 월패드",
                "model": "코맥스 월패드",
                "manufacturer": "Commax"
            }
            
            for device_type, device_info in self.DEVICE_LISTS.items():
                if device_info['type'] == 'switch':  # 조명
                    for idx, _ in enumerate(device_info['list']):
                        device_id = f"{device_type}{idx+1}"
                        config_topic = f"{discovery_prefix}/switch/{device_id}/config"
                        
                        payload = {
                            "name": f"{device_type} {idx+1}",
                            "unique_id": f"cwbs_{device_id}",
                            "state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            "command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "payload_on": "ON",
                            "payload_off": "OFF",
                            "device": device_info
                        }
                        await self.publish_mqtt(config_topic, json.dumps(payload), retain=True)

                elif device_info['type'] == 'fan':  # 환기장치 
                    for idx, _ in enumerate(device_info['list']):
                        device_id = f"{device_type}{idx+1}"
                        config_topic = f"{discovery_prefix}/fan/{device_id}/config"
                        
                        payload = {
                            "name": f"{device_type} {idx+1}",
                            "unique_id": f"cwbs_{device_id}",
                            "state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            "command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "speed_state_topic": self.STATE_TOPIC.format(device_id, "speed"),
                            "speed_command_topic": f"{self.HA_TOPIC}/{device_id}/speed/command",
                            "speeds": ["low", "medium", "high"],
                            "payload_on": "ON", 
                            "payload_off": "OFF",
                            "device": device_info
                        }
                        await self.publish_mqtt(config_topic, json.dumps(payload), retain=True)

                elif device_info['type'] == 'climate':  # 온도조절기
                    for idx, _ in enumerate(device_info['list']):
                        device_id = f"{device_type}{idx+1}"
                        config_topic = f"{discovery_prefix}/climate/{device_id}/config"
                        
                        payload = {
                            "name": f"{device_type} {idx+1}",
                            "unique_id": f"cwbs_{device_id}",
                            "device": device_info,
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
                        
                        await self.publish_mqtt(config_topic, json.dumps(payload), retain=True)

            self.logger.info("MQTT Discovery 설정 완료")
            
        except Exception as e:
            self.logger.error(f"MQTT Discovery 설정 중 오류 발생: {str(e)}")


    def generate_device_packets(self, dev_name):
        """
        /share/cwbs_found_device.json로부터 각 기기의 패킷을 만드는 함수
        
        Args:
            dev_name (str): 기기 이름
        
        Returns:
            dict: 기기별 패킷 정보
        """
        if self.device_list is None:
            raise Exception("device_list가 초기화되지 않았습니다.")
        num = self.device_list[dev_name].get('Number', 0)
        if num > 0:
            arr = [{
                cmd + onoff: self.insert_device_index_to_hex(k, 
                    self.device_list[dev_name].get(cmd + onoff),
                    self.device_list[dev_name].get(cmd + 'NUM')
                )
                for cmd in ['command', 'state']
                for onoff in ['ON', 'OFF']
            } for k in range(num)]
            
            if dev_name == 'fan':
                tmp_hex = arr[0]['stateON']
                change = self.device_list[dev_name].get('speedNUM')
                arr[0]['stateON'] = [
                    self.insert_device_index_to_hex(k, tmp_hex, change) 
                    for k in range(3)
                ]
                tmp_hex = self.device_list[dev_name].get('commandCHANGE')
                arr[0]['CHANGE'] = [
                    self.insert_device_index_to_hex(k, tmp_hex, change) 
                    for k in range(3)
                ]

            return {'type': self.device_list[dev_name]['type'], 'list': arr}
        return None

    def make_device_lists(self):
        """
        기기 목록을 생성하는 함수
        
        Returns:
            dict: 기기 목록
        """
        if self.device_list is None:
            raise Exception("device_list가 초기화되지 않았습니다.")
        device_lists = {}
        for device in self.device_list:
            result = self.generate_device_packets(device)
            if result:
                device_lists[device] = result
        return device_lists
    
    #TODO: DEVICE_LISTS는 없는데.. device_list,,, 정리하기
    def run(self):
        self.logger.info("'Commax Wallpad Addon'을 시작합니다.")
        self.logger.info("저장된 기기정보가 있는지 확인합니다. (/share/cwbs_found_device.json)")
        try:
            with open(self.share_dir + '/cwbs_found_device.json') as file:
                self.device_list = json.load(file)
            if not self.device_list:
                self.logger.info('기기 목록이 비어있습니다. 기기 찾기를 시도합니다.')
                self.device_list = self.find_device()
            else:
                self.logger.info(f'기기정보를 찾았습니다. \n{json.dumps(self.DEVICE_LISTS, ensure_ascii=False, indent=4)}')
            self.DEVICE_LISTS = self.make_device_lists()
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
            
    def load_device_structures(self):
        try:
            with open('/apps/devices_and_packet_structures.json') as file:
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
