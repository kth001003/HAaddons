import json
from filelock import FileLock #type: ignore

class JsonDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = FileLock(f"{self.db_path}.lock")

    def load(self) -> dict:
        """DB 전체 내용을 딕셔너리로 반환합니다."""
        with self.lock:
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    try:
                        return json.load(f)
                    except json.JSONDecodeError:
                        return {}
            except FileNotFoundError:
                return {}

    def save(self, map_id, map_data) -> None:
        """ID에 해당하는 내용을 저장하거나 업데이트합니다."""
        with self.lock:
            db = self.load()
            db[map_id] = map_data
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=4)

    def delete(self, map_id) -> bool:
        """특정 ID의 데이터를 삭제합니다. 삭제되면 True, 없으면 False 반환."""
        with self.lock:
            db = self.load()

            if map_id in db:
                del db[map_id]
                with open(self.db_path, 'w', encoding='utf-8') as f:
                    json.dump(db, f, indent=4)

                return True
            return False

    def update_all(self, key, value) -> int:
        """
        모든 ID에 대해 동일한 key-value 쌍을 추가 또는 수정합니다.
        - key: 추가하거나 수정할 키 이름
        - value: 해당 키에 설정할 값
        - 반환값: 업데이트된 항목의 개수
        """
        with self.lock:
            db = self.load()
            updated_count = 0
            for item_key, item_value in db.items():
                if item_value.get(key) != value:  # 값이 다를 때만 업데이트
                    item_value[key] = value
                    updated_count += 1
            if updated_count > 0:
                with open(self.db_path, 'w', encoding='utf-8') as f:
                    json.dump(db, f, indent=4)
            return updated_count

    def get_all_maps(self) -> list:
        """모든 맵의 목록을 반환합니다."""
        db = self.load()
        maps = []
        for map_id, map_data in db.items():
            if isinstance(map_data, dict) and 'name' in map_data:
                maps.append({
                    'id': map_id,
                    'name': map_data['name'],
                    'created_at': map_data.get('created_at', ''),
                    'updated_at': map_data.get('updated_at', ''),
                    'walls': map_data.get('walls', '')
                })
        return maps

    def get_map(self, map_id: str) -> dict:
        """특정 맵의 상세 정보를 반환합니다."""
        db = self.load()
        return db.get(map_id, {})