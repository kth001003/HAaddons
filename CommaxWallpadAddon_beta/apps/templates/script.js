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
// 대시보드 관련 클래스
// ===============================
class Dashboard {
    constructor() {
        this.initializeIntervals();
        this.bindEvents();
    }

    initializeIntervals() {
        // 주기적 업데이트 설정
        setInterval(() => this.updateMqttStatus(), 5000);   // 5초마다 MQTT 상태 업데이트
        setInterval(() => this.updateEW11Status(), 5000);   // 5초마다 EW11 상태 업데이트
        setInterval(() => this.updateRecentMessages(), 2000); // 2초마다 최근 메시지 업데이트
        setInterval(() => this.updateDeviceList(), 10000);  // 10초마다 기기목록 업데이트
    }

    bindEvents() {
        // 기기 새로고침 버튼 이벤트 바인딩
        const refreshButton = document.getElementById('refreshDevicesButton');
        if (refreshButton) {
            refreshButton.addEventListener('click', () => this.refreshDevices());
        }
    }

    refreshDevices() {
        if (!confirm('기기를 다시 검색하기 위해 애드온을 재시작합니다. 재시작 후 30초정도 후에 기기가 검색됩니다. 계속하시겠습니까?')) {
            return;
        }
    
        fetch('./api/find_devices', {
            method: 'POST'
        });
    }
    
    updateDeviceList() {
        fetch('./api/devices')
            .then(response => response.json())
            .then(data => {
                const deviceListDiv = document.getElementById('deviceList');
                if (!deviceListDiv) return;
    
                let html = '';
                for (const [deviceName, info] of Object.entries(data)) {
                    html += `
                        <div class="mb-2 p-3 bg-gray-50 dark:bg-gray-800 rounded">
                            <div class="flex justify-between">
                                <h3 class="dark:text-gray-300">${deviceName}</h3>
                                <span class="text-sm text-gray-500">${info.type}</span>
                            </div>
                            <div class="text-sm text-gray-600">개수: ${info.count}개</div>
                        </div>
                    `;
                }
                deviceListDiv.innerHTML = html || '<p class="text-gray-500 dark:text-gray-400">연결된 기기가 없습니다.</p>';
            })
            .catch(error => console.error('기기 목록 업데이트 실패:', error));
    }
    
    updateMqttStatus() {
        fetch('./api/mqtt_status')
            .then(response => response.json())
            .then(data => {
                const statusElement = document.getElementById('connectionStatus');
                statusElement.textContent = data.connected ? '연결됨' : '연결 끊김';
                statusElement.className = data.connected ? 
                    'px-2 py-1 rounded text-sm bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-100' : 
                    'px-2 py-1 rounded text-sm bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-100';
                
                document.getElementById('brokerInfo').textContent = data.broker || '-';
                document.getElementById('clientId').textContent = data.client_id || '-';
                
                // 구독 중인 토픽 표시
                const topicsContainer = document.getElementById('subscribedTopicsWithMessages');
                topicsContainer.innerHTML = ''; // 컨테이너 초기화
                if (!data.subscribed_topics || data.subscribed_topics.length === 0) {
                    topicsContainer.innerHTML = `
                        <div class="text-center text-gray-500 py-4">
                            <p>구독 중인 채널이 없습니다.</p>
                        </div>
                    `;
                    return;
                }
                const subscribedTopicsDiv = document.getElementById('subscribedTopics');
                subscribedTopicsDiv.innerHTML = data.subscribed_topics.join(', ');
                // 기존에 없는 토픽에 대한 div 추가
                data.subscribed_topics.forEach(topic => {
                    // 특수문자를 안전하게 처리하도록 수정
                    const topicId = `topic-${topic.replace(/[^a-zA-Z0-9]/g, function(match) {
                        // '/'와 '+' 문자를 각각 다르게 처리
                        if (match === '/') return '-';
                        if (match === '+') return 'plus';
                        return '';
                    })}`;
                    
                    // 기존 div가 없는 경우에만 새로 생성
                    if (!document.getElementById(topicId)) {
                        const topicDiv = document.createElement('div');
                        topicDiv.id = topicId;
                        topicDiv.className = 'bg-gray-50 dark:bg-gray-800 p-2 rounded mb-1';
                        topicDiv.innerHTML = `
                            <div class="flex justify-between items-center">
                                <div class="flex items-center gap-2">
                                    <span class="font-medium text-gray-700 dark:text-gray-300">${topic}</span>
                                    <pre class="text-xs text-gray-600 dark:text-gray-400">메시지 없음</pre>
                                </div>
                                <span class="text-xs text-gray-500 dark:text-gray-400">-</span>
                            </div>
                        `;
                        topicsContainer.appendChild(topicDiv);
                    } else {
                        // 기존 div가 있는 경우 토픽 이름만 업데이트
                        const existingDiv = document.getElementById(topicId);
                        const topicSpan = existingDiv.querySelector('.font-medium');
                        if (topicSpan) {
                            topicSpan.textContent = topic;
                        }
                    }
                });
    
                // 더 이상 구독하지 않는 토픽의 div 제거
                const existingTopicDivs = topicsContainer.querySelectorAll('[id^="topic-"]');
                existingTopicDivs.forEach(div => {
                    // ID를 토픽으로 변환할 때도 동일한 규칙 적용
                    const topicFromId = div.id.replace('topic-', '')
                        .replace(/-/g, '/')
                        .replace(/plus/g, '+');
                    if (!data.subscribed_topics.includes(topicFromId)) {
                        div.remove();
                    }
                });
            });
    }

