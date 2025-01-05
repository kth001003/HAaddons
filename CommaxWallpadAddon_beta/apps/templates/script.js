// 전역 변수 선언
let lastPackets = new Set();
let packetSuggestions = null;
const HISTORY_KEY = 'packet_analysis_history';
const MAX_HISTORY = 20;
let historyIndex = -1;  // 히스토리 인덱스 추가
let currentInput = '';   // 현재 입력값 저장용 변수 추가

// 실시간 패킷 로그 관련 함수들
let liveLastPackets = new Set();
let isPaused = false;  // 일시정지 상태를 저장하는 변수 추가

// 폴링 관련 변수
let isPolling = false;
let pollingInterval;

let packetLogInterval;

const PACKET_TYPES = {
    'command': '명령 패킷',
    'state': '상태 패킷',
    'state_request': '상태 요청 패킷',
    'ack': '응답 패킷'
};

// ===============================
// 페이지 전환 함수
// ===============================
function showPage(pageId) {
    // 모든 페이지 숨기기
    document.querySelectorAll('.page').forEach(page => {
        page.classList.add('hidden');
    });
    
    // 선택된 페이지 보이기
    document.getElementById(pageId).classList.remove('hidden');
    
    // 네비게이션 메뉴 활성화 상태 변경
    document.querySelectorAll('nav a').forEach(link => {
        if (link.getAttribute('onclick').includes(pageId)) {
            link.classList.add('border-indigo-500', 'text-gray-900');
            link.classList.remove('border-transparent', 'text-gray-500');
        } else {
            link.classList.remove('border-indigo-500', 'text-gray-900');
            link.classList.add('border-transparent', 'text-gray-500');
        }
    });

    // 실시간 패킷 페이지인 경우 폴링 시작
    if (pageId === 'live_packets') {
        startPolling();
    } else {
        stopPolling();
    }
    if (pageId === 'playground') {
        startPacketLogUpdate();
    } else {
        stopPacketLogUpdate();
    }
}

// ===============================
// 기기 목록 관련 함수
// ===============================
function refreshDevices() {
    if (!confirm('기기를 다시 검색하기 위해 애드온을 재시작합니다. 재시작 후 30초정도 후에 기기가 검색됩니다. 계속하시겠습니까?')) {
        return;
    }

    fetch('./api/find_devices', {
        method: 'POST'
    });
}

function updateDeviceList() {
    fetch('./api/devices')
        .then(response => response.json())
        .then(data => {
            const deviceListDiv = document.getElementById('deviceList');
            if (!deviceListDiv) return;

            let html = '';
            for (const [deviceName, info] of Object.entries(data)) {
                html += `
                    <div class="mb-4 p-4 bg-gray-50 rounded-lg">
                        <div class="flex justify-between items-center">
                            <h3 class="text-lg font-medium">${deviceName}</h3>
                            <span class="text-sm text-gray-500">타입: ${info.type}</span>
                        </div>
                        <div class="mt-2 text-sm text-gray-600">
                            개수: ${info.count}개
                        </div>
                    </div>
                `;
            }
            deviceListDiv.innerHTML = html || '<p class="text-gray-500">연결된 기기가 없습니다.</p>';
        })
        .catch(error => console.error('기기 목록 업데이트 실패:', error));
}

// ===============================
// 패킷 분석 관련 함수
// ===============================
function detectPacketType(header) {
    if (!packetSuggestions || !packetSuggestions.headers) {
        return 'command';  // 기본값
    }
    
    const types = {
        'state': 'state',
        'state_request': 'state_request',
        'ack': 'ack'
    };
    
    for (const [type, value] of Object.entries(types)) {
        if (packetSuggestions.headers[type].some(h => h.header === header)) {
            return value;
        }
    }
    
    return 'command';
}

// 패킷 로그 표시 관련 함수들 통합
function updatePacketDisplay(isLive = false) {
    const elements = document.getElementsByClassName(isLive ? 'live-unknown-packet' : 'unknown-packet');
    const displayStyle = document.getElementById(isLive ? 'hideUnknownLive' : 'hideUnknown').checked ? 'none' : '';
    
    Array.from(elements).forEach(el => el.style.display = displayStyle);
}

// 기존의 updatePacketLogDisplay와 updateLivePacketLogDisplay를 대체
const updatePacketLogDisplay = () => updatePacketDisplay(false);
const updateLivePacketLogDisplay = () => updatePacketDisplay(true);

// 패킷 처리 유틸리티 함수들
const utils = {
    formatPacket: packet => packet.match(/.{2}/g).join(' '),
    isValidPacket: packet => /^[0-9A-F]{14}$|^[0-9A-F]{16}$/.test(packet),
    getTimestamp: () => new Date().toLocaleTimeString('ko-KR', { hour12: false }),
    cleanPacket: input => input.replace(/[\s-]+/g, '').trim().toUpperCase()
};

// 패킷 히스토리 관리 간소화
function handlePacketHistory() {
    const packetInput = document.getElementById('packetInput');
    const historySelect = document.getElementById('packetHistory');
    
    return {
        save: (packet) => {
            const history = JSON.parse(localStorage.getItem('packetHistory') || '[]');
            if (!history.includes(packet)) {
                history.unshift(packet);
                if (history.length > 10) history.pop();
                localStorage.setItem('packetHistory', JSON.stringify(history));
                this.load();
            }
        },
        load: () => {
            const history = JSON.parse(localStorage.getItem('packetHistory') || '[]');
            historySelect.innerHTML = '<option value="">패킷 기록...</option>' +
                history.map(p => `<option value="${p}">${utils.formatPacket(p)}</option>`).join('');
        },
        select: () => {
            if (historySelect.value) {
                packetInput.value = utils.formatPacket(historySelect.value);
                analyzePacket();
            }
        }
    };
}

