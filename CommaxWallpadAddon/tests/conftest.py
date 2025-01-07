import pytest
import sys
import os

# apps 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def config():
    """테스트용 설정을 제공하는 fixture"""
    return {
        'mqtt_TOPIC': 'test/wallpad',
        'mqtt_server': 'localhost',
        'mqtt_id': 'test',
        'mqtt_password': 'test',
        'DEBUG': True,
        'elfin_log': True,
        'mqtt_log': True,
        'min_receive_count': 3,
        'climate_min_temp': 5,
        'climate_max_temp': 40
    }

@pytest.fixture
def logger():
    """테스트용 로거를 제공하는 fixture"""
    from apps.logger import Logger
    return Logger(debug=True, elfin_log=True, mqtt_log=True)

@pytest.fixture
def controller(config, logger):
    """테스트용 WallpadController를 제공하는 fixture"""
    from apps.main import WallpadController
    return WallpadController(config, logger) 