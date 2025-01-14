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
import re
from flask import current_app

class ThermalMapGenerator:
    def __init__(self, walls_data: str, sensors_data: List[Dict[str, Any]], get_sensor_state_func):
        """
        온도맵 생성기를 초기화합니다.
        
        Args:
            walls_data: SVG 형식의 벽 데이터
            sensors_data: 센서 위치 및 정보 목록
            get_sensor_state_func: 센서 상태를 조회하는 함수
        """
        self.walls_data = walls_data
        self.sensors_data = sensors_data
        self.get_sensor_state = get_sensor_state_func
        self.padding = 50  # 여백 크기
        self.areas: List[Polygon] = []  # area 폴리곤 저장용
        self.area_sensors: Dict[int, List[Tuple[Point, float]]] = {}  # area별 센서 그룹
        current_app.logger.info("ThermalMapGenerator 초기화됨")

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

    def _calculate_area_temperature(self, area_idx: int, grid_x: np.ndarray, grid_y: np.ndarray) -> np.ndarray:
        """특정 area의 온도 분포를 계산합니다."""
        sensors = self.area_sensors.get(area_idx, [])
        area = self.areas[area_idx]
        
        try:
            # 그리드 포인트가 area 내부인지 확인하는 마스크 생성
            grid_points = np.column_stack((grid_x.flatten(), grid_y.flatten()))
            area_mask = np.array([area.contains(Point(x, y)) for x, y in grid_points])
            area_mask = area_mask.reshape(grid_x.shape)
            
            if not sensors:  # 센서가 없는 area
                current_app.logger.debug(f"Area {area_idx}에 센서가 없음")
                return np.full_like(grid_x, np.nan)
            
            if len(sensors) == 1:  # 센서가 1개인 area
                current_app.logger.debug(f"Area {area_idx}에 센서가 1개: {sensors[0][1]:.1f}°C")
                # 가우시안 분포로 부드럽게 처리
                center_x, center_y = sensors[0][0].x, sensors[0][0].y
                sigma = min(grid_x.max() - grid_x.min(), grid_y.max() - grid_y.min()) / 20
                
                weights = np.exp(-((grid_x - center_x)**2 + (grid_y - center_y)**2) / (2 * sigma**2))
                weights = weights / weights.max()
                
                temp_variation = 0.3  # 온도 변화 범위 축소
                grid_z = sensors[0][1] - temp_variation * (1 - weights)
                return np.where(area_mask, grid_z, np.nan)
            
            # 2개 이상의 센서가 있는 area는 RBF 보간 수행
            sensor_points = np.array([[p.x, p.y] for p, _ in sensors])
            sensor_temps = np.array([t for _, t in sensors])
            
            current_app.logger.debug(f"Area {area_idx} RBF 보간 시작: {len(sensors)}개 센서, 온도: {sensor_temps}")
            
            try:
                # RBF 보간기 생성 (multiquadric 함수 사용)
                rbf = Rbf(sensor_points[:, 0], sensor_points[:, 1], sensor_temps,
                         function='multiquadric',
                         epsilon=np.mean([grid_x.max() - grid_x.min(), grid_y.max() - grid_y.min()]) / 8)
                
                # 전체 그리드에 대해 보간
                grid_z = rbf(grid_x, grid_y)
                
                # area 외부는 NaN으로 설정
                return np.where(area_mask, grid_z, np.nan)
                
            except Exception as e:
                current_app.logger.error(f"Area {area_idx} RBF 보간 실패: {str(e)}")
                # 실패시 linear 보간으로 폴백
                try:
                    grid_z = griddata(sensor_points, sensor_temps, (grid_x, grid_y), method='linear')
                    if np.any(np.isnan(grid_z)):
                        nearest = griddata(sensor_points, sensor_temps, (grid_x, grid_y), method='nearest')
                        grid_z[np.isnan(grid_z)] = nearest[np.isnan(grid_z)]
                    return np.where(area_mask, grid_z, np.nan)
                except:
                    # 모든 보간이 실패하면 평균값 사용
                    return np.where(area_mask, np.mean(sensor_temps), np.nan)
            
        except Exception as e:
            current_app.logger.error(f"Area {area_idx} 온도 계산 중 오류: {str(e)}")
            return np.full_like(grid_x, np.nan)

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

    def _calculate_bounds(self) -> Tuple[float, float, float, float]:
        """모든 area의 경계를 계산합니다."""
        if not self.areas:
            return 0, 100, 0, 100  # 기본값
            
        bounds = self.areas[0].bounds
        for area in self.areas[1:]:
            area_bounds = area.bounds
            bounds = (
                min(bounds[0], area_bounds[0]),
                min(bounds[1], area_bounds[1]),
                max(bounds[2], area_bounds[2]),
                max(bounds[3], area_bounds[3])
            )
        return bounds

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
            current_app.logger.info(f"센서가 있는 area 수: {len(self.area_sensors)}")

            # 경계 계산
            min_x, min_y, max_x, max_y = self._calculate_bounds()
            current_app.logger.debug(f"맵 경계: ({min_x}, {min_y}) - ({max_x}, {max_y})")
            
            # 격자 생성 (해상도 대폭 증가)
            grid_x, grid_y = np.mgrid[
                min_x-self.padding:max_x+self.padding:100j,
                min_y-self.padding:max_y+self.padding:100j
            ]

            # 전체 마스크와 온도 배열 초기화
            grid_z = np.full_like(grid_x, np.nan)
            
            # 각 area별로 처리
            for area_idx, area in enumerate(self.areas):
                # area 마스크 생성
                grid_points = np.column_stack((grid_x.flatten(), grid_y.flatten()))
                area_mask = np.array([area.contains(Point(x, y)) for x, y in grid_points])
                area_mask = area_mask.reshape(grid_x.shape)
                
                if area_idx in self.area_sensors:
                    # 센서가 있는 area
                    sensors = self.area_sensors[area_idx]
                    sensor_locs = np.array([[p.x, p.y] for p, _ in sensors])
                    sensor_temps = np.array([t for _, t in sensors])
                    
                    if len(sensors) == 1:
                        # 단일 센서: 가우시안 분포로 부드럽게 처리
                        center_x, center_y = sensor_locs[0]
                        sigma = min(grid_x.max() - grid_x.min(), grid_y.max() - grid_y.min()) / 20  # 표준편차 설정
                        
                        # 가우시안 가중치 계산
                        weights = np.exp(-((grid_x - center_x)**2 + (grid_y - center_y)**2) / (2 * sigma**2))
                        weights = weights / weights.max()  # 정규화
                        
                        # 온도값 설정 (중심에서 멀어질수록 약간의 변화)
                        temp_variation = 0.5  # 온도 변화 범위 (°C)
                        grid_z_area = sensor_temps[0] - temp_variation * (1 - weights)
                        
                        # area 마스크 적용
                        grid_z[area_mask.reshape(grid_x.shape)] = grid_z_area[area_mask.reshape(grid_x.shape)]
                        
                        current_app.logger.debug(f"Area {area_idx}: 가우시안 분포로 온도 {sensor_temps[0]:.1f}°C 설정")
                    else:
                        # 다중 센서: cubic 보간 시도 후 실패시 linear
                        try:
                            # 해당 area 내부의 점들만 선택
                            mask_points = grid_points[area_mask.flatten()]
                            
                            # cubic 보간 시도
                            try:
                                temps = griddata(sensor_locs, sensor_temps, mask_points, method='cubic')
                                if np.any(np.isnan(temps)):
                                    # cubic 실패한 부분은 linear로 보간
                                    linear_temps = griddata(sensor_locs, sensor_temps, mask_points, method='linear')
                                    temps[np.isnan(temps)] = linear_temps[np.isnan(temps)]
                            except Exception:
                                # cubic 실패시 linear 사용
                                temps = griddata(sensor_locs, sensor_temps, mask_points, method='linear')
                            
                            # 여전히 남은 NaN은 nearest로 채움
                            if np.any(np.isnan(temps)):
                                nearest_temps = griddata(sensor_locs, sensor_temps, mask_points, method='nearest')
                                temps[np.isnan(temps)] = nearest_temps[np.isnan(temps)]
                            
                            # 결과를 grid_z에 할당
                            grid_z[area_mask] = temps
                            current_app.logger.debug(f"Area {area_idx}: 다중 센서 보간 완료")
                            
                        except Exception as e:
                            current_app.logger.error(f"Area {area_idx} 보간 실패: {str(e)}")
                            grid_z[area_mask] = np.mean(sensor_temps)  # 실패시 평균값 사용

            # 플롯 생성
            plt.figure(figsize=(15, 15))
            plt.gca().invert_yaxis()

            # 온도 범위 설정
            temp_min = min(temperatures)
            temp_max = max(temperatures)
            temp_range = temp_max - temp_min
            levels = np.linspace(temp_min - 0.1 * temp_range, temp_max + 0.1 * temp_range, 100)  # 레벨 수 증가

            # 온도 데이터가 없는 area 표시 (흰색 배경에 빗금)
            for i, area in enumerate(self.areas):
                if i not in self.area_sensors:
                    for x, y in self._get_polygon_coords(area):
                        plt.fill(x, y, facecolor='white', hatch='///', alpha=1.0)

            # 온도 분포 그리기 (부드러운 그라데이션을 위한 설정)
            contour = plt.contourf(grid_x, grid_y, grid_z,
                                 levels=levels,
                                 cmap='RdYlBu_r',
                                 extend='both',
                                 alpha=0.9)  # 약간의 투명도 추가
            
            # 컬러바 설정
            cbar = plt.colorbar(contour)
            cbar.set_label('Temperature (°C)', fontsize=12)
            cbar.ax.tick_params(labelsize=10)

            # area 경계 그리기
            for area in self.areas:
                for x, y in self._get_polygon_coords(area):
                    plt.plot(x, y, 'black', linewidth=2)

            # 센서 위치 표시
            sensor_x = [p[0] for p in sensor_points]
            sensor_y = [p[1] for p in sensor_points]
            plt.scatter(sensor_x, sensor_y, c='red', s=50, zorder=5)

            # 축 설정
            plt.axis('equal')
            plt.axis('off')

            # 저장
            plt.savefig(output_path,
                       bbox_inches='tight',
                       pad_inches=0,
                       dpi=300,
                       facecolor='white',
                       transparent=False)
            plt.close()

            return True

        except Exception as e:
            current_app.logger.error(f"온도맵 생성 중 오류 발생: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return False 