// 패킷 분석 결과 표시 간소화
function displayPacketAnalysis(packet, results) {
    const resultDiv = document.getElementById('packetResult');
    if (!results.length) {
        resultDiv.innerHTML = `<div class="text-red-500">매칭되는 패킷 구조를 찾을 수 없습니다.</div>`;
        return;
    }

    resultDiv.innerHTML = results.map(result => `
        <div class="bg-white p-4 rounded-lg shadow mb-4">
            <div class="flex justify-between items-center mb-2">
                <h3 class="text-lg font-medium">${result.device}</h3>
                <span class="text-sm text-gray-500">${result.packet_type}</span>
            </div>
            ${Object.entries(result.byte_meanings || {}).map(([byte, meaning]) => `
                <div class="mb-2">
                    <span class="font-medium">Byte ${byte}:</span>
                    <span class="ml-2">${meaning}</span>
                </div>
            `).join('')}
            ${result.description ? `
                <div class="mt-4 text-sm text-gray-600">
                    <span class="font-medium">설명:</span>
                    <span class="ml-2">${result.description}</span>
                </div>
            ` : ''}
        </div>
    `).join('');
}

// 패킷 분석 함수 간소화
function analyzePacket(paddedPacket) {
    const packet = paddedPacket || utils.cleanPacket(document.getElementById('packetInput').value);
    
    if (!packet) {
        showAvailableHeaders();
        return;
    }
    
    if (!utils.isValidPacket(packet)) {
        if (packet.length >= 2 && /^[0-9A-F]+$/.test(packet)) {
            analyzePacket(packet.padEnd(14, '0'));
        }
        return;
    }
    
    if (!paddedPacket) {
        handlePacketHistory().save(packet);
    }

    fetch(`./api/analyze_packet/${packet}`)
        .then(response => response.json())
        .then(data => displayPacketAnalysis(packet, data.results))
        .catch(error => console.error('패킷 분석 실패:', error));
}

function analyzeExpectedState(packet) {
    document.getElementById('packetInput').value = packet;
    analyzePacket();
}

function sendPacket() {
    const packetInput = document.getElementById('packetInput');
    const packet = packetInput.value.replace(/[\s-]+/g, '').trim();

    fetch('./api/send_packet', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ packet: packet })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('패킷을 전송했습니다.');
        } else {
            alert('패킷 전송에 실패했습니다.');
        }
    });
}

// 패킷 로그 관련 함수들
function createPacketLogEntry(packet, type) {
    const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
    const deviceClass = deviceInfo.device === 'Unknown' ? 'unknown-packet' : '';
    const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
    const timestamp = new Date().toLocaleTimeString('ko-KR', { hour12: false });
    
    return `
        <div class="packet-log-entry ${deviceClass} p-2 border-b border-gray-200 hover:bg-gray-50 cursor-pointer" onclick="handlePacketClick('${packet.packet}')">
            <span class="packet-timestamp text-gray-500 text-sm">${timestamp}</span>
            <span class="inline-block min-w-[50px] mr-2 text-sm font-semibold ${type === 'send' ? 'text-green-600' : 'text-blue-600'}">[${type.toUpperCase()}]</span>
            <span class="font-mono">${formattedPacket}</span>
            <span class="inline-block min-w-[120px] ml-2 text-sm text-gray-600">[${deviceInfo.device} - ${deviceInfo.packet_type}]</span>
        </div>`;
}

function updatePacketLog(isLive = false) {
    if (isLive && isPaused) return;

    fetch('./api/packet_logs')
        .then(response => response.json())
        .then(data => {
            const logDiv = document.getElementById(isLive ? 'livePacketLog' : 'packetLog');
            const packetSet = isLive ? liveLastPackets : lastPackets;
            let newContent = '';

            // 송신 및 수신 패킷 처리
            ['send', 'recv'].forEach(type => {
                data[type].forEach(packet => {
                    const packetKey = `${type}:${packet.packet}`;
                    
                    if (isLive) {
                        // 실시간 모드: 새로운 패킷이면 추가
                        if (!packetSet.has(packetKey)) {
                            newContent = createPacketLogEntry(packet, type) + newContent;
                            packetSet.add(packetKey);
                        }
                    } else {
                        // 일반 모드: Set에 없는 패킷만 추가하고 표시
                        if (!packetSet.has(packetKey)) {
                            newContent = createPacketLogEntry(packet, type) + newContent;
                            packetSet.add(packetKey);
                        }
                    }
                });
            });

            if (newContent) {
                if (isLive) {
                    logDiv.innerHTML = newContent + logDiv.innerHTML;
                    updateLivePacketLogDisplay();
                    // 로그 길이 제한
                    const maxEntries = 2000;
                    const entries = logDiv.getElementsByClassName('packet-log-entry');
                    if (entries.length > maxEntries) {
                        for (let i = maxEntries; i < entries.length; i++) {
                            entries[i].remove();
                        }
                    }
                } else {
                    logDiv.innerHTML = newContent;
                    updatePacketLogDisplay();
                }
            }
        })
        .catch(error => console.error('패킷 로그 업데이트 실패:', error));
}

function handlePacketClick(packet) {
    document.getElementById('packetInput').value = packet;
    analyzePacket();
}

function clearPacketLog() {
    const logDiv = document.getElementById('packetLog');
    logDiv.innerHTML = '';
    lastPackets.clear();
}

// 패킷 히스토리 관련 함수들
function loadPacketHistory() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    } catch {
        return [];
    }
}

