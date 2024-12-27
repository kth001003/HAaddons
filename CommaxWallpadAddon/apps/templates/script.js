// @ts-nocheck
// 전역 변수 선언
let lastPackets = new Set();
let packetSuggestions = null;
const HISTORY_KEY = 'packet_analysis_history';
const MAX_HISTORY = 20;
let historyIndex = -1;  // 히스토리 인덱스 추가
let currentInput = '';   // 현재 입력값 저장용 변수 추가

// 실시간 패킷 로그 관련 함수들
let liveLastPackets = new Set();

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
}

// ===============================
// 기기 목록 관련 함수
// ===============================
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
function analyzePacket(paddedPacket) {
    const packetInput = document.getElementById('packetInput');
    const resultDiv = document.getElementById('packetResult');
    // 입력값에서 공백 제거
    const packet = (paddedPacket || packetInput.value.replace(/[\s-]+/g, '').trim()).toUpperCase();
    
    if (!packet) {
        showAvailableHeaders();
        return;
    }
    
    if (!/^[0-9A-F]{14}$/.test(packet) && !/^[0-9A-F]{16}$/.test(packet)) {
        if (packet.length >= 2) {
            // 2자리 이상 입력된 경우 나머지를 00으로 채워서 분석
            const paddedPacket = packet.padEnd(14, '0');
            if (/^[0-9A-F]+$/.test(packet)) {
                analyzePacket(paddedPacket);
            }
        }
        return;
    }
    
    // Enter 키로 분석한 경우에만 히스토리에 저장
    if (!paddedPacket) {
        savePacketHistory(packet);
    }
    
    // 헤더로 패킷 타입 자동 감지
    const header = packet.substring(0, 2);
    let packetType = 'command';  // 기본값
    
    // packetSuggestions이 초기화된 경우에만 패킷 타입 감지 시도
    if (packetSuggestions && packetSuggestions.headers) {
        const isState = packetSuggestions.headers.state.some(h => h.header === header);
        const isStateRequest = packetSuggestions.headers.state_request.some(h => h.header === header);
        const isAck = packetSuggestions.headers.ack.some(h => h.header === header);
        if (isState) {
            packetType = 'state';
        } else if (isStateRequest) {
            packetType = 'state_request';
        } else if (isAck) {
            packetType = 'ack';
        }
    }
    
    fetch('./api/analyze_packet', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            command: packet,
            type: packetType
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let html = '<h3 class="text-lg font-bold mb-2">분석 결과:</h3>';
            if (packetType === 'command') {
                html += `<p class="mb-2">패킷 타입: <strong>명령</strong></p>`;
            } else if (packetType === 'state') {
                html += `<p class="mb-2">패킷 타입: <strong>상태</strong></p>`;
            } else if (packetType === 'state_request') {
                html += `<p class="mb-2">패킷 타입: <strong>상태 요청</strong></p>`;
            } else if (packetType === 'ack') {
                html += `<p class="mb-2">패킷 타입: <strong>응답</strong></p>`;
            }
            html += `<p class="mb-2">기기: <strong>${data.device}</strong></p>`;
            
            if (data.checksum) {
                const formattedChecksum = data.checksum.match(/.{2}/g).join(' ');
                html += `<p class="mb-2">체크섬이 포함된 패킷: <strong class="font-mono">${formattedChecksum}</strong></p>`;
            } else {
                html += '<p class="text-red-500">체크섬 계산 실패</p>';
            }
            
            if (data.analysis && data.analysis.length > 0) {
                html += '<h4 class="text-md font-bold mt-4 mb-2">바이트별 분석:</h4>';
                html += '<div class="font-mono space-y-1">';
                data.analysis.forEach(desc => {
                    html += `<div>${desc}</div>`;
                });
                html += '</div>';
            }
            
            if (packetType === 'command' && data.expected_state) {
                const formattedExpectedPacket = data.expected_state.expected_packet.match(/.{2}/g).join(' ');
                html += `<h4 class="text-md font-bold mt-4 mb-2">예상되는 상태 패킷:</h4>`;
                html += `<p class="mb-2"><strong><a href="#" onclick="analyzeExpectedState('${data.expected_state.expected_packet}')" class="text-blue-500 hover:text-blue-700 font-mono">${formattedExpectedPacket}</a></strong></p>`;
                html += `<p class="mb-2">필수 바이트 위치: ${data.expected_state.required_bytes.join(', ')}</p>`;
                
                if (data.expected_state.analysis && data.expected_state.analysis.length > 0) {
                    html += '<h4 class="text-md font-bold mt-4 mb-2">예상 패킷 바이트별 분석:</h4>';
                    html += '<div class="font-mono space-y-1">';
                    data.expected_state.analysis.forEach(desc => {
                        html += `<div>${desc}</div>`;
                    });
                    html += '</div>';
                }
            }
            
            resultDiv.innerHTML = html;
        } else {
            resultDiv.innerHTML = `<p class="text-red-500">오류: ${data.error}</p>`;
        }
    })
    .catch(error => {
        resultDiv.innerHTML = `<p class="text-red-500">요청 실패: ${error}</p>`;
    });
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
function updatePacketLog() {
    fetch('./api/packet_logs')
        .then(response => response.json())
        .then(data => {
            const logDiv = document.getElementById('packetLog');
            let newContent = '';
            
            // 송신 패킷 처리
            const newSendPackets = data.send.filter(packet => !lastPackets.has('send:' + packet.packet));
            newSendPackets.forEach(packet => {
                const timestamp = new Date().toLocaleTimeString();
                newContent += createPacketLogEntry(packet, 'send');
                lastPackets.add('send:' + packet.packet);
            });
            
            // 수신 패킷 처리
            const newRecvPackets = data.recv.filter(packet => !lastPackets.has('recv:' + packet.packet));
            newRecvPackets.forEach(packet => {
                const timestamp = new Date().toLocaleTimeString();
                newContent += createPacketLogEntry(packet, 'recv');
                lastPackets.add('recv:' + packet.packet);
            });
            
            if (newContent) {
                logDiv.innerHTML = newContent + logDiv.innerHTML;
                // Unknown 패킷 숨기기 상태 적용
                updatePacketLogDisplay();
            }
        });
}

