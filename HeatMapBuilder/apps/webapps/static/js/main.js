// @ts-ignore
import { DrawingTool } from './drawing_tool.js';
// @ts-ignore
import { SensorManager } from './sensor_manager.js';
// @ts-ignore
import { UIManager } from './ui_manager.js';
// @ts-ignore
import { SettingsManager } from './settings_manager.js';
// @ts-ignore
import { ThermalMapManager } from './thermal_map_manager.js';
// @ts-ignore
import { WebSocketDebugger } from './websocket_debugger.js';

document.addEventListener('DOMContentLoaded', async function () {
    console.log('DOM Content Loaded');

    // SVG 초기화
    const svg = document.getElementById('svg-overlay');
    if (!svg) {
        console.error('SVG element not found');
        return;
    }
    console.log('SVG element found:', svg);

    // SVG 초기 설정
    const container = document.getElementById('floorplan-container');
    if (!container) {
        console.error('Container element not found');
        return;
    }

    // SVG 크기를 1000x1000으로 고정
    const FIXED_SIZE = 1000;
    svg.setAttribute('viewBox', `0 0 ${FIXED_SIZE} ${FIXED_SIZE}`);
    console.log('SVG attributes set');

    // 매니저 클래스들 초기화
    const uiManager = new UIManager();
    const settingsManager = new SettingsManager(uiManager);
    const thermalMapManager = new ThermalMapManager(uiManager);
    const websocketDebugger = new WebSocketDebugger(uiManager);

    // DrawingTool 초기화
    const drawingTool = new DrawingTool(svg, uiManager);
    drawingTool.enable();
    console.log('DrawingTool initialized');

    // SensorManager 초기화
    const sensorManager = new SensorManager(svg, uiManager);
    sensorManager.disable();

    // UI 매니저에 도구 설정
    uiManager.setTools(drawingTool, sensorManager);

    // 초기 데이터 로드
    settingsManager.loadConfig(svg, sensorManager, drawingTool);
});