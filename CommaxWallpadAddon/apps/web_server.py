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
            if not self.wallpad_controller.DEVICE_STRUCTURE:
                return jsonify({"error": "Device structure not initialized"}), 400
                
            structures = {}
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                if 'command' in device:
                    command = device['command']
                    example = bytearray([0] * 7)  # 7바이트 (체크섬 제외)
                    desc_parts = []
                    
                    # 헤더 설정
                    example[0] = int(command['header'], 16)
                    
                    # deviceId는 1로 설정
                    device_id_pos = int(command['fieldPositions']['deviceId'])
                    example[device_id_pos] = 1
                    desc_parts.append("01: deviceId")
                    
                    # 기기별 특수 처리
                    if device_name == 'Thermo':
                        # 온도조절기 전원 켜기 예시
                        example[int(command['fieldPositions']['commandType'])] = int(command['structure']['2']['values']['power'], 16)
                        example[int(command['fieldPositions']['value'])] = int(command['structure']['3']['values']['on'], 16)
                        desc_parts.append("04: power")
                        desc_parts.append("81: on")
                    elif device_name == 'Fan':
                        # 환기장치 전원 켜기 예시
                        example[int(command['fieldPositions']['commandType'])] = int(command['structure']['2']['values']['power'], 16)
                        example[int(command['fieldPositions']['value'])] = int(command['structure']['3']['values']['on'], 16)
                        desc_parts.append("01: power")
                        desc_parts.append("04: on")
                    else:
                        # 일반적인 전원 켜기 예시
                        power_pos = command['fieldPositions'].get('power')
                        if power_pos:
                            example[int(power_pos)] = int(command['structure'][power_pos]['values']['on'], 16)
                            desc_parts.append("01: on")
                    
                    structures[device_name] = {
                        "type": device['type'],
                        "header": command['header'],
                        "example": example.hex().upper(),
                        "description": f"1번 {device_name} 켜기 ({', '.join(desc_parts)})"
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