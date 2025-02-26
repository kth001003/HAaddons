import os
import logging
import time
from datetime import datetime
import threading
import uuid
from PIL import Image # type: ignore
import io
import asyncio
from quart import Quart, jsonify, request, render_template, Response, send_from_directory # type: ignore
import hypercorn.asyncio # type: ignore
import hypercorn.config # type: ignore
import matplotlib.pyplot as plt # type: ignore
import matplotlib.cm as cm # type: ignore
import numpy as np # type: ignore
import shutil

class WebServer:
    """지도 웹 서버 클래스"""
    
    def __init__(self, ConfigManager, SensorManager, MapGenerator, Logger):
        self.app = Quart(__name__,
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
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        
        # Flask 로깅 설정
        self.app.logger.handlers.clear()
        logging.getLogger('werkzeug').disabled = True
        
        # 404 에러 핸들러 등록
        self.app.register_error_handler(404, self.handle_404_error)
    
    async def handle_404_error(self, error):
        """404 에러 처리"""
        return await render_template('404.html'), 404

    def _setup_routes(self):
        """라우트 설정"""
        @self.app.route('/')
        async def maps_page():
            return await self.maps_page()

        @self.app.route('/map')
        async def map_edit():
            return await self.map_edit()

        @self.app.route('/api/states')
        async def get_states():
            return await self.get_states()
        
        @self.app.route('/api/get_label_registry')
        async def get_label_registry():
            return await self.get_label_registry()

        @self.app.route('/api/save-walls-and-sensors', methods=['POST'])
        async def save_walls_and_sensors():
            return await self.save_walls_and_sensors()

        @self.app.route('/api/save-interpolation-parameters', methods=['POST'])
        async def save_interpolation_parameters():
            return await self.save_interpolation_parameters()

        @self.app.route('/api/save-gen-config', methods=['POST'])
        async def save_gen_config():
            return await self.save_gen_config()

        @self.app.route('/api/load-config')
        async def load_heatmap_config():
            return await self.load_heatmap_config()

        @self.app.route('/local/<path:filename>')
        async def serve_media(filename):
            return await self.serve_media(filename)

        @self.app.route('/local/HeatMapBuilder/<path:filename>')
        async def serve_heatmap_media(filename):
            return await self.serve_media(filename)

        @self.app.route('/api/generate-map', methods=['GET'])
        async def generate_map():
            """지도 생성 API"""
            if not self.current_map_id:
                return jsonify({
                    'status': 'error',
                    'error': '현재 선택된 맵이 없습니다.'
                }), 400

            if not self.map_lock.acquire(blocking=False):
                return jsonify({
                    'status': 'error',
                    'error': '다른 프로세스가 지도를 생성 중입니다. 잠시 후 다시 시도해주세요.'
                })

            try:
                # 지도 생성
                output_filename, _, output_path = self.config_manager.get_output_info(self.current_map_id)
                    
                success, error_msg = await self.map_generator.generate(self.current_map_id,output_path)
                if success:
                    self.app.logger.info("지도 생성 완료")

                    return jsonify({
                        'status': 'success',
                        'image_url': f'/local/HeatMapBuilder/{self.current_map_id}/{output_filename}',
                        'time': self.map_generator.generation_time,
                        'duration': self.map_generator.generation_duration
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'error': error_msg
                    })

            except Exception as e:
                self.app.logger.error(f"지도 생성 실패: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'error': str(e)
                })
            finally:
                try:
                    # 웹소켓 연결 종료
                    await self.sensor_manager.websocket_client.close()
                except Exception as close_error:
                    self.app.logger.error(f"웹소켓 연결 종료 중 오류 발생: {str(close_error)}")
                finally:
                    self.map_lock.release()  # 락 해제

        @self.app.route('/api/check-map-time', methods=['GET'])
        async def check_map_time():
            return await self.check_map_time()

        @self.app.route('/api/maps', methods=['GET'])
        async def get_maps():
            return await self.get_maps()

        @self.app.route('/api/maps', methods=['POST'])
        async def create_map():
            return await self.create_map()

        @self.app.route('/api/maps/<map_id>', methods=['GET'])
        async def get_map(map_id):
            return await self.get_map(map_id)

        # @self.app.route('/api/maps/<map_id>', methods=['PUT'])
        # async def update_map(map_id):
        #     return await self.update_map(map_id)

        @self.app.route('/api/maps/<map_id>', methods=['DELETE'])
        async def delete_map(map_id):
            return await self.delete_map(map_id)

        @self.app.route('/api/maps/<map_id>/clone', methods=['POST'])
        async def clone_map_route(map_id):
            return await self.clone_map(map_id)

        @self.app.route('/api/maps/<map_id>/previous-maps', methods=['GET'])
        async def get_previous_maps_by_id(map_id):
            """특정 맵의 이전 생성 이미지 목록 조회"""
            return await self.get_previous_maps(map_id)

        @self.app.route('/api/maps/export', methods=['GET'])
        async def export_maps():
            return await self.export_maps()

        @self.app.route('/api/maps/import', methods=['POST'])
        async def import_maps():
            return await self.import_maps()

        @self.app.route('/api/debug-websocket', methods=['POST'])
        async def debug_websocket():
            """WebSocket 디버그 API"""
            try:
                data = await request.get_json()
                message_type = data.get('message_type')
                kwargs = data.get('kwargs', {})
                
                if not message_type:
                    return jsonify({
                        'status': 'error',
                        'error': 'message_type이 필요합니다.'
                    }), 400
                    
                result = await self.sensor_manager.debug_websocket(message_type, **kwargs)
                return jsonify({
                    'status': 'success',
                    'result': result
                })
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'error': str(e)
                }), 500

        @self.app.route('/api/preview_colormap', methods=['POST'])
        async def preview_colormap():
            """컬러맵 미리보기 API"""
            try:
                data = await request.get_json()
                colormap_name = data.get('colormap')
                
                if not colormap_name:
                    return jsonify({
                        'status': 'error',
                        'error': '컬러맵 이름이 필요합니다.'
                    }), 400

                # matplotlib을 사용하여 컬러맵 미리보기 이미지 생성
                
                try:
                    # 컬러맵 유효성 검사
                    cm.get_cmap(colormap_name)
                except ValueError:
                    return jsonify({
                        'status': 'error',
                        'error': '잘못된 컬러맵 이름입니다.'
                    }), 400

                # 컬러맵 미리보기 이미지 생성
                fig, ax = plt.subplots(figsize=(6, 1))
                gradient = np.linspace(0, 1, 256)
                gradient = np.vstack((gradient, gradient))
                ax.imshow(gradient, aspect='auto', cmap=colormap_name)
                ax.set_axis_off()
                
                # 이미지를 바이트로 변환
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
                buf.seek(0)
                plt.close()

                return Response(buf.getvalue(), mimetype='image/png')

            except Exception as e:
                self.logger.error(f"컬러맵 미리보기 생성 실패: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'error': str(e)
                }), 500

    async def maps_page(self):
        """맵 선택 페이지"""
        return await render_template('maps.html')

    async def map_edit(self):
        """맵 편집 페이지"""
        map_id = request.args.get('id')
        
        if not map_id:
            return await render_template('404.html', error_message='맵 ID가 필요합니다'), 404
        
        try:
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return await render_template('404.html', error_message='요청하신 맵을 찾을 수 없습니다'), 404
            
            # 현재 맵 ID 설정 및 설정 업데이트
            self.current_map_id = map_id
        except Exception as e:
            self.logger.error(f"맵 전환 실패: {str(e)}")
            return await render_template('404.html', error_message='맵 로딩 중 오류가 발생했습니다'), 404
            
        if not self.current_map_id:
            return await render_template('404.html', error_message='선택된 맵이 없습니다'), 404
        
        last_generation_info = self.config_manager.db.get_map(self.current_map_id).get('last_generation', {})
        cache_buster = int(time.time())
        return await render_template('index.html', 
                            img_url=f'/local/HeatMapBuilder/{self.current_map_id}/{self.config_manager.get_output_filename(self.current_map_id)}?{cache_buster}',
                            cache_buster=cache_buster,
                            is_map_generated= True if last_generation_info.get('timestamp') else False,
                            map_generation_time=last_generation_info.get('timestamp', ''),
                            map_generation_duration=last_generation_info.get('duration', ''),
                            map_name=map_data.get('name', ''),
                            map_id=self.current_map_id)

    
    async def get_states(self):
        """센서 상태 정보"""
        states = await self.sensor_manager.get_all_states()
        return jsonify(states)
    
    async def get_label_registry(self):
        """라벨 레지스트리 정보"""
        label_registry = await self.sensor_manager.get_label_registry()
        return jsonify(label_registry)

    async def save_walls_and_sensors(self):
        """벽 및 센서 설정 저장"""
        data = await request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        self.config_manager.db.update_map(self.current_map_id, {
            'walls': data.get("wallsData", ""),
            'sensors': data.get("sensorsData", ""),
            'unit': data.get("unit", "")
        })
        return jsonify({'status': 'success'})
    
    async def save_interpolation_parameters(self):
        """보간 파라미터 저장"""
        data = await request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        self.config_manager.db.update_map(self.current_map_id, {
            'parameters': data.get('interpolation_params', {})
        })
        return jsonify({'status': 'success'})
    
    async def save_gen_config(self):
        """생성 구성 저장"""
        data = await request.get_json() or {}
        if not self.current_map_id:
            return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
        gen_config = data.get('gen_config', {})
        self.config_manager.db.update_map(self.current_map_id, {
            'gen_config': gen_config,
            'img_url': f'/local/HeatMapBuilder/{self.current_map_id}/{gen_config.get("file_name", "thermal_map")}.{gen_config.get("format", "png")}'
        })
        return jsonify({'status': 'success'})

    async def load_heatmap_config(self):
        """히트맵 설정 로드"""
        try:
            if not self.current_map_id:
                return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
            config = self.config_manager.db.get_map(self.current_map_id)
            return jsonify(config)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    async def serve_media(self, filename):
        """미디어 파일 제공"""
        self.app.logger.debug(f"미디어 파일 요청: {filename}")
        media_path = self.config_manager.paths['media']
        full_path = os.path.join(media_path, filename)
        directory = os.path.dirname(full_path)
        base_filename = os.path.basename(full_path)
        
        if os.path.exists(full_path):
            return await send_from_directory(directory, base_filename)
        else:
            self.app.logger.error(f"파일을 찾을 수 없음: {filename}")
            return "File not found", 404
    
    async def check_map_time(self):
        """지도 생성 시간 확인"""
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
    
    async def get_maps(self):
        """모든 맵 목록을 반환"""
        maps = self.config_manager.db.get_all_maps()
        return jsonify(maps)

    async def create_map(self):
        """새로운 맵 생성"""
        data = await request.get_json() or {}
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
                    "label_color": "#000000",
                    "min_temp": 0,
                    "max_temp": 30,
                    "temp_steps": 100
                }
            }
        }

        self.config_manager.db.save(map_id, default_config)
        return jsonify({'id': map_id})

    async def get_map(self, map_id):
        """특정 맵의 상세 정보 조회"""
        try:
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return jsonify({'error': '맵을 찾을 수 없습니다.'}), 404
            return jsonify(map_data)
        except Exception as e:
            self.logger.error(f"맵 조회 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # async def update_map(self, map_id):
    #     """맵 정보 업데이트"""
    #     data = await request.get_json() or {}
    #     if not map_id:
    #         return jsonify({'error': '맵 ID가 필요합니다.'}), 400
    #     self.config_manager.db.save(map_id, data)
    #     return jsonify({'status': 'success'})

    async def delete_map(self, map_id):
        """맵 삭제"""
        try:
            # 맵 폴더 경로 생성
            map_dir = os.path.join(self.config_manager.paths['media'], str(map_id))
            
            # DB에서 맵 삭제
            self.config_manager.db.delete_map(map_id)
            
            # 맵 폴더가 존재하면 삭제
            if os.path.exists(map_dir):
                shutil.rmtree(map_dir)
            
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    async def clone_map(self, map_id):
        """맵 복제"""
        try:
            data = await request.get_json() or {}
            new_name = data.get('name')
            if not new_name:
                return jsonify({'error': '새 맵 이름이 필요합니다.'}), 400

            # 원본 맵 데이터 가져오기
            original_map = self.config_manager.db.get_map(map_id)
            if not original_map:
                return jsonify({'error': '원본 맵을 찾을 수 없습니다.'}), 404

            # 새로운 맵 ID 생성
            new_map_id = str(uuid.uuid4())

            # 새로운 맵 데이터 생성 (sensors 제외)
            new_map_data = original_map.copy()
            new_map_data['name'] = new_name
            new_map_data['created_at'] = datetime.now().isoformat()
            new_map_data['updated_at'] = datetime.now().isoformat()
            new_map_data['sensors'] = []  # sensors는 비움
            
            # 새로운 맵 저장
            self.config_manager.db.save(new_map_id, new_map_data)
            
            return jsonify({
                'status': 'success',
                'id': new_map_id
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    async def export_maps(self):
        """맵 데이터 내보내기"""
        try:
            maps = self.config_manager.db.load()
            return jsonify(maps)
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    async def import_maps(self):
        """맵 데이터 불러오기"""
        try:
            data = await request.get_json()
            if not isinstance(data, dict):
                return jsonify({'error': '올바르지 않은 맵 데이터 형식입니다.'}), 400

            # 기존 맵 데이터와 병합
            existing_maps = self.config_manager.db.load()
            for map_id, map_data in data.items():
                if map_id in existing_maps:
                    # 기존 맵이 있는 경우 업데이트
                    existing_maps[map_id].update(map_data)
                else:
                    # 새로운 맵인 경우 추가
                    existing_maps[map_id] = map_data

            # 저장
            self.config_manager.db.save_all(existing_maps)
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    async def get_previous_maps(self, map_id=None):
        """이전 생성 이미지 목록을 반환합니다."""
        try:
            self.logger.debug(f"get_previous_maps 호출: map_id={map_id}")
            if map_id is None:
                return jsonify({'error': '현재 선택된 맵이 없습니다.'}), 400
                
            # 맵 데이터에서 파일 이름과 형식 가져오기
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return jsonify({'error': '요청한 맵을 찾을 수 없습니다.'}), 404
                
            gen_config = map_data.get('gen_config', {})
            file_name = gen_config.get('file_name', 'thermal_map')
            file_format = gen_config.get('format', 'png')
                        
            dir = os.path.dirname(self.config_manager.get_output_path(map_id))
            # 패턴에 맞는 파일 목록 가져오기
            previous_maps = []
            if os.path.exists(dir):
                for file in os.listdir(dir):
                    import re
                    # 파일 이름 패턴 확인 (thermal_map-숫자.확장자)
                    match = re.match(f"{file_name}-(\\d+)\\.{file_format}", file)
                    if match:
                        index = int(match.group(1))
                        img_url = f"/local/HeatMapBuilder/{map_id}/{file}"
                        timestamp = os.path.getmtime(os.path.join(dir, file))
                        previous_maps.append({
                            'index': index,
                            'url': img_url,
                            'timestamp': timestamp,
                            'date': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        })
            
            # 인덱스 기준으로 정렬 (작은 숫자가 최신)
            previous_maps.sort(key=lambda x: x['index'])
            self.logger.debug(f"이전 맵 목록: {previous_maps}")
            return jsonify({
                'status': 'success',
                'previous_maps': previous_maps
            })
        except Exception as e:
            self.logger.error(f"이전 맵 목록 조회 실패: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    def run(self, host='0.0.0.0', port=None):
        """서버 실행"""
        if port is None:
            port = int(os.environ.get('PORT', 8099))

        config = hypercorn.config.Config()
        config.bind = [f"{host}:{port}"]
        config.use_reloader = True
        config.reload_dirs = ['apps']  # 앱 디렉토리 변경 감시
        config.reload_includes = ['*.py', '*.html', '*.js', '*.css']  # 감시할 파일 확장자
        config.reload_excludes = ['*.pyc', '*.pyo']  # 제외할 파일 확장자
        config.accesslog = None  # 액세스 로그 비활성화
        config.errorlog = '-'
        
        asyncio.run(hypercorn.asyncio.serve(self.app, config))