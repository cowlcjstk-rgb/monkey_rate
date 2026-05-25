# Monkey Rate

여행 플랫폼 가격 비교용 Streamlit 앱입니다.

## 구성
- `app.py`: 메인 앱
- `core/`: 공통 유틸과 Selenium 드라이버
- `platforms/`: 플랫폼별 수집 로직
- `requirements.txt`: Python 의존성
- `packages.txt`: Streamlit Community Cloud용 시스템 패키지
- `.streamlit/config.toml`: Streamlit 설정

## 로컬 실행
```bash
streamlit run app.py
```

## Streamlit Community Cloud 배포
1. 이 저장소를 GitHub에 올립니다.
2. Streamlit Community Cloud에서 `Create app`을 엽니다.
3. 저장소와 브랜치, 엔트리포인트를 지정합니다.
4. Main file path는 `app.py`로 둡니다.
5. Deploy를 누릅니다.

## 실행 중 생성 파일
- `runtime/`: 최근 검색 기록, 엑셀 다운로드 파일 등 실행 중 생성되는 파일 저장
- 이 폴더는 Git에 포함하지 않습니다.
