export class UIManager {
    constructor() {
        this.mapId = new URLSearchParams(window.location.search).get('id');
        this.currentTool = 'select';
        this.drawingTool = null;
        this.sensorManager = null;
        this.settingsManager = null;
        this.thermalMapManager = null;
        this.lastSavedState = null;
        this.svg = document.getElementById('svg-overlay');
        this.messageContainer = document.getElementById('message-container');
        this.confirmModal = document.getElementById('confirm-modal');
        this.lastSavedHistoryIndex = 0; // 마지막으로 저장된 히스토리 인덱스
        this.lastSavedSettings = null; // 마지막으로 저장된 설정 상태
        this.initializeTabs();
        this.initializeSettingsTabs();
        this.initializeDrawingTools();
        this.initializeFloorplanUpload();
        this.initializeSensorPanel();
        this.initializeConfirmModal();
    }

    showMessage(message, type = 'info') {
        const messageElement = document.createElement('div');
        messageElement.className = `px-4 py-2 rounded-lg shadow-md mx-auto max-w-lg text-center ${
            type === 'error' ? 'bg-red-500 text-white' :
            type === 'success' ? 'bg-green-500 text-white' :
            'bg-blue-500 text-white'
        }`;
        messageElement.innerHTML = `<i class="mdi mdi-information"></i> ${message}`;
        this.messageContainer.innerHTML = '';
        this.messageContainer.appendChild(messageElement);

        setTimeout(() => {
            messageElement.remove();
        }, 3000);
    }

    initializeTabs() {
        this.tabs = {
            map: document.getElementById('map-content'),
            map_edit: document.getElementById('map-edit-content'),
            settings: document.getElementById('settings-content'),
            debug: document.getElementById('debug-content')
        };

        this.tabButtons = {
            map: document.getElementById('map-tab'),
            map_edit: document.getElementById('map-edit-tab'),
            settings: document.getElementById('settings-tab'),
            debug: document.getElementById('debug-tab')
        };

        Object.keys(this.tabButtons).forEach(tabName => {
            this.tabButtons[tabName].addEventListener('click', () => this.switchTab(tabName));
        });

        // 초기 탭 설정 - 지도 탭을 기본으로 표시
        this.switchTab('map');
    }

    switchTab(tabName) {
        // 현재 활성화된 탭 찾기
        const currentTab = Object.entries(this.tabs).find(([_, tab]) => !tab.classList.contains('hidden'))?.[0];

        // 지도 편집 탭이나 설정 탭에서 다른 탭으로 이동하려고 할 때
        if ((currentTab === 'map_edit' || currentTab === 'settings') && currentTab !== tabName) {
            // 저장되지 않은 변경사항이 있는지 확인
            if (this.hasUnsavedChanges()) {
                this.showConfirmModal(
                    '저장 확인',
                    '저장되지 않은 변경사항이 있습니다. 어떻게 하시겠습니까?',
                    null,
                    [
                        {
                            text: '취소',
                            className: 'bg-gray-500 text-white hover:bg-gray-600 mr-2'
                        },
                        {
                            text: '저장 안함',
                            className: 'bg-red-500 text-white hover:bg-red-600 mr-2',
                            action: () => this.performTabSwitch(tabName)
                        },
                        {
                            text: '저장',
                            className: 'bg-blue-500 text-white hover:bg-blue-600',
                            action: async () => {
                                if (currentTab === 'map_edit') {
                                    await this.saveWallsAndSensors();
                                } else if (currentTab === 'settings') {
                                    await this.settingsManager.saveAllSettings();
                                }
                                this.performTabSwitch(tabName);
                            }
                        }
                    ]
                );
                return;
            }
        }

        this.performTabSwitch(tabName);
    }

    performTabSwitch(tabName) {
        Object.values(this.tabs).forEach(tab => tab.classList.add('hidden'));
        Object.values(this.tabButtons).forEach(btn => {
            btn.classList.remove('text-gray-900', 'border-b-2', 'border-blue-500');
            btn.classList.add('text-gray-500');
        });

        this.tabs[tabName].classList.remove('hidden');
        this.tabButtons[tabName].classList.remove('text-gray-500');
        this.tabButtons[tabName].classList.add('text-gray-900', 'border-b-2', 'border-blue-500');

        // 지도 편집 탭으로 이동할 때 센서 로드
        if (tabName === 'map_edit' && this.sensorManager) {
            this.showMessage('센서 로드 중...');
            this.sensorManager.loadSensors().then(() => {
                console.log('센서 로드 완료');
                this.showMessage('센서 로드 완료', 'success');
            }).catch(error => {
                console.error('센서 로드 실패:', error);
                this.showMessage('센서 로드에 실패했습니다.', 'error');
            });
        }
    }

