import { DrawingUtils } from './drawing_utils.js';

export class DrawingTool {
    constructor(svgElement, uiManager) {
        this.uiManager = uiManager;
        this.svg = svgElement;
        this.isDrawing = false;
        this.currentTool = 'line';
        this.lineWidth = 3;
        this.startPoint = null;
        this.enabled = false;
        this.isShiftPressed = false;
        this.isAltPressed = false;
        this.snapDistance = 20;
        this.history = [];  // 초기 빈 상태
        this.currentHistoryIndex = 0;
        this.maxHistoryLength = 500; // 최대 실행취소 횟수
        this.areas = []; // 감지된 영역들을 저장

        // 점 이동 관련 속성 추가
        this.selectedPoint = null;
        this.affectedLines = new Set();
        this.isDragging = false;

        // 이벤트 리스너 바인딩
        this.startDrawing = this.startDrawing.bind(this);
        this.draw = this.draw.bind(this);
        this.endDrawing = this.endDrawing.bind(this);
        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleKeyUp = this.handleKeyUp.bind(this);
        this.undo = this.undo.bind(this);
        this.redo = this.redo.bind(this);
        this.clear = this.clear.bind(this);
        this.startPointMove = this.startPointMove.bind(this);
        this.movePoint = this.movePoint.bind(this);
        this.endPointMove = this.endPointMove.bind(this);

        // SVG 이벤트 리스너 등록
        this.svg.addEventListener('mousedown', this.startDrawing);
        this.svg.addEventListener('mousemove', this.draw);
        this.svg.addEventListener('mouseup', this.endDrawing);
        this.svg.addEventListener("touchstart", this.touchHandler, true);
        this.svg.addEventListener("touchmove", this.touchHandler, true);
        this.svg.addEventListener("touchend", this.touchHandler, true);
        this.svg.addEventListener("touchcancel", this.touchHandler, true);

        // 키보드 이벤트 리스너 등록
        document.addEventListener('keydown', this.handleKeyDown);
        document.addEventListener('keyup', this.handleKeyUp);

        // 실행취소/다시실행 버튼 이벤트 리스너 등록
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');
        if (undoBtn) undoBtn.addEventListener('click', this.undo);
        if (redoBtn) redoBtn.addEventListener('click', this.redo);

        // path 요소들의 pointer-events 비활성화
        this.svg.querySelectorAll('path').forEach(path => {
            path.style.pointerEvents = 'none';
        });

        // SVG defs 요소가 없으면 생성
        this.initializeDefs();
    }

    // defs 초기화 및 마커 생성 메서드
    initializeDefs() {
        // 마커용 defs 생성 또는 찾기
        let markerDefs = this.svg.querySelector('defs.marker-defs');
        if (!markerDefs) {
            markerDefs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            markerDefs.classList.add('marker-defs');
            this.svg.insertBefore(markerDefs, this.svg.firstChild);
        }

        // 기존 마커 제거
        const oldDefaultMarker = markerDefs.querySelector('#defaultEndpoint');
        const oldHoverMarker = markerDefs.querySelector('#hoverEndpoint');
        if (oldDefaultMarker) oldDefaultMarker.remove();
        if (oldHoverMarker) oldHoverMarker.remove();

        // 기본 마커 정의
        this.createMarkerDef('defaultEndpoint', '#4CAF50', 5);
        // 호버 상태 마커 정의
        this.createMarkerDef('hoverEndpoint', '#2196F3', 7);
    }

    // 마커 정의 생성 메서드
    createMarkerDef(id, color, radius) {
        const markerDefs = this.svg.querySelector('defs.marker-defs');
        if (!markerDefs) return;

        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        
        marker.setAttribute('id', id);
        marker.setAttribute('viewBox', `-${radius} -${radius} ${radius * 2} ${radius * 2}`);
        marker.setAttribute('refX', '0');
        marker.setAttribute('refY', '0');
        marker.setAttribute('markerWidth', String(radius * 2));
        marker.setAttribute('markerHeight', String(radius * 2));
        marker.setAttribute('markerUnits', 'strokeWidth');
        marker.setAttribute('orient', 'auto');
        
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '0');
        circle.setAttribute('cy', '0');
        circle.setAttribute('r', String(radius));
        circle.setAttribute('fill', color);
        circle.style.transition = 'r 0.2s ease-in-out, fill 0.2s ease-in-out';
        
