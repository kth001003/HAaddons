import os
import json
from typing import Dict, Tuple
from jsonDB import JsonDB
import time

class ConfigManager:
    """설정 관리를 담당하는 클래스"""
    
    def __init__(self, is_local: bool, CONFIG):
        self.is_local = is_local
        self.CONFIG = CONFIG #아직 안쓰임임
        self.paths = self._init_paths()
        self.db = JsonDB(self.paths['maps'])
        
    def _init_paths(self) -> Dict[str, str]:
        """경로 초기화"""
        base_path = '/data'
        media_path = os.path.join('/homeassistant', 'www', 'HeatMapBuilder')
        if self.is_local:
            base_path = os.path.join('local','temp')
            media_path = os.path.join(base_path,'HeatMapBuilder')

        paths = {
            'maps': os.path.join(base_path, 'maps.json'),  # 맵 데이터베이스 파일
            'log': os.path.join(base_path, 'thermomap.log'),
            'config': os.path.join(base_path, 'options.json'),
            'media': media_path
        }

        # 필요한 디렉토리 생성
        for path in paths.values():
            if path.endswith(('.json', '.log')):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            else:
                os.makedirs(path, exist_ok=True)

        return paths

    def get_mock_data(self) -> Dict:
        """개발 환경용 mock 데이터 반환"""
        try:
            with open(os.path.join('local','test_config.json'), 'r') as f:
                data = json.load(f)
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_output_filename(self, map_id: str) -> str:
        """맵의 출력 파일 이름을 반환"""
        gen_config = self.db.get_map(map_id).get('gen_config', {})
        return f"{gen_config.get('file_name', 'map')}.{gen_config.get('format', 'png')}"

    def get_output_format(self, map_id: str) -> str:
        """맵의 출력 파일 포맷을 반환"""
        gen_config = self.db.get_map(map_id).get('gen_config', {})
        return gen_config.get('format', 'png')

    def get_output_path(self, map_id: str) -> str:
        """맵의 출력 파일 전체 경로를 반환"""
        os.makedirs(os.path.join(self.paths['media'], map_id), exist_ok=True)
        return os.path.join(self.paths['media'], map_id, self.get_output_filename(map_id))

    def get_output_info(self, map_id: str) -> Tuple[str, str, str]:
        """맵의 출력 파일 정보(파일명, 포맷, 경로)를 한번에 반환"""
        gen_config = self.db.get_map(map_id).get('gen_config', {})
        format = gen_config.get('format', 'png')
        filename = f"{gen_config.get('file_name', 'map')}.{format}"
        os.makedirs(os.path.join(self.paths['media'], map_id), exist_ok=True)
        path = os.path.join(self.paths['media'], map_id, filename)
        return filename, format, path

    def get_image_url(self, map_id: str) -> str:
        """맵의 이미지 URL을 반환합니다.
        
        Args:
            map_id: 맵 ID
            
        Returns:
            str: 이미지 URL
        """
        map_data = self.db.get_map(map_id)
        img_url = map_data.get('img_url', '')
        if not img_url:
            timestamp = map_data.get('last_generation', {}).get('timestamp', int(time.time()))
            output_filename = self.get_output_filename(map_id)
            img_url = f"/local/HeatMapBuilder/{map_id}/{output_filename}?{timestamp}"
            self.db.update_map(map_id, {'img_url': img_url})
        return img_url
    
    def get_gif_url(self, map_id: str) -> str:
        map_data = self.db.get_map(map_id)
        gif_url = map_data.get('gif_url', '')
        if not gif_url:
            timestamp = map_data.get('last_generation', {}).get('timestamp', int(time.time()))
            output_filename = self.get_output_filename(map_id)
            gif_filename = f"{output_filename.replace('.png', '')}_animation.gif"
            gif_url = f"/local/HeatMapBuilder/{map_id}/{gif_filename}?{timestamp}"
            self.db.update_map(map_id, {'gif_url': gif_url})
        return gif_url
    
    def get_previous_image_url(self, map_id: str, index: int) -> str:
        """이전 생성 이미지의 URL을 생성합니다. cache_buster 추가
        
        Args:
            map_id: 맵 ID
            index: 이미지 인덱스
            
        Returns:
            str: 이미지 URL
        """
        map_data = self.db.get_map(map_id)
        gen_config = map_data.get('gen_config', {})
        filename = gen_config.get('file_name', 'map')
        file_format = gen_config.get('format', 'png')
        cache_buster = int(time.time())
            
        return f"/local/HeatMapBuilder/{map_id}/{filename}-{index}.{file_format}?{cache_buster}"