    initializeSettingsTabs() {
        this.settingsTabs = {
            interpolation: document.getElementById('interpolation-content'),
            generation: document.getElementById('generation-content'),
            range: document.getElementById('range-content'),
            display: document.getElementById('display-content'),
            sensorMarker: document.getElementById('sensor-marker-content'),
            colorbar: document.getElementById('colorbar-content')
        };

        this.settingsTabButtons = {
            interpolation: document.getElementById('interpolation-tab'),
            generation: document.getElementById('generation-tab'),
            range: document.getElementById('range-tab'),
            display: document.getElementById('display-tab'),
            sensorMarker: document.getElementById('sensor-marker-tab'),
            colorbar: document.getElementById('colorbar-tab')
        };

        Object.keys(this.settingsTabButtons).forEach(tabName => {
            this.settingsTabButtons[tabName].addEventListener('click', () => this.switchSettingsTab(tabName));
        });

        // 초기 설정 탭 설정
        this.switchSettingsTab('generation');
    }

    switchSettingsTab(tabName) {
        Object.values(this.settingsTabs).forEach(tab => tab.classList.add('hidden'));
        Object.values(this.settingsTabButtons).forEach(btn => {
            btn.classList.remove('text-gray-900', 'border-blue-500');
            btn.classList.add('text-gray-500', 'border-transparent');
        });

        this.settingsTabs[tabName].classList.remove('hidden');
        this.settingsTabButtons[tabName].classList.remove('text-gray-500', 'border-transparent');
        this.settingsTabButtons[tabName].classList.add('text-gray-900', 'border-blue-500');
    }

    initializeDrawingTools() {
        // 선 두께 조절
        const lineWidthInput = /** @type {HTMLInputElement} */ (document.getElementById('line-width'));
        const lineWidthValue = document.getElementById('line-width-value');

        if (lineWidthInput && lineWidthValue) {
            lineWidthInput.addEventListener('input', () => {
                const width = parseInt(lineWidthInput.value);
                lineWidthValue.textContent = `${width}px`;
                if (this.drawingTool) {
                    this.drawingTool.setLineWidth(width);
                }
            });
        }

        // 도구 버튼 이벤트 리스너
        document.getElementById('select-tool')?.addEventListener('click', () => {
            this.setActiveTool('select');
        });

        document.getElementById('line-tool')?.addEventListener('click', () => {
            this.setActiveTool('line');
        });

        document.getElementById('eraser-tool')?.addEventListener('click', () => {
            this.setActiveTool('eraser');
        });

        document.getElementById('sensor-list-tool')?.addEventListener('click', () => {
            this.toggleSensorPanel();
        });

        // 초기화 버튼 이벤트 리스너
        document.getElementById('clear-btn')?.addEventListener('click', () => {
            this.showConfirmModal(
                '초기화',
                '모든 벽과 센서를 삭제하시겠습니까?',
                () => {
                    if (this.drawingTool) {
                        this.drawingTool.clear();
                    }
                    if (this.sensorManager) {
                        this.sensorManager.removeAllSensors();
                    }
                    this.showMessage('모든 벽과 센서가 삭제되었습니다.', 'success');
                }
            );
        });

        // 다시로드 버튼 이벤트 리스너
        document.getElementById('reload-btn')?.addEventListener('click', () => {
            this.showConfirmModal(
                '다시로드',
                '저장 되지 않은 변경을 취소하고 저장된 정보를 다시 불러오시겠습니까?',
                async () => {
                    try {
                        this.loadWallsAndSensors();
                    } catch (error) {
                        console.error('설정 로드 실패:', error);
                        this.showMessage('설정을 불러오는데 실패했습니다.', 'error');
                    }
                }
            );
        });

        // 저장 버튼 이벤트 리스너
        document.getElementById('save-walls-sensors')?.addEventListener('click', async () => {
            await this.saveWallsAndSensors();
        });

        // SVG 이동을 위한 이벤트 리스너
        this.initializeSVGPan();
    }

