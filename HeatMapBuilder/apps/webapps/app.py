import logging
from logging.handlers import RotatingFileHandler
import os
import json
import time
from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
from typing import Optional, Dict, Any
from thermal_map import ThermalMapGenerator

app = Flask(__name__)


# 개발 환경 확인
IS_DEV = os.environ.get('FLASK_ENV') == 'development'
IS_LOCAL = os.environ.get('SUPERVISOR_TOKEN') is None

if IS_DEV:
    app.debug = True
    # 템플릿 자동 리로드
    app.jinja_env.auto_reload = True
    # 정적 파일 캐시 비활성화 
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# 캐시버스터
cache_buster = str(time.time())

# 로깅 설정
LOG_PATH = os.path.join(os.path.dirname(__file__), 'thermomap.log') if IS_LOCAL else '/data/thermomap.log'
handler = RotatingFileHandler(LOG_PATH, maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG if IS_DEV else logging.INFO)
    
# 설정 파일 경로
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'test_config.json') if IS_LOCAL else '/data/options.json'
MEDIA_PATH = os.path.join(os.path.dirname(__file__), 'media') if IS_LOCAL else '/media'
WALLS_CONFIG = os.path.join(os.path.dirname(__file__), 'media', 'walls.json') if IS_LOCAL else '/data/walls.json'
SENSORS_CONFIG = os.path.join(os.path.dirname(__file__), 'media', 'sensors.json') if IS_LOCAL else '/data/sensors.json'

# media 디렉토리가 없으면 생성
try:
    os.makedirs(MEDIA_PATH, exist_ok=True)
    app.logger.info(f"미디어 디렉토리 경로: {MEDIA_PATH}")
except Exception as e:
    app.logger.error(f"미디어 디렉토리 생성 실패: {str(e)}")

def load_mock_config():
    """mock 설정을 로드합니다."""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_mock_data():
    """개발 환경용 mock 데이터를 반환합니다."""
    config = load_mock_config()
    return config.get('mock_data', {})

def get_ha_api() -> Optional[Dict[str, Any]]:
    """Home Assistant API 설정을 가져옵니다."""
    if IS_LOCAL:
        return {
            'base_url': 'mock_url',
            'headers': {'Content-Type': 'application/json'}
        }
    supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
    return {
        'base_url': 'http://supervisor/core/api',
        'headers': {
            'Authorization': f'Bearer {supervisor_token}',
            'Content-Type': 'application/json'
        }
    }

def get_sensor_state(entity_id: str) -> Dict[str, Any]:
    """센서 상태를 가져옵니다."""
    try:
        if IS_LOCAL:
            mock_data = get_mock_data()
            for sensor in mock_data.get('temperature_sensors', []):
                if sensor['entity_id'] == entity_id:
                    return {
                        'entity_id': entity_id,
                        'state': sensor.get('state', '0'),
                        'attributes': sensor.get('attributes', {})
                    }
            app.logger.warning(f"Mock 센서 데이터를 찾을 수 없음: {entity_id}")
            return {'state': '20', 'entity_id': entity_id}  # 테스트를 위한 기본값
        
        api = get_ha_api()
        if not api:
            app.logger.error("Home Assistant API 설정을 가져올 수 없습니다")
            return {'state': '0', 'entity_id': entity_id}
        
        app.logger.info(f"센서 상태 조회 중: {entity_id}")
        response = requests.get(
            f"{api['base_url']}/states/{entity_id}",
            headers=api['headers']
        )
        return response.json()
    except Exception as e:
        app.logger.error(f"센서 상태 조회 실패: {str(e)}")
        return {'state': '0', 'entity_id': entity_id}

@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@app.route('/api/states')
def get_states():
    """상태 정보를 가져옵니다."""
    if IS_LOCAL:
        mock_data = get_mock_data()
        return jsonify(mock_data.get('temperature_sensors', []))
    
    api = get_ha_api()
    if not api:
        return jsonify([])
    
    response = requests.get(f"{api['base_url']}/states", headers=api['headers'])
    # 온도 센서만 필터링
    states = response.json()
    filtered_states = [
        state for state in states
        if state.get('attributes', {}).get('device_class') == 'temperature' and
           state.get('attributes', {}).get('state_class') == 'measurement'
    ]
    response._content = json.dumps(filtered_states).encode('utf-8')
    return jsonify(response.json())

