// 전역 변수 선언
let lastPackets = new Set();
let packetSuggestions = null;
const HISTORY_KEY = 'packet_analysis_history';
const MAX_HISTORY = 20;

// 패킷 분석 함수
function analyzePacket() {
    const packetInput = document.getElementById('packetInput');
    const resultDiv = document.getElementById('packetResult');
    // 입력값에서 공백 제거
    const packet = packetInput.value.replace(/\s+/g, '').trim();
    
    if (!packet) {
        resultDiv.innerHTML = '<p class="error">패킷을 입력하세요.</p>';
        return;
    }
    
    if (!/^[0-9A-Fa-f]{14}$/.test(packet) && !/^[0-9A-Fa-f]{16}$/.test(packet)) {
        resultDiv.innerHTML = '<p class="error">패킷은 7바이트(14자리) 또는 8바이트(16자리)여야 합니다.</p>';
        return;
    }
    
    // 히스토리에 저장
    savePacketHistory(packet);
    
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
            let html = '<h3>분석 결과:</h3>';
            if (packetType === 'command') {
                html += `<p>패킷 타입: <strong>명령</strong></p>`;
            } else if (packetType === 'state') {
                html += `<p>패킷 타입: <strong>상태</strong></p>`;
            } else if (packetType === 'state_request') {
                html += `<p>패킷 타입: <strong>상태 요청</strong></p>`;
            } else if (packetType === 'ack') {
                html += `<p>패킷 타입: <strong>응답</strong></p>`;
            }
            html += `<p>기기: <strong>${data.device}</strong></p>`;
            
            if (data.checksum) {
                const formattedChecksum = data.checksum.match(/.{2}/g).join(' ');
                html += `<p>체크섬이 포함된 패킷: <strong class="byte-spaced" data-packet="${formattedChecksum}">&nbsp;</strong></p>`;
            } else {
                html += '<p class="error">체크섬 계산 실패</p>';
            }
            
            if (data.analysis && data.analysis.length > 0) {
                html += '<h4>바이트별 분석:</h4>';
                html += '<div style="font-family: monospace;">';
                data.analysis.forEach(desc => {
                    html += `<div>${desc}</div>`;
                });
                html += '</div>';
            }
            
            if (packetType === 'command' && data.expected_state) {
                const formattedExpectedPacket = data.expected_state.expected_packet.match(/.{2}/g).join(' ');
                html += `<h4>예상되는 상태 패킷:</h4>`;
                html += `<p><strong><a href="#" onclick="analyzeExpectedState('${data.expected_state.expected_packet}')" style="color: #2196F3; text-decoration: none;" class="byte-spaced" data-packet="${formattedExpectedPacket}">&nbsp;</a></strong></p>`;
                html += `<p>필수 바이트 위치: ${data.expected_state.required_bytes.join(', ')}</p>`;
                
                if (data.expected_state.analysis && data.expected_state.analysis.length > 0) {
                    html += '<h4>예상 패킷 바이트별 분석:</h4>';
                    html += '<div style="font-family: monospace;">';
                    data.expected_state.analysis.forEach(desc => {
                        html += `<div>${desc}</div>`;
                    });
                    html += '</div>';
                }
            }
            
            resultDiv.innerHTML = html;
        } else {
            resultDiv.innerHTML = `<p class="error">오류: ${data.error}</p>`;
        }
    })
    .catch(error => {
        resultDiv.innerHTML = `<p class="error">요청 실패: ${error}</p>`;
    });
}

// 패킷 로그 업데이트
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
                newContent += createPacketLogEntry(timestamp, packet, 'send');
                lastPackets.add('send:' + packet.packet);
            });
            
            // 수신 패킷 처리
            const newRecvPackets = data.recv.filter(packet => !lastPackets.has('recv:' + packet.packet));
            newRecvPackets.forEach(packet => {
                const timestamp = new Date().toLocaleTimeString();
                newContent += createPacketLogEntry(timestamp, packet, 'recv');
                lastPackets.add('recv:' + packet.packet);
            });
            
            if (newContent) {
                logDiv.innerHTML = newContent + logDiv.innerHTML;
            }
        });
}

