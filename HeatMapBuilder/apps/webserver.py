import os
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, Response
import json
import logging
import time
from datetime import datetime
import threading
import uuid
from PIL import Image # type: ignore
import io

class WebServer:
    """열지도 웹 서버 클래스"""
    
    def __init__(self, ConfigManager, SensorManager, MapGenerator, Logger):
        self.app = Flask(__name__,
                         template_folder=os.path.join('webapps', 'templates'),
                         static_folder=os.path.join('webapps', 'static'))
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
        
        # 404 에러 핸들러 등록
        self.app.register_error_handler(404, self.handle_404_error)
    
    def handle_404_error(self, error):
        """404 에러 처리"""
        return render_template('404.html'), 404

    def _setup_routes(self):
        """라우트 설정"""
        self.app.route('/')(self.maps_page)
        self.app.route('/map')(self.map_edit)
        self.app.route('/api/states')(self.get_states)

        self.app.route('/api/save-walls-and-sensors', methods=['POST'])(self.save_walls_and_sensors)
        self.app.route('/api/save-interpolation-parameters', methods=['POST'])(self.save_interpolation_parameters)
        self.app.route('/api/save-gen-config', methods=['POST'])(self.save_gen_config)
        self.app.route('/api/load-config')(self.load_heatmap_config)
        self.app.route('/local/<path:filename>')(self.serve_media)
        self.app.route('/local/HeatMapBuilder/<path:filename>')(self.serve_media)
        self.app.route('/api/generate-map', methods=['GET'])(self.generate_map)
        self.app.route('/api/check-map-time', methods=['GET'])(self.check_map_time)
        
        self.app.route('/api/maps', methods=['GET'])(self.get_maps)
        self.app.route('/api/maps', methods=['POST'])(self.create_map)
        self.app.route('/api/maps/<map_id>', methods=['GET'])(self.get_map)
        self.app.route('/api/maps/<map_id>', methods=['PUT'])(self.update_map)
        self.app.route('/api/maps/<map_id>', methods=['DELETE'])(self.delete_map)
        self.app.route('/stream/<map_id>')(self.stream_map)    

    def maps_page(self):
        """맵 선택 페이지"""
        return render_template('maps.html')

    def map_edit(self):
        """맵 편집 페이지"""
        map_id = request.args.get('id')
        
        if not map_id:
            return render_template('404.html', error_message='맵 ID가 필요합니다'), 404
        
        try:
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return render_template('404.html', error_message='요청하신 맵을 찾을 수 없습니다'), 404
            
            # 현재 맵 ID 설정 및 설정 업데이트
            self.current_map_id = map_id
        except Exception as e:
            self.logger.error(f"맵 전환 실패: {str(e)}")
            return render_template('404.html', error_message='맵 로딩 중 오류가 발생했습니다'), 404
            
        if not self.current_map_id:
            return render_template('404.html', error_message='선택된 맵이 없습니다'), 404
        
        last_generation_info = self.config_manager.db.get_map(self.current_map_id).get('last_generation', {})
        cache_buster = int(time.time())
        return render_template('index.html', 
                            img_url=f'/local/HeatMapBuilder/{self.current_map_id}/{self.config_manager.get_output_filename(self.current_map_id)}?{cache_buster}',
                            cache_buster=cache_buster,
                            is_map_generated= True if last_generation_info.get('timestamp') else False,
                            map_generation_time=last_generation_info.get('timestamp', ''),
                            map_generation_duration=last_generation_info.get('duration', ''),
                            map_id=self.current_map_id)

    
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
        full_path = os.path.join(media_path, filename)
        directory = os.path.dirname(full_path)
        base_filename = os.path.basename(full_path)
        
        if os.path.exists(full_path):
            return send_from_directory(directory, base_filename)
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
                
            if self.map_generator.generate(self.current_map_id,output_path):
                self.app.logger.info("열지도 생성 완료")

                return jsonify({
                    'status': 'success',
                    'image_url': f'/local/HeatMapBuilder/{self.current_map_id}/{output_filename}',
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
                    'image_url': f'/local/HeatMapBuilder/{self.current_map_id}/{output_filename}'
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
        
        # 기본 설정값
        default_config = {
            "name": data.get("name", "untitled"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "walls": "",
            "sensors": [],
            "parameters": {
                "gaussian": {
                    "sigma_factor": 8
                },
                "rbf": {
                    "function": "inverse",
                    "epsilon_factor": 0.5
                },
                "kriging": {
                    "variogram_model": "power",
                    "nlags": 6,
                    "weight": True,
                    "anisotropy_scaling": 1,
                    "anisotropy_angle": 0,
                    "variogram_parameters": {
                        "scale": 1,
                        "exponent": 1.5,
                        "nugget": 0
                    }
                }
            },
            "gen_config": {
                "gen_interval": 5,
                "format": "png",
                "file_name": "thermal_map",
                "visualization": {
                    "empty_area": "white",
                    "area_border_width": 7,
                    "area_border_color": "#000000",
                    "plot_border_width": 0,
                    "plot_border_color": "#000000",
                    "sensor_display": "position_temp",
                    "sensor_info_bg": {
                        "color": "#FFFFFF",
                        "opacity": 70,
                        "padding": 5,
                        "border_radius": 4,
                        "border_width": 1,
                        "border_color": "#000000",
                        "position": "right",
                        "distance": 10
                    },
                    "sensor_marker": {
                        "style": "circle",
                        "size": 10,
                        "color": "#FF0000"
                    },
                    "sensor_name": {
                        "font_size": 12,
                        "color": "#000000"
                    },
                    "sensor_temp": {
                        "font_size": 12,
                        "color": "#000000"
                    }
                },
                "colorbar": {
                    "cmap": "RdYlBu_r",
                    "show_colorbar": True,
                    "width": 5,
                    "height": 80,
                    "location": "right",
                    "borderpad": 0,
                    "orientation": "vertical",
                    "show_label": True,
                    "label": "온도 (°C)",
                    "font_size": 10,
                    "tick_size": 8,
                    "min_temp": 0,
                    "max_temp": 30,
                    "temp_steps": 100
                }
            }
        }

        self.config_manager.db.save(map_id, default_config)
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
        try:
            # 맵 디렉토리 경로 가져오기
            map_dir = os.path.join(self.config_manager.paths['media'], map_id)
            
            # 데이터베이스에서 맵 삭제
            if self.config_manager.db.delete(map_id):
                # 맵 디렉토리가 존재하면 삭제
                if os.path.exists(map_dir):
                    import shutil
                    shutil.rmtree(map_dir)
                return jsonify({'status': 'success'})
            return jsonify({'error': '맵을 찾을 수 없습니다.'}), 404
        except Exception as e:
            self.logger.error(f"맵 삭제 중 오류 발생: {str(e)}")
            return jsonify({'error': f'맵 삭제 중 오류가 발생했습니다: {str(e)}'}), 500

    def stream_map(self, map_id):
        """맵의 MJPEG 스트림을 제공합니다."""
        # 맵 ID 검증
        map_data = self.config_manager.db.get_map(map_id)
        if not map_data:
            return render_template('404.html', error_message=f'맵 ID {map_id}를 찾을 수 없습니다.'), 404
            
        def generate():
            while True:
                image_filename, _, output_path = self.config_manager.get_output_info(map_id)
                if os.path.exists(output_path):
                    try:
                        # PIL을 사용하여 이미지를 JPEG로 변환
                        img = Image.open(output_path)
                        # RGBA를 RGB로 변환
                        if img.mode == 'RGBA':
                            # 흰색 배경에 이미지 합성
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[3])  # 알파 채널을 마스크로 사용
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                            
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='JPEG', quality=100)
                        frame = img_byte_arr.getvalue()
                        
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    except Exception as e:
                        self.logger.error(f"이미지 변환 중 오류 발생: {str(e)}")
                time.sleep(1)  # 1초마다 이미지 업데이트

        return Response(generate(),
                      mimetype='multipart/x-mixed-replace; boundary=frame')

    def run(self, host='0.0.0.0', port=None):
        """서버 실행"""
        if port is None:
            port = int(os.environ.get('PORT', 8099))
        self.app.run(host=host, port=port, debug=False)