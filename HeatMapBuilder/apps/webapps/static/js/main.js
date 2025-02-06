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
            showSensorPoints(false)
        } else if (step === 2) {
            if (drawingTool) drawingTool.disable();
            if (sensorManager) sensorManager.enable();
            showSensorPoints(true)
        }
    }
    // SVG 내의 포인트 표시 토글 함수
    function showSensorPoints(toggle) {
        const points = svg.querySelectorAll('g');
        const display = toggle ? 'block' : 'none';
        points.forEach(point => {
            point.style.display = display;
        });
    }

    // 다음 단계로 이동
    function goToStep(step) {
        currentStep = step;
        updateStepIndicators(step);
        showStepControls(step);
    }

    // 벽 및 센서 저장
    async function saveWallsAndSensors() {
        try {
            // SVG에서 line 및 path 요소만 선택
            const wallsElements = svg.querySelectorAll('line, path');
            
            // 선택된 요소들의 HTML 문자열 생성
            let wallsHTML = '';
            wallsElements.forEach(element => {
                wallsHTML += element.outerHTML;
            });
            const wallsData = {
                walls: wallsHTML
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
            showMessage('벽과 센서위치를 저장했습니다.', 'success')
        } catch (error) {
            console.error('벽 및 센서 저장 실패:', error);
            showMessage('벽 저장에 실패했습니다.', 'error')
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

    async function loadConfig() {
        try {
            const response = await fetch('./api/load-config');
            if (response.ok) {
                const config = await response.json();
                console.log("서버에서 받은 config:", config); // 서버 응답 확인
                if (config.walls) {
                    svg.innerHTML = config.walls
                }
                if (config.sensors) {
                    config.sensors.forEach(savedSensor => {
                        const sensor = sensorManager.sensors.find(s => s.entity_id === savedSensor.entity_id);
                        if (sensor && savedSensor.position) {
                             console.log("적용 전 센서:", sensor); // 적용 전 센서 객체 확인
                            sensor.position = savedSensor.position;
                             sensor.calibration = savedSensor.calibration || 0;
                            console.log("적용 후 센서:", sensor); // 적용 후 센서 객체 확인
                            sensorManager.updateSensorMarker(sensor, savedSensor.position);
                        }
                    });
                }
                if(config.parameters)
                    loadInterpolationParameters(config.parameters)
                if(config.gen_config) {
                    /** @type {HTMLInputElement} */ (document.getElementById('generation-interval')).value = config.gen_config.gen_interval ?? 5;
                    /** @type {HTMLInputElement} */ (document.getElementById('format')).value = config.gen_config.format ?? 'png';
                    /** @type {HTMLInputElement} */ (document.getElementById('file-name')).value = config.gen_config.file_name ?? 'thermal_map';
                  
                    // 시각화 설정 로드
                    const visualization = config.gen_config.visualization || {};
                    /** @type {HTMLSelectElement} */ (document.getElementById('empty-area-style')).value = visualization.empty_area ?? 'white';
                    /** @type {HTMLInputElement} */ (document.getElementById('area-border-width')).value = visualization.area_border_width ?? 2;
                    /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value = visualization.area_border_color ?? '#000000';
                    /** @type {HTMLInputElement} */ (document.getElementById('plot-border-width')).value = visualization.plot_border_width ?? 0;
                    /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value = visualization.plot_border_color ?? '#000000';
                    /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option')).value = visualization.sensor_display ?? 'position_name_temp';
                    
                    // 컬러바 설정 로드
                    const colorbar = config.gen_config.colorbar || {};
                    /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap')).value = colorbar.cmap ?? 'RdYlBu_r';
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-colorbar')).checked = colorbar.show_colorbar ?? true;
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-width')).value = colorbar.width ?? 5;
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-height')).value = colorbar.height ?? 100;
                    /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-location')).value = colorbar.location ?? 'right';
                    /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-borderpad')).value = colorbar.borderpad ?? '0';
                    /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-orientation')).value = colorbar.orientation ?? 'vertical';
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-label')).checked = colorbar.show_label ?? true;
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label')).value = colorbar.label ?? '온도 (°C)';
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-font-size')).value = colorbar.font_size ?? 12;
                    /** @type {HTMLInputElement} */ (document.getElementById('colorbar-tick-size')).value = colorbar.tick_size ?? 10;
                    /** @type {HTMLInputElement} */ (document.getElementById('min-temp')).value = colorbar.min_temp ?? 15;
                    /** @type {HTMLInputElement} */ (document.getElementById('max-temp')).value = colorbar.max_temp ?? 35;
                    /** @type {HTMLInputElement} */ (document.getElementById('temp-steps')).value = colorbar.temp_steps ?? 100;
                    
                    // 컬러맵 프리뷰 업데이트
                    updateColormapPreview();
              }
                await sensorManager.loadSensors();
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
    svg.setAttribute('viewBox', `0 0 ${FIXED_SIZE} ${FIXED_SIZE}`);
    
    console.log('SVG attributes set');
    
    function saveGenConfig(){
        const genConfig = {
            gen_interval: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('generation-interval')).value),
            format: /** @type {HTMLInputElement} */ (document.getElementById('format')).value,
            file_name: /** @type {HTMLInputElement} */ (document.getElementById('file-name')).value,
            visualization: {
                empty_area: /** @type {HTMLSelectElement} */ (document.getElementById('empty-area-style')).value,
                area_border_width: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('area-border-width')).value),
                area_border_color: /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value,
                plot_border_width: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('plot-border-width')).value),
                plot_border_color: /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value,
                sensor_display: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option')).value
            },
            colorbar: {
                cmap: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap')).value,
                show_colorbar: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-colorbar')).checked,
                width: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('colorbar-width')).value),
                height: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('colorbar-height')).value),
                location: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-location')).value,
                borderpad: parseFloat(/** @type {HTMLSelectElement} */ (document.getElementById('colorbar-borderpad')).value),
                orientation: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-orientation')).value,
                show_label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-label')).checked,
                label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label')).value,
                font_size: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('colorbar-font-size')).value),
                tick_size: parseInt(/** @type {HTMLInputElement} */ (document.getElementById('colorbar-tick-size')).value),
                min_temp: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('min-temp')).value),
                max_temp: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('max-temp')).value),
                temp_steps: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('temp-steps')).value)
            }
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

        // 모델별 파라미터 설정
        const model = interpolationParams.kriging.variogram_model;
        if (model === 'linear') {
            interpolationParams.kriging.variogram_parameters = {
                slope: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-slope')).value),
                nugget: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-linear-nugget')).value)
            };
        } else if (model === 'power') {
            interpolationParams.kriging.variogram_parameters = {
                scale: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-scale')).value),
                exponent: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-exponent')).value),
                nugget: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-power-nugget')).value)
            };
        } else {
            // gaussian, spherical, exponential, hole-effect 모델
            interpolationParams.kriging.variogram_parameters = {
                nugget: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-nugget')).value),
                sill: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-sill')).value),
                range: parseFloat(/** @type {HTMLInputElement} */ (document.getElementById('kriging-range')).value)
            };
        }

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
            /** @type {HTMLInputElement} */ (document.getElementById('gaussian-sigma-factor')).value = params?.gaussian?.sigma_factor ?? 8.0;
            /** @type {HTMLSelectElement} */ (document.getElementById('rbf-function')).value = params?.rbf?.function ?? 'gaussian';
            /** @type {HTMLInputElement} */ (document.getElementById('rbf-epsilon-factor')).value = params?.rbf?.epsilon_factor ?? 0.5;
            
            const model = params?.kriging?.variogram_model ?? 'gaussian';
            /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model')).value = model;
            
            // 모델별 파라미터 로드
            if (model === 'linear') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-slope')).value = params?.kriging?.variogram_parameters?.slope ?? 1;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-linear-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 0;
            } else if (model === 'power') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-scale')).value = params?.kriging?.variogram_parameters?.scale ?? 1;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-exponent')).value = params?.kriging?.variogram_parameters?.exponent ?? 1.5;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-power-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 0;
            } else {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 5;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-sill')).value = params?.kriging?.variogram_parameters?.sill ?? 20;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-range')).value = params?.kriging?.variogram_parameters?.range ?? 10;
            }
            
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-nlags')).value = params?.kriging?.nlags ?? 6;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-weight')).checked = params?.kriging?.weight ?? true;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-scaling')).value = params?.kriging?.anisotropy_scaling ?? 1.0;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-angle')).value = params?.kriging?.anisotropy_angle ?? 0;

            // 모델에 따른 파라미터 UI 표시/숨김 처리
            updateVariogramParametersVisibility(model);
        } catch (error) {
            console.error('Error:', error);
            showMessage('파라미터 로드 중 오류가 발생했습니다.', 'error');
        }
    }

    // 베리오그램 파라미터 UI 표시/숨김 처리 함수
    function updateVariogramParametersVisibility(model) {
        const standardParams = document.getElementById('standard-params');
        const linearParams = document.getElementById('linear-params');
        const powerParams = document.getElementById('power-params');
        
        standardParams.classList.add('hidden');
        linearParams.classList.add('hidden');
        powerParams.classList.add('hidden');
        
        if (model === 'linear') {
            linearParams.classList.remove('hidden');
        } else if (model === 'power') {
            powerParams.classList.remove('hidden');
        } else {
            standardParams.classList.remove('hidden');
        }
    }

    // 베리오그램 모델 변경 이벤트 핸들러
    const krigingVariogramModel = /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model'));
    if (krigingVariogramModel) {
        krigingVariogramModel.addEventListener('change', function() {
            const model = this.value;
            
            // 모델에 따른 기본값 설정
            const defaultParams = {
                'gaussian': { nugget: 5, sill: 20, range: 10 },
                'spherical': { nugget: 0, sill: 10, range: 20 },
                'exponential': { nugget: 0, sill: 15, range: 15 },
                'hole-effect': { nugget: 0, sill: 10, range: 15 },
                'linear': { slope: 1, nugget: 0 },
                'power': { scale: 1, exponent: 1.5, nugget: 0 }
            };
            
            // UI 업데이트
            updateVariogramParametersVisibility(model);
            
            // 기본값 설정
            const params = defaultParams[model];
            if (params) {
                if (model === 'linear') {
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-slope')).value = params.slope;
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-linear-nugget')).value = params.nugget;
                } else if (model === 'power') {
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-scale')).value = params.scale;
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-exponent')).value = params.exponent;
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-power-nugget')).value = params.nugget;
                } else {
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-nugget')).value = params.nugget;
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-sill')).value = params.sill;
                    /** @type {HTMLInputElement} */ (document.getElementById('kriging-range')).value = params.range;
                }
            }
        });
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
    const mapGenerationTime = document.getElementById('map-generation-time');
    const mapGenerationDuration = document.getElementById('map-generation-duration');

    async function refreshThermalMap() {
        showMessage('온도지도 생성 중..')
        try {
            const response = await fetch('./api/generate-map');
            const data = await response.json();
            
            if (data.status === 'success') {
                const timestamp = new Date().getTime();
                thermalMapImage.setAttribute('src', `${data.image_url}?t=${timestamp}`);
                if (mapGenerationTime) {
                    mapGenerationTime.textContent = data.time;
                }
                if (mapGenerationDuration){
                    mapGenerationDuration.textContent = data.duration;
                }
                showMessage('온도지도를 새로 생성했습니다.', 'success');
            } else {
                showMessage(data.error || '온도지도 생성에 실패했습니다.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            showMessage('온도지도 생성 중 오류가 발생했습니다.', 'error');
        }
    }

    // 맵 생성 시간 확인 및 자동 새로고침 함수
    async function checkAndRefreshMap() {
        try {
            const response = await fetch('./api/check-map-time');
            const data = await response.json();
            
            if (data.status === 'success' && data.generation_time) {
                const serverTime = new Date(data.generation_time).getTime();
                const currentDisplayTime = mapGenerationTime ? new Date(mapGenerationTime.textContent).getTime() : 0;
                
                if (serverTime > currentDisplayTime) {
                    const timestamp = new Date().getTime();
                    thermalMapImage.setAttribute('src', `${data.image_url}?t=${timestamp}`);
                    if (mapGenerationTime) {
                        mapGenerationTime.textContent = data.time;  // 시간 값 할당
                    }
                    if (mapGenerationDuration) {
                        mapGenerationDuration.textContent = data.duration; // 지속 시간 값 할당
                    }
                }
            }
        } catch (error) {
            console.error('맵 시간 확인 중 오류:', error);
        }
    }

    // 새로고침 버튼 이벤트 리스너
    document.getElementById('generate-now').addEventListener('click', refreshThermalMap);

    // 탭 이벤트 리스너 등록
    document.getElementById('dashboard-tab').addEventListener('click', () => switchTab('dashboard'));
    document.getElementById('map-tab').addEventListener('click', () => switchTab('map'));
    document.getElementById('settings-tab').addEventListener('click', () => switchTab('settings'));

    // 초기 탭 설정
    switchTab('dashboard');

    // 단계 버튼 클릭 이벤트
    document.querySelectorAll('.step-button').forEach(button => {
        button.addEventListener('click', function() {
            const targetStep = parseInt(this.dataset.step);
            goToStep(targetStep);
        });
    });

    // 저장 버튼 이벤트 리스너
    document.getElementById('save-walls-sensors').addEventListener('click', function() {
        saveWallsAndSensors();
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

    // 컬러맵 프리뷰 생성 함수
    function updateColormapPreview() {
        const cmap = /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap')).value;
        const preview = document.getElementById('colormap-preview');
        
        // 컬러맵별 그라데이션 색상 정의
        const gradients = {
            'RdYlBu_r': 'linear-gradient(to right, #313695, #74add1, #fed976, #feb24c, #f46d43, #a50026)',
            'RdBu_r': 'linear-gradient(to right, #2166ac, #67a9cf, #f7f7f7, #ef8a62, #b2182b)',
            'coolwarm': 'linear-gradient(to right, #3a4cc0, #b4c4e7, #f7f7f7, #eda1a1, #cd1719)',
            'bwr': 'linear-gradient(to right, #0000ff, #ffffff, #ff0000)',
            'seismic': 'linear-gradient(to right, #00004c, #0000ff, #ffffff, #ff0000, #4c0000)',
            'PiYG': 'linear-gradient(to right, #8e0152, #de77ae, #f7f7f7, #7fbc41, #276419)',
            'PRGn': 'linear-gradient(to right, #40004b, #9970ab, #f7f7f7, #5aae61, #00441b)',
            'BrBG': 'linear-gradient(to right, #543005, #bf812d, #f7f7f7, #35978f, #003c30)',
            'PuOr': 'linear-gradient(to right, #7f3b08, #f1a340, #f7f7f7, #998ec3, #40004b)',
            'Spectral': 'linear-gradient(to right, #9e0142, #f46d43, #fee08b, #66c2a5, #5e4fa2)',
            'Spectral_r': 'linear-gradient(to right, #5e4fa2, #66c2a5, #fee08b, #f46d43, #9e0142)'
        };
        
        if (preview) {
            preview.style.background = gradients[cmap] || gradients['RdYlBu_r'];
        }
    }

    // 컬러맵 변경 이벤트 리스너
    const colormapSelect = document.getElementById('colorbar-cmap');
    if (colormapSelect) {
        colormapSelect.addEventListener('change', updateColormapPreview);
        // 초기 프리뷰 생성
        updateColormapPreview();
    }

    // 색상 프리셋 선택 이벤트 리스너
    document.getElementById('area-border-color-preset').addEventListener('change', function() {
        const color = /** @type {HTMLSelectElement} */ (this).value;
        /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value = color;
    });

    document.getElementById('plot-border-color-preset').addEventListener('change', function() {
        const color = /** @type {HTMLSelectElement} */ (this).value;
        /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value = color;
    });

    // 색상 선택 이벤트 리스너
    document.getElementById('area-border-color').addEventListener('input', function() {
        const color = /** @type {HTMLInputElement} */ (this).value;
        /** @type {HTMLSelectElement} */ (document.getElementById('area-border-color-preset')).value = color;
    });

    document.getElementById('plot-border-color').addEventListener('input', function() {
        const color = /** @type {HTMLInputElement} */ (this).value;
        /** @type {HTMLSelectElement} */ (document.getElementById('plot-border-color-preset')).value = color;
    });
    
    try {
        // DrawingTool 초기화
        drawingTool = new DrawingTool(svg);
        console.log('DrawingTool initialized');
        
        // SensorManager 초기화
        sensorManager = new SensorManager(svg);
        sensorManager.disable();

        // 초기 데이터 로드
        loadConfig();
        
        // 센서는 1분마다 업데이트
        setInterval(async function() {
            await sensorManager.refreshSensors();
        }, 60000);
        // 맵 자동 새로고침 - 10초마다 확인
        setInterval(checkAndRefreshMap, 10000);
        
    } catch (error) {
        console.error('Initialization failed:', error);
    }
}); 