function createPacketLogEntry(packet, type) {
    const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
    const deviceText = deviceInfo.device !== "Unknown" ? 
        `${deviceInfo.device} ${deviceInfo.packet_type}` : 
        "Unknown";
    
    const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
    
    return `
        <div class="p-2 border-b border-gray-200 hover:bg-gray-50 cursor-pointer ${deviceInfo.device === 'Unknown' ? 'opacity-70 unknown-packet' : ''}" onclick="handlePacketClick('${packet.packet}')">
            <span class="inline-block min-w-[50px] mr-2 text-sm font-semibold ${type === 'send' ? 'text-green-600' : 'text-blue-600'}">[${type.toUpperCase()}]</span>
            <span class="font-mono">${formattedPacket}</span>
            <span class="inline-block min-w-[120px] ml-2 text-sm text-gray-600">[${deviceText}]</span>
        </div>`;
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

function updatePacketLogDisplay() {
    const hideUnknown = document.getElementById('hideUnknown').checked;
    const unknownPackets = document.querySelectorAll('.unknown-packet');
    
    unknownPackets.forEach(packet => {
        if (hideUnknown) {
            packet.classList.add('hidden');
        } else {
            packet.classList.remove('hidden');
        }
    });
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
    const headers = ['Byte', '명령', '응답', '상태요청', '상태'];
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
        
        const types = ['command', 'ack', 'state_request', 'state'];
        types.forEach(type => {
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

// 초기화 함수
function initialize() {
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
}

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

            const configDiv = document.getElementById('configDisplay');
            configDiv.innerHTML = '';

            // 스키마 기반으로 설정 UI 생성
            for (const [key, value] of Object.entries(data.config)) {
                const schema = data.schema[key] || '';
                const fieldDiv = document.createElement('div');
                fieldDiv.className = 'border-b border-gray-200 pb-4';

                const label = document.createElement('label');
                label.className = 'block font-medium text-gray-700 mb-2';
                label.textContent = key;

                const description = document.createElement('p');
                description.className = 'text-sm text-gray-500 mb-2';
                description.textContent = ''; // 스키마에 설명이 없음

                fieldDiv.appendChild(label);
                fieldDiv.appendChild(description);

                // 스키마 타입 파싱
                const schemaType = schema.split('(')[0];
                const isOptional = schema.endsWith('?');

                // 입력 필드 생성
                let input;
                if (schemaType === 'bool') {
                    input = document.createElement('select');
                    input.className = 'form-select block w-full rounded-md border-gray-300';
                    
                    const trueOption = document.createElement('option');
                    trueOption.value = 'true';
                    trueOption.textContent = '예 (true)';
                    trueOption.selected = value === true;
                    
                    const falseOption = document.createElement('option');
                    falseOption.value = 'false';
                    falseOption.textContent = '아니오 (false)';
                    falseOption.selected = value === false;
                    
                    input.appendChild(trueOption);
                    input.appendChild(falseOption);
                } else if (schemaType === 'list') {
                    input = document.createElement('select');
                    input.className = 'form-select block w-full rounded-md border-gray-300';
                    // list(commax|custom) 형식에서 옵션 추출
                    const options = schema.split('(')[1].rstrip('?)').split('|');
                    options.forEach(option => {
                        const optionElement = document.createElement('option');
                        optionElement.value = option;
                        optionElement.textContent = option;
                        optionElement.selected = option === value;
                        input.appendChild(optionElement);
                    });
                } else if (schemaType === 'int' || schemaType === 'float') {
                    input = document.createElement('input');
                    input.type = 'number';
                    input.value = value;
                    input.className = 'form-input block w-full rounded-md border-gray-300';
                    if (schemaType === 'float') {
                        input.step = '0.1';
                    }
                } else {
                    input = document.createElement('input');
                    input.type = key.includes('password') ? 'password' : 'text';
                    input.value = value;
                    input.className = 'form-input block w-full rounded-md border-gray-300';
                }
                input.id = `config-${key}`;
                input.dataset.key = key;
                input.dataset.type = schemaType;
                if (!isOptional) {
                    input.required = true;
                    label.textContent += ' *';
                }

                fieldDiv.appendChild(input);
                configDiv.appendChild(fieldDiv);
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
        
        configData[key] = value;
    });

    showConfigMessage('설정을 저장하고 애드온을 재시작하는 중...', false);

    fetch('./api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showConfigMessage('설정이 저장되었습니다. 애드온이 재시작됩니다...', false);
            // MQTT 상태 업데이트
            setTimeout(updateMqttStatus, 1000);
        } else {
            let errorMessage = '설정 저장 실패: ' + (data.error || '알 수 없는 오류');
            if (data.details) {
                errorMessage += '\n' + data.details.join('\n');
            }
            showConfigMessage(errorMessage, true);
        }
    })
    .catch(error => {
        showConfigMessage('설정 저장 중 오류가 발생했습니다: ' + error, true);
    });
}

