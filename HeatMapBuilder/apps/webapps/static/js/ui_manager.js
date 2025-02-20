export class UIManager {
    constructor() {
        this.messageContainer = document.getElementById('message-container');
        this.drawingTool = null;
        this.sensorManager = null;
        this.currentTool = null;
        this.initializeTabs();
        this.initializeSettingsTabs();
        this.initializeDrawingTools();
        this.initializeFloorplanUpload();
        this.initializeSensorPanel();
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
            dashboard: document.getElementById('dashboard-content'),
            map: document.getElementById('map-content'),
            settings: document.getElementById('settings-content'),
            debug: document.getElementById('debug-content')
        };

        this.tabButtons = {
            dashboard: document.getElementById('dashboard-tab'),
            map: document.getElementById('map-tab'),
            settings: document.getElementById('settings-tab'),
            debug: document.getElementById('debug-tab')
        };

        Object.keys(this.tabButtons).forEach(tabName => {
            this.tabButtons[tabName].addEventListener('click', () => this.switchTab(tabName));
        });

        // 초기 탭 설정 - 대시보드 탭을 기본으로 표시
        this.switchTab('dashboard');
    }

    switchTab(tabName) {
        Object.values(this.tabs).forEach(tab => tab.classList.add('hidden'));
        Object.values(this.tabButtons).forEach(btn => {
            btn.classList.remove('text-gray-900', 'border-b-2', 'border-blue-500');
            btn.classList.add('text-gray-500');
        });

        this.tabs[tabName].classList.remove('hidden');
        this.tabButtons[tabName].classList.remove('text-gray-500');
        this.tabButtons[tabName].classList.add('text-gray-900', 'border-b-2', 'border-blue-500');

        // map 탭으로 이동할 때 센서 로드
        if (tabName === 'map' && this.sensorManager) {
            this.sensorManager.loadSensors().then(() => {
                console.log('센서 로드 완료');
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

        document.getElementById('move-point-tool')?.addEventListener('click', () => {
            this.setActiveTool('move-point');
        });

        document.getElementById('eraser-tool')?.addEventListener('click', () => {
            this.setActiveTool('eraser');
        });

        // 초기화 버튼 이벤트 리스너
        document.getElementById('clear-btn')?.addEventListener('click', () => {
            if (this.drawingTool) {
                this.drawingTool.clear();
                // 도면 이미지와 흰색 배경 초기화
                const floorplanImg = document.getElementById('floorplan-img');
                const floorplanOverlay = document.getElementById('floorplan-overlay');
                if (floorplanImg instanceof HTMLImageElement) {
                    floorplanImg.src = '';
                }
                floorplanOverlay?.classList.add('hidden');
            }
        });

        // Undo/Redo 버튼 이벤트 리스너
        document.getElementById('undo-btn')?.addEventListener('click', () => {
            if (this.drawingTool) {
                this.drawingTool.undo();
            }
        });

        document.getElementById('redo-btn')?.addEventListener('click', () => {
            if (this.drawingTool) {
                this.drawingTool.redo();
            }
        });

        // 저장 버튼 이벤트 리스너
        document.getElementById('save-walls-sensors')?.addEventListener('click', async () => {
            await this.saveWallsAndSensors();
        });

        // SVG 이동을 위한 이벤트 리스너
        this.initializeSVGPan();
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
            const sensorConfig = this.sensorManager.getSensorConfig();
            const unit = sensorConfig.unit;
            const sensorsData = sensorConfig.sensors;
            
            await fetch('./api/save-walls-and-sensors', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ wallsData, sensorsData, unit })
            });
            this.showMessage('벽과 센서위치를 저장했습니다.', 'success');
        } catch (error) {
            console.error('벽 및 센서 저장 실패:', error);
            this.showMessage('벽 저장에 실패했습니다.', 'error');
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

            // 현재 위치에서 마우스 포인터까지의 거리
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
        }, { passive: false });

        svgContainer.addEventListener('mousedown', (e) => {
            if (this.currentTool !== 'select') return;
            
            // 센서 요소 위에서는 이벤트 무시
            const target = /** @type {Element} */ (e.target);
            if (target.closest('g.sensor')) return;

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
            if (['line', 'move-point', 'eraser'].includes(tool)) {
                this.drawingTool.enable();
                this.drawingTool.setTool(tool);
                if (this.sensorManager) this.sensorManager.disable();
            } else if (tool === 'select') {
                this.drawingTool.disable();
                if (this.sensorManager) {
                    this.sensorManager.enable();
                }
            }
        }

        // 센서 관련 도구 활성화/비활성화
        if (tool === 'sensor') {
            if (this.drawingTool) this.drawingTool.disable();
            if (this.sensorManager) {
                this.sensorManager.enable();
            }
        }

        // 커서 스타일 업데이트
        const svgContainer = document.getElementById('svg-overlay-container');
        if (svgContainer) {
            svgContainer.style.cursor = tool === 'select' ? 'grab' : 'default';
        }
    }

    setTools(drawingTool, sensorManager) {
        this.drawingTool = drawingTool;
        this.sensorManager = sensorManager;
        // 초기 도구 설정
        this.setActiveTool('select');
    }

    initializeFloorplanUpload() {
        const floorplanUpload = document.getElementById('floorplan-upload');
        const floorplanImg = /** @type {HTMLImageElement} */ (document.getElementById('floorplan-img'));
        const floorplanOverlay = document.getElementById('floorplan-overlay');
        const FIXED_SIZE = 1000;

        if (floorplanUpload && floorplanImg) {
            floorplanUpload.addEventListener('change', (e) => {
                const input = /** @type {HTMLInputElement} */ (e.target);
                const file = input.files?.[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        const result = /** @type {string} */ (e.target?.result);
                        floorplanImg.src = result;
                        // 이미지가 로드되면 흰색 배경 표시
                        floorplanOverlay?.classList.remove('hidden');
                        
                        floorplanImg.onload = () => {
                            // 이미지의 큰 쪽을 1000px에 맞추고 비율 유지
                            const aspectRatio = floorplanImg.naturalWidth / floorplanImg.naturalHeight;
                            let width, height;

                            if (aspectRatio > 1) {
                                // 가로가 더 긴 경우
                                width = FIXED_SIZE;
                                height = FIXED_SIZE / aspectRatio;
                            } else {
                                // 세로가 더 긴 경우
                                height = FIXED_SIZE;
                                width = FIXED_SIZE * aspectRatio;
                            }

                            // 이미지 크기 설정
                            floorplanImg.style.width = `${width}px`;
                            floorplanImg.style.height = `${height}px`;

                            // 드로잉툴 초기화
                            if (this.drawingTool) {
                                this.drawingTool.enable();
                                this.drawingTool.setTool('line');
                                this.setActiveTool('line');
                            }
                        };
                    };
                    reader.readAsDataURL(file);
                }
            });
        }
    }

    initializeSensorPanel() {
        const sensorPanel = document.getElementById('sensor-panel');
        const toggleButton = document.getElementById('toggle-sensor-panel');
        const toggleIcon = document.getElementById('toggle-sensor-icon');
        let isPanelOpen = false;

        function togglePanel() {
            isPanelOpen = !isPanelOpen;
            if (isPanelOpen) {
                sensorPanel.style.transform = 'translateX(0)';
                toggleButton.style.right = '19.5rem';
                toggleIcon.classList.remove('mdi-chevron-right');
                toggleIcon.classList.add('mdi-chevron-left');
            } else {
                sensorPanel.style.transform = 'translateX(100%)';
                toggleButton.style.right = '0';
                toggleIcon.classList.remove('mdi-chevron-left');
                toggleIcon.classList.add('mdi-chevron-right');
            }
        }

        toggleButton.addEventListener('click', togglePanel);
    }
} 