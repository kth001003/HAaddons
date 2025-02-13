export class SensorManager {
    constructor(svgElement) {
        this.svg = svgElement;
        this.sensors = [];
        this.onSensorsUpdate = null;
        this.enabled = true;

        // SVG viewBox 파싱
        const viewBox = this.svg.getAttribute('viewBox');
        if (viewBox) {
            const [minX, minY, width, height] = viewBox.split(' ').map(Number);
            this.viewBox = { minX, minY, width, height };
        } else {
            this.viewBox = { minX: 0, minY: 0, width: this.svg.clientWidth, height: this.svg.clientHeight };
        }

        // 이벤트 핸들러 바인딩
        this.handleDragStart = this.handleDragStart.bind(this);
        this.handleDragOver = this.handleDragOver.bind(this);
        this.handleDrop = this.handleDrop.bind(this);
        this.handleCheckboxChange = this.handleCheckboxChange.bind(this);

        // SVG 이벤트 리스너 등록
        this.svg.addEventListener('dragover', this.handleDragOver);
        this.svg.addEventListener('drop', this.handleDrop);

          // 상수 정의
        this.MARKER_RADIUS = 5;
        this.MARKER_FILL = 'red';
        this.TEXT_FILL = 'black';
        this.TEXT_SIZE = '12';
        this.RECT_FILL = 'white';
        this.RECT_OPACITY = '0.8';
        this.RECT_RADIUS = '3';
    }

    enable() {
        this.enabled = true;
        this.updateSensorList();
    }

    disable() {
        this.enabled = false;
        this.updateSensorList();
    }

    // 센서 데이터 로드
    async loadSensors() {
        try {
            // 센서 상태 로드
            const response = await fetch('./api/states');
            const states = await response.json();
            console.log("SensorManager - 서버에서 받은 states:", states);
            this.sensors = states.filter(state =>
                state.attributes.device_class === 'temperature'
            );
            // 저장된 설정 로드
            const configResponse = await fetch('./api/load-config');
            if (configResponse.ok) {
                const config = await configResponse.json();
      
                // 저장된 센서 위치 정보를 현재 센서 데이터에 적용
                if (config.sensors) {
                    config.sensors.forEach(savedSensor => {
                        const sensor = this.sensors.find(s => s.entity_id === savedSensor.entity_id);
                        const placedSensor = this.svg.querySelector(`g[data-entity-id="${savedSensor.entity_id}"]`);
                        if (sensor && savedSensor.position && ! placedSensor) {
                            sensor.position = savedSensor.position;
                            sensor.calibration = savedSensor.calibration || 0;
                            this.updateSensorMarker(sensor, savedSensor.position);
                        }
                    });
                }
            }
      
            this.updateSensorList();
        } catch (error) {
            console.error('센서 정보를 불러오는데 실패했습니다:', error);
              this.displayError(`센서 정보를 불러오는데 실패했습니다: ${error.message}`);
        }
    }
    async refreshSensors() {
        try {
            // 센서 상태 로드
            const response = await fetch('./api/states');
            const states = await response.json();
            const newSensors = states.filter(state =>
                state.attributes.device_class === 'temperature'
            );
            this.sensors.forEach(sensor => {
                const newSensor = newSensors.find(newSensor => newSensor.entity_id === sensor.entity_id);
                if (newSensor) {
                    sensor.state = newSensor.state;
                }
            });
            this.updateSensorList();
        } catch (error) {
            console.error('센서 정보를 불러오는데 실패했습니다:', error);
              this.displayError(`센서 정보를 불러오는데 실패했습니다: ${error.message}`);
        }
    }
    displayError(message) {
        const container = document.getElementById('sensor-container');
        if (container) {
            container.innerHTML = `
                <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-600">${message}</p>
                    <button id="retry-load-sensors" class="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-700">다시 로드</button>
                </div>
            `;
         document.getElementById('retry-load-sensors').addEventListener('click', this.loadSensors.bind(this));
        }
    }
    
   // 센서 목록 UI 업데이트
    updateSensorList() {
        const container = document.getElementById('sensor-container');
        if (!container) return;

        if (!this.sensors || this.sensors.length === 0) {
            container.innerHTML = `
                <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                    <p class="text-yellow-600">사용 가능한 온도 센서가 없습니다.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.sensors.map(sensor => this.createSensorListItem(sensor)).join('');
        
        // 체크박스 이벤트 설정
        if(this.enabled) {
            container.querySelectorAll('.sensor-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', this.handleCheckboxChange);
            });

            // 보정값 입력 이벤트 설정
            container.querySelectorAll('.calibration-input').forEach(input => {
                input.addEventListener('change', (e) => this.handleCalibrationChange(e));
                input.addEventListener('click', (e) => e.stopPropagation());
            });
         }
    }
    
    createSensorListItem(sensor) {
         const isPlaced = sensor.position !== undefined;
        const itemClass = 'sensor-item p-3 bg-white border border-gray-200 rounded-md shadow-sm hover:shadow-md transition-shadow cursor-pointer flex justify-between items-center';
        const calibration = sensor.calibration || 0;
        const calibratedTemp = parseFloat(sensor.state) + calibration;

        return `
            <div class="${itemClass}" data-entity-id="${sensor.entity_id}">
                <div class="flex-1">
                     <div class="flex items-center">
                        <input type="checkbox"
                            class="sensor-checkbox mr-2"
                            data-entity-id="${sensor.entity_id}"
                            ${isPlaced ? 'checked' : ''}
                            ${this.enabled ? '' : 'disabled'}
                        >
                        <span class="font-medium">${sensor.attributes.friendly_name || sensor.entity_id}</span>
                    </div>
                    <div class="flex items-center mt-1">
                        <span class="text-xs text-gray-600 mr-2">측정값: ${sensor.state}°C</span>
                        <span class="text-xs text-blue-600">보정값: 
                            <input type="number" 
                                class="calibration-input text-xs w-16 px-1 py-0.5 border border-gray-300 rounded"
                                value="${calibration}"
                                step="0.1"
                                data-entity-id="${sensor.entity_id}"
                                ${this.enabled ? '' : 'disabled'}
                            > °C
                        </span>
                        <span class="text-xs text-green-600 ml-2">보정후: ${calibratedTemp.toFixed(1)}°C</span>
                    </div>
                </div>
            </div>
        `;
    }
    handleCalibrationChange(e) {
        const entityId = e.target.dataset.entityId;
        const calibration = parseFloat(e.target.value) || 0;
        const sensor = this.sensors.find(s => s.entity_id === entityId);
        if (sensor) {
            sensor.calibration = calibration;
            this.updateSensorList();
        }
    }

    // 체크박스 변경 핸들러
    handleCheckboxChange(e) {
        if (!this.enabled) {
            e.preventDefault();
            return;
        }

        const entityId = e.target.dataset.entityId;
        const sensor = this.sensors.find(s => s.entity_id === entityId);

        if (!sensor) return;

        if (e.target.checked) {
            if (!sensor.position) {
                 sensor.position = this.getRandomCenterPoint();
                this.updateSensorMarker(sensor,  sensor.position);
            }

        } else {
             sensor.position = undefined;
            this.removeSensorMarker(entityId);
        }
    }
   getRandomCenterPoint() {
        const {minX, minY, width, height} = this.viewBox;
        const randX = Math.round(Math.random()*100) -50;
        const randY = Math.round(Math.random()*100) -50;
            return {
                x: (minX + width / 2) + randX,
                y: (minY + height / 2) + randY
            };
    }
    removeSensorMarker(entityId) {
           const marker = this.svg.querySelector(`g[data-entity-id="${entityId}"]`);
           if (marker) marker.remove();
   }

    // 드래그 앤 드롭 핸들러
    handleDragStart(e) {
        if (!this.enabled) return;
        e.dataTransfer.setData('text/plain', e.target.dataset.entityId);
        e.dataTransfer.effectAllowed = 'move';
    }

    handleDragOver(e) {
        if (!this.enabled) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }

    handleDrop(e) {
        if (!this.enabled) return;
        e.preventDefault();
       
        const entityId = e.dataTransfer.getData('text/plain');
        if (!entityId) return;
        
        const sensor = this.sensors.find(s => s.entity_id === entityId);
        if(sensor){
           const point = this.clientToSVGPoint(e.clientX, e.clientY);
            this.updateSensorPosition(sensor, point);
        }
    }

    // 센서 위치 업데이트
    updateSensorPosition(sensor, point) {
        if (!this.enabled || !sensor) return;
        sensor.position = point;
        this.updateSensorMarker(sensor, point);
    }

  
   // 센서 마커 업데이트
   updateSensorMarker(sensor, point) {
        let group = this.svg.querySelector(`g[data-entity-id="${sensor.entity_id}"]`);

        if (!group) {
            group = this.createSensorMarkerGroup(sensor);
        }
        this.updateMarkerPosition(group,sensor, point);
        this.setupDragEvents(group, sensor, point);
    }

    createSensorMarkerGroup(sensor) {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('data-entity-id', sensor.entity_id);
        group.setAttribute('draggable', 'true');
        group.style.cursor = 'move';

        // 배경 사각형 생성
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('rx', '3');
        rect.setAttribute('ry', '3');
        rect.style.pointerEvents = 'none';
        const config = /** @type {{
            sensor_display: string,
            sensor_info_bg: { color: string, opacity: number },
            sensor_marker: { style: string, size: number, color: string },
            sensor_name: { font_size: number, color: string },
            sensor_temp: { font_size: number, color: string }
        }} */ (this.getVisualizationConfig());
        rect.setAttribute('fill', config.sensor_info_bg.color);
        rect.setAttribute('fill-opacity', String(config.sensor_info_bg.opacity / 100));

        // 센서 위치 마커 생성 (드래그를 위한 투명한 원)
        const dragHandle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dragHandle.setAttribute('r', '10');  // 드래그 영역을 위한 충분한 크기
        dragHandle.setAttribute('fill', 'transparent');  // 투명하게 설정
        dragHandle.style.pointerEvents = 'all';  // 이벤트 처리 활성화

        // 텍스트 생성
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'middle');
        text.style.pointerEvents = 'none';

        group.appendChild(rect);
        group.appendChild(dragHandle);  // 드래그 핸들을 먼저 추가
        group.appendChild(text);

        this.svg.appendChild(group);
        return group;
    }

    getVisualizationConfig() {
        const genConfigElement = document.getElementById('save-gen-configs');
        if (!genConfigElement) return {};
        
        return {
            sensor_display: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option'))?.value ?? 'position_temp',
            sensor_info_bg: {
                color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-bg-color'))?.value ?? '#FFFFFF',
                opacity: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('sensor-info-bg-opacity'))?.value ?? '70')
            },
            sensor_marker: {
                style: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-marker-style'))?.value ?? 'circle',
                size: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('sensor-marker-size'))?.value ?? '10'),
                color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-marker-color'))?.value ?? '#FF0000'
            },
            sensor_name: {
                font_size: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('sensor-name-font-size'))?.value ?? '12'),
                color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-name-color'))?.value ?? '#000000'
            },
            sensor_temp: {
                font_size: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('sensor-temp-font-size'))?.value ?? '12'),
                color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-temp-color'))?.value ?? '#000000'
            }
        };
    }

    createMarkerPath(style, size, x, y) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.classList.add('sensor-marker');
        
        let d = '';
        switch (style) {
            case 'circle':
                d = `M ${x} ${y} m -${size} 0 a ${size} ${size} 0 1 0 ${size*2} 0 a ${size} ${size} 0 1 0 -${size*2} 0`;
                break;
            case 'square':
                d = `M ${x-size} ${y-size} h ${size*2} v ${size*2} h -${size*2} z`;
                break;
            case 'triangle':
                d = `M ${x} ${y-size} l ${size} ${size*1.732} h -${size*2} z`;
                break;
            case 'star':
                const outerPoints = [];
                const innerPoints = [];
                for (let i = 0; i < 5; i++) {
                    const outerAngle = (i * 72 - 90) * Math.PI / 180;
                    const innerAngle = (i * 72 - 90 + 36) * Math.PI / 180;
                    outerPoints.push(`${x + size * Math.cos(outerAngle)} ${y + size * Math.sin(outerAngle)}`);
                    innerPoints.push(`${x + size * 0.4 * Math.cos(innerAngle)} ${y + size * 0.4 * Math.sin(innerAngle)}`);
                }
                const points = [];
                for (let i = 0; i < 5; i++) {
                    points.push(outerPoints[i], innerPoints[i]);
                }
                d = `M ${points[0]} L ${points.slice(1).join(' L ')} Z`;
                break;
            case 'cross':
                d = `M ${x-size} ${y} h ${size*2} M ${x} ${y-size} v ${size*2}`;
                break;
            default:
                d = `M ${x} ${y} m -${size} 0 a ${size} ${size} 0 1 0 ${size*2} 0 a ${size} ${size} 0 1 0 -${size*2} 0`;
        }
        path.setAttribute('d', d);
        return path;
    }

    updateMarkerPosition(group, sensor, point) {
        const text = group.querySelector('text');
        const rect = group.querySelector('rect');
        const dragHandle = group.querySelector('circle');  // 드래그 핸들 요소 가져오기
        const config = /** @type {{
            sensor_display: string,
            sensor_info_bg: { color: string, opacity: number },
            sensor_marker: { style: string, size: number, color: string },
            sensor_name: { font_size: number, color: string },
            sensor_temp: { font_size: number, color: string }
        }} */ (this.getVisualizationConfig());

        // 드래그 핸들 위치 업데이트
        dragHandle.setAttribute('cx', String(point.x));
        dragHandle.setAttribute('cy', String(point.y));

        // 마커 스타일 업데이트
        const markerConfig = config.sensor_marker;
        const markerSize = markerConfig.size;
        const markerStyle = markerConfig.style;
        const markerColor = markerConfig.color;

        // 기존 마커 제거
        const oldPath = group.querySelector('path.sensor-marker');
        if (oldPath) {
            oldPath.remove();
        }

        // 새 마커 생성
        const markerPath = this.createMarkerPath(markerStyle, markerSize, point.x, point.y);
        markerPath.setAttribute('fill', markerStyle === 'cross' ? 'none' : markerColor);
        markerPath.setAttribute('stroke', markerColor);
        markerPath.setAttribute('stroke-width', markerStyle === 'cross' ? '2' : '0');
        markerPath.style.pointerEvents = 'none';
        group.appendChild(markerPath);

        // 텍스트 내용 초기화
        while (text.firstChild) {
            text.removeChild(text.firstChild);
        }

        // 텍스트 위치 설정
        text.setAttribute('x', String(point.x));
        text.setAttribute('y', String(point.y - markerSize - 5));
        
        const displayOption = config.sensor_display;
        const calibratedTemp = this.getCalibratedTemperature(sensor);
        
        // 센서 이름 표시
        if (displayOption.includes('name')) {
            const nameConfig = config.sensor_name;
            const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
            nameText.textContent = sensor.attributes.friendly_name || sensor.entity_id;
            nameText.setAttribute('x', String(point.x));
            nameText.setAttribute('font-size', String(nameConfig.font_size));
            nameText.setAttribute('fill', nameConfig.color);
            text.appendChild(nameText);
        }

        // 온도 표시
        if (displayOption.includes('temp')) {
            const tempConfig = config.sensor_temp;
            const tempText = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
            tempText.textContent = `${calibratedTemp.toFixed(1)}°C`;
            tempText.setAttribute('x', String(point.x));
            tempText.setAttribute('dy', displayOption.includes('name') ? String(tempConfig.font_size) : '0');
            tempText.setAttribute('font-size', String(tempConfig.font_size));
            tempText.setAttribute('fill', tempConfig.color);
            text.appendChild(tempText);
        }

        // 배경 사각형 업데이트
        const textBBox = text.getBBox();
        const padding = 4;
        rect.setAttribute('x', String(point.x - textBBox.width/2 - padding));
        rect.setAttribute('y', String(point.y - textBBox.height - markerSize - padding));
        rect.setAttribute('width', String(textBBox.width + padding * 2));
        rect.setAttribute('height', String(textBBox.height + padding * 2));
        rect.setAttribute('fill', config.sensor_info_bg.color);
        rect.setAttribute('fill-opacity', String(config.sensor_info_bg.opacity / 100));
    }

    setupDragEvents(group, sensor, point) {
        let isDragging = false;
        let startX = 0;
        let startY = 0;
        let offsetX = 0;
        let offsetY = 0;
        let dragStartPoint = { x: 0, y: 0 };
        
        const handleMouseDown = (e) => {
            if (!this.enabled) return;
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;

            dragStartPoint = this.clientToSVGPoint(e.clientX, e.clientY);
            offsetX = dragStartPoint.x - point.x;
            offsetY = dragStartPoint.y - point.y;

            group.style.pointerEvents = 'none';
            e.stopPropagation();
        };

        const handleMouseMove = (e) => {
            if (!isDragging) return;
            const currentSVGPoint = this.clientToSVGPoint(e.clientX, e.clientY);

            const newPoint = {
                x: currentSVGPoint.x - offsetX,
                y: currentSVGPoint.y - offsetY
            };
            this.updateMarkerPosition(group, sensor, newPoint);
            sensor.position = newPoint;
            point = newPoint;
            e.stopPropagation();
        };

        const handleMouseUp = (e) => {
            if (!isDragging) return;
            isDragging = false;
            group.style.pointerEvents = 'auto';
            e.stopPropagation();
        };

        // 기존 이벤트 리스너 제거
        if (group._eventHandlers) {
            group.removeEventListener('mousedown', group._eventHandlers.mouseDown);
            document.removeEventListener('mousemove', group._eventHandlers.mouseMove);
            document.removeEventListener('mouseup', group._eventHandlers.mouseUp);
        }

        // 새로운 핸들러 등록
        group._eventHandlers = {
            mouseDown: handleMouseDown,
            mouseMove: handleMouseMove,
            mouseUp: handleMouseUp
        };

        group.addEventListener('mousedown', handleMouseDown);
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }
    // 클라이언트 좌표를 SVG 좌표로 변환
    clientToSVGPoint(clientX, clientY) {
        const rect = this.svg.getBoundingClientRect();
        // svg는 1:1 ratio
        const rect_size = Math.min(rect.width, rect.height)
        const scaleX = this.viewBox.width / rect_size;
        const scaleY = this.viewBox.height / rect_size;
        return {
            x: (clientX - rect.left) * scaleX + this.viewBox.minX,
            y: (clientY - rect.top) * scaleY + this.viewBox.minY
        };
   }

    // SVG 좌표를 클라이언트 좌표로 변환
    svgToClientPoint(svgX, svgY) {
        const rect = this.svg.getBoundingClientRect();
        const scaleX = rect.width / this.viewBox.width;
        const scaleY = rect.height / this.viewBox.height;

        return {
            x: (svgX - this.viewBox.minX) * scaleX + rect.left,
            y: (svgY - this.viewBox.minY) * scaleY + rect.top
        };
    }

    // 현재 센서 데이터 반환
    getSensors() {
        return this.sensors;
    }

    // 설정 저장을 위한 센서 데이터 반환
    getSensorConfig() {
        return this.sensors.map(sensor => ({
            entity_id: sensor.entity_id,
            position: sensor.position || null,
            calibration: sensor.calibration || 0
        }));
    }

    // 보정된 온도값 반환
    getCalibratedTemperature(sensor) {
        const rawTemp = parseFloat(sensor.state);
        const calibration = sensor.calibration || 0;
        return rawTemp + calibration;
    }
}