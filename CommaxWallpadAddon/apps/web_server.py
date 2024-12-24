from flask import Flask, render_template, jsonify, request # type: ignore
import threading
import logging
import os
from typing import Dict, Any
import time

class WebServer:
    def __init__(self, wallpad_controller):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.wallpad_controller = wallpad_controller
        
        # 로깅 비활성화
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        # Home Assistant Ingress 베이스 URL 설정
        self.base_url = os.environ.get('SUPERVISOR_TOKEN', '')
        
        # 라우트 설정
        @self.app.route('/')
        def home():
            # 디버깅을 위한 경로 출력
            print(f"Static folder path: {self.app.static_folder}")
            print(f"CSS path: {os.path.join(self.app.static_folder, 'style.css')}")
            print(f"JS path: {os.path.join(self.app.static_folder, 'script.js')}")
            
            try:
                css_mtime = os.path.getmtime(os.path.join(self.app.static_folder, 'style.css'))
                js_mtime = os.path.getmtime(os.path.join(self.app.static_folder, 'script.js'))
                version = max(css_mtime, js_mtime)
            except OSError as e:
                print(f"Error accessing static files: {e}")
                version = time.time()  # os.time.time() -> time.time()로 수정
            return render_template('index.html', version=version)
            
        @self.app.after_request
        def add_header(response):
            if 'static' in request.path:
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '-1'
            return response 
        
        @self.app.route('/api/devices')
        def get_devices():
            return jsonify(self.wallpad_controller.device_list or {})
            
        @self.app.route('/api/state')
        def get_state():
            return jsonify(self.wallpad_controller.HOMESTATE)
            
        @self.app.route('/api/packet_logs')
        def get_packet_logs():
            """패킷 로그를 제공합니다."""
            try:
                send_packets = []
                recv_packets = []

                # 가능한 패킷 타입
                packet_types = ['command', 'state_request', 'state', 'ack']

                # 송신 패킷 처리
                for packet in self.wallpad_controller.COLLECTDATA['send_data']:
                    packet_info = {
                        'packet': packet,
                        'results': []
                    }
                    for packet_type in packet_types:
                        device_info = self._analyze_packet_structure(packet, packet_type)
                        if device_info['success']:
                            packet_info['results'].append({
                                'device': device_info['device'],
                                'packet_type': packet_type
                            })
                    
                    # 분석 결과가 없는 경우 Unknown으로 처리
                    if not packet_info['results']:
                        packet_info['results'].append({
                            'device': 'Unknown',
                            'packet_type': 'Unknown'
                        })

                    send_packets.append(packet_info)

                # 수신 패킷 처리 (송신 패킷 처리와 동일한 로직 적용)
                for packet in self.wallpad_controller.COLLECTDATA['recv_data']:
                    packet_info = {
                        'packet': packet,
                        'results': []
                    }
                    for packet_type in packet_types:
                        device_info = self._analyze_packet_structure(packet, packet_type)
                        if device_info['success']:
                            packet_info['results'].append({
                                'device': device_info['device'],
                                'packet_type': packet_type
                            })

                    # 분석 결과가 없는 경우 Unknown으로 처리
                    if not packet_info['results']:
                        packet_info['results'].append({
                            'device': 'Unknown',
                            'packet_type': 'Unknown'
                        })

                    recv_packets.append(packet_info)

                return jsonify({
                    'send': send_packets,
                    'recv': recv_packets
                })

            except Exception as e:
                return jsonify({
                    'error': str(e)
                }), 500
            
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

                # 체크섬 계산
                checksum_result = self.wallpad_controller.checksum(command)

                # 패킷 구조 분석
                analysis_result = self._analyze_packet_structure(command, packet_type)

                if not analysis_result["success"]:
                    return jsonify(analysis_result), 400

                response = {
                    "success": True,
                    "device": analysis_result["device"],
                    "analysis": analysis_result["analysis"],
                    "checksum": checksum_result
                }

                # command 패킷 경우 예상 상태 패킷 추가
                if packet_type == 'command' and checksum_result:
                    expected_state = self.wallpad_controller.generate_expected_state_packet(checksum_result)
                    if expected_state:
                        response["expected_state"] = expected_state

                return jsonify(response)

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
                    "state": self._get_packet_structure(device_name, device, 'state'),
                    "state_request": self._get_packet_structure(device_name, device, 'state_request'),
                    "ack": self._get_packet_structure(device_name, device, 'ack')
                }
             
            return jsonify(structures)
        
        @self.app.route('/api/packet_suggestions')
        def get_packet_suggestions():
            """패킷 입력 도우미를 위한 정보를 제공합니다."""
            suggestions = {
                'headers': {},  # 헤더 정보
                'values': {}    # 각 바이트 위치별 가능한 값
            }
            
            # 명령 패킷 헤더
            command_headers = []
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                if 'command' in device:
                    command_headers.append({
                        'header': device['command']['header'],
                        'device': device_name
                    })
            suggestions['headers']['command'] = command_headers
            
            # 상태 패킷 헤더
            state_headers = []
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                if 'state' in device:
                    state_headers.append({
                        'header': device['state']['header'],
                        'device': device_name
                    })
            suggestions['headers']['state'] = state_headers
            
            # 상태 요청 패킷 헤더
            state_request_headers = []
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                if 'state_request' in device:
                    state_request_headers.append({
                        'header': device['state_request']['header'],
                        'device': device_name
                    })
            suggestions['headers']['state_request'] = state_request_headers
            
            # 응답 패킷 헤더
            ack_headers = []
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                if 'ack' in device:
                    ack_headers.append({
                        'header': device['ack']['header'],
                        'device': device_name
                    })
            suggestions['headers']['ack'] = ack_headers
            
            # 각 기기별 가능한 값들
            for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
                for packet_type in ['command', 'state', 'state_request', 'ack']:
                    if packet_type in device:
                        key = f"{device_name}_{packet_type}"
                        suggestions['values'][key] = {}
                        
                        for pos, field in device[packet_type]['structure'].items():
                            if 'values' in field:
                                suggestions['values'][key][pos] = {
                                    'name': field['name'],
                                    'values': field['values']
                                }
            
            return jsonify(suggestions)
    
    def run(self):
        threading.Thread(target=self._run_server, daemon=True).start()
        
    def _run_server(self):
        self.app.run(
            host='0.0.0.0',
            port=8099,
            use_reloader=False,
            threaded=True
        ) 
    
    def _analyze_packet_structure(self, command: str, packet_type: str) -> Dict[str, Any]:
        """패킷 구조를 분석하고 관련 정보를 반환합니다."""
        # 헤더 기기 찾기
        header = command[:2]
        device_info = None
        device_name = None

        for name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
            if packet_type in device and device[packet_type]['header'] == header:
                device_info = device[packet_type]
                device_name = name
                break

        if not device_info:
            return {
                "success": False,
                "error": f"알 수 없는 패킷입니다."
            }

        # 각 바이트 분석
        byte_analysis = []
        # 헤더 추가
        byte_analysis.append(f"Byte 0: header = {device_name} {packet_type} ({header})")

        for pos, field in device_info['structure'].items():
            pos = int(pos)
            if pos * 2 + 2 <= len(command):
                byte_value = command[pos*2:pos*2+2]
                desc = f"Byte {pos}: {field['name']}"

                if field['name'] == 'empty':
                    desc = f"Byte {pos}: (00)"
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

        return {
            "success": True,
            "device": device_name,
            "analysis": byte_analysis
        }

    def _get_packet_structure(self, device_name: str, device: Dict[str, Any], packet_type: str) -> Dict[str, Any]:
        """패킷 구조 정보를 생성합니다."""
        if packet_type not in device:
            return {}

        structure = device[packet_type]
        byte_desc = []
        examples = []

        # 패킷 구조 분석을 통해 byte_desc 생성
        analysis_result = self._analyze_packet_structure('00' * len(structure['structure']), packet_type)
        if analysis_result["success"]:
            byte_desc = [desc.split(" = ")[0] for desc in analysis_result["analysis"]]

        # 헤더 설명
        byte_desc.append(f"Byte 0: 헤더 ({structure['header']})")
        
        # 각 바이트 설명 생성
        for pos, field in structure['structure'].items():
            pos = int(pos)
            if field['name'] == 'empty':
                byte_desc.append(f"Byte {pos}: (00)")
            elif field['name'] == 'checksum':
                byte_desc.append(f"Byte {pos}: 체크섬")
            else:
                desc = f"Byte {pos}: {field['name']}"
                if 'values' in field:
                    values = [f"{k}={v}" for k, v in field['values'].items()]
                    desc += f" ({', '.join(values)})"
                byte_desc.append(desc)
        
        # 예시 패킷 동적 생성
        if device['type'] == 'Thermo':
            if packet_type == 'command':
                # 온도조절기 켜기
                packet = list('00' * 7)  # 7바이트 초기화
                packet[0] = structure['header']  # 헤더
                packet[1] = '01'  # 1번 온도조절기
                packet[2] = '04'  # 전원
                packet[3] = '81'  # ON
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 켜기"
                })
                
                # 온도 설정
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 온도조절기
                packet[2] = '03'  # 온도 설정
                packet[3] = '18'  # 24도
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 온도 24도로 설정"
                })
            elif packet_type == 'state':
                # 대기 상태
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '81'  # 상태
                packet[2] = '01'  # 1번 온도조절기
                packet[3] = '18'  # 24도
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 대기 상태 (현재 24도, 설정 24도)"
                })
                
                # 난방 중
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '83'  # 난방
                packet[2] = '01'  # 1번 온도조절기
                packet[3] = '18'  # 24도
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 난방 중 (현재 24도, 설정 24도)"
                })
            elif packet_type == 'state_request':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 온도조절기
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 상태 요청"
                })
            elif packet_type == 'ack':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 온도조절기
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 온도조절기 상태 요청"
                })
                
        elif device['type'] == 'Light':
            if packet_type == 'command':
                # 조명 끄기
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 조명
                packet[2] = '00'  # OFF
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 끄기"
                })
                
                # 조명 켜기
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 조명
                packet[2] = '01'  # ON
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 켜기"
                })
            elif packet_type == 'state':
                # 조명 꺼짐
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '00'  # OFF
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 꺼짐"
                })
                
                # 조명 켜짐
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # ON
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 켜짐"
                })
            elif packet_type == 'state_request':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 조명
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 상태 요청"
                })
            elif packet_type == 'ack':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 조명
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 조명 상태 요청"
                })
                
        elif device['type'] == 'Fan':
            if packet_type == 'command':
                # 환기장치 켜기
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 환기장치
                packet[2] = '01'  # 전원
                packet[3] = '04'  # ON
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 켜기"
                })
                
                # 환기장치 약으로 설정
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 환기장치
                packet[2] = '02'  # 풍량
                packet[3] = '00'  # 약(low)
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 약(low)으로 설정"
                })
            elif packet_type == 'state':
                # 환기장치 켜짐 (약)
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '04'  # ON
                packet[2] = '01'  # 1번 환기장치
                packet[3] = '00'  # 약(low)
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 켜짐 (약)"
                })
                
                # 환기장치 꺼짐
                packet = list('00' * 7)
                packet[0] = structure['header']
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 꺼짐"
                })
            elif packet_type == 'state_request':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 환기장치
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 상태 요청"
                })
            elif packet_type == 'ack':
                # 상태 요청
                packet = list('00' * 7)
                packet[0] = structure['header']
                packet[1] = '01'  # 1번 환기장치
                examples.append({
                    "packet": ''.join(packet),
                    "desc": "1번 환기장치 상태 요청"
                })
        
        return {
            "header": structure['header'],
            "byte_desc": byte_desc,
            "examples": examples
        } 
    
    def _get_device_info(self, packet: str) -> Dict[str, str]:
        """패킷의 헤더를 기반으로 기기 정보를 반환합니다."""
        if len(packet) < 2:
            return {"name": "Unknown", "packet_type": "Unknown"}
            
        header = packet[:2]
        
        # 명령 패킷 확인
        for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
            if 'command' in device and device['command']['header'] == header:
                return {"name": device_name, "packet_type": "Command"}
                
        # 태 패킷 확인
        for device_name, device in self.wallpad_controller.DEVICE_STRUCTURE.items():
            if 'state' in device and device['state']['header'] == header:
                return {"name": device_name, "packet_type": "State"}
                
        return {"name": "Unknown", "packet_type": "Unknown"} 
