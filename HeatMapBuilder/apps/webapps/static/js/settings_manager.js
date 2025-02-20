export class SettingsManager {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.lastValidCustomCmap = '';
        this.initializeColorSync();
        this.initializeVariogramModel();
        this.initializeColormapControls();
        this.initializeEventListeners();
        this.setupSensorDisplayUpdate();
    }

    initializeEventListeners() {
        // 모든 설정 저장 버튼 이벤트
        const saveAllSettingsBtn = document.getElementById('save-all-settings');
        if (saveAllSettingsBtn) {
            saveAllSettingsBtn.addEventListener('click', () => {
                this.saveInterpolationParameters();
                this.saveGenConfig();
                this.uiManager.showMessage('모든 설정이 저장되었습니다.', 'success');
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
            'sensor-name-font-size', 'sensor-name-color', 'sensor-name-color-preset',
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
            
            await fetch('./api/save-walls-and-sensors', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ wallsData, sensorsData, unit })
            });
            this.uiManager.showMessage('벽과 센서위치를 저장했습니다.', 'success');
        } catch (error) {
            console.error('벽 및 센서 저장 실패:', error);
            this.uiManager.showMessage('벽 저장에 실패했습니다.', 'error');
        }
    }

    async saveInterpolationParameters() {
        const interpolationParams = this.collectInterpolationParams();
        try {
            const response = await fetch('./api/save-interpolation-parameters', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    interpolation_params: interpolationParams
                })
            });
            const data = await response.json();
            if (data.status === 'success') {
                this.uiManager.showMessage('파라미터를 저장했습니다.', 'success');
            } else {
                this.uiManager.showMessage(data.error || '파라미터 저장에 실패했습니다.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiManager.showMessage('파라미터 저장 중 오류가 발생했습니다.', 'error');
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

    async saveGenConfig() {
        const genConfig = this.collectGenConfig();
        try {
            const response = await fetch('./api/save-gen-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    gen_config: genConfig
                })
            });
            const data = await response.json();
            if (data.status === 'success') {
                this.uiManager.showMessage('구성을 저장했습니다.', 'success');
            } else {
                this.uiManager.showMessage(data.error || '구성 저장에 실패했습니다.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiManager.showMessage('구성 저장 중 오류가 발생했습니다.', 'error');
        }
    }

    collectGenConfig() {
        return {
            gen_interval: parseInt(/** @type {HTMLInputElement} */(document.getElementById('generation-interval')).value),
            format: /** @type {HTMLInputElement} */ (document.getElementById('format')).value,
            file_name: /** @type {HTMLInputElement} */ (document.getElementById('file-name')).value,
            rotation_count: parseInt(/** @type {HTMLInputElement} */(document.getElementById('rotation-count')).value),
            visualization: this.collectVisualizationConfig(),
            colorbar: {
                ...this.collectColorbarConfig(),
                cmap: this.getSelectedColormap()
            }
        };
    }

    collectVisualizationConfig() {
        return {
            empty_area: /** @type {HTMLSelectElement} */ (document.getElementById('empty-area-style')).value,
            area_border_width: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('area-border-width')).value),
            area_border_color: /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value,
            plot_border_width: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('plot-border-width')).value),
            plot_border_color: /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value,
            sensor_display: /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option')).value,
            sensor_info_bg: this.collectSensorInfoBgConfig(),
            sensor_marker: this.collectSensorMarkerConfig(),
            sensor_name: this.collectSensorNameConfig(),
            sensor_temp: this.collectSensorTempConfig()
        };
    }

    collectColorbarConfig() {
        return {
            show_colorbar: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-colorbar')).checked,
            width: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-width')).value),
            height: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-height')).value),
            location: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-location')).value,
            borderpad: parseFloat(/** @type {HTMLSelectElement} */(document.getElementById('colorbar-borderpad')).value),
            orientation: /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-orientation')).value,
            show_label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-label')).checked,
            label: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label')).value,
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-font-size')).value),
            tick_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('colorbar-tick-size')).value),
            label_color: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label-color')).value,
            show_shadow: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-shadow')).checked,
            shadow_color: /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-color')).value,
            shadow_width: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-width')).value),
            shadow_x_offset: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-x-offset')).value),
            shadow_y_offset: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('colorbar-shadow-y-offset')).value),
            min_temp: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('min-temp')).value),
            max_temp: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('max-temp')).value),
            temp_steps: parseFloat(/** @type {HTMLInputElement} */(document.getElementById('temp-steps')).value)
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

    collectSensorNameConfig() {
        return {
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-name-font-size')).value),
            color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-name-color')).value
        };
    }

    collectSensorTempConfig() {
        return {
            font_size: parseInt(/** @type {HTMLInputElement} */(document.getElementById('sensor-temp-font-size')).value),
            color: /** @type {HTMLInputElement} */ (document.getElementById('sensor-temp-color')).value
        };
    }

    initializeColorSync() {
        const colorSyncPairs = [
            ['sensor-info-bg-color', 'sensor-info-bg-color-preset'],
            ['sensor-marker-color', 'sensor-marker-color-preset'],
            ['sensor-name-color', 'sensor-name-color-preset'],
            ['sensor-temp-color', 'sensor-temp-color-preset'],
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
            const response = await fetch('/api/preview_colormap', {
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
            console.error('Error previewing colormap:', error);
            this.uiManager.showMessage('잘못된 컬러맵 이름입니다. 다시 확인해주세요.', 'error');
        }
    }

    async updateColormapPreview() {
        try {
            const response = await fetch('/api/preview_colormap', {
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
            console.error('Error previewing colormap:', error);
            this.uiManager.showMessage('잘못된 컬러맵 이름입니다. 다시 확인해주세요.', 'error');
        }
    }

    async loadConfig(svg, sensorManager, drawingTool) {
        try {
            const response = await fetch('./api/load-config');
            if (response.ok) {
                const config = await response.json();
                if (config.walls) {
                    svg.innerHTML = config.walls;
                }
                if (config.sensors) {
                    config.sensors.forEach(savedSensor => {
                        const sensor = sensorManager.sensors.find(s => s.entity_id === savedSensor.entity_id);
                        if (sensor && savedSensor.position) {
                            console.log("적용 전 센서:", sensor);
                            sensor.position = savedSensor.position;
                            sensor.calibration = savedSensor.calibration || 0;
                            console.log("적용 후 센서:", sensor);
                            sensorManager.updateSensorMarker(sensor, savedSensor.position);
                        }
                    });
                }
                if (config.parameters) {
                    this.loadInterpolationParameters(config.parameters);
                }
                if (config.gen_config) {
                    this.loadGenConfig(config.gen_config);
                }
            }
            drawingTool.saveState();
        } catch (error) {
            console.error('설정을 불러오는데 실패했습니다:', error);
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
            console.error('Error:', error);
            this.uiManager.showMessage('파라미터 로드 중 오류가 발생했습니다.', 'error');
        }
    }

    loadGenConfig(config) {
        /** @type {HTMLInputElement} */ (document.getElementById('generation-interval')).value = config.gen_interval ?? 5;
        /** @type {HTMLInputElement} */ (document.getElementById('format')).value = config.format ?? 'png';
        /** @type {HTMLInputElement} */ (document.getElementById('file-name')).value = config.file_name ?? 'thermal_map';
        /** @type {HTMLInputElement} */ (document.getElementById('rotation-count')).value = config.rotation_count ?? 20;

        // 시각화 설정 로드
        const visualization = config.visualization || {};
        /** @type {HTMLSelectElement} */ (document.getElementById('empty-area-style')).value = visualization.empty_area ?? 'white';
        /** @type {HTMLInputElement} */ (document.getElementById('area-border-width')).value = visualization.area_border_width ?? 2;
        /** @type {HTMLInputElement} */ (document.getElementById('area-border-color')).value = visualization.area_border_color ?? '#000000';
        /** @type {HTMLInputElement} */ (document.getElementById('plot-border-width')).value = visualization.plot_border_width ?? 0;
        /** @type {HTMLInputElement} */ (document.getElementById('plot-border-color')).value = visualization.plot_border_color ?? '#000000';
        /** @type {HTMLSelectElement} */ (document.getElementById('sensor-display-option')).value = visualization.sensor_display ?? 'position_name_temp';

        // 센서 정보 배경 설정 로드
        const sensorInfoBg = visualization.sensor_info_bg || {};
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-bg-color')).value = sensorInfoBg.color ?? '#FFFFFF';
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-bg-opacity')).value = sensorInfoBg.opacity ?? 70;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-padding')).value = sensorInfoBg.padding ?? 5;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-border-radius')).value = sensorInfoBg.border_radius ?? 4;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-border-width')).value = sensorInfoBg.border_width ?? 1;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-border-color')).value = sensorInfoBg.border_color ?? '#000000';
        /** @type {HTMLSelectElement} */ (document.getElementById('sensor-info-position')).value = sensorInfoBg.position ?? 'right';
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-info-distance')).value = sensorInfoBg.distance ?? 10;

        // 위치 표시 설정 로드
        const sensorMarker = visualization.sensor_marker || {};
        /** @type {HTMLSelectElement} */ (document.getElementById('sensor-marker-style')).value = sensorMarker.style ?? 'circle';
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-marker-size')).value = sensorMarker.size ?? 10;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-marker-color')).value = sensorMarker.color ?? '#FF0000';

        // 센서 이름 설정 로드
        const sensorName = visualization.sensor_name || {};
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-name-font-size')).value = sensorName.font_size ?? 12;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-name-color')).value = sensorName.color ?? '#000000';

        // 온도 표시 설정 로드
        const sensorTemp = visualization.sensor_temp || {};
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-temp-font-size')).value = sensorTemp.font_size ?? 12;
        /** @type {HTMLInputElement} */ (document.getElementById('sensor-temp-color')).value = sensorTemp.color ?? '#000000';

        // 컬러바 설정 로드
        const colorbar = config.colorbar || {};
        const cmap = colorbar.cmap ?? 'RdYlBu_r';
        const isReversed = cmap.endsWith('_r');
        const baseColormap = isReversed ? cmap.slice(0, -2) : cmap;
        
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-cmap')).value = baseColormap;
        /** @type {HTMLInputElement} */ (document.getElementById('reverse-colormap')).checked = isReversed;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-colorbar')).checked = colorbar.show_colorbar ?? true;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-width')).value = colorbar.width ?? 5;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-height')).value = colorbar.height ?? 100;
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-location')).value = colorbar.location ?? 'right';
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-borderpad')).value = colorbar.borderpad ?? '0';
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-orientation')).value = colorbar.orientation ?? 'vertical';
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-label')).checked = colorbar.show_label ?? true;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label')).value = colorbar.label ?? '온도 (°C)';
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-font-size')).value = colorbar.font_size ?? 12;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-tick-size')).value = colorbar.tick_size ?? 10;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-label-color')).value = colorbar.label_color ?? '#000000';
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-label-color-preset')).value = colorbar.label_color ?? '#000000';
        /** @type {HTMLInputElement} */ (document.getElementById('min-temp')).value = colorbar.min_temp ?? 15;
        /** @type {HTMLInputElement} */ (document.getElementById('max-temp')).value = colorbar.max_temp ?? 35;
        /** @type {HTMLInputElement} */ (document.getElementById('temp-steps')).value = colorbar.temp_steps ?? 100;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-show-shadow')).checked = colorbar.show_shadow ?? true;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-color')).value = colorbar.shadow_color ?? '#FFFFFF';
        /** @type {HTMLSelectElement} */ (document.getElementById('colorbar-shadow-color-preset')).value = colorbar.shadow_color ?? '#FFFFFF';
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-width')).value = colorbar.shadow_width ?? 1;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-x-offset')).value = colorbar.shadow_x_offset ?? 1;
        /** @type {HTMLInputElement} */ (document.getElementById('colorbar-shadow-y-offset')).value = colorbar.shadow_y_offset ?? 1;

        // 컬러맵 프리뷰 업데이트
        this.updateColormapPreview();

        // 컬러바 색상 프리셋 동기화 설정
        this.setupColorSync('colorbar-label-color', 'colorbar-label-color-preset');
        this.setupColorSync('colorbar-shadow-color', 'colorbar-shadow-color-preset');
    }
} 