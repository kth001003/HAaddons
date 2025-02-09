import os
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect
import json
import logging
import time
from datetime import datetime
import threading
import uuid

class WebServer:
    """열지도 웹 서버 클래스"""
    
    def __init__(self, is_local, ConfigManager, SensorManager, MapGenerator, Logger):
        self.app = Flask(__name__,
                         template_folder=os.path.join('webapps', 'templates'),
                         static_folder=os.path.join('webapps', 'static'))
        self.is_local = is_local
        self.logger = Logger
        self.map_lock = threading.Lock()  # 락 메커니즘 추가

        self.config_manager = ConfigManager
        self.sensor_manager = SensorManager
        self.map_generator = MapGenerator
        self.current_map_id = None 
        
        self._init_app()
        self._setup_routes()
    
    def _init_app(self):
        """Flask 앱 초기화"""
        self.app.debug = True
        self.app.jinja_env.auto_reload = True
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        
        # Flask 로깅 설정
        self.app.logger.handlers.clear()
        logging.getLogger('werkzeug').disabled = True
        
    
    def _setup_routes(self):
        """라우트 설정"""
        self.app.route('/')(self.maps_page)  # 맵 선택 페이지를 기본 페이지로
        self.app.route('/map')(self.index)  # 메인 페이지는 /map으로 이동
        self.app.route('/api/states')(self.get_states)
        self.app.route('/api/save-walls-and-sensors', methods=['POST'])(self.save_walls_and_sensors)
        self.app.route('/api/save-interpolation-parameters', methods=['POST'])(self.save_interpolation_parameters)
        self.app.route('/api/save-gen-config', methods=['POST'])(self.save_gen_config)
        self.app.route('/api/load-config')(self.load_heatmap_config)
        self.app.route('/local/<path:filename>')(self.serve_media)
        self.app.route('/api/generate-map', methods=['GET'])(self.generate_map)
        self.app.route('/api/check-map-time', methods=['GET'])(self.check_map_time)
        
        # 맵 관리 API 추가
        self.app.route('/api/maps', methods=['GET'])(self.get_maps)
        self.app.route('/api/maps', methods=['POST'])(self.create_map)
        self.app.route('/api/maps/<map_id>', methods=['GET'])(self.get_map)
        self.app.route('/api/maps/<map_id>', methods=['PUT'])(self.update_map)
        self.app.route('/api/maps/<map_id>', methods=['DELETE'])(self.delete_map)
        self.app.route('/api/maps/<map_id>/switch', methods=['POST'])(self.switch_map)
    
    def maps_page(self):
        """맵 선택 페이지"""
        return render_template('maps.html')

    def index(self):
        """메인 페이지"""
        if not self.current_map_id:
            return redirect('/')  # 맵이 선택되지 않은 경우 맵 선택 페이지로 리다이렉트
            
        cache_buster = int(time.time())
        return render_template('index.html', 
                            img_url=f'/local/{self.current_map_id}/{self.config_manager.get_output_filename(self.current_map_id)}?{cache_buster}',
                            cache_buster=cache_buster, 
                            map_generation_time=self.map_generator.generation_time,
                            map_generation_duration=self.map_generator.generation_duration)

    
    def get_states(self):
        """센서 상태 정보"""
        states = self.sensor_manager.get_all_states()
        return jsonify(states)
    
    def save_walls_and_sensors(self):
        """벽 및 센서 설정 저장"""
        data = request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        map_data = self.config_manager.db.get_map(self.current_map_id)
        map_data['walls'] = data.get("wallsData", "")
        map_data['sensors'] = data.get("sensorsData", "")
        self.config_manager.db.save(self.current_map_id, map_data)
        return jsonify({'status': 'success'})
    
    def save_interpolation_parameters(self):
        """보간 파라미터 저장"""
        data = request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        map_data = self.config_manager.db.get_map(self.current_map_id)
        map_data['parameters'] = data.get('interpolation_params', {})
        self.config_manager.db.save(self.current_map_id, map_data)
        return jsonify({'status': 'success'})
    
    def save_gen_config(self):
        """생성 구성 저장"""
        data = request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        gen_config = data.get('gen_config', {})
        map_data = self.config_manager.db.get_map(self.current_map_id)
        map_data['gen_config'] = gen_config
        self.config_manager.db.save(self.current_map_id, map_data)
        return jsonify({'status': 'success'})

    def load_heatmap_config(self):
        """히트맵 설정 로드"""
        try:
            if not self.current_map_id:
                return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
            config = self.config_manager.db.get_map(self.current_map_id)
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
        if not self.current_map_id:
            return jsonify({
                'status': 'error',
                'error': '현재 선택된 맵이 없습니다.'
            }), 400

        if not self.map_lock.acquire(blocking=False):
            return jsonify({
                'status': 'error',
                'error': '다른 프로세스가 열지도를 생성 중입니다. 잠시 후 다시 시도해주세요.'
            })

        try:
            # 열지도 생성
            output_filename, _, output_path = self.config_manager.get_output_info(self.current_map_id)
                
            if self.map_generator.generate(output_path):
                self.app.logger.info("열지도 생성 완료")

                return jsonify({
                    'status': 'success',
                    'image_url': f'/local/{self.current_map_id}/{output_filename}',
                    'time': self.map_generator.generation_time,
                    'duration': self.map_generator.generation_duration
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
        finally:
            self.map_lock.release()  # 락 해제
    
    def check_map_time(self):
        """열지도 생성 시간 확인"""
        try:
            if not self.current_map_id:
                return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400

            output_filename, _, output_path = self.config_manager.get_output_info(self.current_map_id)

            if os.path.exists(output_path):
                map_data = self.config_manager.db.get_map(self.current_map_id)
                last_generation = map_data.get('last_generation', {})
                return jsonify({
                    'status': 'success',
                    'time': last_generation.get('time', ''),
                    'duration': last_generation.get('duration', ''),
                    'image_url': f'/local/{self.current_map_id}/{output_filename}'
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
    
    def get_maps(self):
        """모든 맵 목록을 반환"""
        maps = self.config_manager.db.get_all_maps()
        return jsonify(maps)

    def create_map(self):
        """새로운 맵 생성"""
        data = request.get_json() or {}
        map_id = str(uuid.uuid4())
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        self.config_manager.db.save(map_id, data)
        return jsonify({'id': map_id})

    def get_map(self, map_id):
        """특정 맵의 상세 정보 조회"""
        try:
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return jsonify({'error': '맵을 찾을 수 없습니다.'}), 404
            return jsonify(map_data)
        except Exception as e:
            self.logger.error(f"맵 조회 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

    def update_map(self):
        """맵 정보 업데이트"""
        data = request.get_json() or {}
        map_id = data.get('id')
        if not map_id:
            return jsonify({'error': '맵 ID가 필요합니다.'}), 400
        self.config_manager.db.save(map_id, data)
        return jsonify({'status': 'success'})

    def delete_map(self, map_id):
        """맵 삭제"""
        if self.config_manager.db.delete(map_id):
            return jsonify({'status': 'success'})
        return jsonify({'error': '맵을 찾을 수 없습니다.'}), 404

    def switch_map(self, map_id):
        """현재 맵 전환"""
        try:
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return jsonify({'error': '맵을 찾을 수 없습니다.'}), 404
            
            # 현재 맵 ID 설정
            self.current_map_id = map_id
            # MapGenerator 설정 업데이트
            self.map_generator.load_map_config(map_id)
            # 생성 설정 업데이트
            
            return jsonify({'status': 'success'})
        except Exception as e:
            self.logger.error(f"맵 전환 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

    def run(self, host='0.0.0.0', port=None):
        """서버 실행"""
        if port is None:
            port = int(os.environ.get('PORT', 8099))
        self.app.run(host=host, port=port, debug=True)