function showConfigMessage(message, isError) {
    const messageElement = document.getElementById('configMessage');
    messageElement.textContent = message;
    messageElement.className = `text-sm ${isError ? 'text-red-600' : 'text-green-600'}`;
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

// 실시간 패킷 로그 관련 함수들
function updateLivePacketLog() {
    fetch('./api/packet_logs')
        .then(response => response.json())
        .then(data => {
            const logDiv = document.getElementById('livePacketLog');
            let newContent = '';
            
            // 송신 패킷 처리
            data.send.forEach(packet => {
                const timestamp = new Date().toLocaleTimeString();
                newContent += createLivePacketLogEntry(packet, 'send', timestamp);
            });
            
            // 수신 패킷 처리
            data.recv.forEach(packet => {
                const timestamp = new Date().toLocaleTimeString();
                newContent += createLivePacketLogEntry(packet, 'recv', timestamp);
            });
            
            if (newContent) {
                logDiv.innerHTML = newContent + logDiv.innerHTML;
                // Unknown 패킷 숨기기 상태 적용
                updateLivePacketLogDisplay();
            }
        });
}

function createLivePacketLogEntry(packet, type, timestamp) {
    const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
    const deviceText = deviceInfo.device !== "Unknown" ? 
        `${deviceInfo.device} ${deviceInfo.packet_type}` : 
        "Unknown";
    
    const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
    
    return `
        <div class="p-2 border-b border-gray-200 hover:bg-gray-50 cursor-pointer ${deviceInfo.device === 'Unknown' ? 'opacity-70 unknown-packet' : ''}" onclick="handlePacketClick('${packet.packet}')">
            <div class="flex items-center justify-between">
                <span class="text-xs text-gray-500">${timestamp}</span>
                <span class="inline-block min-w-[50px] text-sm font-semibold ${type === 'send' ? 'text-green-600' : 'text-blue-600'}">[${type.toUpperCase()}]</span>
            </div>
            <div class="font-mono">${formattedPacket}</div>
            <div class="text-sm text-gray-600">[${deviceText}]</div>
        </div>`;
}

function clearLivePacketLog() {
    const logDiv = document.getElementById('livePacketLog');
    logDiv.innerHTML = '';
    liveLastPackets.clear();
}

function updateLivePacketLogDisplay() {
    const hideUnknown = document.getElementById('liveHideUnknown').checked;
    const unknownPackets = document.querySelectorAll('#livePacketLog .unknown-packet');
    
    unknownPackets.forEach(packet => {
        if (hideUnknown) {
            packet.classList.add('hidden');
        } else {
            packet.classList.remove('hidden');
        }
    });
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
document.addEventListener('DOMContentLoaded', function() {
    // 패킷 에디터 초기화
    loadCustomPacketStructure();
    checkVendorSetting();

    // 저장 버튼 이벤트 핸들러
    document.getElementById('savePacketStructure').addEventListener('click', saveCustomPacketStructure);
    
    // vendor 변경 버튼 이벤트 핸들러
    document.getElementById('changeVendorButton').addEventListener('click', changeVendorToCustom);
});

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

    // vendor 설정만 변경
    const configData = { vendor: 'custom' };

    showPacketEditorMessage('vendor 설정을 변경하고 애드온을 재시작하는 중...', false);

    fetch('./api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showPacketEditorMessage('vendor 설정이 custom으로 변경되었습니다. 애드온이 재시작됩니다...', false);
            document.getElementById('vendorWarning').classList.add('hidden');
            // 설정 페이지 업데이트
            setTimeout(loadConfig, 1000);
        } else {
            let errorMessage = 'vendor 설정 변경 실패: ' + (data.error || '알 수 없는 오류');
            if (data.details) {
                errorMessage += '\n' + data.details.join('\n');
            }
            showPacketEditorMessage(errorMessage, true);
        }
    })
    .catch(error => {
        showPacketEditorMessage('vendor 설정 변경 중 오류가 발생했습니다: ' + error, true);
    });
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
        
        // 기기 이름과 타입
        deviceSection.innerHTML = `
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-medium">${deviceName}</h3>
                <input type="text" value="${deviceData.type}" 
                    class="border rounded px-2 py-1 text-sm"
                    data-device="${deviceName}" data-field="type">
            </div>
        `;

        // 패킷 타입별 섹션 추가
        ['command', 'state', 'state_request', 'ack'].forEach(packetType => {
            if (deviceData[packetType]) {
                const packetSection = createPacketSection(deviceName, packetType, deviceData[packetType]);
                deviceSection.appendChild(packetSection);
            }
        });

        editorDiv.appendChild(deviceSection);
    }
}

