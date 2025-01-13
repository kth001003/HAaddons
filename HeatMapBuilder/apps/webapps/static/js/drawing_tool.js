import { DrawingUtils } from './drawing_utils.js';

export class DrawingTool {
    constructor(svgElement) {
        this.svg = svgElement;
        this.isDrawing = false;
        this.currentTool = 'line';
        this.lineWidth = 10;
        this.startPoint = null;
        this.enabled = false;
        this.isShiftPressed = false;
        this.isAltPressed = false;
        this.snapDistance = 20;
        this.history = [''];  // 초기 빈 상태
        this.currentHistoryIndex = 0;
        this.maxHistoryLength = 50; // 최대 실행취소 횟수
        this.areas = []; // 감지된 영역들을 저장

        // 이벤트 리스너 바인딩
        this.startDrawing = this.startDrawing.bind(this);
        this.draw = this.draw.bind(this);
        this.endDrawing = this.endDrawing.bind(this);
        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleKeyUp = this.handleKeyUp.bind(this);
        this.undo = this.undo.bind(this);
        this.redo = this.redo.bind(this);
        this.clear = this.clear.bind(this);

        // SVG 이벤트 리스너 등록
        this.svg.addEventListener('mousedown', this.startDrawing);
        this.svg.addEventListener('mousemove', this.draw);
        this.svg.addEventListener('mouseup', this.endDrawing);
        this.svg.addEventListener('mouseleave', this.endDrawing);

        // 키보드 이벤트 리스너 등록
        document.addEventListener('keydown', this.handleKeyDown);
        document.addEventListener('keyup', this.handleKeyUp);

        // 실행취소/다시실행 버튼 이벤트 리스너 등록
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');
        if (undoBtn) undoBtn.addEventListener('click', this.undo);
        if (redoBtn) redoBtn.addEventListener('click', this.redo);

        // 초기 상태 저장
        this.saveState();
    }
    // 현재 상태 저장
    saveState() {
        // 현재 인덱스 이후의 기록 제거
        this.history = this.history.slice(0, this.currentHistoryIndex + 1);
        
        // 새로운 상태 추가
        this.history.push(this.svg.innerHTML);
        
        // 최대 길이 제한
        if (this.history.length > this.maxHistoryLength) {
            this.history = this.history.slice(this.history.length - this.maxHistoryLength);
        }
        
        this.currentHistoryIndex = this.history.length - 1;
        this.updateUndoRedoButtons();
    }

    // 실행취소
    undo() {
        if (!this.enabled) return;
        if (this.currentHistoryIndex > 0) {
            this.currentHistoryIndex--;
            this.svg.innerHTML = this.history[this.currentHistoryIndex];
            this.updateUndoRedoButtons();
        }
    }

    // 다시실행
    redo() {
        if (!this.enabled) return;
        if (this.currentHistoryIndex < this.history.length - 1) {
            this.currentHistoryIndex++;
            this.svg.innerHTML = this.history[this.currentHistoryIndex];
            this.updateUndoRedoButtons();
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

    // 초기화
    clear() {
        if (!this.enabled) return;
        if (confirm('모든 벽을 삭제하시겠습니까?')) {
            this.svg.innerHTML = '';
            this.areas = [];
            this.history = [''];
            this.currentHistoryIndex = 0;
            this.saveState();
        }
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
                const currentPoint = this.getMousePosition({
                    clientX: this.lastMouseX,
                    clientY: this.lastMouseY
                });
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
                const currentPoint = this.getMousePosition({
                    clientX: this.lastMouseX,
                    clientY: this.lastMouseY
                });
                this.drawTempLine(this.processPoint(currentPoint));
            }
        }
    }

