import os
import logging
import time
from datetime import datetime
import threading
import uuid
import io
import asyncio
import json
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
        
        # 기본 설정 로드
        self.default_config = self._load_default_config()
        
        self._init_app()
        self._setup_routes()
    
    def _load_default_config(self):
        """기본 설정 JSON 파일을 로드합니다."""
        try:
            # 먼저 미디어 경로에서 설정 파일 확인
            config_path = os.path.join(self.config_manager.paths['media'], 'default_config.json')
            
            # 파일이 존재하지 않으면 apps 디렉토리에서 찾기
            if not os.path.exists(config_path):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(base_dir, 'default_config.json')
                
                if not os.path.exists(config_path):
                    self.logger.warning(f"기본 설정 파일을 찾을 수 없습니다: {config_path}")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.logger.debug(f"기본 설정 파일 로드 완료: {config_path}")
                    return config
            else:
                self.logger.warning("기본 설정 파일이 없어 빈 객체를 사용합니다.")
                return {}
        except Exception as e:
            self.logger.error(f"기본 설정 파일 로드 실패: {str(e)}")
            # 파일 로드 실패 시 빈 객체 반환
            return {}

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

        @self.app.route('/api/save-walls-and-sensors/<map_id>', methods=['POST'])
        async def save_walls_and_sensors(map_id):
            """벽 및 센서 설정 저장"""
            data = await request.get_json() or {}
            self.config_manager.db.update_map(map_id, {
                'walls': data.get("wallsData", ""),
                'sensors': data.get("sensorsData", ""),
                'unit': data.get("unit", "")
            })
            return jsonify({'status': 'success'})
    
        @self.app.route('/api/save-interpolation-parameters/<map_id>', methods=['POST'])
        async def save_interpolation_parameters(map_id):
            """보간 파라미터 저장"""
            data = await request.get_json() or {}
            self.config_manager.db.update_map(map_id, {
                'parameters': data.get('interpolation_params', {})
            })
            return jsonify({'status': 'success'})
    
        @self.app.route('/api/save-gen-config/<map_id>', methods=['POST'])
        async def save_gen_config(map_id):
            """생성 구성 저장"""
            data = await request.get_json() or {}
            gen_config = data.get('gen_config', {})
            self.config_manager.db.update_map(map_id, {
                'gen_config': gen_config
            })
            return jsonify({'status': 'success'})

        @self.app.route('/api/load-config/<map_id>', methods=['GET'])
        async def load_heatmap_config(map_id):
            """히트맵 설정 로드"""
            try:
                config = self.config_manager.db.get_map(map_id)
                return jsonify(config)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/local/<path:filename>')
        async def serve_media(filename):
            return await self.serve_media(filename)

        @self.app.route('/local/HeatMapBuilder/<path:filename>')
        async def serve_heatmap_media(filename):
            return await self.serve_media(filename)

        @self.app.route('/api/generate-map/<map_id>', methods=['GET'])
        async def generate_map(map_id):
            """지도 생성 API"""
            if not self.map_lock.acquire(blocking=False):
                return jsonify({
                    'status': 'error',
                    'error': '다른 프로세스가 지도를 생성 중입니다. 잠시 후 다시 시도해주세요.'
                })

            try:
                # 지도 생성
                _, _, output_path = self.config_manager.get_output_info(map_id)
                result = await self.map_generator.generate(map_id, output_path)
                if result['success']:
                    map_name = self.config_manager.db.get_map(map_id).get('name', '')
                    last_generation = self.config_manager.db.get_map(map_id).get('last_generation', {})
                    self.logger.info("Webserver: 수동 맵 생성 완료 %s (%s) (소요시간: %s)",
                                    self.logger._colorize(map_name, "blue"),
                                    map_id,
                                    self.logger._colorize(last_generation.get('duration', ''), "green"))

                    return jsonify({
                        'status': 'success',
                        'img_url': self.config_manager.get_image_url(map_id),
                        'time': result['time'],
                        'duration': result['duration']
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'error': result['error']
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

        @self.app.route('/api/check-map-time/<map_id>', methods=['GET'])
        async def check_map_time(map_id):
            """지도 생성 시간 확인"""
            try:
                output_filename, _, output_path = self.config_manager.get_output_info(map_id)

                if os.path.exists(output_path):
                    map_data = self.config_manager.db.get_map(map_id)
                    last_generation = map_data.get('last_generation', {})
                    return jsonify({
                        'status': 'success',
                        'time': last_generation.get('time', ''),
                        'duration': last_generation.get('duration', ''),
                        'img_url': self.config_manager.get_image_url(map_id)
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

        @self.app.route('/api/maps', methods=['GET'])
        async def get_maps():
            return await self.get_maps()

        @self.app.route('/api/maps', methods=['POST'])
        async def create_map():
            return await self.create_map()

        @self.app.route('/api/maps/<map_id>', methods=['GET'])
        async def get_map(map_id):
            return await self.get_map(map_id)

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

        @self.app.route('/api/maps/<map_id>/previous-maps/<image_id>', methods=['DELETE'])
        async def delete_previous_map(map_id, image_id):
            """특정 맵의 이전 생성 이미지 삭제"""
            return await self.delete_previous_map(map_id, image_id)

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
            
            last_generation_info = map_data.get('last_generation', {})
            timestamp = last_generation_info.get('timestamp', '')
            img_url = self.config_manager.get_image_url(map_id)
            img_url_without_timestamp = img_url.split('?')[0] if '?' in img_url else img_url
            
            # 호스트 URL 생성
            host_url = request.host_url.rstrip('/')
            full_img_url = f"{host_url}{img_url}"
            full_img_url_without_timestamp = f"{host_url}{img_url_without_timestamp}"
            
            return await render_template('index.html', 
                            img_url=full_img_url,
                            img_url_without_timestamp=full_img_url_without_timestamp,
                            cache_buster=timestamp,
                            map_generation_time=timestamp,
                            map_generation_duration=last_generation_info.get('duration', ''),
                            map_name=map_data.get('name', ''),
                            map_id=map_id)
        except Exception as e:
            self.logger.error(f"맵 전환 실패: {str(e)}")
            return await render_template('404.html', error_message='맵 로딩 중 오류가 발생했습니다'), 404

    
    async def get_states(self):
        """센서 상태 정보"""
        states = await self.sensor_manager.get_all_states()
        return jsonify(states)
    
    async def get_label_registry(self):
        """라벨 레지스트리 정보"""
        label_registry = await self.sensor_manager.get_label_registry()
        return jsonify(label_registry)

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
    
    async def get_maps(self):
        """모든 맵 목록을 반환"""
        maps = self.config_manager.db.get_all_maps()
        return jsonify(maps)

    async def create_map(self):
        """새로운 맵 생성"""
        data = await request.get_json() or {}
        map_id = str(uuid.uuid4())
        
        # 기본 설정값 (JSON 파일에서 로드)
        default_config = self.default_config.get("default_map_config", {})
        
        # 사용자 제공 데이터로 기본값 업데이트
        map_config = default_config.copy()
        
        # 필수 기본 값 설정 (설정 파일이 없는 경우를 대비)
        if 'walls' not in map_config:
            map_config['walls'] = ""
        if 'sensors' not in map_config:
            map_config['sensors'] = []
        if 'gen_config' not in map_config:
            map_config['gen_config'] = {
                "auto_generation": True,
                "colorbar": {"cmap": "RdYlBu_r"},
                "file_name": "thermal_map",
                "format": "png"
            }
        
        map_config["name"] = data.get("name", "untitled")
        map_config["created_at"] = datetime.now().isoformat()
        map_config["updated_at"] = datetime.now().isoformat()
        
        self.config_manager.db.save(map_id, map_config)
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

            # 새로운 맵 데이터 생성 - 기본 값 설정
            default_config = self.default_config.get("default_map_config", {})
            new_map_data = default_config.copy()
            
            # 이름 및 생성 시간 설정
            new_map_data['name'] = new_name
            new_map_data['created_at'] = datetime.now().isoformat()
            new_map_data['updated_at'] = datetime.now().isoformat()
            
            # 원본에서 복제할 필드: walls, gen_config, parameters
            if 'walls' in original_map:
                new_map_data['walls'] = original_map.get('walls', '')
            if 'gen_config' in original_map:
                new_map_data['gen_config'] = original_map.get('gen_config', {})
            if 'parameters' in original_map:
                new_map_data['parameters'] = original_map.get('parameters', {})
            
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
            self.logger.trace(f"get_previous_maps 호출: map_id={map_id}")
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
                        img_url = self.config_manager.get_previous_image_url(map_id, index)
                        timestamp = os.path.getmtime(os.path.join(dir, file))
                        previous_maps.append({
                            'id': str(index),  # 사용할 ID 형식으로 변환
                            'index': index,
                            'url': img_url,
                            'timestamp': timestamp,
                            'date': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        })
            
            # 인덱스 기준으로 정렬 (작은 숫자가 최신)
            previous_maps.sort(key=lambda x: x['index'])
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
            
    async def delete_previous_map(self, map_id, image_id):
        """이전 생성 이미지를 삭제합니다.
        
        Args:
            map_id (str): 맵 ID
            image_id (str): 이미지 ID (이미지 인덱스)
            
        Returns:
            Response: 삭제 결과
        """
        try:
            self.logger.info(f"이미지 삭제 요청: map_id={map_id}, image_id={image_id}")
            
            if not map_id:
                return jsonify({'status': 'error', 'error': '맵 ID가 필요합니다.'}), 400
                
            if not image_id:
                return jsonify({'status': 'error', 'error': '이미지 ID가 필요합니다.'}), 400
                
            # 맵 데이터에서 파일 이름과 형식 가져오기
            map_data = self.config_manager.db.get_map(map_id)
            if not map_data:
                return jsonify({'status': 'error', 'error': '요청한 맵을 찾을 수 없습니다.'}), 404
                
            gen_config = map_data.get('gen_config', {})
            file_name = gen_config.get('file_name', 'thermal_map')
            file_format = gen_config.get('format', 'png')
            
            # 이미지 파일 경로
            output_dir = os.path.dirname(self.config_manager.get_output_path(map_id))
            image_file = os.path.join(output_dir, f"{file_name}-{image_id}.{file_format}")
            
            # 파일 존재 여부 확인
            if not os.path.exists(image_file):
                return jsonify({
                    'status': 'error',
                    'error': '이미지 파일을 찾을 수 없습니다.'
                }), 404
                
            # 파일 삭제
            os.remove(image_file)
            self.logger.info(f"이미지 파일 삭제 완료: {image_file}")
            
            return jsonify({
                'status': 'success',
                'message': '이미지가 삭제되었습니다.'
            })
            
        except Exception as e:
            self.logger.error(f"이미지 삭제 중 오류 발생: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    def run(self, host='0.0.0.0', port=None, background_task_manager=None):
        """서버 실행"""
        self.logger.debug("웹서버 시작 중...")
        
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
        
        # 현재 실행 중인 이벤트 루프를 가져오거나 새로 생성
        try:
            loop = asyncio.get_running_loop()
            self.logger.debug(f"웹서버에서 기존 이벤트 루프 사용 (ID: {id(loop)})")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.logger.debug(f"웹서버에서 새 이벤트 루프 생성 (ID: {id(loop)})")
        
        # 이벤트 루프가 시작되면 백그라운드 작업 시작을 위한 함수
        async def start_background_task_manager():
            # 웹서버가 완전히 시작될 때까지 약간 대기
            await asyncio.sleep(1)
            
            if background_task_manager:
                try:
                    # 이벤트 루프가 실행 중인 상태에서 백그라운드 작업 시작
                    self.logger.info("웹서버 시작 후 백그라운드 작업 시작")
                    background_task_manager.start()
                except Exception as e:
                    self.logger.error(f"백그라운드 작업 시작 중 오류 발생: {str(e)}")
        
        # hypercorn 서버 생성
        server_coro = hypercorn.asyncio.serve(self.app, config)
        
        if background_task_manager:
            # 백그라운드 태스크 시작 태스크 추가
            asyncio.ensure_future(start_background_task_manager(), loop=loop)
            self.logger.info(f"웹서버와 백그라운드 작업 실행 시작 (포트: {port})")
        else:
            self.logger.info(f"웹서버 실행 시작 (포트: {port})")
        
        # 서버 실행
        loop.run_until_complete(server_coro)