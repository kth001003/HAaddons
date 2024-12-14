import sys
print("Main application starting...", file=sys.stderr)
import paho.mqtt.client as mqtt
import json
import time
import asyncio
import telnetlib
import re

share_dir = '/share'

ELFIN_TOPIC = 'ew11'


def log(string):
    # 현재 시간을 포함하여 로그 메시지를 출력합니다.
    date = time.strftime('%Y-%m-%d %p %I:%M:%S', time.localtime(time.time()))
    print(f'[{date}] {string}')
    return


def checksum(input_hex):
    # 주어진 16진수 문자열의 체크섬을 계산하여 반환합니다.
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


def find_device(config):
    # MQTT를 통해 기기를 검색하고, 기기 정보를 JSON 파일로 저장합니다.
    HA_TOPIC = config['mqtt_TOPIC']

    with open('/apps/cwbs_devinfo.json') as file:
        dev_info = json.load(file)
    statePrefix = {dev_info[name]['stateON'][:2]: name for name in dev_info if dev_info[name].get('stateON')}
    device_num = {name: 0 for name in statePrefix.values()}
    collect_data = {name: set() for name in statePrefix.values()}

    target_time = time.time() + 20

    def on_connect(client, userdata, flags, rc):
        # MQTT 브로커에 연결되었을 때 호출됩니다.
        if rc == 0:
            log("MQTT broker 접속 완료")
            log("20초동안 기기를 검색합니다.")
            client.subscribe(f'{ELFIN_TOPIC}/#', 0)
        else:
            errcode = {1: 'Connection refused - incorrect protocol version',
                       2: 'Connection refused - invalid client identifier',
                       3: 'Connection refused - server unavailable',
                       4: 'Connection refused - bad username or password',
                       5: 'Connection refused - not authorised'}
            log(errcode[rc])

    def on_message(client, userdata, msg):
        # MQTT 메시지를 수신했을 때 호출됩니다.
        raw_data = msg.payload.hex().upper()
        for k in range(0, len(raw_data), 16):
            data = raw_data[k:k + 16]
            if data == checksum(data) and data[:2] in statePrefix:
                name = statePrefix[data[:2]]
                collect_data[name].add(data)
                if dev_info[name].get('stateNUM'):
                    device_num[name] = max([device_num[name], int(data[int(dev_info[name]['stateNUM']) - 1])])
                else:
                    device_num[name] = 1

    mqtt_client = mqtt.Client('cwbs')
    mqtt_client.username_pw_set(config['mqtt_id'], config['mqtt_password'])
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect_async(config['mqtt_server'])
    mqtt_client.user_data_set(target_time)
    mqtt_client.loop_start()

    while time.time() < target_time:
        pass

    mqtt_client.loop_stop()

    log('다음의 데이터를 찾았습니다...')
    log('======================================')

    for name in collect_data:
        collect_data[name] = sorted(collect_data[name])
        dev_info[name]['Number'] = device_num[name]
        log('DEVICE: {}'.format(name))
        log('Packets: {}'.format(collect_data[name]))
        log('-------------------')
    log('======================================')
    log('기기의 숫자만 변경하였습니다. 상태 패킷은 직접 수정하여야 합니다.')
    with open(share_dir + '/cwbs_found_device.json', 'w', encoding='utf-8') as make_file:
        json.dump(dev_info, make_file, indent="\t")
        log('기기리스트 저장 중 : /share/cowbs_found_device.json')
        log('파일을 수정하고 싶은 경우 종료 후 다시 시작하세요.')
    return dev_info


