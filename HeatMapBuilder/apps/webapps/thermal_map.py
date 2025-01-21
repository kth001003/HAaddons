import os
import json
import numpy as np  #type: ignore
import matplotlib.pyplot as plt #type: ignore
from scipy.interpolate import griddata, Rbf  #type: ignore
from scipy.spatial import Voronoi  #type: ignore
import xml.etree.ElementTree as ET
from io import StringIO
from typing import List, Dict, Tuple, Any, Optional
from shapely.geometry import LineString, Point, Polygon, MultiPolygon  #type: ignore
from shapely.ops import unary_union  #type: ignore
import svgpath2mpl  #type: ignore
import matplotlib.path as mpath  #type: ignore
import matplotlib.font_manager as fm  #type: ignore
import re
from flask import current_app
from pykrige.ok import OrdinaryKriging  #type: ignore

class ThermalMapGenerator:
    def __init__(self, walls_data: str, sensors_data: List[Dict[str, Any]], get_sensor_state_func, 
                 interpolation_params: Optional[Dict[str, Any]] = None):
        """
        온도맵 생성기를 초기화합니다.
        
        Args:
            walls_data: SVG 형식의 벽 데이터
            sensors_data: 센서 위치 및 정보 목록
            get_sensor_state_func: 센서 상태를 조회하는 함수
            interpolation_params: 보간 파라미터 설정
        """
        self.walls_data = walls_data
        self.sensors_data = sensors_data
        self.get_sensor_state = get_sensor_state_func
        self.padding = 50  # 여백 크기
        self.areas: List[Polygon] = []  # area 폴리곤 저장용
        self.area_sensors: Dict[int, List[Tuple[Point, float]]] = {}  # area별 센서 그룹
        
        # 보간 파라미터 설정
        self.interpolation_params = {
            'gaussian': {
                'sigma_factor': 8.0,  # area 크기 대비 sigma 비율
            },
            'rbf': {
                'function': 'inverse',
                'epsilon_factor': 1.5,  # area 크기 대비 epsilon 비율
            },
            'kriging': {
                'variogram_model': 'gaussian',
                'nlags': 20,
                'weight': True,
                'anisotropy_scaling': 1.0,
                'anisotropy_angle': 0.0
            }
        }
        
        # 사용자 정의 파라미터로 업데이트
        if interpolation_params:
            self._update_interpolation_params(interpolation_params)
        
        # 한글 폰트 설정
        self._setup_korean_font()
        current_app.logger.info("ThermalMapGenerator 초기화됨")

    def _update_interpolation_params(self, params: Dict[str, Any]):
        """보간 파라미터를 업데이트합니다."""
        for method in ['gaussian', 'rbf', 'kriging']:
            if method in params:
                self.interpolation_params[method].update(params[method])
                current_app.logger.debug(f"{method} 파라미터 업데이트: {params[method]}")

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
                    current_app.logger.info(f"한글 폰트 설정 완료: {font_path}")
                    font_found = True
                    break
            
            if not font_found:
                current_app.logger.warning("한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
                
            # 마이너스 기호 깨짐 방지
            plt.rcParams['axes.unicode_minus'] = False
            
        except Exception as e:
            current_app.logger.error(f"한글 폰트 설정 중 오류 발생: {str(e)}")

    def _parse_svg_path(self, path_data: str) -> Optional[Polygon]:
        """SVG path 데이터를 Polygon으로 변환합니다."""
        try:
            # SVG path 데이터 전처리
            path_data = path_data.strip()
            if not path_data:
                return None
            
            # SVG path를 matplotlib path로 변환
            path = svgpath2mpl.parse_path(path_data)
            vertices = path.vertices
            
            # 점 개수 확인
            if len(vertices) < 3:
                current_app.logger.warning(f"점이 부족함 (최소 3개 필요): {len(vertices)}개")
                return None
            
            # 첫 점과 마지막 점이 같은지 확인하고 처리
            if not np.allclose(vertices[0], vertices[-1], rtol=1e-5, atol=1e-8):
                vertices = np.vstack([vertices, vertices[0]])  # 첫 점을 마지막에 추가하여 폴리곤 닫기
            
            # 폴리곤 생성
            try:
                polygon = Polygon(vertices).buffer(0)  # buffer(0)로 자체 교차 해결
                if not polygon.is_valid:
                    current_app.logger.warning("유효하지 않은 폴리곤")
                    return None
                
                # 면적이 너무 작은 폴리곤 필터링
                if polygon.area < 1e-6:
                    current_app.logger.warning("면적이 너무 작은 폴리곤")
                    return None
                return polygon
                
            except Exception as e:
                current_app.logger.warning(f"폴리곤 생성 실패: {str(e)}")
                return None
            
        except Exception as e:
            current_app.logger.error(f"SVG path 파싱 오류: {str(e)}, path_data={path_data}")
            return None

    def _parse_areas(self) -> Tuple[List[Polygon], Optional[ET.Element]]:
        """area 데이터를 파싱하여 Polygon 목록과 XML 요소를 반환합니다."""
        try:
            svg_data = f'<svg>{self.walls_data}</svg>'
            
            tree = ET.parse(StringIO(svg_data))
            root = tree.getroot()

            self.areas = []
            
            # SVG 변환 행렬 확인
            transform = root.get('transform', '')
            current_app.logger.debug(f"SVG transform: {transform}")
            
            # path 요소 찾기
            paths = root.findall('.//{*}path')
            
            for i, path in enumerate(paths):
                # path의 스타일과 클래스 확인
                style = path.get('style', '')
                class_name = path.get('class', '')
                
                d = path.get('d', '')
                if not d:
                    current_app.logger.warning(f"Path {i}: 'd' 속성 없음")
                    continue
                
                # path별 transform 확인
                path_transform = path.get('transform', '')
                if path_transform:
                    current_app.logger.debug(f"Path {i} transform: {path_transform}")
                
                polygon = self._parse_svg_path(d)
                if polygon and polygon.is_valid:
                    self.areas.append(polygon)
                else:
                    current_app.logger.warning(f"Path {i}: 유효한 폴리곤 생성 실패")

            current_app.logger.info(f"총 {len(self.areas)}개의 area 파싱됨 (전체 path 중 {len(paths)}개)")
            return self.areas, root
            
        except Exception as e:
            current_app.logger.error(f"Area 파싱 중 오류 발생: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return [], None

    def _assign_sensors_to_areas(self, points: List[List[float]], temperatures: List[float]):
        """센서들을 해당하는 area에 할당합니다."""
        self.area_sensors.clear()
        
        # 각 area의 경계 버퍼 생성 (경계 근처의 센서를 포함하기 위해)
        buffered_areas = [(i, area.buffer(1e-6)) for i, area in enumerate(self.areas)]
        
        for i, (point_coords, temp) in enumerate(zip(points, temperatures)):
            point = Point(point_coords[0], point_coords[1])
            assigned = False
            
            # 정확한 포함 관계 확인
            for area_idx, area in enumerate(self.areas):
                if area.contains(point):
                    if area_idx not in self.area_sensors:
                        self.area_sensors[area_idx] = []
                    self.area_sensors[area_idx].append((point, temp))
                    current_app.logger.info(f"센서 {i} (temp={temp:.1f}°C)가 Area {area_idx}에 정확히 포함됨")
                    assigned = True
                    break
            
            # 정확한 포함 관계가 없는 경우, 버퍼를 사용하여 재확인
            if not assigned:
                for area_idx, buffered_area in buffered_areas:
                    if buffered_area.contains(point):
                        if area_idx not in self.area_sensors:
                            self.area_sensors[area_idx] = []
                        self.area_sensors[area_idx].append((point, temp))
                        current_app.logger.info(f"센서 {i} (temp={temp:.1f}°C)가 Area {area_idx}의 경계 근처에 할당됨")
                        assigned = True
                        break
            
            # 여전히 할당되지 않은 경우, 가장 가까운 area에 할당
            if not assigned:
                min_distance = float('inf')
                nearest_area_idx = None
                
                for area_idx, area in enumerate(self.areas):
                    distance = area.distance(point)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_area_idx = area_idx
                
                if nearest_area_idx is not None:
                    if nearest_area_idx not in self.area_sensors:
                        self.area_sensors[nearest_area_idx] = []
                    self.area_sensors[nearest_area_idx].append((point, temp))
                    current_app.logger.warning(f"센서 {i} (temp={temp:.1f}°C)가 가장 가까운 Area {nearest_area_idx}에 할당됨 (거리: {min_distance:.2f})")
                else:
                    current_app.logger.error(f"센서 {i} (temp={temp:.1f}°C)를 할당할 수 있는 area를 찾지 못함")

        # 할당 결과 출력
        for area_idx, sensors in self.area_sensors.items():
            current_app.logger.info(f"Area {area_idx}: {len(sensors)}개의 센서, 온도: {[temp for _, temp in sensors]}")

    def _calculate_area_temperature(self, area_idx: int, area: Polygon, grid_points: np.ndarray, 
                                   grid_x: np.ndarray, grid_y: np.ndarray, min_x: float, max_x: float, 
                                   min_y: float, max_y: float) -> np.ndarray:
        """특정 area의 온도 분포를 계산합니다."""
        try:
            # area 마스크 생성
            area_mask = np.array([area.contains(Point(x, y)) for x, y in grid_points])
            area_mask = area_mask.reshape(grid_x.shape)
            temps = np.full_like(grid_x[area_mask], np.nan)
            
            if area_idx not in self.area_sensors:
                return temps
            
            # 센서가 있는 area
            sensors = self.area_sensors[area_idx]
            sensor_locs = np.array([[p.x, p.y] for p, _ in sensors])
            sensor_temps = np.array([t for _, t in sensors])
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
            sigma = min(area_width, area_height) / self.interpolation_params['gaussian']['sigma_factor']
            
            if sensor_count == 1:  # 단일 센서: 가우시안 분포
                current_app.logger.debug(f"Area {area_idx}: {sensor_count}개 센서 - 가우시안 분포 적용")
                temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
                
            elif sensor_count <= 3:  # 2~3개 센서: RBF -> 가우시안
                try:
                    current_app.logger.debug(f"Area {area_idx}: {sensor_count}개 센서 - RBF 보간 시도")
                    # RBF 보간기 설정
                    rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                            function=self.interpolation_params['rbf']['function'],
                            epsilon=min(area_width, area_height) / self.interpolation_params['rbf']['epsilon_factor'])
                    
                    # RBF 예측 수행
                    temps = rbf(mask_points[:, 0], mask_points[:, 1])
                    
                    # 예측값 범위 제한
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.1 * (temp_max - temp_min)  # 10% 마진
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                    
                    current_app.logger.debug(f"Area {area_idx}: RBF 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                    
                except Exception as rbf_error:
                    current_app.logger.warning(f"Area {area_idx} RBF 보간 실패, 가우시안 분포로 대체: {str(rbf_error)}")
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
                        **self.interpolation_params['kriging']
                    )
                    
                    # 크리깅 예측 수행
                    temps, variances = ok.execute('points', mask_points[:, 0], mask_points[:, 1])
                    
                    # 예측값 범위 제한
                    temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                    margin = 0.5 * (temp_max - temp_min)  # 50% 마진
                    temps = np.clip(temps, temp_min - margin, temp_max + margin)
                    
                    current_app.logger.debug(f"Area {area_idx}: 크리깅 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                    
                except Exception as kriging_error:
                    current_app.logger.warning(f"Area {area_idx} 크리깅 보간 실패, RBF 시도: {str(kriging_error)}")
                    try:
                        # RBF 보간 시도
                        rbf = Rbf(sensor_locs[:, 0], sensor_locs[:, 1], sensor_temps,
                                function=self.interpolation_params['rbf']['function'],
                                epsilon=min(area_width, area_height) / self.interpolation_params['rbf']['epsilon_factor'])
                        temps = rbf(mask_points[:, 0], mask_points[:, 1])
                        
                        # 예측값 범위 제한
                        temp_min, temp_max = np.min(sensor_temps), np.max(sensor_temps)
                        margin = 0.1 * (temp_max - temp_min)
                        temps = np.clip(temps, temp_min - margin, temp_max + margin)
                        
                        current_app.logger.debug(f"Area {area_idx}: RBF 보간 성공 - 온도 범위: {np.min(temps):.1f}°C ~ {np.max(temps):.1f}°C")
                        
                    except Exception as rbf_error:
                        current_app.logger.warning(f"Area {area_idx} RBF 보간도 실패, 가우시안 분포로 대체: {str(rbf_error)}")
                        temps = calculate_gaussian_distribution(mask_points, sensor_locs, sensor_temps, sigma)
            
            # NaN 처리
            if np.any(np.isnan(temps)):
                current_app.logger.debug(f"Area {area_idx}: NaN 값을 nearest로 채우기")
                nearest_temps = griddata(sensor_locs, sensor_temps, mask_points, method='nearest')
                temps[np.isnan(temps)] = nearest_temps[np.isnan(temps)]
            
            return temps
            
        except Exception as e:
            current_app.logger.error(f"Area {area_idx} 온도 계산 중 오류: {str(e)}")
            return np.full_like(grid_x[area_mask], np.nan)

    def _collect_sensor_data(self) -> Tuple[List[List[float]], List[float]]:
        """센서 데이터를 수집하여 위치와 온도 값을 반환합니다."""
        points = []
        temperatures = []
        
        for sensor in self.sensors_data:
            try:
                if not sensor.get('position'):
                    current_app.logger.debug(f"센서 위치 정보 없음: {sensor['entity_id']}")
                    continue
                
                state = self.get_sensor_state(sensor['entity_id'])
                current_app.logger.debug(f"센서 상태 데이터: {state}")
                
                # 온도 값 처리
                temp = float(state['state'])
                
                # 위치 값 처리
                position = sensor['position']
                
                # position 형식에 따른 처리
                if isinstance(position, dict):
                    if 'x' in position and 'y' in position:
                        x = float(position['x'])
                        y = float(position['y'])
                        points.append([x, y])
                        temperatures.append(temp)
                    else:
                        current_app.logger.warning(f"잘못된 딕셔너리 위치 형식: {position}")
                        continue
                elif isinstance(position, list) and len(position) == 2:
                    x = float(position[0]) if isinstance(position[0], str) else position[0]
                    y = float(position[1]) if isinstance(position[1], str) else position[1]
                    points.append([x, y])
                    temperatures.append(temp)
                else:
                    current_app.logger.warning(f"지원하지 않는 위치 형식: {position}")
                    continue
                
            except (ValueError, KeyError, TypeError, IndexError) as e:
                current_app.logger.warning(f"센서 데이터 변환 실패: {sensor.get('entity_id', 'unknown')} - {str(e)}")
                continue

        return points, temperatures

    def _get_polygon_coords(self, geom) -> List[Tuple[np.ndarray, np.ndarray]]:
        """폴리곤 또는 멀티폴리곤에서 좌표를 추출합니다."""
        coords = []
        if isinstance(geom, Polygon):
            coords.append((np.array(geom.exterior.xy[0]), np.array(geom.exterior.xy[1])))
        elif isinstance(geom, MultiPolygon):
            for polygon in geom.geoms:
                coords.append((np.array(polygon.exterior.xy[0]), np.array(polygon.exterior.xy[1])))
        return coords

    def generate(self, output_path: str) -> bool:
        try:
            # area 데이터 파싱
            areas, root = self._parse_areas()
            if not areas:
                current_app.logger.error("유효한 area를 찾을 수 없습니다")
                return False

            # 센서 데이터 수집
            sensor_points, temperatures = self._collect_sensor_data()
            if not sensor_points:
                current_app.logger.error("유효한 센서 데이터가 없습니다")
                return False

            # 센서를 area에 할당
            self._assign_sensors_to_areas(sensor_points, temperatures)

            # SVG 전체 크기 사용
            # min_x, min_y, max_x, max_y = 0, 0, 1200, 1000
            min_x, min_y, max_x, max_y = 0, 0, 1000, 1000
            
            # 격자 생성 (해상도 대폭 증가)
            grid_x, grid_y = np.mgrid[
                min_x:max_x:150j,  # padding 제거
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
                area_mask = np.array([area.contains(Point(x, y)) for x, y in grid_points])
                area_mask = area_mask.reshape(grid_x.shape)
                grid_z[area_mask] = area_temps

            # 플롯 생성
            # fig = plt.figure(figsize=(12, 10))  # 전체 figure 크기
            fig = plt.figure(figsize=(10, 10))  # 전체 figure 크기

            # 메인 플롯 (열지도)
            # main_ax = plt.subplot2grid((1, 20), (0, 0), colspan=17)  # 열지도용 axes
            main_ax = plt.subplot2grid((1, 20), (0, 0), colspan=20)  # 열지도용 axes
            main_ax.invert_yaxis()

            # 온도 범위 설정
            temp_min = min(temperatures)
            temp_max = max(temperatures)
            temp_range = temp_max - temp_min
            levels = np.linspace(temp_min - 0.3 * temp_range, temp_max + 0.3 * temp_range, 100)

            # 온도 데이터가 없는 area 표시 (흰색 배경에 빗금)
            for i, area in enumerate(self.areas):
                if i not in self.area_sensors:
                    for x, y in self._get_polygon_coords(area):
                        main_ax.fill(x, y, facecolor='white', hatch='///', alpha=1.0)

            # 온도 분포 그리기 (부드러운 그라데이션을 위한 설정)
            contour = main_ax.contourf(grid_x, grid_y, grid_z,
                                   levels=levels,
                                   cmap='RdYlBu_r',
                                   extend='both',
                                   alpha=0.9)  # 약간의 투명도 추가
            
            # area 경계 그리기
            for area in self.areas:
                for x, y in self._get_polygon_coords(area):
                    main_ax.plot(x, y, 'black', linewidth=2)

            # 센서 위치 표시
            sensor_x = [p[0] for p in sensor_points]
            sensor_y = [p[1] for p in sensor_points]
            main_ax.scatter(sensor_x, sensor_y, c='red', s=10, zorder=5)

            # 센서 온도값과 이름 표시
            for i, (point, sensor) in enumerate(zip(sensor_points, self.sensors_data)):
                if 'position' in sensor:
                    try:
                        state = self.get_sensor_state(sensor['entity_id'])
                        temp = float(state['state'])
                        name = state['attributes'].get('friendly_name', sensor['entity_id'].split('.')[-1])
                        
                        # 텍스트 위치 (센서 위치보다 약간 위로)
                        text_x = point[0]
                        text_y = point[1] - 10
                        
                        # 온도값과 이름 표시
                        main_ax.text(text_x, text_y, f'{name}\n{temp:.1f}°C',
                                 horizontalalignment='center',
                                 verticalalignment='bottom',
                                 fontsize=8,
                                 bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=1),
                                 zorder=6)
                    except Exception as e:
                        current_app.logger.warning(f"센서 {sensor['entity_id']} 텍스트 표시 실패: {str(e)}")
                        continue

            # # 컬러바 설정 (오른쪽 subplot 사용)
            # cbar_ax = plt.subplot2grid((1, 20), (0, 17), colspan=1)  # 컬러바용 axes
            # cbar = plt.colorbar(contour, cax=cbar_ax)
            # cbar.set_label('온도 (°C)', fontsize=12)
            # cbar.ax.tick_params(labelsize=10)

            # 축 설정
            main_ax.set_aspect('equal')
            main_ax.axis('off')

            # 저장 (dpi 조정으로 1000x1000 크기 맞추기)
            # width_inches = fig.get_size_inches()[0] * (17/20)  # 메인 플롯의 실제 너비
            width_inches = fig.get_size_inches()[0]  # 메인 플롯의 실제 너비
            dpi = 1000 / (width_inches)  # 1000px 위해 필요한 dpi 계산
            
            plt.savefig(output_path,
                       bbox_inches='tight',
                       pad_inches=0,
                       dpi=dpi,
                       facecolor='white',
                       transparent=False)
            plt.close()

            return True

        except Exception as e:
            current_app.logger.error(f"온도맵 생성 중 오류 발생: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return False 