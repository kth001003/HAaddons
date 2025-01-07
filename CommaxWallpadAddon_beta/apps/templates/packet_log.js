
// ===============================
// 패킷 로그 관련 클래스
// ===============================
class PacketLogger {
    constructor() {
        this.lastPackets = new Set();
        this.liveLastPackets = new Set();
        this.isPaused = false;
        this.isPolling = false;
        this.pollingInterval = null;
        this.packetLogInterval = null;

        this.bindEvents();
    }

    bindEvents() {
        // 패킷 로그 초기화 버튼 이벤트 리스너
        const clearButton = document.getElementById('packetLogClearButton');
        if (clearButton) {
            clearButton.addEventListener('click', () => this.clearPacketLog());
        }

        // 실시간 패킷 로그 초기화 버튼 이벤트 리스너
        const clearLiveButton = document.getElementById('livePacketLogClearButton');
        if (clearLiveButton) {
            clearLiveButton.addEventListener('click', () => this.clearLivePacketLog());
        }

        // 일시정지 버튼 이벤트 리스너
        const pauseButton = document.getElementById('pauseButton');
        if (pauseButton) {
            pauseButton.addEventListener('click', () => {
                this.togglePause();
                pauseButton.textContent = this.isPaused ? '재개' : '일시정지';
                pauseButton.classList.toggle('bg-blue-500');
                pauseButton.classList.toggle('bg-green-500');
            });
        }
    }

    updatePacketDisplay(isLive = false) {
        const elements = document.getElementsByClassName(isLive ? 'live-unknown-packet' : 'unknown-packet');
        const hideUnknown = document.getElementById(isLive ? 'hideUnknownLive' : 'hideUnknown');
        if (!(hideUnknown instanceof HTMLInputElement)) return;
        const displayStyle = hideUnknown.checked ? 'none' : '';
        
        Array.from(elements).forEach(el => {
            if (el instanceof HTMLElement) {
                el.style.display = displayStyle;
            }
        });
    }

    createPacketLogEntry(packet, type) {
        const deviceInfo = packet.results.length > 0 ? packet.results[0] : { device: 'Unknown', packet_type: 'Unknown' };
        const deviceClass = deviceInfo.device === 'Unknown' ? 'unknown-packet' : '';
        const formattedPacket = packet.packet.match(/.{2}/g).join(' ');
        
        return `
            <div class="packet-log-entry ${deviceClass} p-2 border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer" onclick="packetLogger.handlePacketClick('${packet.packet}')">
                <span class="inline-block min-w-[50px] mr-2 text-sm font-semibold ${type === 'send' ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}">[${type.toUpperCase()}]</span>
                <span class="font-mono dark:text-gray-300">${formattedPacket}</span>
                <span class="inline-block min-w-[120px] ml-2 text-sm text-gray-600 dark:text-gray-400">[${deviceInfo.device} - ${deviceInfo.packet_type}]</span>
            </div>`;
    }

    updatePacketLog(isLive = false) {
        if (isLive && this.isPaused) return;

        fetch('./api/packet_logs')
            .then(response => response.json())
            .then(data => {
                const logDiv = document.getElementById(isLive ? 'livePacketLog' : 'packetLog');
                const packetSet = isLive ? this.liveLastPackets : this.lastPackets;
                let newContent = '';

                // 송신 및 수신 패킷 처리
                ['send', 'recv'].forEach(type => {
                    data[type].forEach(packet => {
                        const packetKey = `${type}:${packet.packet}`;
                        
                        if (isLive) {
                            // 실시간 모드: 새로운 패킷이면 추가
                            if (!packetSet.has(packetKey)) {
                                newContent = this.createPacketLogEntry(packet, type) + newContent;
                                packetSet.add(packetKey);
                            }
                        } else {
                            // 일반 모드: Set에 없는 패킷만 추가하고 표시
                            if (!packetSet.has(packetKey)) {
                                newContent = this.createPacketLogEntry(packet, type) + newContent;
                                packetSet.add(packetKey);
                            }
                        }
                    });
                });

                if (newContent) {
                    if (isLive) {
                        logDiv.innerHTML = newContent + logDiv.innerHTML;
                        this.updatePacketDisplay(true);
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
                        this.updatePacketDisplay(false);
                    }
                }
            })
            .catch(error => console.error('패킷 로그 업데이트 실패:', error));
    }

    handlePacketClick(packet) {
        const packetInput = document.getElementById('packetInput');
        if (!(packetInput instanceof HTMLInputElement)) return;
        packetInput.value = packet;
        packetAnalyzer.analyzePacket();
    }

    clearPacketLog() {
        const logDiv = document.getElementById('packetLog');
        logDiv.innerHTML = '';
        this.lastPackets.clear();
    }

    clearLivePacketLog() {
        const sendLogDiv = document.getElementById('send-data');
        const recvLogDiv = document.getElementById('recv-data');
        sendLogDiv.innerHTML = '';
        recvLogDiv.innerHTML = '';
        this.liveLastPackets.clear();
    }

    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        
        // 500ms마다 데이터 요청
        this.pollingInterval = setInterval(() => this.fetchPacketData(), 500);
    }

    stopPolling() {
        if (!this.isPolling) return;
        
        this.isPolling = false;
        
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    async fetchPacketData() {
        if (this.isPaused) return;
        
        try {
            const response = await fetch('./api/live_packets');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            
            // 패킷 데이터 업데이트
            this.updateLivePacketDisplay(data);
        } catch (error) {
            console.error('패킷 데이터 요청 실패:', error);
        }
    }

    updateLivePacketDisplay(data) {
        const sendDataElement = document.getElementById('send-data');
        const recvDataElement = document.getElementById('recv-data');
        
        if (sendDataElement && data.send_data) {
            sendDataElement.textContent = data.send_data.join('\n');
        }
        if (recvDataElement && data.recv_data) {
            recvDataElement.textContent = data.recv_data.join('\n');
        }
    }

    togglePause() {
        this.isPaused = !this.isPaused;
        const pauseButton = document.getElementById('pauseButton');
        if (pauseButton) {
            pauseButton.textContent = this.isPaused ? '재개' : '일시정지';
        }
    }

    startPacketLogUpdate() {
        this.packetLogInterval = setInterval(() => this.updatePacketLog(), 1000);
    }

    stopPacketLogUpdate() {
        if (this.packetLogInterval) {
            clearInterval(this.packetLogInterval);
            this.packetLogInterval = null;
        }
    }
}