    updateRecentMessages() {
        fetch('./api/recent_messages')
            .then(response => response.json())
            .then(data => {
                if (!data.messages || data.messages.length === 0) return;
    
                // 토픽별로 메시지 그룹화
                const messagesByTopic = {};
                data.messages.forEach(msg => {
                    messagesByTopic[msg.topic] = msg;
                });
    
                // 각 토픽의 div 업데이트
                Object.entries(messagesByTopic).forEach(([topic, msg]) => {
                    // 와일드카드 토픽 매칭을 위한 함수
                    function matchTopic(pattern, topic) {
                        const patternParts = pattern.split('/');
                        const topicParts = topic.split('/');
                        
                        if (patternParts.length !== topicParts.length) return false;
                        
                        return patternParts.every((part, i) => 
                            part === '+' || part === topicParts[i]
                        );
                    }
    
                    // 모든 구독 중인 토픽에 대해 매칭 확인
                    document.querySelectorAll('[id^="topic-"]').forEach(topicDiv => {
                        const subscribedTopic = topicDiv.id
                            .replace('topic-', '')
                            .replace(/-/g, '/')
                            .replace(/plus/g, '+');
                        
                        if (matchTopic(subscribedTopic, topic)) {
                            const timestamp = topicDiv.querySelector('span:last-child');
                            const payload = topicDiv.querySelector('pre');
                            if (timestamp && payload) {
                                timestamp.textContent = msg.timestamp;
                                payload.textContent = msg.payload;
                            }
                        }
                    });
                });
            });
    }
    
