// @ts-ignore
const random = Math.random();
// @ts-ignore
import { DrawingTool } from './drawing_tool.js?cache_buster=${random}';
// @ts-ignore
import { SensorManager } from './sensor_manager.js?cache_buster=${random}'; 

document.addEventListener('DOMContentLoaded', async function() {
    console.log('DOM Content Loaded');
    
    // 전역 변수 선언
    let drawingTool;
    let sensorManager;
    let currentStep = 1;

    // 탭 전환 함수
    function switchTab(tabId) {
        // 모든 탭 컨텐츠 숨기기
        document.querySelectorAll('#dashboard-content, #map-content, #settings-content').forEach(content => {
            content.classList.add('hidden');
        });
        
        // 모든 탭 버튼 비활성화 스타일
        document.querySelectorAll('#dashboard-tab, #map-tab, #settings-tab').forEach(tab => {
            tab.classList.remove('text-gray-900', 'border-b-2', 'border-blue-500');
            tab.classList.add('text-gray-500');
        });
        
        // 선택된 탭 컨텐츠 표시 및 버튼 활성화
        const selectedContent = document.getElementById(`${tabId}-content`);
        const selectedTab = document.getElementById(`${tabId}-tab`);
        if (selectedContent && selectedTab) {
            selectedContent.classList.remove('hidden');
            selectedTab.classList.remove('text-gray-500');
            selectedTab.classList.add('text-gray-900', 'border-b-2', 'border-blue-500');
        }

        // 지도 탭에서는 DrawingTool과 SensorManager 활성화
        if (tabId === 'map') {
            if (drawingTool) drawingTool.enable();
            showStepControls(currentStep);
        } else {
            if (drawingTool) drawingTool.disable();
            if (sensorManager) sensorManager.disable();
        }
    }

    // 단계 표시기 업데이트
    function updateStepIndicators(step) {
        for (let i = 1; i < 2; i++) {
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

    // 단계별 컨트롤 표시/숨김
    function showStepControls(step) {
        console.log('Showing step controls for step:', step);
        console.log('DrawingTool status:', drawingTool ? 'initialized' : 'not initialized');
        
        document.getElementById('step1-controls').classList.toggle('hidden', step !== 1);
        document.getElementById('step2-controls').classList.toggle('hidden', step !== 2);

        // 단계별 기능 활성화/비활성화
        if (step === 1) {
            if (drawingTool) {
                console.log('Enabling drawing tool for step 1');
                drawingTool.enable();
                drawingTool.setTool('line');
                setActiveTool('line');
            } else {
                console.error('DrawingTool is not initialized');
            }
            if (sensorManager) sensorManager.disable();
        } else if (step === 2) {
            if (drawingTool) drawingTool.disable();
            if (sensorManager) sensorManager.enable();
        }
    }

    // 단계 이동 가능 여부 확인 --> TODO: 벽, 센서 있는지 확인하는 함수로 변경
    function canMoveToStep(targetStep) {
        // 1단계는 언제나 이동 가능
        if (targetStep === 1) return true;

        // 2단계로 이동하려면 벽이 그려져 있어야 함
        if (targetStep === 2) {
            return svg.innerHTML.includes('<line');
        }

        // 3단계로 이동하려면 센서가 배치되어 있어야 함
        if (targetStep === 3) {
            return sensorManager.getSensorConfig().some(sensor => sensor.position !== null);
        }

        return false;
    }

    // 다음 단계로 이동
    function goToStep(step) {
        saveWallsAndSensors()
        currentStep = step;
        updateStepIndicators(step);
        showStepControls(step);
    }

    // 벽 및 센서 저장
    async function saveWallsAndSensors() {
        try {
            const wallsData = {
                walls: svg.innerHTML
            };
            const sensorsData = {
                sensors: sensorManager.getSensorConfig()
            };
            await fetch('./api/save-walls-and-sensors', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({wallsData,sensorsData})
            });
        } catch (error) {
            console.error('벽 및 센서 저장 실패:', error);
            alert('벽 저장에 실패했습니다.');
        }
    }

    function setActiveTool(tool) {
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

    // SVG 초기화
    const svg = document.getElementById('svg-overlay');
    if (!svg) {
        console.error('SVG element not found');
        return;
    }
    console.log('SVG element found:', svg);

    // 저장된 설정 로드
    async function loadConfig() {
        try {
            const response = await fetch('./api/load-config');
            if (response.ok) {
                const config = await response.json();
                if (config.walls && config.walls.trim() !== '') {
                    svg.innerHTML = config.walls;    
                }
                if (config.sensors && config.sensors.length > 0 && 
                    config.sensors.some(sensor => sensor.position)) {
                        await sensorManager.loadSensors();
                }
                if(config.parameters)
                    loadInterpolationParameters(config.parameters)

            }
            drawingTool.saveState();
        } catch (error) {
            console.error('설정을 불러오는데 실패했습니다:', error);
        }
    }

    // 플로어플랜 이미지 초기화
    const floorplanImg = /** @type {HTMLImageElement} */ (document.getElementById('floorplan-img'));
    if (!floorplanImg) {
        console.error('Floorplan image element not found');
        return;
    }
    
    // SVG 초기 설정
    const container = document.getElementById('floorplan-container');
    if (!container) {
        console.error('Container element not found');
        return;
    }
    
    // SVG 크기를 1000x1000으로 고정
    const FIXED_SIZE = 1000;
    svg.style.width = '100%';
    svg.style.height = '100%';
    
    svg.setAttribute('width', String(FIXED_SIZE));
    svg.setAttribute('height', String(FIXED_SIZE));
    svg.setAttribute('viewBox', `0 0 ${FIXED_SIZE} ${FIXED_SIZE}`);
    
    console.log('SVG attributes set');
    
    function saveGenConfig(){
        const genConfig = {
            gen_interval: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('generation-interval')).value)
        }
        
        fetch('./api/save-gen-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                gen_config: genConfig
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showMessage('구성을 저장했습니다.', 'success');
            } else {
                showMessage(data.error || '구성 저장에 실패했습니다.', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showMessage('구성 저장 중 오류가 발생했습니다.', 'error');
        });
    }

    // 파라미터 저장 함수
    function saveInterpolationParameters() {
        // 보간 파라미터 수집
        const interpolationParams = {
            gaussian: {
                sigma_factor: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('gaussian-sigma-factor')).value)
            },
            rbf: {
                function: /** @type {HTMLSelectElement} */ (document.getElementById('rbf-function')).value,
                epsilon_factor: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('rbf-epsilon-factor')).value)
            },
            kriging: {
                variogram_model: /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model')).value,
                nlags: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('kriging-nlags')).value),
                weight: /** @type {HTMLInputElement} */ (document.getElementById('kriging-weight')).checked,
                anisotropy_scaling: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-scaling')).value),
                anisotropy_angle: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-angle')).value)
            }
        };

        fetch('./api/save-interpolation-parameters', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                interpolation_params: interpolationParams
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showMessage('파라미터를 저장했습니다.', 'success');
            } else {
                showMessage(data.error || '파라미터 저장에 실패했습니다.', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showMessage('파라미터 저장 중 오류가 발생했습니다.', 'error');
        });
    }

    // 파라미터 로드 함수
    async function loadInterpolationParameters(params) {
        try {
            document.getElementById('gaussian-sigma-factor').value = params?.gaussian?.sigma_factor ?? 8.0;
            document.getElementById('rbf-function').value = params?.rbf?.function ?? 'gaussian';
            document.getElementById('rbf-epsilon-factor').value = params?.rbf?.epsilon_factor ?? 0.5;
            document.getElementById('kriging-variogram-model').value = params?.kriging?.variogram_model ?? 'gaussian';
            document.getElementById('kriging-nlags').value = params?.kriging?.nlags ?? 6;
            document.getElementById('kriging-weight').checked = params?.kriging?.weight ?? true;
            document.getElementById('kriging-anisotropy-scaling').value = params?.kriging?.anisotropy_scaling ?? 1.0;
            document.getElementById('kriging-anisotropy-angle').value = params?.kriging?.anisotropy_angle ?? 0;
        } catch (error) {
            console.error('Error:', error);
            showMessage('파라미터 로드 중 오류가 발생했습니다.', 'error');
        }
    }

    // 메시지 표시 함수
    function showMessage(message, type = 'info') {
        const messageContainer = document.getElementById('message-container');
        if (!messageContainer) return;

        const messageElement = document.createElement('div');
        messageElement.className = `alert alert-${type} fixed top-4 left-1/2 transform -translate-x-1/2 
            px-4 py-2 rounded-lg shadow-lg z-50 ${type === 'error' ? 'bg-red-100 text-red-700' : 
            type === 'success' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`;
        messageElement.textContent = message;
        
        // 기존 메시지 제거
        while (messageContainer.firstChild) {
            messageContainer.removeChild(messageContainer.firstChild);
        }
        
        messageContainer.appendChild(messageElement);
        
        // 3초 후 메시지 자동 제거
        setTimeout(() => {
            messageElement.remove();
        }, 3000);
    }
    
    // 새 이미지 생성 및 추가
    const thermalMapImage = /** @type {HTMLImageElement} */ (document.getElementById('thermal-map-img'));
    const timestamp = new Date().getTime();    
    thermalMapImage.setAttribute('src', `/local/thermal_map.png?t=${timestamp}`);  // 캐시 방지를 위한 타임스탬프 추가

    try {
        // DrawingTool 초기화
        drawingTool = new DrawingTool(svg);
        console.log('DrawingTool initialized');
        
        // SensorManager 초기화
        sensorManager = new SensorManager(svg);
        sensorManager.disable();
        
        // 탭 이벤트 리스너 등록
        document.getElementById('dashboard-tab').addEventListener('click', () => switchTab('dashboard'));
        document.getElementById('map-tab').addEventListener('click', () => switchTab('map'));
        document.getElementById('settings-tab').addEventListener('click', () => switchTab('settings'));

        // 초기 탭 설정
        switchTab('dashboard');
        
        // 이벤트 리스너 등록
        // 단계 버튼 클릭 이벤트
        document.querySelectorAll('.step-button').forEach(button => {
            button.addEventListener('click', function() {
                const targetStep = parseInt(this.dataset.step);
                goToStep(targetStep);
            });
        });

        // 도구 버튼 이벤트 리스너
        document.getElementById('line-tool').addEventListener('click', function() {
            setActiveTool('line');
            drawingTool.setTool('line');
        });
        
        document.getElementById('move-point-tool').addEventListener('click', function() {
            setActiveTool('move-point');
            drawingTool.setTool('move-point');
        });
        
        document.getElementById('eraser-tool').addEventListener('click', function() {
            setActiveTool('eraser');
            drawingTool.setTool('eraser');
        });

        // 초기화 버튼 이벤트 리스너
        document.getElementById('clear-btn').addEventListener('click', function() {
            drawingTool.clear();
        });

        // 선 두께 조절
        const lineWidthInput = /** @type {HTMLInputElement} */ (document.getElementById('line-width'));
        const lineWidthValue = document.getElementById('line-width-value');
        
        if (lineWidthInput && lineWidthValue) {
            lineWidthInput.addEventListener('input', function() {
                const width = parseInt(this.value);
                lineWidthValue.textContent = `${width}px`;
                drawingTool.setLineWidth(width);
            });
        }

        // Floor Plan 업로드 처리
        const floorplanUpload = document.getElementById('floorplan-upload');
        if (floorplanUpload) {
            floorplanUpload.addEventListener('change', function(e) {
                const input = /** @type {HTMLInputElement} */ (e.target);
                const file = input.files?.[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const result = /** @type {string} */ (e.target?.result);
                        floorplanImg.src = result;
                        floorplanImg.onload = function() {
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
                            
                            // SVG 크기는 1000x1000 유지
                            svg.setAttribute('width', String(FIXED_SIZE));
                            svg.setAttribute('height', String(FIXED_SIZE));
                            svg.setAttribute('viewBox', `0 0 ${FIXED_SIZE} ${FIXED_SIZE}`);

                            // 드로잉툴 초기화
                            drawingTool.enable();
                            drawingTool.setTool('line');
                            setActiveTool('line');
                        };
                    };
                    reader.readAsDataURL(file);
                }
            });
        }

        // 초기 데이터 로드
        loadConfig();

        // 파라미터 저장 버튼 이벤트
        const saveInterpolationParametersBtn = document.getElementById('save-interpolation-parameters');
        if (saveInterpolationParametersBtn) {
            saveInterpolationParametersBtn.addEventListener('click', function() {
                saveInterpolationParameters();
            });
        }
        
        // 파라미터 저장 버튼 이벤트
        const saveGenConfigBtn = document.getElementById('save-gen-configs');
        if (saveGenConfigBtn) {
            saveGenConfigBtn.addEventListener('click', function() {
                saveGenConfig();
            });
        }
        
    } catch (error) {
        console.error('Initialization failed:', error);
    }
}); 