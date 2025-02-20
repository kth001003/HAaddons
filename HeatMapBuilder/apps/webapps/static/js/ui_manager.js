export class UIManager {
    constructor() {
        this.messageContainer = document.getElementById('message-container');
        this.currentStep = 1;
        this.drawingTool = null;
        this.sensorManager = null;
        this.initializeTabs();
        this.initializeSettingsTabs();
        this.initializeStepIndicators();
        this.initializeDrawingTools();
        this.initializeFloorplanUpload();
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

    initializeStepIndicators() {
        this.currentStep = 1;
        document.querySelectorAll('.step-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const target = /** @type {HTMLElement} */ (e.target);
                const targetStep = parseInt(target.dataset.step);
                this.goToStep(targetStep);
            });
        });
    }

    updateStepIndicators(step) {
        for (let i = 1; i <= 2; i++) {
            const indicator = document.getElementById(`step${i}-indicator`);
            if (i === step) {
                indicator.classList.remove('bg-gray-300');
                indicator.classList.add('bg-blue-500');
            } else {
                indicator.classList.remove('bg-blue-500');
                indicator.classList.add('bg-gray-300');
            }
        }
    }

    goToStep(step) {
        this.currentStep = step;
        this.updateStepIndicators(step);
        this.showStepControls(step);
    }

    showStepControls(step) {
        console.log('Showing step controls for step:', step);
        console.log('DrawingTool status:', this.drawingTool ? 'initialized' : 'not initialized');

        document.getElementById('step1-controls').classList.toggle('hidden', step !== 1);
        document.getElementById('step2-controls').classList.toggle('hidden', step !== 2);

        // 단계별 기능 활성화/비활성화
        if (step === 1) {
            if (this.drawingTool) {
                console.log('Enabling drawing tool for step 1');
                this.drawingTool.enable();
                this.drawingTool.setTool('line');
                this.setActiveTool('line');
            } else {
                console.error('DrawingTool is not initialized');
            }
            if (this.sensorManager) this.sensorManager.disable();
            this.showSensorPoints(false);
        } else if (step === 2) {
            if (this.drawingTool) this.drawingTool.disable();
            if (this.sensorManager) this.sensorManager.enable();
            this.showSensorPoints(true);
        }
    }

    showSensorPoints(toggle) {
        const points = document.getElementById('svg-overlay').querySelectorAll('g');
        const display = toggle ? 'block' : 'none';
        points.forEach(point => {
            point.style.display = display;
        });
    }

    setActiveTool(tool) {
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.classList.remove('bg-blue-500', 'text-white');
            btn.classList.add('bg-white');
        });
        const activeBtn = document.getElementById(`${tool}-tool`);
        if (activeBtn) {
            activeBtn.classList.remove('bg-white');
            activeBtn.classList.add('bg-blue-500', 'text-white');
        }
    }

    setTools(drawingTool, sensorManager) {
        this.drawingTool = drawingTool;
        this.sensorManager = sensorManager;
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
        document.getElementById('line-tool')?.addEventListener('click', () => {
            this.setActiveTool('line');
            if (this.drawingTool) {
                this.drawingTool.setTool('line');
            }
        });

        document.getElementById('move-point-tool')?.addEventListener('click', () => {
            this.setActiveTool('move-point');
            if (this.drawingTool) {
                this.drawingTool.setTool('move-point');
            }
        });

        document.getElementById('eraser-tool')?.addEventListener('click', () => {
            this.setActiveTool('eraser');
            if (this.drawingTool) {
                this.drawingTool.setTool('eraser');
            }
        });

        // 초기화 버튼 이벤트 리스너
        document.getElementById('clear-btn')?.addEventListener('click', () => {
            if (this.drawingTool) {
                this.drawingTool.clear();
            }
        });
    }

    initializeFloorplanUpload() {
        const floorplanUpload = document.getElementById('floorplan-upload');
        const floorplanImg = /** @type {HTMLImageElement} */ (document.getElementById('floorplan-img'));
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
} 