export class ThermalMapManager {
    constructor(uiManager) {
        this.uiManager = uiManager;
        this.mapId = new URLSearchParams(window.location.search).get('id');
        this.thermalMapImage = /** @type {HTMLImageElement} */ (document.getElementById('thermal-map-img'));
        this.mapGenerationTime = document.getElementById('map-generation-time');
        this.mapGenerationElapsed = document.getElementById('map-generation-elapsed');
        this.mapGenerationDuration = document.getElementById('map-generation-duration');
        this.nextGenerationTime = document.getElementById('next-generation-time');
        this.nextGenerationRemaining = document.getElementById('next-generation-remaining');
        this.autoGenerationStatus = document.getElementById('auto-generation-status');
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
        this.deleteImageBtn = /** @type {HTMLButtonElement} */ (document.getElementById('delete-image-btn'));

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
        
        // 이미지 삭제 버튼 이벤트 리스너
        if (this.deleteImageBtn) {
            this.deleteImageBtn.addEventListener('click', () => this.confirmDeleteCurrentImage());
        }

        // 초기 이전 생성 이미지 데이터 로드
        this.loadPreviousMaps();

        // 10초마다 지도 자동 새로고침
        setInterval(() => this.checkAndRefreshMap(), 10000);
        
        // 1분마다 경과 시간 업데이트
        setInterval(() => this.updateElapsedTime(), 60000);
        
        // 초기 상태 업데이트
        this.updateAutoGenerationStatus();
        this.updateElapsedTime();
        this.updateNextGenerationTime();
    }

    async updateAutoGenerationStatus() {
        if (!this.mapId || !this.autoGenerationStatus) return;

        try {
            const response = await fetch(`./api/load-config/${this.mapId}`);
            const config = await response.json();
            const autoGeneration = config.gen_config?.auto_generation || false;
            
            this.autoGenerationStatus.textContent = autoGeneration ? '켜짐' : '꺼짐';
            this.autoGenerationStatus.className = 'font-medium ' + 
                (autoGeneration ? 'text-green-600' : 'text-gray-500');
        } catch (error) {
            this.uiManager.showMessage(`자동생성 상태 확인 중 오류: ${error}`, 'error');
            this.autoGenerationStatus.textContent = '확인 실패';
            this.autoGenerationStatus.className = 'font-medium text-red-500';
        }
    }