    // 15도 단위로 각도 스냅
    snapToAngle(point) {
        if (!this.isShiftPressed || !this.startPoint) return point;

        const dx = point.x - this.startPoint.x;
        const dy = point.y - this.startPoint.y;
        const angle = Math.atan2(dy, dx);
        const distance = Math.sqrt(dx * dx + dy * dy);

        // 15도 단위로 반올림
        const snapAngle = Math.round(angle / (Math.PI / 12)) * (Math.PI / 12);

        return {
            x: this.startPoint.x + Math.cos(snapAngle) * distance,
            y: this.startPoint.y + Math.sin(snapAngle) * distance
        };
    }

    enable() {
        this.enabled = true;
        
        // 커스텀 커서 설정
        const cursorSvg = `
            <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>
                <line x1='0' y1='12' x2='24' y2='12' stroke='white' stroke-width='3'/>
                <line x1='12' y1='0' x2='12' y2='24' stroke='white' stroke-width='3'/>
                <line x1='0' y1='12' x2='24' y2='12' stroke='black' stroke-width='1'/>
                <line x1='12' y1='0' x2='12' y2='24' stroke='black' stroke-width='1'/>
            </svg>`;
        
        const cursorUrl = `data:image/svg+xml;base64,${btoa(cursorSvg)}`;
        this.svg.style.cursor = `url('${cursorUrl}') 12 12, crosshair`;
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
    }

    setLineWidth(width) {
        this.lineWidth = width;
    }

