import unittest
from unittest.mock import Mock, patch, mock_open
import json
import asyncio
import sys
import os
import yaml
import pytest

# apps 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apps.main import WallpadController
from apps.logger import Logger
from apps.main import CollectData, ExpectedStatePacket

@pytest.fixture
def config():
    """테스트용 설정을 제공하는 fixture"""
    # 테스트용 패킷 구조 파일 경로 설정
    packet_file = os.path.join(os.path.dirname(__file__), 'fixtures', 'packet_structures_commax.yaml')
    
    return {
        'DEBUG': False,
        'mqtt_log': False,
        'elfin_log': False,
        'vendor': 'commax',
        'queue_interval_in_second': 0.1,
        'max_send_count': 15,
        'min_receive_count': 1,
        'climate_min_temp': 5,
        'climate_max_temp': 40,
        'mqtt': {
            'mqtt_server': '192.168.0.39',
            'mqtt_id': 'my_user',
            'mqtt_password': 'm1o@s#quitto'
        },
        'mqtt_TOPIC': 'commax',
        'elfin': {
            'use_auto_reboot': True,
            'elfin_server': '192.168.0.38',
            'elfin_id': 'admin',
            'elfin_password': 'admin',
            'elfin_reboot_interval': 60
        },
        'log': {
            'DEBUG': True,
            'elfin_log': True,
            'mqtt_log': True
        },
        'command_settings': {
            'queue_interval_in_second': 0.1,
            'max_send_count': 15,
            'min_receive_count': 1
        },
        'climate_settings': {
            'min_temp': 5,
            'max_temp': 40
        },
        'packet_file': packet_file  # 테스트용 패킷 파일 경로
    }

@pytest.fixture
def controller(config):
    """테스트용 컨트롤러를 제공하는 fixture"""
    logger = Logger(debug=True, elfin_log=True, mqtt_log=True)
    controller = WallpadController(config, logger)
    
    # 파일이 존재하는지 확인
    if not os.path.exists(config['packet_file']):
        raise FileNotFoundError(f"패킷 구조 파일이 존재하지 않습니다: {config['packet_file']}")
        
    # 패킷 구조 로드
    controller.load_devices_and_packets_structures()
    return controller

def test_load_devices_and_packets_structures(controller):
    """패킷 구조 파일 로딩 테스트"""
    # DEVICE_STRUCTURE가 None이 아닌지 확인
    assert controller.DEVICE_STRUCTURE is not None, "DEVICE_STRUCTURE가 None입니다"
    
    # 모든 기기에 대해 fieldPositions이 생성되었는지 확인
    for device_name, device in controller.DEVICE_STRUCTURE.items():
        for packet_type in ['command', 'state']:
            if packet_type in device:
                # fieldPositions이 있는지 확인
                assert 'fieldPositions' in device[packet_type], \
                    f"{device_name}의 {packet_type}에 fieldPositions이 없습니다"
                
                # structure의 모든 필드가 fieldPositions에 있는지 확인
                structure = device[packet_type]['structure']
                field_positions = device[packet_type]['fieldPositions']
                
                for pos, field in structure.items():
                    field_name = field['name']
                    if field_name != 'empty' and field_name != 'checksum':
                        assert field_name in field_positions, \
                            f"{device_name}의 {packet_type}에서 {field_name}이 fieldPositions에 없습니다"
                        assert field_positions[field_name] == pos, \
                            f"{device_name}의 {packet_type}에서 {field_name}의 위치가 잘못되었습니다"

@pytest.mark.asyncio
async def test_process_ha_command(controller):
    """홈어시스턴트 명령 처리 테스트"""
    # 테스트 토픽과 값
    topics = ['commax', 'Thermo1', 'curTemp', 'command']
    value = '24'
    
    # process_ha_command 호출
    await controller.process_ha_command(topics, value)
    
    # QUEUE에 명령이 추가되었는지 확인
    assert len(controller.QUEUE) > 0

@pytest.mark.asyncio
async def test_process_ha_command_light(controller):
    """조명 명령 패킷 테스트"""
    # 조명 켜기
    topics = ['commax', 'Light1', 'power', 'command'] 
    value = 'ON'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '3101010000000033'
    
    # 조명 끄기
    value = 'OFF'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '3101000000000032'

@pytest.mark.asyncio
async def test_process_ha_command_thermo(controller):
    """온도조절기 명령 패킷 테스트"""
    # 온도조절기 켜기
    topics = ['commax', 'Thermo1', 'power', 'command']
    value = 'heat'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '040104810000008A'

    # 온도조절기 끄기
    value = 'off'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '0401040000000009'

    # 온도 설정
    topics = ['commax', 'Thermo1', 'setTemp', 'command']
    value = '24'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '040103240000002C'