function createPacketLogEntry(timestamp, packet, type) {
    // 패킷 정보에서 첫 번째 결과 사용 (없는 경우 Unknown으로 처리)
    const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
    const deviceText = deviceInfo.device !== "Unknown" ? 
        `${deviceInfo.device} ${deviceInfo.packet_type}` : 
        "Unknown";
    
    // 패킷을 2자리씩 분할
    const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
    
    return `
        <div class="packet-log-entry ${type} ${deviceInfo.device === 'Unknown' ? 'unknown-packet' : ''}" onclick="handlePacketClick('${packet.packet}')">
            <span class="timestamp">${timestamp}</span>
            <span class="packet-type-label">[${type.toUpperCase()}]</span>
            <span class="packet" data-packet="${formattedPacket}">&nbsp;</span>
            <span class="device-label">[${deviceText}]</span>
        </div>`;
}

function handlePacketClick(packet, type) {
    document.getElementById('packetInput').value = packet;
    analyzePacket();
}

// 패킷 구조 정보 로드
function loadPacketStructures() {
    fetch('./api/packet_structures')
        .then(response => response.json())
        .then(structures => {
            const tabButtons = document.getElementById('deviceTabs');
            const tabContents = document.getElementById('tabContents');
            tabButtons.innerHTML = '';
            tabContents.innerHTML = '';
            
            let isFirst = true;
            
            for (const [deviceName, info] of Object.entries(structures)) {
                // 탭 버튼 추가
                const button = document.createElement('button');
                button.className = `tablinks ${isFirst ? 'active' : ''}`;
                button.onclick = function(evt) { openDeviceTab(evt, deviceName); };
                button.textContent = deviceName;
                tabButtons.appendChild(button);
                
                // 탭 내용 추가
                const tabContent = document.createElement('div');
                tabContent.id = deviceName;
                tabContent.className = 'tab-content';
                tabContent.style.display = isFirst ? 'block' : 'none';
                tabContent.innerHTML = `
                    <h3>${deviceName} (${info.type})</h3>
                    <table class="packet-reference-table">
                        <tr>
                            <th colspan="2">명령 패킷</th>
                        </tr>
                        <tr>
                            <td>
                                <div style="font-family: monospace;">
                                    ${info.command.byte_desc.map(desc => `<div>${desc}</div>`).join('')}
                                </div>
                            </td>
                            <td>
                                ${info.command.examples.map(ex => {
                                    const formattedPacket = ex.packet.match(/.{2}/g).join(' ');
                                    return `
                                        <div style="margin-bottom: 10px;">
                                            <code class="byte-spaced" data-packet="${formattedPacket}">&nbsp;</code><br>
                                            <small>${ex.desc}</small>
                                        </div>
                                    `;
                                }).join('')}
                            </td>
                        </tr>
                        <tr>
                            <th colspan="2">상태 패킷</th>
                        </tr>
                        <tr>
                            <td>
                                <div style="font-family: monospace;">
                                    ${info.state.byte_desc.map(desc => `<div>${desc}</div>`).join('')}
                                </div>
                            </td>
                            <td>
                                ${info.state.examples.map(ex => {
                                    const formattedPacket = ex.packet.match(/.{2}/g).join(' ');
                                    return `
                                        <div style="margin-bottom: 10px;">
                                            <code class="byte-spaced" data-packet="${formattedPacket}">&nbsp;</code><br>
                                            <small>${ex.desc}</small>
                                        </div>
                                    `;
                                }).join('')}
                            </td>
                        </tr>
                        ${info.state_request ? `
                        <tr>
                            <th colspan="2">상태 요청 패킷</th>
                        </tr>
                        <tr>
                            <td>
                                <div style="font-family: monospace;">
                                    ${info.state_request.byte_desc.map(desc => `<div>${desc}</div>`).join('')}
                                </div>
                            </td>
                            <td>
                                ${info.state_request.examples.map(ex => {
                                    const formattedPacket = ex.packet.match(/.{2}/g).join(' ');
                                    return `
                                        <div style="margin-bottom: 10px;">
                                            <code class="byte-spaced" data-packet="${formattedPacket}">&nbsp;</code><br>
                                            <small>${ex.desc}</small>
                                        </div>
                                    `;
                                }).join('')}
                            </td>
                        </tr>
                        ` : ''}
                        ${info.ack ? `
                        <tr>
                            <th colspan="2">응답 패킷</th>
                        </tr>
                        <tr>
                            <td>
                                <div style="font-family: monospace;">
                                    ${info.ack.byte_desc.map(desc => `<div>${desc}</div>`).join('')}
                                </div>
                            </td>
                            <td>
                                ${info.ack.examples.map(ex => {
                                    const formattedPacket = ex.packet.match(/.{2}/g).join(' ');
                                    return `
                                        <div style="margin-bottom: 10px;">
                                            <code class="byte-spaced" data-packet="${formattedPacket}">&nbsp;</code><br>
                                            <small>${ex.desc}</small>
                                        </div>
                                    `;
                                }).join('')}
                            </td>
                        </tr>
                        ` : ''}
                    </table>
                `;
                tabContents.appendChild(tabContent);
                
                isFirst = false;
            }
        })
        .catch(error => {
            console.error('패킷 구조 로드 실패:', error);
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
    updateHistorySelect();
}

function updateHistorySelect() {
    const history = loadPacketHistory();
    const select = document.getElementById('packetHistory');
    
    // 옵션 제거 (첫 번째 옵션 제외)
    while (select.options.length > 1) {
        select.remove(1);
    }
    
    // 히스토리 옵션 추가
    history.forEach(packet => {
        const formattedPacket = packet.match(/.{2}/g).join(' ');
        const option = document.createElement('option');
        option.value = packet;
        option.setAttribute('data-packet', formattedPacket);
        option.className = 'byte-spaced';
        option.innerHTML = '&nbsp;';
        select.appendChild(option);
    });
}

function loadPacketFromHistory() {
    const select = document.getElementById('packetHistory');
    const packet = select.value;
    if (packet) {
        document.getElementById('packetInput').value = packet;
        analyzePacket();
        select.selectedIndex = 0;  // 선택 초기화
    }
}

// Enter 키 입력 처리
document.getElementById('packetInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        analyzePacket();
    }
});