function savePacketHistory(packet) {
    if (!packet) return;
    
    let history = loadPacketHistory();
    
    // 중복 제거
    history = history.filter(p => p !== packet);
    
    // 새 패킷을 앞에 추가
    history.unshift(packet);
    
    // 최대 개수 유지
    if (history.length > MAX_HISTORY) {
        history = history.slice(0, MAX_HISTORY);
    }
    
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    historyIndex = -1;  // 히스토리 인덱스 초기화
}

function showAvailableHeaders() {
    if (!packetSuggestions) return;
    const resultDiv = document.getElementById('packetResult');
    let html = '<h3 class="text-lg font-bold mb-2">사용 가능한 헤더:</h3>';
    html += '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">';
    
    // 명령 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600">명령 패킷</h4>';
    packetSuggestions.headers.command.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 px-1">${header.header}</span> - ${header.device}</div>`;
    });
    html += '</div>';
    
    // 상태 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600">상태 패킷</h4>';
    packetSuggestions.headers.state.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 px-1">${header.header}</span> - ${header.device}</div>`;
    });
    html += '</div>';
    
    // 상태 요청 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600">상태 요청 패킷</h4>';
    packetSuggestions.headers.state_request.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 px-1">${header.header}</span> - ${header.device}</div>`;
    });
    html += '</div>';
    
    // 응답 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600">응답 패킷</h4>';
    packetSuggestions.headers.ack.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 px-1">${header.header}</span> - ${header.device}</div>`;
    });
    html += '</div>';
    
    html += '</div>';
    resultDiv.innerHTML = html;
}

function handlePacketInput(e) {
    const input = e.target;
    const packet = input.value.replace(/[\s-]+/g, '').trim().toUpperCase();
    
    if (packet.length === 0) {
        showAvailableHeaders();
        return;
    }
    if (packet.length >= 2) {
        // 입력된 패킷이 2자리 이상이면 나머지를 00으로 채워서 분석
        const paddedPacket = packet.padEnd(14, '0');
        if (/^[0-9A-F]+$/.test(packet)) {  // 유효한 16진수인 경우에만 분석
            analyzePacket(paddedPacket);
        }
    }
}

// 패킷 구조 및 참조 자료 관련 함수들
function createPacketTable(deviceData) {
    const table = document.createElement('table');
    table.className = 'min-w-full divide-y divide-gray-200';
    
    const headerRow = document.createElement('tr');
    const headers = ['Byte', ...Object.values(PACKET_TYPES)];
    headers.forEach(header => {
        const th = document.createElement('th');
        th.className = 'px-4 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider';
        th.textContent = header;
        headerRow.appendChild(th);
    });
    table.appendChild(headerRow);
    
    for (let byte = 0; byte < 8; byte++) {
        const row = document.createElement('tr');
        row.className = byte % 2 === 0 ? 'bg-white' : 'bg-gray-50';
        
        const byteCell = document.createElement('td');
        byteCell.className = 'px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-900';
        byteCell.textContent = `Byte ${byte}`;
        row.appendChild(byteCell);
        
        Object.keys(PACKET_TYPES).forEach(type => {
            const td = document.createElement('td');
            td.className = 'px-4 py-2 text-sm text-gray-500';
            
            if (deviceData[type]) {
                if (deviceData[type].byte_desc && deviceData[type].byte_desc[byte] !== undefined) {
                    const descDiv = document.createElement('div');
                    descDiv.className = 'font-medium text-gray-900 mb-2';
                    descDiv.textContent = deviceData[type].byte_desc[byte];
                    td.appendChild(descDiv);
                }
                
                if (deviceData[type].byte_values && deviceData[type].byte_values[byte]) {
                    const valuesDiv = document.createElement('div');
                    valuesDiv.className = 'space-y-1';
                    Object.entries(deviceData[type].byte_values[byte]).forEach(([key, value]) => {
                        const valueSpan = document.createElement('div');
                        valueSpan.className = 'text-sm text-gray-600';
                        valueSpan.textContent = `${key}: ${value}`;
                        valuesDiv.appendChild(valueSpan);
                    });
                    td.appendChild(valuesDiv);
                }
                
                if (deviceData[type].byte_memos && deviceData[type].byte_memos[byte]) {
                    const memoDiv = document.createElement('div');
                    memoDiv.className = 'mt-2 text-sm text-gray-500 italic';
                    memoDiv.textContent = `💡 ${deviceData[type].byte_memos[byte]}`;
                    td.appendChild(memoDiv);
                }
            }
            
            row.appendChild(td);
        });
        
        table.appendChild(row);
    }
    
    return table;
}

function updatePacketReference(data) {
    const tabContents = document.getElementById('tabContents');
    tabContents.innerHTML = '';

    // 각 디바이스에 대한 테이블 생성
    Object.entries(data).forEach(([deviceName, deviceData]) => {
        const deviceSection = document.createElement('div');
        deviceSection.id = `device-${deviceName}`;
        deviceSection.className = 'tab-content';
        
        const table = createPacketTable(deviceData);
        deviceSection.appendChild(table);
        
        tabContents.appendChild(deviceSection);
    });
}

