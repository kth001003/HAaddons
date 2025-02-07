import os
import logging
import json
from typing import Dict

class ConfigManager:
    """설정 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, CONFIG):
        self.is_local = is_local
        self.paths = self._init_paths()
        self.config = CONFIG
        self.gen_config = {}
        self.load_gen_config()
        self.output_file = f'{self.gen_config.get("file_name","thermal_map")}.{self.gen_config.get("format","PNG")}'
        self.output_path = os.path.join(self.paths['media'], self.output_file )

        try:
            os.makedirs(self.paths['media'], exist_ok=True)
        except Exception as e:
            logging.error(f"미디어 디렉토리 생성 실패: {str(e)}")
        
    def _init_paths(self) -> Dict[str, str]:
        """경로 초기화"""
        base_dir = os.path.dirname(__file__)
        
        if self.is_local:
            return {
                'log': os.path.join(base_dir, 'thermomap.log'),
                'config': os.path.join(base_dir, 'test_config.json'),
                'media': os.path.join(base_dir, 'media'),
                'gen_config': os.path.join(base_dir, 'media', 'gen_config.json'),
                'parameters': os.path.join(base_dir, 'media', 'parameters.json'),
                'walls': os.path.join(base_dir, 'media', 'walls.json'),
                'sensors': os.path.join(base_dir, 'media', 'sensors.json')
            }
        else:
            return {
                'log': '/data/thermomap.log',
                'config': '/data/options.json',
                'gen_config': '/data/gen_config.json',
                'media': '/homeassistant/www',
                'parameters': '/data/parameters.json',
                'walls': '/data/walls.json',
                'sensors': '/data/sensors.json'
            }
    
    def _create_media_directory(self):
        """미디어 디렉토리 생성"""
    
    def load_mock_config(self) -> Dict:
        """mock 설정 로드"""
        with open(self.paths['config'], 'r') as f:
            return json.load(f)
    
    def get_mock_data(self) -> Dict:
        """개발 환경용 mock 데이터 반환"""
        config = self.load_mock_config()
        return config.get('mock_data', {})
    
    def save_walls(self, walls_data: Dict) -> None:
        """벽 설정 저장"""
        with open(self.paths['walls'], 'w') as f:
            json.dump({'walls': walls_data.get('walls', '')}, f, indent=4)
    
    def save_sensors(self, sensors_data: Dict) -> None:
        """센서 위치 저장"""
        with open(self.paths['sensors'], 'w') as f:
            json.dump({'sensors': sensors_data.get('sensors', [])}, f, indent=4)
    
    def save_parameters(self, parameters_data: Dict) -> None:
        """보간파라메터 위치 저장"""
        with open(self.paths['parameters'], 'w') as f:
            json.dump(parameters_data, f, indent=4)
    
    def save_gen_config(self, gen_config: Dict) -> None:
        """생성 구성 저장"""
        with open(self.paths['gen_config'], 'w') as f:
            json.dump(gen_config, f, indent=4)
    
    def load_gen_config(self) -> Dict:
        """생성 구성 로드"""
        try:
            with open(self.paths['gen_config'], 'r') as f:
                self.gen_config = json.load(f)
                return self.gen_config
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def load_heatmap_config(self) -> Dict:
        """히트맵 설정 로드"""
        config = {
            'parameters':{},
            'walls': '',
            'sensors': [],
            'gen_configs': {}
        }

        # 파라미터 설정 로드
        if os.path.exists(self.paths['parameters']):
            with open(self.paths['parameters'], 'r') as f:
                parameters_data = json.load(f)
                config['parameters'] = parameters_data

        # 생성 구성 로드
        if os.path.exists(self.paths['gen_config']):
            with open(self.paths['gen_config'], 'r') as f:
                gen_config_data = json.load(f)
                config['gen_config'] = gen_config_data

        # 벽 설정 로드
        if os.path.exists(self.paths['walls']):
            with open(self.paths['walls'], 'r') as f:
                walls_data = json.load(f)
                config['walls'] = walls_data.get('walls', '')
        
        # 센서 설정 로드
        if os.path.exists(self.paths['sensors']):
            with open(self.paths['sensors'], 'r') as f:
                sensors_data = json.load(f)
                config['sensors'] = sensors_data.get('sensors', [])
        
        return config
