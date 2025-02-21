export class UIManager {
    constructor() {
        this.messageContainer = document.getElementById('message-container');
        this.drawingTool = null;
        this.sensorManager = null;
        this.currentTool = null;
        this.confirmModal = document.getElementById('confirm-modal');
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

                            // 드로잉툴 초기화
                            if (this.drawingTool) {
                                this.drawingTool.enable();
                                this.drawingTool.setTool('line');
                                this.setActiveTool('line');
                            }
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
        const toggleButton = document.getElementById('toggle-sensor-panel');
        const toggleIcon = document.getElementById('toggle-sensor-icon');
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

        function togglePanel() {
            isPanelOpen = !isPanelOpen;
            if (isPanelOpen) {
                sensorPanel.style.display = 'block';
                toggleButton.style.right = window.innerWidth < 640 ? 'calc(95vw - 8px)' : '492px';
                toggleIcon.classList.remove('mdi-chevron-left');
                toggleIcon.classList.add('mdi-chevron-right');
            } else {
                sensorPanel.style.display = 'none';
                toggleButton.style.right = '0';
                toggleIcon.classList.remove('mdi-chevron-right');
                toggleIcon.classList.add('mdi-chevron-left');
            }
        }

        toggleButton?.addEventListener('click', togglePanel);

        // 화면 크기 변경 시 토글 버튼 위치 업데이트
        window.addEventListener('resize', () => {
            if (isPanelOpen) {
                toggleButton.style.right = window.innerWidth < 640 ? 'calc(95vw - 8px)' : '492px';
            }
        });
    }

    // 확인 모달 초기화
    initializeConfirmModal() {
        const cancelBtn = document.getElementById('confirm-modal-cancel');
        const confirmBtn = document.getElementById('confirm-modal-confirm');
        
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
    showConfirmModal(title, message, onConfirm) {
        const modalTitle = document.getElementById('confirm-modal-title');
        const modalMessage = document.getElementById('confirm-modal-message');
        const confirmBtn = document.getElementById('confirm-modal-confirm');
        
        if (modalTitle) modalTitle.textContent = title;
        if (modalMessage) modalMessage.textContent = message;
        
        // 이전 이벤트 리스너 제거
        const newConfirmBtn = confirmBtn?.cloneNode(true);
        confirmBtn?.parentNode?.replaceChild(newConfirmBtn, confirmBtn);
        
        // 새 이벤트 리스너 추가
        newConfirmBtn?.addEventListener('click', () => {
            onConfirm();
            this.hideConfirmModal();
        });

        this.confirmModal?.classList.remove('hidden');
        this.confirmModal?.classList.add('flex');
    }

    // 확인 모달 숨기기
    hideConfirmModal() {
        this.confirmModal?.classList.remove('flex');
        this.confirmModal?.classList.add('hidden');
    }
} 