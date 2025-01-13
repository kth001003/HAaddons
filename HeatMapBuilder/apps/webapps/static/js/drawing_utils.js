// SVG 관련 유틸리티 함수들
export class DrawingUtils {
    // 점 관련 유틸리티
    static isPointEqual(p1, p2, tolerance = 0.1) {
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
        const hue = Math.floor(Math.random() * 360);
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
} 