    // 저장되지 않은 변경사항이 있는지 확인
    hasUnsavedChanges() {
        const currentTab = Object.entries(this.tabs).find(([_, tab]) => !tab.classList.contains('hidden'))?.[0];
        
        if (currentTab === 'map_edit') {
            if (!this.drawingTool) return false;
            return this.drawingTool.currentHistoryIndex !== this.lastSavedHistoryIndex;
        } else if (currentTab === 'settings') {
            return this.hasSettingsChanged();
        }
        
        return false;
    }

    // 설정 변경 여부 확인
    hasSettingsChanged() {
        if (!this.lastSavedSettings) return true;

        const currentSettings = this.getCurrentSettings();
        return !this.areSettingsEqual(currentSettings, this.lastSavedSettings);
    }

    // 현재 설정값들 가져오기
    getCurrentSettings() {
        if (!this.settingsManager) return null;

        const settings = {
            interpolation: this.settingsManager.collectInterpolationParams(),
            generation: this.settingsManager.collectGenConfig(),
        };

        return settings;
    }

    // 설정값 비교
    areSettingsEqual(settings1, settings2) {
        if (!settings1 || !settings2) return false;
        console.log(settings1, settings2);
        return JSON.stringify(settings1) === JSON.stringify(settings2);
    }

    // 설정 저장 시 현재 상태 저장
    saveCurrentSettings() {
        this.lastSavedSettings = this.getCurrentSettings();
    }