@app.route('/api/save-walls', methods=['POST'])
def save_walls():
    """벽 설정을 저장합니다."""
    data = request.get_json() or {}
    
    # 벽 설정 저장
    with open(WALLS_CONFIG, 'w') as f:
        json.dump({
            'walls': data.get('walls', '')
        }, f)
    
    return jsonify({'status': 'success'})

@app.route('/api/save-sensors', methods=['POST'])
def save_sensors():
    """센서 위치를 저장합니다."""
    data = request.get_json() or {}
    
    # 센서 설정 저장
    with open(SENSORS_CONFIG, 'w') as f:
        json.dump({
            'sensors': data.get('sensors', [])
        }, f)
    
    return jsonify({'status': 'success'})

@app.route('/api/load-config')
def load_heatmap_config():
    """저장된 히트맵 설정을 불러옵니다."""
    try:
        config = {
            'floorplan': None,
            'walls': '',
            'sensors': []
        }

        # 플로어플랜 이미지 로드
        floorplan_path = os.path.join(MEDIA_PATH, 'floorplan.png')
        if os.path.exists(floorplan_path):
            with open(floorplan_path, 'rb') as f:
                import base64
                image_data = base64.b64encode(f.read()).decode('utf-8')
                config['floorplan'] = f'data:image/png;base64,{image_data}'

        # 벽 설정 로드
        if os.path.exists(WALLS_CONFIG):
            with open(WALLS_CONFIG, 'r') as f:
                walls_data = json.load(f)
                config['walls'] = walls_data.get('walls', '')

        # 센서 설정 로드
        if os.path.exists(SENSORS_CONFIG):
            with open(SENSORS_CONFIG, 'r') as f:
                sensors_data = json.load(f)
                config['sensors'] = sensors_data.get('sensors', [])

        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/media/<path:filename>')
def serve_media(filename):
    """미디어 파일을 제공합니다."""
    app.logger.debug(f"미디어 파일 요청: {filename}, 경로: {MEDIA_PATH}")
    if os.path.exists(os.path.join(MEDIA_PATH, filename)):
        return send_from_directory(MEDIA_PATH, filename)
    else:
        app.logger.error(f"파일을 찾을 수 없음: {filename}")
        return "File not found", 404

@app.route('/api/generate-map', methods=['POST'])
def generate_map():
    """온도 데이터를 기반으로 열지도를 생성합니다."""
    try:
        app.logger.info("열지도 생성 시작")
        
        # 요청 데이터 파싱
        data = request.get_json() or {}
        interpolation_params = data.get('interpolation_params', {})
        
        # 벽 설정 로드
        app.logger.debug("벽 설정 로드 중")
        with open(WALLS_CONFIG, 'r') as f:
            walls_data = json.load(f)
            walls = walls_data.get('walls', '')

        # 센서 설정 로드
        app.logger.debug("센서 설정 로드 중")
        with open(SENSORS_CONFIG, 'r') as f:
            sensors_data = json.load(f)
            sensors = sensors_data.get('sensors', [])
        
        # 열지도 생성기 초기화
        thermal_map_path = os.path.join(MEDIA_PATH, 'thermal_map.png')
        generator = ThermalMapGenerator(walls, sensors, get_sensor_state, interpolation_params)
        
        # 열지도 생성
        if generator.generate(thermal_map_path):
            app.logger.info("열지도 생성 완료")
            return jsonify({
                'status': 'success',
                'image_url': '/media/thermal_map.png'
            })
        else:
            app.logger.error("열지도 생성 실패")
            return jsonify({'error': '열지도 생성에 실패했습니다.'}), 500
    
    except Exception as e:
        app.logger.error(f"열지도 생성 실패: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8099))
    app.run(host='0.0.0.0', port=port, debug=IS_DEV) 