def do_work(config, device_list):
    # 주어진 설정과 기기 목록을 사용하여 작업을 수행합니다.
    HA_TOPIC = config['mqtt_TOPIC']
    STATE_TOPIC = HA_TOPIC + '/{}/{}/state'

    debug = config['DEBUG']
    mqtt_log = config['mqtt_log']
    elfin_log = config['elfin_log']

    mqtt_client = mqtt.Client(HA_TOPIC)

    def pad(value):
        # 주어진 값을 두 자리 문자열로 변환합니다.
        value = int(value)
        return '0' + str(value) if value < 10 else str(value)

    def make_hex(k, input_hex, change):
        # 주어진 입력을 기반으로 16진수 명령을 생성합니다.
        if input_hex:
            try:
                change = int(change)
                input_hex = f'{input_hex[:change - 1]}{int(input_hex[change - 1]) + k}{input_hex[change:]}'
            except:
                pass
        return checksum(input_hex)

    def make_hex_temp(k, curTemp, setTemp, state):
        # 온도 조절기 명령을 위한 16진수 문자열을 생성합니다.
        if state == 'OFF' or state == 'ON' or state == 'CHANGE':
            tmp_hex = device_list['Thermo'].get('command' + state)
            change = device_list['Thermo'].get('commandNUM')
            tmp_hex = make_hex(k, tmp_hex, change)
            if state == 'CHANGE':
                setT = pad(setTemp)
                chaTnum = OPTION['Thermo'].get('chaTemp')
                tmp_hex = tmp_hex[:chaTnum - 1] + setT + tmp_hex[chaTnum + 1:]
            return checksum(tmp_hex)
        else:
            tmp_hex = device_list['Thermo'].get(state)
            change = device_list['Thermo'].get('stateNUM')
            tmp_hex = make_hex(k, tmp_hex, change)
            setT = pad(setTemp)
            curT = pad(curTemp)
            curTnum = OPTION['Thermo'].get('curTemp')
            setTnum = OPTION['Thermo'].get('setTemp')
            tmp_hex = tmp_hex[:setTnum - 1] + setT + tmp_hex[setTnum + 1:]
            tmp_hex = tmp_hex[:curTnum - 1] + curT + tmp_hex[curTnum + 1:]
            if state == 'stateOFF':
                return checksum(tmp_hex)
            elif state == 'stateON':
                tmp_hex2 = tmp_hex[:3] + str(3) + tmp_hex[4:]
                return [checksum(tmp_hex), checksum(tmp_hex2)]
            else:
                return None

    def make_device_info(dev_name):
        # 주어진 기기 이름에 대한 정보를 생성합니다.
        num = device_list[dev_name].get('Number', 0)
        if num > 0:
            arr = [ {cmd + onoff: make_hex(k, device_list[dev_name].get(cmd + onoff), device_list[dev_name].get(cmd + 'NUM'))
                           for cmd in ['command', 'state'] for onoff in ['ON', 'OFF']} for k in range(num) ]
            if dev_name == 'fan':
                tmp_hex = arr[0]['stateON']
                change = device_list[dev_name].get('speedNUM')
                arr[0]['stateON'] = [make_hex(k, tmp_hex, change) for k in range(3)]
                tmp_hex = device_list[dev_name].get('commandCHANGE')
                arr[0]['CHANGE'] = [make_hex(k, tmp_hex, change) for k in range(3)]

            return {'type': device_list[dev_name]['type'], 'list': arr}
        else:
            return None

    DEVICE_LISTS = {}
    for name in device_list:
        device_info = make_device_info(name)
        if device_info:
            DEVICE_LISTS[name] = device_info

    prefix_list = {}
    log('----------------------')
    log('등록된 기기 목록 DEVICE_LISTS..')
    log('----------------------')
    for name in DEVICE_LISTS:
        state = DEVICE_LISTS[name]['list'][0].get('stateON')
        if state:
            prefix = state[0][:2] if isinstance(state, list) else state[:2]
            prefix_list[prefix] = name
        log(f'{name}: {DEVICE_LISTS[name]["type"]}')
        log(f' >>>> {DEVICE_LISTS[name]["list"]}')
    log('----------------------')

    HOMESTATE = {}
    QUEUE = []
    COLLECTDATA = {'data': set(), 'EVtime': time.time(), 'LastRecv': time.time_ns()}

    async def recv_from_HA(topics, value):
        # Home Assistant로부터 명령을 수신하여 처리합니다.
        if mqtt_log:
            log('[LOG] HA ->> : {} -> {}'.format('/'.join(topics), value))

        device = ''.join(re.findall('[a-zA-Z]', topics[1]))

        if device in DEVICE_LISTS:
            key = topics[1] + topics[2]
            idx = int(''.join(re.findall('\d', topics[1])))
            value = 'ON' if value == 'heat' else value.upper()

            if device == 'Thermo':
                curTemp = HOMESTATE.get(topics[1] + 'curTemp')
                setTemp = HOMESTATE.get(topics[1] + 'setTemp')
                if topics[2] == 'power':
                    sendcmd = make_hex_temp(idx - 1, curTemp, setTemp, value)
                    recvcmd = [make_hex_temp(idx - 1, curTemp, setTemp, 'state' + value)]
                    if sendcmd:
                        QUEUE.append({'sendcmd': sendcmd, 'recvcmd': recvcmd, 'count': 0})
                        if debug:
                            log('[DEBUG] Queued ::: sendcmd: {}, recvcmd: {}'.format(sendcmd, recvcmd))
                elif topics[2] == 'setTemp':
                    value = int(float(value))
                    if value == int(setTemp):
                        if debug:
                            log('[DEBUG] {} is already set: {}'.format(topics[1], value))
                    else:
                        setTemp = value
                        sendcmd = make_hex_temp(idx - 1, curTemp, setTemp, 'CHANGE')
                        recvcmd = [make_hex_temp(idx - 1, curTemp, setTemp, 'stateON')]
                        if sendcmd:
                            QUEUE.append({'sendcmd': sendcmd, 'recvcmd': recvcmd, 'count': 0})
                            if debug:
                                log('[DEBUG] Queued ::: sendcmd: {}, recvcmd: {}'.format(sendcmd, recvcmd))

            elif device == 'Fan':
                if topics[2] == 'power':
                    sendcmd = DEVICE_LISTS[device]['list'][idx-1].get('command' + value)
                    recvcmd = DEVICE_LISTS[device]['list'][idx-1].get('state' + value) if value == 'ON' else [
                        DEVICE_LISTS[device]['list'][idx-1].get('state' + value)]
                    QUEUE.append({'sendcmd': sendcmd, 'recvcmd': recvcmd, 'count': 0})
                    if debug:
                        log('[DEBUG] Queued ::: sendcmd: {}, recvcmd: {}'.format(sendcmd, recvcmd))
                elif topics[2] == 'speed':
                    speed_list = ['LOW', 'MEDIUM', 'HIGH']
                    if value in speed_list:
                        index = speed_list.index(value)
                        sendcmd = DEVICE_LISTS[device]['list'][idx-1]['CHANGE'][index]
                        recvcmd = [DEVICE_LISTS[device]['list'][idx-1]['stateON'][index]]
                        QUEUE.append({'sendcmd': sendcmd, 'recvcmd': recvcmd, 'count': 0})
                        if debug:
                            log('[DEBUG] Queued ::: sendcmd: {}, recvcmd: {}'.format(sendcmd, recvcmd))

            else:
                sendcmd = DEVICE_LISTS[device]['list'][idx-1].get('command' + value)
                if sendcmd:
                    recvcmd = [DEVICE_LISTS[device]['list'][idx-1].get('state' + value, 'NULL')]
                    QUEUE.append({'sendcmd': sendcmd, 'recvcmd': recvcmd, 'count': 0})
                    if debug:
                        log('[DEBUG] Queued ::: sendcmd: {}, recvcmd: {}'.format(sendcmd, recvcmd))
                else:
                    if debug:
                        log('[DEBUG] There is no command for {}'.format('/'.join(topics)))
        else:
            if debug:
                log('[DEBUG] There is no command for {}'.format('/'.join(topics)))

    async def slice_raw_data(raw_data):
        # 수신된 원시 데이터를 16바이트 단위로 나누어 처리합니다.
        if elfin_log:
            log('[SIGNAL] receved: {}'.format(raw_data))

        cors = [recv_from_elfin(raw_data[k:k + 16]) for k in range(0, len(raw_data), 16) if raw_data[k:k + 16] == checksum(raw_data[k:k + 16])]
        await asyncio.gather(*cors)

    async def recv_from_elfin(data):
        # Elfin 장치로부터 수신된 데이터를 처리합니다.
        COLLECTDATA['LastRecv'] = time.time_ns()
        if data:
            if HOMESTATE.get('EV1power') == 'ON':
                if COLLECTDATA['EVtime'] < time.time():
                    await update_state('EV', 0, 'OFF')
            for que in QUEUE:
                if data in que['recvcmd']:
                    QUEUE.remove(que)
                    if debug:
                        log('[DEBUG] Found matched hex: {}. Delete a queue: {}'.format(data, que))
                    break

            device_name = prefix_list.get(data[:2])
            if device_name == 'Thermo':
                curTnum = device_list['Thermo']['curTemp']
                setTnum = device_list['Thermo']['setTemp']
                curT = data[curTnum - 1:curTnum + 1]
                setT = data[setTnum - 1:setTnum + 1]
                onoffNUM = device_list['Thermo']['stateONOFFNUM']
                staNUM = device_list['Thermo']['stateNUM']
                index = int(data[staNUM - 1]) - 1
                onoff = 'ON' if int(data[onoffNUM - 1]) > 0 else 'OFF'
                await update_state(device_name, index, onoff)
                await update_temperature(index, curT, setT)
            elif device_name == 'Fan':
                if data in DEVICE_LISTS['Fan']['list'][0]['stateON']:
                    speed = DEVICE_LISTS['Fan']['list'][0]['stateON'].index(data)
                    await update_state('Fan', 0, 'ON')
                    await update_fan(0, speed)
                elif data == DEVICE_LISTS['Fan']['list'][0]['stateOFF']:
                    await update_state('Fan', 0, 'OFF')
                else:
                    log(f"[WARNING] <{device_name}> 기기의 신호를 찾음: {data}")
                    log('[WARNING] 기기목록에 등록되지 않는 패킷입니다. JSON 파일을 확인하세요..')
            elif device_name == 'Outlet':
                staNUM = device_list['Outlet']['stateNUM']
                index = int(data[staNUM - 1]) - 1

                for onoff in ['OFF', 'ON']:
                    if data.startswith(DEVICE_LISTS[device_name]['list'][index]['state' + onoff][:8]):
                        await update_state(device_name, index, onoff)
                        if onoff == 'ON':
                            await update_outlet_value(index, data[10:14])
                        else:
                            await update_outlet_value(index, 0)
            elif device_name == 'EV':
                val = int(data[4:6], 16)
                await update_state('EV', 0, 'ON')
                await update_ev_value(0, val)
                COLLECTDATA['EVtime'] = time.time() + 3
            else:
                num = len(DEVICE_LISTS[device_name]['list'])
                state = [DEVICE_LISTS[device_name]['list'][k]['stateOFF'] for k in range(num)] + [
                    DEVICE_LISTS[device_name]['list'][k]['stateON'] for k in range(num)]
                if data in state:
                    index = state.index(data)
                    onoff, index = ['OFF', index] if index < num else ['ON', index - num]
                    await update_state(device_name, index, onoff)
                else:
                    log(f"[WARNING] <{device_name}> 기기의 신호를 찾음: {data}")
                    log('[WARNING] 기기목록에 등록되지 않는 패킷입니다. JSON 파일을 확인하세요..')

    async def update_state(device, idx, onoff):
        # 기기의 상태를 업데이트하고 MQTT로 전송합니다.
        state = 'power'
        deviceID = device + str(idx + 1)
        key = deviceID + state

        topic = STATE_TOPIC.format(deviceID, state)
        mqtt_client.publish(topic, onoff.encode())
        if mqtt_log:
            log('[LOG] ->> HA : {} >> {}'.format(topic, onoff))
        return

    async def update_fan(idx, onoff):
        # 팬의 상태를 업데이트하고 MQTT로 전송합니다.
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
        topic = STATE_TOPIC.format(deviceID, state)
        mqtt_client.publish(topic, onoff.encode())
        if mqtt_log:
            log('[LOG] ->> HA : {} >> {}'.format(topic, onoff))
        return

    async def update_temperature(idx, curTemp, setTemp):
        # 온도 조절기의 현재 온도와 설정 온도를 업데이트하고 MQTT로 전송합니다.
        deviceID = 'Thermo' + str(idx + 1)
        temperature = {'curTemp': pad(curTemp), 'setTemp': pad(setTemp)}
        for state in temperature:
            key = deviceID + state
            val = temperature[state]
            topic = STATE_TOPIC.format(deviceID, state)
            mqtt_client.publish(topic, val.encode())
            HOMESTATE[deviceID + 'curTemp'] = curTemp
            HOMESTATE[deviceID + 'setTemp'] = setTemp
            if mqtt_log:
                log('[LOG] ->> HA : {} -> {}'.format(topic, val))
        return

    async def update_outlet_value(idx, val):
        # 콘센트의 전력 소비량을 업데이트하고 MQTT로 전송합니다.
        deviceID = 'Outlet' + str(idx + 1)
        try:
            val = '%.1f' % float(int(val) / 10)
            topic = STATE_TOPIC.format(deviceID, 'watt')
            mqtt_client.publish(topic, val.encode())
            if debug:
                log('[LOG] ->> HA : {} -> {}'.format(topic, val))
        except:
            pass

    async def update_ev_value(idx, val):
        # EV의 층 정보를 업데이트하고 MQTT로 전송합니다.
        deviceID = 'EV' + str(idx + 1)
        try:
            BF = device_info['EV']['BasementFloor']
            val = str(int(val) - BF + 1) if val >= BF else 'B' + str(BF - int(val))
            topic = STATE_TOPIC.format(deviceID, 'floor')
            mqtt_client.publish(topic, val.encode())
            if debug:
                log('[LOG] ->> HA : {} -> {}'.format(topic, val))
        except:
            pass

    def on_connect(client, userdata, flags, rc):
        # MQTT 브로커에 연결되었을 때 호출됩니다.
        if rc == 0:
            log("MQTT 접속 완료..")
            client.subscribe([(HA_TOPIC + '/#', 0), (ELFIN_TOPIC + '/recv', 0), (ELFIN_TOPIC + '/send', 1)])
            if 'EV' in DEVICE_LISTS:
                asyncio.run(update_state('EV', 0, 'OFF'))
            # MQTT discover
            for device in DEVICE_LISTS:
                for idx in range(len(DEVICE_LISTS[device]['list'])):
                    config_topic = f'homeassistant/{DEVICE_LISTS[device]["type"]}/commax_{device.lower()}{idx + 1}/config'
                    if DEVICE_LISTS[device]["type"] == "climate":
                        payload = {
                            "device": {
                                "identifiers": "cwbs",
                                "name": "코맥스 월패드 by Saram",
                                "manufacturer": "commax",
                            },
                            "device_class": DEVICE_LISTS[device]["type"],
                            "name": f'{device}{idx+1}',
                            "object_id": f'cwbs_{device.lower()}{idx + 1}',
                            "unique_id": f'cwbs_{device.lower()}{idx + 1}',
                            "entity_category": 'config',
                            "mode_cmd_t": f"{HA_TOPIC}/{device}{idx+1}/power/command",
                            "mode_stat_t": f"{HA_TOPIC}/{device}{idx+1}/power/state",
                            "temp_cmd_t": f"{HA_TOPIC}/{device}{idx+1}/setTemp/command",
                            "temp_stat_t": f"{HA_TOPIC}/{device}{idx+1}/setTemp/state",
                            "curr_temp_t": f"{HA_TOPIC}/{device}{idx+1}/curTemp/state",
                            "min_temp":"10",
                            "max_temp":"30",
                            "temp_step":"1",
                            "modes":["off", "heat"],
                            "mode_state_template": "{% set modes = {'OFF': 'off', 'ON': 'heat'} %} {{modes[value] if value in modes.keys() else 'off'}}"
                                }
                    else:
                        payload = {
                            "device": {
                                "identifiers": "cwbs",
                                "name": "코맥스 월패드 by Saram",
                                "manufacturer": "commax",
                            },
                            "~": f'{HA_TOPIC}/{device}{idx + 1}/power',
                            "device_class": DEVICE_LISTS[device]["type"],
                            "name": f'{device}{idx+1}',
                            "object_id": f'cwbs_{device.lower()}{idx + 1}',
                            "unique_id": f'cwbs_{device.lower()}{idx + 1}',
                            "cmd_t": "~/command",
                            "stat_t": "~/state"}
                        if device == "Outlet":
                            payload["device_class"] = 'outlet'
                            payload["entity_category"] = 'diagnostic'

                    log(config_topic)
                    log(json.dumps(payload))
                    mqtt_client.publish(config_topic, json.dumps(payload))
                    if device == "Outlet":
                        config_topic = f'homeassistant/sensor/cwbs_{device}{idx + 1}_watt/config'
                        payload = {
                            "device": {
                                "identifiers": "cwbs",
                                "name": "코맥스 월패드 by Saram",
                                "manufacturer": "commax",
                            },
                            "device_class": 'energy',
                            "name": f'{device}{idx + 1} Watt',
                            "object_id": f'cwbs_{device.lower()}{idx + 1}_watt',
                            "unique_id": f'cwbs_{device.lower()}{idx + 1}_watt',
                            "entity_category": 'diagnostic',
                            "stat_t": f'{HA_TOPIC}/{device}{idx + 1}/watt/state',
                            "unit_of_measurement": "W"
                        }
                        log(config_topic)
                        log(json.dumps(payload))
                        mqtt_client.publish(config_topic, json.dumps(payload))

        else:
            errcode = {1: 'Connection refused - incorrect protocol version',
                       2: 'Connection refused - invalid client identifier',
                       3: 'Connection refused - server unavailable',
                       4: 'Connection refused - bad username or password',
                       5: 'Connection refused - not authorised'}
            log(errcode[rc])

    def on_message(client, userdata, msg):
        # MQTT 메시지를 수신했을 때 호출됩니다.
        topics = msg.topic.split('/')
        try:
            if topics[0] == HA_TOPIC and topics[-1] == 'command':
                asyncio.run(recv_from_HA(topics, msg.payload.decode('utf-8')))
            elif topics[0] == ELFIN_TOPIC and topics[-1] == 'recv':
                asyncio.run(slice_raw_data(msg.payload.hex().upper()))
        except:
            pass

    def log_error(err):
        # 에러 메시지를 로그에 출력합니다.
        log(f'[ERROR] {err}')

    def log_warning(message):
        # 경고 메시지를 로그에 출력합니다.
        log(f'[WARNING] {message}')

    def log_debug(message, debug):
        # 디버그 메시지를 로그에 출력합니다. 디버그 모드가 활성화된 경우에만 출력됩니다.
        if debug:
            log(f'[DEBUG] {message}')

    def log_signal(message, elfin_log):
        # 신호 관련 메시지를 로그에 출력합니다. Elfin 로그가 활성화된 경우에만 출력됩니다.
        if elfin_log:
            log(f'[SIGNAL] {message}')

    def publish_mqtt(topic, message, mqtt_client, mqtt_log):
        # MQTT 메시지를 주어진 토픽으로 발행합니다. MQTT 로그가 활성화된 경우 로그에 출력합니다.
        mqtt_client.publish(topic, message.encode())
        if mqtt_log:
            log(f'[LOG] ->> HA : {topic} >> {message}')

    async def handle_elfin_reboot(elfin_reboot_interval, config, mqtt_client):
        # Elfin 장치를 주기적으로 재부팅하고, 큐를 처리합니다.
        while True:
            try:
                if time.time_ns() - COLLECTDATA['LastRecv'] > elfin_reboot_interval * 1e9:
                    log_warning(f'{elfin_reboot_interval}초간 신호를 받지 못했습니다. ew11 기기를 재시작합니다.')
                    await reboot_elfin_device(config)
                    COLLECTDATA['LastRecv'] = time.time_ns()
                elif time.time_ns() - COLLECTDATA['LastRecv'] > 1e8:
                    await process_queue(mqtt_client)
            except Exception as err:
                log_error(f'send_to_elfin(): {err}')
                return True
            await asyncio.sleep(0.01)

    async def reboot_elfin_device(config):
        # Elfin 장치를 재부팅합니다.
        try:
            ew11 = telnetlib.Telnet(config['elfin_server'])
            ew11.read_until(b"login:")
            ew11.write(config['elfin_id'].encode('utf-8') + b'\n')
            ew11.read_until(b"password:")
            ew11.write(config['elfin_password'].encode('utf-8') + b'\n')
            ew11.write('Restart'.encode('utf-8') + b'\n')
            await asyncio.sleep(10)
        except:
            log_warning('기기 재시작 오류! 기기 상태를 확인하세요.')

    async def process_queue(mqtt_client):
        # 큐에 있는 명령을 처리하고, 필요시 재시도합니다.
        if QUEUE:
            send_data = QUEUE.pop(0)
            log_signal(f'신호 전송: {send_data}', elfin_log)
            mqtt_client.publish(ELFIN_TOPIC + '/send', bytes.fromhex(send_data['sendcmd']))
            if send_data['count'] < 5:
                send_data['count'] += 1
                QUEUE.append(send_data)
            else:
                log_signal(f'Send over 5 times. Send Failure. Delete a queue: {send_data}', elfin_log)

    mqtt_client.username_pw_set(config['mqtt_id'], config['mqtt_password'])
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect_async(config['mqtt_server'])
    mqtt_client.loop_start()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(handle_elfin_reboot(config.get('elfin_reboot_interval', 10), config, mqtt_client))
    loop.close()
    mqtt_client.loop_stop()


if __name__ == '__main__':
    # 프로그램의 진입점입니다. 설정 파일을 로드하고 작업을 시작합니다.
    log("'Commax Wallpad by Saram'을 시작합니다.")
    with open('/data/options.json') as file:
        CONFIG = json.load(file)
    try:
        with open(share_dir + '/cwbs_found_device.json') as file:
            log('기기 정보 파일을 찾음: /share/cwbs_found_device.json')
            OPTION = json.load(file)
    except IOError:
        log('기기 정보 파일이 없습니다. mqtt에 접속하여 기기를 찾습니다.')
        OPTION = find_device(CONFIG)

    while True:
        do_work(CONFIG, OPTION)
