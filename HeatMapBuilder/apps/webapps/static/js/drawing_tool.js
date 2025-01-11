class DrawingTool {
    constructor(svgElement) {
        this.svg = svgElement;
        this.isDrawing = false;
        this.currentTool = 'line';
        this.lineWidth = 10;
        this.startPoint = null;
        this.enabled = true;
        this.isShiftPressed = false;
        this.history = [''];  // 초기 빈 상태
        this.currentHistoryIndex = 0;
        this.maxHistoryLength = 50; // 최대 실행취소 횟수

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

        // 실행취소, 다시실행, 초기화 버튼 이벤트 리스너 등록
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');
        const clearBtn = document.getElementById('clear-btn');
        if (undoBtn) undoBtn.addEventListener('click', this.undo);
        if (redoBtn) redoBtn.addEventListener('click', this.redo);
        if (clearBtn) clearBtn.addEventListener('click', this.clear);

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
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');
        
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
            this.history = [''];
            this.currentHistoryIndex = 0;
            this.saveState();
        }
    }

    handleKeyDown(e) {
        if (e.key === 'Shift') {
            this.isShiftPressed = true;
            // 현재 그리고 있는 선이 있다면 업데이트
            if (this.isDrawing && this.startPoint) {
                const tempLine = this.svg.querySelector('.temp-line');
                if (tempLine) {
                    const currentPoint = this.getMousePosition({
                        clientX: this.lastMouseX,
                        clientY: this.lastMouseY
                    });
                    this.drawTempLine(this.snapToAngle(currentPoint));
                }
            }
        } else if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
            // Ctrl+Z (Windows) 또는 Cmd+Z (Mac) 실행취소
            e.preventDefault();
            if (e.shiftKey) {
                // Ctrl+Shift+Z 또는 Cmd+Shift+Z: 다시실행
                this.redo();
            } else {
                // Ctrl+Z 또는 Cmd+Z: 실행취소
                this.undo();
            }
        } else if (e.key === 'y' && (e.ctrlKey || e.metaKey)) {
            // Ctrl+Y (Windows) 또는 Cmd+Y (Mac) 다시실행
            e.preventDefault();
            this.redo();
        }
    }

    handleKeyUp(e) {
        if (e.key === 'Shift') {
            this.isShiftPressed = false;
            // 현재 그리고 있는 선이 있다면 업데이트
            if (this.isDrawing && this.startPoint) {
                const tempLine = this.svg.querySelector('.temp-line');
                if (tempLine) {
                    const currentPoint = this.getMousePosition({
                        clientX: this.lastMouseX,
                        clientY: this.lastMouseY
                    });
                    this.drawTempLine(currentPoint);
                }
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
        this.svg.style.pointerEvents = 'auto';
    }

    disable() {
        this.enabled = false;
        this.svg.style.pointerEvents = 'none';
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
        this.isDrawing = true;
        const point = this.getMousePosition(e);
        
        if (this.currentTool === 'line') {
            this.startPoint = point;
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    draw(e) {
        if (!this.enabled || !this.isDrawing) return;
        
        // 마우스 위치 저장
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
        
        const currentPoint = this.getMousePosition(e);
        
        if (this.currentTool === 'line' && this.startPoint) {
            // Shift 키가 눌려있으면 15도 단위로 스냅
            const snapPoint = this.isShiftPressed ? this.snapToAngle(currentPoint) : currentPoint;
            this.drawTempLine(snapPoint);
        } else if (this.currentTool === 'eraser') {
            this.eraseElements(e);
        }
    }

    endDrawing(e) {
        if (!this.enabled || !this.isDrawing) return;
        
        if (this.currentTool === 'line' && this.startPoint) {
            const currentPoint = this.getMousePosition(e);
            // Shift 키가 눌려있으면 15도 단위로 스냅
            const snapPoint = this.isShiftPressed ? this.snapToAngle(currentPoint) : currentPoint;
            this.drawFinalLine(snapPoint);
        }
        
        this.isDrawing = false;
        this.startPoint = null;
    }

    drawTempLine(currentPoint) {
        // 임시 선 업데이트
        const tempLine = this.svg.querySelector('.temp-line');
        if (tempLine) tempLine.remove();
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(this.startPoint.x));
        line.setAttribute('y1', String(this.startPoint.y));
        line.setAttribute('x2', String(currentPoint.x));
        line.setAttribute('y2', String(currentPoint.y));
        line.setAttribute('stroke', 'black');
        line.setAttribute('stroke-width', String(this.lineWidth));
        line.classList.add('temp-line');
        this.svg.appendChild(line);
    }

    drawFinalLine(endPoint) {
        // 임시 선 제거
        const tempLine = this.svg.querySelector('.temp-line');
        if (tempLine) tempLine.remove();
        
        // 최종 선 그리기
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(this.startPoint.x));
        line.setAttribute('y1', String(this.startPoint.y));
        line.setAttribute('x2', String(endPoint.x));
        line.setAttribute('y2', String(endPoint.y));
        line.setAttribute('stroke', 'black');
        line.setAttribute('stroke-width', String(this.lineWidth));
        this.svg.appendChild(line);

        // 상태 저장
        this.saveState();
    }

    eraseElements(e) {
        const elements = document.elementsFromPoint(e.clientX, e.clientY);
        let hasErased = false;
        elements.forEach(element => {
            if (element instanceof SVGElement && (element.tagName === 'path' || element.tagName === 'line')) {
                element.remove();
                hasErased = true;
            }
        });
        // 요소가 지워졌을 때만 상태 저장
        if (hasErased) {
            this.saveState();
        }
    }

    getMousePosition(e) {
        const rect = this.svg.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }
} 