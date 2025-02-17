import os
import numpy as np  #type: ignore
import matplotlib.pyplot as plt #type: ignore
from matplotlib.patches import Circle, Rectangle, Polygon #type: ignore
from matplotlib.lines import Line2D #type: ignore
import matplotlib.patches as patches #type: ignore
from scipy.interpolate import griddata, Rbf  #type: ignore
from scipy.spatial import Voronoi  #type: ignore
import xml.etree.ElementTree as ET
from io import StringIO
from typing import List, Dict, Tuple, Any, Optional
from shapely.geometry import LineString, Point, Polygon, MultiPolygon  #type: ignore
from shapely.ops import unary_union  #type: ignore
import matplotlib.path as mpath  #type: ignore
import matplotlib.font_manager as fm  #type: ignore
import re
from pykrige.ok import OrdinaryKriging  #type: ignore
from mpl_toolkits.axes_grid1.inset_locator import inset_axes #type: ignore
from matplotlib.ticker import MaxNLocator #type: ignore
import time
from datetime import datetime

class MapGenerator:
    def __init__(self, config_manager, sensor_manager, logger):
        """
        온도맵 생성기를 초기화합니다.
        """
        self.logger = logger
        self.config_manager = config_manager
        self.sensor_manager = sensor_manager
        self.generation_time = ''
        self.generation_duration = ''
        self.current_map_id = None

        self.configs = {}
        self.walls_data = ''
        self.sensors_data = []
        self.get_sensor_state = self.sensor_manager.get_sensor_state
        self.parameters = {}
        self.gen_config = {}
        
        self.areas: List[Dict[str, Any]] = []  # area 폴리곤과 속성 저장용 (polygon, is_exterior)
        self.area_sensors: Dict[int, List[Tuple[Point, float, str]]] = {}  # area별 센서 그룹

        # 한글 폰트 설정
        self._setup_korean_font()
        self.logger.info("ThermalMapGenerator 초기화됨")

    def _setup_korean_font(self):
        """한글 폰트를 설정합니다."""
        try:
            font_paths = [
                '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',  # Linux 나눔고딕
            ]
            
            font_found = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    # 폰트 추가
                    fm.fontManager.addfont(font_path)
                    # 기본 폰트 설정
                    plt.rcParams['font.family'] = 'NanumGothic'  # 폰트 이름으로 직접 설정
                    font_found = True
                    break
            
            if not font_found:
                self.logger.warning("한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
                
            # 마이너스 기호 깨짐 방지
            plt.rcParams['axes.unicode_minus'] = False
            
        except Exception as e:
            self.logger.error(f"한글 폰트 설정 중 오류 발생: {str(e)}")
            
    def _parse_svg_path(self, d: str) -> Optional[Polygon]:
        """
        SVG path의 d 속성을 파싱하여 Shapely Polygon 객체를 반환합니다.
        여러 서브패스가 있다면, 첫 번째는 외부 윤곽(shell)으로,
        나머지는 내부 구멍(hole)으로 처리합니다.
        """
        try:
            # 대문자 명령어만 고려(M, L, Z)하는 간단한 파서 예제
            # 커맨드와 숫자들을 분리
            tokens = re.findall(r'([MLZmlz])|([-+]?\d*\.?\d+)', d)
            # tokens: 각 튜플은 (command, None) 또는 (None, number) 형태로 추출됨
            
            # 경로들을 저장할 리스트: 각 경로는 (x, y) 좌표의 리스트
            subpaths: List[List[Tuple[float, float]]] = []
            current_path: List[Tuple[float, float]] = []
            current_command = None
            idx = 0
            
            while idx < len(tokens):
                token = tokens[idx]
                if token[0]:  # 명령어인 경우
                    cmd = token[0].upper()
                    current_command = cmd
                    if cmd == 'M':
                        # 새로운 서브패스 시작. 만약 기존에 좌표가 있다면 추가하고 새로 시작
                        if current_path:
                            subpaths.append(current_path)
                        current_path = []
                        idx += 1
                        # M 다음에는 좌표쌍이 따라옴
                        if idx + 1 < len(tokens) and tokens[idx][1] and tokens[idx+1][1]:
                            x = float(tokens[idx][1])
                            y = float(tokens[idx+1][1])
                            current_path.append((x, y))
                            idx += 2
                        else:
                            break
                    elif cmd == 'L':
                        # L 커맨드는 좌표쌍을 따른다.
                        idx += 1
                        if idx + 1 < len(tokens) and tokens[idx][1] and tokens[idx+1][1]:
                            x = float(tokens[idx][1])
                            y = float(tokens[idx+1][1])
                            current_path.append((x, y))
                            idx += 2
                        else:
                            break
                    elif cmd == 'Z':
                        # Z는 현재 경로 닫음을 의미
                        # 닫힘 여부는 Polygon 생성 시 자동으로 처리되므로 그대로 둠
                        idx += 1
                    else:
                        # 다른 커맨드는 무시
                        idx += 1
                else:
                    # 숫자 토큰이 나온 경우 (정상적인 상황에서는 커맨드 다음이어야 함)
                    idx += 1
            
            # 마지막 서브패스 추가
            if current_path:
                subpaths.append(current_path)
            
            if not subpaths:
                return None
            
            # 첫 번째 서브패스는 외부 윤곽(shell), 나머지는 내부 구멍(hole)로 사용
            shell = subpaths[0]
            holes = subpaths[1:] if len(subpaths) > 1 else None
            
            poly = Polygon(shell, holes)
            if not poly.is_valid:
                # 단순한 다각형일 경우, buffer(0)로 보정 시도
                poly = poly.buffer(0)
            return poly
        except Exception as e:
            self.logger.error(f"SVG path 파싱 중 오류: {str(e)}")
            return None

    def _parse_areas(self) -> Tuple[List[Dict[str, Any]], Optional[ET.Element]]:
        """area 데이터를 파싱하여 Polygon과 속성 목록, XML 요소를 반환합니다."""
        try:
            svg_data = f'<svg>{self.walls_data}</svg>'
            
            tree = ET.parse(StringIO(svg_data))
            root = tree.getroot()

            self.areas = []
            
            # SVG 변환 행렬 확인
            transform = root.get('transform', '')
            self.logger.debug(f"SVG transform: {transform}")
            
            # path 요소 찾기
            paths = root.findall('.//{*}path')
            
            for i, path in enumerate(paths):
                # path의 스타일과 클래스 확인
                style = path.get('style', '')
                class_name = path.get('class', '')
                
                # exterior 클래스 여부 확인
                is_exterior = 'exterior' in class_name.lower() if class_name else False
                
                d = path.get('d', '')
                if not d:
                    self.logger.warning(f"Path {i}: 'd' 속성 없음")
                    continue
                
                # path별 transform 확인
                path_transform = path.get('transform', '')
                if path_transform:
                    self.logger.debug(f"Path {i} transform: {path_transform}")
                
                polygon = self._parse_svg_path(d)
                if polygon and polygon.is_valid:
                    self.areas.append({
                        'polygon': polygon,
                        'is_exterior': is_exterior
                    })
                    self.logger.debug(f"Path {i}: {'외부' if is_exterior else '내부'} 영역으로 파싱됨")
                else:
                    self.logger.warning(f"Path {i}: 유효한 폴리곤 생성 실패")

            self.logger.debug(f"총 {len(self.areas)}개의 area 파싱됨 (전체 path 중 {len(paths)}개)")
            return self.areas, root
            
        except Exception as e:
            self.logger.error(f"Area 파싱 중 오류 발생: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return [], None

    async def _collect_sensor_data(self) -> Tuple[List[List[float]], List[float], List[str]]:
        """센서 데이터를 수집하여 좌표, 온도값, 센서ID 리스트를 반환합니다."""
        points = []
        temperatures = []
        sensor_ids = []
        self.logger.debug(f"저장된 센서 데이터: {self.sensors_data}")
        for sensor in self.sensors_data:
            if 'position' not in sensor:
                continue
                
            position = sensor['position']
            if not position or 'x' not in position or 'y' not in position:
                self.logger.warning(f"{sensor['entity_id']} 센서에 position 데이터가 유효하지 않음")
                continue
                
            # 센서 상태 조회
            state = await self.get_sensor_state(sensor['entity_id'])
            if not state or not isinstance(state, dict):
                self.logger.warning(f"센서 {sensor['entity_id']} 상태 데이터가 유효하지 않음")
                continue
                
            try:
                # 온도값 파싱 및 보정값 적용
                raw_temp = float(state.get('state', 0))  # 상태값을 state 키에서 가져옴
                calibration = float(sensor.get('calibration', 0))  # 보정값이 없으면 0
                temp = raw_temp + calibration  # 보정값 적용
                
                points.append([position['x'], position['y']])
                temperatures.append(temp)
                sensor_ids.append(sensor['entity_id'])
                self.logger.debug(f"센서 {sensor['entity_id']}: 원본={raw_temp}°C, 보정값={calibration}°C, 보정후={temp}°C")
            except (ValueError, TypeError, AttributeError) as e:
                self.logger.error(f"센서 {sensor['entity_id']} 데이터 처리 중 오류: {str(e)}")
                continue
        
        return points, temperatures, sensor_ids

    def _assign_sensors_to_areas(self, points: List[List[float]], temperatures: List[float], sensor_ids: List[str]):
        """센서들을 해당하는 area에 할당합니다."""
        self.area_sensors.clear()
        
        # 각 area의 경계 버퍼 생성 (경계 근처의 센서를 포함하기 위해)
        buffered_areas = [(i, area['polygon'].buffer(1e-6)) for i, area in enumerate(self.areas)]
        
        for i, (point_coords, temp, sensor_id) in enumerate(zip(points, temperatures, sensor_ids)):
            point = Point(point_coords[0], point_coords[1])
            assigned = False
            
            # 정확한 포함 관계 확인
            for area_idx, area in enumerate(self.areas):
                if area['polygon'].contains(point):
                    if area_idx not in self.area_sensors:
                        self.area_sensors[area_idx] = []
                    self.area_sensors[area_idx].append((point, temp, sensor_id))
                    # self.logger.debug(f"센서 {sensor_id} (temp={temp:.1f}°C)가 Area {area_idx}에 정확히 포함됨")
                    assigned = True
                    break
            
            # 정확한 포함 관계가 없는 경우, 버퍼를 사용하여 재확인
            if not assigned:
                for area_idx, buffered_area in buffered_areas:
                    if buffered_area.contains(point):
                        if area_idx not in self.area_sensors:
                            self.area_sensors[area_idx] = []
                        self.area_sensors[area_idx].append((point, temp, sensor_id))
                        # self.logger.debug(f"센서 {sensor_id} (temp={temp:.1f}°C)가 Area {area_idx}의 경계 근처에 할당됨")
                        assigned = True
                        break
            
            # 여전히 할당되지 않은 경우, 가장 가까운 area에 할당
            if not assigned:
                min_distance = float('inf')
                nearest_area_idx = None
                
                for area_idx, area in enumerate(self.areas):
                    distance = area['polygon'].distance(point)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_area_idx = area_idx
                
                if nearest_area_idx is not None:
                    if nearest_area_idx not in self.area_sensors:
                        self.area_sensors[nearest_area_idx] = []
                    self.area_sensors[nearest_area_idx].append((point, temp, sensor_id))
                    # self.logger.warning(f"센서 {sensor_id} (temp={temp:.1f}°C)가 가장 가까운 Area {nearest_area_idx}에 할당됨 (거리: {min_distance:.2f})")
                else:
                    self.logger.error(f"센서 {sensor_id} (temp={temp:.1f}°C)를 할당할 수 있는 area를 찾지 못함")

        # 할당 결과 출력
        for area_idx, sensors in self.area_sensors.items():
            self.logger.info(f"Area {area_idx}: {len(sensors)}개의 센서, {[f'{sensor_id}:{temp:.1f}' for _, temp, sensor_id in sensors]}")

    def _calculate_area_temperature(self, area_idx: int, area: Dict[str, Any], grid_points: np.ndarray, 
                                   grid_x: np.ndarray, grid_y: np.ndarray, min_x: float, max_x: float, 
                                   min_y: float, max_y: float) -> np.ndarray:
        """특정 area의 온도 분포를 계산합니다."""
        try:
            # area 마스크 생성
            area_mask = np.array([area['polygon'].contains(Point(x, y)) for x, y in grid_points])
            area_mask = area_mask.reshape(grid_x.shape)
            temps = np.full_like(grid_x[area_mask], np.nan)
            
            if area_idx not in self.area_sensors:
                return temps
            
            # 센서가 있는 area
            sensors = self.area_sensors[area_idx]
            sensor_locs = np.array([[p.x, p.y] for p, _, _ in sensors])
            sensor_temps = np.array([t for _, t, _ in sensors])
            mask_points = grid_points[area_mask.flatten()]
            
            # 가우시안 분포 계산 함수
            def calculate_gaussian_distribution(points, locs, temps, sigma):
                weighted_temps = np.zeros_like(points[:, 0])
                weight_sum = np.zeros_like(points[:, 0])
                
                for loc, temp in zip(locs, temps):
                    distances = np.sqrt(np.sum((points - loc) ** 2, axis=1))
                    weights = np.exp(-(distances ** 2) / (2 * sigma ** 2))
                    weighted_temps += weights * temp
                    weight_sum += weights
                
                return weighted_temps / (weight_sum + 1e-10)
            
            # 센서 개수에 따른 처리
            sensor_count = len(sensors)
            area_width = max_x - min_x
            area_height = max_y - min_y
            
            # 가우시안 sigma 계산
            sigma = min(area_width, area_height) / self.parameters['gaussian']['sigma_factor']
            
            if sensor_count == 1:  # 단일 센서: 가우시안 분포
                self.logger.debug(f"Area {area_idx}: {sensor_count}개 센서 - 가우시안 분포 적용")
                temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
                
            elif sensor_count <= 3:  # 2~3개 센서: RBF -> 가우시안
                try:
                    self.logger.debug(f"Area {area_idx}: {sensor_count}개 센서 - RBF 보간 시도")
                    # RBF 보간기 설정
                    rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                            function=self.parameters['rbf']['function'],
                            epsilon=min(area_width, area_height) / self.parameters['rbf']['epsilon_factor'])
                    
                    # RBF 예측 수행
                    temps = rbf(mask_points[:, 0], mask_points[:, 1])
                    
                    # 예측값 범위 제한
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.1 * (temp_max - temp_min)  # 10% 마진
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                    
                    self.logger.debug(f"Area {area_idx}: RBF 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                    
                except Exception as rbf_error:
                    self.logger.warning(f"Area {area_idx} RBF 보간 실패, 가우시안 분포로 대체: {str(rbf_error)}")
                    temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
                
            else:  # 4개 이상: 크리깅 -> RBF -> 가우시안
                try:
                    # 데이터 전처리: 중복된 위치 제거
                    unique_locs = {}
                    for loc, temp in zip(sensor_locs, sensor_temps):
                        key = (loc[0], loc[1])
                        if key not in unique_locs:
                            unique_locs[key] = []
                        unique_locs[key].append(temp)
                    
                    unique_sensor_locs = np.array(list(unique_locs.keys()))
                    unique_sensor_temps = np.array([np.mean(temps) for temps in unique_locs.values()])
                    
                    # 크리깅 모델 생성
                    ok = OrdinaryKriging(
                        unique_sensor_locs[:, 0],
                        unique_sensor_locs[:, 1],
                        unique_sensor_temps,
                        **self.parameters['kriging']
                    )
                    
                    # 크리깅 예측 수행
                    temps, variances = ok.execute('points', mask_points[:, 0], mask_points[:, 1])
                    
                    # 예측값 범위 제한
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.5 * (temp_max - temp_min)  # 50% 마진
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                    
                    self.logger.debug(f"Area {area_idx}: 크리깅 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                    
                except Exception as kriging_error:
                    self.logger.warning(f"Area {area_idx} 크리깅 보간 실패, RBF 시도: {str(kriging_error)}")
                    try:
                        # RBF 보간 시도
                        rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                                function=self.parameters['rbf']['function'],
                                epsilon=min(area_width, area_height) / self.parameters['rbf']['epsilon_factor'])
                        temps = rbf(mask_points[:, 0], mask_points[:, 1])
                        
                        # 예측값 범위 제한
                        temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                        margin = 0.1 * (temp_max - temp_min)
                        temps = np.clip(temps, temp_min - margin, temp_max + margin)
                        
                        self.logger.debug(f"Area {area_idx}: RBF 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                        
                    except Exception as rbf_error:
                        self.logger.warning(f"Area {area_idx} RBF 보간도 실패, 가우시안 분포로 대체: {str(rbf_error)}")
                        temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
            
            # NaN 처리
            if np.any(np.isnan(temps)):
                self.logger.debug(f"Area {area_idx}: NaN 값을 nearest로 채우기")
                nearest_temps = griddata(sensor_locs, sensor_temps, mask_points, method='nearest')
                temps[np.isnan(temps)] = nearest_temps[np.isnan(temps)]
            
            return temps
            
        except Exception as e:
            self.logger.error(f"Area {area_idx} 온도 계산 중 오류: {str(e)}")
            return np.full_like(grid_x[area_mask], np.nan)

    def _get_polygon_coords(self, geom) -> List[Tuple[np.ndarray, np.ndarray]]:
        """폴리곤 또는 멀티폴리곤에서 좌표를 추출합니다."""
        coords = []
        if isinstance(geom, Polygon):
            coords.append((np.array(geom.exterior.xy[0]), np.array(geom.exterior.xy[1])))
        elif isinstance(geom, MultiPolygon):
            for polygon in geom.geoms:
                coords.append((np.array(polygon.exterior.xy[0]), np.array(polygon.exterior.xy[1])))
        return coords

    def load_map_config(self, map_id: str):
        """맵 설정 로드"""
        self.current_map_id = map_id
        self.configs = self.config_manager.db.get_map(map_id)
        self.walls_data = self.configs.get('walls', '')
        self.sensors_data = self.configs.get('sensors', [])
        self.parameters = self.configs.get('parameters', {})
        self.gen_config = self.configs.get('gen_config', {})

    def save_generation_time(self):
        """생성 시간 저장"""
        if not self.current_map_id:
            return
        map_data = self.config_manager.db.get_map(self.current_map_id)
        map_data['last_generation'] = {
            'timestamp': datetime.now().isoformat(),
            'duration': self.generation_duration
        }
        self.config_manager.db.save(self.current_map_id, map_data)

    def _create_sensor_marker(self, point, temperature, sensor_id, state):
        """센서 마커를 생성합니다."""
        try:
            # 센서 표시 설정 가져오기
            sensor_display = self.gen_config.get('visualization', {}).get('sensor_display', 'position_temp')
            sensor_info_bg = self.gen_config.get('visualization', {}).get('sensor_info_bg', {})
            sensor_marker = self.gen_config.get('visualization', {}).get('sensor_marker', {})
            sensor_name = self.gen_config.get('visualization', {}).get('sensor_name', {})
            sensor_temp = self.gen_config.get('visualization', {}).get('sensor_temp', {})

            # 마커 스타일 설정
            marker_style = sensor_marker.get('style', 'circle')
            marker_size = sensor_marker.get('size', 10)
            marker_color = sensor_marker.get('color', '#FF0000')

            # 마커 생성
            if marker_style == 'circle':
                marker = Circle((point[0], point[1]), marker_size/2)
                marker.set_facecolor(marker_color)
                marker.set_zorder(5)
            elif marker_style == 'square':
                marker = Rectangle((point[0]-marker_size/2, point[1]-marker_size/2), marker_size, marker_size)
                marker.set_facecolor(marker_color)
                marker.set_zorder(5)
            elif marker_style == 'triangle':
                vertices = np.array([
                    [point[0], point[1]-marker_size/2],
                    [point[0]+marker_size/2, point[1]+marker_size/2],
                    [point[0]-marker_size/2, point[1]+marker_size/2]
                ])
                marker = patches.Polygon(vertices, fc=marker_color)
                marker.set_zorder(5)
            elif marker_style == 'star':
                vertices = []
                for i in range(5):
                    angle = (i * 72 - 90) * np.pi / 180
                    vertices.append([point[0] + marker_size * np.cos(angle),
                                   point[1] + marker_size * np.sin(angle)])
                    inner_angle = ((i * 72 + 36) - 90) * np.pi / 180
                    vertices.append([point[0] + marker_size * 0.4 * np.cos(inner_angle),
                                   point[1] + marker_size * 0.4 * np.sin(inner_angle)])
                marker = patches.Polygon(np.array(vertices), fc=marker_color)
                marker.set_zorder(5)
            elif marker_style == 'cross':
                marker = Line2D([point[0]-marker_size/2, point[0]+marker_size/2],
                              [point[1], point[1]], color=marker_color)
                marker.set_zorder(5)
                marker2 = Line2D([point[0], point[0]],
                               [point[1]-marker_size/2, point[1]+marker_size/2],
                               color=marker_color)
                marker2.set_zorder(5)
                plt.gca().add_artist(marker2)
            else:
                marker = Circle((point[0], point[1]), marker_size/2)
                marker.set_facecolor(marker_color)
                marker.set_zorder(5)

            plt.gca().add_artist(marker)

            # 텍스트 표시 설정
            if sensor_display != 'none' and sensor_display != 'position':
                name = state.get('attributes', {}).get('friendly_name', sensor_id.split('.')[-1])
                text = ''
                
                if 'name' in sensor_display:
                    text = name
                    font_size = sensor_name.get('font_size', 12)
                    font_color = sensor_name.get('color', '#000000')
                
                if 'temp' in sensor_display:
                    if text:
                        text += '\n'
                    text += f'{temperature:.1f}°C'
                    if 'name' not in sensor_display:
                        font_size = sensor_temp.get('font_size', 12)
                        font_color = sensor_temp.get('color', '#000000')

                # 배경 설정
                bg_color = sensor_info_bg.get('color', '#FFFFFF')
                bg_opacity = sensor_info_bg.get('opacity', 70) / 100
                bg_padding = sensor_info_bg.get('padding', 5)
                bg_border_radius = sensor_info_bg.get('border_radius', 4)
                bg_border_width = sensor_info_bg.get('border_width', 1)
                bg_border_color = sensor_info_bg.get('border_color', '#000000')
                bg_position = sensor_info_bg.get('position', 'right')
                bg_distance = sensor_info_bg.get('distance', 10)

                # 텍스트 위치 계산
                text_x, text_y = point[0], point[1]
                if bg_position == 'right':
                    text_x = point[0] + marker_size/2 + bg_distance
                    text_y = point[1]
                elif bg_position == 'left':
                    text_x = point[0] - marker_size/2 - bg_distance
                    text_y = point[1]
                elif bg_position == 'top':
                    text_x = point[0]
                    text_y = point[1] - marker_size/2 - bg_distance
                elif bg_position == 'bottom':
                    text_x = point[0]
                    text_y = point[1] + marker_size/2 + bg_distance
                elif bg_position == 'top-right':
                    text_x = point[0] + marker_size/2 + bg_distance/1.4
                    text_y = point[1] - marker_size/2 - bg_distance/1.4
                elif bg_position == 'top-left':
                    text_x = point[0] - marker_size/2 - bg_distance/1.4
                    text_y = point[1] - marker_size/2 - bg_distance/1.4
                elif bg_position == 'bottom-right':
                    text_x = point[0] + marker_size/2 + bg_distance/1.4
                    text_y = point[1] + marker_size/2 + bg_distance/1.4
                elif bg_position == 'bottom-left':
                    text_x = point[0] - marker_size/2 - bg_distance/1.4
                    text_y = point[1] + marker_size/2 + bg_distance/1.4

                # 텍스트 정렬 설정
                halign = 'center'
                valign = 'center'
                if 'right' in bg_position:
                    halign = 'left'
                elif 'left' in bg_position:
                    halign = 'right'
                if 'top' in bg_position:
                    valign = 'bottom'
                elif 'bottom' in bg_position:
                    valign = 'top'

                # 텍스트 추가
                plt.text(text_x, text_y, text,
                        horizontalalignment=halign,
                        verticalalignment=valign,
                        fontsize=font_size,
                        color=font_color,
                        bbox=dict(
                            facecolor=bg_color,
                            alpha=bg_opacity,
                            edgecolor=bg_border_color if bg_border_width > 0 else 'none',
                            linewidth=bg_border_width,
                            pad=bg_padding,
                            boxstyle=f'round,pad={bg_padding/10},rounding_size={bg_border_radius}'
                        ),
                        zorder=6)

        except Exception as e:
            self.logger.error(f"센서 마커 생성 중 오류 발생: {str(e)}")

    async def generate(self, map_id: str, output_path: str) -> bool:
        """
        온도맵을 생성하고 이미지 파일로 저장합니다.
        
        Args:
            output_path: 출력 이미지 파일 경로
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 출력 디렉토리 확인 및 생성
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    parent_dir = os.path.dirname(output_dir)
                    if parent_dir and not os.path.exists(parent_dir):
                        self.logger.info(f"상위 디렉토리가 없습니다. 전체 경로를 생성합니다: {output_dir}")
                    os.makedirs(output_dir, exist_ok=True)
                    self.logger.info(f"출력 디렉토리 생성 완료: {output_dir}")
                except Exception as dir_error:
                    self.logger.error(f"출력 디렉토리 생성 실패 ({output_dir}): {str(dir_error)}")
                    return False

            self.current_map_id = map_id
            if not self.current_map_id:
                self.logger.error("현재 선택된 맵이 없습니다")
                return False
            self.load_map_config(self.current_map_id)

            # walls_data와 sensors_data 유효성 검사
            if not self.walls_data or len(self.sensors_data) == 0:
                self.logger.error("벽 데이터 또는 센서 데이터가 없습니다")
                return False
            
            timestamp_start = time.time_ns()

            # 설정된 온도 범위 가져오기
            min_temp = self.gen_config.get('colorbar', {}).get('min_temp', 0)
            max_temp = self.gen_config.get('colorbar', {}).get('max_temp', 40)
            
            # area 데이터 파싱
            areas, root = self._parse_areas()
            if not areas:
                self.logger.error("유효한 area를 찾을 수 없습니다")
                return False

            # 센서 데이터 수집
            sensor_points, raw_temps, sensor_ids = await self._collect_sensor_data()
            if not sensor_points:
                self.logger.error("유효한 센서 데이터가 없습니다")
                return False
            temperatures = raw_temps
            # 온도값 범위 제한 적용
            if min_temp is not None:
                temperatures = [max(t, min_temp) for t in raw_temps]
            if max_temp is not None:
                temperatures = [min(t, max_temp) for t in raw_temps]
                
            # 센서를 area에 할당
            self._assign_sensors_to_areas(sensor_points, temperatures, sensor_ids)

            # SVG 전체 크기 사용
            min_x, min_y, max_x, max_y = 0, 0, 1000, 1000
            
            # 격자 생성
            grid_x, grid_y = np.mgrid[
                min_x:max_x:150j,
                min_y:max_y:150j
            ]

            # 전체 마스크와 온도 배열 초기화
            grid_z = np.full_like(grid_x, np.nan)
            grid_points = np.column_stack((grid_x.flatten(), grid_y.flatten()))
            
            # 각 area별로 온도 계산
            for area_idx, area in enumerate(self.areas):
                area_temps = self._calculate_area_temperature(
                    area_idx, area, grid_points, grid_x, grid_y,
                    min_x, max_x, min_y, max_y
                )
                # area 마스크 생성 및 결과 할당
                area_mask = np.array([area['polygon'].contains(Point(x, y)) for x, y in grid_points])
                area_mask = area_mask.reshape(grid_x.shape)
                grid_z[area_mask] = area_temps

            # 플롯 생성
            fig = plt.figure(figsize=(10, 10))  # 전체 figure 크기

            # 메인 플롯 (열지도)
            main_ax = plt.subplot2grid((1, 20), (0, 0), colspan=20)  # 열지도용 axes
            main_ax.invert_yaxis()

            # 온도 범위 설정
            temp_range = min_temp - max_temp
            steps = self.gen_config.get('colorbar', {}).get('temp_steps', 100)
            levels = np.linspace(min_temp - 0.1 * temp_range, max_temp + 0.1 * temp_range, steps)

            # 온도 데이터가 없는 area 표시
            for i, area in enumerate(self.areas):
                if i not in self.area_sensors:
                    empty_area_style = self.gen_config.get('visualization', {}).get('empty_area', 'white')
                    if empty_area_style == 'white':
                        for x, y in self._get_polygon_coords(area['polygon']):
                            main_ax.fill(x, y, facecolor='white', alpha=1.0, edgecolor='none')
                    elif empty_area_style == 'transparent':
                        # transparent 스타일인 경우 해당 영역을 건너뜀
                        continue
                    elif empty_area_style == 'hatched':
                        for x, y in self._get_polygon_coords(area['polygon']):
                            main_ax.fill(x, y, facecolor='white', hatch='///', alpha=1.0, edgecolor='none')

            # 온도 분포 그리기 (부드러운 그라데이션을 위한 설정)
            contour = main_ax.contourf(grid_x, grid_y, grid_z,
                                   levels=levels,
                                   cmap=self.gen_config.get('colorbar', {}).get('cmap', 'RdYlBu_r'),
                                   extend='both',
                                   alpha=0.9)  # 약간의 투명도 추가
            
            # area 경계 그리기
            area_border_width = self.gen_config.get('visualization', {}).get('area_border_width', 2)
            area_border_color = self.gen_config.get('visualization', {}).get('area_border_color', '#000000')
            if area_border_width > 0:  # 선 두께가 0보다 큰 경우에만 그리기
                for area in self.areas:
                    if not area['is_exterior']:
                        for x, y in self._get_polygon_coords(area['polygon']):
                            main_ax.plot(x, y, color=area_border_color, linewidth=area_border_width)

            # plot 외곽선 그리기
            plot_border_width = self.gen_config.get('visualization', {}).get('plot_border_width', 0)
            plot_border_color = self.gen_config.get('visualization', {}).get('plot_border_color', '#000000')
            if plot_border_width > 0:  # 선 두께가 0보다 큰 경우에만 그리기
                for spine in ['top', 'bottom', 'left', 'right']:
                    main_ax.spines[spine].set_linewidth(plot_border_width)
                    main_ax.spines[spine].set_color(plot_border_color)
                    main_ax.spines[spine].set_visible(True)

            # 센서 표시 설정
            sensor_display = self.gen_config.get('visualization', {}).get('sensor_display', 'position_name_temp')
            
            if sensor_display != 'none':  # 'none'이 아닐 때만 센서 표시
                # 센서 위치 표시
                for point, temperature, sensor_id in zip(sensor_points, raw_temps, sensor_ids):
                    try:
                        state = await self.get_sensor_state(sensor_id)
                        if not state or not isinstance(state, dict):
                            continue
                        self._create_sensor_marker([point[0], point[1]], temperature, sensor_id, state)
                    except Exception as e:
                        self.logger.warning(f"센서 {sensor_id} 표시 실패: {str(e)}")
                        continue

            # 컬러바 설정 적용
            colorbar_config = self.gen_config.get('colorbar', {})
            if colorbar_config and colorbar_config.get('show_colorbar', True):  # 컬러바 표시 여부 확인
                # 컬러바 위치 및 크기 설정
                width = colorbar_config.get('width', 5)
                height = colorbar_config.get('height', 100)
                location = colorbar_config.get('location', 'right')
                orientation = colorbar_config.get('orientation', 'vertical')
                borderpad = colorbar_config.get('borderpad',0)
                # orientation에 따라 width와 height 조정
                if orientation == 'horizontal':
                    # 가로 방향일 경우 width와 height를 교체
                    width, height = height, width
                
                # 컬러바 생성
                cax = inset_axes(main_ax,
                 width=f'{width}%',
                 height=f'{height}%',
                 loc=location,
                 borderpad=borderpad)
                cbar = fig.colorbar(contour, cax=cax, orientation=orientation)
                
                # 컬러바의 major locator를 정수로 설정
                cbar.locator = MaxNLocator(integer=True)
                cbar.update_ticks()
                # 레이블 설정
                if colorbar_config.get('show_label', True):
                    label = colorbar_config.get('label', '온도 (°C)')
                    font_size = colorbar_config.get('font_size', 12)
                    cbar.set_label(label, fontsize=font_size)

                # 눈금 크기 설정
                tick_size = colorbar_config.get('tick_size', 10)
                cbar.ax.tick_params(labelsize=tick_size)

            # 축 설정
            main_ax.set_aspect('equal')
            main_ax.axis('off')

            # 저장 (dpi 조정으로 1000x1000 크기 맞추기)
            width_inches = fig.get_size_inches()[0]  # 메인 플롯의 실제 너비
            dpi = 1000 / (width_inches)  # 1000px 위해 필요한 dpi 계산
            
            format = self.config_manager.get_output_format(self.current_map_id)
            plt.savefig(output_path,
                       bbox_inches='tight',
                       pad_inches=0,
                       dpi=dpi,
                       facecolor='none',  # 배경색을 none으로 변경
                       transparent=True,
                       format=format)
            plt.close()
            
            # 생성 시간 정보 업데이트
            timestamp_end = time.time_ns()
            self.generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.generation_duration = f'{((timestamp_end - timestamp_start)/1000000000):.3f}s'
            
            self.save_generation_time()
            
            return True

        except Exception as e:
            self.logger.error(f"온도맵 생성 중 오류 발생: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False 