    async saveWallsAndSensors() {
        try {
            const svg = document.getElementById('svg-overlay');
            if (!svg || !this.sensorManager) {
                throw new Error('SVG 또는 센서 매니저를 찾을 수 없습니다.');
            }

            const wallsElements = svg.querySelectorAll('line, path.area');
            let wallsHTML = '';
            wallsElements.forEach(element => {
                wallsHTML += element.outerHTML;
            });
            const wallsData = wallsHTML;
            this.sensorManager.parseSensorsFromSVG();
            const sensorConfig = this.sensorManager.getSensorConfig();
            const unit = sensorConfig.unit;
            const sensorsData = sensorConfig.sensors;
            
            await fetch(`./api/save-walls-and-sensors/${this.mapId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ wallsData, sensorsData, unit })
            });

            // 저장 성공 시 현재 히스토리 인덱스를 저장
            if (this.drawingTool) {
                this.lastSavedHistoryIndex = this.drawingTool.currentHistoryIndex;
            }

            this.showMessage('벽과 센서위치를 저장했습니다.', 'success');
        } catch (error) {
            console.error('벽 및 센서 저장 실패:', error);
            this.showMessage('벽 저장에 실패했습니다.', 'error');
        }
    }

    updateSVGContent(newContent) {
        if (!this.svg) {
            console.error('SVG 요소를 찾을 수 없습니다.');
            return;
        }

        // 마커용 defs 임시 저장
        const defs = this.svg.querySelector('defs');
        if (defs) defs.remove();

        // SVG 내용 업데이트
        this.svg.innerHTML = newContent;

        // floorplan-rect가 없으면 추가
        if (!this.svg.querySelector('#floorplan-rect')) {
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('id', 'floorplan-rect');
            rect.setAttribute('width', '100%');
            rect.setAttribute('height', '100%');
            rect.setAttribute('fill', '#FFFFFF');
            this.svg.insertBefore(rect, this.svg.firstChild);
        }

        // 마커용 defs 복원
        if (defs) {
            this.svg.insertBefore(defs, this.svg.firstChild);
        } else if (this.drawingTool) {
            this.drawingTool.initializeDefs();
        }

        // 센서 정보 다시 파싱
        if (this.sensorManager) {
            this.sensorManager.parseSensorsFromSVG();
        }
    }

    async loadWallsAndSensors() {
        const svg = this.svg;
        const sensorManager = this.sensorManager;
        const drawingTool = this.drawingTool;
        try {
            const response = await fetch(`./api/load-config/${this.mapId}`);
            if (response.ok) {
                const config = await response.json();
                if (config.walls) {
                    this.updateSVGContent(config.walls);
                }
                if (config.sensors) {
                    config.sensors.forEach(savedSensor => {
                        const sensor = sensorManager.sensors.find(s => s.entity_id === savedSensor.entity_id);
                        if (sensor && savedSensor.position) {
                            sensor.position = savedSensor.position;
                            sensor.calibration = savedSensor.calibration || 0;
                            sensorManager.updateSensorMarker(sensor, savedSensor.position);
                        }
                    });
                }
                // 로드 성공 시 현재 히스토리 인덱스를 저장
                if (drawingTool) {
                    drawingTool.resetState();
                    this.lastSavedHistoryIndex = drawingTool.currentHistoryIndex;
                }
            }
        } catch (error) {
            console.error('설정을 불러오는데 실패했습니다:', error);
        }
    }
    initializeSVGPan() {
        const svgContainer = document.getElementById('svg-overlay-container');
        const resetTransformBtn = document.getElementById('reset-transform-btn');
        let isDragging = false;
        let startX = 0;
        let startY = 0;
        let currentTranslateX = 0;
        let currentTranslateY = 0;
        let currentScale = 1;
        let lastTouchDistance = 0;

        // 핀치 줌을 위한 터치 이벤트
        svgContainer.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                lastTouchDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
            }
        }, { passive: false });

        svgContainer.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                const currentDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );

                if (lastTouchDistance > 0) {
                    const scaleChange = currentDistance / lastTouchDistance;
                    const newScale = Math.min(Math.max(currentScale * scaleChange, 0.1), 5);

                    // 두 손가락의 중간점 계산
                    const centerX = (touch1.clientX + touch2.clientX) / 2;
                    const centerY = (touch1.clientY + touch2.clientY) / 2;
                    const rect = svgContainer.getBoundingClientRect();
                    const mouseX = centerX - rect.left;
                    const mouseY = centerY - rect.top;

                    // 현재 위치에서 중간점까지의 거리
                    const distanceX = mouseX - currentTranslateX;
                    const distanceY = mouseY - currentTranslateY;

                    // 새로운 거리 계산
                    const newDistanceX = distanceX * scaleChange;
                    const newDistanceY = distanceY * scaleChange;

                    // 새로운 위치 계산
                    currentTranslateX = mouseX - newDistanceX;
                    currentTranslateY = mouseY - newDistanceY;
                    currentScale = newScale;

                    // 변환 적용
                    svgContainer.style.transform = `translate(${currentTranslateX}px, ${currentTranslateY}px) scale(${currentScale})`;

                    // 초기화 버튼 표시 여부
                    if (currentScale !== 1 || currentTranslateX !== 0 || currentTranslateY !== 0) {
                        resetTransformBtn?.classList.remove('opacity-0');
                    } else {
                        resetTransformBtn?.classList.add('opacity-0');
                    }
                }
                lastTouchDistance = currentDistance;
            }
        }, { passive: false });

        svgContainer.addEventListener('touchend', () => {
            lastTouchDistance = 0;
        });

        // 초기화 버튼 이벤트
        resetTransformBtn?.addEventListener('click', () => {
            currentTranslateX = 0;
            currentTranslateY = 0;
            currentScale = 1;
            svgContainer.style.transform = `translate(0px, 0px) scale(1)`;
            resetTransformBtn.classList.add('opacity-0');
        });

        // 마우스 휠 이벤트
        svgContainer.addEventListener('wheel', (e) => {
            if (this.currentTool !== 'select') return;
            e.preventDefault();

            const delta = e.deltaY;
            const scaleChange = delta > 0 ? 0.9 : 1.1; // 휠 방향에 따라 10% 확대/축소
            const newScale = Math.min(Math.max(currentScale * scaleChange, 0.1), 5); // 최소 0.1, 최대 5배

            // 마우스 포인터 위치를 기준으로 확대/축소
            const rect = svgContainer.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            // 새로운 위치 계산 (마우스 포인터 위치를 기준으로)
            currentTranslateX = mouseX - (mouseX - currentTranslateX) * scaleChange;
            currentTranslateY = mouseY - (mouseY - currentTranslateY) * scaleChange;
            currentScale = newScale;

            // 변환 적용
            svgContainer.style.transform = `translate(${currentTranslateX}px, ${currentTranslateY}px) scale(${currentScale})`;

            // 초기화 버튼 표시 여부
            if (currentScale !== 1 || currentTranslateX !== 0 || currentTranslateY !== 0) {
                resetTransformBtn?.classList.remove('opacity-0');
            } else {
                resetTransformBtn?.classList.add('opacity-0');
            }
        }, { passive: false });

        svgContainer.addEventListener('mousedown', (e) => {
            if (this.currentTool !== 'select') return;
            
            // 센서 요소나 선의 끝점 위에서는 이벤트 무시
            const target = /** @type {Element} */ (e.target);
            if (target.closest('g.sensor')) return;

            // 선의 끝점 근처인지 확인
            if (this.drawingTool?.isNearLineEndpoint(e)) return;

            isDragging = true;
            startX = e.clientX - currentTranslateX;
            startY = e.clientY - currentTranslateY;
            svgContainer.style.cursor = 'grabbing';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;

            const x = e.clientX - startX;
            const y = e.clientY - startY;
            
            currentTranslateX = x;
            currentTranslateY = y;
            
            svgContainer.style.transform = `translate(${x}px, ${y}px) scale(${currentScale})`;

            // 초기화 버튼 표시 여부
            if (x !== 0 || y !== 0 || currentScale !== 1) {
                resetTransformBtn?.classList.remove('opacity-0');
            } else {
                resetTransformBtn?.classList.add('opacity-0');
            }
        });

        document.addEventListener('mouseup', () => {
            isDragging = false;
            svgContainer.style.cursor = this.currentTool === 'select' ? 'grab' : 'default';
        });
    }

    setActiveTool(tool) {
        this.currentTool = tool;

        // 버튼 스타일 업데이트
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.classList.remove('bg-blue-500', 'text-white');
            btn.classList.add('bg-white', 'text-gray-700');
        });
        const activeBtn = document.getElementById(`${tool}-tool`);
        if (activeBtn) {
            activeBtn.classList.remove('bg-white', 'text-gray-700');
            activeBtn.classList.add('bg-blue-500', 'text-white');
        }

        // 도구별 기능 활성화/비활성화
        if (this.drawingTool) {
            if (['line', 'eraser'].includes(tool)) {
                this.drawingTool.enable();
                this.drawingTool.setTool(tool);
                if (this.sensorManager) this.sensorManager.disable();
            } else if (tool === 'select') {
                this.drawingTool.enable();
                this.drawingTool.setTool(tool);
                if (this.sensorManager) this.sensorManager.enable();
            }
        }

        // 커서 스타일 업데이트
        const svgContainer = document.getElementById('svg-overlay-container');
        if (svgContainer) {
            svgContainer.style.cursor = tool === 'select' ? 'grab' : 'default';
        }
    }

    setTools(drawingTool, sensorManager, settingsManager) {
        this.drawingTool = drawingTool;
        this.sensorManager = sensorManager;
        this.settingsManager = settingsManager;
        // 초기 도구 설정
        this.setActiveTool('select');
    }

    initializeFloorplanUpload() {
        const floorplanUpload = document.getElementById('floorplan-upload');
        const svgOverlay = document.getElementById('svg-overlay');
        const FIXED_SIZE = 1000; // SVG viewBox 크기

        if (floorplanUpload && svgOverlay) {
            floorplanUpload.addEventListener('change', (e) => {
                const input = /** @type {HTMLInputElement} */ (e.target);
                const file = input.files?.[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        const result = /** @type {string} */ (e.target?.result);
                        
                        // 기존 플로어플랜 관련 요소 제거
                        const oldDefs = svgOverlay.querySelector('defs.floorplan-defs');
                        if (oldDefs) oldDefs.remove();

                        // 임시 이미지로 원본 크기 측정
                        const tempImg = new Image();
                        tempImg.onload = () => {
                            const imgWidth = tempImg.naturalWidth;
                            const imgHeight = tempImg.naturalHeight;
                            const aspectRatio = imgWidth / imgHeight;

                            let width, height;
                            let x = 0, y = 0;

                            if (aspectRatio > 1) {
                                // 가로가 더 긴 경우
                                width = FIXED_SIZE;
                                height = FIXED_SIZE / aspectRatio;
                                y = (FIXED_SIZE - height) / 2;
                            } else {
                                // 세로가 더 긴 경우
                                height = FIXED_SIZE;
                                width = FIXED_SIZE * aspectRatio;
                                x = (FIXED_SIZE - width) / 2;
                            }

                            // SVG 요소 생성
                            const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                            defs.classList.add('floorplan-defs');
                            
                            // 패턴 생성
                            const pattern = document.createElementNS("http://www.w3.org/2000/svg", "pattern");
                            const image = document.createElementNS("http://www.w3.org/2000/svg", "image");
                            
                            // 필터 생성
                            const filter = document.createElementNS("http://www.w3.org/2000/svg", "filter");
                            const feFloodBackground = document.createElementNS("http://www.w3.org/2000/svg", "feFlood");
                            const feFloodOverlay = document.createElementNS("http://www.w3.org/2000/svg", "feFlood");
                            const feCompositeBackground = document.createElementNS("http://www.w3.org/2000/svg", "feComposite");
                            const feCompositeOverlay = document.createElementNS("http://www.w3.org/2000/svg", "feComposite");
                            
                            // 필터 설정
                            filter.setAttribute("id", "white-overlay");
                            
                            // 배경 흰색 레이어 생성
                            feFloodBackground.setAttribute("flood-color", "white");
                            feFloodBackground.setAttribute("flood-opacity", "1");
                            feFloodBackground.setAttribute("result", "background");
                            
                            // 배경과 이미지 합성
                            feCompositeBackground.setAttribute("in", "SourceGraphic");
                            feCompositeBackground.setAttribute("in2", "background");
                            feCompositeBackground.setAttribute("operator", "over");
                            feCompositeBackground.setAttribute("result", "backgrounded-image");
                            
                            // 오버레이 흰색 레이어 생성
                            feFloodOverlay.setAttribute("flood-color", "white");
                            feFloodOverlay.setAttribute("flood-opacity", "0.1");
                            feFloodOverlay.setAttribute("result", "overlay");
                            
                            // 최종 합성
                            feCompositeOverlay.setAttribute("in", "overlay");
                            feCompositeOverlay.setAttribute("in2", "backgrounded-image");
                            feCompositeOverlay.setAttribute("operator", "over");
                            
                            // 필터 조립
                            filter.appendChild(feFloodBackground);
                            filter.appendChild(feCompositeBackground);
                            filter.appendChild(feFloodOverlay);
                            filter.appendChild(feCompositeOverlay);

                            // 패턴 설정
                            pattern.setAttribute("id", "floorplan-pattern");
                            pattern.setAttribute("patternUnits", "userSpaceOnUse");
                            pattern.setAttribute("width", FIXED_SIZE.toString());
                            pattern.setAttribute("height", FIXED_SIZE.toString());

                            // 이미지 설정
                            image.setAttribute("href", result);
                            image.setAttribute("x", x.toString());
                            image.setAttribute("y", y.toString());
                            image.setAttribute("width", width.toString());
                            image.setAttribute("height", height.toString());
                            image.setAttribute("preserveAspectRatio", "none");
                            image.setAttribute("filter", "url(#white-overlay)");

                            // 기존 rect 업데이트
                            const floorplanRect = svgOverlay.querySelector('#floorplan-rect');
                            if (floorplanRect) {
                                floorplanRect.setAttribute("fill", "url(#floorplan-pattern)");
                            }

                            // 요소 조립
                            pattern.appendChild(image);
                            defs.appendChild(pattern);
                            defs.appendChild(filter);
                            
                            // SVG에 추가
                            svgOverlay.appendChild(defs);
                        };
                        tempImg.src = result;
                    };
                    reader.readAsDataURL(file);
                }
            });
        }
    }

    initializeSensorPanel() {
        const sensorPanel = document.getElementById('sensor-panel');
        let isPanelOpen = false;

        // 초기 상태 설정
        if (sensorPanel) {
            sensorPanel.style.display = 'none';
            sensorPanel.style.transform = 'none';  // 기존 transform 제거
        }

        // 모두 추가/제거 버튼 이벤트 리스너
        document.getElementById('add-all-sensors')?.addEventListener('click', () => {
            if (!this.sensorManager) return;
            
            this.showConfirmModal(
                '모든 센서 추가',
                '필터링된 모든 센서를 맵에 추가하시겠습니까?\n (※가장 위에 있는 센서의 단위와 같은 단위를 가지는 센서들만 추가됩니다.)',
                () => {
                    this.sensorManager.addAllSensors();
                    this.showMessage('필터링된 모든 센서를 추가했습니다.', 'success');
                }
            );
        });

        document.getElementById('remove-all-sensors')?.addEventListener('click', () => {
            if (!this.sensorManager) return;
            
            this.showConfirmModal(
                '모든 센서 제거',
                '현재 배치된 모든 센서를 제거하시겠습니까?',
                () => {
                    this.sensorManager.removeAllSensors();
                    this.showMessage('모든 센서를 제거했습니다.', 'success');
                }
            );
        });
    }

    toggleSensorPanel() {
        const sensorPanel = document.getElementById('sensor-panel');
        const sensorListTool = document.getElementById('sensor-list-tool');
        
        if (!sensorPanel || !sensorListTool) return;

        const isHidden = sensorPanel.style.display === 'none';
        
        if (isHidden) {
            sensorPanel.style.display = 'block';
            sensorListTool.classList.remove('bg-white', 'text-gray-700');
            sensorListTool.classList.add('bg-blue-500', 'text-white');
        } else {
            sensorPanel.style.display = 'none';
            sensorListTool.classList.remove('bg-blue-500', 'text-white');
            sensorListTool.classList.add('bg-white', 'text-gray-700');
        }
    }

    // 확인 모달 초기화
    initializeConfirmModal() {
        const cancelBtn = document.getElementById('confirm-modal-cancel');
        const confirmBtn = document.getElementById('confirm-modal-confirm');
        const actionBtnsContainer = document.getElementById('confirm-modal-action-btns');
        
        cancelBtn?.addEventListener('click', () => {
            this.hideConfirmModal();
        });

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !this.confirmModal?.classList.contains('hidden')) {
                this.hideConfirmModal();
            }
        });

        // 모달 외부 클릭시 닫기
        this.confirmModal?.addEventListener('click', (e) => {
            if (e.target === this.confirmModal) {
                this.hideConfirmModal();
            }
        });
    }

    // 확인 모달 표시
    showConfirmModal(title, message, onConfirm, options = null) {
        const modalTitle = document.getElementById('confirm-modal-title');
        const modalMessage = document.getElementById('confirm-modal-message');
        const defaultBtns = document.getElementById('confirm-modal-default-btns');
        const actionBtns = document.getElementById('confirm-modal-action-btns');
        
        if (modalTitle) modalTitle.textContent = title;
        if (modalMessage) modalMessage.textContent = message;

        // 기존 액션 버튼들 제거
        if (actionBtns) {
            actionBtns.innerHTML = '';
            actionBtns.classList.add('hidden');
        }
        
        if (defaultBtns) {
            defaultBtns.classList.add('hidden');
        }

        // 옵션이 있는 경우 커스텀 버튼 생성
        if (options && actionBtns) {
            actionBtns.classList.remove('hidden');
            options.forEach(option => {
                const btn = document.createElement('button');
                btn.textContent = option.text;
                btn.className = `px-4 py-2 rounded-lg ${option.className || 'bg-blue-500 text-white hover:bg-blue-600'}`;
                btn.addEventListener('click', () => {
                    if (option.action) option.action();
                    this.hideConfirmModal();
                });
                actionBtns.appendChild(btn);
            });
        } else if (defaultBtns) {
            // 기본 확인/취소 버튼 표시
            defaultBtns.classList.remove('hidden');
            const confirmBtn = document.getElementById('confirm-modal-confirm');
            // 이전 이벤트 리스너 제거
            const newConfirmBtn = confirmBtn?.cloneNode(true);
            confirmBtn?.parentNode?.replaceChild(newConfirmBtn, confirmBtn);
            
            // 새 이벤트 리스너 추가
            newConfirmBtn?.addEventListener('click', () => {
                if (onConfirm) onConfirm();
                this.hideConfirmModal();
            });
        }

        this.confirmModal?.classList.remove('hidden');
        this.confirmModal?.classList.add('flex');
    }

    // 확인 모달 숨기기
    hideConfirmModal() {
        this.confirmModal?.classList.remove('flex');
        this.confirmModal?.classList.add('hidden');
    }

} 