    updateEW11Status() {
        fetch('./api/ew11_status')
            .then(response => response.json())
            .then(data => {
                const statusElement = document.getElementById('ew11ConnectionStatus');
                const lastResponseElement = document.getElementById('ew11LastResponse');
                
                if (!data.last_recv_time) {
                    statusElement.textContent = '응답 없음';
                    statusElement.className = 'px-2 py-1 rounded text-sm bg-red-100 text-red-800';
                    lastResponseElement.textContent = '응답 기록 없음';
                    return;
                }
                
                const currentTime = Math.floor(Date.now() / 1000); // 현재 시간을 초 단위로 변환
                const lastRecvTime = Math.floor(data.last_recv_time / 1000000000); // 나노초를 초 단위로 변환
                const timeDiff = currentTime - lastRecvTime;
                
                const isConnected = timeDiff <= data.elfin_reboot_interval;
                
                // 연결 상태 업데이트
                statusElement.textContent = isConnected ? '응답 있음' : '응답 없음';
                statusElement.className = `px-2 py-1 rounded text-sm ${isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`;
                
                // 마지막 응답 시간 업데이트 (초 단위)
                lastResponseElement.textContent = `${timeDiff}초 전`;
            })
            .catch(error => {
                console.error('EW11 상태 업데이트 실패:', error);
                const statusElement = document.getElementById('ew11ConnectionStatus');
                statusElement.textContent = '상태 확인 실패';
                statusElement.className = 'px-2 py-1 rounded text-sm bg-yellow-100 text-yellow-800';
            });
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
                    <div class="mb-2 p-3 bg-gray-50 dark:bg-gray-800 rounded">
                        <div class="flex justify-between">
                            <h3 class="dark:text-gray-300">${deviceName}</h3>
                            <span class="text-sm text-gray-500">${info.type}</span>
                        </div>
                        <div class="text-sm text-gray-600">개수: ${info.count}개</div>
                    </div>
                `;
            }
            deviceListDiv.innerHTML = html || '<p class="text-gray-500 dark:text-gray-400">연결된 기기가 없습니다.</p>';
        })
        .catch(error => console.error('기기 목록 업데이트 실패:', error));
}
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
            link.classList.add('border-indigo-500', 'text-gray-900', 'dark:text-white');
            link.classList.remove('border-transparent', 'text-gray-500', 'dark:text-gray-400');
        } else {
            link.classList.remove('border-indigo-500', 'text-gray-900', 'dark:text-white');
            link.classList.add('border-transparent', 'text-gray-500', 'dark:text-gray-400');
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
// 모바일 메뉴 토글 함수
function toggleMobileMenu() {
    const mobileMenu = document.getElementById('mobileMenu');
    if (mobileMenu.classList.contains('hidden')) {
        mobileMenu.classList.remove('hidden');
    } else {
        mobileMenu.classList.add('hidden');
    }
}

// ===============================
// 패킷 히스토리 관련 함수
// ===============================
const packetHistory = {
    load: () => {
        try {
            return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        } catch {
            return [];
        }
    },

    save: (packet) => {
        if (!packet) return;
        
        let history = packetHistory.load();
        history = history.filter(p => p !== packet); // 중복 제거
        history.unshift(packet); // 새 패킷을 앞에 추가
        
        // 최대 개수 유지
        if (history.length > MAX_HISTORY) {
            history = history.slice(0, MAX_HISTORY);
        }
        
        localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        historyIndex = -1; // 히스토리 인덱스 초기화
        
        // 드롭다운 목록 업데이트
        const historySelect = document.getElementById('packetHistory');
        if (historySelect) {
            historySelect.innerHTML = '<option value="">패킷 기록...</option>' +
                history.map(p => `<option value="${p}">${utils.formatPacket(p)}</option>`).join('');
        }
    },

    select: () => {
        const historySelect = document.getElementById('packetHistory');
        const packetInput = document.getElementById('packetInput');
        if (historySelect && historySelect.value) {
            packetInput.value = utils.formatPacket(historySelect.value);
            analyzePacket();
        }
    }
};

// ===============================
// 패킷 분석기 관련 함수
// ===============================
const utils = {
    formatPacket: packet => packet.match(/.{2}/g).join(' '),
    isValidPacket: packet => /^[0-9A-F]{14}$|^[0-9A-F]{16}$/.test(packet),
    getTimestamp: () => new Date().toLocaleTimeString('ko-KR', { hour12: false }),
    cleanPacket: input => input.replace(/[\s-]+/g, '').trim().toUpperCase(),
    isValidHex: packet => /^[0-9A-F]*$/.test(packet),
    padPacket: packet => packet.padEnd(14, '0'),
    validatePacket: (packet) => {
        if (!packet) return { isValid: false };
        if (!utils.isValidHex(packet)) {
            return {
                isValid: false,
                error: "잘못된 문자가 포함되어 있습니다. 16진수만 입력해주세요."
            };
        }
        if (!utils.isValidPacket(packet)) {
            if (packet.length >= 2 && packet.length < 14) {
                return {
                    isValid: false,
                    shouldPad: true
                };
            }
            return {
                isValid: false,
                error: "패킷은 14자리 또는 16자리여야 합니다."
            };
        }
        return { isValid: true };
    }
};

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


function showAvailableHeaders() {
    if (!packetSuggestions) return;
    const resultDiv = document.getElementById('packetResult');
    let html = '<h3 class="text-lg font-bold mb-2 dark:text-white">사용 가능한 헤더:</h3>';
    html += '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">';
    
    // 명령 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600 dark:text-gray-400">명령 패킷</h4>';
    packetSuggestions.headers.command.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 dark:bg-gray-700 px-1 dark:text-gray-300">${header.header}</span> - <span class="dark:text-gray-400">${header.device}</span></div>`;
    });
    html += '</div>';
    
    // 상태 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600 dark:text-gray-400">상태 패킷</h4>';
    packetSuggestions.headers.state.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 dark:bg-gray-700 px-1 dark:text-gray-300">${header.header}</span> - <span class="dark:text-gray-400">${header.device}</span></div>`;
    });
    html += '</div>';
    
    // 상태 요청 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600 dark:text-gray-400">상태 요청 패킷</h4>';
    packetSuggestions.headers.state_request.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 dark:bg-gray-700 px-1 dark:text-gray-300">${header.header}</span> - <span class="dark:text-gray-400">${header.device}</span></div>`;
    });
    html += '</div>';
    
    // 응답 패킷 헤더
    html += '<div class="space-y-2">';
    html += '<h4 class="font-bold text-sm text-gray-600 dark:text-gray-400">응답 패킷</h4>';
    packetSuggestions.headers.ack.forEach(header => {
        html += `<div class="text-sm"><span class="font-mono bg-gray-100 dark:bg-gray-700 px-1 dark:text-gray-300">${header.header}</span> - <span class="dark:text-gray-400">${header.device}</span></div>`;
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


function displayPacketAnalysis(results) {
    const resultDiv = document.getElementById('packetResult');
    if (!results.length) {
        resultDiv.innerHTML = `<div class="text-red-500 dark:text-red-400">매칭되는 패킷 구조를 찾을 수 없습니다.</div>`;
        return;
    }

    resultDiv.innerHTML = results.map(result => `
        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-4">
            <div class="flex justify-between items-center mb-2">
                <h3 class="text-lg font-medium dark:text-white">${result.device}</h3>
                <span class="text-sm text-gray-500 dark:text-gray-400">${result.packet_type}</span>
            </div>
            ${Object.entries(result.byte_meanings || {}).map(([byte, meaning]) => `
                <div class="mb-2">
                    <span class="font-medium dark:text-gray-300">Byte ${byte}:</span>
                    <span class="ml-2 dark:text-gray-400">${meaning}</span>
                </div>
            `).join('')}
            ${result.checksum ? `
                <div class="mt-4 text-sm text-gray-600 dark:text-gray-400">
                    <span class="font-medium dark:text-gray-300">체크섬:</span>
                    <span class="ml-2">${result.checksum}</span>
                </div>
            ` : ''}
            ${result.expected_state ? `
                <div class="mt-4 border-t pt-4 dark:border-gray-700">
                    <h4 class="text-md font-medium mb-2 dark:text-white">예상 상태 패킷</h4>
                    <div class="space-y-2">
                        ${result.expected_state.required_bytes ? `
                            <div class="text-sm">
                                <span class="font-medium dark:text-gray-300">필수 바이트:</span>
                                <span class="ml-2 font-mono dark:text-gray-400">${result.expected_state.required_bytes}</span>
                            </div>
                        ` : ''}
                        ${result.expected_state.possible_values ? `
                            <div class="text-sm">
                                <span class="font-medium dark:text-gray-300">가능한 값:</span>
                                <div class="ml-4 space-y-1">
                                    ${Object.entries(result.expected_state.possible_values).map(([key, value]) => `
                                        <div class="dark:text-gray-400">
                                            <span class="font-mono">${key}</span>: ${value}
                                            <button onclick="analyzeExpectedState('${key}')" 
                                                    class="ml-2 text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
                                                분석
                                            </button>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            ` : ''}
        </div>
    `).join('');
}
function analyzePacket(paddedPacket) {
    const packetInput = document.getElementById('packetInput');
    const resultDiv = document.getElementById('packetResult');
    
    // 입력값 정리
    const packet = utils.cleanPacket(paddedPacket || packetInput.value);
    
    if (!packet) {
        showAvailableHeaders();
        return;
    }
    
    // 패킷 유효성 검사
    const validation = utils.validatePacket(packet);
    if (!validation.isValid) {
        if (validation.shouldPad && !paddedPacket) {
            analyzePacket(utils.padPacket(packet));
            return;
        }
        if (validation.error) {
            resultDiv.innerHTML = `<p class="text-red-500 dark:text-red-400">${validation.error}</p>`;
            return;
        }
        return;
    }
    
    // Enter 키로 분석한 경우에만 히스토리에 저장
    if (!paddedPacket) {
        packetHistory.save(packet);
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
            displayPacketAnalysis([{
                device: data.device,
                packet_type: PACKET_TYPES[data.packet_type || 'command'],
                byte_meanings: data.analysis.reduce((acc, desc) => {
                    const match = desc.match(/Byte (\d+): (.+)/);
                    if (match) {
                        const [, byteNum, description] = match;
                        if (byteNum === '0' && description.startsWith('header')) {
                            acc[byteNum] = description;
                        } 
                        else if (description.includes('체크섬')) {
                            acc[byteNum] = description;
                        }
                        else {
                            const [name, value] = description.split(' = ');
                            if (value) {
                                acc[byteNum] = `${name} = ${value}`;
                            } else {
                                acc[byteNum] = description;
                            }
                        }
                    }
                    return acc;
                }, {}),
                checksum: data.checksum,
                expected_state: data.expected_state
            }]);
        } else {
            resultDiv.innerHTML = `<p class="text-red-500 dark:text-red-400">오류: ${data.error}</p>`;
        }
    })
    .catch(error => {
        resultDiv.innerHTML = `<p class="text-red-500 dark:text-red-400">요청 실패: ${error}</p>`;
    });
}

// 분석 버튼 클릭 이벤트 리스너
document.getElementById('analyzePacketButton').addEventListener('click', function() {
    analyzePacket();
});

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
document.getElementById('sendPacketButton').addEventListener('click', function() {
    sendPacket();
});
// 패킷 입력 필드 이벤트 리스너 설정
const packetInput = document.getElementById('packetInput');
if (packetInput) {
    packetInput.addEventListener('input', handlePacketInput);
    packetInput.addEventListener('keydown', function(e) {
        const history = packetHistory.load();
        
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



// ===============================
// 패킷 로그 관련 함수 (실시간, 플레이그라운드)
// ===============================

function updatePacketDisplay(isLive = false) {
    const elements = document.getElementsByClassName(isLive ? 'live-unknown-packet' : 'unknown-packet');
    const displayStyle = document.getElementById(isLive ? 'hideUnknownLive' : 'hideUnknown').checked ? 'none' : '';
    
    Array.from(elements).forEach(el => el.style.display = displayStyle);
}

function createPacketLogEntry(packet, type) {
    const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
    const deviceClass = deviceInfo.device === 'Unknown' ? 'unknown-packet' : '';
    const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
    
    return `
        <div class="packet-log-entry ${deviceClass} p-2 border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer" onclick="handlePacketClick('${packet.packet}')">
            <span class="inline-block min-w-[50px] mr-2 text-sm font-semibold ${type === 'send' ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}">[${type.toUpperCase()}]</span>
            <span class="font-mono dark:text-gray-300">${formattedPacket}</span>
            <span class="inline-block min-w-[120px] ml-2 text-sm text-gray-600 dark:text-gray-400">[${deviceInfo.device} - ${deviceInfo.packet_type}]</span>
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
                    updatePacketDisplay(true);
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
                    updatePacketDisplay(false);
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

// 패킷 로그 초기화 버튼 이벤트 리스너 추가
document.getElementById('packetLogClearButton').addEventListener('click', function() {
    clearPacketLog();
});
function clearLivePacketLog() {
    const sendLogDiv = document.getElementById('send-data');
    const recvLogDiv = document.getElementById('recv-data');
    sendLogDiv.innerHTML = '';
    recvLogDiv.innerHTML = '';
    liveLastPackets.clear();
}
// 초기화 버튼 이벤트 리스너 추가
document.getElementById('livePacketLogClearButton').addEventListener('click', function() {
    clearLivePacketLog();
});

const PacketReference = {
    createTable(deviceData) {
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
                    this.appendCellContent(td, deviceData[type], byte);
                }
                
                row.appendChild(td);
            });
            
            table.appendChild(row);
        }
        
        return table;
    },

    appendCellContent(td, typeData, byte) {
        if (typeData.byte_desc && typeData.byte_desc[byte] !== undefined) {
            const descDiv = document.createElement('div');
            descDiv.className = 'font-medium text-gray-900 mb-2';
            descDiv.textContent = typeData.byte_desc[byte];
            td.appendChild(descDiv);
        }
        
        if (typeData.byte_values && typeData.byte_values[byte]) {
            const valuesDiv = document.createElement('div');
            valuesDiv.className = 'space-y-1';
            Object.entries(typeData.byte_values[byte]).forEach(([key, value]) => {
                const valueSpan = document.createElement('div');
                valueSpan.className = 'text-sm text-gray-600';
                valueSpan.textContent = `${key}: ${value}`;
                valuesDiv.appendChild(valueSpan);
            });
            td.appendChild(valuesDiv);
        }
        
        if (typeData.byte_memos && typeData.byte_memos[byte]) {
            const memoDiv = document.createElement('div');
            memoDiv.className = 'mt-2 text-sm text-gray-500 italic';
            memoDiv.textContent = `💡 ${typeData.byte_memos[byte]}`;
            td.appendChild(memoDiv);
        }
    },

    update(data) {
        const tabContents = document.getElementById('tabContents');
        if (!tabContents) return;
        
        tabContents.innerHTML = '';
        Object.entries(data).forEach(([deviceName, deviceData]) => {
            const deviceSection = document.createElement('div');
            deviceSection.id = `device-${deviceName}`;
            deviceSection.className = 'tab-content';
            
            const table = this.createTable(deviceData);
            deviceSection.appendChild(table);
            
            tabContents.appendChild(deviceSection);
        });
    },

    openTab(evt, deviceName) {
        const tabcontents = document.getElementsByClassName("tab-content");
        for (let content of tabcontents) {
            content.classList.add('hidden');
        }

        const tabButtons = document.getElementById('deviceTabs').getElementsByTagName('button');
        for (let button of tabButtons) {
            button.className = button.className
                .replace('border-blue-500 text-blue-600', 'border-transparent text-gray-500')
                .replace('hover:text-gray-700 hover:border-gray-300', '');
            
            if (button.getAttribute('data-tab') !== deviceName) {
                button.className += ' hover:text-gray-700 hover:border-gray-300';
            }
        }
        
        const selectedTab = document.getElementById(deviceName);
        if (selectedTab) {
            selectedTab.classList.remove('hidden');
        }
        evt.currentTarget.className = evt.currentTarget.className
            .replace('border-transparent text-gray-500', 'border-blue-500 text-blue-600');
    }
};

function loadReferencePacketStructures() {
    fetch('./api/packet_structures')
        .then(response => response.json())
        .then(structures => {
            const tabButtons = document.getElementById('deviceTabs');
            const tabContents = document.getElementById('tabContents');
            if (!tabButtons || !tabContents) return;
            
            tabButtons.innerHTML = '';
            let isFirst = true;
            
            for (const [deviceName, deviceData] of Object.entries(structures)) {
                const button = document.createElement('button');
                button.className = `px-4 py-2 text-sm font-medium border-b-2 focus:outline-none transition-colors ${
                    isFirst ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`;
                button.setAttribute('data-tab', deviceName);
                button.onclick = function(evt) { PacketReference.openTab(evt, deviceName); };
                button.textContent = deviceName;
                tabButtons.appendChild(button);
                isFirst = false;
            }
            
            PacketReference.update(structures);
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

// 실시간 패킷 데이터 폴링 시작
function startPolling() {
    if (isPolling) return;
    
    isPolling = true;
    
    // 500ms마다 데이터 요청
    pollingInterval = setInterval(fetchPacketData, 500);
}

// 실시간 패킷 데이터 폴링 중지
function stopPolling() {
    if (!isPolling) return;
    
    isPolling = false;
    
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
// 일시정지 버튼 이벤트 리스너
document.getElementById('pauseButton').addEventListener('click', function() {
    togglePause();
    this.textContent = isPaused ? '재개' : '일시정지';
    this.classList.toggle('bg-blue-500');
    this.classList.toggle('bg-green-500');
});


function startPacketLogUpdate() {
    packetLogInterval = setInterval(updatePacketLog, 1000);
}

function stopPacketLogUpdate() {
    if (packetLogInterval) {
        clearInterval(packetLogInterval);
        packetLogInterval = null;
    }
}

// ===============================
// 초기화 및 상태 업데이트 함수들
// ===============================


document.addEventListener('DOMContentLoaded', function() {
    // 대시보드 초기화
    const dashboard = new Dashboard();
    
    // 초기 상태 업데이트
    dashboard.updateDeviceList();
    dashboard.updateMqttStatus();
    dashboard.updateEW11Status();

    fetch('./api/packet_suggestions')
        .then(response => response.json())
        .then(data => {
            packetSuggestions = data;
            showAvailableHeaders();
        });
});
