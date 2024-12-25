// @ts-nocheck
// 전역 변수 선언
let lastPackets = new Set();
let packetSuggestions = null;
const HISTORY_KEY = 'packet_analysis_history';
const MAX_HISTORY = 20;
let historyIndex = -1;  // 히스토리 인덱스 추가
let currentInput = '';   // 현재 입력값 저장용 변수 추가

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
                // 새 내용이 추가된 후 Unknown 패킷 숨기기 상태 적용
                const hideUnknown = document.getElementById('hideUnknown').checked;
                if (hideUnknown) {
                    const unknownPackets = logDiv.querySelectorAll('.unknown-packet');
                    unknownPackets.forEach(packet => {
                        packet.classList.add('hidden');
                    });
                }
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
    headers.forEach((header, index) => {
        const th = document.createElement('th');
        th.className = 'px-4 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ' + 
            (index === 0 ? 'w-[10%]' : 'w-[22.5%]');
        th.textContent = header;
        headerRow.appendChild(th);
    });
    table.appendChild(headerRow);
    
    for (let byte = 0; byte < 8; byte++) {
        const row = document.createElement('tr');
        row.className = byte % 2 === 0 ? 'bg-white' : 'bg-gray-50';
        
        const byteCell = document.createElement('td');
        byteCell.className = 'px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 w-[10%]';
        byteCell.textContent = `Byte ${byte}`;
        row.appendChild(byteCell);
        
        const types = ['command', 'ack', 'state_request', 'state'];
        types.forEach(type => {
            const td = document.createElement('td');
            td.className = 'px-4 py-3 text-sm text-gray-500 w-[22.5%]';
            
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
            const configDiv = document.getElementById('configDisplay');
            configDiv.innerHTML = Object.entries(data).map(([key, value]) => `
                <div class="border-b border-gray-200 pb-4">
                    <div class="font-medium text-gray-700">${key}</div>
                    <div class="mt-1 text-sm text-gray-500">${JSON.stringify(value)}</div>
                </div>
            `).join('');
        });
}

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

// 페이지 로드 완료 후 초기화 실행 및 주기적 업데이트 설정
document.addEventListener('DOMContentLoaded', function() {
    initialize();
    
    // 주기적 업데이트 설정
    setInterval(updateDeviceList, 30000);  // 30초마다 기기목록 업데이트
    setInterval(updatePacketLog, 1000);    // 1초마다 패킷 로그 업데이트
    setInterval(updateMqttStatus, 5000);   // 5초마다 MQTT 상태 업데이트
    setInterval(updateRecentMessages, 2000); // 2초마다 최근 메시지 업데이트
    
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