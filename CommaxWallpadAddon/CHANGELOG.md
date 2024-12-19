# Changelog

모든 주요 변경 사항이 이 파일에 기록됩니다.

## [1.1.1] - 2024-03-XX

### 변경됨
- MQTT 클라이언트 설정 로직 개선
  - `setup_mqtt()` 메소드를 재사용 가능하도록 리팩토링
  - 임시 MQTT 연결과 메인 MQTT 연결 로직 통합
  - Optional 타입 힌트 추가로 타입 안정성 향상

### 개선됨
- 기기 검색 로직 개선
  - 임시 MQTT 클라이언트 연결 후 명시적 연결 해제 추가
  - 검색 결과 처리 및 저장 로직 구조화

### 제거됨
- 사용하지 않는 기기 관련 메소드 주석 처리
  - `insert_device_index_to_hex()`
  - `update_fan()`
  - `update_outlet_value()`
  - `update_ev_value()`
  - `generate_device_packets()`
  - `make_device_lists()`

### 버그 수정
- 한글 인코딩 관련 문제 수정
- MQTT 재연결 로직 안정성 개선

## [1.1.0] - 2024-03-XX

### 변경됨
- MQTT 클라이언트 설정 로직 개선
  - `setup_mqtt()` 메소드를 재사용 가능하도록 리팩토링
  - 임시 MQTT 연결과 메인 MQTT 연결 로직 통합
  - Optional 타입 힌트 추가로 타입 안정성 향상

### 개선됨
- 기기 검색 로직 개선
  - 임시 MQTT 클라이언트 연결 후 명시적 연결 해제 추가
  - 검색 결과 처리 및 저장 로직 구조화

### 제거됨
- 사용하지 않는 기기 관련 메소드 주석 처리
  - `insert_device_index_to_hex()`
  - `update_fan()`
  - `update_outlet_value()`
  - `update_ev_value()`
  - `generate_device_packets()`
  - `make_device_lists()`

### 버그 수정
- 한글 인코딩 관련 문제 수정
- MQTT 재연결 로직 안정성 개선

## [1.0.0] - 2024-03-XX

### 추가됨
- 최초 릴리스
- 코맥스 월패드 기기 제어 기능
- MQTT 통신 지원
- Home Assistant 통합