    updateElapsedTime() {
        if (!this.mapGenerationTime || !this.mapGenerationElapsed) return;

        const generationTime = new Date(this.mapGenerationTime.textContent);
        if (isNaN(generationTime.getTime())) {
            this.mapGenerationElapsed.textContent = '';
            return;
        }

        const now = new Date();
        const diffMinutes = Math.floor((now.getTime() - generationTime.getTime()) / (60 * 1000));
        
        if (diffMinutes < 1) {
            this.mapGenerationElapsed.textContent = '(방금 전)';
        } else if (diffMinutes < 60) {
            this.mapGenerationElapsed.textContent = `(${diffMinutes}분 전)`;
        } else {
            const hours = Math.floor(diffMinutes / 60);
            if (hours < 24) {
                this.mapGenerationElapsed.textContent = `(${hours}시간 전)`;
            } else {
                const days = Math.floor(hours / 24);
                this.mapGenerationElapsed.textContent = `(${days}일 전)`;
            }
        }
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
                
                // 경과 시간 초기화
                this.updateElapsedTime();
                
                // 다음 생성 예정 시각 업데이트
                this.updateNextGenerationTime();
                
                // 자동생성 상태 업데이트
                this.updateAutoGenerationStatus();
                
                this.uiManager.showMessage('지도를 새로 생성했습니다.', 'success');
                
                // 새 지도가 생성되면 이전 이미지 목록 다시 로드
                this.loadPreviousMaps();
            } else {
                this.uiManager.showMessage(data.error || '지도 생성에 실패했습니다.', 'error');
            }
        } catch (error) {
            this.uiManager.showMessage('지도 생성 중 오류가 발생했습니다.', 'error');
        }

        this.mapGenerationButton.children[0].classList.remove('animate-spin');
    }

    async checkAndRefreshMap() {
        if (!this.mapId) return;

        try {
            const response = await fetch(`./api/check-map-time/${this.mapId}`);
            const data = await response.json();

            if (data.status === 'success') {
                // 이미지 URL이 변경되었다면 이미지 새로고침
                if (this.thermalMapImage && data.img_url && this.thermalMapImage.src.split('?')[0] !== data.img_url.split('?')[0]) {
                    this.thermalMapImage.src = data.img_url;
                }
                
                // 생성 시간과 소요 시간 업데이트
                if (this.mapGenerationTime && data.time) {
                    this.mapGenerationTime.textContent = data.time;
                    this.updateElapsedTime();
                }
                if (this.mapGenerationDuration && data.duration) {
                    this.mapGenerationDuration.textContent = data.duration;
                }
                
                // 다음 생성 예정 시간 업데이트
                this.updateNextGenerationTime();
            }
        } catch (error) {
            this.uiManager.showMessage(`지도 시간 확인 중 오류: ${error}`, 'error');
        }
    }

    async updateNextGenerationTime() {
        if (!this.mapId || !this.nextGenerationTime || !this.mapGenerationTime) return;

        try {
            // 맵 설정 로드
            const response = await fetch(`./api/load-config/${this.mapId}`);
            const config = await response.json();
     
            // 자동 생성 여부 가져오기
            const autoGeneration = config.gen_config?.auto_generation || false;
            if (!autoGeneration) {
                this.nextGenerationTime.textContent = '자동생성 꺼져있음';
                if (this.nextGenerationRemaining) {
                    this.nextGenerationRemaining.textContent = '';
                }
                return;
            }
            
            // 생성 주기 (분) 가져오기
            const genInterval = config.gen_config?.gen_interval || 15;
            
            // 마지막 생성 시각
            const lastGenTime = new Date(this.mapGenerationTime.textContent);
            if (isNaN(lastGenTime.getTime())) {
                this.nextGenerationTime.textContent = '시간 정보 없음';
                if (this.nextGenerationRemaining) {
                    this.nextGenerationRemaining.textContent = '';
                }
                return;
            }
            
            // 다음 생성 예정 시각 계산
            const nextGenTime = new Date(lastGenTime.getTime() + genInterval * 60 * 1000);
            
            // 현재 시각과의 차이 계산
            const now = new Date();
            const diffMinutes = Math.round((nextGenTime.getTime() - now.getTime()) / (60 * 1000));
            
            // 표시
            if (diffMinutes <= 0) {
                this.nextGenerationTime.textContent = '곧 생성';
                if (this.nextGenerationRemaining) {
                    this.nextGenerationRemaining.textContent = '';
                }
            } else {
                this.nextGenerationTime.textContent = nextGenTime.toLocaleTimeString();
                if (this.nextGenerationRemaining) {
                    this.nextGenerationRemaining.textContent = `(${diffMinutes}분 후)`;
                }
            }
        } catch (error) {
            this.uiManager.showMessage(`다음 생성 시각 계산 중 오류: ${error}`, 'error');
            this.nextGenerationTime.textContent = '계산 오류';
            if (this.nextGenerationRemaining) {
                this.nextGenerationRemaining.textContent = '';
            }
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
                this.uiManager.showMessage('맵 ID를 찾을 수 없습니다.', 'error');
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
                this.uiManager.showMessage(`이전 맵 로드 실패: ${data.error}`, 'error');
                this.showEmptyPreviousMap();
            }
        } catch (error) {
            this.uiManager.showMessage(`이전 맵 로드 중 오류: ${error}`, 'error');
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

    /**
     * 현재 이미지 삭제 확인 대화상자 표시
     */
    confirmDeleteCurrentImage() {
        if (this.previousMaps.length === 0 || this.currentIndex < 0 || this.currentIndex >= this.previousMaps.length) {
            return;
        }
        
        const currentMap = this.previousMaps[this.currentIndex];
        const imageDateText = currentMap.date;
        
        // 모달 확인 창 표시
        this.uiManager.showConfirmModal(
            '이미지 삭제 확인',
            `${imageDateText}에 생성된 이미지를 삭제하시겠습니까?`,
            () => this.deleteCurrentImage(),
            null,
            '삭제',
            'bg-red-500 hover:bg-red-600'
        );
    }
    
    /**
     * 현재 이미지 삭제
     */
    async deleteCurrentImage() {
        if (this.previousMaps.length === 0 || this.currentIndex < 0 || this.currentIndex >= this.previousMaps.length) {
            return;
        }
        
        try {
            this.showPreviousMapLoading(true);
            
            const currentMap = this.previousMaps[this.currentIndex];
            const imageId = currentMap.id;
            
            // 삭제 요청 전송
            const response = await fetch(`./api/maps/${this.mapId}/previous-maps/${imageId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                // 삭제 성공 메시지
                this.uiManager.showMessage('이미지가 삭제되었습니다.', 'success');
                
                // 이미지 목록 다시 로드
                await this.loadPreviousMaps();
            } else {
                // 삭제 실패 메시지
                this.uiManager.showMessage(result.error || '이미지 삭제에 실패했습니다.', 'error');
            }
        } catch (error) {
            this.uiManager.showMessage(`이미지 삭제 중 오류: ${error}`, 'error');
        } finally {
            this.showPreviousMapLoading(false);
        }
    }
} 