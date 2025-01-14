// SVG 관련 유틸리티 함수들
export class DrawingUtils {
    // 이전에 사용된 색상들을 저장할 정적 배열
    static usedHues = [];

    // 점 관련 유틸리티
    static isPointEqual(p1, p2, tolerance = 0.5) {
        return Math.abs(p1.x - p2.x) < tolerance && Math.abs(p1.y - p2.y) < tolerance;
    }

    static isPointOnEndpoints(point, endpoints, tolerance = 0.1) {
        return endpoints.some(endpoint => this.isPointEqual(point, endpoint, tolerance));
    }

    static calculateDistance(p1, p2) {
        return Math.sqrt(Math.pow(p2.x - p1.x, 2) + Math.pow(p2.y - p1.y, 2));
    }

    // SVG 요소 생성 유틸리티
    static createSVGLine(x1, y1, x2, y2, lineWidth, isTemp = false) {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(x1));
        line.setAttribute('y1', String(y1));
        line.setAttribute('x2', String(x2));
        line.setAttribute('y2', String(y2));
        line.setAttribute('stroke', 'black');
        line.setAttribute('stroke-width', String(lineWidth));
        if (isTemp) line.classList.add('temp-line');
        return line;
    }

    // 색상 관련 유틸리티
    static generatePastelColor() {
        const minHueDifference = 30; // 최소 색상 차이 (도)
        let hue;
        let attempts = 0;
        const maxAttempts = 12; // 최대 시도 횟수

        do {
            hue = Math.floor(Math.random() * 360);
            attempts++;

            // 모든 이전 색상과 충분한 차이가 있는지 확인
            const isUnique = this.usedHues.every(usedHue => {
                const diff = Math.min(
                    Math.abs(hue - usedHue),
                    360 - Math.abs(hue - usedHue)
                );
                return diff >= minHueDifference;
            });

            if (isUnique || attempts >= maxAttempts) {
                this.usedHues.push(hue);
                // 너무 많은 색상이 저장되지 않도록 관리
                if (this.usedHues.length > 12) {
                    this.usedHues.shift(); // 가장 오래된 색상 제거
                }
                break;
            }
        } while (attempts < maxAttempts);

        return `hsl(${hue}, 70%, 80%)`;
    }

    // 기하학 관련 유틸리티
    static calculateArea(path) {
        let area = 0;
        for (let i = 0; i < path.length; i++) {
            const j = (i + 1) % path.length;
            area += path[i].x * path[j].y;
            area -= path[j].x * path[i].y;
        }
        return Math.abs(area) / 2;
    }

    static doLinesIntersect(p1, p2, p3, p4) {
        const ccw = (A, B, C) => {
            return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x);
        };
        
        return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && 
               ccw(p1, p2, p3) !== ccw(p1, p2, p4);
    }

    static findIntersection(line1, line2) {
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
            
            return {
                x: Math.round(x * 100) / 100,
                y: Math.round(y * 100) / 100
            };
        }

        return null;
    }

    static projectPointOnLine(point, lineStart, lineEnd) {
        const dx = lineEnd.x - lineStart.x;
        const dy = lineEnd.y - lineStart.y;
        const lineLength = Math.sqrt(dx * dx + dy * dy);
        
        if (lineLength === 0) return null;

        const t = (
            ((point.x - lineStart.x) * dx + (point.y - lineStart.y) * dy) /
            (lineLength * lineLength)
        );

        if (t < 0 || t > 1) return null;

        return {
            x: lineStart.x + t * dx,
            y: lineStart.y + t * dy
        };
    }

    // 마우스/SVG 좌표 변환 유틸리티
    static getMousePosition(e, svg) {
        const rect = svg.getBoundingClientRect();
        const point = svg.createSVGPoint();
        point.x = e.clientX;
        point.y = e.clientY;
        
        // SVG 좌표계로 변환
        const matrix = svg.getScreenCTM();
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

    // 선분 기울기 관련 유틸리티
    static hasSameSlope(x1, y1, x2, y2, x3, y3, x4, y4, tolerance = 0.1) {
        // 수직선 처리
        const isVertical1 = Math.abs(x2 - x1) < tolerance;
        const isVertical2 = Math.abs(x4 - x3) < tolerance;
        
        if (isVertical1 && isVertical2) return true;
        if (isVertical1 || isVertical2) return false;
        
        const slope1 = (y2 - y1) / (x2 - x1);
        const slope2 = (y4 - y3) / (x4 - x3);
        
        return Math.abs(slope1 - slope2) < tolerance;
    }

    // 각도 스냅 유틸리티
    static snapToAngle(point, startPoint) {
        if (!startPoint) return point;

        const dx = point.x - startPoint.x;
        const dy = point.y - startPoint.y;
        const angle = Math.atan2(dy, dx);
        const distance = Math.sqrt(dx * dx + dy * dy);

        // 15도 단위로 반올림
        const snapAngle = Math.round(angle / (Math.PI / 12)) * (Math.PI / 12);

        return {
            x: startPoint.x + Math.cos(snapAngle) * distance,
            y: startPoint.y + Math.sin(snapAngle) * distance
        };
    }

    // 경로의 중심점을 계산하는 유틸리티
    static calculatePathCenter(path) {
        let sumX = 0;
        let sumY = 0;
        
        for (const point of path) {
            sumX += point.x;
            sumY += point.y;
        }
        
        return {
            x: sumX / path.length,
            y: sumY / path.length
        };
    }

    // 경로 중복 제거 유틸리티
    static removeDuplicatePaths(paths) {
        // 1단계: 완전히 동일한 경로 제거
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
        console.log("완전중복제거후 갯수", uniquePaths.length);

        // 2단계: 양쪽 끝이 연결된 선분들의 중점 중 하나라도 path 내부에 있는 경우 제거
        const result = [];
        const allLines = Array.from(document.querySelectorAll('line'));
        
        // 각 선분의 끝점들을 수집
        const endpoints = new Set();
        allLines.forEach(line => {
            endpoints.add(`${line.getAttribute('x1')},${line.getAttribute('y1')}`);
            endpoints.add(`${line.getAttribute('x2')},${line.getAttribute('y2')}`);
        });

        // 양쪽 끝이 연결된 선분들만 필터링하여 중점 수집
        const midpoints = allLines
            .filter(line => {
                const start = `${line.getAttribute('x1')},${line.getAttribute('y1')}`;
                const end = `${line.getAttribute('x2')},${line.getAttribute('y2')}`;
                
                // 시작점과 끝점이 다른 선분과 공유되는지 확인
                let startConnected = false;
                let endConnected = false;
                
                allLines.forEach(otherLine => {
                    if (otherLine === line) return;
                    
                    const otherStart = `${otherLine.getAttribute('x1')},${otherLine.getAttribute('y1')}`;
                    const otherEnd = `${otherLine.getAttribute('x2')},${otherLine.getAttribute('y2')}`;
                    
                    if (start === otherStart || start === otherEnd) startConnected = true;
                    if (end === otherStart || end === otherEnd) endConnected = true;
                });
                
                return startConnected && endConnected;
            })
            .map(line => ({
                x: (parseFloat(line.getAttribute('x1')) + parseFloat(line.getAttribute('x2'))) / 2,
                y: (parseFloat(line.getAttribute('y1')) + parseFloat(line.getAttribute('y2'))) / 2
            }));
            
        pathLoop: for (const path of uniquePaths) {
            // 각 path에 대해 모든 lines의 중점을 검사
            for (const midpoint of midpoints) {
                // 중점이 path 내부에 있는지 확인
                if (this.isPointInPath(midpoint, path)) {
                    // 내부에 중점이 있는 경우 이 path는 제외
                    continue pathLoop;
                }
            }
            
            // 어떤 line의 중점도 내부에 없는 path만 추가
            console.log("중점 없는 path 추가", path);
            result.push(path);
        }

        return result;
    }

    // 점이 경로 내부에 있는지 확인하는 유틸리티
    static isPointInPath(point, path) {
        // 선분 위의 점인지 먼저 확인
        for (let i = 0; i < path.length; i++) {
            const start = path[i];
            const end = path[(i + 1) % path.length];
            
            if (this.isPointOnLineSegment(point, start, end)) {
                return false;
            }
        }
        
        // Ray casting algorithm으로 내부 점 확인
        let inside = false;
        for (let i = 0, j = path.length - 1; i < path.length; j = i++) {
            const xi = path[i].x, yi = path[i].y;
            const xj = path[j].x, yj = path[j].y;
            
            const intersect = ((yi > point.y) !== (yj > point.y)) &&
                (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        console.log("내부 점 확인", inside);
        return inside;
    }

    // 경로 비교 유틸리티
    static arePathsEqual(path1, path2) {
        if (path1.length !== path2.length) return false;

        // 정방향 비교
        for (let start = 0; start < path1.length; start++) {
            let isEqual = true;
            for (let i = 0; i < path1.length; i++) {
                const p1 = path1[i];
                const p2 = path2[(start + i) % path2.length];
                if (!this.isPointEqual(p1, p2)) {
                    isEqual = false;
                    break;
                }
            }
            if (isEqual) return true;
        }

        // 역방향 비교
        const reversedPath2 = [...path2].reverse();
        for (let start = 0; start < path1.length; start++) {
            let isEqual = true;
            for (let i = 0; i < path1.length; i++) {
                const p1 = path1[i];
                const p2 = reversedPath2[(start + i) % path2.length];
                if (!this.isPointEqual(p1, p2)) {
                    isEqual = false;
                    break;
                }
            }
            if (isEqual) return true;
        }

        return false;
    }

    // 커스텀 커서 SVG 생성 유틸리티
    static createCustomCursor() {
        const cursorSvg = `
            <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>
                <line x1='0' y1='12' x2='24' y2='12' stroke='black' stroke-width='3'/>
                <line x1='12' y1='0' x2='12' y2='24' stroke='black' stroke-width='3'/>
                <line x1='0' y1='12' x2='24' y2='12' stroke='white' stroke-width='1'/>
                <line x1='12' y1='0' x2='12' y2='24' stroke='white' stroke-width='1'/>
            </svg>`;
        
        const cursorUrl = `data:image/svg+xml;base64,${btoa(cursorSvg)}`;
        return `url('${cursorUrl}') 12 12, crosshair`;
    }

    // 자체 교차 검사 유틸리티
    static hasSelfIntersection(path) {
        for (let i = 0; i < path.length; i++) {
            const p1 = path[i];
            const p2 = path[(i + 1) % path.length];
            
            for (let j = i + 2; j < path.length; j++) {
                const p3 = path[j];
                const p4 = path[(j + 1) % path.length];
                
                if (i === 0 && j === path.length - 1) continue; // 시작점과 끝점 연결은 무시
                
                if (this.doLinesIntersect(p1, p2, p3, p4)) {
                    return true;
                }
            }
        }
        return false;
    }

    // 유효하지 않은 교차 검사 유틸리티
    static hasInvalidIntersections(path, lines) {
        for (let i = 0; i < path.length; i++) {
            const p1 = path[i];
            const p2 = path[(i + 1) % path.length];

            for (const line of lines) {
                const x1 = parseFloat(line.getAttribute('x1'));
                const y1 = parseFloat(line.getAttribute('y1'));
                const x2 = parseFloat(line.getAttribute('x2'));
                const y2 = parseFloat(line.getAttribute('y2'));

                // 현재 경로를 구성하는 선분은 건너뛰기
                if (this.isPointEqual(p1, { x: x1, y: y1 }) && this.isPointEqual(p2, { x: x2, y: y2 }) ||
                    this.isPointEqual(p1, { x: x2, y: y2 }) && this.isPointEqual(p2, { x: x1, y: y1 })) {
                    continue;
                }

                const intersection = this.findIntersection(
                    { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y },
                    { x1, y1, x2, y2 }
                );

                if (intersection && 
                    !this.isPointEqual(intersection, p1) && 
                    !this.isPointEqual(intersection, p2) &&
                    !this.isPointEqual(intersection, { x: x1, y: y1 }) &&
                    !this.isPointEqual(intersection, { x: x2, y: y2 })) {
                        return true;
                    }
            }
        }
        return false;
    }

    // 선분이 다른 선분들과 교차하는지 확인하는 유틸리티
    static hasIntersectionWithOtherLines(testLine, allLines, excludeLines = []) {
        const x1 = parseFloat(testLine.getAttribute('x1'));
        const y1 = parseFloat(testLine.getAttribute('y1'));
        const x2 = parseFloat(testLine.getAttribute('x2'));
        const y2 = parseFloat(testLine.getAttribute('y2'));

        for (const line of allLines) {
            if (line === testLine || excludeLines.includes(line)) continue;

            const x3 = parseFloat(line.getAttribute('x1'));
            const y3 = parseFloat(line.getAttribute('y1'));
            const x4 = parseFloat(line.getAttribute('x2'));
            const y4 = parseFloat(line.getAttribute('y2'));

            const intersection = this.findIntersection(
                { x1, y1, x2, y2 },
                { x1: x3, y1: y3, x2: x4, y2: y4 }
            );

            if (intersection) return true;
        }

        return false;
    }

    // 점이 선분 위에 있는지 확인하는 메서드
    static isPointOnLineSegment(point, lineStart, lineEnd) {
        // 점이 선분의 시작점과 끝점 사이에 있는지 확인
        const d1 = this.calculateDistance(point, lineStart);
        const d2 = this.calculateDistance(point, lineEnd);
        const lineLength = this.calculateDistance(lineStart, lineEnd);
        
        // 부동소수점 오차를 고려한 비교
        const tolerance = 0.1;
        return Math.abs(d1 + d2 - lineLength) < tolerance;
    }
} 