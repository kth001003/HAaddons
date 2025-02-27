export class WebSocketDebugger {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.sendWebsocketDebug = document.getElementById('send-websocket-debug');
        this.clearWebsocketResult = document.getElementById('clear-websocket-result');
        this.websocketResult = document.getElementById('websocket-result');
        this.websocketMessageType = /** @type {HTMLInputElement} */ (document.getElementById('websocket-message-type'));
        this.websocketParams = /** @type {HTMLTextAreaElement} */ (document.getElementById('websocket-params'));

        this.initialize();
    }

    initialize() {
        if (this.sendWebsocketDebug && this.clearWebsocketResult && this.websocketResult) {
            this.sendWebsocketDebug.addEventListener('click', () => this.sendDebugRequest());
            this.clearWebsocketResult.addEventListener('click', () => this.clearResult());
        }
    }

    async sendDebugRequest() {
        try {
            const messageType = this.websocketMessageType.value.trim();
            if (!messageType) {
                this.uiManager.showMessage('메시지 타입을 입력해주세요.', 'error');
                return;
            }

            let kwargs = {};
            const paramsText = this.websocketParams.value.trim();
            if (paramsText) {
                try {
                    kwargs = JSON.parse(paramsText);
                } catch (e) {
                    this.uiManager.showMessage('파라미터 JSON 형식이 올바르지 않습니다.', 'error');
                    return;
                }
            }

            const response = await fetch('./api/debug-websocket', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message_type: messageType,
                    kwargs: kwargs
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                this.websocketResult.textContent = JSON.stringify(data.result, null, 2);
                this.uiManager.showMessage('WebSocket 디버그 요청이 성공했습니다.', 'success');
            } else {
                this.websocketResult.textContent = JSON.stringify(data, null, 2);
                this.uiManager.showMessage(data.error || 'WebSocket 디버그 요청이 실패했습니다.', 'error');
            }
        } catch (error) {
            this.uiManager.showMessage('WebSocket 디버그 요청 중 오류가 발생했습니다.', 'error');
        }
    }

    clearResult() {
        if (this.websocketResult) {
            this.websocketResult.textContent = '';
            this.uiManager.showMessage('결과를 지웠습니다.', 'success');
        }
    }
} 