function openDeviceTab(evt, deviceName) {
    // 모든 탭 내용 숨기기
    const tabcontents = document.getElementsByClassName("tab-content");
    for (let content of tabcontents) {
        content.classList.add('hidden');
    }

    // 모든 탭 버튼 비활성화
    const tabButtons = document.getElementById('deviceTabs').getElementsByTagName('button');
    for (let button of tabButtons) {
        button.className = button.className
            .replace('border-blue-500 text-blue-600', 'border-transparent text-gray-500')
            .replace('hover:text-gray-700 hover:border-gray-300', '');
        
        // 호버 효과 다시 추가 (비활성 탭에만)
        if (button.getAttribute('data-tab') !== deviceName) {
            button.className += ' hover:text-gray-700 hover:border-gray-300';
        }
    }
    
    // 선택된 탭 내용 표시 및 버튼 활성화
    const selectedTab = document.getElementById(deviceName);
    selectedTab.classList.remove('hidden');
    evt.currentTarget.className = evt.currentTarget.className
        .replace('border-transparent text-gray-500', 'border-blue-500 text-blue-600');
}

// ===============================
// 초기화 및 상태 업데이트 함수들
// ===============================

// MQTT 상태 업데이트
function updateMqttStatus() {
    fetch('./api/mqtt_status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('connectionStatus');
            statusElement.textContent = data.connected ? '연결됨' : '연결 끊김';
            statusElement.className = data.connected ? 
                'px-2 py-1 rounded text-sm bg-green-100 text-green-800' : 
                'px-2 py-1 rounded text-sm bg-red-100 text-red-800';
            
            document.getElementById('brokerInfo').textContent = data.broker || '-';
            document.getElementById('clientId').textContent = data.client_id || '-';
            
            // 구독 중인 토픽 표시
            const topicsDiv = document.getElementById('subscribedTopics');
            topicsDiv.innerHTML = data.subscribed_topics.map(topic => 
                `<div class="text-sm bg-gray-50 p-2 rounded">${topic}</div>`
            ).join('');
        });
}

// CONFIG 로드
function loadConfig() {
    fetch('./api/config')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showConfigMessage('설정을 불러오는 중 오류가 발생했습니다: ' + data.error, true);
                return;
            }

            const configDiv = document.getElementById('configForm');
            configDiv.innerHTML = '';

            // 스키마 기반으로 설정 UI 생성
            for (const [key, value] of Object.entries(data.config)) {
                const schema = data.schema[key] || '';
                configDiv.appendChild(createConfigField(key, value, schema));
            }
        });
}

function createConfigField(key, value, schema) {
    const fieldDiv = document.createElement('div');
    fieldDiv.className = 'border-b border-gray-200 py-2';

    // 객체인 경우 하위 설정 처리
    if (typeof value === 'object' && value !== null) {
        fieldDiv.innerHTML = `
            <div class="mb-2">
                <label class="text-sm font-medium text-gray-700">${key}</label>
            </div>
            <div class="pl-4 space-y-2">
                ${Object.entries(value).map(([subKey, subValue]) => `
                    <div class="flex items-center gap-2">
                        <label class="text-sm text-gray-600 w-1/3">${subKey}:</label>
                        <input type="text" 
                            value="${subValue}" 
                            class="form-input block rounded-md border-gray-300 text-sm py-1"
                            data-key="${key}"
                            data-subkey="${subKey}">
                    </div>
                `).join('')}
            </div>
        `;
        return fieldDiv;
    }

    // 기존 단일 설정 처리
    const labelContainer = createLabelContainer(key, schema);
    fieldDiv.appendChild(labelContainer);

    const description = document.createElement('p');
    description.className = 'text-xs text-gray-500 mb-1';
    description.textContent = '';
    fieldDiv.appendChild(description);

    const input = createInputField(key, value, schema);
    fieldDiv.appendChild(input);

    return fieldDiv;
}

function createLabelContainer(key, schema) {
    const labelContainer = document.createElement('div');
    labelContainer.className = 'flex items-center gap-1 mb-1';

    const label = document.createElement('label');
    label.className = 'text-sm font-medium text-gray-700';
    label.textContent = key;

    const isOptional = schema.endsWith('?');
    if (!isOptional) {
        label.textContent += ' *';
    }
    schema = schema.replace('?', '');

    labelContainer.appendChild(label);

    // 스키마 타입에 따른 툴팁 추가
    if (schema.includes('(')) {
        const tooltip = createTooltip(schema);
        if (tooltip) {
            labelContainer.appendChild(tooltip);
        }
    }

    return labelContainer;
}

function createTooltip(schema) {
    const schemaType = schema.split('(')[0];
    const tooltip = document.createElement('span');
    tooltip.className = 'text-xs text-gray-500';

    if (schemaType === 'int' || schemaType === 'float') {
        const rangeMatch = schema.match(/\(([^)]+)\)/);
        if (rangeMatch) {
            const [min, max] = rangeMatch[1].split(',').map(v => v.trim());
            tooltip.textContent = `(${min || '제한없음'} ~ ${max || '제한없음'})`;
            return tooltip;
        }
    } else if (schemaType === 'list') {
        const options = schema.split('(')[1].replace('?)', '').replace(')', '');
        tooltip.textContent = `(${options})`;
        return tooltip;
    } else if (schema === 'match(^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$)') {
        tooltip.textContent = '(예: 192.168.0.2)';
        return tooltip;
    }

    return null;
}

function createInputField(key, value, schema) {
    const schemaType = schema.split('(')[0];
    const isOptional = schema.endsWith('?');
    schema = schema.replace('?', '');

    let input;
    const baseClassName = 'form-input block w-full rounded-md border-gray-300 text-sm py-1';

    switch (schemaType) {
        case 'bool':
            input = createSelectInput(['true', 'false'], value === true, baseClassName);
            break;
        case 'list':
            const options = schema.split('(')[1].replace('?)', '').replace(')', '').split('|');
            input = createSelectInput(options, value, baseClassName);
            break;
        case 'int':
        case 'float':
            input = createNumberInput(schema, value, schemaType, baseClassName);
            break;
        case 'match':
            input = createMatchInput(schema, value, baseClassName);
            break;
        default:
            input = createTextInput(value, baseClassName);
    }

    input.id = `config-${key}`;
    input.dataset.key = key;
    input.dataset.type = schemaType;
    if (!isOptional) {
        input.required = true;
    }

    return input;
}

