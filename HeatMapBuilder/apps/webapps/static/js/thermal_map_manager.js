export class ThermalMapManager {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.thermalMapImage = /** @type {HTMLImageElement} */ (document.getElementById('thermal-map-img'));
        this.mapGenerationTime = document.getElementById('map-generation-time');
        this.mapGenerationDuration = document.getElementById('map-generation-duration');
        this.mapGenerationButton = /** @type {HTMLButtonElement} */ (document.getElementById('generate-now'));
        this.copyImageUrlBtn = document.getElementById('copy-image-url');

        this.initialize();
    }

    initialize() {
        if (this.mapGenerationButton) {
            this.mapGenerationButton.addEventListener('click', () => this.refreshThermalMap());
        }

        if (this.copyImageUrlBtn) {
            this.copyImageUrlBtn.addEventListener('click', () => this.copyImageUrl());
        }

        // 10초마다 지도 자동 새로고침
        setInterval(() => this.checkAndRefreshMap(), 10000);
    }

    async refreshThermalMap() {
        if (!this.mapGenerationButton) {
            return;
        }

        this.uiManager.showMessage('지도 생성 중..');
        this.mapGenerationButton.children[0].classList.add('animate-spin');

        try {
            const response = await fetch('./api/generate-map');
            const data = await response.json();

            if (data.status === 'success') {
                const timestamp = new Date().getTime();
                this.thermalMapImage.setAttribute('src', `${data.image_url}?t=${timestamp}`);
                
                if (this.mapGenerationTime) {
                    this.mapGenerationTime.textContent = data.time;
                }
                if (this.mapGenerationDuration) {
                    this.mapGenerationDuration.textContent = data.duration;
                }
                
                this.uiManager.showMessage('지도를 새로 생성했습니다.', 'success');
            } else {
                this.uiManager.showMessage(data.error || '지도 생성에 실패했습니다.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.uiManager.showMessage('지도 생성 중 오류가 발생했습니다.', 'error');
        }

        this.mapGenerationButton.children[0].classList.remove('animate-spin');
    }

    async checkAndRefreshMap() {
        if (!this.mapGenerationButton) {
            return;
        }

        try {
            const response = await fetch('./api/check-map-time');
            const data = await response.json();

            if (data.status === 'success' && data.generation_time) {
                const serverTime = new Date(data.generation_time).getTime();
                const currentDisplayTime = this.mapGenerationTime ? 
                    new Date(this.mapGenerationTime.textContent).getTime() : 0;

                if (serverTime > currentDisplayTime) {
                    const timestamp = new Date().getTime();
                    this.thermalMapImage.setAttribute('src', `${data.image_url}?t=${timestamp}`);
                    
                    if (this.mapGenerationTime) {
                        this.mapGenerationTime.textContent = data.time;
                    }
                    if (this.mapGenerationDuration) {
                        this.mapGenerationDuration.textContent = data.duration;
                    }
                }
            }
        } catch (error) {
            console.error('지도 시간 확인 중 오류:', error);
        }
    }

    copyImageUrl() {
        if (!this.copyImageUrlBtn) return;

        let url = new URL(this.copyImageUrlBtn.dataset.url, window.location.href).href;
        url = url.split('?')[0];
        
        navigator.clipboard.writeText(url)
            .then(() => {
                this.uiManager.showMessage('이미지 주소가 복사되었습니다.', 'success');
            })
            .catch(() => {
                this.uiManager.showMessage('이미지 주소 복사에 실패했습니다.', 'error');
            });
    }
} 