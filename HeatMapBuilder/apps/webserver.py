from custom_logger import CustomLogger
import os
from flask import Flask, request, jsonify, render_template, send_from_directory
import json
import logging
import time
from datetime import datetime

class WebServer:
    """열지도 웹 서버 클래스"""
    
    def __init__(self, is_local, ConfigManager, SensorManager, MapGenerator, Logger):
        self.app = Flask(__name__,
                         template_folder=os.path.join('webapps', 'templates'),
                         static_folder=os.path.join('webapps', 'static'))
        self.is_local = is_local
        self.map_generation_time = ''
        self.map_generation_duration = ''
        self.logger = Logger

        self.config_manager = ConfigManager
        self.sensor_manager = SensorManager
        self.map_generator = MapGenerator
        
        self._init_app()
        self._setup_routes()
    
    def _init_app(self):
        """Flask 앱 초기화"""
        self.app.debug = True
        self.app.jinja_env.auto_reload = True
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        
        # Flask 기본 로깅 비활성화
        self.app.logger.handlers.clear()
        logging.getLogger('werkzeug').disabled = True
        
    
    def _setup_routes(self):
        """라우트 설정"""
        self.app.route('/')(self.index)
        self.app.route('/api/states')(self.get_states)
        self.app.route('/api/save-walls-and-sensors', methods=['POST'])(self.save_walls_and_sensors)
        self.app.route('/api/save-interpolation-parameters', methods=['POST'])(self.save_interpolation_parameters)
        self.app.route('/api/save-gen-config', methods=['POST'])(self.save_gen_config)
        self.app.route('/api/load-config')(self.load_heatmap_config)
        self.app.route('/local/<path:filename>')(self.serve_media)
        self.app.route('/api/generate-map', methods=['GET'])(self.generate_map)
        self.app.route('/api/check-map-time', methods=['GET'])(self.check_map_time)
    
    def index(self):
        """메인 페이지"""
        cache_buster = int(time.time())
        return render_template('index.html', 
                               img_url=f'/local/{self.config_manager.output_file}?{cache_buster}',
                               cache_buster=cache_buster, 
                               map_generation_time=self.map_generation_time,
                               map_generation_duration=self.map_generation_duration)
    
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
            timestamp_start = time.time_ns()
            # 벽 설정 로드
            walls_data = self._load_walls()
            # 센서 설정 로드
            sensors_data = self._load_sensors()
            # 보간 파라미터 로드
            params_data = self._load_params()
            # 생성 설정 로드
            gen_config = self.config_manager.load_gen_config()

            # # 열지도 생성기 초기화
            # generator = ThermalMapGenerator(
            #     walls_data=walls_data,
            #     sensors_data=sensors_data,
            #     get_sensor_state_func=self.sensor_manager.get_sensor_state,
            #     interpolation_params=params_data,
            #     gen_config=gen_config
            # )
            # 열지도 생성
            if self.map_generator.generate(self.config_manager.output_path):
                self.app.logger.info("열지도 생성 완료")
                self.map_generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                timestamp_end = time.time_ns()
                self.map_generation_duration = f'{((timestamp_end - timestamp_start)/1000000000):.3f}s'
                return jsonify({
                    'status': 'success',
                    'image_url': f'/local/{self.config_manager.output_file}',
                    'time': self.map_generation_time,
                    'duration': self.map_generation_duration
                })
            else:
                return jsonify({
                    'status': 'error',
                    'error': '열지도 생성에 실패했습니다.'
                })

        except Exception as e:
            self.app.logger.error(f"열지도 생성 실패: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            })

    def _load_walls(self):
        """벽 설정 로드"""
        with open(self.config_manager.paths['walls'], 'r') as f:
            walls_data = json.load(f)
            return walls_data.get('walls', '')

    def _load_sensors(self):
        """센서 설정 로드"""
        with open(self.config_manager.paths['sensors'], 'r') as f:
            sensors_data = json.load(f)
            return sensors_data.get('sensors', [])
        
    def _load_params(self):
        """보간 구성 로드"""
        with open(self.config_manager.paths['parameters'], 'r') as f:
            params_data = json.load(f)
            return params_data or {}
    
    def check_map_time(self):
        """열지도 생성 시간 확인"""
        try:
            map_path = os.path.join(self.config_manager.paths['media'], 'thermal_map.png')
            if os.path.exists(map_path):
                return jsonify({
                    'status': 'success',
                    'time': self.map_generation_time,
                    'duration': self.map_generation_duration,
                    'image_url': '/local/thermal_map.png'
                })
            else:
                return jsonify({
                    'status': 'error',
                    'error': '온도 지도가 아직 생성되지 않았습니다.'
                })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'error': str(e)
            })
    
    def run(self, host='0.0.0.0', port=None):
        """서버 실행"""
        if port is None:
            port = int(os.environ.get('PORT', 8099))
        self.app.run(host=host, port=port, debug=True)
