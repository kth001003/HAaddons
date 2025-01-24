import threading
import logging
import os
import json
import time
from logging.handlers import RotatingFileHandler
from time import sleep
from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
from typing import Optional, Dict, Any, List
from thermal_map import ThermalMapGenerator


class ConfigManager:
    """설정 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool):
        self.is_local = is_local
        self.paths = self._init_paths()
        try:
            os.makedirs(self.paths['media'], exist_ok=True)
        except Exception as e:
            logging.error(f"미디어 디렉토리 생성 실패: {str(e)}")
        
    def _init_paths(self) -> Dict[str, str]:
        """경로 초기화"""
        base_dir = os.path.dirname(__file__)
        
        if self.is_local:
            return {
                'log': os.path.join(base_dir, 'thermomap.log'),
                'config': os.path.join(base_dir, 'test_config.json'),
                'media': os.path.join(base_dir, 'media'),
                'gen_config': os.path.join(base_dir, 'media', 'gen_config.json'),
                'parameters': os.path.join(base_dir, 'media', 'parameters.json'),
                'walls': os.path.join(base_dir, 'media', 'walls.json'),
                'sensors': os.path.join(base_dir, 'media', 'sensors.json')
            }
        else:
            return {
                'log': '/data/thermomap.log',
                'config': '/data/options.json',
                'gen_config': '/data/gen_config.json',
                'media': '/homeassistant/www',
                'parameters': '/data/parameters.json',
                'walls': '/data/walls.json',
                'sensors': '/data/sensors.json'
            }
    
    def _create_media_directory(self):
        """미디어 디렉토리 생성"""
    
    def load_mock_config(self) -> Dict:
        """mock 설정 로드"""
        with open(self.paths['config'], 'r') as f:
            return json.load(f)
    
    def get_mock_data(self) -> Dict:
        """개발 환경용 mock 데이터 반환"""
        config = self.load_mock_config()
        return config.get('mock_data', {})
    
    def save_walls(self, walls_data: Dict) -> None:
        """벽 설정 저장"""
        with open(self.paths['walls'], 'w') as f:
            json.dump({'walls': walls_data.get('walls', '')}, f)
    
    def save_sensors(self, sensors_data: Dict) -> None:
        """센서 위치 저장"""
        with open(self.paths['sensors'], 'w') as f:
            json.dump({'sensors': sensors_data.get('sensors', [])}, f)
    
    def save_parameters(self, parameters_data: Dict) -> None:
        """보간파라메터 위치 저장"""
        with open(self.paths['parameters'], 'w') as f:
            json.dump(parameters_data, f)
    
    def save_gen_config(self, gen_config: Dict) -> None:
        """생성 구성 저장"""
        with open(self.paths['gen_config'], 'w') as f:
            json.dump(gen_config, f)
    
    def load_heatmap_config(self) -> Dict:
        """히트맵 설정 로드"""
        config = {
            'parameters':{},
            'walls': '',
            'sensors': []
        }

        # 파라미터 설정 로드
        if os.path.exists(self.paths['parameters']):
            with open(self.paths['parameters'], 'r') as f:
                parameters_data = json.load(f)
                config['parameters'] = parameters_data

        # 생성 구성 로드
        if os.path.exists(self.paths['gen_config']):
            with open(self.paths['gen_config'], 'r') as f:
                gen_config_data = json.load(f)
                config['gen_config'] = gen_config_data

        # 벽 설정 로드
        if os.path.exists(self.paths['walls']):
            with open(self.paths['walls'], 'r') as f:
                walls_data = json.load(f)
                config['walls'] = walls_data.get('walls', '')
        
        # 센서 설정 로드
        if os.path.exists(self.paths['sensors']):
            with open(self.paths['sensors'], 'r') as f:
                sensors_data = json.load(f)
                config['sensors'] = sensors_data.get('sensors', [])
        
        return config

class SensorManager:
    """센서 상태 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, config_manager):
        self.is_local = is_local
        self.config_manager = config_manager
    
    def get_ha_api(self) -> Optional[Dict[str, Any]]:
        """Home Assistant API 설정"""
        if self.is_local:
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
    
    def get_sensor_state(self, entity_id: str) -> Dict[str, Any]:
        """센서 상태 조회"""
        try:
            if self.is_local:
                mock_data = self.config_manager.get_mock_data()
                for sensor in mock_data.get('temperature_sensors', []):
                    if sensor['entity_id'] == entity_id:
                        return {
                            'entity_id': entity_id,
                            'state': sensor.get('state', '0'),
                            'attributes': sensor.get('attributes', {})
                        }
                logging.warning(f"Mock 센서 데이터를 찾을 수 없음: {entity_id}")
                return {'state': '20', 'entity_id': entity_id}
            
            api = self.get_ha_api()
            if not api:
                logging.error("Home Assistant API 설정을 가져올 수 없습니다")
                return {'state': '0', 'entity_id': entity_id}
            
            logging.info(f"센서 상태 조회 중: {entity_id}")
            response = requests.get(
                f"{api['base_url']}/states/{entity_id}",
                headers=api['headers']
            )
            return response.json()
        except Exception as e:
            logging.error(f"센서 상태 조회 실패: {str(e)}")
            return {'state': '0', 'entity_id': entity_id}
    
    def get_all_states(self) -> List[Dict]:
        """모든 센서 상태 조회"""
        if self.is_local:
            mock_data = self.config_manager.get_mock_data()
            return mock_data.get('temperature_sensors', [])
        
        api = self.get_ha_api()
        if not api:
            return []
        
        response = requests.get(f"{api['base_url']}/states", headers=api['headers'])
        states = response.json()
        return [
            state for state in states
            if state.get('attributes', {}).get('device_class') == 'temperature' and
               state.get('attributes', {}).get('state_class') == 'measurement'
        ]

