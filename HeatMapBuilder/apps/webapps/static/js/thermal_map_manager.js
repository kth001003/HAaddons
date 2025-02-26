export class ThermalMapManager {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.mapId = new URLSearchParams(window.location.search).get('id');
        this.thermalMapImage = /** @type {HTMLImageElement} */ (document.getElementById('thermal-map-img'));
        this.mapGenerationTime = document.getElementById('map-generation-time');
        this.mapGenerationDuration = document.getElementById('map-generation-duration');
        this.mapGenerationButton = /** @type {HTMLButtonElement} */ (document.getElementById('generate-now'));
        this.copyImageUrlBtn = document.getElementById('copy-image-url');

        // 이전 생성 이미지 관련 요소들
        this.previousMapImage = /** @type {HTMLImageElement} */ (document.getElementById('previous-map-image'));
        this.previousMapEmptyDiv = document.getElementById('previous-map-empty');
        this.previousMapLoading = document.getElementById('previous-map-loading');
        this.previousMapInfo = document.getElementById('previous-map-info');
        this.currentImageIndex = document.getElementById('current-image-index');
        this.totalImages = document.getElementById('total-images');
        this.currentImageDate = document.getElementById('current-image-date');
        this.prevImageBtn = /** @type {HTMLButtonElement} */ (document.getElementById('prev-image-btn'));
        this.nextImageBtn = /** @type {HTMLButtonElement} */ (document.getElementById('next-image-btn'));

        // 이전 생성 이미지 데이터
        this.previousMaps = [];
        this.currentIndex = 0;
        
        this.initialize();
    }

    initialize() {
        if (this.mapGenerationButton) {
            this.mapGenerationButton.addEventListener('click', () => this.refreshThermalMap());
        }

        if (this.copyImageUrlBtn) {
            this.copyImageUrlBtn.addEventListener('click', () => this.copyImageUrl());
        }

        // 이전 생성 이미지 버튼 이벤트 리스너
        if (this.prevImageBtn) {
            this.prevImageBtn.addEventListener('click', () => this.showPreviousImage());
        }
        
        if (this.nextImageBtn) {
            this.nextImageBtn.addEventListener('click', () => this.showNextImage());
        }

        // 초기 이전 생성 이미지 데이터 로드
        this.loadPreviousMaps();

        // 10초마다 지도 자동 새로고침
        setInterval(() => this.checkAndRefreshMap(), 10000);
    }

    async refreshThermalMap() {
        if (!this.mapGenerationButton || !this.mapId) {
            this.uiManager.showMessage('맵 ID가 없습니다.', 'error');
            return;
        }

        this.uiManager.showMessage('지도 생성 중..');
        this.mapGenerationButton.children[0].classList.add('animate-spin');

        try {
            const response = await fetch(`./api/generate-map/${this.mapId}`);
            const data = await response.json();

            if (data.status === 'success') {
                const timestamp = new Date().getTime();
                this.thermalMapImage.setAttribute('src', `${data.img_url}?t=${timestamp}`);
                
                if (this.mapGenerationTime) {
                    this.mapGenerationTime.textContent = data.time;
                }
                if (this.mapGenerationDuration) {
                    this.mapGenerationDuration.textContent = data.duration;
                }
                
                this.uiManager.showMessage('지도를 새로 생성했습니다.', 'success');
                
                // 새 지도가 생성되면 이전 이미지 목록 다시 로드
                this.loadPreviousMaps();
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
        if (!this.mapGenerationButton || !this.mapId) {
            return;
        }

        try {
            const response = await fetch(`./api/check-map-time/${this.mapId}`);
            const data = await response.json();

            if (data.status === 'success' && data.time) {
                const serverTime = new Date(data.time).getTime();
                const currentDisplayTime = this.mapGenerationTime ? 
                    new Date(this.mapGenerationTime.textContent).getTime() : 0;

                if (serverTime > currentDisplayTime) {
                    const timestamp = new Date().getTime();
                    this.thermalMapImage.setAttribute('src', `${data.img_url}?t=${timestamp}`);
                    
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

    /**
     * 이전 생성 이미지 목록을 로드합니다.
     */
    async loadPreviousMaps() {
        if (!this.previousMapImage) return;
        
        try {
            this.showPreviousMapLoading(true);
            
            // URL에서 맵 ID 추출
            const urlParams = new URLSearchParams(window.location.search);
            const mapId = urlParams.get('id');
            
            if (!mapId) {
                console.error('맵 ID를 찾을 수 없습니다.');
                this.showEmptyPreviousMap();
                return;
            }
            
            // 새로운 API 엔드포인트 사용
            const response = await fetch(`./api/maps/${mapId}/previous-maps`);
            const data = await response.json();
            
            if (data.status === 'success') {
                this.previousMaps = data.previous_maps || [];
                
                if (this.previousMaps.length > 0) {
                    // 이미지가 있으면 첫 번째 이미지 표시
                    this.currentIndex = 0;
                    this.updatePreviousMapDisplay();
                } else {
                    // 이미지가 없으면 빈 메시지 표시
                    this.showEmptyPreviousMap();
                }
            } else {
                console.error('이전 맵 로드 실패:', data.error);
                this.showEmptyPreviousMap();
            }
        } catch (error) {
            console.error('이전 맵 로드 중 오류:', error);
            this.showEmptyPreviousMap();
        } finally {
            this.showPreviousMapLoading(false);
        }
    }
    
    /**
     * 이전 이미지 표시
     */
    showPreviousImage() {
        if (this.currentIndex > 0) {
            this.currentIndex--;
            this.updatePreviousMapDisplay();
        }
    }
    
    /**
     * 다음 이미지 표시
     */
    showNextImage() {
        if (this.currentIndex < this.previousMaps.length - 1) {
            this.currentIndex++;
            this.updatePreviousMapDisplay();
        }
    }
    
    /**
     * 이전 맵 표시 업데이트
     */
    updatePreviousMapDisplay() {
        if (this.previousMaps.length === 0) {
            this.showEmptyPreviousMap();
            return;
        }
        
        const current = this.previousMaps[this.currentIndex];
        
        // 이미지 표시
        this.previousMapImage.src = current.url;
        this.previousMapImage.classList.remove('hidden');
        
        if (this.previousMapEmptyDiv) {
            this.previousMapEmptyDiv.classList.add('hidden');
        }
        
        // 인덱스 정보 업데이트
        if (this.currentImageIndex) {
            this.currentImageIndex.textContent = (this.currentIndex + 1).toString();
        }
        
        if (this.totalImages) {
            this.totalImages.textContent = this.previousMaps.length.toString();
        }
        
        if (this.currentImageDate) {
            this.currentImageDate.textContent = current.date;
        }
        
        if (this.previousMapInfo) {
            this.previousMapInfo.classList.remove('hidden');
        }
        
        // 버튼 활성화/비활성화
        this.updateNavigationButtons();
    }
    
    /**
     * 빈 이전 맵 메시지 표시
     */
    showEmptyPreviousMap() {
        if (this.previousMapImage) {
            this.previousMapImage.classList.add('hidden');
        }
        
        if (this.previousMapEmptyDiv) {
            this.previousMapEmptyDiv.classList.remove('hidden');
        }
        
        if (this.previousMapInfo) {
            this.previousMapInfo.classList.add('hidden');
        }
        
        // 버튼 비활성화
        if (this.prevImageBtn) {
            this.prevImageBtn.disabled = true;
        }
        
        if (this.nextImageBtn) {
            this.nextImageBtn.disabled = true;
        }
    }
    
    /**
     * 로딩 상태 표시
     */
    showPreviousMapLoading(show) {
        if (this.previousMapLoading) {
            if (show) {
                this.previousMapLoading.classList.remove('hidden');
            } else {
                this.previousMapLoading.classList.add('hidden');
            }
        }
    }
    
    /**
     * 네비게이션 버튼 활성화/비활성화
     */
    updateNavigationButtons() {
        if (this.prevImageBtn) {
            this.prevImageBtn.disabled = this.currentIndex <= 0;
        }
        
        if (this.nextImageBtn) {
            this.nextImageBtn.disabled = this.currentIndex >= this.previousMaps.length - 1;
        }
    }
} 