@pytest.mark.asyncio
async def test_process_ha_command_fan(controller):
    """환기장치 명령 패킷 테스트"""
    # 전원 켜기
    topics = ['commax', 'Fan1', 'power', 'command']
    value = 'ON'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '780101040000007E'

    # 전원 끄기
    value = 'off'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '780101000000007A'

    # 속도 low
    topics = ['commax', 'Fan1', 'speed', 'command']
    value = 'low'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '780102010000007C'

    # 속도 medium
    value = 'medium'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '780102020000007D'

    # 속도 high
    value = 'high'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '780102030000007E'

@pytest.mark.asyncio
async def test_process_ha_command_gas(controller):
    """가스밸브 명령 패킷 테스트"""
    # 가스밸브 차단
    topics = ['commax', 'Gas1', 'power', 'command']
    value = 'OFF'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '1101800000000092'

@pytest.mark.asyncio
async def test_process_ha_command_outlet(controller):
    """콘센트 명령 패킷 테스트"""
    # 전원 켜기
    topics = ['commax', 'Outlet1', 'power', 'command']
    value = 'ON'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '7A0101010000007D'

    # 전원 끄기 
    value = 'OFF'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '7A0101000000007C'

@pytest.mark.asyncio
async def test_process_ha_command_lightbreaker(controller):
    """조명차단기 명령 패킷 테스트"""
    # 전원 켜기
    topics = ['commax', 'LightBreaker1', 'power', 'command']
    value = 'ON'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '2201010100000025'

    # 전원 끄기
    value = 'off'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == '2201010000000024'

@pytest.mark.asyncio
async def test_process_ha_command_ev(controller):
    """EV 호출 명령 패킷 테스트"""
    # 전원 켜기
    topics = ['commax', 'EV1', 'power', 'command']
    value = 'ON'
    await controller.process_ha_command(topics, value)
    assert controller.QUEUE[-1]['sendcmd'] == 'A0010101081500C0'

def test_find_device_with_light(controller):
    """조명 기기 검색 테스트"""
    # 조명 상태 패킷 (1번 조명 켜짐)
    light_packet = "B0010100000000B2"
    controller.COLLECTDATA['recv_data'] = [light_packet]
    
    # find_device 실행
    result = controller.find_device()
    
    # 결과 검증
    assert 'Light' in result
    assert result['Light']['count'] == 1
    assert result['Light']['type'] == 'light'

def test_find_device_with_thermo(controller):
    """온도조절기 검색 테스트"""
    # 온도조절기 상태 패킷 (2번 온도조절기, 전원 켜짐, 현재온도 24도, 설정온도 20도)
    thermo_packet = "8281022420000049"
    controller.COLLECTDATA['recv_data'] = [thermo_packet]
    
    # find_device 실행
    result = controller.find_device()
    
    # 결과 검증
    assert 'Thermo' in result
    assert result['Thermo']['count'] == 2
    assert result['Thermo']['type'] == 'climate'

def test_find_device_with_multiple_devices(controller):
    """여러 기기 동시 검색 테스트"""
    # 여러 기기의 상태 패킷
    packets = [
        "B0010100000000B2",  # 1번 조명 켜짐
        "B0010200000000B3",  # 2번 조명 켜짐
        "828301242000004A",  # 1번 온도조절기
        "8281022420000049",  # 2번 온도조절기
        "F6000101000000F8",   # 1번 환기장치
        "9080800000000090",   # 가스차단기
        "F70101810000FFFF",  # 잘못된 체크섬
        "F60101182425FFFF",  # 잘못된 체크섬
    ]
    controller.COLLECTDATA['recv_data'] = packets
    
    # find_device 실행
    result = controller.find_device()
    
    # 결과 검증
    assert 'Light' in result
    assert result['Light']['count'] == 2
    
    assert 'Thermo' in result
    assert result['Thermo']['count'] == 2
    
    assert 'Fan' in result
    assert result['Fan']['count'] == 1
    
    assert 'Gas' in result
    assert result['Gas']['count'] == 1

def test_find_device_with_invalid_packets(controller):
    """잘못된 패킷으로 기기 검색 테스트"""
    # 잘못된 체크섬을 가진 패킷들
    invalid_packets = [
        "F70101810000FFFF",  # 잘못된 체크섬
        "F60101182425FFFF",  # 잘못된 체크섬
    ]
    controller.COLLECTDATA['recv_data'] = invalid_packets
    
    # find_device 실행
    result = controller.find_device()
    
    # 결과 검증 - 빈 딕셔너리여야 함
    assert result == {}

def test_checksum_generation():
    """체크섬 생성 테스트"""
    from apps.utils import checksum
    # 테스트 데이터
    test_data = "82830124200000"
    expected_checksum = "828301242000004A"
    
    result = checksum(test_data)
    assert result == expected_checksum

def test_byte_to_hex_str():
    """바이트를 16진수 문자열로 변환하는 테스트"""
    from apps.utils import byte_to_hex_str
    test_byte = 0x82
    expected_hex = "82"
    
    result = byte_to_hex_str(test_byte)
    assert result == expected_hex