function createSelectInput(options, selectedValue, className) {
    const select = document.createElement('select');
    select.className = className;

    options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.textContent = option === 'true' ? '예 (true)' : 
                                  option === 'false' ? '아니오 (false)' : 
                                  option;
        optionElement.selected = option === String(selectedValue);
        select.appendChild(optionElement);
    });

    return select;
}

function createNumberInput(schema, value, type, className) {
    const input = document.createElement('input');
    input.type = 'number';
    input.value = value;
    input.className = className;
    input.step = type === 'float' ? '0.01' : '1';

    if (schema.includes('(')) {
        const rangeMatch = schema.match(/\(([^)]+)\)/);
        if (rangeMatch) {
            const [min, max] = rangeMatch[1].split(',').map(v => v.trim());
            if (min) input.min = min;
            if (max) input.max = max;
            addRangeValidation(input, min, max, type);
        }
    }

    return input;
}

function createMatchInput(schema, value, className) {
    const input = document.createElement('input');
    input.type = 'text';
    input.value = value;
    input.className = className;

    const pattern = schema.split('(')[1].replace('?)', '').replace(')', '');
    input.pattern = pattern;
    addPatternValidation(input, pattern);

    return input;
}

function createTextInput(value, className) {
    const input = document.createElement('input');
    input.type = 'text';
    input.value = value;
    input.className = className;
    return input;
}

function addRangeValidation(input, min, max, type) {
    input.addEventListener('input', function() {
        const val = type === 'int' ? parseInt(this.value) : parseFloat(this.value);
        if (min && val < parseFloat(min)) {
            this.setCustomValidity(`최소값은 ${min}입니다.`);
        } else if (max && val > parseFloat(max)) {
            this.setCustomValidity(`최대값은 ${max}입니다.`);
        } else {
            this.setCustomValidity('');
        }
    });
}

function addPatternValidation(input, pattern) {
    input.addEventListener('input', function() {
        const regex = new RegExp(pattern);
        if (!regex.test(this.value)) {
            const isIpPattern = pattern === '^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$';
            this.setCustomValidity(isIpPattern ? '올바른 IP 주소 형식이 아닙니다.' : '올바른 형식이 아닙니다.');
        } else {
            this.setCustomValidity('');
        }
    });
}

// 설정 저장
function saveConfig() {
    if (!confirm('설정을 저장하면 애드온이 재시작됩니다. 계속하시겠습니까?')) {
        return;
    }

    const configData = {};
    const inputs = document.querySelectorAll('#configForm input, #configForm select');
    
    inputs.forEach(input => {
        const key = input.getAttribute('data-key');
        const subKey = input.getAttribute('data-subkey');
        const schemaType = input.getAttribute('data-type');
        
        let value;
        if (schemaType === 'bool') {
            value = input.value === 'true';
        } else if (schemaType === 'int') {
            value = parseInt(input.value);
        } else if (schemaType === 'float') {
            value = parseFloat(input.value);
        } else {
            value = input.value;
        }
        
        // 비밀번호 필드가 마스킹된 상태면 저장하지 않음
        if (input.type === 'password' && value === '********') {
            return;
        }
        
        // 하위 설정 처리
        if (subKey) {
            if (!configData[key]) {
                configData[key] = {};
            }
            configData[key][subKey] = value;
        } else {
            configData[key] = value;
        }
    });

    showConfigMessage('설정을 저장하고 애드온을 재시작하는 중...', false);

    // 설정 저장 API 호출
    fetch('./api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        // 유효성 검사 실패 등의 즉각적인 오류 처리
        if (!data.success) {
            if (data.error === '유효성 검사 실패' && data.details) {
                const errorMessage = ['유효성 검사 실패:'].concat(data.details).join('\n');
                showConfigMessage(errorMessage, true);
                throw new Error('validation_failed');
            } else {
                showConfigMessage(data.error || '설정 저장 실패', true);
                throw new Error('save_failed');
            }
        }
    })
    .catch(error => {
        // 유효성 검사 실패나 명시적인 저장 실패가 아닌 경우는 재시작으로 인한 연결 끊김으로 간주
        if (error.message !== 'validation_failed' && error.message !== 'save_failed') {
            console.log('애드온이 재시작되는 중입니다...');
            // 10초 후에 페이지 새로고침
            setTimeout(() => {
                window.location.reload();
            }, 10000);
        } else {
            console.error('설정 저장 실패:', error);
        }
    });
}

function showConfigMessage(message, isError) {
    const messageElement = document.getElementById('configMessage');
    messageElement.innerHTML = message.replace(/\n/g, '<br>');
    messageElement.className = `text-sm ${isError ? 'text-red-600' : 'text-green-600'} whitespace-pre-line`;
}

// 이벤트 리스너 추가
document.addEventListener('DOMContentLoaded', function() {
    const saveButton = document.getElementById('saveConfig');
    if (saveButton) {
        saveButton.addEventListener('click', saveConfig);
    }
});

// 최근 MQTT 메시지 업데이트
function updateRecentMessages() {
    fetch('./api/recent_messages')
        .then(response => response.json())
        .then(data => {
            const messagesDiv = document.getElementById('recentMessages');
            messagesDiv.innerHTML = data.messages.map(msg => `
                <div class="text-sm border-l-4 border-blue-500 pl-2">
                    <div class="font-medium">${msg.topic}</div>
                    <div class="text-gray-600">${msg.payload}</div>
                    <div class="text-xs text-gray-400">${msg.timestamp}</div>
                </div>
            `).join('');
        });
}