class ThermoMapServer:
    """열지도 웹 서버 클래스"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.is_dev = os.environ.get('FLASK_ENV') == 'development'
        self.is_local = os.environ.get('SUPERVISOR_TOKEN') is None
        
        self.config_manager = ConfigManager(self.is_local)
        self.sensor_manager = SensorManager(self.is_local, self.config_manager)
        
        self._init_app()
        self._setup_routes()
    
    def _init_app(self):
        """Flask 앱 초기화"""
        if self.is_dev:
            self.app.debug = True
            self.app.jinja_env.auto_reload = True
            self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        
        # 로깅 설정
        handler = RotatingFileHandler(
            self.config_manager.paths['log'],
            maxBytes=10000000,
            backupCount=5
        )
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        ))
        self.app.logger.addHandler(handler)
        self.app.logger.setLevel(logging.DEBUG if self.is_dev else logging.INFO)
    
    def _setup_routes(self):
        """라우트 설정"""
        self.app.route('/')(self.index)
        self.app.route('/api/states')(self.get_states)
        self.app.route('/api/save-walls-and-sensors', methods=['POST'])(self.save_walls_and_sensors)
        self.app.route('/api/save-interpolation-parameters', methods=['POST'])(self.save_interpolation_parameters)
        self.app.route('/api/save-gen-config', methods=['POST'])(self.save_gen_config)
        self.app.route('/api/load-config')(self.load_heatmap_config)
        self.app.route('/local/<path:filename>')(self.serve_media)
        self.app.route('/api/generate-map')(self.generate_map)
    
    def index(self):
        """메인 페이지"""
        cache_buster = int(time.time())
        return render_template('index.html', cache_buster=cache_buster)
    
    def get_states(self):
        """센서 상태 정보"""
        states = self.sensor_manager.get_all_states()
        return jsonify(states)
    
    def save_walls_and_sensors(self):
        """벽 및 센서 설정 저장"""
        data = request.get_json() or {}
        self.config_manager.save_walls(data.get("wallsData",""))
        self.config_manager.save_sensors(data.get("sensorsData",""))
        return jsonify({'status': 'success'})
    
    def save_interpolation_parameters(self):
        """보간 파라미터 저장"""
        data = request.get_json() or {}
        self.config_manager.save_parameters(data.get('interpolation_params', {}))
        return jsonify({'status': 'success'})
    
    def save_gen_config(self):
        """생성 구성 저장"""
        data = request.get_json() or {}
        self.config_manager.save_gen_config(data.get('gen_config', {}))
        return jsonify({'status': 'success'})

    def load_heatmap_config(self):
        """히트맵 설정 로드"""
        try:
            config = self.config_manager.load_heatmap_config()
            return jsonify(config)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    def serve_media(self, filename):
        """미디어 파일 제공"""
        self.app.logger.debug(f"미디어 파일 요청: {filename}")
        media_path = self.config_manager.paths['media']
        if os.path.exists(os.path.join(media_path, filename)):
            return send_from_directory(media_path, filename)
        else:
            self.app.logger.error(f"파일을 찾을 수 없음: {filename}")
            return "File not found", 404
    
    def generate_map(self):
        """열지도 생성"""
        try:
            self.app.logger.info("열지도 생성 시작")
                        
            # 보간 설정 로드
            with open(self.config_manager.paths['parameters'], 'r') as f:
                interpolation_params = json.load(f)

            # 벽 설정 로드
            with open(self.config_manager.paths['walls'], 'r') as f:
                walls_data = json.load(f)
                walls = walls_data.get('walls', '')
            
            # 센서 설정 로드
            with open(self.config_manager.paths['sensors'], 'r') as f:
                sensors_data = json.load(f)
                sensors = sensors_data.get('sensors', [])
            
            # 열지도 생성
            thermal_map_path = os.path.join(self.config_manager.paths['media'], 'thermal_map.png')
            generator = ThermalMapGenerator(
                walls,
                sensors,
                self.sensor_manager.get_sensor_state,
                interpolation_params
            )
            
            if generator.generate(thermal_map_path):
                self.app.logger.info("열지도 생성 완료")
                return jsonify({
                    'status': 'success',
                    'image_url': '/local/thermal_map.png'
                })
            else:
                self.app.logger.error("열지도 생성 실패")
                return jsonify({'error': '열지도 생성에 실패했습니다.'}), 500
        
        except Exception as e:
            self.app.logger.error(f"열지도 생성 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    def run(self, host='0.0.0.0', port=None):
        """서버 실행"""
        if port is None:
            port = int(os.environ.get('PORT', 8099))
        self.app.run(host=host, port=port, debug=self.is_dev)

class BackgroundTaskManager:
    def __init__(self, app, config_manager, sensor_manager, logger):
        self.app = app
        self.config_manager = config_manager
        self.sensor_manager = sensor_manager
        self.logger = logger
        self.thread = None
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()

    def run(self):
        while self.running:
            try:
                with self.app.app_context():
                    # 애플리케이션 컨텍스트 내에서 작업 실행
                    self.logger.info("백그라운드 열지도 생성 시작")
                    result = self.generate_map()
                    self.logger.info(f"백그라운드 열지도 생성 완료: {result}")
            except Exception as e:
                self.logger.error(f"백그라운드 열지도 생성 실패: {str(e)}")
            
            time.sleep(60)  # 60초 간격으로 실행

    def generate_map(self):
        """열지도 생성 로직"""
        try:
            walls = self.load_walls()
            sensors = self.load_sensors()
            interpolation_params = self.load_params()

            # 열지도 생성
            thermal_map_path = os.path.join(self.config_manager.paths['media'], 'thermal_map.png')
            generator = ThermalMapGenerator(
                walls, sensors, self.sensor_manager.get_sensor_state, interpolation_params
            )

            if generator.generate(thermal_map_path):
                return {'status': 'success', 'image_url': '/local/thermal_map.png'}
            else:
                raise Exception("열지도 생성 실패")
        except Exception as e:
            raise e

    def load_walls(self):
        """벽 설정 로드"""
        with open(self.config_manager.paths['walls'], 'r') as f:
            walls_data = json.load(f)
            return walls_data.get('walls', '')

    def load_sensors(self):
        """센서 설정 로드"""
        with open(self.config_manager.paths['sensors'], 'r') as f:
            sensors_data = json.load(f)
            return sensors_data.get('sensors', [])
        
    def load_params(self):
        """보간 구성 로드"""
        with open(self.config_manager.paths['parameters'], 'r') as f:
            params_data = json.load(f)
            return params_data or {}

if __name__ == '__main__':
    server = ThermoMapServer()
    background_task_manager = BackgroundTaskManager(
        server.app,
        server.config_manager,
        server.sensor_manager,
        server.app.logger
    )

    background_task_manager.start()

    try:
        server.run()
    finally:
        background_task_manager.stop()