@patch('paho.mqtt.client.Client')
def test_setup_mqtt(mock_mqtt_client, controller, config):
    """MQTT 클라이언트 설정 테스트"""
    # MQTT 클라이언트 설정
    client = controller.setup_mqtt('test_client')
    
    # username_pw_set이 호출되었는지 확인
    mock_mqtt_client.return_value.username_pw_set.assert_called_once_with(
        config['mqtt']['mqtt_id'],
        config['mqtt']['mqtt_password']
    )

@patch('paho.mqtt.client.Client')
def test_publish_mqtt(mock_mqtt_client, controller):
    """MQTT 메시지 발행 테스트"""
    controller.mqtt_client = mock_mqtt_client
    
    # 테스트 토픽과 값
    test_topic = "test/topic"
    test_value = "ON"
    
    # publish_mqtt 호출
    controller.publish_mqtt(test_topic, test_value)
    
    # publish가 호출되었는지 확인
    mock_mqtt_client.publish.assert_called_once()

def test_generate_expected_state_packet(controller):
    """예상 상태 패킷 생성 테스트"""
    # 테스트 명령 패킷 (조명 1번 켜기 명령)
    command_str = "3101010000000033"
    
    # generate_expected_state_packet 호출
    result = controller.generate_expected_state_packet(command_str)
    
    # 결과가 None이 아닌지 확인
    assert result is not None, "예상 상태 패킷이 생성되지 않았습니다"
    
    # ExpectedStatePacket의 필수 필드들이 있는지 확인
    assert 'required_bytes' in result, "required_bytes 필드가 없습니다"
    assert 'possible_values' in result, "possible_values 필드가 없습니다"
    
    # 필드 타입 확인
    assert isinstance(result['required_bytes'], list), "required_bytes가 리스트가 아닙니다"
    assert isinstance(result['possible_values'], list), "possible_values가 리스트가 아닙니다"
    
    # 조명 상태 패킷의 경우 예상되는 값들 확인
    assert 0 in result['required_bytes'], "헤더 위치(0)가 required_bytes에 없습니다"
    assert 1 in result['required_bytes'], "power 위치(1)가 required_bytes에 없습니다"
    assert 2 in result['required_bytes'], "deviceId 위치(2)가 required_bytes에 없습니다"
    
    # possible_values 길이 확인
    assert len(result['possible_values']) == 7, "possible_values의 길이가 7이 아닙니다"

def test_load_devices_and_packets_structures_custom_vendor(config):
    """커스텀 벤더 설정 테스트"""
    # vendor를 custom으로 설정
    config['vendor'] = 'custom'
    logger = Logger(debug=True, elfin_log=True, mqtt_log=True)
    controller = WallpadController(config, logger)
    
    # 실제 기본 패킷 구조 파일 읽기
    packet_file = os.path.join(os.path.dirname(__file__), 'fixtures', 'packet_structures_commax.yaml')
    with open(packet_file, 'r', encoding='utf-8') as f:
        default_structure = yaml.safe_load(f)
    
    # custom 파일 경로에 대한 mock 설정
    custom_file_path = '/share/packet_structures_custom.yaml'
    m = mock_open()
    with patch('builtins.open', m) as mock_file:
        # FileNotFoundError를 한 번 발생시킨 후, 그 다음에는 정상적으로 파일을 읽도록 설정
        mock_file.side_effect = [
            FileNotFoundError(),  # 첫 번째 호출에서는 파일이 없음
            mock_open(read_data=yaml.dump(default_structure)).return_value  # 두 번째 호출에서는 파일 읽기 성공
        ]
        
        # load_devices_and_packets_structures 호출
        with patch('os.makedirs') as mock_makedirs, \
             patch('shutil.copy') as mock_copy:
            controller.load_devices_and_packets_structures()
            
            # 디렉토리 생성이 시도되었는지 확인
            mock_makedirs.assert_called_once()
            
            # 파일 복사가 시도되었는지 확인
            mock_copy.assert_called_once()
    
    # DEVICE_STRUCTURE가 None이 아니어야 함
    assert controller.DEVICE_STRUCTURE is not None
    
    # Light 기기가 있는지 확인
    assert 'Light' in controller.DEVICE_STRUCTURE
    assert controller.DEVICE_STRUCTURE['Light']['type'] == 'light'
    
@pytest.mark.asyncio
async def test_process_elfin_data_outlet(controller):
    """콘센트 상태 패킷 처리 테스트"""
    # 콘센트 상태 패킷 (1번 콘센트, 전원 ON, 전력 10.3W)
    outlet_packet = "F901011100010310"
    
    # update_outlet 메서드를 mock으로 대체
    with patch.object(controller, 'update_outlet') as mock_update:
        # 패킷 처리
        await controller.process_elfin_data(outlet_packet)
        
        # update_outlet이 올바른 인자와 함께 호출되었는지 확인
        mock_update.assert_called_once_with(1, "ON", 103, None)