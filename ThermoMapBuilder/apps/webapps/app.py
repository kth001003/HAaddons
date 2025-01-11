import os
import json
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, render_template, send_from_directory
from scipy.interpolate import griddata
import requests

app = Flask(__name__)

# 설정 파일 경로
CONFIG_PATH = '/data/options.json'
MEDIA_PATH = '/media'

def load_config():
    """Home Assistant 애드온 설정을 로드합니다."""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_ha_api():
    """Home Assistant API 설정을 가져옵니다."""
    config = load_config()
    supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
    return {
        'base_url': 'http://supervisor/core/api',
        'headers': {
            'Authorization': f'Bearer {supervisor_token}',
            'Content-Type': 'application/json'
        }
    }

@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@app.route('/api/states')
def get_states():
    """Home Assistant의 모든 상태를 가져옵니다."""
    api = get_ha_api()
    response = requests.get(f"{api['base_url']}/states", headers=api['headers'])
    return jsonify(response.json())

@app.route('/api/save-config', methods=['POST'])
def save_config():
    """Floor plan 설정을 저장합니다."""
    data = request.json
    config_file = '/data/thermomap_config.json'
    
    # Base64 이미지를 파일로 저장
    if data.get('floorplan'):
        import base64
        img_data = data['floorplan'].split(',')[1]
        img_bytes = base64.b64decode(img_data)
        with open(f'{MEDIA_PATH}/floorplan.png', 'wb') as f:
            f.write(img_bytes)
    
    # 설정 저장
    with open(config_file, 'w') as f:
        json.dump({
            'walls': data.get('walls', ''),
            'sensors': data.get('sensors', [])
        }, f)
    
    return jsonify({'status': 'success'})

@app.route('/api/generate-map', methods=['POST'])
def generate_map():
    """온도 데이터를 기반으로 열지도를 생성합니다."""
    try:
        # 설정 로드
        with open('/data/thermomap_config.json', 'r') as f:
            config = json.load(f)
        
        # 기준 이미지 로드
        base_img = Image.open(f'{MEDIA_PATH}/floorplan.png')
        width, height = base_img.size
        
        # 센서 데이터 수집
        api = get_ha_api()
        sensors = config['sensors']
        points = []
        temperatures = []
        
        for sensor in sensors:
            if not sensor.get('position'):
                continue
            
            # 센서 상태 조회
            response = requests.get(
                f"{api['base_url']}/states/{sensor['entity_id']}", 
                headers=api['headers']
            )
            state = response.json()
            
            try:
                temp = float(state['state'])
                x, y = sensor['position']
                points.append([x, y])
                temperatures.append(temp)
            except (ValueError, KeyError):
                continue
        
        if not points:
            return jsonify({'error': '유효한 센서 데이터가 없습니다.'}), 400
        
        # 격자 생성
        grid_x, grid_y = np.mgrid[0:width:100j, 0:height:100j]
        
        # 보간
        grid_z = griddata(
            np.array(points), 
            np.array(temperatures), 
            (grid_x, grid_y), 
            method='cubic'
        )
        
        # 열지도 생성
        plt.figure(figsize=(10, 10))
        plt.imshow(base_img)
        plt.contourf(grid_x, grid_y, grid_z.T, alpha=0.5, cmap='RdYlBu_r')
        plt.colorbar(label='Temperature (°C)')
        
        # 이미지 저장
        plt.savefig(f'{MEDIA_PATH}/thermal_map.png', 
                   bbox_inches='tight', 
                   pad_inches=0)
        plt.close()
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099) 