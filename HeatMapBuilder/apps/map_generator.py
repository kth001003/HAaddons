import os
import re
import time
from datetime import datetime
from io import StringIO
from multiprocessing import Pool, cpu_count
from typing import List, Dict, Tuple, Any, Optional

import numpy as np  #type: ignore
import matplotlib.pyplot as plt  #type: ignore
import matplotlib.font_manager as fm  #type: ignore
import matplotlib.patches as patches  #type: ignore
from matplotlib.lines import Line2D  #type: ignore
from matplotlib.patches import Circle, Rectangle, Polygon  #type: ignore
from matplotlib.ticker import MaxNLocator  #type: ignore
from mpl_toolkits.axes_grid1.inset_locator import inset_axes  #type: ignore
import matplotlib.patheffects as path_effects  #type: ignore
from scipy.interpolate import griddata, Rbf  #type: ignore
import xml.etree.ElementTree as ET
from shapely.geometry import Point, Polygon, MultiPolygon  #type: ignore
from shapely.vectorized import contains  #type: ignore
from pykrige.ok import OrdinaryKriging  #type: ignore

class MapGenerator:
    def __init__(self, config_manager, sensor_manager, logger):
        """
        온도맵 생성기를 초기화합니다.
        """
        self.logger = logger
        self.config_manager = config_manager
        self.sensor_manager = sensor_manager

        self.configs = {}
        self.walls_data = ''
        self.sensors_data = []
        self.parameters = {}
        self.gen_config = {}
        
        self.areas: List[Dict[str, Any]] = []  # area 폴리곤과 속성 저장용 (polygon, is_exterior)
        self.area_sensors: Dict[int, List[Tuple[Point, float, str]]] = {}  # area별 센서 그룹

        # 한글 폰트 설정
        self._setup_korean_font()

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
            
            # path 요소 찾기
            paths = root.findall('.//{*}path')
            
            for i, path in enumerate(paths):
                class_name = path.get('class', '')
                
                # exterior 클래스 여부 확인
                is_exterior = 'exterior' in class_name.lower() if class_name else False
                
                d = path.get('d', '')
                if not d:
                    self.logger.warning(f"Path {i}: 'd' 속성 없음")
                    continue
                
                polygon = self._parse_svg_path(d)
                if polygon and polygon.is_valid:
                    self.areas.append({
                        'polygon': polygon,
                        'is_exterior': is_exterior
                    })
                else:
                    self.logger.warning(f"Path {i}: 유효한 폴리곤 생성 실패")

            self.logger.debug("총 %s개의 area 파싱됨 (전체 path 중 %s개)",
                             self.logger._colorize(len(self.areas), "green"),
                             self.logger._colorize(len(paths), "blue"))
            return self.areas, root
            
        except Exception as e:
            self.logger.error(f"Area 파싱 중 오류 발생: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return [], None

    async def _collect_sensor_data(self, states_dict: Dict[str, Dict[str, Any]]) -> Tuple[List[List[float]], List[float], List[str]]:
        """센서 데이터를 수집하여 좌표, 온도값, 센서ID 리스트를 반환합니다."""
        points = []
        temperatures = []
        sensor_ids = []
        
        self.logger.debug("상태조회 대상 센서 %s개", 
                          self.logger._colorize(len(self.sensors_data), "blue"))
                          
        for sensor in self.sensors_data:
            if 'position' not in sensor:
                continue
                
            position = sensor['position']
            if not position or 'x' not in position or 'y' not in position:
                self.logger.warning("%s 센서에 position 데이터가 유효하지 않음",
                                    self.logger._colorize(sensor['entity_id'], "red"))
                continue
                
            state = states_dict.get(sensor['entity_id'], {'state': '0', 'entity_id': sensor['entity_id']})
            
            try:
                # 온도값 파싱 및 보정값 적용
                raw_state = state.get('state', '0')  # 상태값을 state 키에서 가져옴
                
                # unavailable, unknown, N/A 등의 값 체크
                if raw_state.lower() in ['unavailable', 'unknown', 'n/a', 'null', 'none']:
                    self.logger.warning("%s 센서를 사용할 수 없습니다 (상태: %s)",
                                        self.logger._colorize(sensor['entity_id'], "red"),
                                        self.logger._colorize(raw_state, "yellow"))
                    continue
                    
                raw_temp = float(raw_state)
                calibration = float(sensor.get('calibration', 0))  # 보정값이 없으면 0
                temp = raw_temp + calibration  # 보정값 적용
                
                points.append([position['x'], position['y']])
                temperatures.append(temp)
                sensor_ids.append(sensor['entity_id'])
                self.logger.debug("센서 %s: 원본=%s%s, 보정값=%s%s, 보정후=%s%s",
                                 self.logger._colorize(sensor['entity_id'], "blue"),
                                 self.logger._colorize(raw_temp, "yellow"),
                                 self.logger._colorize(self.unit, "blue"),
                                 self.logger._colorize(calibration, "yellow"),
                                 self.logger._colorize(self.unit, "blue"),
                                 self.logger._colorize(temp, "green"),
                                 self.logger._colorize(self.unit, "blue"))
            except (ValueError, TypeError, AttributeError) as e:
                self.logger.error("센서 %s 데이터 처리 중 오류: %s",
                                 self.logger._colorize(sensor['entity_id'], "red"),
                                 self.logger._colorize(str(e), "red"))
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
                    assigned = True
                    break
            
            # 정확한 포함 관계가 없는 경우, 버퍼를 사용하여 재확인
            if not assigned:
                for area_idx, buffered_area in buffered_areas:
                    if buffered_area.contains(point):
                        if area_idx not in self.area_sensors:
                            self.area_sensors[area_idx] = []
                        self.area_sensors[area_idx].append((point, temp, sensor_id))
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
                else:
                    self.logger.warning("센서 %s (temp=%s%s)를 할당할 수 있는 area를 찾지 못함",
                                        self.logger._colorize(sensor_id, "red"),
                                        self.logger._colorize(temp, "yellow"),
                                        self.logger._colorize(self.unit, "blue"))

        # 할당 결과 출력
        for area_idx, sensors in self.area_sensors.items():
            self.logger.debug("Area %s: %s개의 센서, %s",
                             self.logger._colorize(area_idx, "green"),
                             self.logger._colorize(len(sensors), "blue"),
                             self.logger._colorize([f'{sensor_id}:{temp:.1f}{self.unit}' for _, temp, sensor_id in sensors], "white"))

    @staticmethod
    def _calculate_area_temperature_static(area_idx: int, area: Dict[str, Any], grid_points: np.ndarray,
                                       grid_x: np.ndarray, grid_y: np.ndarray, min_x: float, max_x: float,
                                       min_y: float, max_y: float, area_sensors: Dict[int, List[Tuple[Point, float, str]]],
                                       parameters: Dict) -> np.ndarray:
        """특정 area의 온도 분포를 계산합니다."""
        try:
            pmask = np.array(contains(area['polygon'], grid_points[:, 0], grid_points[:, 1]))
            area_mask = pmask.reshape(grid_x.shape)
            temps = np.full_like(grid_x[area_mask], np.nan)
            
            if area_idx not in area_sensors:
                return temps
            
            # 센서가 있는 area
            sensors = area_sensors[area_idx]
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
            sigma = min(area_width, area_height) / parameters['gaussian']['sigma_factor']
            
            if sensor_count == 1:  # 단일 센서: 단일값 적용
                temps = np.full_like(mask_points[:, 0], sensor_temps[0])
            elif sensor_count <= 3:
                try:
                    rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                            function=parameters['rbf']['function'],
                            epsilon=min(area_width, area_height) / parameters['rbf']['epsilon_factor'])
                    temps = rbf(mask_points[:, 0], mask_points[:, 1])
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.1 * (temp_max - temp_min)
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                except Exception:
                    temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
            else:
                try:
                    unique_locs = {}
                    for loc, temp in zip(sensor_locs, sensor_temps):
                        key = (loc[0], loc[1])
                        if key not in unique_locs:
                            unique_locs[key] = []
                        unique_locs[key].append(temp)
                    unique_sensor_locs = np.array(list(unique_locs.keys()))
                    unique_sensor_temps = np.array([np.mean(temps) for temps in unique_locs.values()])
                    ok = OrdinaryKriging(
                        unique_sensor_locs[:, 0],
                        unique_sensor_locs[:, 1],
                        unique_sensor_temps,
                        **parameters['kriging']
                    )
                    temps, _ = ok.execute('points', mask_points[:, 0], mask_points[:, 1])
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.5 * (temp_max - temp_min)
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                except Exception:
                    try:
                        rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                                function=parameters['rbf']['function'],
                                epsilon=min(area_width, area_height) / parameters['rbf']['epsilon_factor'])
                        temps = rbf(mask_points[:, 0], mask_points[:, 1])
                        temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                        margin = 0.1 * (temp_max - temp_min)
                        temps = np.clip(temps, temp_min - margin, temp_max + margin)
                    except Exception:
                        temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
            
            if np.any(np.isnan(temps)):
                nearest_temps = griddata(sensor_locs, sensor_temps, mask_points, method='nearest')
                temps[np.isnan(temps)] = nearest_temps[np.isnan(temps)]
            
            return temps
            
        except Exception as e:
            return np.full_like(grid_x[area_mask], np.nan)

    @staticmethod
    def _process_area_static(args: Tuple[int, Dict[str, Any], np.ndarray, np.ndarray, np.ndarray, float, float, float, float, Dict[int, List[Tuple[Point, float, str]]], Dict]) -> Tuple[int, np.ndarray, np.ndarray]:
        """멀티프로세싱용 area 처리 함수"""
        area_idx, area, grid_points, grid_x, grid_y, min_x, max_x, min_y, max_y, area_sensors, parameters = args
        
        try:
            print(f"[프로세스] Area {area_idx} 처리 시작")  # 프로세스 내부 로그
            area_temps = MapGenerator._calculate_area_temperature_static(
                area_idx, area, grid_points, grid_x, grid_y,
                min_x, max_x, min_y, max_y, area_sensors, parameters
            )
            print(f"[프로세스] Area {area_idx} 온도 계산 완료")  # 프로세스 내부 로그
            
            # area 마스크 생성
            pmask = np.array(contains(area['polygon'], grid_points[:, 0], grid_points[:, 1]))
            area_mask = pmask.reshape(grid_x.shape)
            print(f"[프로세스] Area {area_idx} 마스크 생성 완료")  # 프로세스 내부 로그
            
            return area_idx, area_temps, area_mask
            
        except Exception as e:
            print(f"[프로세스] Area {area_idx} 처리 중 오류 발생: {str(e)}")  # 프로세스 내부 로그
            import traceback
            print(traceback.format_exc())  # 프로세스 내부 로그
            raise

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
        self.configs = self.config_manager.db.get_map(map_id)
        self.walls_data = self.configs.get('walls', '')
        self.sensors_data = self.configs.get('sensors', [])
        self.parameters = self.configs.get('parameters', {})
        self.gen_config = self.configs.get('gen_config', {})
        self.unit = self.configs.get('unit', '')

    def save_generation_time(self, map_id: str, generation_time: str, generation_duration: str):
        """생성 시간 저장"""
        if not map_id:
            return
        map_data = self.config_manager.db.get_map(map_id)
        map_data['last_generation'] = {
            'timestamp': generation_time,
            'duration': generation_duration
        }
        # 이미지 URL 업데이트
        output_filename = self.config_manager.get_output_filename(map_id)
        map_data['img_url'] = f'/local/HeatMapBuilder/{map_id}/{output_filename}?{generation_time}'
        
        self.config_manager.db.save(map_id, map_data)

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
                    text += f'{temperature:.1f}{self.unit}'
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

    def _create_colorbar(self, fig, im, colorbar_config):
        """컬러바를 생성합니다."""
        
        show_label = colorbar_config.get('show_label', True)
        label = colorbar_config.get('label', self.unit)
        label_color = colorbar_config.get('label_color', '#000000')
        tick_size = colorbar_config.get('tick_size', 10)
        show_shadow = colorbar_config.get('show_shadow', True)
        shadow_color = colorbar_config.get('shadow_color', '#FFFFFF')
        shadow_width = colorbar_config.get('shadow_width', 3)
        shadow_x_offset = colorbar_config.get('shadow_x_offset', 1)
        shadow_y_offset = colorbar_config.get('shadow_y_offset', 1)
        orientation = colorbar_config.get('orientation', 'vertical')
        location = colorbar_config.get('location', 'right')
        width = colorbar_config.get('width', 5)
        height = colorbar_config.get('height', 80)
        pad = colorbar_config.get('borderpad', 0)

        if orientation == 'horizontal':
            width, height = height, width
        main_ax = fig.gca()
        cax = inset_axes(main_ax,
                        width=f'{width}%',
                        height=f'{height}%',
                        loc=location,
                        borderpad=pad)

        cbar = fig.colorbar(im, cax=cax, orientation=orientation)

        if show_label:
            # 그림자 효과 설정
            path_effects_list = []
            if show_shadow:
                path_effects_list.append(path_effects.withStroke(linewidth=shadow_width, 
                                                               foreground=shadow_color,
                                                               offset=(shadow_x_offset, shadow_y_offset * -1)))
            
            # 레이블과 눈금에 그림자 효과 적용
            cbar.set_label(label, 
                        size=colorbar_config.get('font_size', 10),
                        color=label_color,
                        path_effects=path_effects_list if path_effects_list else None)
            
            # 눈금 레이블에도 그림자 효과 적용
            for label in cbar.ax.get_yticklabels():
                label.set_path_effects(path_effects_list if path_effects_list else None)
            for label in cbar.ax.get_xticklabels():
                label.set_path_effects(path_effects_list if path_effects_list else None)
                
            cbar.ax.tick_params(labelsize=tick_size,
                            colors=label_color)

        cbar.ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    def _add_timestamp(self, ax, timestamp_config):
        """타임스탬프를 추가합니다."""
        try:
            # 현재 시간을 설정된 형식으로 포맷팅
            format_map = {
                'YYYY-MM-DD HH:mm:ss': '%Y-%m-%d %H:%M:%S',
                'YYYY/MM/DD HH:mm:ss': '%Y/%m/%d %H:%M:%S',
                'MM-DD HH:mm': '%m-%d %H:%M',
                'HH:mm:ss': '%H:%M:%S',
                'HH:mm': '%H:%M'
            }
            time_format = format_map.get(timestamp_config.get('format', 'YYYY-MM-DD HH:mm:ss'), '%Y-%m-%d %H:%M:%S')
            timestamp_text = datetime.now().strftime(time_format)

            # 위치 설정
            position = timestamp_config.get('position', 'bottom-right')
            margin_x = timestamp_config.get('margin_x', 10)
            margin_y = timestamp_config.get('margin_y', 10)
            
            # 데이터 좌표계에서의 여백 계산 (1000x1000 기준)
            margin_x_data = (margin_x / 1000) * 1000  # 픽셀 값을 데이터 좌표로 변환
            margin_y_data = (margin_y / 1000) * 1000
            
            # 위치에 따른 좌표와 정렬 설정
            position_settings = {
                'top-left': {'x': margin_x_data, 'y': margin_y_data, 'ha': 'left', 'va': 'top'},
                'top-right': {'x': 1000 - margin_x_data, 'y': margin_y_data, 'ha': 'right', 'va': 'top'},
                'bottom-left': {'x': margin_x_data, 'y': 1000 - margin_y_data, 'ha': 'left', 'va': 'bottom'},
                'bottom-right': {'x': 1000 - margin_x_data, 'y': 1000 - margin_y_data, 'ha': 'right', 'va': 'bottom'}
            }
            pos = position_settings.get(position, position_settings['bottom-right'])

            # 글자 설정
            font_size = timestamp_config.get('font_size', 16)
            font_color = timestamp_config.get('font_color', '#ffffff')

            # 그림자 설정
            shadow = timestamp_config.get('shadow', {})
            path_effects_list = []
            if shadow.get('enabled', True):
                shadow_color = shadow.get('color', '#000000')
                shadow_size = shadow.get('size', 2)
                
                # 그림자 오프셋을 데이터 좌표계로 변환
                shadow_x_offset = shadow.get('x_offset', 1)
                shadow_y_offset = shadow.get('y_offset', 1)
                shadow_y_offset *= -1  # 그림자 방향 반전
                
                # 데이터 좌표계에서의 오프셋 계산
                shadow_x_data = (shadow_x_offset / 1000) * 1000
                shadow_y_data = (shadow_y_offset / 1000) * 1000
                
                path_effects_list.append(path_effects.withStroke(linewidth=shadow_size,
                                                               foreground=shadow_color,
                                                               offset=(shadow_x_data, shadow_y_data)))

            # 타임스탬프 텍스트 추가
            ax.text(pos['x'], pos['y'],
                   timestamp_text,
                   fontsize=font_size,
                   color=font_color,
                   horizontalalignment=pos['ha'],
                   verticalalignment=pos['va'],
                   path_effects=path_effects_list if path_effects_list else None,
                   zorder=10)  # 다른 요소들 위에 표시

        except Exception as e:
            self.logger.error(f"타임스탬프 추가 중 오류 발생: {str(e)}")

    async def generate(self, map_id: str, output_path: str) -> Dict[str, Any]:
        """온도맵을 생성하고 이미지 파일로 저장합니다.
        
        Returns:
            Dict[str, Any]: {
                'success': bool,  # 성공 여부
                'error': str,     # 에러 메시지
                'time': str,      # 생성 시간
                'duration': str   # 생성 소요 시간
            }
        """
        try:
            # 출력 디렉토리 확인 및 생성
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    self.logger.debug(f"출력 디렉토리 생성 완료: {output_dir}")
                except Exception as dir_error:
                    error_msg = f"출력 디렉토리 생성 실패 ({output_dir}): {str(dir_error)}"
                    self.logger.error(error_msg)
                    return {'success': False, 'error': error_msg, 'time': '', 'duration': ''}
            if not map_id:
                error_msg = "맵 ID가 없습니다"
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg, 'time': '', 'duration': ''}
            self.load_map_config(map_id)

            # walls_data와 sensors_data 유효성 검사
            if not self.walls_data or len(self.sensors_data) == 0:
                error_msg = "벽 데이터 또는 센서 데이터가 없습니다"
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg, 'time': '', 'duration': ''}
            
            timestamp_start = time.time_ns()

            try:
                # 센서 상태 조회를 현재 이벤트 루프에서 실행
                self.logger.debug("센서 상태 조회 시작")
                start_time = time.time()
                
                # 센서 상태 조회 실행
                self.logger.debug("센서 상태 조회 실행 시작...")
                all_states = await self.sensor_manager.get_all_states()
                elapsed_time = time.time() - start_time
                
                if all_states:
                    self.logger.debug(f"센서 상태 조회 완료: {len(all_states)}개 센서, 소요시간: {elapsed_time:.3f}초")
                    states_dict = {state['entity_id']: state for state in all_states}
                else:
                    self.logger.error(f"센서 상태 조회 실패: 결과가 비어있음 (소요시간: {elapsed_time:.3f}초)")
                    states_dict = {}
            except Exception as e:
                import traceback
                self.logger.error(f"센서 상태 조회 중 오류 발생: {str(e)}")
                self.logger.error(traceback.format_exc())
                # 오류 발생 시 빈 딕셔너리로 초기화
                states_dict = {}
            
            # 설정된 온도 범위 가져오기
            min_temp = self.gen_config.get('colorbar', {}).get('min_temp', 0)
            max_temp = self.gen_config.get('colorbar', {}).get('max_temp', 40)
            
            # area 데이터 파싱
            areas, root = self._parse_areas()
            if not areas:
                error_msg = "유효한 area를 찾을 수 없습니다"
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg, 'time': '', 'duration': ''}

            # 센서 데이터 수집 (states_dict 전달)
            sensor_points, raw_temps, sensor_ids = await self._collect_sensor_data(states_dict)
            if not sensor_points:
                error_msg = "유효한 센서 데이터가 없습니다"
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg, 'time': '', 'duration': ''}
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
            
            # 멀티프로세싱 설정
            num_processes = min(cpu_count(), len(self.areas))
            self.logger.debug(f"멀티프로세싱 시작: {num_processes}개의 프로세스 사용")
            
            # 프로세스 풀 생성 및 작업 실행
            try:
                self.logger.debug("프로세스 풀 생성 시작")
                with Pool(processes=num_processes) as pool:
                    # 작업 인자 준비
                    self.logger.debug("작업 인자 준비 시작")
                    process_args = [
                        (area_idx, area, grid_points, grid_x, grid_y, min_x, max_x, min_y, max_y, 
                         self.area_sensors, self.parameters)
                        for area_idx, area in enumerate(self.areas)
                    ]
                    self.logger.debug(f"작업 인자 준비 완료: {len(process_args)}개의 작업")
                    
                    # 병렬 처리 실행
                    self.logger.debug("병렬 처리 시작")
                    results = []
                    for i, result in enumerate(pool.imap_unordered(self._process_area_static, process_args)):
                        self.logger.debug(f"Area 처리 완료 ({i+1}/{len(process_args)})")
                        results.append(result)
                    
                    # 결과 처리
                    self.logger.debug("결과 처리 시작")
                    for area_idx, area_temps, area_mask in results:
                        self.logger.debug(f"Area {area_idx} 결과 적용 중")
                        grid_z[area_mask] = area_temps
                        self.logger.debug(f"Area {area_idx} 결과 적용 완료")
                    
                    self.logger.debug("모든 area 처리 완료")
                    
            except Exception as e:
                self.logger.error(f"멀티프로세싱 처리 중 오류 발생: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                raise

            # 플롯 생성
            self.logger.debug("플롯 생성 시작")
            try:
                plt.close('all')  # 기존 플롯 정리
                self.logger.debug("figure 생성 시작")
                fig = plt.figure(figsize=(10, 10))  # 전체 figure 크기
                self.logger.debug("figure 생성 완료")

                # 메인 플롯 (열지도)
                self.logger.debug("메인 플롯 axes 생성 시작")
                main_ax = plt.subplot2grid((1, 20), (0, 0), colspan=20)  # 열지도용 axes
                main_ax.invert_yaxis()
                self.logger.debug("메인 플롯 axes 생성 완료")

                # 온도 범위 설정
                self.logger.debug("온도 범위 설정 시작")
                temp_range = min_temp - max_temp
                steps = self.gen_config.get('colorbar', {}).get('temp_steps', 100)
                levels = np.linspace(min_temp - 0.1 * temp_range, max_temp + 0.1 * temp_range, steps)
                self.logger.debug("온도 범위 설정 완료")

                # 온도 데이터가 없는 area 표시
                self.logger.debug("빈 area 처리 시작")
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
                self.logger.debug("빈 area 처리 완료")

                # 온도 분포 그리기
                self.logger.debug("온도 분포 그리기 시작")
                contour = main_ax.contourf(grid_x, grid_y, grid_z,
                                       levels=levels,
                                       cmap=self.gen_config.get('colorbar', {}).get('cmap', 'RdYlBu_r'),
                                       extend='both',
                                       alpha=0.9)
                self.logger.debug("온도 분포 그리기 완료")

                # area 경계 그리기
                self.logger.debug("area 경계 그리기 시작")
                area_border_width = self.gen_config.get('visualization', {}).get('area_border_width', 2)
                area_border_color = self.gen_config.get('visualization', {}).get('area_border_color', '#000000')
                if area_border_width > 0:
                    for area in self.areas:
                        if not area['is_exterior']:
                            for x, y in self._get_polygon_coords(area['polygon']):
                                main_ax.plot(x, y, color=area_border_color, linewidth=area_border_width)
                self.logger.debug("area 경계 그리기 완료")

                # plot 외곽선 그리기
                self.logger.debug("plot 외곽선 그리기 시작")
                plot_border_width = self.gen_config.get('visualization', {}).get('plot_border_width', 0)
                plot_border_color = self.gen_config.get('visualization', {}).get('plot_border_color', '#000000')
                if plot_border_width > 0:
                    for spine in ['top', 'bottom', 'left', 'right']:
                        main_ax.spines[spine].set_linewidth(plot_border_width)
                        main_ax.spines[spine].set_color(plot_border_color)
                        main_ax.spines[spine].set_visible(True)
                self.logger.debug("plot 외곽선 그리기 완료")

                # 센서 표시 설정
                self.logger.debug("센서 표시 시작")
                sensor_display = self.gen_config.get('visualization', {}).get('sensor_display', 'position_name_temp')
                if sensor_display != 'none':
                    for point, temperature, sensor_id in zip(sensor_points, raw_temps, sensor_ids):
                        try:
                            state = states_dict.get(sensor_id, {'state': '0', 'entity_id': sensor_id})
                            self._create_sensor_marker([point[0], point[1]], temperature, sensor_id, state)
                        except Exception as e:
                            self.logger.error(f"센서 {sensor_id} 표시 실패: {str(e)}")
                            continue
                self.logger.debug("센서 표시 완료")

                # 컬러바 설정 적용
                self.logger.debug("컬러바 설정 시작")
                colorbar_config = self.gen_config.get('colorbar', {})
                if colorbar_config and colorbar_config.get('show_colorbar', True):
                    self._create_colorbar(fig, contour, colorbar_config)
                self.logger.debug("컬러바 설정 완료")

                # 타임스탬프 설정 적용
                self.logger.debug("타임스탬프 설정 시작")
                timestamp_config = self.gen_config.get('timestamp', {})
                if timestamp_config.get('enabled', False):
                    self._add_timestamp(main_ax, timestamp_config)
                self.logger.debug("타임스탬프 설정 완료")

                # 축 설정
                self.logger.debug("축 설정 시작")
                main_ax.set_aspect('equal')
                main_ax.axis('off')
                self.logger.debug("축 설정 완료")

                # 저장 (dpi 조정으로 1000x1000 크기 맞추기)
                self.logger.debug("이미지 저장 시작")
                width_inches = fig.get_size_inches()[0]
                dpi = 1000 / width_inches
                
                format = self.config_manager.get_output_format(map_id)
                plt.savefig(output_path,
                           bbox_inches='tight',
                           pad_inches=0,
                           dpi=dpi,
                           facecolor='none',
                           transparent=True,
                           format=format)
                self.logger.debug("이미지 저장 완료")
                
                plt.close(fig)  # 메모리 정리
                self.logger.debug("플롯 생성 완료")
                
                # 생성 시간 정보 업데이트
                timestamp_end = time.time_ns()
                generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                generation_duration = f'{((timestamp_end - timestamp_start)/1000000000):.3f}s'
                
                self.save_generation_time(map_id, generation_time, generation_duration)
                
                return {
                    'success': True,
                    'error': '',
                    'time': generation_time,
                    'duration': generation_duration
                }

            except Exception as e:
                self.logger.error(f"플롯 생성 중 오류 발생: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                plt.close('all')  # 오류 발생 시에도 메모리 정리
                raise

        except Exception as e:
            error_msg = f"온도맵 생성 중 오류 발생: {str(e)}"
            self.logger.error(error_msg)
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': error_msg,
                'time': '',
                'duration': ''
            } 