function updateDeviceList() {
    fetch('./api/devices')
        .then(response => response.json())
        .then(devices => {
            const deviceList = document.getElementById('deviceList');
            deviceList.innerHTML = '';
            
            for (const [deviceName, info] of Object.entries(devices)) {
                const card = document.createElement('div');
                card.className = 'device-card';
                card.innerHTML = `
                    <h3>${deviceName}</h3>
                    <p>타입: ${info.type}</p>
                    <p>개수: ${info.count}</p>
                `;
                deviceList.appendChild(card);
            }
        });
}

function findDevices() {
    fetch('./api/find_devices', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            updateDeviceList();
        }
    });
}

// 초기화 함수
function initialize() {
    initializePacketBuilder();  // 패킷 빌더 초기화 (packetSuggestions 설정)
    updateHistorySelect();      // 히스토리 로드
    updateDeviceList();         // 기기 목록 로드
    updatePacketLog();          // 패킷 로그 초기 로드
    loadPacketStructures();     // 패킷 구조 정보 로드
}

// 페이지 로드 완료 후 초기화 실행 및 주기적 업데이트 설정
document.addEventListener('DOMContentLoaded', function() {
    initialize(); // 초기화 함수 호출

    // 주기적 업데이트 설정
    setInterval(updateDeviceList, 30000);  // 30초마다 상태 업데이트
    setInterval(updatePacketLog, 1000);    // 1초마다 패킷 로그 업데이트

    // 패킷 입력 필요 이벤트 리스너
    const packetInput = document.getElementById('packetInput');
    if (packetInput) {
        packetInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                analyzePacket();
            }
        });
    }
});

// 패킷 로그 지우기
function clearPacketLog() {
    const logDiv = document.getElementById('packetLog');
    logDiv.innerHTML = '';
    lastPackets.clear();
}

// 접 수 있는 참조 자료 섹션 기능
var coll = document.getElementsByClassName("collapsible");
for (var i = 0; i < coll.length; i++) {
    coll[i].addEventListener("click", function() {
        this.classList.toggle("active");
        var content = this.nextElementSibling;
        if (content.style.display === "block") {
            content.style.display = "none";
        } else {
            content.style.display = "block";
        }
    });
}

function openDeviceTab(evt, deviceName) {
    var i, tabcontent, tablinks;
    
    // 모든 탭 내용 숨기기
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    
    // 모든 탭 버튼 비활성화
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    
    // 선택된 탭 내용 표시 및 버튼 활성화
    document.getElementById(deviceName).style.display = "block";
    evt.currentTarget.className += " active";
}

function analyzeExpectedState(packet) {
    document.getElementById('packetInput').value = packet;
    analyzePacket();
}

// 패킷 로그 표시 업데이트
function updatePacketLogDisplay() {
    const hideUnknown = document.getElementById('hideUnknown').checked;
    const unknownPackets = document.querySelectorAll('.unknown-packet');
    
    unknownPackets.forEach(packet => {
        packet.style.display = hideUnknown ? 'none' : '';
    });
}

