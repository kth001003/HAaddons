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
        self.DEVICE_LISTS = {}

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
            except:
                pass
        return self.checksum(input_hex)

    def make_hex_temp(self, k, curTemp, setTemp, state):
        if state == 'OFF' or state == 'ON' or state == 'CHANGE':
            tmp_hex = self.device_list['Thermo'].get('command' + state)
            change = self.device_list['Thermo'].get('commandNUM')
            tmp_hex = self.make_hex(k, tmp_hex, change)
            if state == 'CHANGE':
                setT = self.pad(setTemp)
                chaTnum = self.OPTION['Thermo'].get('chaTemp')
                tmp_hex = tmp_hex[:chaTnum - 1] + setT + tmp_hex[chaTnum + 1:]
            return self.checksum(tmp_hex)
        else:
            tmp_hex = self.device_list['Thermo'].get(state)
            change = self.device_list['Thermo'].get('stateNUM')
            tmp_hex = self.make_hex(k, tmp_hex, change)
            setT = self.pad(setTemp)
            curT = self.pad(curTemp)
            curTnum = self.OPTION['Thermo'].get('curTemp')
            setTnum = self.OPTION['Thermo'].get('setTemp')
            tmp_hex = tmp_hex[:setTnum - 1] + setT + tmp_hex[setTnum + 1:]
            tmp_hex = tmp_hex[:curTnum - 1] + curT + tmp_hex[curTnum + 1:]
            if state == 'stateOFF':
                return self.checksum(tmp_hex)
            elif state == 'stateON':
                tmp_hex2 = tmp_hex[:3] + str(3) + tmp_hex[4:]
                return [self.checksum(tmp_hex), self.checksum(tmp_hex2)]
            else:
                return None

    def make_device_info(self, dev_name):
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

    async def update_fan(self, idx, onoff):
        deviceID = 'Fan' + str(idx + 1)
        if onoff == 'ON' or onoff == 'OFF':
            state = 'power'
        else:
            try:
                speed_list = ['low', 'medium', 'high']
                onoff = speed_list[int(onoff) - 1]
                state = 'speed'
            except:
                return
        key = deviceID + state
        topic = self.STATE_TOPIC.format(deviceID, state)
        self.mqtt_client.publish(topic, onoff.encode())
        if self.config['mqtt_log']:
            self.logger.info(f'[LOG] ->> HA : {topic} >> {onoff}')

    async def update_temperature(self, idx, curTemp, setTemp):
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
            BF = self.device_info['EV']['BasementFloor']
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

    def run(self):
        self.logger.info("'Commax Wallpad by Saram'을 시작합니다.")
        
        try:
            with open(self.share_dir + '/cwbs_found_device.json') as file:
                self.logger.info('기기 정보 파일을 찾음: /share/cwbs_found_device.json')
                self.device_list = json.load(file)
        except IOError:
            self.logger.info('기기 정보 파일이 없습니다. mqtt에 접속하여 기기를 찾습니다.')
            self.device_list = self.find_device()

        self.setup_mqtt()
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.handle_elfin_reboot(
                self.config.get('elfin_reboot_interval', 10)
            )
        )
        loop.close()
        self.mqtt_client.loop_stop()

if __name__ == '__main__':
    with open('/data/options.json') as file:
        CONFIG = json.load(file)
    
    logger = Logger(debug=CONFIG['DEBUG'], elfin_log=CONFIG['elfin_log'])
    controller = WallpadController(CONFIG, logger)
    controller.run()