function createPacketSection(deviceName, packetType, packetData) {
    const section = document.createElement('div');
    section.className = 'mt-4';

    const title = {
        'command': '명령 패킷',
        'state': '상태 패킷',
        'state_request': '상태 요청 패킷',
        'ack': '응답 패킷'
    }[packetType];

    section.innerHTML = `
        <h4 class="font-medium mb-2">${title}</h4>
        <div class="ml-4 space-y-2">
            <div class="flex items-center">
                <span class="w-20 text-sm">Header:</span>
                <input type="text" value="${packetData.header}" 
                    class="border rounded px-2 py-1 text-sm"
                    data-device="${deviceName}" 
                    data-packet-type="${packetType}" 
                    data-field="header">
            </div>
        </div>
    `;

    if (packetData.structure) {
        const structureDiv = document.createElement('div');
        structureDiv.className = 'ml-4 mt-2';
        
        Object.entries(packetData.structure).forEach(([position, field]) => {
            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'border-l-2 border-gray-200 pl-4 py-2 mt-2';
            fieldDiv.innerHTML = `
                <div class="text-sm font-medium">Position ${position}</div>
                <div class="grid grid-cols-2 gap-2 mt-1">
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

// 페이지 로드 완료 후 초기화 실행 및 주기적 업데이트 설정
document.addEventListener('DOMContentLoaded', function() {
    initialize();
    
    // 주기적 업데이트 설정
    setInterval(updateDeviceList, 30000);  // 30초마다 기기목록 업데이트
    setInterval(updatePacketLog, 1000);    // 1초마다 패킷 로그 업데이트
    setInterval(updateMqttStatus, 5000);   // 5초마다 MQTT 상태 업데이트
    setInterval(updateRecentMessages, 2000); // 2초마다 최근 메시지 업데이트
    setInterval(updateLivePacketLog, 1000);    // 1초마다 실시간 패킷 로그 업데이트
    
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
                
                // 예시 패킷 섹션 추가
                if (info.command?.examples?.length > 0 || 
                    info.state?.examples?.length > 0 || 
                    info.state_request?.examples?.length > 0 || 
                    info.ack?.examples?.length > 0) {
                    
                    const examplesDiv = document.createElement('div');
                    examplesDiv.className = 'mt-4 bg-gray-50 p-4 rounded';
                    
                    ['command', 'state', 'state_request', 'ack'].forEach(type => {
                        if (info[type]?.examples?.length > 0) {
                            const typeHeader = document.createElement('h4');
                            typeHeader.className = 'font-medium mb-2';
                            typeHeader.textContent = {
                                'command': '명령 패킷',
                                'state': '상태 패킷',
                                'state_request': '상태 요청 패킷',
                                'ack': '응답 패킷'
                            }[type];
                            examplesDiv.appendChild(typeHeader);
                            
                            info[type].examples.forEach(example => {
                                const exampleDiv = document.createElement('div');
                                exampleDiv.className = 'mb-2 pl-4';
                                const formattedPacket = example.packet.match(/.{2}/g).join(' ');
                                exampleDiv.innerHTML = `
                                    <code class="font-mono text-sm bg-gray-100 px-2 py-1 rounded">${formattedPacket}</code>
                                    <span class="text-sm text-gray-600 ml-2">${example.desc || ''}</span>
                                `;
                                examplesDiv.appendChild(exampleDiv);
                            });
                        }
                    });
                    
                    tabContent.appendChild(examplesDiv);
                }
                
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