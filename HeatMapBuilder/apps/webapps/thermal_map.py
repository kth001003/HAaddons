import os
import json
import numpy as np  #type: ignore
import matplotlib.pyplot as plt #type: ignore
from scipy.interpolate import griddata  #type: ignore
from scipy.spatial import Voronoi  #type: ignore
import xml.etree.ElementTree as ET
from io import StringIO
from typing import List, Dict, Tuple, Any
import logging
from shapely.geometry import LineString, Point, Polygon  #type: ignore
from shapely.ops import unary_union  #type: ignore

logger = logging.getLogger(__name__)

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
        self.wall_lines = []  # 벽 라인 저장용

    def _parse_walls(self) -> Tuple[List[Tuple[float, float]], ET.Element]:
        """벽 데이터를 파싱하여 좌표와 XML 요소를 반환합니다."""
        svg_data = f'<svg>{self.walls_data}</svg>'
        tree = ET.parse(StringIO(svg_data))
        root = tree.getroot()

        coords = []
        self.wall_lines = []  # 벽 라인 초기화
        for line in root.findall('.//{*}line'):
            x1 = float(line.get('x1', 0))
            y1 = float(line.get('y1', 0))
            x2 = float(line.get('x2', 0))
            y2 = float(line.get('y2', 0))
            coords.extend([(x1, y1), (x2, y2)])
            self.wall_lines.append(LineString([(x1, y1), (x2, y2)]))

        return coords, root

    def _is_path_blocked(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        """두 점 사이의 경로가 벽에 의해 차단되는지 확인합니다."""
        path = LineString([p1, p2])
        for wall in self.wall_lines:
            if path.intersects(wall):
                return True
        return False

    def _add_boundary_points(self, points: List[List[float]], temperatures: List[float], 
                           bounds: Tuple[float, float, float, float]) -> Tuple[List[List[float]], List[float]]:
        """경계 영역에 가상의 센서 포인트를 추가합니다."""
        min_x, max_x, min_y, max_y = bounds
        extended_points = points.copy()
        extended_temps = temperatures.copy()
        
        # 각 센서에 대해 경계점 추가
        for i in range(len(points)):
            point = points[i]
            temp = temperatures[i]
            
            # 현재 센서의 경계점들
            new_boundary_points = [
                [min_x - self.padding, point[1]],  # 왼쪽
                [max_x + self.padding, point[1]],  # 오른쪽
                [point[0], min_y - self.padding],  # 위
                [point[0], max_y + self.padding]   # 아래
            ]
            
            # 경계점과 온도 추가
            extended_points.extend(new_boundary_points)
            extended_temps.extend([temp] * len(new_boundary_points))
            
        return extended_points, extended_temps

    def _interpolate_with_walls(self, grid_x: np.ndarray, grid_y: np.ndarray, 
                              points: List[List[float]], temperatures: List[float]) -> Tuple[np.ndarray, np.ndarray]:
        """벽을 고려한 온도 보간을 수행합니다."""
        grid_z = np.zeros_like(grid_x)
        no_data_mask = np.ones_like(grid_x, dtype=bool)  # 데이터가 없는 영역 마스크
        
        # 각 그리드 포인트에 대해
        for i in range(grid_x.shape[0]):
            for j in range(grid_x.shape[1]):
                grid_point = (grid_x[i,j], grid_y[i,j])
                
                # 각 센서까지의 거리와 벽 차단 여부 확인
                valid_points = []
                valid_temps = []
                valid_distances = []
                
                for k, point in enumerate(points):
                    point_tuple = (point[0], point[1])
                    # 벽 차단 여부 확인
                    if not self._is_path_blocked(grid_point, point_tuple):
                        valid_points.append(point)
                        valid_temps.append(temperatures[k])
                        # 유클리드 거리 계산
                        dist = np.sqrt((point[0]-grid_point[0])**2 + (point[1]-grid_point[1])**2)
                        valid_distances.append(dist)
                
                if valid_points:
                    no_data_mask[i,j] = False  # 유효한 데이터가 있는 영역
                    if len(valid_points) >= 4:  # 충분한 데이터가 있으면 cubic 보간
                        try:
                            grid_z[i,j] = griddata(np.array(valid_points),
                                                np.array(valid_temps),
                                                grid_point,
                                                method='cubic')
                        except Exception:
                            # cubic 보간 실패시 nearest로 폴백
                            min_dist_idx = np.argmin(valid_distances)
                            grid_z[i,j] = valid_temps[min_dist_idx]
                    else:  # 데이터가 부족하면 nearest neighbor 사용
                        min_dist_idx = np.argmin(valid_distances)
                        grid_z[i,j] = valid_temps[min_dist_idx]
                else:
                    # 모든 센서가 차단된 경우, 가장 가까운 센서의 값을 사용
                    distances = [np.sqrt((p[0]-grid_point[0])**2 + (p[1]-grid_point[1])**2) 
                               for p in points]
                    min_dist_idx = np.argmin(distances)
                    grid_z[i,j] = temperatures[min_dist_idx]
                    # 벽으로 차단된 영역은 no_data_mask를 True로 유지
        
        # NaN 값을 주변 값으로 채우기
        mask = np.isnan(grid_z)
        grid_z[mask] = griddata(
            (grid_x[~mask], grid_y[~mask]),
            grid_z[~mask],
            (grid_x[mask], grid_y[mask]),
            method='nearest'
        )
        
        return grid_z, no_data_mask

    def _collect_sensor_data(self) -> Tuple[List[List[float]], List[float]]:
        """센서 데이터를 수집하여 위치와 온도 값을 반환합니다."""
        points = []
        temperatures = []
        
        for sensor in self.sensors_data:
            try:
                if not sensor.get('position'):
                    logger.debug(f"센서 위치 정보 없음: {sensor['entity_id']}")
                    continue
                
                state = self.get_sensor_state(sensor['entity_id'])
                logger.debug(f"센서 상태 데이터: {state}")
                
                # 온도 값 처리
                temp = float(state['state'])
                logger.debug(f"변환된 온도 값: {temp}")
                
                # 위치 값 처리
                position = sensor['position']
                logger.debug(f"센서 위치 데이터: {position}")
                
                # position 형식에 따른 처리
                if isinstance(position, dict):
                    # 딕셔너리 형식 (예: {'x': 301, 'y': 218})
                    if 'x' in position and 'y' in position:
                        x = float(position['x'])
                        y = float(position['y'])
                        logger.debug(f"딕셔너리에서 변환된 위치 값: x={x}, y={y}")
                        points.append([x, y])
                        temperatures.append(temp)
                    else:
                        logger.warning(f"잘못된 딕셔너리 위치 형식: {position}")
                        continue
                elif isinstance(position, list) and len(position) == 2:
                    # 리스트 형식 (예: [301, 218])
                    x = float(position[0]) if isinstance(position[0], str) else position[0]
                    y = float(position[1]) if isinstance(position[1], str) else position[1]
                    logger.debug(f"리스트에서 변환된 위치 값: x={x}, y={y}")
                    points.append([x, y])
                    temperatures.append(temp)
                else:
                    logger.warning(f"지원하지 않는 위치 형식: {position}")
                    continue
                
            except (ValueError, KeyError, TypeError, IndexError) as e:
                logger.warning(f"센서 데이터 변환 실패: {sensor.get('entity_id', 'unknown')} - {str(e)}")
                continue

        logger.info(f"수집된 센서 데이터: points={points}, temperatures={temperatures}")
        return points, temperatures

    def _calculate_bounds(self, coords: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
        """좌표들의 경계를 계산합니다."""
        min_x = min(x for x, _ in coords)
        max_x = max(x for x, _ in coords)
        min_y = min(y for _, y in coords)
        max_y = max(y for _, y in coords)
        return min_x, max_x, min_y, max_y

    def generate(self, output_path: str) -> bool:
        """
        온도맵을 생성하고 저장합니다.
        
        Args:
            output_path: 결과 이미지를 저장할 경로
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 벽 데이터 파싱
            coords, root = self._parse_walls()
            if not coords:
                logger.error("벽 좌표를 찾을 수 없습니다")
                return False

            # 센서 데이터 수집
            points, temperatures = self._collect_sensor_data()
            if not points:
                logger.error("유효한 센서 데이터가 없습니다")
                return False

            # 경계 계산
            min_x, max_x, min_y, max_y = self._calculate_bounds(coords)
            bounds = (min_x, max_x, min_y, max_y)

            # 경계 포인트 추가
            extended_points, extended_temps = self._add_boundary_points(points, temperatures, bounds)

            # 격자 생성
            grid_x, grid_y = np.mgrid[
                min_x-self.padding:max_x+self.padding:100j,
                min_y-self.padding:max_y+self.padding:100j
            ]

            # 벽을 고려한 보간 수행
            grid_z, no_data_mask = self._interpolate_with_walls(grid_x, grid_y, extended_points, extended_temps)

            # 플롯 생성
            plt.figure(figsize=(10, 10))

            # y축 반전
            plt.gca().invert_yaxis()

            # 온도 분포 그리기 (알파값 조정)
            contour = plt.contourf(grid_x, grid_y, grid_z, alpha=1.0, cmap='RdYlBu_r')
            plt.colorbar(contour, label='Temperature (°C)')

            # 데이터가 없는 영역 빗금 표시 (알파값과 색상 조정)
            plt.contourf(grid_x, grid_y, no_data_mask, colors='none', hatches=['///'], alpha=0.3)

            # 벽 그리기
            for line in root.findall('.//{*}line'):
                x1 = float(line.get('x1', 0))
                y1 = float(line.get('y1', 0))
                x2 = float(line.get('x2', 0))
                y2 = float(line.get('y2', 0))
                plt.plot([x1, x2], [y1, y2], 'black', linewidth=2)

            # 센서 위치 표시
            sensor_x = [p[0] for p in points]
            sensor_y = [p[1] for p in points]
            plt.scatter(sensor_x, sensor_y, c='red', s=50)

            # 축 설정
            plt.axis('equal')
            plt.axis('off')

            # 저장
            plt.savefig(output_path,
                       bbox_inches='tight',
                       pad_inches=0,
                       dpi=300)
            plt.close()

            return True

        except Exception as e:
            logger.error(f"온도맵 생성 중 오류 발생: {str(e)}")
            return False 