// 패킷 입력 도우미 초기화
function initializePacketBuilder() {
    fetch('./api/packet_suggestions')
        .then(response => response.json())
        .then(data => {
            packetSuggestions = data;

            // 모든 헤더 옵션 추가
            const headerSelect = document.getElementById('packetHeaderSelect');
            headerSelect.innerHTML = '<option value="">헤더 선택...</option>'; // 기존 옵션 제거

            // 명령 패킷 헤더
            const commandGroup = document.createElement('optgroup');
            commandGroup.label = '명령 패킷';
            data.headers.command.forEach(header => {
                const option = document.createElement('option');
                option.value = `command:${header.header}`;
                option.textContent = `${header.device} (${header.header})`;
                commandGroup.appendChild(option);
            });

            // 상태 패킷 헤더
            const stateGroup = document.createElement('optgroup');
            stateGroup.label = '상태 패킷';
            data.headers.state.forEach(header => {
                const option = document.createElement('option');
                option.value = `state:${header.header}`;
                option.textContent = `${header.device} (${header.header})`;
                stateGroup.appendChild(option);
            });
            
            // 상태 요청 패킷 헤더
            const stateRequestGroup = document.createElement('optgroup');
            stateRequestGroup.label = '상태 요청 패킷';
            data.headers.state_request.forEach(header => {
                const option = document.createElement('option');
                option.value = `state_request:${header.header}`;
                option.textContent = `${header.device} (${header.header})`;
                stateRequestGroup.appendChild(option);
            });
            
            // 응답 패킷 헤더
            const ackGroup = document.createElement('optgroup');
            ackGroup.label = '응답 패킷';
            data.headers.ack.forEach(header => {
                const option = document.createElement('option');
                option.value = `ack:${header.header}`;
                option.textContent = `${header.device} (${header.header})`;
                ackGroup.appendChild(option);
            });

            // 헤더 선택 엘리먼트에 그룹 추가 (한 번만)
            headerSelect.appendChild(commandGroup);
            headerSelect.appendChild(stateGroup);
            headerSelect.appendChild(stateRequestGroup);
            headerSelect.appendChild(ackGroup);
        });
}

function handleHeaderSelect() {
    const headerSelect = document.getElementById('packetHeaderSelect');
    const byteInputsDiv = document.getElementById('packetByteInputs');
    const packetInput = document.getElementById('packetInput');
    
    const selectedValue = headerSelect.value;
    if (!selectedValue) {
        byteInputsDiv.innerHTML = '';
        return;
    }
    
    const [type, header] = selectedValue.split(':');
    
    // 선택된 헤더에 해당하는 기기 찾기
    const deviceInfo = packetSuggestions.headers[type].find(h => h.header === header);
    if (!deviceInfo) return;
    
    const deviceKey = `${deviceInfo.device}_${type}`;
    
    // 바이트 입력 필드 생성 (7바이트)
    let html = '';
    for (let i = 1; i < 7; i++) {
        const byteInfo = packetSuggestions.values[deviceKey]?.[i];
        if (byteInfo) {
            html += `
                <div class="byte-input">
                    <label class="byte-label">Byte ${i}: ${byteInfo.name}</label>
                    <select onchange="updatePacket()" data-byte="${i}">
                        <option value="">선택...</option>
                        ${Object.entries(byteInfo.values).map(([key, value]) => 
                            `<option value="${value}">${key} (${value})</option>`
                        ).join('')}
                    </select>
                </div>`;
        } else {
            html += `
                <div class="byte-input">
                    <label class="byte-label">Byte ${i}</label>
                    <input type="text" maxlength="2" pattern="[0-9A-Fa-f]{2}" 
                           onchange="updatePacket()" data-byte="${i}"
                           placeholder="00">
                </div>`;
        }
    }
    byteInputsDiv.innerHTML = html;
    
    // 패킷 초기값 설정
    updatePacket();
}

function updatePacket() {
    const byteInputsDiv = document.getElementById('packetByteInputs');
    const packetInput = document.getElementById('packetInput');
    const headerSelect = document.getElementById('packetHeaderSelect');
    
    const [type, header] = headerSelect.value.split(':');
    let packet = header;  // 헤더로 시작
    
    // 각 바이트 값 수집 (7바이트)
    for (let i = 1; i < 7; i++) {
        const input = byteInputsDiv.querySelector(`[data-byte="${i}"]`);
        if (input) {
            let value = input.value || '00';
            if (value.length === 1) value = '0' + value;
            packet += value;
        } else {
            packet += '00';
        }
    }
    
    packetInput.value = packet;
} 