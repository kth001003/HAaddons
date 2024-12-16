import sys
print("Main application starting...", file=sys.stderr)
import paho.mqtt.client as mqtt
import json
import time
import asyncio
import telnetlib
import re
import os
from logger import Logger
from typing import Union, List

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

    def make_hex_temp(self, device_index: int, current_temp: int, target_temp: int, command_type: str) -> Union[str, None]:
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
            >>> make_hex_temp(0, 22, 24, 'commandON')  # 온도절기 1번 켜기
            >>> make_hex_temp(1, 25, 26, 'commandCHANGE')  # 온도조절기 2번 온도 변경
        """
        try:
            if not command_type.startswith('command'):
                self.logger.error(f'잘못된 명령어 타입: {command_type}')
                return None
            
            tmp_hex = self.device_list['Thermo'].get(command_type)
            position = self.device_list['Thermo'].get('commandNUM')
            tmp_hex = self.insert_device_index_to_hex(device_index, tmp_hex, position)
            
            if command_type == 'commandCHANGE':
                setT = self.pad(target_temp)
                chaTnum = self.device_list['Thermo'].get('chaTemp')
                tmp_hex = tmp_hex[:chaTnum - 1] + setT + tmp_hex[chaTnum + 1:]
            
            return self.checksum(tmp_hex)
            
        except Exception as e:
            self.logger.error(f'make_hex_temp 실패 - device_index:{device_index}, 현재 온도: {current_temp}°C, 설정 온도: {target_temp}°C, 상태: {command_type}, 오류: {str(e)}')
            return None

    def make_device_list(self, dev_name):
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

    def find_device(self):
        try:
            # share 디렉토리가 없는 경우 생성
            if not os.path.exists(self.share_dir):
                os.makedirs(self.share_dir)
                self.logger.info(f'{self.share_dir} 디렉토리를 생성했습니다.')
            
            save_path = os.path.join(self.share_dir, 'cwbs_found_device.json')
            
            with open('/apps/cwbs_devinfo.json') as file:
                dev_info = json.load(file)
            
            statePrefix = {dev_info[name]['stateON'][:2]: name for name in dev_info if dev_info[name].get('stateON')}
            device_num = {name: 0 for name in statePrefix.values()}
            collect_data = {name: set() for name in statePrefix.values()}

            target_time = time.time() + 20

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self.logger.info("MQTT broker 접속 완료")
                    self.logger.info("20초동안 기기를 검색합니다.")
                    client.subscribe(f'{self.ELFIN_TOPIC}/#', 0)
                else:
                    errcode = {
                        1: 'Connection refused - incorrect protocol version',
                        2: 'Connection refused - invalid client identifier',
                        3: 'Connection refused - server unavailable',
                        4: 'Connection refused - bad username or password',
                        5: 'Connection refused - not authorised'
                    }
                    self.logger.error(errcode[rc])

            def on_message(client, userdata, msg):
                raw_data = msg.payload.hex().upper()
                for k in range(0, len(raw_data), 16):
                    data = raw_data[k:k + 16]
                    if data == self.checksum(data) and data[:2] in statePrefix:
                        name = statePrefix[data[:2]]
                        collect_data[name].add(data)
                        if dev_info[name].get('stateNUM'):
                            device_num[name] = max([device_num[name], 
                                                 int(data[int(dev_info[name]['stateNUM']) - 1])])
                        else:
                            device_num[name] = 1

            mqtt_client = mqtt.Client('cwbs')
            mqtt_client.username_pw_set(self.config['mqtt_id'], self.config['mqtt_password'])
            mqtt_client.on_connect = on_connect
            mqtt_client.on_message = on_message
            mqtt_client.connect_async(self.config['mqtt_server'])
            mqtt_client.user_data_set(target_time)
            mqtt_client.loop_start()

            while time.time() < target_time:
                pass

            mqtt_client.loop_stop()

            self.logger.info('다음의 데이터를 찾았습니다...')
            self.logger.info('======================================')

            for name in collect_data:
                collect_data[name] = sorted(collect_data[name])
                dev_info[name]['Number'] = device_num[name]
                self.logger.info('DEVICE: {}'.format(name))
                self.logger.info('Packets: {}'.format(collect_data[name]))
                self.logger.info('-------------------')

            self.logger.info('======================================')
            self.logger.info('기기의 숫자만 변경하였습니다. 상태 패킷은 직접 수정하여야 합니다.')
            
            # 파일 저장 시 예외 처리 추가
            try:
                with open(save_path, 'w', encoding='utf-8') as make_file:
                    json.dump(dev_info, make_file, indent="\t")
                    self.logger.info(f'기기리스트 저장 중 : {save_path}')
                    self.logger.info('파일을 수정하고 싶은 경우 종료 후 다시 시작하세요.')
            except IOError as e:
                self.logger.error(f'기기리스트 저장 실패: {str(e)}')
            
            return dev_info
            
        except Exception as e:
            self.logger.error(f'기기 검색 중 오류 발생: {str(e)}')
            return None
    
    async def update_light(self, idx, onoff):
        state = 'power'
        deviceID = 'Light' + str(idx)

        topic = self.STATE_TOPIC.format(deviceID, state)
        self.mqtt_client.publish(topic, onoff.encode())
        self.logger.mqtt(f'->> HA : {topic} >> {onoff}')

    async def update_fan(self, idx, value):
        try:
            deviceID = 'Fan' + str(idx + 1)
            if value == 'OFF':
                topic = self.STATE_TOPIC.format(deviceID, 'power')
                self.mqtt_client.publish(topic, 'OFF'.encode())
            else:
                speed_map = {1: 'low', 2: 'medium', 3: 'high'}
                topic = self.STATE_TOPIC.format(deviceID, 'speed')
                speed = speed_map.get(int(value), 'low')
                self.mqtt_client.publish(topic, speed.encode())
                
                topic = self.STATE_TOPIC.format(deviceID, 'power')
                self.mqtt_client.publish(topic, 'ON'.encode())
                
            self.logger.mqtt(f'->> HA : {topic} -> {value}')
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
                self.mqtt_client.publish(topic, val.encode())
                self.HOMESTATE[deviceID + state] = val
            
            power_state = mode_text
            power_topic = self.STATE_TOPIC.format(deviceID, 'power')
            self.mqtt_client.publish(power_topic, power_state.encode())
            
            self.logger.mqtt(f'->> HA : {deviceID} 온도={curTemp}°C, 설정={setTemp}°C, 상태={power_state}')
        except Exception as e:
            self.logger.error(f"온도 업데이트 중 오류 발생: {str(e)}")

    async def update_outlet_value(self, idx, val):
        deviceID = 'Outlet' + str(idx + 1)
        try:
            val = '%.1f' % float(int(val) / 10)
            topic = self.STATE_TOPIC.format(deviceID, 'watt')
            self.mqtt_client.publish(topic, val.encode())
            self.logger.mqtt(f'->> HA : {topic} -> {val}')
        except:
            pass

    async def update_ev_value(self, idx, val):
        deviceID = 'EV' + str(idx + 1)
        try:
            BF = self.device_list['EV']['BasementFloor']
            val = str(int(val) - BF + 1) if val >= BF else 'B' + str(BF - int(val))
            topic = self.STATE_TOPIC.format(deviceID, 'floor')
            self.mqtt_client.publish(topic, val.encode())
            self.logger.mqtt(f'->> HA : {topic} -> {val}')
        except:
            pass

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
        """
        MQTT 설정을 초기화합니다.
        MQTT 클라이언트를 생성하고, 서버에 연결합니다.
        또한, MQTT 브로커에 접속 성공 시 구독할 토픽을 정의합니다.
        """
        self.mqtt_client = mqtt.Client(self.HA_TOPIC)
        self.mqtt_client.username_pw_set(
            self.config['mqtt_id'],
            self.config['mqtt_password']
        )
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.connect_async(self.config['mqtt_server'])
        self.mqtt_client.loop_start()

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """
        MQTT 브로커에 연결 성공 시 호출되는 함수입니다.
        연결 결과 코드를 확인하고, 성공 시 구독할 토픽을 정의합니다.
        """
        if rc == 0:
            self.logger.info("MQTT broker 접속 완료")
            topics = [
                (f'{self.HA_TOPIC}/+/+/command', 0),
                (f'{self.ELFIN_TOPIC}/recv', 0),
                (f'{self.ELFIN_TOPIC}/send', 0)
            ]
            client.subscribe(topics)
            self.logger.info(f"구독 시작: {topics}")
            
            # MQTT Discovery 메시지 발행
            self.publish_discovery_message()
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
                    self.logger.signal(f'->> RS485 수신: {raw_data}')
                    self.COLLECTDATA['LastRecv'] = time.time_ns()
                    
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.process_elfin_data(raw_data),
                            self.loop
                        )
                elif topics[1] == 'send':
                    raw_data = msg.payload.hex().upper()
                    self.logger.signal(f'->> RS485 송신: {raw_data}')
                    
            elif topics[0] == self.HA_TOPIC:
                value = msg.payload.decode()
                self.logger.mqtt(f'HA로부터 수신: {"/".join(topics)} -> {value}')
                
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
                
                if current_time - last_recv > elfin_reboot_interval * 1_000_000_000:  # 초를 나노초로 변환
                    self.logger.warning(f'{elfin_reboot_interval}초간 신호를 받지 못했습니다.')
                    if (self.config.get("elfin_auto_reboot",True)):
                        self.logger.warning('EW11 재시작을 시도합니다.')
                        await self.reboot_elfin_device()
                        self.COLLECTDATA['LastRecv'] = time.time_ns()
                    else:
                        self.logger.warning('elfin_auto_reboot가 False이므로 아무것도 하지 않습니다.')
                if current_time - last_recv > 200_000_000:  # 100ms를 나노초로 변환
                    await self.process_queue()
                
            except Exception as err:
                self.logger.error(f'process_queue_and_monitor() 오류: {str(err)}')
                return True
            
            await asyncio.sleep(0.001) #1ms 마다

    async def process_queue(self):
        """
        큐에 있는 모든 데이터를 처리합니다.
        
        이 함수는 큐에 있는 모든 데이터를 처리합니다. 각 데이터는 전송 횟수를 포함합니다. 
        전송 횟수가 5회 미만인 경우, 데이터는 큐에 다시 추가됩니다. 
        전송 횟수가 5회 이상인 경우, 데이터는 큐에서 제거됩니다.
        """
        if self.QUEUE:
            send_data = self.QUEUE.pop(0)
            self.mqtt_client.publish(f'{self.ELFIN_TOPIC}/send', bytes.fromhex(send_data['sendcmd']))
            if send_data['count'] < 5:
                send_data['count'] += 1
                self.QUEUE.append(send_data)

    async def process_elfin_data(self, raw_data):
        """
        Elfin 장치에서 전송된 raw_data를 분석합니다.
        
        이 함수는 Elfin 장치에서 전송된 raw_data를 분석합니다. raw_data는 16바이트씩 나누어 각 부분을 분석합니다.
        분석된 데이터는 적절한 처리 함수로 전달됩니다.
        
        Args:
            raw_data (str): Elfin 장치에서 전송된 raw_data.
        """
        try:            
            for k in range(0, len(raw_data), 16):
                data = raw_data[k:k + 16]
                if data == self.checksum(data):
                    self.COLLECTDATA['data'].add(data)
                    hex_array = [data[i:i+2] for i in range(0, len(data), 2)]                    
                    #온조조절기빼고 엉터리입니다
                    if hex_array[0] == '82':  # 온도조절기
                        sub_id = int(hex_array[2])
                        mode = hex_array[1] # 80: off, 81: heat
                        mode_text = 'off' if mode == '80' else 'heat'
                        current_temp = int(hex_array[3], 10)
                        set_temp = int(hex_array[4],10)
                        self.logger.debug(f'{hex_array}:온도조절기 ### {sub_id}번, 모드: {mode_text}, 현재 온도: {current_temp}°C, 설정 온도: {set_temp}°C')
                        await self.update_temperature(sub_id, mode_text, current_temp, set_temp)
                    elif hex_array[0] == 'B0':  # 조명
                        sub_id = int(hex_array[1])
                        state = "ON" if hex_array[2] == "01" else "OFF"
                        self.logger.debug(f'{hex_array}:조명 ### {sub_id}번, 상태: {state}')
                        await self.update_light(sub_id, state)
                    elif data[:2] == 'F6':  # 환기
                        self.logger.debug(f'환기장치 데이터 감지: {data}')
                        if data[2:4] == '01':
                            if data[4] == '0':
                                self.logger.debug('환기장치 OFF 상태')
                                await self.update_fan(0, 'OFF')
                            else:
                                self.logger.debug(f'환기장치 속도: {data[4]}')
                                await self.update_fan(0, data[4])
                    elif data[:2] == '23':  # 엘리베이터
                        self.logger.debug(f'엘리베이터 데이터 감지: {data}')
                        if time.time() - self.COLLECTDATA['EVtime'] > 0.5:
                            self.COLLECTDATA['EVtime'] = time.time()
                            self.logger.debug(f'엘리베이터 층수 업데이트: {data[4]}')
                            await self.update_ev_value(0, data[4])
                            
                    elif data[:2] == 'F9':  # 전기
                        self.logger.debug(f'전기 사용량 데이터 감지: {data[4:6]}')
                        await self.update_outlet_value(0, data[4:6])
                        
                    elif data[:2] == '90':  # 가스
                        self.logger.debug(f'가스 사용량 데이터 감지: {data[4:6]}')
                        await self.update_outlet_value(1, data[4:6])
                else:
                    self.logger.signal(f'체크섬 불일치: {data}')
                
        except Exception as e:
            self.logger.error(f"Elfin 데이터 처리 중 오류 발생: {str(e)}")

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
                        
                        sendcmd = self.make_hex_temp(num, cur_temp, set_temp, 'commandON')
                        self.logger.debug(f'온도조절기 켜기 명령: {sendcmd}')
                    else:  # off는 OFF로 처리
                        cur_temp = self.HOMESTATE.get(topics[1] + 'curTemp')
                        set_temp = self.HOMESTATE.get(topics[1] + 'setTemp')
                        
                        if cur_temp is None or set_temp is None:
                            self.logger.error(f'현재 온도 또는 설정 온도가 존재하지 않습니다: curTemp={cur_temp}, setTemp={set_temp}')
                            return
                        
                        sendcmd = self.make_hex_temp(num, cur_temp, set_temp, 'commandOFF')
                        self.logger.debug(f'온도조절기 끄기 명령: {sendcmd}')
                elif state == 'setTemp':
                    # 문자열을 float로 변환한 후 int로 변환
                    set_temp_value = int(float(value))
                    
                    # HOMESTATE에서 현재 온도와 설정 온도가 존재하는지 확인
                    cur_temp = self.HOMESTATE.get(topics[1] + 'curTemp')
                    
                    if cur_temp is None:
                        self.logger.error(f'현재 온도가 존재하지 않습니다: {topics[1] + "curTemp"}')
                        return
                    
                    sendcmd = self.make_hex_temp(num, cur_temp, set_temp_value, 'commandCHANGE')
                    self.logger.debug(f'온도조절기 설정 온도 변경 명령: {sendcmd}')

            if sendcmd:
                if isinstance(sendcmd, list):
                    for cmd in sendcmd:
                        self.QUEUE.append({'sendcmd': cmd, 'count': 0})
                else:
                    self.QUEUE.append({'sendcmd': sendcmd, 'count': 0})
        except Exception as e:
            self.logger.error(f"HA 명령 처리 중 오류 발생: {str(e)}")

    def publish_discovery_message(self):
        """홈어시스턴트 MQTT Discovery 메시지 발행"""
        try:
            # Discovery 접두사
            discovery_prefix = "homeassistant"
            
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
                            "device": {
                                "identifiers": [f"cwbs_{device_type}"],
                                "name": f"코맥스 {device_type}",
                                "model": "코맥스 월패드",
                                "manufacturer": "Commax"
                            }
                        }
                        
                        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)
                        
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
                            "device": {
                                "identifiers": [f"cwbs_{device_type}"],
                                "name": f"코맥스 {device_type}",
                                "model": "코맥스 월패드",
                                "manufacturer": "Commax"
                            }
                        }
                        
                        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)

                elif device_info['type'] == 'climate':  # 온도조절기
                    for idx, _ in enumerate(device_info['list']):
                        device_id = f"{device_type}{idx+1}"
                        config_topic = f"{discovery_prefix}/climate/{device_id}/config"
                        
                        payload = {
                            "name": f"{device_type} {idx+1}",
                            "unique_id": f"cwbs_{device_id}",
                            "device": {
                                "identifiers": [f"cwbs_{device_type}"],
                                "name": f"코맥스 {device_type}",
                                "model": "코맥스 월패드",
                                "manufacturer": "Commax"
                            },
                            # 현재 온도 토픽
                            "current_temperature_topic": self.STATE_TOPIC.format(device_id, "curTemp"),
                            # 설정 온도 토픽
                            "temperature_command_topic": f"{self.HA_TOPIC}/{device_id}/setTemp/command",
                            "temperature_state_topic": self.STATE_TOPIC.format(device_id, "setTemp"),
                            # 전원 상태 토픽
                            "mode_command_topic": f"{self.HA_TOPIC}/{device_id}/power/command",
                            "mode_state_topic": self.STATE_TOPIC.format(device_id, "power"),
                            # 기타 필수 설정
                            "modes": ["off", "heat"],
                            "temperature_unit": "C",
                            "min_temp": 18,
                            "max_temp": 30,
                            "temp_step": 1,
                            "precision": 0.1
                        }
                        
                        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)

            self.logger.info("MQTT Discovery 설정 완료")
            
        except Exception as e:
            self.logger.error(f"MQTT Discovery 설정 중 오류 발생: {str(e)}")

    def make_device_lists(self):
        device_lists = {}
        for device in self.device_list:
            result = self.make_device_list(device)
            if result:
                device_lists[device] = result
        return device_lists
    
    def run(self):
        self.logger.info("'Commax Wallpad Addon'을 시작합니다.")
        self.logger.info("저장된 기기정보가 있는지 확인합니다. (/share/cwbs_found_device.json)")
        
        try:
            with open(self.share_dir + '/cwbs_found_device.json') as file:
                self.device_list = json.load(file)
                self.DEVICE_LISTS = self.make_device_lists()
                self.logger.info(f'기기정보를 찾았습니다. \n{json.dumps(self.DEVICE_LISTS, ensure_ascii=False, indent=4)}')
        except IOError:
            self.logger.info('저장된 기기 정보가 없습니다. mqtt에 접속하여 기기 찾기를 시도합니다.')
            self.device_list = self.find_device()

        self.setup_mqtt()
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        tasks = [
            self.process_queue_and_monitor(self.config.get('elfin_reboot_interval', 10)),
        ]
        try:
            self.loop.run_until_complete(asyncio.gather(*tasks))
        except Exception as e:
            self.logger.error(f"실행 중 오류 발생: {str(e)}")
        finally:
            self.loop.close()
            self.mqtt_client.loop_stop()

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

if __name__ == '__main__':
    with open('/data/options.json') as file:
        CONFIG = json.load(file)
    logger = Logger(debug=CONFIG['DEBUG'], elfin_log=CONFIG['elfin_log'], mqtt_log=CONFIG['mqtt_log'])
    controller = WallpadController(CONFIG, logger)
    controller.run()