    startDrawing(e) {
        if (!this.enabled) return;
        
        e.preventDefault();
        this.isDrawing = true;
        const point = DrawingUtils.getMousePosition(e, this.svg);
        
        if (this.currentTool === 'line') {
            this.startPoint = this.processPoint(point);
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    draw(e) {
        if (!this.enabled || !this.isDrawing) return;
        
        e.preventDefault();
        
        // 마우스 위치 저장
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
        
        const currentPoint = DrawingUtils.getMousePosition(e, this.svg);
        
        if (this.currentTool === 'line' && this.startPoint) {
            const processedPoint = this.processPoint(currentPoint);
            this.drawTempLine(processedPoint);
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    // 두 선분의 교차점 계산
    findIntersection(line1, line2) {
        const x1 = line1.x1;
        const y1 = line1.y1;
        const x2 = line1.x2;
        const y2 = line1.y2;
        
        const x3 = line2.x1;
        const y3 = line2.y1;
        const x4 = line2.x2;
        const y4 = line2.y2;

        // 평행한 경우 처리
        const denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
        if (Math.abs(denominator) < 0.001) return null;

        const ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denominator;
        const ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denominator;

        // 선분 내부에 교차점이 있는 경우만 반환
        if (ua >= -0.1 && ua <= 1.1 && ub >= -0.1 && ub <= 1.1) {
            const x = x1 + ua * (x2 - x1);
            const y = y1 + ua * (y2 - y1);
            
            // 좌표를 소수점 둘째 자리까지 유지하여 정밀도 문제 방지
            return {
                x: Math.round(x * 100) / 100,
                y: Math.round(y * 100) / 100
            };
        }

        return null;
    }

    // 선분 분할
    splitLine(line, point) {
        const x1 = parseFloat(line.getAttribute('x1'));
        const y1 = parseFloat(line.getAttribute('y1'));
        const x2 = parseFloat(line.getAttribute('x2'));
        const y2 = parseFloat(line.getAttribute('y2'));

        // 점이 다른 선과 연결되어 있는지 확인하는 함수
        const isPointConnected = (px, py) => {
            const existingLines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
            let connectionCount = 0;
            
            for (const otherLine of existingLines) {
                if (otherLine === line) continue;
                
                const ox1 = parseFloat(otherLine.getAttribute('x1'));
                const oy1 = parseFloat(otherLine.getAttribute('y1'));
                const ox2 = parseFloat(otherLine.getAttribute('x2'));
                const oy2 = parseFloat(otherLine.getAttribute('y2'));
                
                // 점과 선의 끝점 사이의 거리가 허용 오차 이내인지 확인
                const tolerance = 1.0;
                if ((Math.abs(px - ox1) < tolerance && Math.abs(py - oy1) < tolerance) ||
                    (Math.abs(px - ox2) < tolerance && Math.abs(py - oy2) < tolerance)) {
                    connectionCount++;
                }
            }
            // 2개 이상의 선과 연결되어 있어야 true 반환
            return connectionCount >= 2;
        };

        const minLength = 10; // 최소 선분 길이
        const tinyLength = 5; // 매우 작은 길이 기준
        const lines = [];

        // 첫 번째 선분 길이 확인
        const length1 = DrawingUtils.calculateDistance({x: x1, y: y1}, point);
        const isPoint1Connected = isPointConnected(x1, y1);
        const isIntersectionPointConnected = isPointConnected(point.x, point.y);

        if (length1 >= minLength || (length1 >= tinyLength && (isPoint1Connected || isIntersectionPointConnected))) {
            lines.push(DrawingUtils.createSVGLine(x1, y1, point.x, point.y, this.lineWidth));
        }

        // 두 번째 선분 길이 확인
        const length2 = DrawingUtils.calculateDistance(point, {x: x2, y: y2});
        const isPoint2Connected = isPointConnected(x2, y2);

        if (length2 >= minLength || (length2 >= tinyLength && (isPoint2Connected || isIntersectionPointConnected))) {
            lines.push(DrawingUtils.createSVGLine(point.x, point.y, x2, y2, this.lineWidth));
        }

        return lines;
    }

    // 교차점에서 선분 분할 처리
    processIntersections(newLine) {
        let currentLines = [newLine];
        const existingLines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        const intersections = [];

        // 모든 교차점 찾기
        for (const existingLine of existingLines) {
            const intersection = this.findIntersection(
                {
                    x1: parseFloat(newLine.getAttribute('x1')),
                    y1: parseFloat(newLine.getAttribute('y1')),
                    x2: parseFloat(newLine.getAttribute('x2')),
                    y2: parseFloat(newLine.getAttribute('y2'))
                },
                {
                    x1: parseFloat(existingLine.getAttribute('x1')),
                    y1: parseFloat(existingLine.getAttribute('y1')),
                    x2: parseFloat(existingLine.getAttribute('x2')),
                    y2: parseFloat(existingLine.getAttribute('y2'))
                }
            );

            if (intersection) {
                intersections.push({
                    point: intersection,
                    existingLine: existingLine
                });
            }
        }

        // 교차점들을 선분의 시작점에서부터의 거리순으로 정렬
        intersections.sort((a, b) => {
            const distA = Math.pow(a.point.x - parseFloat(newLine.getAttribute('x1')), 2) +
                         Math.pow(a.point.y - parseFloat(newLine.getAttribute('y1')), 2);
            const distB = Math.pow(b.point.x - parseFloat(newLine.getAttribute('x1')), 2) +
                         Math.pow(b.point.y - parseFloat(newLine.getAttribute('y1')), 2);
            return distA - distB;
        });

        // 각 교차점에서 선분들 분할
        for (const intersection of intersections) {
            // 현재 선분들을 교차점에서 분할
            const newSplitLines = [];
            for (const line of currentLines) {
                const splitLines = this.splitLineAtPoint(line, intersection.point);
                if (splitLines.length > 0) {
                    newSplitLines.push(...splitLines);
                } else {
                    newSplitLines.push(line);
                }
            }
            currentLines = newSplitLines;

            // 기존 선분 분할
            const splitExistingLines = this.splitLineAtPoint(intersection.existingLine, intersection.point);
            if (splitExistingLines.length > 0) {
                // 기존 선분을 DOM에서 제거
                this.svg.removeChild(intersection.existingLine);
                
                // 분할된 선분들을 DOM에 추가
                splitExistingLines.forEach(line => {
                    this.svg.appendChild(line);
                });
            }
        }

        return currentLines;
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

    endDrawing(e) {
        if (!this.enabled || !this.isDrawing) return;
        
        if (e) e.preventDefault();
        
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
            this.svg.appendChild(newLine);

            // 교차점 처리
            const splitLines = this.processIntersections(newLine);
            
            // 원래 선 제거하고 분할된 선들 추가
            newLine.remove();
            splitLines.forEach(line => this.svg.appendChild(line));

            // 닫힌 영역 감지 및 채우기
            const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
            const closedPaths = this.detectClosedArea(lines) || [];
            
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

            // 사용자 행동 완료 후 상태 저장
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
        this.svg.appendChild(line);
    }

    eraseElements(e) {
        const elements = document.elementsFromPoint(e.clientX, e.clientY);
        let hasErased = false;
        let erasedLines = [];

        elements.forEach(element => {
            if (element instanceof SVGElement) {
                if (element.tagName === 'path') {
                    element.remove();
                    hasErased = true;
                } else if (element.tagName === 'line') {
                    erasedLines.push(element);
                    element.remove();
                    hasErased = true;
                }
            }
        });

        // 선분이 지워졌다면 병합 처리 수행
        if (erasedLines.length > 0) {
            this.mergeLinesAfterErase();
        }

        // 요소가 지워졌을 때만 상태 저장
        if (hasErased) {
            this.saveState();
        }
    }

    // 선분이 다른 선분들과 교차하는지 확인
    hasIntersectionWithOtherLines(testLine, excludeLines = []) {
        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        
        for (const line of lines) {
            if (excludeLines.includes(line) || line === testLine) continue;
            
            const x1 = parseFloat(line.getAttribute('x1'));
            const y1 = parseFloat(line.getAttribute('y1'));
            const x2 = parseFloat(line.getAttribute('x2'));
            const y2 = parseFloat(line.getAttribute('y2'));
            
            const intersection = DrawingUtils.findIntersection(
                {
                    x1: parseFloat(testLine.getAttribute('x1')),
                    y1: parseFloat(testLine.getAttribute('y1')),
                    x2: parseFloat(testLine.getAttribute('x2')),
                    y2: parseFloat(testLine.getAttribute('y2'))
                },
                { x1, y1, x2, y2 }
            );

            if (intersection) {
                const testLinePoints = [
                    { x: parseFloat(testLine.getAttribute('x1')), y: parseFloat(testLine.getAttribute('y1')) },
                    { x: parseFloat(testLine.getAttribute('x2')), y: parseFloat(testLine.getAttribute('y2')) }
                ];
                const linePoints = [
                    { x: x1, y: y1 },
                    { x: x2, y: y2 }
                ];

                if (!DrawingUtils.isPointOnEndpoints(intersection, testLinePoints) && 
                    !DrawingUtils.isPointOnEndpoints(intersection, linePoints)) {
                    return true;
                }
            }
        }
        return false;
    }

    // 점을 선에 투영
    projectPointOnLine(point, lineStart, lineEnd) {
        const dx = lineEnd.x - lineStart.x;
        const dy = lineEnd.y - lineStart.y;
        const lineLength = Math.sqrt(dx * dx + dy * dy);
        
        if (lineLength === 0) return null;

        const t = (
            ((point.x - lineStart.x) * dx + (point.y - lineStart.y) * dy) /
            (lineLength * lineLength)
        );

        // 선분 범위 내에 있는지 확인
        if (t < 0 || t > 1) return null;

        return {
            x: lineStart.x + t * dx,
            y: lineStart.y + t * dy
        };
    }

    // 포인트 처리 (스냅 + 각도 스냅)
    processPoint(point) {
        let processedPoint = this.findSnapPoint(point);
        
        if (this.isShiftPressed) {
            processedPoint = this.snapToAngle(processedPoint);
        }
        
        return processedPoint;
    }

    // 스냅 포인트 찾기
    findSnapPoint(point) {
        if (this.isAltPressed) return point;

        const lines = Array.from(this.svg.querySelectorAll('line:not(.temp-line)'));
        let closestPoint = point;
        let minDistance = Infinity;

        // 끝점들을 체크
        for (const line of lines) {
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
            for (const line of lines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                const projectedPoint = DrawingUtils.projectPointOnLine(point, { x: x1, y: y1 }, { x: x2, y: y2 });
                if (projectedPoint) {
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

    // 경로의 면적 계산
    calculateArea(path) {
        let area = 0;
        for (let i = 0; i < path.length; i++) {
            const j = (i + 1) % path.length;
            area += path[i].x * path[j].y;
            area -= path[j].x * path[i].y;
        }
        return Math.abs(area) / 2;
    }

    // 자체 교차 검사
    hasSelfIntersection(path) {
        for (let i = 0; i < path.length; i++) {
            const p1 = path[i];
            const p2 = path[(i + 1) % path.length];
            
            for (let j = i + 2; j < path.length; j++) {
                const p3 = path[j];
                const p4 = path[(j + 1) % path.length];
                
                if (i === 0 && j === path.length - 1) continue; // 시작점과 끝점 연결은 무시
                
                if (DrawingUtils.doLinesIntersect(p1, p2, p3, p4)) {
                    return true;
                }
            }
        }
        return false;
    }

    // 두 선분의 교차 여부 확인
    doLinesIntersect(p1, p2, p3, p4) {
        const ccw = (A, B, C) => {
            return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x);
        };
        
        return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && 
               ccw(p1, p2, p3) !== ccw(p1, p2, p4);
    }

    // 다른 선분과의 유효하지 않은 교차 검사
    hasInvalidIntersections(path, lines) {
        for (let i = 0; i < path.length; i++) {
            const p1 = path[i];
            const p2 = path[(i + 1) % path.length];

            for (const line of lines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                // 현재 경로를 구성하는 선분은 건너뛰기
                if (DrawingUtils.isPointEqual(p1, { x: x1, y: y1 }) && DrawingUtils.isPointEqual(p2, { x: x2, y: y2 }) ||
                    DrawingUtils.isPointEqual(p1, { x: x2, y: y2 }) && DrawingUtils.isPointEqual(p2, { x: x1, y: y1 })) {
                    continue;
                }

                const intersection = DrawingUtils.findIntersection(
                    { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y },
                    { x1, y1, x2, y2 }
                );

                if (intersection && 
                    !DrawingUtils.isPointEqual(intersection, p1) && 
                    !DrawingUtils.isPointEqual(intersection, p2) &&
                    !DrawingUtils.isPointEqual(intersection, { x: x1, y: y1 }) &&
                    !DrawingUtils.isPointEqual(intersection, { x: x2, y: y2 })) {
                        return true;
                    }
                }
            }
            return false;
    }

    // 중복 경로 제거
    removeDuplicatePaths(paths) {
        const uniquePaths = [];
        for (const path of paths) {
            let isDuplicate = false;
            for (const existingPath of uniquePaths) {
                if (this.arePathsEqual(path, existingPath)) {
                    isDuplicate = true;
                    break;
                }
            }
            if (!isDuplicate) {
                uniquePaths.push(path);
            }
        }
        return uniquePaths;
    }

    // 두 경로가 같은지 확인
    arePathsEqual(path1, path2) {
        if (path1.length !== path2.length) return false;

        // 모든 가능한 시작점에 대해 비교
        for (let start = 0; start < path1.length; start++) {
            let isEqual = true;
            for (let i = 0; i < path1.length; i++) {
                const p1 = path1[i];
                const p2 = path2[(start + i) % path2.length];
                if (!DrawingUtils.isPointEqual(p1, p2)) {
                    isEqual = false;
                    break;
                }
            }
            if (isEqual) return true;
        }
        return false;
    }

    // 영역 채우기
    fillArea(path) {
        if (!path || path.length < 3) return;  // 최소 3개의 점이 필요

        // path가 이미 좌표 객체 배열인 경우 처리
        const points = path.map(point => {
            if (typeof point === 'string') {
                return point.split(',').map(Number);
            }
            return [point.x, point.y];
        });
        
        // 영역이 너무 작으면 무시
        const minArea = 100; // 최소 영역 크기 (픽셀 단위)
        const area = DrawingUtils.calculateArea(path);
        
        if (area < minArea) {
            return;
        }

        try {
            // SVG path 생성
            const pathData = points.reduce((acc, [x, y], i) => {
                return acc + (i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
            }, '') + ' Z';
            
            const areaElement = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            areaElement.setAttribute('d', pathData);
            areaElement.setAttribute('fill', DrawingUtils.generatePastelColor());
            areaElement.setAttribute('fill-opacity', '0.3');
            areaElement.setAttribute('class', 'area');
            areaElement.setAttribute('stroke', 'none');  // 테두리 없음
            
            // 영역을 선 뒤에 삽입 (맨 뒤로)
            this.svg.insertBefore(areaElement, this.svg.firstChild);
            
            this.areas.push(areaElement);
        } catch (error) {
            console.error('영역 생성 중 오류:', error);
        }
    }

    // 파스텔 색상 생성
    generatePastelColor() {
        const hue = Math.floor(Math.random() * 360);
        return `hsl(${hue}, 70%, 80%)`;
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
        const findCycles = (startNode, currentNode, visited = new Set(), path = []) => {
            const cycles = [];
            visited.add(currentNode);
            path.push(currentNode);

            const node = nodes.get(currentNode);
            for (const nextNode of node.connections) {
                if (nextNode === startNode && path.length >= 3) {
                    // 사이클 발견
                    cycles.push([...path]);
                } else if (!visited.has(nextNode)) {
                    // 다음 노드로 탐색
                    const newCycles = findCycles(startNode, nextNode, visited, path);
                    cycles.push(...newCycles);
                }
            }

            visited.delete(currentNode);
            path.pop();
            return cycles;
        };

        // 모든 노드에서 시작하여 사이클 찾기
        const allCycles = [];
        for (const startNode of nodes.keys()) {
            const cycles = findCycles(startNode, startNode);
            allCycles.push(...cycles);
        }

        // 사이클을 좌표 객체 배열로 변환
        const pathsFromCycles = allCycles.map(cycle => 
            cycle.map(point => {
                const [x, y] = point.split(',').map(Number);
                return { x, y };
            })
        );

        // 유효한 경로만 필터링
        const validPaths = pathsFromCycles.filter(path => {
            // 최소 크기 검증
            const area = DrawingUtils.calculateArea(path);
            if (area < 100) return false; // 최소 크기 제한

            // 자체 교차 검증
            if (this.hasSelfIntersection(path)) return false;

            // 다른 선분과의 교차 검증
            if (this.hasInvalidIntersections(path, lines)) return false;

            return true;
        });

        // 중복 경로 제거
        const uniquePaths = this.removeDuplicatePaths(validPaths);
        console.log(`전체 경로: ${pathsFromCycles.length}, 유효 경로: ${validPaths.length}, 중복 제거 경로: ${uniquePaths.length}`);
        return uniquePaths;
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
                        if (!this.hasIntersectionWithOtherLines(tempLine, [line1, line2])) {
                            const newLine = DrawingUtils.createSVGLine(
                                mergedLine.x1,
                                mergedLine.y1,
                                mergedLine.x2,
                                mergedLine.y2,
                                this.lineWidth
                            );
                            
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

    getMousePosition(e) {
        const rect = this.svg.getBoundingClientRect();
        const point = this.svg.createSVGPoint();
        point.x = e.clientX;
        point.y = e.clientY;
        
        // SVG 좌표계로 변환
        const matrix = this.svg.getScreenCTM();
        if (matrix) {
            const transformedPoint = point.matrixTransform(matrix.inverse());
            return {
                x: transformedPoint.x,
                y: transformedPoint.y
            };
        }
        
        // fallback: 간단한 좌표 계산
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }
} 