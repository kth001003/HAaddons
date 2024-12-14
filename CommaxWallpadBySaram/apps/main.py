import sys
print("Main application starting...", file=sys.stderr)
import paho.mqtt.client as mqtt
import json
import time
import asyncio
import telnetlib
import re

class Logger:
    def __init__(self, debug=False, elfin_log=False):
        self.enable_debug = debug
        self.enable_elfin_log = elfin_log

    def log(self, string):
        date = time.strftime('%Y-%m-%d %p %I:%M:%S', time.localtime(time.time()))
        print(f'[{date}] {string}')

    def info(self, string):
        self.log(f'[INFO] {string}')

    def error(self, err):
        self.log(f'[ERROR] {err}')

    def warning(self, message):
        self.log(f'[WARNING] {message}')

    def debug(self, message):
        if self.enable_debug:
            self.log(f'[DEBUG] {message}')

    def signal(self, message):
        if self.enable_elfin_log:
            self.log(f'[SIGNAL] {message}')

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

    def find_device(self):
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
                self.logger.info(errcode[rc])

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
        
        with open(self.share_dir + '/cwbs_found_device.json', 'w', encoding='utf-8') as make_file:
            json.dump(dev_info, make_file, indent="\t")
            self.logger.info('기기리스트 저장 중 : /share/cowbs_found_device.json')
            self.logger.info('파일을 수정하고 싶은 경우 종료 후 다시 시작하세요.')
        return dev_info

    def pad(self, value):
        value = int(value)
        return '0' + str(value) if value < 10 else str(value)

    def make_hex(self, k, input_hex, change):
        if input_hex:
            try:
                change = int(change)
                input_hex = f'{input_hex[:change - 1]}{int(input_hex[change - 1]) + k}{input_hex[change:]}'
            except (ValueError, IndexError) as e:
                self.logger.error(f'make_hex 오류: {str(e)}')
                pass
        return self.checksum(input_hex)

    def make_hex_temp(self, k, curTemp, setTemp, state):
        if state == 'OFF' or state == 'ON' or state == 'CHANGE':
            tmp_hex = self.device_list['Thermo'].get('command' + state)
            change = self.device_list['Thermo'].get('commandNUM')
            tmp_hex = self.make_hex(k, tmp_hex, change)
            if state == 'CHANGE':
                setT = self.pad(setTemp)
                chaTnum = self.device_list['Thermo'].get('chaTemp')
                tmp_hex = tmp_hex[:chaTnum - 1] + setT + tmp_hex[chaTnum + 1:]
            return self.checksum(tmp_hex)
        else:
            tmp_hex = self.device_list['Thermo'].get(state)
            change = self.device_list['Thermo'].get('stateNUM')
            tmp_hex = self.make_hex(k, tmp_hex, change)
            setT = self.pad(setTemp)
            curT = self.pad(curTemp)
            curTnum = self.device_list['Thermo'].get('curTemp')
            setTnum = self.device_list['Thermo'].get('setTemp')
            tmp_hex = tmp_hex[:setTnum - 1] + setT + tmp_hex[setTnum + 1:]
            tmp_hex = tmp_hex[:curTnum - 1] + curT + tmp_hex[curTnum + 1:]
            if state == 'stateOFF':
                return self.checksum(tmp_hex)
            elif state == 'stateON':
                tmp_hex2 = tmp_hex[:3] + str(3) + tmp_hex[4:]
                return [self.checksum(tmp_hex), self.checksum(tmp_hex2)]
            else:
                return None

    def make_device_list(self, dev_name):
        num = self.device_list[dev_name].get('Number', 0)
        if num > 0:
            arr = [{
                cmd + onoff: self.make_hex(k, 
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
                    self.make_hex(k, tmp_hex, change) 
                    for k in range(3)
                ]
                tmp_hex = self.device_list[dev_name].get('commandCHANGE')
                arr[0]['CHANGE'] = [
                    self.make_hex(k, tmp_hex, change) 
                    for k in range(3)
                ]

            return {'type': self.device_list[dev_name]['type'], 'list': arr}
        return None

    async def update_state(self, device, idx, onoff):
        state = 'power'
        deviceID = device + str(idx + 1)
        key = deviceID + state

        topic = self.STATE_TOPIC.format(deviceID, state)
        self.mqtt_client.publish(topic, onoff.encode())
        if self.config['mqtt_log']:
            self.logger.info(f'[LOG] ->> HA : {topic} >> {onoff}')

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
                
            if self.config['mqtt_log']:
                self.logger.debug(f'[LOG] ->> HA : {topic} -> {value}')
        except Exception as e:
            self.logger.error(f"팬 상태 업데이트 중 오류 발생: {str(e)}")

    async def update_temperature(self, idx, curTemp, setTemp):
        try:
            deviceID = 'Thermo' + str(idx + 1)
            temperature = {
                'curTemp': self.pad(curTemp),
                'setTemp': self.pad(setTemp)
            }
            for state in temperature:
                key = deviceID + state
                val = temperature[state]
                topic = self.STATE_TOPIC.format(deviceID, state)
                self.mqtt_client.publish(topic, val.encode())
                self.HOMESTATE[deviceID + 'curTemp'] = curTemp
                self.HOMESTATE[deviceID + 'setTemp'] = setTemp
                if self.config['mqtt_log']:
                    self.logger.info(f'[LOG] ->> HA : {topic} -> {val}')
        except Exception as e:
            self.logger.error(f"온도 업데이트 중 오류 발생: {str(e)}")

    async def update_outlet_value(self, idx, val):
        deviceID = 'Outlet' + str(idx + 1)
        try:
            val = '%.1f' % float(int(val) / 10)
            topic = self.STATE_TOPIC.format(deviceID, 'watt')
            self.mqtt_client.publish(topic, val.encode())
            self.logger.debug(f'[LOG] ->> HA : {topic} -> {val}')
        except:
            pass

    async def update_ev_value(self, idx, val):
        deviceID = 'EV' + str(idx + 1)
        try:
            BF = self.device_list['EV']['BasementFloor']
            val = str(int(val) - BF + 1) if val >= BF else 'B' + str(BF - int(val))
            topic = self.STATE_TOPIC.format(deviceID, 'floor')
            self.mqtt_client.publish(topic, val.encode())
            self.logger.debug(f'[LOG] ->> HA : {topic} -> {val}')
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
        if rc == 0:
            self.logger.info("MQTT broker 접속 완료")
            topics = [
                (f'{self.HA_TOPIC}/+/+/command', 0),
                (f'{self.ELFIN_TOPIC}/recv', 0)
            ]
            client.subscribe(topics)
            self.logger.info(f"구독 시작: {topics}")
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
                raw_data = msg.payload.hex().upper()
                if self.config['elfin_log']:
                    self.logger.signal(f'수신: {raw_data}')
                self.COLLECTDATA['LastRecv'] = time.time_ns()
                
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.process_elfin_data(raw_data),
                        self.loop
                    )
                
            elif topics[0] == self.HA_TOPIC:
                value = msg.payload.decode()
                if self.config['mqtt_log']:
                    self.logger.debug(f'HA로부터 수신: {"/".join(topics)} -> {value}')
                
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.process_ha_command(topics, value),
                        self.loop
                    )
                
        except Exception as err:
            self.logger.error(f'MQTT 메시지 처리 중 오류 발생: {str(err)}')

    async def handle_elfin_reboot(self, elfin_reboot_interval):
        while True:
            try:
                if time.time_ns() - self.COLLECTDATA['LastRecv'] > elfin_reboot_interval * 1e9:
                    self.logger.warning(f'{elfin_reboot_interval}초간 신호를 받지 못했습니다. ew11 기기를 재시작합니다.')
                    await self.reboot_elfin_device()
                    self.COLLECTDATA['LastRecv'] = time.time_ns()
                elif time.time_ns() - self.COLLECTDATA['LastRecv'] > 1e8:
                    await self.process_queue()
            except Exception as err:
                self.logger.error(f'send_to_elfin() 오류: {str(err)}')
                return True
            await asyncio.sleep(0.01)

    async def process_queue(self):
        if self.QUEUE:
            send_data = self.QUEUE.pop(0)
            if self.config['elfin_log']:
                self.logger.signal(f'신호 전송: {send_data}')
            self.mqtt_client.publish(f'{self.ELFIN_TOPIC}/send', bytes.fromhex(send_data['sendcmd']))
            if send_data['count'] < 5:
                send_data['count'] += 1
                self.QUEUE.append(send_data)
            else:
                if self.config['elfin_log']:
                    self.logger.signal(f'5회 이상 전송 실패. 큐에서 제거: {send_data}')

    def run(self):
        self.logger.info("'Commax Wallpad Addon'을 시작합니다.")
        
        try:
            with open(self.share_dir + '/cwbs_found_device.json') as file:
                self.logger.info('기기 정보 파일을 찾음: /share/cwbs_found_device.json')
                self.device_list = json.load(file)
                self.DEVICE_LISTS = self.make_device_lists()
        except IOError:
            self.logger.info('기기 정보 파일이 없습니다. mqtt에 접속하여 기기를 찾습니다.')
            self.device_list = self.find_device()

        self.setup_mqtt()
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        tasks = [
            self.handle_elfin_reboot(self.config.get('elfin_reboot_interval', 10)),
            self.process_mqtt_messages(),
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

    async def process_elfin_data(self, raw_data):
        try:
            for k in range(0, len(raw_data), 16):
                data = raw_data[k:k + 16]
                if data == self.checksum(data):
                    self.COLLECTDATA['data'].add(data)
                    if data[:2] == '30':  # 엘리베이터
                        if time.time() - self.COLLECTDATA['EVtime'] > 0.5:
                            self.COLLECTDATA['EVtime'] = time.time()
                            await self.update_ev_value(0, data[4])
                    elif data[:2] == '31':  # 전기
                        await self.update_outlet_value(0, data[4:6])
                    elif data[:2] == '32':  # 가스
                        await self.update_outlet_value(1, data[4:6])
                    elif data[:2] == '33':  # 수도
                        await self.update_outlet_value(2, data[4:6])
                    elif data[:2] == '36':  # 온도조절기
                        if data[2:4] == '01':
                            await self.update_temperature(0, data[4], data[5])
                        elif data[2:4] == '02':
                            await self.update_temperature(1, data[4], data[5])
                    elif data[:2] == '34':  # 조명
                        if data[2:4] == '01':
                            await self.update_state('Light', 0, 'ON' if data[4] == '1' else 'OFF')
                        elif data[2:4] == '02':
                            await self.update_state('Light', 1, 'ON' if data[4] == '1' else 'OFF')
                    elif data[:2] == '35':  # 환기
                        if data[2:4] == '01':
                            if data[4] == '0':
                                await self.update_fan(0, 'OFF')
                            else:
                                await self.update_fan(0, data[4])
        except Exception as e:
            self.logger.error(f"Elfin 데이터 처리 중 오류 발생: {str(e)}")

    async def process_ha_command(self, topics, value):
        try:
            device = ''.join(re.findall('[a-zA-Z]', topics[1]))
            num = int(''.join(re.findall('[0-9]', topics[1]))) - 1
            state = topics[2]

            if device == 'Light':
                if value == 'ON':
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandON']
                else:
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandOFF']
            elif device == 'Fan':
                if state == 'power':
                    if value == 'ON':
                        sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandON']
                    else:
                        sendcmd = self.DEVICE_LISTS[device]['list'][num]['commandOFF']
                else:
                    speed = {'low': 0, 'medium': 1, 'high': 2}
                    sendcmd = self.DEVICE_LISTS[device]['list'][num]['CHANGE'][speed[value]]
            elif device == 'Thermo':
                if state == 'power':
                    if value == 'ON':
                        sendcmd = self.make_hex_temp(num, 
                            self.HOMESTATE[topics[1] + 'curTemp'],
                            self.HOMESTATE[topics[1] + 'setTemp'],
                            'commandON')
                    else:
                        sendcmd = self.make_hex_temp(num, 
                            self.HOMESTATE[topics[1] + 'curTemp'],
                            self.HOMESTATE[topics[1] + 'setTemp'],
                            'commandOFF')
                else:
                    sendcmd = self.make_hex_temp(num, 
                        self.HOMESTATE[topics[1] + 'curTemp'],
                        value,
                        'commandCHANGE')

            if sendcmd:
                if isinstance(sendcmd, list):
                    for cmd in sendcmd:
                        self.QUEUE.append({'sendcmd': cmd, 'count': 0})
                else:
                    self.QUEUE.append({'sendcmd': sendcmd, 'count': 0})
        except Exception as e:
            self.logger.error(f"HA 명령 처리 중 오류 발생: {str(e)}")

    async def process_mqtt_messages(self):
        """MQTT 메시지 처리 루프"""
        while True:
            await asyncio.sleep(0.1)
            # MQTT 메시지는 on_mqtt_message 콜백에서 처리됨

    def make_device_lists(self):
        device_lists = {}
        for device in self.device_list:
            result = self.make_device_list(device)
            if result:
                device_lists[device] = result
        return device_lists

if __name__ == '__main__':
    print("Reading config file...", file=sys.stderr)
    with open('/data/options.json') as file:
        CONFIG = json.load(file)
    
    logger = Logger(debug=CONFIG['DEBUG'], elfin_log=CONFIG['elfin_log'])
    logger.info("Initializing settings...")
    controller = WallpadController(CONFIG, logger)
    controller.run()
