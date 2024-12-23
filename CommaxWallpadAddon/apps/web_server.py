from flask import Flask, render_template, jsonify, request # type: ignore
import threading
import logging
import os

class WebServer:
    def __init__(self, wallpad_controller):
        self.app = Flask(__name__)
        self.wallpad_controller = wallpad_controller
        
        # 로깅 비활성화
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        # Home Assistant Ingress 베이스 URL 설정
        self.base_url = os.environ.get('SUPERVISOR_TOKEN', '')
        
        # 라우트 설정
        @self.app.route('/')
        def home():
            return render_template('index.html')
            
        @self.app.route('/api/devices')
        def get_devices():
            return jsonify(self.wallpad_controller.device_list or {})
            
        @self.app.route('/api/state')
        def get_state():
            return jsonify(self.wallpad_controller.HOMESTATE)
            
        @self.app.route('/api/find_devices', methods=['POST'])
        def find_devices():
            self.wallpad_controller.device_list = self.wallpad_controller.find_device()
            return jsonify({"success": True})
            
        @self.app.route('/api/analyze_packet', methods=['POST'])
        def analyze_packet():
            try:
                data = request.get_json()
                command = data.get('command', '').strip()
                
                # 체크섬 계산
                checksum_result = self.wallpad_controller.checksum(command)
                
                # 예상 상태 패킷 생성
                expected_state = None
                if checksum_result:
                    expected_state = self.wallpad_controller.generate_expected_state_packet(checksum_result)
                
                return jsonify({
                    "success": True,
                    "checksum": checksum_result,
                    "expected_state": expected_state
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 400
            
        @self.app.route('/api/packet_structures')
        def get_packet_structures():
            structures = {}
            for device_type, commands in self.wallpad_controller.PACKET_STRUCTURE.items():
                structures[device_type] = {}
                for command_name, command in commands.items():
                    example = [0x00] * len(command['structure'])
                    
                    # 기본값 설정
                    for pos, field in command['structure'].items():
                        pos = int(pos)
                        if 'default' in field:
                            example[pos] = int(field['default'], 16)
                            
                    # 전원 값 설정 (있는 경우에만)
                    for pos, field in command['structure'].items():
                        pos = int(pos)
                        if 'values' in field and ('on' in field['values'] or 'off' in field['values']):
                            example[pos] = int(field['values'].get('on', '0x00'), 16)
                    
                    structures[device_type][command_name] = {
                        'structure': command['structure'],
                        'example': ' '.join([format(b, '02X') for b in example])
                    }
            
            return jsonify(structures)
    
    def run(self):
        threading.Thread(target=self._run_server, daemon=True).start()
        
    def _run_server(self):
        self.app.run(
            host='0.0.0.0',
            port=8099,
            use_reloader=False,
            threaded=True
        ) 