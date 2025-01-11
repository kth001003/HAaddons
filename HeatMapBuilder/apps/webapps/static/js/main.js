document.addEventListener('DOMContentLoaded', function() {
    let isDrawing = false;
    let currentPath = [];
    const svg = document.getElementById('svg-overlay');
    const floorplanImg = document.getElementById('floorplan-img');
    let sensors = [];

    // Floor Plan 업로드 처리
    document.getElementById('floorplan-upload').addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                floorplanImg.src = e.target.result;
                floorplanImg.onload = function() {
                    svg.setAttribute('width', this.width);
                    svg.setAttribute('height', this.height);
                };
            };
            reader.readAsDataURL(file);
        }
    });

    // SVG 벽 그리기 기능
    svg.addEventListener('mousedown', startDrawing);
    svg.addEventListener('mousemove', draw);
    svg.addEventListener('mouseup', endDrawing);

    function startDrawing(e) {
        isDrawing = true;
        const point = getMousePosition(e);
        currentPath = [point];
        drawPath();
    }

    function draw(e) {
        if (!isDrawing) return;
        const point = getMousePosition(e);
        currentPath.push(point);
        drawPath();
    }

    function endDrawing() {
        isDrawing = false;
    }

    function getMousePosition(e) {
        const rect = svg.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }

    function drawPath() {
        if (currentPath.length < 2) return;
        
        const pathData = currentPath.map((point, i) => 
            (i === 0 ? 'M' : 'L') + point.x + ' ' + point.y
        ).join(' ');

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('stroke', 'black');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('fill', 'none');
        
        // 기존 path 제거 후 새로운 path 추가
        const oldPath = svg.querySelector('path');
        if (oldPath) svg.removeChild(oldPath);
        svg.appendChild(path);
    }

    // HA API를 통해 온도 센서 정보 가져오기
    async function loadSensors() {
        try {
            const response = await fetch('/api/states');
            const states = await response.json();
            sensors = states.filter(state => 
                state.attributes.unit_of_measurement === '°C' &&
                state.attributes.device_class === 'temperature'
            );
            updateSensorList();
        } catch (error) {
            console.error('센서 정보를 불러오는데 실패했습니다:', error);
        }
    }

    function updateSensorList() {
        const container = document.getElementById('sensor-container');
        container.innerHTML = sensors.map(sensor => `
            <div class="sensor-item" draggable="true" data-entity-id="${sensor.entity_id}">
                ${sensor.attributes.friendly_name || sensor.entity_id}
                (${sensor.state}°C)
            </div>
        `).join('');

        // 드래그 앤 드롭 이벤트 설정
        container.querySelectorAll('.sensor-item').forEach(item => {
            item.addEventListener('dragstart', handleDragStart);
        });
    }

    // 저장 버튼 이벤트
    document.getElementById('save-btn').addEventListener('click', async function() {
        const data = {
            floorplan: floorplanImg.src,
            walls: svg.innerHTML,
            sensors: sensors.map(sensor => ({
                entity_id: sensor.entity_id,
                position: sensor.position || null
            }))
        };

        try {
            await fetch('/api/save-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            alert('설정이 저장되었습니다.');
        } catch (error) {
            console.error('저장 실패:', error);
            alert('설정 저장에 실패했습니다.');
        }
    });

    // 온도지도 생성 버튼 이벤트
    document.getElementById('generate-map').addEventListener('click', async function() {
        try {
            const response = await fetch('/api/generate-map', {
                method: 'POST'
            });
            if (response.ok) {
                alert('온도지도가 생성되었습니다.');
            }
        } catch (error) {
            console.error('온도지도 생성 실패:', error);
            alert('온도지도 생성에 실패했습니다.');
        }
    });

    // 초기 센서 정보 로드
    loadSensors();
}); 