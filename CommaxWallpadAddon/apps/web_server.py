from flask import Flask, render_template, jsonify, request # type: ignore
import threading
import logging
import os
from typing import Dict, Any

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
            
        @self.app.route('/api/packet_logs')
        def get_packet_logs():
            # 송수신 패킷 모두 가져오기
            send_packets = list(self.wallpad_controller.COLLECTDATA.get('send_data', set()))[-50:]
            recv_packets = list(self.wallpad_controller.COLLECTDATA.get('recv_data', set()))[-50:]
            
            return jsonify({
                'send': send_packets,
                'recv': recv_packets
            })
            
        @self.app.route('/api/find_devices', methods=['POST'])
        def find_devices():
            self.wallpad_controller.device_list = self.wallpad_controller.find_device()
            return jsonify({"success": True})
            
        @self.app.route('/api/analyze_packet', methods=['POST'])
        def analyze_packet():
            try:
                data = request.get_json()
                command = data.get('command', '').strip()
                packet_type = data.get('type', 'command')  # 'command' 또는 'state'
                
                if packet_type == 'command':
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
                else:  # state packet analysis
                    # 헤더로 기기 찾기
                    header = command[:2]
                    device_info = None
                    device_name = None
                    
                    for name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                        if 'state' in device and device['state']['header'] == header:
                            device_info = device['state']
                            device_name = name
                            break
                    
                    if not device_info:
                        return jsonify({
                            "success": False,
                            "error": "알 수 없는 상태 패킷입니다."
                        }), 400
                    
                    # 각 바이트 분석
                    byte_analysis = []
                    for pos, field in device_info['structure'].items():
                        pos = int(pos)
                        if pos * 2 + 2 <= len(command):
                            byte_value = command[pos*2:pos*2+2]
                            desc = f"Byte {pos}: {field['name']}"
                            
                            if field['name'] == 'empty':
                                desc = f"Byte {pos}: 예약됨 (00)"
                            elif field['name'] == 'checksum':
                                desc = f"Byte {pos}: 체크섬"
                            elif 'values' in field:
                                # 알려진 값과 매칭
                                matched_value = None
                                for key, value in field['values'].items():
                                    if value == byte_value:
                                        matched_value = key
                                        break
                                if matched_value:
                                    desc += f" = {matched_value} ({byte_value})"
                                else:
                                    desc += f" = {byte_value}"
                            else:
                                desc += f" = {byte_value}"
                            
                            byte_analysis.append(desc)
                 
                return jsonify({
                    "success": True,
                    "device": device_name,
                    "analysis": byte_analysis
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 400
            
        @self.app.route('/api/packet_structures')
        def get_packet_structures():
            structures = {}
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                structures[device_name] = {
                    "type": device['type'],
                    "command": self._get_packet_structure(device_name, device, 'command'),
                    "state": self._get_packet_structure(device_name, device, 'state')
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
    
    def _get_packet_structure(self, device_name: str, device: Dict[str, Any], packet_type: str) -> Dict[str, Any]:
        """패킷 구조 정보를 생성합니다."""
        if packet_type not in device:
            return {}
            
        structure = device[packet_type]
        byte_desc = []
        examples = []
        
        # 헤더 설명
        byte_desc.append(f"Byte 0: 헤더 ({structure['header']})")
        
        # 각 바이트 설명 생성
        for pos, field in structure['structure'].items():
            pos = int(pos)
            if field['name'] == 'empty':
                byte_desc.append(f"Byte {pos}: 예약됨 (00)")
            elif field['name'] == 'checksum':
                byte_desc.append(f"Byte {pos}: 체크섬")
            else:
                desc = f"Byte {pos}: {field['name']}"
                if 'values' in field:
                    values = [f"{k}={v}" for k, v in field['values'].items()]
                    desc += f" ({', '.join(values)})"
                byte_desc.append(desc)
        
        # 예시 패킷 생성
        if packet_type == 'command':
            if device_name == 'Thermo':
                examples.extend([
                    {"packet": "040104810000", "desc": "1번 온도조절기 켜기"},
                    {"packet": "040103180000", "desc": "1번 온도조절기 온도 24도로 설정"}
                ])
            elif device_name == 'Light':
                examples.extend([
                    {"packet": "310100000000", "desc": "1번 조명 끄기"},
                    {"packet": "310101000000", "desc": "1번 조명 켜기"}
                ])
            elif device_name == 'Fan':
                examples.extend([
                    {"packet": "780101040000", "desc": "1번 환기장치 켜기"},
                    {"packet": "780102000000", "desc": "1번 환기장치 약(low)으로 설정"}
                ])
        else:  # state
            if device_name == 'Thermo':
                examples.extend([
                    {"packet": "828101180000", "desc": "1번 온도조절기 대기 상태 (현재 24도, 설정 24도)"},
                    {"packet": "828301180000", "desc": "1번 온도조절기 난방 중 (현재 24도, 설정 24도)"}
                ])
            elif device_name == 'Light':
                examples.extend([
                    {"packet": "B0000000000000", "desc": "1번 조명 꺼짐"},
                    {"packet": "B0010000000000", "desc": "1번 조명 켜짐"}
                ])
            elif device_name == 'Fan':
                examples.extend([
                    {"packet": "F6040100000000", "desc": "1번 환기장치 켜짐 (약)"},
                    {"packet": "F6000000000000", "desc": "1번 환기장치 꺼짐"}
                ])
        
        return {
            "header": structure['header'],
            "byte_desc": byte_desc,
            "examples": examples
        } 