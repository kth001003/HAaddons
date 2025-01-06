class ConfigManager {
    constructor() {
        this.configForm = document.getElementById('configForm');
        this.messageElement = document.getElementById('configMessage');
        this.bindEvents();
    }

    bindEvents() {
        document.addEventListener('DOMContentLoaded', () => {
            const saveButton = document.getElementById('saveConfig');
            if (saveButton) {
                saveButton.addEventListener('click', () => this.saveConfig());
            }
        });
    }

    // 기존 loadConfig 함수를 메서드로 변환
    async loadConfig() {
        try {
            const response = await fetch('./api/config');
            const data = await response.json();
            
            if (data.error) {
                this.showConfigMessage('설정을 불러오는 중 오류가 발생했습니다: ' + data.error, true);
                return;
            }

            this.configForm.innerHTML = '';

            // 스키마 기반으로 설정 UI 생성
            for (const [key, value] of Object.entries(data.config)) {
                const schema = data.schema[key] || '';
                this.configForm.appendChild(this.createConfigField(key, value, schema));
            }
        } catch (error) {
            this.showConfigMessage('설정을 불러오는 중 오류가 발생했습니다.', true);
        }
    }

    // ... 기존 함수들을 클래스 메서드로 변환 ...
    createConfigField(key, value, schema) {
        const fieldDiv = document.createElement('div');
        fieldDiv.className = 'border-b border-gray-700 dark:border-gray-600 py-2';

        // 객체인 경우 하위 설정 처리
        if (typeof value === 'object' && value !== null) {
            fieldDiv.innerHTML = `
                <div class="mb-2">
                    <label class="text-sm font-medium text-gray-700 dark:text-gray-300">${key}</label>
                </div>
                <div class="pl-4 space-y-2">
                    ${Object.entries(value).map(([subKey, subValue]) => `
                        <div class="flex items-center gap-2">
                            <label class="text-sm text-gray-600 dark:text-gray-400 w-1/3">${subKey}:</label>
                            <input type="text" 
                                value="${subValue}" 
                                class="form-input block rounded-md border-gray-700 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm py-1"
                                data-key="${key}"
                                data-subkey="${subKey}">
                        </div>
                    `).join('')}
                </div>
            `;
            return fieldDiv;
        }

        // 기존 단일 설정 처리
        const labelContainer = this.createLabelContainer(key, schema);
        fieldDiv.appendChild(labelContainer);

        const description = document.createElement('p');
        description.className = 'text-xs text-gray-500 mb-1';
        description.textContent = '';
        fieldDiv.appendChild(description);

        const input = this.createInputField(key, value, schema);
        fieldDiv.appendChild(input);

        return fieldDiv;
    }

    createLabelContainer(key, schema) {
        const labelContainer = document.createElement('div');
        labelContainer.className = 'flex items-center gap-1 mb-1';

        const label = document.createElement('label');
        label.className = 'text-sm font-medium text-gray-700 dark:text-gray-300';
        label.textContent = key;

        const isOptional = schema.endsWith('?');
        if (!isOptional) {
            label.textContent += ' *';
        }
        schema = schema.replace('?', '');

        labelContainer.appendChild(label);

        // 스키마 타입에 따른 툴팁 추가
        if (schema.includes('(')) {
            const tooltip = this.createTooltip(schema);
            if (tooltip) {
                tooltip.className = 'text-xs text-gray-500 dark:text-gray-400';
                labelContainer.appendChild(tooltip);
            }
        }

        return labelContainer;
    }

    createTooltip(schema) {
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

    createInputField(key, value, schema) {
        const schemaType = schema.split('(')[0];
        const isOptional = schema.endsWith('?');
        schema = schema.replace('?', '');

        let input;
        const baseClassName = 'form-input block w-full rounded-md border-gray-700 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm py-1';

        switch (schemaType) {
            case 'bool':
                input = this.createSelectInput(['true', 'false'], value === true, baseClassName);
                break;
            case 'list':
                const options = schema.split('(')[1].replace('?)', '').replace(')', '').split('|');
                input = this.createSelectInput(options, value, baseClassName);
                break;
            case 'int':
            case 'float':
                input = this.createNumberInput(schema, value, schemaType, baseClassName);
                break;
            case 'match':
                input = this.createMatchInput(schema, value, baseClassName);
                break;
            default:
                input = this.createTextInput(value, baseClassName);
        }

        input.id = `config-${key}`;
        input.dataset.key = key;
        input.dataset.type = schemaType;
        if (!isOptional) {
            input.required = true;
        }

        return input;
    }

    createSelectInput(options, selectedValue, className) {
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

    createNumberInput(schema, value, type, className) {
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
                this.addRangeValidation(input, min, max, type);
            }
        }

        return input;
    }

    createMatchInput(schema, value, className) {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.className = className;

        const pattern = schema.split('(')[1].replace('?)', '').replace(')', '');
        input.pattern = pattern;
        this.addPatternValidation(input, pattern);

        return input;
    }

    createTextInput(value, className) {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.className = className;
        return input;
    }

    addRangeValidation(input, min, max, type) {
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

    addPatternValidation(input, pattern) {
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

    async saveConfig() {
        if (!confirm('설정을 저장하면 애드온이 재시작됩니다. 계속하시겠습니까?')) {
            return;
        }

        const configData = this.collectConfigData();
        this.showConfigMessage('설정을 저장하고 애드온을 재시작하는 중...', false);

        try {
            const response = await fetch('./api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                if (data.error === '유효성 검사 실패' && data.details) {
                    const errorMessage = ['유효성 검사 실패:'].concat(data.details).join('\n');
                    this.showConfigMessage(errorMessage, true);
                    throw new Error('validation_failed');
                } else {
                    this.showConfigMessage(data.error || '설정 저장 실패', true);
                    throw new Error('save_failed');
                }
            }
        } catch (error) {
            if (error.message !== 'validation_failed' && error.message !== 'save_failed') {
                console.log('애드온이 재시작되는 중입니다...');
                setTimeout(() => {
                    window.location.reload();
                }, 10000);
            } else {
                console.error('설정 저장 실패:', error);
            }
        }
    }

    collectConfigData() {
        const configData = {};
        const inputs = this.configForm.querySelectorAll('input, select');
        
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            const subKey = input.getAttribute('data-subkey');
            const schemaType = input.getAttribute('data-type');
            
            let value = this.parseInputValue(input, schemaType);
            
            if (subKey) {
                if (!configData[key]) {
                    configData[key] = {};
                }
                configData[key][subKey] = value;
            } else {
                configData[key] = value;
            }
        });
        
        return configData;
    }

    parseInputValue(input, schemaType) {
        switch(schemaType) {
            case 'bool':
                return input.value === 'true';
            case 'int':
                return parseInt(input.value);
            case 'float':
                return parseFloat(input.value);
            default:
                return input.value;
        }
    }

    showConfigMessage(message, isError) {
        this.messageElement.innerHTML = message.replace(/\n/g, '<br>');
        this.messageElement.className = `text-sm ${isError ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'} whitespace-pre-line`;
    }
}

// 인스턴스 생성 및 초기화
const configManager = new ConfigManager();
configManager.loadConfig();
