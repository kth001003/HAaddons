export class SettingsManager {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.lastValidCustomCmap = '';
        this.mapId = new URLSearchParams(window.location.search).get('id');
        this.svg = null;
        this.sensorManager = null;
        this.drawingTool = null;
        this.initializeColorSync();
        this.initializeVariogramModel();
        this.initializeColormapControls();
        this.initializeToggleControls();
        this.initializeEventListeners();
        this.setupSensorDisplayUpdate();
    }

    initializeEventListeners() {
        // 모든 설정 저장 버튼 이벤트
        const saveAllSettingsBtn = document.getElementById('save-all-settings');
        if (saveAllSettingsBtn) {
            saveAllSettingsBtn.addEventListener('click', () => {
                this.saveConfiguration();
            });
        }

        // 벽과 센서 저장 버튼 이벤트 리스너
        document.getElementById('save-walls-sensors')?.addEventListener('click', () => {
            const svg = document.getElementById('svg-overlay');
            if (svg && this.uiManager.sensorManager) {
                this.saveWallsAndSensors(svg, this.uiManager.sensorManager);
            }
        });
    }

    setupSensorDisplayUpdate() {
        const sensorDisplaySettings = [
            'sensor-display-option',
            'sensor-info-bg-color', 'sensor-info-bg-color-preset', 'sensor-info-bg-opacity',
            'sensor-marker-style', 'sensor-marker-size', 'sensor-marker-color', 'sensor-marker-color-preset',
            'sensor-font-size', 'sensor-font-color', 'sensor-font-color-preset',
            'sensor-temp-font-size', 'sensor-temp-color', 'sensor-temp-color-preset'
        ];

        sensorDisplaySettings.forEach(settingId => {
            const element = /** @type {HTMLInputElement | HTMLSelectElement} */ (document.getElementById(settingId));
            if (element) {
                const updateSensorMarkers = () => {
                    if (this.uiManager.sensorManager) {
                        const sensors = this.uiManager.sensorManager.getSensors();
                        sensors.forEach(sensor => {
                            if (sensor.position) {
                                this.uiManager.sensorManager.updateSensorMarker(sensor, sensor.position);
                            }
                        });
                    }
                };

                element.addEventListener('change', updateSensorMarkers);

                // input 이벤트도 처리 (실시간 색상 변경을 위해)
                if ('type' in element && (element.type === 'color' || element.type === 'range' || element.type === 'number')) {
                    element.addEventListener('input', updateSensorMarkers);
                }
            }
        });
    }

    async saveWallsAndSensors(svg, sensorManager) {
        if (!this.mapId) {
            this.uiManager.showMessage('맵 ID가 없습니다.', 'error');
            return;
        }

        try {
            const wallsElements = svg.querySelectorAll('line, path.area');
            let wallsHTML = '';
            wallsElements.forEach(element => {
                wallsHTML += element.outerHTML;
            });
            const wallsData = wallsHTML;
            const sensorConfig = sensorManager.getSensorConfig();
            const unit = sensorConfig.unit;
            const sensorsData = sensorConfig.sensors;
            
            await fetch(`./api/save-walls-and-sensors/${this.mapId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ wallsData, sensorsData, unit })
            });
            this.uiManager.showMessage('벽과 센서위치를 저장했습니다.', 'success');
        } catch (error) {
            this.uiManager.showMessage('벽 저장에 실패했습니다.', 'error');
        }
    }

    async saveConfiguration() {
        if (!this.mapId) {
            this.uiManager.showMessage('맵 ID가 없습니다.', 'error');
            return;
        }

        try {
            // 저장할 데이터 준비
            let payload = {};
            let apiEndpoint = '';
            let successMessage = '';
            payload.interpolation_params = this.collectInterpolationParams();
            payload.gen_config = this.collectGenConfig();
            // API 엔드포인트 및 성공 메시지 설정
            apiEndpoint = `./api/save-configuration/${this.mapId}`;
            successMessage = '모든 설정을 저장했습니다.';

            const response = await fetch(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            if (data.status === 'success') {
                this.uiManager.showMessage(successMessage, 'success');
            } else {
                this.uiManager.showMessage(data.error || '설정 저장에 실패했습니다.', 'error');
            }
            this.uiManager.saveCurrentSettings();
        } catch (error) {
            this.uiManager.showMessage('설정 저장 중 오류가 발생했습니다.', 'error');
        }
    }

    collectInterpolationParams() {
        const interpolationParams = {
            gaussian: {
                sigma_factor: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('gaussian-sigma-factor')).value)
            },
            rbf: {
                function: /** @type {HTMLSelectElement} */ (document.getElementById('rbf-function')).value,
                epsilon_factor: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('rbf-epsilon-factor')).value)
            },
            kriging: {
                variogram_model: /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model')).value,
                nlags: parseInt(/** @type {HTMLInputElement} */(document.getElementById('kriging-nlags')).value),
                weight: /** @type {HTMLInputElement} */ (document.getElementById('kriging-weight')).checked,
                anisotropy_scaling: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-anisotropy-scaling')).value),
                anisotropy_angle: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-anisotropy-angle')).value)
            }
        };

        const model = interpolationParams.kriging.variogram_model;
        if (model === 'linear') {
            interpolationParams.kriging.variogram_parameters = {
                slope: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-slope')).value),
                nugget: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-linear-nugget')).value)
            };
        } else if (model === 'power') {
            interpolationParams.kriging.variogram_parameters = {
                scale: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-scale')).value),
                exponent: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-exponent')).value),
                nugget: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-power-nugget')).value)
            };
        } else {
            interpolationParams.kriging.variogram_parameters = {
                nugget: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-nugget')).value),
                sill: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-sill')).value),
                range: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('kriging-range')).value)
            };
        }

        return interpolationParams;
    }

    collectGenConfig() {
        return {
            auto_generation: /** @type {HTMLInputElement} */ (document.getElementById('auto-generation-enabled')).checked,
            gen_interval: parseInt(/** @type {HTMLInputElement} */(document.getElementById('generation-interval')).value),
            format: /** @type {HTMLInputElement} */ (document.getElementById('format')).value,
            file_name: /** @type {HTMLInputElement} */ (document.getElementById('file-name')).value,
            rotation_count: parseInt(/** @type {HTMLInputElement} */(document.getElementById('rotation-count')).value),
            gif_enabled: /** @type {HTMLInputElement} */ (document.getElementById('gif-enabled')).checked ?? false,
            gif_frame_duration: parseInt(/** @type {HTMLInputElement} */(document.getElementById('gif-frame-duration')).value) ?? 1000,
            timestamp: this.collectTimestampConfig(),
            visualization: this.collectVisualizationConfig(),
            colorbar: {
                ...this.collectColorbarConfig(),
                cmap: this.getSelectedColormap()
            }
        };
    }

    collectTimestampConfig() {
        return {
            enabled: /** @type {HTMLInputElement} */ (document.getElementById('timestamp-enabled')).checked,
            format: /** @type {HTMLSelectElement} */ (document.getElementById('timestamp-format')).value,
            position: /** @type {HTMLSelectElement} */ (document.getElementById('timestamp-position')).value,
            margin_x: parseInt(/** @type {HTMLInputElement} */(document.getElementById('timestamp-margin-x')).value),
            margin_y: parseInt(/** @type {HTMLInputElement} */(document.getElementById('timestamp-margin-y')).value),
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('timestamp-font-size')).value),
            font_color: /** @type {HTMLInputElement} */ (document.getElementById('timestamp-font-color')).value,
            shadow: {
                enabled: /** @type {HTMLInputElement} */ (document.getElementById('timestamp-shadow-enabled')).checked,
                color: /** @type {HTMLInputElement} */ (document.getElementById('timestamp-shadow-color')).value,
                size: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('timestamp-shadow-size')).value),
                x_offset: parseInt(/** @type {HTMLInputElement} */(document.getElementById('timestamp-shadow-x-offset')).value),
                y_offset: parseInt(/** @type {HTMLInputElement} */(document.getElementById('timestamp-shadow-y-offset')).value)
            }
        };
    }

    collectVisualizationConfig() {
        const plot_border_width = parseFloat(/** @type {HTMLInputElement} */(document.getElementById('plot-border-width')).value);
        
        return {
            empty_area: /** @type {HTMLSelectElement} */ (document.getElementById('empty-area-style')).value,
            area_border_width: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('area-border-width')).value),
            area_border_color: /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value,
            plot_border_width: isNaN(plot_border_width) ? 0 : plot_border_width,
            plot_border_color: /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value,
            sensor_display: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option')).value,
            sensor_info_bg: this.collectSensorInfoBgConfig(),
            sensor_marker: this.collectSensorMarkerConfig(),
            sensor_font: this.collectSensorFontConfig()
        };
    }

    collectColorbarConfig() {
        return {
            show_colorbar: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-colorbar')).checked,
            width: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-width')).value),
            height: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-height')).value),
            location: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-location')).value,
            borderpad: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-borderpad')).value),
            orientation: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-orientation')).value,
            show_label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-label')).checked,
            label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label')).value,
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-font-size')).value),
            tick_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-tick-size')).value),
            label_color: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label-color')).value,
            show_shadow: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-shadow')).checked,
            shadow_color: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-color')).value,
            shadow_size: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-size')).value),
            shadow_x_offset: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-x-offset')).value),
            shadow_y_offset: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-y-offset')).value),
            auto_range: /** @type {HTMLInputElement} */ (document.getElementById('auto-range')).checked,
            min_temp: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('min-temp')).value),
            max_temp: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('max-temp')).value),
            temp_steps: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('temp-steps')).value),
            cmap: this.getSelectedColormap()
        };
    }

    collectSensorInfoBgConfig() {
        return {
            color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-bg-color')).value,
            opacity: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-info-bg-opacity')).value),
            padding: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-info-padding')).value),
            border_radius: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-info-border-radius')).value),
            border_width: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-info-border-width')).value),
            border_color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-border-color')).value,
            position: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-info-position')).value,
            distance: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-info-distance')).value)
        };
    }

    collectSensorMarkerConfig() {
        return {
            style: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-marker-style')).value,
            size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-marker-size')).value),
            color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-marker-color')).value
        };
    }

    collectSensorFontConfig() {
        return {
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-font-size')).value),
            color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-font-color')).value
        };
    }

    initializeColorSync() {
        const colorSyncPairs = [
            ['sensor-info-bg-color', 'sensor-info-bg-color-preset'],
            ['sensor-marker-color', 'sensor-marker-color-preset'],
            ['sensor-font-color', 'sensor-font-color-preset'],
            ['area-border-color', 'area-border-color-preset'],
            ['plot-border-color', 'plot-border-color-preset'],
            ['colorbar-label-color', 'colorbar-label-color-preset'],
            ['colorbar-shadow-color', 'colorbar-shadow-color-preset']
        ];

        colorSyncPairs.forEach(([colorId, presetId]) => {
            this.setupColorSync(colorId, presetId);
        });
    }

    setupColorSync(colorId, presetId) {
        const colorPicker = /** @type {HTMLInputElement} */ (document.getElementById(colorId));
        const presetSelect = /** @type {HTMLSelectElement} */ (document.getElementById(presetId));

        if (colorPicker && presetSelect) {
            colorPicker.addEventListener('input', function (e) {
                presetSelect.value = /** @type {HTMLInputElement} */ (e.target).value;
            });

            presetSelect.addEventListener('change', function (e) {
                colorPicker.value = /** @type {HTMLSelectElement} */ (e.target).value;
            });
        }
    }

    initializeVariogramModel() {
        const krigingVariogramModel = /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model'));
        if (krigingVariogramModel) {
            krigingVariogramModel.addEventListener('change', () => {
                const model = krigingVariogramModel.value;
                this.updateVariogramParametersVisibility(model);
                this.setDefaultVariogramParameters(model);
            });
        }
    }

    updateVariogramParametersVisibility(model) {
        const standardParams = document.getElementById('standard-params');
        const linearParams = document.getElementById('linear-params');
        const powerParams = document.getElementById('power-params');

        standardParams.classList.add('hidden');
        linearParams.classList.add('hidden');
        powerParams.classList.add('hidden');

        if (model === 'linear') {
            linearParams.classList.remove('hidden');
        } else if (model === 'power') {
            powerParams.classList.remove('hidden');
        } else {
            standardParams.classList.remove('hidden');
        }
    }

    setDefaultVariogramParameters(model) {
        const defaultParams = {
            'gaussian': { nugget: 5, sill: 20, range: 10 },
            'spherical': { nugget: 0, sill: 10, range: 20 },
            'exponential': { nugget: 0, sill: 15, range: 15 },
            'hole-effect': { nugget: 0, sill: 10, range: 15 },
            'linear': { slope: 1, nugget: 0 },
            'power': { scale: 1, exponent: 1.5, nugget: 0 }
        };

        const params = defaultParams[model];
        if (params) {
            if (model === 'linear') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-slope')).value = params.slope;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-linear-nugget')).value = params.nugget;
            } else if (model === 'power') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-scale')).value = params.scale;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-exponent')).value = params.exponent;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-power-nugget')).value = params.nugget;
            } else {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-nugget')).value = params.nugget;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-sill')).value = params.sill;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-range')).value = params.range;
            }
        }
    }

    initializeColormapControls() {
        const colormapSelect = /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap'));
        const customColormapInput = document.getElementById('custom-colormap-input');
        const customCmapInput = /** @type {HTMLInputElement} */ (document.getElementById('custom-cmap'));
        const reverseColormap = /** @type {HTMLInputElement} */ (document.getElementById('reverse-colormap'));
        const applyCustomCmap = document.getElementById('apply-custom-cmap');

        if (colormapSelect) {
            colormapSelect.addEventListener('change', () => {
                if (colormapSelect.value === 'custom') {
                    customColormapInput.classList.remove('hidden');
                    customCmapInput.value = this.lastValidCustomCmap;
                } else {
                    customColormapInput.classList.add('hidden');
                    this.updateColormapPreview();
                }
            });
        }

        if (applyCustomCmap) {
            applyCustomCmap.addEventListener('click', () => {
                const customValue = customCmapInput.value.trim();
                let customValueWithoutReverse = customValue;
                if (customValue.endsWith('_r')){
                    customValueWithoutReverse = customValue.slice(0, -2);
                    customCmapInput.value = customValueWithoutReverse;
                    reverseColormap.checked = true;
                }
                if (customValue) {
                    this.validateAndApplyCustomColormap(customValueWithoutReverse, reverseColormap.checked);
                }
            });
        }

        if (reverseColormap) {
            reverseColormap.addEventListener('change', () => {
                this.updateColormapPreview();
            });
        }
    }

    getSelectedColormap() {
        const colormapSelect = /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap'));
        const reverseChecked = /** @type {HTMLInputElement} */ (document.getElementById('reverse-colormap')).checked;
        const baseCmap = colormapSelect.value === 'custom' ? (this.lastValidCustomCmap || 'RdYlBu') : colormapSelect.value;
        return reverseChecked ? (baseCmap.endsWith('_r') ? baseCmap : baseCmap + '_r') : baseCmap;
    }

    async validateAndApplyCustomColormap(customValue, isReversed) {
        try {
            const response = await fetch('./api/preview_colormap', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    colormap: customValue + (isReversed ? '_r' : '')
                })
            });

            if (!response.ok) {
                throw new Error('Invalid colormap');
            }

            const blob = await response.blob();
            this.lastValidCustomCmap = customValue;
            const previewElement = document.getElementById('colormap-preview');
            const url = URL.createObjectURL(blob);
            previewElement.style.backgroundImage = `url(${url})`;
            previewElement.style.backgroundSize = 'cover';
        } catch (error) {
            this.uiManager.showMessage('잘못된 컬러맵 이름입니다. 다시 확인해주세요.', 'error');
        }
    }

    async updateColormapPreview() {
        try {
            const response = await fetch('./api/preview_colormap', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    colormap: this.getSelectedColormap()
                })
            });

            if (!response.ok) {
                throw new Error('Invalid colormap');
            }

            const blob = await response.blob();
            const previewElement = document.getElementById('colormap-preview');
            const url = URL.createObjectURL(blob);
            previewElement.style.backgroundImage = `url(${url})`;
            previewElement.style.backgroundSize = 'cover';
        } catch (error) {
            this.uiManager.showMessage('잘못된 컬러맵 이름입니다. 다시 확인해주세요.', 'error');
        }
    }

    async fetchConfig() {
        const response = await fetch(`./api/load-config/${this.mapId}`);
        if (response.ok) {
            return await response.json();
        }
        return null;
    }

    async loadConfig(svg, sensorManager, drawingTool) {
        if (!this.mapId) {
            this.uiManager.showMessage('맵 ID가 없습니다.', 'error');
            return;
        }

        // svg, sensorManager, drawingTool이 주어지지 않은 경우 현재 값 사용
        svg = svg || this.svg;
        sensorManager = sensorManager || this.sensorManager;
        drawingTool = drawingTool || this.drawingTool;

        // HTML 요소 존재 여부 확인
        const requiredElements = [
            'auto-generation-enabled',
            'generation-interval',
            'format',
            'file-name',
            'rotation-count',
            'timestamp-enabled',
            'timestamp-format',
            'timestamp-position',
            'empty-area-style',
            'sensor-display-option',
            'colorbar-cmap',
            'colorbar-show-colorbar',
            'auto-range'
        ];

        for (const elementId of requiredElements) {
            if (!document.getElementById(elementId)) {
                this.uiManager.showMessage(`필수 HTML 요소를 찾을 수 없습니다: ${elementId}`, 'error');
                return;
            }
        }

        this.svg = svg;
        this.sensorManager = sensorManager;
        this.drawingTool = drawingTool;
        try {
            const config = await this.fetchConfig();
            if (config) {
                if (config.walls) {
                    await this.loadWalls(config.walls);
                }
                if (config.sensors) {
                    await this.sensorManager.loadSensors();
                }
                if (config.parameters) {
                    this.loadInterpolationParameters(config.parameters);
                }
                if (config.gen_config) {
                    this.loadGenConfig(config.gen_config);
                }
            }
            drawingTool.resetState();
            this.uiManager.saveCurrentSettings();
        } catch (error) {
            this.uiManager.showMessage(`settingsManager: 설정을 불러오는데 실패했습니다. ${error}`, 'error');
        }
    }
    async loadWalls(walls) {
        const config = walls ? { walls } : await this.fetchConfig();
        if (config && config.walls && this.svg) {
            this.svg.innerHTML += config.walls;
        } else if (config && config.walls) {
            this.uiManager.showMessage('SVG 요소를 찾을 수 없습니다.', 'error');
        }
    }

    async loadInterpolationParameters(params) {
        try {
            /** @type {HTMLInputElement} */ (document.getElementById('gaussian-sigma-factor')).value = params?.gaussian?.sigma_factor ?? 8.0;
            /** @type {HTMLSelectElement} */ (document.getElementById('rbf-function')).value = params?.rbf?.function ?? 'gaussian';
            /** @type {HTMLInputElement} */ (document.getElementById('rbf-epsilon-factor')).value = params?.rbf?.epsilon_factor ?? 0.5;

            const model = params?.kriging?.variogram_model ?? 'gaussian';
            /** @type {HTMLSelectElement} */ (document.getElementById('kriging-variogram-model')).value = model;

            // 모델별 파라미터 로드
            if (model === 'linear') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-slope')).value = params?.kriging?.variogram_parameters?.slope ?? 1;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-linear-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 0;
            } else if (model === 'power') {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-scale')).value = params?.kriging?.variogram_parameters?.scale ?? 1;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-exponent')).value = params?.kriging?.variogram_parameters?.exponent ?? 1.5;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-power-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 0;
            } else {
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-nugget')).value = params?.kriging?.variogram_parameters?.nugget ?? 5;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-sill')).value = params?.kriging?.variogram_parameters?.sill ?? 20;
                /** @type {HTMLInputElement} */ (document.getElementById('kriging-range')).value = params?.kriging?.variogram_parameters?.range ?? 10;
            }

            /** @type {HTMLInputElement} */ (document.getElementById('kriging-nlags')).value = params?.kriging?.nlags ?? 6;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-weight')).checked = params?.kriging?.weight ?? true;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-scaling')).value = params?.kriging?.anisotropy_scaling ?? 1.0;
            /** @type {HTMLInputElement} */ (document.getElementById('kriging-anisotropy-angle')).value = params?.kriging?.anisotropy_angle ?? 0;

            // 모델에 따른 파라미터 UI 표시/숨김 처리
            this.updateVariogramParametersVisibility(model);
        } catch (error) {
            this.uiManager.showMessage('파라미터 로드 중 오류가 발생했습니다.', 'error');
        }
    }

    /**
     * HTML 요소를 안전하게 가져오고 값을 설정하는 헬퍼 함수
     * @param {string} elementId - 요소의 ID
     * @param {any} value - 설정할 값
     * @param {string} property - 설정할 속성 (예: 'value', 'checked')
     * @returns {boolean} - 성공 여부
     */
    safeSetElementValue(elementId, value, property = 'value') {
        const element = document.getElementById(elementId);
        if (!element) {
            console.warn(`Element not found: ${elementId}`);
            return false;
        }
        try {
            element[property] = value;
            return true;
        } catch (error) {
            console.error(`Error setting ${property} for ${elementId}:`, error);
            return false;
        }
    }

    loadGenConfig(config) {
        // 기본 설정
        this.safeSetElementValue('auto-generation-enabled', config.auto_generation ?? true, 'checked');
        this.safeSetElementValue('generation-interval', config.gen_interval ?? 5);
        this.safeSetElementValue('format', config.format ?? 'png');
        this.safeSetElementValue('file-name', config.file_name ?? 'map');
        this.safeSetElementValue('rotation-count', config.rotation_count ?? 20);
        this.safeSetElementValue('gif-enabled', config.gif_enabled ?? false, 'checked');
        this.safeSetElementValue('gif-frame-duration', config.gif_frame_duration ?? 1000);

        // GIF 설정 토글 초기화
        this.setupToggleControl('gif-enabled', 'gif-settings');

        // 타임스탬프 설정
        const timestamp = config.timestamp || {};
        this.safeSetElementValue('timestamp-enabled', timestamp.enabled ?? false, 'checked');
        this.safeSetElementValue('timestamp-format', timestamp.format ?? 'YYYY-MM-DD HH:mm:ss');
        this.safeSetElementValue('timestamp-position', timestamp.position ?? 'bottom-right');
        this.safeSetElementValue('timestamp-margin-x', timestamp.margin_x ?? 10);
        this.safeSetElementValue('timestamp-margin-y', timestamp.margin_y ?? 10);
        this.safeSetElementValue('timestamp-font-size', timestamp.font_size ?? 16);
        this.safeSetElementValue('timestamp-font-color', timestamp.font_color ?? '#ffffff');

        // 타임스탬프 그림자 설정
        const shadow = timestamp.shadow || {};
        this.safeSetElementValue('timestamp-shadow-enabled', shadow.enabled ?? true, 'checked');
        this.safeSetElementValue('timestamp-shadow-color', shadow.color ?? '#000000');
        this.safeSetElementValue('timestamp-shadow-size', shadow.size ?? 2);
        this.safeSetElementValue('timestamp-shadow-x-offset', shadow.x_offset ?? 1);
        this.safeSetElementValue('timestamp-shadow-y-offset', shadow.y_offset ?? 1);

        // 시각화 설정
        const visualization = config.visualization || {};
        this.safeSetElementValue('empty-area-style', visualization.empty_area ?? 'white');
        this.safeSetElementValue('area-border-width', visualization.area_border_width ?? 2);
        this.safeSetElementValue('area-border-color', visualization.area_border_color ?? '#000000');
        this.safeSetElementValue('plot-border-width', visualization.plot_border_width ?? 0);
        this.safeSetElementValue('plot-border-color', visualization.plot_border_color ?? '#000000');
        this.safeSetElementValue('sensor-display-option', visualization.sensor_display ?? 'position_name_temp');

        // 센서 정보 배경 설정
        const sensorInfoBg = visualization.sensor_info_bg || {};
        this.safeSetElementValue('sensor-info-bg-color', sensorInfoBg.color ?? '#FFFFFF');
        this.safeSetElementValue('sensor-info-bg-opacity', sensorInfoBg.opacity ?? 70);
        this.safeSetElementValue('sensor-info-padding', sensorInfoBg.padding ?? 5);
        this.safeSetElementValue('sensor-info-border-radius', sensorInfoBg.border_radius ?? 4);
        this.safeSetElementValue('sensor-info-border-width', sensorInfoBg.border_width ?? 1);
        this.safeSetElementValue('sensor-info-border-color', sensorInfoBg.border_color ?? '#000000');
        this.safeSetElementValue('sensor-info-position', sensorInfoBg.position ?? 'right');
        this.safeSetElementValue('sensor-info-distance', sensorInfoBg.distance ?? 10);

        // 센서 마커 설정
        const sensorMarker = visualization.sensor_marker || {};
        this.safeSetElementValue('sensor-marker-style', sensorMarker.style ?? 'circle');
        this.safeSetElementValue('sensor-marker-size', sensorMarker.size ?? 10);
        this.safeSetElementValue('sensor-marker-color', sensorMarker.color ?? '#FF0000');
        this.safeSetElementValue('sensor-marker-color-preset', sensorMarker.color ?? '#FF0000');

        // 센서 폰트 설정 (통합됨)
        const sensorFont = visualization.sensor_font || {};
        let fontSizeValue = 12;
        let fontColorValue = '#000000';
        
        // 이전 설정 구조 지원 (하위 호환성)
        if (visualization.sensor_name && !visualization.sensor_font) {
            fontSizeValue = visualization.sensor_name.font_size ?? 12;
            fontColorValue = visualization.sensor_name.color ?? '#000000';
        }
        
        this.safeSetElementValue('sensor-font-size', sensorFont.font_size ?? fontSizeValue);
        this.safeSetElementValue('sensor-font-color', sensorFont.color ?? fontColorValue);
        this.safeSetElementValue('sensor-font-color-preset', sensorFont.color ?? fontColorValue);

        // 컬러바 설정
        const colorbar = config.colorbar || {};
        const cmap = colorbar.cmap ?? 'RdYlBu_r';
        const isReversed = cmap.endsWith('_r');
        const baseColormap = isReversed ? cmap.slice(0, -2) : cmap;

        this.safeSetElementValue('colorbar-cmap', baseColormap);
        this.safeSetElementValue('reverse-colormap', isReversed, 'checked');
        this.safeSetElementValue('colorbar-show-colorbar', colorbar.show_colorbar ?? true, 'checked');
        this.safeSetElementValue('colorbar-width', colorbar.width ?? 5);
        this.safeSetElementValue('colorbar-height', colorbar.height ?? 100);
        this.safeSetElementValue('colorbar-location', colorbar.location ?? 'right');
        this.safeSetElementValue('colorbar-borderpad', colorbar.borderpad ?? 0);
        this.safeSetElementValue('colorbar-orientation', colorbar.orientation ?? 'vertical');
        this.safeSetElementValue('colorbar-show-label', colorbar.show_label ?? true, 'checked');
        this.safeSetElementValue('colorbar-label', colorbar.label ?? '°C');
        this.safeSetElementValue('colorbar-font-size', colorbar.font_size ?? 12);
        this.safeSetElementValue('colorbar-tick-size', colorbar.tick_size ?? 10);
        this.safeSetElementValue('colorbar-label-color', colorbar.label_color ?? '#000000');
        this.safeSetElementValue('colorbar-label-color-preset', colorbar.label_color ?? '#000000');
        this.safeSetElementValue('auto-range', colorbar.auto_range ?? false, 'checked');
        this.safeSetElementValue('min-temp', colorbar.min_temp ?? 15);
        this.safeSetElementValue('max-temp', colorbar.max_temp ?? 35);
        this.safeSetElementValue('temp-steps', colorbar.temp_steps ?? 100);
        this.safeSetElementValue('colorbar-show-shadow', colorbar.show_shadow ?? true, 'checked');
        this.safeSetElementValue('colorbar-shadow-color', colorbar.shadow_color ?? '#FFFFFF');
        this.safeSetElementValue('colorbar-shadow-color-preset', colorbar.shadow_color ?? '#FFFFFF');
        this.safeSetElementValue('colorbar-shadow-size', colorbar.shadow_size ?? 1);
        this.safeSetElementValue('colorbar-shadow-x-offset', colorbar.shadow_x_offset ?? 1);
        this.safeSetElementValue('colorbar-shadow-y-offset', colorbar.shadow_y_offset ?? 1);

        // 컬러맵 프리뷰 업데이트
        this.updateColormapPreview();

        // 컬러바 색상 프리셋 동기화 설정
        this.setupColorSync('colorbar-label-color', 'colorbar-label-color-preset');
        this.setupColorSync('colorbar-shadow-color', 'colorbar-shadow-color-preset');

        // 토글 컨트롤 초기화
        this.initializeToggleControls();
    }

    /**
     * 토글 설정에 따른 관련 옵션들의 활성화/비활성화를 관리하는 함수
     * @param {string} toggleId - 토글 체크박스의 ID
     * @param {string} targetId - 비활성화할 대상 컨테이너의 ID
     * @param {boolean} reverseLogic - true일 경우 체크되었을 때 비활성화
     */
    setupToggleControl(toggleId, targetId, reverseLogic = false) {
        const toggleElement = /** @type {HTMLInputElement} */ (document.getElementById(toggleId));
        const targetElement = document.getElementById(targetId);
        
        if (!toggleElement || !targetElement) return;

        const updateState = () => {
            const isChecked = toggleElement.checked;
            const shouldDisable = reverseLogic ? isChecked : !isChecked;
            
            targetElement.style.opacity = shouldDisable ? '0.5' : '1';
            
            // 대상 컨테이너 내의 모든 입력 요소들을 비활성화
            const inputs = targetElement.querySelectorAll('input, select, button');
            inputs.forEach(input => {
                /** @type {HTMLInputElement} */ (input).disabled = shouldDisable;
            });
        };

        toggleElement.addEventListener('change', updateState);
        // 초기 상태 설정
        updateState();
    }

    initializeToggleControls() {
        // 자동 범위 설정
        this.setupToggleControl('auto-range', 'manual-range-inputs', true);
        
        // 자동맵 생성 설정
        this.setupToggleControl('auto-generation-enabled', 'generation-interval-setting');
        
        // 타임스탬프 설정
        this.setupToggleControl('timestamp-enabled', 'timestamp-settings');
        
        // 타임스탬프 그림자 설정
        this.setupToggleControl('timestamp-shadow-enabled', 'timestamp-shadow-settings');
        
        // 컬러바 설정
        this.setupToggleControl('colorbar-show-colorbar', 'colorbar-settings');
        
        // 컬러바 레이블 설정
        this.setupToggleControl('colorbar-show-label', 'colorbar-label-settings');
        
        // 컬러바 그림자 설정
        this.setupToggleControl('colorbar-show-shadow', 'colorbar-shadow-settings');
        
        // 센서 정보 배경 설정
        this.setupToggleControl('sensor-info-bg-enabled', 'sensor-info-bg-settings');
        
        // 센서 마커 그림자 설정
        this.setupToggleControl('sensor-marker-shadow-enabled', 'sensor-marker-shadow-settings');
    }
} 