function clearLivePacketLog() {
    const sendLogDiv = document.getElementById('send-data');
    const recvLogDiv = document.getElementById('recv-data');
    sendLogDiv.innerHTML = '';
    recvLogDiv.innerHTML = '';
    liveLastPackets.clear();
}

// 모바일 메뉴 토글 함수
function toggleMobileMenu() {
    const mobileMenu = document.getElementById('mobileMenu');
    if (mobileMenu.classList.contains('hidden')) {
        mobileMenu.classList.remove('hidden');
    } else {
        mobileMenu.classList.add('hidden');
    }
}

// 페킷 구조 편집 관련 함수들
function checkVendorSetting() {
    fetch('./api/config')
        .then(response => response.json())
        .then(data => {
            const vendorWarning = document.getElementById('vendorWarning');
            if (data.config && data.config.vendor === 'commax') {
                vendorWarning.classList.remove('hidden');
            } else {
                vendorWarning.classList.add('hidden');
            }
        });
}

function changeVendorToCustom() {
    if (!confirm('vendor 설정을 변경하면 애드온이 재시작됩니다. 계속하시겠습니까?')) {
        return;
    }
    fetch('./api/config')
        .then(response => response.json())
        .then(data => {
            const configData = data.config || {};
            configData.vendor = 'custom';  // vendor만 custom으로 변경
            return configData;
        })
        .then(configData => {

            showPacketEditorMessage('vendor 설정을 변경하고 애드온을 재시작하는 중...', false);

            fetch('./api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            })
            setTimeout(() => {
                window.location.reload();
            }, 3000);
    })
}

function loadCustomPacketStructure() {
    fetch('./api/custom_packet_structure/editable')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderPacketStructureEditor(data.content);
            } else {
                showPacketEditorMessage(data.error, true);
            }
        })
        .catch(error => showPacketEditorMessage('패킷 구조를 불러오는 중 오류가 발생했습니다: ' + error, true));
}

