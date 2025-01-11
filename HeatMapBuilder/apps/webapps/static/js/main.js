document.addEventListener('DOMContentLoaded', async function() {
    const svg = document.getElementById('svg-overlay');
    const floorplanImg = /** @type {HTMLImageElement} */ (document.getElementById('floorplan-img'));
    
    // DrawingTool 초기화
    const drawingTool = new DrawingTool(svg);
    
    // SensorManager 초기화
    const sensorManager = new SensorManager(svg);

    // 현재 단계 관리
    let currentStep = 1;

    // 단계 표시기 업데이트
    function updateStepIndicators(step) {
        for (let i = 1; i <= 3; i++) {
            const indicator = document.getElementById(`step${i}-indicator`);
            if (i < step) {
                indicator.classList.remove('bg-gray-300', 'bg-blue-500');
                indicator.classList.add('bg-green-500');
            } else if (i === step) {
                indicator.classList.remove('bg-gray-300', 'bg-green-500');
                indicator.classList.add('bg-blue-500');
            } else {
                indicator.classList.remove('bg-blue-500', 'bg-green-500');
                indicator.classList.add('bg-gray-300');
            }
        }
    }

    // 단계별 컨트롤 표시/숨김
    function showStepControls(step) {
        document.getElementById('step1-controls').classList.toggle('hidden', step !== 1);
        document.getElementById('step2-controls').classList.toggle('hidden', step !== 2);
        document.getElementById('step3-controls').classList.toggle('hidden', step !== 3);

        // 플로어플랜 이미지 표시/숨김
        if (step === 1) {
            floorplanImg.style.display = 'block';
        } else {
            floorplanImg.style.display = 'none';
        }

        // 단계별 기능 활성화/비활성화
        if (step === 1) {
            drawingTool.enable();
            drawingTool.setTool('line');
            setActiveTool('line');
            sensorManager.disable();
            svg.style.cursor = 'crosshair';
        } else if (step === 2) {
            drawingTool.disable();
            sensorManager.enable();
            svg.style.cursor = 'default';
        } else {
            drawingTool.disable();
            sensorManager.disable();
            svg.style.cursor = 'default';
        }
    }

    // 단계 이동 전 확인
    function confirmStepChange(targetStep) {
        if (targetStep < currentStep) {
            return confirm(`${targetStep}단계로 돌아가시겠습니까?\n주의: 현재 작업 중인 내용이 저장되지 않을 수 있습니다.`);
        }
        return true;
    }

    // 단계 이동 가능 여부 확인
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
        if (!canMoveToStep(step)) {
            alert('이전 단계를 먼저 완료해주세요.');
            return;
        }

        if (!confirmStepChange(step)) {
            return;
        }

        currentStep = step;
        updateStepIndicators(step);
        showStepControls(step);
    }

    // 단계 버튼 클릭 이벤트
    document.querySelectorAll('.step-button').forEach(button => {
        button.addEventListener('click', function() {
            const targetStep = parseInt(this.dataset.step);
            goToStep(targetStep);
        });
    });

    // 저장된 설정 로드
    async function loadConfig() {
        try {
            const response = await fetch('/api/load-config');
            if (response.ok) {
                const config = await response.json();
                

                // 벽 정보가 있으면 로드하고 2단계부터 시작
                if (config.walls && config.walls.trim() !== '') {
                    svg.innerHTML = config.walls;
                    
                    // 센서 정보가 있으면 3단계부터 시작
                    if (config.sensors && config.sensors.length > 0 && 
                        config.sensors.some(sensor => sensor.position)) {
                        await sensorManager.loadSensors();
                        goToStep(3);
                    } else {
                        goToStep(2);
                    }
                } else {
                    goToStep(1);
                }
            }
        } catch (error) {
            console.error('설정을 불러오는데 실패했습니다:', error);
            goToStep(1);
        }
    }

    // 도구 버튼 이벤트 리스너
    document.getElementById('line-tool').addEventListener('click', function() {
        setActiveTool('line');
        drawingTool.setTool('line');
    });
    
    document.getElementById('eraser-tool').addEventListener('click', function() {
        setActiveTool('eraser');
        drawingTool.setTool('eraser');
    });

    // 선 두께 조절
    const lineWidthInput = /** @type {HTMLInputElement} */ (document.getElementById('line-width'));
    const lineWidthValue = document.getElementById('line-width-value');
    
    lineWidthInput.addEventListener('input', function() {
        const width = parseInt(this.value);
        lineWidthValue.textContent = `${width}px`;
        drawingTool.setLineWidth(width);
    });

    function setActiveTool(tool) {
        document.querySelectorAll('.tool-btn').forEach(btn => {
            btn.classList.remove('bg-blue-500', 'text-white');
            btn.classList.add('bg-white');
        });
        const activeBtn = document.getElementById(`${tool}-tool`);
        activeBtn.classList.remove('bg-white');
        activeBtn.classList.add('bg-blue-500', 'text-white');
    }

    // Floor Plan 업로드 처리
    document.getElementById('floorplan-upload').addEventListener('change', function(e) {
        const input = /** @type {HTMLInputElement} */ (e.target);
        const file = input.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const result = /** @type {string} */ (e.target?.result);
                floorplanImg.src = result;
                floorplanImg.onload = function() {
                    svg.setAttribute('width', String(floorplanImg.width));
                    svg.setAttribute('height', String(floorplanImg.height));
                };
            };
            reader.readAsDataURL(file);
        }
    });

    // 벽 저장 및 다음 단계로 이동
    document.getElementById('save-walls-btn').addEventListener('click', async function() {
        const data = {
            walls: svg.innerHTML
        };

        try {
            await fetch('/api/save-walls', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            goToStep(2);
        } catch (error) {
            console.error('저장 실패:', error);
            alert('벽 저장에 실패했습니다.');
        }
    });

    // 센서 저장 및 다음 단계로 이동
    document.getElementById('save-sensors-btn').addEventListener('click', async function() {
        const data = {
            sensors: sensorManager.getSensorConfig()
        };

        try {
            await fetch('/api/save-sensors', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            goToStep(3);
        } catch (error) {
            console.error('저장 실패:', error);
            alert('센서 저장에 실패했습니다.');
        }
    });

    // 온도지도 생성 버튼 이벤트
    document.getElementById('generate-map').addEventListener('click', function() {
        generateHeatmap();
    });

    // 초기 데이터 로드
    loadConfig();
    sensorManager.loadSensors();

    function generateHeatmap() {
        fetch('/api/generate-map', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            console.log('서버 응답:', data);  // 응답 데이터 로깅
            
            if (data.status === 'success') {
                // 열지도 이미지 표시
                const thermalMapContainer = document.getElementById('thermal-map-container');
                
                // 기존 내용 제거
                while (thermalMapContainer.firstChild) {
                    thermalMapContainer.removeChild(thermalMapContainer.firstChild);
                }
                
                // 새 이미지 생성 및 추가
                const thermalMapImage = document.createElement('img');
                const timestamp = new Date().getTime();
                thermalMapImage.src = `/media/thermal_map.png?t=${timestamp}`;  // 캐시 방지를 위한 타임스탬프 추가
                thermalMapImage.style.width = '100%';
                thermalMapImage.style.height = 'auto';
                thermalMapImage.style.maxWidth = '800px';
                thermalMapImage.alt = '생성된 온도지도';
                
                thermalMapImage.onload = function() {
                    showMessage('열지도가 생성되었습니다.', 'success');
                };
                thermalMapImage.onerror = function() {
                    console.error('이미지 로드 실패:', thermalMapImage.src);
                    showMessage('열지도 이미지 로드에 실패했습니다.', 'error');
                };
                
                thermalMapContainer.appendChild(thermalMapImage);
            } else {
                showMessage(data.error || '열지도 생성에 실패했습니다.', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showMessage('열지도 생성 중 오류가 발생했습니다.', 'error');
        });
    }

    function showMessage(message, type = 'info') {
        const messageContainer = document.getElementById('message-container');
        const messageElement = document.createElement('div');
        messageElement.className = `alert alert-${type}`;
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
}); 