        marker.appendChild(circle);
        markerDefs.appendChild(marker);
    }
    resetState() {
        this.history = [];
        this.currentHistoryIndex = 0;
        this.saveState();
    }
    // 현재 상태 저장
    saveState() {
        // defs 임시 제거
        const Defs = this.svg.querySelector('defs');
        if (Defs) Defs.remove();

        // 현재 인덱스 이후의 기록 제거
        this.history = this.history.slice(0, this.currentHistoryIndex + 1);
        
        // 새로운 상태 추가
        this.history.push(this.svg.innerHTML);
        
        // 최대 길이 제한
        if (this.history.length > this.maxHistoryLength) {
            this.history = this.history.slice(this.history.length - this.maxHistoryLength);
        }
        
        this.currentHistoryIndex = this.history.length - 1;

        // defs 복원
        if (Defs) {
            this.svg.insertBefore(Defs, this.svg.firstChild);
        }

        this.updateUndoRedoButtons();
    }

    // 실행취소 메서드 수정
    undo() {
        if (this.currentHistoryIndex > 0) {
            // 마커용 defs 임시 저장
            const Defs = this.svg.querySelector('defs');
            if (Defs) Defs.remove();

            // 센서 마커들 임시 저장
            const sensorMarkers = Array.from(this.svg.querySelectorAll('g[data-entity-id]'));
            sensorMarkers.forEach(marker => marker.remove());

            this.currentHistoryIndex--;
            this.svg.innerHTML = this.history[this.currentHistoryIndex];

            // 마커용 defs 복원
            if (Defs) {
                this.svg.insertBefore(Defs, this.svg.firstChild);
            } else {
                this.initializeDefs();
            }

            // 센서 마커들 복원
            sensorMarkers.forEach(marker => {
                this.svg.appendChild(marker);
            });

            this.updateUndoRedoButtons();
            this.uiManager.sensorManager.parseSensorsFromSVG();
        }
    }

    // 다시실행 메서드 수정
    redo() {
        if (this.currentHistoryIndex < this.history.length - 1) {
            // defs 임시 저장
            const Defs = this.svg.querySelector('defs');
            if (Defs) Defs.remove();

            // 센서 마커들 임시 저장
            const sensorMarkers = Array.from(this.svg.querySelectorAll('g[data-entity-id]'));
            sensorMarkers.forEach(marker => marker.remove());

            this.currentHistoryIndex++;
            this.svg.innerHTML = this.history[this.currentHistoryIndex];

            // defs 복원
            if (Defs) {
                this.svg.insertBefore(Defs, this.svg.firstChild);
            } else {
                this.initializeDefs();
            }

            // 센서 마커들 복원
            sensorMarkers.forEach(marker => {
                this.svg.appendChild(marker);
            });

            this.updateUndoRedoButtons();
            this.uiManager.sensorManager.parseSensorsFromSVG();
        }
    }

    // 실행취소/다시실행 버튼 상태 업데이트
    updateUndoRedoButtons() {
        const undoBtn = /** @type {HTMLButtonElement} */ (document.getElementById('undo-btn'));
        const redoBtn = /** @type {HTMLButtonElement} */ (document.getElementById('redo-btn'));
        
        if (undoBtn) {
            undoBtn.disabled = this.currentHistoryIndex <= 0;
            undoBtn.classList.toggle('opacity-50', this.currentHistoryIndex <= 0);
        }
        
        if (redoBtn) {
            redoBtn.disabled = this.currentHistoryIndex >= this.history.length - 1;
            redoBtn.classList.toggle('opacity-50', this.currentHistoryIndex >= this.history.length - 1);
        }
    }

    // 초기화 메서드 수정
    clear() {
        // 마커용 defs 임시 저장
        const Defs = this.svg.querySelector('defs');
        if (Defs) Defs.remove();

        this.svg.innerHTML = '<rect id="floorplan-rect" width="100%" height="100%" fill="#FFFFFF"/>';
        
        // defs 복원
        if (Defs) {
            this.svg.insertBefore(Defs, this.svg.firstChild);
        } else {
            this.initializeDefs();
        }

        this.areas = [];
        this.history = [''];
        this.currentHistoryIndex = 0;
        this.saveState();
    }

    handleKeyDown(e) {
        if (e.key === 'Shift') {
            this.isShiftPressed = true;
        } else if (e.key === 'Alt') {
            this.isAltPressed = true;
        } else if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            if (e.shiftKey) {
                this.redo();
            } else {
                this.undo();
            }
        } else if (e.key === 'y' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            this.redo();
        }

        // 현재 그리고 있는 선이 있다면 업데이트
        if (this.isDrawing && this.startPoint) {
            const tempLine = this.svg.querySelector('.temp-line');
            if (tempLine) {
                const currentPoint = DrawingUtils.getMousePosition({
                    clientX: this.lastMouseX,
                    clientY: this.lastMouseY
                }, this.svg);
                this.drawTempLine(this.processPoint(currentPoint));
            }
        }
    }

    handleKeyUp(e) {
        if (e.key === 'Shift') {
            this.isShiftPressed = false;
        } else if (e.key === 'Alt') {
            this.isAltPressed = false;
        }

        // 현재 그리고 있는 선이 있다면 업데이트
        if (this.isDrawing && this.startPoint) {
            const tempLine = this.svg.querySelector('.temp-line');
            if (tempLine) {
                const currentPoint = DrawingUtils.getMousePosition({
                    clientX: this.lastMouseX,
                    clientY: this.lastMouseY
                }, this.svg);
                this.drawTempLine(this.processPoint(currentPoint));
            }
        }
    }


    enable() {
        this.enabled = true;
        this.svg.style.cursor = DrawingUtils.createCustomCursor(this.currentTool);
    }

    disable() {
        this.enabled = false;
        
        // 기본 커서로 복원
        this.svg.style.cursor = 'default';
        
        // 진행 중인 그리기 작업 중단
        if (this.isDrawing) {
            this.endDrawing();
        }
    }

    setTool(tool) {
        this.currentTool = tool;
        this.svg.style.cursor = DrawingUtils.createCustomCursor(this.currentTool);

        // 모든 선의 호버 이벤트 업데이트
        const lines = this.svg.querySelectorAll('line:not(.temp-line)');
        lines.forEach(line => {
            this.setupLineHoverEvents(line);
        });
    }

    setLineWidth(width) {
        this.lineWidth = width;
        this.svg.querySelectorAll('line').forEach(line => {
            line.setAttribute('stroke-width', width);
        });
        this.saveState();
    }

    // 점 이동 시작
    startPointMove(e) {
        if (this.currentTool !== 'select') return;
        
        e.preventDefault();
        const mousePoint = DrawingUtils.getMousePosition(e, this.svg);
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        
        // 모든 선의 끝점을 검사하여 마우스와 가까운 점 찾기
        for (const line of lines) {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));
            
            const point1 = { x: x1, y: y1 };
            const point2 = { x: x2, y: y2 };
            
            if (DrawingUtils.calculateDistance(mousePoint, point1) < this.snapDistance) {
                this.selectedPoint = point1;
                this.findConnectedLines(point1);
                this.isDragging = true;
                break;
            } else if (DrawingUtils.calculateDistance(mousePoint, point2) < this.snapDistance) {
                this.selectedPoint = point2;
                this.findConnectedLines(point2);
                this.isDragging = true;
                break;
            }
        }
    }

    // 연결된 모든 선 찾기
    findConnectedLines(point) {
        this.affectedLines.clear();
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        
        for (const line of lines) {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));
            
            if (DrawingUtils.isPointEqual(point, { x: x1, y: y1 })) {
                this.affectedLines.add({ line, isStart: true });
            } else if (DrawingUtils.isPointEqual(point, { x: x2, y: y2 })) {
                this.affectedLines.add({ line, isStart: false });
            }
        }
    }

    // 점 이동
    movePoint(e) {
        if (!this.isDragging || !this.selectedPoint) return;
        
        e.preventDefault();

        // 현재 마우스 위치를 가져옴
        const currentPoint = DrawingUtils.getMousePosition(e, this.svg);
        
        // 스냅 포인트 찾기
        const processedPoint = this.findSnapPoint(currentPoint);

        // 임시 선이 없는 경우에만 생성 (처음 한 번만 생성)
        if (!this.svg.querySelector('.temp-affected-line')) {
            // 연결된 모든 선의 끝점에 대해 임시 선 생성
            for (const { line } of this.affectedLines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                // 임시 선 생성 (원래 위치에 고정)
                const tempLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                tempLine.classList.add('temp-affected-line');
                tempLine.setAttribute('x1', String(x1));
                tempLine.setAttribute('y1', String(y1));
                tempLine.setAttribute('x2', String(x2));
                tempLine.setAttribute('y2', String(y2));
                tempLine.setAttribute('stroke', '#000');
                tempLine.setAttribute('stroke-width', String(this.lineWidth));
                tempLine.setAttribute('opacity', '0.3');
                tempLine.style.pointerEvents = 'none';

                // 임시 선을 SVG에 추가
                this.svg.appendChild(tempLine);
            }
        }

        // 실제 선 업데이트 (이동)
        for (const { line, isStart } of this.affectedLines) {
            if (isStart) {
                line.setAttribute('x1', String(processedPoint.x));
                line.setAttribute('y1', String(processedPoint.y));
            } else {
                line.setAttribute('x2', String(processedPoint.x));
                line.setAttribute('y2', String(processedPoint.y));
            }
        }
        
        this.selectedPoint = processedPoint;
    }

    // 점 이동 종료
    endPointMove() {
        if (this.isDragging) {
            // 임시 선들 제거
            this.svg.querySelectorAll('.temp-affected-line').forEach(line => line.remove());

            // 각 이동된 선에 대해 교차점 처리
            for (const { line } of this.affectedLines) {
                const splitLines = this.processIntersections(line);
                line.remove();
                splitLines.forEach(newLine => {
                    this.applyLineStyle(newLine);
                    this.svg.appendChild(newLine);
                });
            }

            this.isDragging = false;
            this.selectedPoint = null;
            this.affectedLines.clear();

            // 영역 업데이트
            this.updateAreas();
            
            // 상태 저장
            this.saveState();
        }
    }

    // 영역 감지 및 채우기 공통 메서드
    updateAreas() {
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        const closedPaths = this.detectClosedArea(lines) || [];
        const openPath = this.detectOpenArea(lines)|| [];
        
        console.log(`닫힌 영역 감지 결과: ${closedPaths.length}개`, closedPaths);
        
        // 기존 영역 제거
        const existingAreas = Array.from(this.svg.querySelectorAll('.area'));
        for (const area of existingAreas) {
            if (area && area.parentNode) {
                area.remove();
            }
        }
        this.areas = [];
        
        // 새로운 영역 채우기
        for (const path of closedPaths) {
            this.fillArea(path);
        }
        this.fillArea(openPath,true)

        // 길이가 0에 가까운 선분 제거
        this.removeTinyLines();
    }
    
    touchHandler(event) {
        const touch = event.changedTouches[0];
        const simulatedEvent = new MouseEvent({
            touchstart: "mousedown",
            touchmove: "mousemove",
            touchend: "mouseup"
        }[event.type], {
            bubbles: true,
            cancelable: true,
            view: window,
            detail: 1,
            screenX: touch.screenX,
            screenY: touch.screenY,
            clientX: touch.clientX,
            clientY: touch.clientY,
            ctrlKey: false,
            altKey: false,
            shiftKey: false,
            metaKey: false,
            button: 0,
            relatedTarget: null
        });

        touch.target.dispatchEvent(simulatedEvent);
        event.preventDefault();
    }
    // 기존 startDrawing 메서드 수정
    startDrawing(e) {
        if (!this.enabled) return;
        
        e.preventDefault();

        if (this.currentTool === 'select') {
            // 점 이동 시작 시도
            const mousePoint = DrawingUtils.getMousePosition(e, this.svg);
            const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
            
            // 모든 선의 끝점을 검사하여 마우스와 가까운 점 찾기
            for (const line of lines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));
                
                const point1 = { x: x1, y: y1 };
                const point2 = { x: x2, y: y2 };
                
                if (DrawingUtils.calculateDistance(mousePoint, point1) < this.snapDistance) {
                    this.selectedPoint = point1;
                    this.findConnectedLines(point1);
                    this.isDragging = true;
                    return;
                } else if (DrawingUtils.calculateDistance(mousePoint, point2) < this.snapDistance) {
                    this.selectedPoint = point2;
                    this.findConnectedLines(point2);
                    this.isDragging = true;
                    return;
                }
            }
            return;
        }
        
        this.isDrawing = true;
        const point = DrawingUtils.getMousePosition(e, this.svg);
        
        if (this.currentTool === 'line') {
            this.startPoint = this.processPoint(point);
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    // 기존 draw 메서드 수정
    draw(e) {
        if (!this.enabled) return;
        
        e.preventDefault();
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
        
        if (this.currentTool === 'select' && this.isDragging && this.selectedPoint) {
            this.movePoint(e);
            return;
        }
        
        if (!this.isDrawing) return;
        
        const currentPoint = DrawingUtils.getMousePosition(e, this.svg);
        
        if (this.currentTool === 'line' && this.startPoint) {
            const processedPoint = this.processPoint(currentPoint);
            this.drawTempLine(processedPoint);
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    // 선분 분할
    splitLine(line, point) {
        const x1 = parseFloat(line.getAttribute('x1'));
        const y1 = parseFloat(line.getAttribute('y1'));
        const x2 = parseFloat(line.getAttribute('x2'));
        const y2 = parseFloat(line.getAttribute('y2'));

        // 분할점이 선분의 끝점과 같은 경우 분할하지 않음
        if (DrawingUtils.isPointEqual({x: x1, y: y1}, point) || 
            DrawingUtils.isPointEqual({x: x2, y: y2}, point)) {
            return [];
        }

        // 선분의 길이 계산
        const length1 = DrawingUtils.calculateDistance({x: x1, y: y1}, point);
        const length2 = DrawingUtils.calculateDistance(point, {x: x2, y: y2});
        
        const minLength = 1;
        const lines = [];

        if (length1 >= minLength) {
            lines.push(DrawingUtils.createSVGLine(x1, y1, point.x, point.y, this.lineWidth));
        }

        if (length2 >= minLength) {
            lines.push(DrawingUtils.createSVGLine(point.x, point.y, x2, y2, this.lineWidth));
        }

        return lines;
    }

    // 교차점에서 선분 분할 처리
    processIntersections(newLine) {
        const existingLines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        const intersections = [];
        const linesToProcess = new Set([newLine]); // 처리해야 할 선분들
        const processedLines = new Set(); // 이미 처리된 선분들
        const linesToRemove = new Set(); // 제거할 선분들
        const newLines = new Set(); // 새로 추가할 선분들

        // 새로운 선의 시작점과 끝점
        const newX1 = parseFloat(newLine.getAttribute('x1'));
        const newY1 = parseFloat(newLine.getAttribute('y1'));
        const newX2 = parseFloat(newLine.getAttribute('x2'));
        const newY2 = parseFloat(newLine.getAttribute('y2'));

        // 모든 교차점 찾기
        for (const existingLine of existingLines) {
            if (existingLine === newLine) continue;

            const x1 = parseFloat(existingLine.getAttribute('x1'));
            const y1 = parseFloat(existingLine.getAttribute('y1'));
            const x2 = parseFloat(existingLine.getAttribute('x2'));
            const y2 = parseFloat(existingLine.getAttribute('y2'));

            // 새로운 선의 시작점이 기존 선 위에 있는지 확인
            const startPointOnLine = DrawingUtils.projectPointOnLine(
                {x: newX1, y: newY1},
                {x: x1, y: y1},
                {x: x2, y: y2}
            );

            if (startPointOnLine && 
                DrawingUtils.calculateDistance({x: newX1, y: newY1}, startPointOnLine) < 0.1 &&
                DrawingUtils.isPointOnLineSegment(startPointOnLine, {x: x1, y: y1}, {x: x2, y: y2})) {
                intersections.push({
                    point: {x: newX1, y: newY1},
                    existingLine: existingLine
                });
                if (!processedLines.has(existingLine)) {
                    linesToProcess.add(existingLine);
                }
            }

            // 새로운 선의 끝점이 기존 선 위에 있는지 확인
            const endPointOnLine = DrawingUtils.projectPointOnLine(
                {x: newX2, y: newY2},
                {x: x1, y: y1},
                {x: x2, y: y2}
            );

            if (endPointOnLine && 
                DrawingUtils.calculateDistance({x: newX2, y: newY2}, endPointOnLine) < 0.1 &&
                DrawingUtils.isPointOnLineSegment(endPointOnLine, {x: x1, y: y1}, {x: x2, y: y2})) {
                intersections.push({
                    point: {x: newX2, y: newY2},
                    existingLine: existingLine
                });
                if (!processedLines.has(existingLine)) {
                    linesToProcess.add(existingLine);
                }
            }

            // 일반적인 교차점 찾기
            const intersection = DrawingUtils.findIntersection(
                {
                    x1: newX1,
                    y1: newY1,
                    x2: newX2,
                    y2: newY2
                },
                {
                    x1: x1,
                    y1: y1,
                    x2: x2,
                    y2: y2
                }
            );

            if (intersection) {
                // 교차점이 선분의 끝점과 일치하는지 확인
                const isEndPoint = (
                    DrawingUtils.isPointEqual(intersection, {x: newX1, y: newY1}) ||
                    DrawingUtils.isPointEqual(intersection, {x: newX2, y: newY2}) ||
                    DrawingUtils.isPointEqual(intersection, {x: x1, y: y1}) ||
                    DrawingUtils.isPointEqual(intersection, {x: x2, y: y2})
                );

                if (!isEndPoint) {
                    intersections.push({
                        point: intersection,
                        existingLine: existingLine
                    });
                    if (!processedLines.has(existingLine)) {
                        linesToProcess.add(existingLine);
                    }
                }
            }
        }

        if (intersections.length === 0) {
            newLines.add(newLine);
        } else {
            // 교차점들을 선분의 시작점에서부터의 거리순으로 정렬
            const sortIntersectionsByDistance = (line, points) => {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                return points.sort((a, b) => {
                    const distA = Math.pow(a.x - x1, 2) + Math.pow(a.y - y1, 2);
                    const distB = Math.pow(b.x - x1, 2) + Math.pow(b.y - y1, 2);
                    return distA - distB;
                });
            };

            // 각 선분에 대해 처리
            for (const line of linesToProcess) {
                if (processedLines.has(line)) continue;

                // 현재 선분과 관련된 모든 교차점 찾기
                const lineIntersections = intersections
                    .filter(intersection => 
                        intersection.existingLine === line || line === newLine)
                    .map(intersection => intersection.point);

                if (lineIntersections.length === 0) {
                    newLines.add(line);
                    processedLines.add(line);
                    continue;
                }

                // 교차점들을 거리순으로 정렬
                const sortedPoints = sortIntersectionsByDistance(line, lineIntersections);
                
                // 선분의 시작점과 끝점
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                // 모든 점들을 순서대로 연결
                let prevPoint = { x: x1, y: y1 };
                for (const point of sortedPoints) {
                    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') {
                        console.warn('유효하지 않은 교차점:', point);
                        continue;
                    }
                    
                    // 이미 존재하는 선분인지 확인
                    let isDuplicate = false;
                    for (const existingLine of newLines) {
                        const ex1 = parseFloat(existingLine.getAttribute('x1'));
                        const ey1 = parseFloat(existingLine.getAttribute('y1'));
                        const ex2 = parseFloat(existingLine.getAttribute('x2'));
                        const ey2 = parseFloat(existingLine.getAttribute('y2'));

                        if ((DrawingUtils.isPointEqual({x: ex1, y: ey1}, prevPoint) && 
                             DrawingUtils.isPointEqual({x: ex2, y: ey2}, point)) ||
                            (DrawingUtils.isPointEqual({x: ex1, y: ey1}, point) && 
                             DrawingUtils.isPointEqual({x: ex2, y: ey2}, prevPoint))) {
                            isDuplicate = true;
                            break;
                        }
                    }

                    if (!isDuplicate && DrawingUtils.calculateDistance(prevPoint, point) >= 1) {
                        const splitLine = DrawingUtils.createSVGLine(
                            prevPoint.x, prevPoint.y,
                            point.x, point.y,
                            this.lineWidth
                        );
                        newLines.add(splitLine);
                    }
                    prevPoint = point;
                }
                
                // 마지막 교차점에서 선분의 끝점까지
                let isDuplicate = false;
                for (const existingLine of newLines) {
                    const ex1 = parseFloat(existingLine.getAttribute('x1'));
                    const ey1 = parseFloat(existingLine.getAttribute('y1'));
                    const ex2 = parseFloat(existingLine.getAttribute('x2'));
                    const ey2 = parseFloat(existingLine.getAttribute('y2'));

                    if ((DrawingUtils.isPointEqual({x: ex1, y: ey1}, prevPoint) && 
                         DrawingUtils.isPointEqual({x: ex2, y: ey2}, {x: x2, y: y2})) ||
                        (DrawingUtils.isPointEqual({x: ex1, y: ey1}, {x: x2, y: y2}) && 
                         DrawingUtils.isPointEqual({x: ex2, y: ey2}, prevPoint))) {
                        isDuplicate = true;
                        break;
                    }
                }

                if (!isDuplicate && DrawingUtils.calculateDistance(prevPoint, {x: x2, y: y2}) >= 1) {
                    const lastSplitLine = DrawingUtils.createSVGLine(
                        prevPoint.x, prevPoint.y,
                        x2, y2,
                        this.lineWidth
                    );
                    newLines.add(lastSplitLine);
                }

                linesToRemove.add(line);
                processedLines.add(line);
            }
        }

        // 제거할 선분들 제거
        linesToRemove.forEach(line => {
            if (line.parentNode) {
                line.remove();
            }
        });

        // 메모리 정리
        linesToProcess.clear();
        processedLines.clear();
        linesToRemove.clear();

        return Array.from(newLines);
    }

    // 선분을 특정 점에서 분할
    splitLineAtPoint(line, point) {
        const x1 = parseFloat(line.getAttribute('x1'));
        const y1 = parseFloat(line.getAttribute('y1'));
        const x2 = parseFloat(line.getAttribute('x2'));
        const y2 = parseFloat(line.getAttribute('y2'));

        // 분할점이 선분의 끝점과 같은 경우 분할하지 않음
        if (DrawingUtils.isPointEqual({x: x1, y: y1}, point) || 
            DrawingUtils.isPointEqual({x: x2, y: y2}, point)) {
            return [];
        }

        // 선분의 길이 계산
        const length1 = DrawingUtils.calculateDistance({x: x1, y: y1}, point);
        const length2 = DrawingUtils.calculateDistance(point, {x: x2, y: y2});
        
        const minLength = 1;
        const lines = [];

        if (length1 >= minLength) {
            lines.push(DrawingUtils.createSVGLine(x1, y1, point.x, point.y, this.lineWidth));
        }

        if (length2 >= minLength) {
            lines.push(DrawingUtils.createSVGLine(point.x, point.y, x2, y2, this.lineWidth));
        }

        return lines;
    }

    // 기존 endDrawing 메서드 수정
    endDrawing(e) {
        if (!this.enabled) return;
        
        if (e) e.preventDefault();
        
        if (this.currentTool === 'select' && this.isDragging) {
            this.endPointMove();
            return;
        }
        
        if (!this.isDrawing) return;
        
        // 임시 선 제거
        const tempLine = this.svg.querySelector('.temp-line');
        if (tempLine) tempLine.remove();
        
        if (this.currentTool === 'line' && this.startPoint) {
            const currentPoint = e ? DrawingUtils.getMousePosition(e, this.svg) : DrawingUtils.getMousePosition({
                clientX: this.lastMouseX,
                clientY: this.lastMouseY
            }, this.svg);
            const processedEndPoint = this.processPoint(currentPoint);
            
            // 시작점과 끝점이 너무 가까우면 그리지 않음
            const length = DrawingUtils.calculateDistance(this.startPoint, processedEndPoint);
            
            if (length < 1) {
                this.isDrawing = false;
                this.startPoint = null;
                return;
            }
            
            // 새로운 선 생성
            const newLine = DrawingUtils.createSVGLine(
                this.startPoint.x,
                this.startPoint.y,
                processedEndPoint.x,
                processedEndPoint.y,
                this.lineWidth
            );

            // 선 스타일 적용
            this.applyLineStyle(newLine);
            this.svg.appendChild(newLine);

            // 교차점 처리
            const splitLines = this.processIntersections(newLine);
            
            // 원래 선 제거하고 분할된 선들 추가
            newLine.remove();
            splitLines.forEach(line => {
                this.applyLineStyle(line);
                this.svg.appendChild(line);
            });

            // 영역 업데이트
            this.updateAreas();
            
            // 상태 저장
            this.saveState();
        }
        
        this.isDrawing = false;
        this.startPoint = null;
    }

    drawTempLine(currentPoint) {
        const tempLine = this.svg.querySelector('.temp-line');
        if (tempLine) tempLine.remove();
        
        const line = DrawingUtils.createSVGLine(
            this.startPoint.x,
            this.startPoint.y,
            currentPoint.x,
            currentPoint.y,
            this.lineWidth,
            true
        );
        
        // 임시 선에도 마커 적용
        this.applyLineStyle(line);
        
        // 임시 선이 항상 최상위에 표시되도록 설정
        line.style.pointerEvents = 'none';
        line.style.zIndex = '9999';
        
        this.svg.appendChild(line);
    }

    eraseElements(e) {
        const elements = document.elementsFromPoint(e.clientX, e.clientY);
        let hasErased = false;

        elements.forEach(element => {
            if (element instanceof SVGElement && element.tagName === 'line') {
                element.remove();
                hasErased = true;
            }
        });
        if (hasErased) {
            this.mergeLinesAfterErase();
            this.updateAreas();
            this.saveState();
        }
    }

    // 포인트 처리 (스냅 + 각도 스냅)
    processPoint(point) {
        let processedPoint = this.findSnapPoint(point);
        
        if (this.isShiftPressed) {
            processedPoint = DrawingUtils.snapToAngle(processedPoint, this.startPoint);
        }
        
        // viewbox 범위 내로 제한
        processedPoint.x = Math.max(0, Math.min(processedPoint.x, this.svg.viewBox.baseVal.width));
        processedPoint.y = Math.max(0, Math.min(processedPoint.y, this.svg.viewBox.baseVal.height));
        
        return processedPoint;
    }

    // 스냅 포인트 찾기
    findSnapPoint(point) {
        if (this.isAltPressed) return point;

        // 현재 이동 중인 점과 연결된 선들을 제외한 모든 선과 임시선 가져오기
        const affectedLineElements = Array.from(this.affectedLines).map(({ line }) => line);
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'))
            .filter(line => !affectedLineElements.includes(line));
        const tempLines = Array.from(this.svg.querySelectorAll('.temp-affected-line'));
        const allLines = [...lines, ...tempLines];
        
        let closestPoint = point;
        let minDistance = Infinity;

        // 끝점들을 체크
        for (const line of allLines) {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));

            const endPoints = [
                { x: x1, y: y1 },
                { x: x2, y: y2 }
            ];

            for (const snapCandidate of endPoints) {
                const distance = DrawingUtils.calculateDistance(point, snapCandidate);

                if (distance < this.snapDistance && distance < minDistance) {
                    minDistance = distance;
                    closestPoint = snapCandidate;
                }
            }
        }

        // 끝점에 스냅되지 않은 경우에만 선 위의 점을 체크
        if (minDistance === Infinity) {
            for (const line of allLines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                const projectedPoint = DrawingUtils.projectPointOnLine(point, { x: x1, y: y1 }, { x: x2, y: y2 });
                if (projectedPoint && DrawingUtils.isPointOnLineSegment(projectedPoint, { x: x1, y: y1 }, { x: x2, y: y2 })) {
                    const distance = DrawingUtils.calculateDistance(point, projectedPoint);

                    if (distance < this.snapDistance && distance < minDistance) {
                        minDistance = distance;
                        closestPoint = projectedPoint;
                    }
                }
            }
        }

        return closestPoint;
    }

    // 영역 채우기
    fillArea(path, is_exterior = false) {
        if (!path || path.length < 3) return;  // 최소 3개의 점이 필요

        // 유효하지 않은 좌표가 있는지 확인
        const validPath = path.every(point => 
            point && 
            typeof point.x === 'number' && 
            typeof point.y === 'number' && 
            !isNaN(point.x) && 
            !isNaN(point.y)
        );

        if (!validPath) {
            console.warn('유효하지 않은 좌표가 포함된 경로:', path);
            return;
        }

        // 영역이 너무 작으면 무시
        const minArea = 100; // 최소 영역 크기 (픽셀 단위)
        const area = DrawingUtils.calculateArea(path);
        
        if (area < minArea) {
            return;
        }

        try {
            // SVG path 생성
            let pathData;
            const areaElement = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            if (is_exterior) {
                areaElement.setAttribute('fill-rule', 'evenodd');
                areaElement.classList.add('exterior');
                // SVG 뷰포트의 크기 가져오기
                const svgRect = this.svg.getBoundingClientRect();
                const width = 1000;
                const height = 1000;
                
                // 외부 사각형 경로와 내부 홀을 결합
                pathData = `M 0 0 L ${width} 0 L ${width} ${height} L 0 ${height} Z ` + // 외부 사각형
                          'M ' + path[0].x + ' ' + path[0].y + ' ' +  // 시작점
                          path.slice(1).map(point => `L ${point.x} ${point.y}`).join(' ') +
                          ' Z'; // 내부 홀
            } else {
                // 일반적인 내부 영역
                pathData = path.reduce((acc, point, i) => {
                    const command = i === 0 ? 'M' : 'L';
                    return `${acc} ${command} ${point.x} ${point.y}`;
                }, '') + ' Z';
            }
            
            areaElement.setAttribute('d', pathData);
            areaElement.setAttribute('fill', DrawingUtils.generatePastelColor());
            areaElement.setAttribute('fill-opacity', '0.3');
            areaElement.classList.add('area');
            areaElement.setAttribute('stroke', 'none');  // 테두리 없음
            areaElement.style.pointerEvents = 'none';  // 마우스 이벤트 비활성화
            
            // rect와 line 사이에 영역 삽입
            const rect = this.svg.querySelector('rect');
            const line = this.svg.querySelector('line');
            if (rect && line) {
                this.svg.insertBefore(areaElement, line);
            } else {
                this.svg.insertBefore(areaElement, this.svg.firstChild);
            }
            
            this.areas.push(areaElement);
        } catch (error) {
            console.error('영역 생성 중 오류:', error);
        }
    }

    // 선들이 닫힌 영역을 형성하는지 확인
    detectClosedArea(lines) {
        // 그래프 구성을 위한 노드와 엣지 생성
        const nodes = new Map(); // 좌표를 키로 사용하는 노드 맵
        const edges = new Map(); // 노드 간의 연결 정보
        
        // 노드와 엣지 초기화
        lines.forEach((line, lineIndex) => {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));

            const point1 = `${x1},${y1}`;
            const point2 = `${x2},${y2}`;
            
            // 노드 추가
            if (!nodes.has(point1)) nodes.set(point1, { x: x1, y: y1, connections: new Set() });
            if (!nodes.has(point2)) nodes.set(point2, { x: x2, y: y2, connections: new Set() });

            // 엣지 추가
            nodes.get(point1).connections.add(point2);
            nodes.get(point2).connections.add(point1);

            // 선분 정보 저장
            if (!edges.has(point1)) edges.set(point1, new Map());
            if (!edges.has(point2)) edges.set(point2, new Map());
            edges.get(point1).set(point2, lineIndex);
            edges.get(point2).set(point1, lineIndex);
        });

        // 사이클 찾기 함수
        const findCycles = (startNode, currentNode, visited = new Set(), path = [], depth = 0) => {
            const cycles = [];
            const maxDepth = 20; // 최대 깊이 제한
            
            if (depth > maxDepth) return cycles; // 깊이 제한 초과시 종료
            
            path.push(currentNode);
            visited.add(currentNode);

            const node = nodes.get(currentNode);
            if (!node) return cycles;

            for (const nextNode of node.connections) {
                if (nextNode === startNode && path.length >= 3) {
                    // 사이클 발견
                    cycles.push([...path]);
                } else if (!visited.has(nextNode)) {
                    // 다음 노드로 탐색
                    const newCycles = findCycles(startNode, nextNode, new Set(visited), [...path], depth + 1);
                    cycles.push(...newCycles);
                }
            }

            return cycles;
        };

        // 모든 노드에서 시작하여 사이클 찾기
        const allCycles = new Set(); // 중복 제거를 위해 Set 사용

        for (const startNode of nodes.keys()) {
            const cycles = findCycles(startNode, startNode);
            cycles.forEach(cycle => {
                // 좌표 객체 배열로 변환
                const pathPoints = cycle.map(point => {
                    const [x, y] = point.split(',').map(Number);
                    return { x, y };
                });
                
                // 정규화된 사이클 문자열 생성 (정렬된 좌표 문자열)
                const normalizedCycle = pathPoints
                    .map(p => `${p.x},${p.y}`)
                    .sort()
                    .join('|');
                
                allCycles.add(JSON.stringify(pathPoints)); // 전체 경로 객체를 JSON으로 저장
            });
        }

        // Set을 배열로 변환하고 각 사이클 JSON을 다시 객체로 변환
        const pathsFromCycles = Array.from(allCycles).map(cycleJson => JSON.parse(cycleJson));

        // 유효한 경로만 필터링
        const validPaths = pathsFromCycles.filter(path => {
            // 유효하지 않은 좌표 확인
            const hasInvalidCoords = path.some(point => 
                !point || 
                typeof point.x !== 'number' || 
                typeof point.y !== 'number' || 
                isNaN(point.x) || 
                isNaN(point.y)
            );
            
            if (hasInvalidCoords) {
                console.warn('유효하지 않은 좌표가 포함된 경로:', path);
                return false;
            }

            // 최소 크기 검증
            const area = DrawingUtils.calculateArea(path);
            if (area < 10) return false; // 최소 크기 제한

            // 자체 교차 검증
            if (DrawingUtils.hasSelfIntersection(path)) return false;

            // 다른 선분과의 교차 검증
            if (DrawingUtils.hasInvalidIntersections(path, lines)) return false;

            return true;
        });

        // 중복 경로 제거
        const uniquePaths = DrawingUtils.removeDuplicatePaths(validPaths);
        console.log(`전체 경로: ${pathsFromCycles.length}, 유효 경로: ${validPaths.length}, 중복 제거 경로: ${uniquePaths.length}`);
        return uniquePaths;
    }

    detectOpenArea(lines) {
        // 1. 그래프 구성: 노드와 엣지 생성 (기존 함수와 동일)
        const nodes = new Map(); // key: "x,y" 형식의 문자열
        lines.forEach((line) => {
          const x1 = parseFloat(line.getAttribute('x1'));
          const y1 = parseFloat(line.getAttribute('y1'));
          const x2 = parseFloat(line.getAttribute('x2'));
          const y2 = parseFloat(line.getAttribute('y2'));
      
          const point1 = `${x1},${y1}`;
          const point2 = `${x2},${y2}`;
      
          if (!nodes.has(point1)) {
            nodes.set(point1, { x: x1, y: y1, connections: new Set() });
          }
          if (!nodes.has(point2)) {
            nodes.set(point2, { x: x2, y: y2, connections: new Set() });
          }
          nodes.get(point1).connections.add(point2);
          nodes.get(point2).connections.add(point1);
        });
      
        // 2. 각 노드에서 연결된 점들을 각도 순(반시계방향)으로 정렬한다.
        //    (현재 노드에서 각 연결점으로 향하는 벡터의 각도를 이용)
        for (const [key, node] of nodes) {
          const sortedConnections = Array.from(node.connections).sort((a, b) => {
            const [ax, ay] = a.split(',').map(Number);
            const [bx, by] = b.split(',').map(Number);
            const angleA = Math.atan2(ay - node.y, ax - node.x);
            const angleB = Math.atan2(by - node.y, bx - node.x);
            return angleA - angleB;
          });
          node.sortedConnections = sortedConnections;
        }
      
        // 3. 모든 방향성 엣지를 생성한다.
        //    각 무방향 엣지는 두 개의 방향성 엣지로 표현된다.
        const directedEdges = new Set();
        for (const [nodeKey, node] of nodes) {
          for (const conn of node.connections) {
            directedEdges.add(`${nodeKey}->${conn}`);
          }
        }
      
        // 4. 면(face) 추출: 각 방향성 엣지를 따라 면의 경계를 추적한다.
        const visitedEdges = new Set();
        const faces = [];
      
        // 면 추적 알고리즘:
        // 시작 방향성 엣지(de)를 선택하고, 해당 엣지를 따라 면 경계를 추적한다.
        // 각 정점에서는 "뒤쪽(reverse)" 방향에서 바로 다음에 오는 엣지를 선택한다.
        for (const de of directedEdges) {
          if (visitedEdges.has(de)) continue;
          const face = [];
          let currentDE = de;
          while (true) {
            visitedEdges.add(currentDE);
            // currentDE 형식: "currentNode->nextNode"
            const [currentNode, nextNode] = currentDE.split("->");
            face.push(currentNode);
      
            // 현재 엣지의 반대 방향: nextNode -> currentNode
            // nextNode에 도착했으므로, 이 정점에서 현재 엣지(반대 방향)의 위치를 찾고,
            // 그 다음 연결된 엣지를 선택한다.
            const nextNodeObj = nodes.get(nextNode);
            const connections = nextNodeObj.sortedConnections;
            // connections 배열에서 현재 정점(currentNode)의 위치(index)를 찾는다.
            const reverseIndex = connections.findIndex(conn => conn === currentNode);
            if (reverseIndex === -1) {
              console.warn('정점 연결 오류:', nextNode, currentNode);
              break;
            }
            // **면 추적 규칙:** 
            // 정점에서, "현재 엣지(반대 방향)"의 바로 다음 연결선을 선택한다.
            // (정렬된 연결 목록은 반시계 순이므로, 이 규칙에 따라 면의 경계를 따라가게 된다.)
            const nextIndex = (reverseIndex + 1) % connections.length;
            const newNextNode = connections[nextIndex];
      
            // 새 방향성 엣지: nextNode -> newNextNode
            const newDE = `${nextNode}->${newNextNode}`;
            currentDE = newDE;
      
            // 시작 엣지(de)로 돌아오면 면 경로 완성
            if (currentDE === de) break;
          }
          faces.push(face);
        }
      
        // 5. 각 면의 넓이(면적)를 계산하여, 가장 넓은 면을 외부 영역으로 판단한다.
        //    DrawingUtils.calculateArea 는 폴리곤의 넓이를 계산하는 함수라고 가정한다.
        let outerFace = null;
        let maxArea = -Infinity;
        for (const face of faces) {
          // face: 각 점은 "x,y" 문자열이므로 좌표 객체로 변환한다.
          const points = face.map(pt => {
            const [x, y] = pt.split(',').map(Number);
            return { x, y };
          });
          // 면의 넓이(절대값)를 계산
          const area = Math.abs(DrawingUtils.calculateArea(points));
          if (area > maxArea) {
            maxArea = area;
            outerFace = points;
          }
        }
      
        console.log(`총 면 개수: ${faces.length}, 외부 영역의 넓이: ${maxArea}`);
        return outerFace;
      }
      
    // 이어진 선분 병합
    mergeLinesAfterErase() {
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        let merged;
        
        do {
            merged = false;
            for (let i = 0; i < lines.length; i++) {
                for (let j = i + 1; j < lines.length; j++) {
                    const line1 = lines[i];
                    const line2 = lines[j];
                    
                    if (!line1.parentNode || !line2.parentNode) continue;

                    const x1 = parseFloat(line1.getAttribute('x1'));
                    const y1 = parseFloat(line1.getAttribute('y1'));
                    const x2 = parseFloat(line1.getAttribute('x2'));
                    const y2 = parseFloat(line1.getAttribute('y2'));
                    
                    const x3 = parseFloat(line2.getAttribute('x1'));
                    const y3 = parseFloat(line2.getAttribute('y1'));
                    const x4 = parseFloat(line2.getAttribute('x2'));
                    const y4 = parseFloat(line2.getAttribute('y2'));

                    // 기울기가 같은지 먼저 확인
                    if (!DrawingUtils.hasSameSlope(x1, y1, x2, y2, x3, y3, x4, y4)) continue;

                    // 두 선분이 연결되어 있는지 확인 (오차 허용)
                    const tolerance = 0.1;
                    let mergedLine = null;

                    // 각 끝점들의 연결 확인
                    if (Math.abs(x2 - x3) < tolerance && Math.abs(y2 - y3) < tolerance) {
                        mergedLine = { x1, y1, x2: x4, y2: y4 };
                    } else if (Math.abs(x2 - x4) < tolerance && Math.abs(y2 - y4) < tolerance) {
                        mergedLine = { x1, y1, x2: x3, y2: y3 };
                    } else if (Math.abs(x1 - x3) < tolerance && Math.abs(y1 - y3) < tolerance) {
                        mergedLine = { x1: x2, y1: y2, x2: x4, y2: y4 };
                    } else if (Math.abs(x1 - x4) < tolerance && Math.abs(y1 - y4) < tolerance) {
                        mergedLine = { x1: x2, y1: y2, x2: x3, y2: y3 };
                    }

                    if (mergedLine) {
                        // 병합된 선분을 임시로 생성
                        const tempLine = DrawingUtils.createSVGLine(
                            mergedLine.x1,
                            mergedLine.y1,
                            mergedLine.x2,
                            mergedLine.y2,
                            this.lineWidth
                        );

                        // 교차점이 없는 경우에만 병합
                        const allLines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
                        if (!DrawingUtils.hasIntersectionWithOtherLines(tempLine, allLines, [line1, line2])) {
                            const newLine = tempLine;
                            
                            this.svg.appendChild(newLine);
                            line1.remove();
                            line2.remove();
                            
                            // lines 배열 업데이트
                            lines[i] = newLine;
                            lines.splice(j, 1);
                            
                            merged = true;
                            break;
                        }
                    }
                }
                if (merged) break;
            }
        } while (merged);
    }

    // 매우 짧은 선분 제거
    removeTinyLines() {
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        const minLength = 0.4; // 최소 길이 (픽셀 단위)
        
        for (const line of lines) {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));
            
            // 선분의 길이 계산
            const length = DrawingUtils.calculateDistance(
                { x: x1, y: y1 },
                { x: x2, y: y2 }
            );
            
            // 최소 길이보다 짧은 선분 제거
            if (length < minLength) {
                line.remove();
            }
        }
    }

    // 선에 마커와 스타일을 적용하는 헬퍼 메서드
    applyLineStyle(line) {
        // 기본 마커와 스타일 적용 (모든 도구에서 공통)
        line.setAttribute('marker-start', 'url(#defaultEndpoint)');
        line.setAttribute('marker-end', 'url(#defaultEndpoint)');
        line.classList.add('endpoint-line');
        line.style.strokeWidth = this.lineWidth;
        line.style.stroke = '#000';

        // 호버 이벤트 리스너 추가
        this.setupLineHoverEvents(line);
    }

    // 마우스 포인터가 선의 끝점 근처인지 확인하는 메서드
    isNearLineEndpoint(e) {
        const mousePoint = DrawingUtils.getMousePosition(e, this.svg);
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        
        for (const line of lines) {
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));
            
            const point1 = { x: x1, y: y1 };
            const point2 = { x: x2, y: y2 };
            
            if (DrawingUtils.calculateDistance(mousePoint, point1) < this.snapDistance ||
                DrawingUtils.calculateDistance(mousePoint, point2) < this.snapDistance) {
                return true;
            }
        }
        return false;
    }

    // 선의 호버 이벤트 설정을 위한 메서드 수정
    setupLineHoverEvents(line) {
        // 기존 이벤트 리스너 제거
        const clone = line.cloneNode(true);
        line.parentNode?.replaceChild(clone, line);
        line = clone;

        // 선택 도구일 때 호버 효과와 커서 스타일 적용
        if (this.currentTool === 'select') {
            // 호버 이벤트 리스너 추가
            line.addEventListener('mouseenter', (e) => {
                const point = DrawingUtils.getMousePosition(e, this.svg);
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));
                
                const distToStart = DrawingUtils.calculateDistance(point, {x: x1, y: y1});
                const distToEnd = DrawingUtils.calculateDistance(point, {x: x2, y: y2});
                
                if (distToStart < this.snapDistance || distToEnd < this.snapDistance) {
                    line.style.cursor = 'move';
                    if (distToStart < this.snapDistance) {
                        line.setAttribute('marker-start', 'url(#hoverEndpoint)');
                    }
                    if (distToEnd < this.snapDistance) {
                        line.setAttribute('marker-end', 'url(#hoverEndpoint)');
                    }
                } else {
                    line.style.cursor = 'default';
                }
            });
            
            line.addEventListener('mouseleave', () => {
                line.setAttribute('marker-start', 'url(#defaultEndpoint)');
                line.setAttribute('marker-end', 'url(#defaultEndpoint)');
                line.style.cursor = 'default';
            });
        }

        return line;
    }
} 