function showPacketEditorMessage(message, isError) {
    const messageElement = document.getElementById('packetEditorMessage');
    if (messageElement) {
        messageElement.textContent = message;
        messageElement.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg ${isError ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`;
        messageElement.classList.remove('hidden');
        setTimeout(() => {
            messageElement.classList.add('hidden');
        }, 15000);
    } else {
        console.error('메시지 표시 요소를 찾을 수 없습니다:', message);
    }
}

function renderPacketStructureEditor(structure) {
    const editorDiv = document.getElementById('packetStructureEditor');
    editorDiv.innerHTML = '';

    for (const [deviceName, deviceData] of Object.entries(structure)) {
        const deviceSection = document.createElement('div');
        deviceSection.className = 'border rounded-lg p-4 mb-4';
        
        deviceSection.innerHTML = `
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-medium">${deviceName}</h3>
                <input type="text" value="${deviceData.type}" 
                    class="border rounded px-2 py-1 text-sm"
                    data-device="${deviceName}" data-field="type">
            </div>
        `;

        // 패킷 타입별 섹션 추가
        Object.entries(PACKET_TYPES).forEach(([type, title]) => {
            if (deviceData[type]) {
                const packetSection = createPacketSection(deviceName, type, deviceData[type], title);
                deviceSection.appendChild(packetSection);
            }
        });

        editorDiv.appendChild(deviceSection);
    }
}

function createPacketSection(deviceName, packetType, packetData, title) {
    const section = document.createElement('div');
    section.className = 'mt-4 w-full sm:w-1/2 lg:w-1/4 inline-block align-top px-2';

    section.innerHTML = `
        <div class="bg-gray-50 p-3 rounded-lg">
            <h4 class="font-medium mb-2">${title}</h4>
            <div class="space-y-2">
                <div class="flex items-center">
                    <span class="w-20 text-sm">Header:</span>
                    <input type="text" value="${packetData.header}" 
                        class="border rounded px-2 py-1 text-sm flex-1"
                        data-device="${deviceName}" 
                        data-packet-type="${packetType}" 
                        data-field="header">
                </div>
            </div>
        `;

    if (packetData.structure) {
        const structureDiv = document.createElement('div');
        structureDiv.className = 'mt-2';
        
        Object.entries(packetData.structure).forEach(([position, field]) => {
            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'border-l-2 border-gray-200 pl-2 py-2 mt-2';
            fieldDiv.innerHTML = `
                <div class="text-sm font-medium">Position ${position}</div>
                <div class="space-y-1 mt-1">
                    <div>
                        <label class="block text-xs text-gray-600">Name:</label>
                        <input type="text" value="${field.name}" 
                            class="border rounded px-2 py-1 text-sm w-full"
                            data-device="${deviceName}" 
                            data-packet-type="${packetType}" 
                            data-position="${position}"
                            data-field="name">
                    </div>
                    <div>
                        <label class="block text-xs text-gray-600">Values:</label>
                        <div class="space-y-1" id="values-${deviceName}-${packetType}-${position}">
                            ${Object.entries(field.values || {}).map(([key, value]) => `
                                <div class="grid grid-cols-9 gap-1">
                                    <input type="text" value="${key}" 
                                        class="col-span-4 border rounded px-2 py-1 text-sm"
                                        placeholder="키"
                                        data-device="${deviceName}" 
                                        data-packet-type="${packetType}" 
                                        data-position="${position}"
                                        data-field="value-key">
                                    <input type="text" value="${value}" 
                                        class="col-span-4 border rounded px-2 py-1 text-sm"
                                        placeholder="값"
                                        data-device="${deviceName}" 
                                        data-packet-type="${packetType}" 
                                        data-position="${position}"
                                        data-field="value-value">
                                    <button class="text-red-500 hover:text-red-700" onclick="removeValue(this)">×</button>
                                </div>
                            `).join('')}
                            <button class="text-sm text-blue-500 hover:text-blue-700" 
                                onclick="addValue('${deviceName}', '${packetType}', '${position}')">
                                + 값 추가
                            </button>
                        </div>
                    </div>
                </div>
            `;
            structureDiv.appendChild(fieldDiv);
        });
        
        section.appendChild(structureDiv);
    }

    return section;
}

function addValue(deviceName, packetType, position) {
    const valuesDiv = document.getElementById(`values-${deviceName}-${packetType}-${position}`);
    const newValueDiv = document.createElement('div');
    newValueDiv.className = 'flex gap-1';
    newValueDiv.innerHTML = `
        <input type="text" class="border rounded px-2 py-1 text-sm flex-1" 
            placeholder="키"
            data-device="${deviceName}" 
            data-packet-type="${packetType}" 
            data-position="${position}"
            data-field="value-key">
        <input type="text" class="border rounded px-2 py-1 text-sm flex-1" 
            placeholder="값"
            data-device="${deviceName}" 
            data-packet-type="${packetType}" 
            data-position="${position}"
            data-field="value-value">
        <button class="text-red-500 hover:text-red-700" onclick="removeValue(this)">×</button>
    `;
    valuesDiv.insertBefore(newValueDiv, valuesDiv.lastElementChild);
}

function removeValue(button) {
    button.parentElement.remove();
}

function saveCustomPacketStructure() {
    const structure = {};
    const editorDiv = document.getElementById('packetStructureEditor');

    // 각 기기별로 데이터 수집
    editorDiv.querySelectorAll('[data-device]').forEach(element => {
        const deviceName = element.dataset.device;
        const packetType = element.dataset.packetType;
        const position = element.dataset.position;
        const field = element.dataset.field;

        if (!structure[deviceName]) {
            structure[deviceName] = { type: '' };
        }

        if (field === 'type') {
            structure[deviceName].type = element.value;
            return;
        }

        if (!packetType) return;

        if (!structure[deviceName][packetType]) {
            structure[deviceName][packetType] = {
                header: '',
                structure: {}
            };
        }

        if (field === 'header') {
            structure[deviceName][packetType].header = element.value;
            return;
        }

        if (position) {
            if (!structure[deviceName][packetType].structure[position]) {
                structure[deviceName][packetType].structure[position] = {
                    name: '',
                    values: {}
                };
            }

            if (field === 'name') {
                structure[deviceName][packetType].structure[position].name = element.value;
            }
        }
    });

    // values 데이터 수집
    editorDiv.querySelectorAll('[data-field^="value-"]').forEach(element => {
        const deviceName = element.dataset.device;
        const packetType = element.dataset.packetType;
        const position = element.dataset.position;
        
        if (!element.value) return;

        const values = structure[deviceName][packetType].structure[position].values;
        const row = element.parentElement;
        const keyInput = row.querySelector('[data-field="value-key"]');
        const valueInput = row.querySelector('[data-field="value-value"]');
        
        if (keyInput.value && valueInput.value) {
            values[keyInput.value] = valueInput.value;
        }
    });

    // 서버에 저장
    fetch('./api/custom_packet_structure/editable', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ content: structure })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showPacketEditorMessage('패킷 구조가 성공적으로 저장되었습니다.', false);
        } else {
            showPacketEditorMessage(data.error, true);
        }
    })
    .catch(error => showPacketEditorMessage('저장 중 오류가 발생했습니다: ' + error, true));
}

function resetPacketStructure() {
    if (!confirm('패킷 구조를 초기화하면 모든 커스텀 설정이 삭제되고 commax기본값으로 돌아갑니다. 계속하시겠습니까?')) {
        return;
    }

    fetch('./api/custom_packet_structure', {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showPacketEditorMessage('패킷 구조가 초기화되었습니다. 애드온을 재시작합니다...', false);
            // 애드온 재시작
            fetch('./api/find_devices', {
                method: 'POST'
            });
            // 3초 후 페이지 새로고침
            setTimeout(() => {
                window.location.reload();
            }, 3000);
        } else {
            showPacketEditorMessage(data.error || '초기화 중 오류가 발생했습니다.', true);
        }
    })
    .catch(error => {
        showPacketEditorMessage('초기화 중 오류가 발생했습니다: ' + error, true);
    });
}

// 이벤트 리스너 추가를 DOMContentLoaded 이벤트 핸들러 내부에 추가
document.addEventListener('DOMContentLoaded', function() {
    fetch('./api/packet_suggestions')
        .then(response => response.json())
        .then(data => {
            packetSuggestions = data;
            showAvailableHeaders();
        });
    updateDeviceList();
    updatePacketLogDisplay();
    loadPacketStructures();
    updateMqttStatus();
    loadConfig();

    // 패킷 에디터 초기화
    loadCustomPacketStructure();
    checkVendorSetting();

    // 저장 버튼 이벤트 핸들러
    document.getElementById('savePacketStructure').addEventListener('click', saveCustomPacketStructure);
    
    // vendor 변경 버튼 이벤트 핸들러
    document.getElementById('changeVendorButton').addEventListener('click', changeVendorToCustom);
    
    const saveButton = document.getElementById('saveConfig');
    if (saveButton) {
        saveButton.addEventListener('click', saveConfig);
    }
    // 패킷 입력 필드 이벤트 리스너 설정
    const packetInput = document.getElementById('packetInput');
    if (packetInput) {
        packetInput.addEventListener('input', handlePacketInput);
        packetInput.addEventListener('keydown', function(e) {
            const history = loadPacketHistory();
            
            if (e.key === 'Enter') {
                analyzePacket();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (historyIndex === -1) {
                    currentInput = this.value;
                }
                if (historyIndex < history.length - 1) {
                    historyIndex++;
                    this.value = history[historyIndex];
                    handlePacketInput({target: this});
                }
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (historyIndex > -1) {
                    historyIndex--;
                    this.value = historyIndex === -1 ? currentInput : history[historyIndex];
                    handlePacketInput({target: this});
                }
            }
        });
        // 포커스를 얻을 때 입력값이 없으면 헤더 목록 표시
        packetInput.addEventListener('focus', function() {
            if (!this.value) {
                showAvailableHeaders();
            }
        });
    }
    // 주기적 업데이트 설정
    setInterval(updateDeviceList, 10000);  // 10초마다 기기목록 업데이트
    setInterval(updateMqttStatus, 5000);   // 5초마다 MQTT 상태 업데이트
    setInterval(updateRecentMessages, 2000); // 2초마다 최근 메시지 업데이트
    
    // 패킷 구조 초기화 버튼 이벤트 리스너
    const resetButton = document.getElementById('resetPacketStructure');
    if (resetButton) {
        resetButton.addEventListener('click', resetPacketStructure);
    }
});

function loadPacketStructures() {
    fetch('./api/packet_structures')
        .then(response => response.json())
        .then(structures => {
            const tabButtons = document.getElementById('deviceTabs');
            const tabContents = document.getElementById('tabContents');
            if (!tabButtons || !tabContents) return;
            
            tabButtons.innerHTML = '';
            tabContents.innerHTML = '';
            
            let isFirst = true;
            
            for (const [deviceName, info] of Object.entries(structures)) {
                // 탭 버튼 추가
                const button = document.createElement('button');
                button.className = `px-4 py-2 text-sm font-medium border-b-2 focus:outline-none transition-colors ${isFirst ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`;
                button.setAttribute('data-tab', deviceName);
                button.onclick = function(evt) { openDeviceTab(evt, deviceName); };
                button.textContent = deviceName;
                tabButtons.appendChild(button);
                
                // 탭 내용 생성
                const tabContent = document.createElement('div');
                tabContent.id = deviceName;
                tabContent.className = `tab-content ${isFirst ? '' : 'hidden'}`;
                
                const table = createPacketTable(info);
                tabContent.appendChild(table);
                
                tabContents.appendChild(tabContent);
                isFirst = false;
            }
        })
        .catch(error => {
            console.error('패킷 구조 로드 실패:', error);
            const tabContents = document.getElementById('tabContents');
            if (tabContents) {
                tabContents.innerHTML = `
                    <div class="text-red-500 p-4">
                        패킷 구조를 로드하는 중 오류가 발생했습니다.<br>
                        ${error.message}
                    </div>
                `;
            }
        });
}

function extractPackets() {
    const logDiv = document.getElementById('livePacketLog');
    const packets = [];
    
    // 전용 클래스를 사용하여 패킷 엔트리 선택
    logDiv.querySelectorAll('.packet-log-entry').forEach(entry => {
        const timestamp = entry.querySelector('.packet-timestamp').textContent;
        const type = entry.querySelector('.packet-type').textContent.replace(/[\[\]]/g, '');
        const packet = entry.querySelector('.packet-content').textContent.trim();
        const deviceInfo = entry.querySelector('.packet-device').textContent.replace(/[\[\]]/g, '').trim();
        
        packets.push(`${timestamp} [${type}] ${packet} [${deviceInfo}]`);
    });
    
    // 텍스트 파일로 저장
    const blob = new Blob([packets.join('\n')], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `packet_log_${new Date().toISOString().slice(0,19).replace(/[:-]/g, '')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// 실시간 패킷 데이터 폴링 시작
function startPolling() {
    if (isPolling) return;
    
    isPolling = true;
    console.log('실시간 패킷 데이터 폴링 시작');
    
    // 500ms마다 데이터 요청
    pollingInterval = setInterval(fetchPacketData, 500);
}

// 실시간 패킷 데이터 폴링 중지
function stopPolling() {
    if (!isPolling) return;
    
    isPolling = false;
    console.log('실시간 패킷 데이터 폴링 중지');
    
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// 실시간 패킷 데이터 요청
async function fetchPacketData() {
    if (isPaused) return;
    
    try {
        const response = await fetch('./api/live_packets');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        // 패킷 데이터 업데이트
        updateLivePacketDisplay(data);
    } catch (error) {
        console.error('패킷 데이터 요청 실패:', error);
    }
}

// 패킷 데이터 화면 업데이트
function updateLivePacketDisplay(data) {
    const sendDataElement = document.getElementById('send-data');
    const recvDataElement = document.getElementById('recv-data');
    
    if (sendDataElement && data.send_data) {
        sendDataElement.textContent = data.send_data.join('\n');
    }
    if (recvDataElement && data.recv_data) {
        recvDataElement.textContent = data.recv_data.join('\n');
    }
}

// 일시정지 토글 함수
function togglePause() {
    isPaused = !isPaused;
    const pauseButton = document.getElementById('pauseButton');
    if (pauseButton) {
        pauseButton.textContent = isPaused ? '재개' : '일시정지';
    }
}

function startPacketLogUpdate() {
    packetLogInterval = setInterval(updatePacketLog, 1000);
}

function stopPacketLogUpdate() {
    if (packetLogInterval) {
        clearInterval(packetLogInterval);
        packetLogInterval = null;
    }
}