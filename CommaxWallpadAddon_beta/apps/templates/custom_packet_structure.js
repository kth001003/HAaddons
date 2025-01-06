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