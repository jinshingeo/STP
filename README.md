# 열환경을 반영한 보행 Space-Time Prism 분석
**Thermal-Inclusive Pedestrian Space-Time Prism Analysis in Seongdong-gu, Seoul**

> 석사 논문 연구 | 성동구 폭염 시간대 보행 접근성의 시공간적 변화

---

## 연구 개요

### 연구 질문
> 폭염 시간대에 열환경을 반영했을 때, 보행 STP의 잠재경로영역(PPA)은 얼마나 감소하는가?
> 그리고 그 감소 폭은 도시 열환경 조건(교량 노출, 그늘 자원)에 따라 얼마나 다른가?

### 핵심 기여
기존 보행 STP 연구는 시간을 단순 예산(time budget)으로만 다루어 **Classic PPA = 시간 무관 원기둥** 형태를 도출한다.
본 연구는 열환경(UTCI)을 시간대별 소프트 제약(soft constraint)으로 적용하여
**Thermal PPA = 폭염 시간대에 허리가 잘록해지는 동적 프리즘** 임을 실증한다.

> "같은 30분 시간예산이라도 *언제* 이동하느냐에 따라 보행 가능 공간이 달라진다"
> → 기존 보행 STP 연구의 간과점을 최초로 지적·실증

---

## 연구 지역 및 비교 설계

| 지역 | 특성 | 역할 |
|---|---|---|
| **응봉동** | 중랑천 교량(고산자로) 통과 필요, 그늘 적음 | 열환경 취약 집단 |
| **성수동** | 서울숲 인접, 교량 없음, 녹지 풍부 | 비교군 (열완충 가능) |

**핵심 비교 지표:**
PPA 감소율(%) = (Classic PPA − Thermal PPA) / Classic PPA × 100
→ 절대 면적이 아닌 **변화의 정도**를 비교 → 지리적 조건 차이 통제

---

## 선행연구 위치

| 연구 흐름 | 대표 논문 | STP 사용 | 열환경 사용 |
|---|---|---|---|
| STP + 소프트 제약 | Kar et al. (2023) *Annals of AAG* | ✅ | ❌ |
| STP + 소프트 제약 (집단) | Kar et al. (2024) *CEUS* | ✅ | ❌ |
| 열환경 + 보행 접근성 | Basu et al. (2024) *Cities* | ❌ | ✅ UTCI |
| 열환경 + 보행 노출 | Colaninno et al. (2024) *EPB* | ❌ | ✅ UTCI |
| **본 연구** | — | **✅** | **✅** |

---

## 데이터

| 데이터 | 출처 | 상태 |
|---|---|---|
| 보행 네트워크 (성동구) | OpenStreetMap (osmnx) | ✅ 완료 |
| 집계구 경계 | 통계청 | ✅ 완료 |
| 건물 footprint | OSM | ✅ 완료 (높이 33% 커버) |
| 기상 데이터 (ASOS) | 기상청 서울 108 | ⏳ 수집 예정 |
| 폭염특보 발령일 | 기상청 | ⏳ 수집 예정 |
| 건물 높이 보완 | 국토부 건물통합정보 | ⏳ 수집 예정 |
| 가로수 현황 | 서울시 열린데이터광장 | ⏳ 수집 예정 |
| 유동인구 (검증용) | 서울 생활인구 (행안부×SKT) | 🔲 교수님 논의 후 결정 |

---

## 분석 프레임워크

```
① Classic PPA
   보행속도 4.5km/h 고정 + 시간예산 30분 + Dijkstra
   → 시간대 무관 원기둥 형태

② Thermal-Inclusive PPA
   도로 유형별 UTCI 기반 임피던스 적용:
     bridge    → 완전 노출 → 폭염 시 통행 불가 (factor=0)
     major_road → 부분 노출 → 속도 감소
     local/footway → 상대적 쾌적 → 영향 최소

③ 시간대별 UTCI 프로파일 (폭염일 기준):
   07-08시 쾌적(A) → 09-10시 보통더위(B) → 11-16시 폭염피크(C)
   → 17-18시 완화(B) → 19-21시 야간쾌적(A)

④ 비교: 응봉동 vs 성수동 PPA 감소율
```

---

## 디렉토리 구조

```
성동구_STP연구/
├── 01_네트워크/
│   ├── 01_download_network.py      # OSM 보행 네트워크 다운로드
│   ├── 02_check_bridges.py         # 교량 링크 확인
│   └── seongdong_walk_network.graphml  # (gitignore)
├── 02_기상데이터/
│   ├── README.md                   # 기상 데이터 수집 가이드
│   └── raw/                        # (gitignore)
├── 03_건물데이터/
│   └── 01_download_buildings.py    # OSM 건물 데이터 수집
├── 04_분석결과/
│   ├── 01_classic_ppa.py           # Classic PPA 분석
│   ├── 02_thermal_ppa.py           # Thermal PPA (3 시나리오)
│   ├── 03_multi_origin_ppa.py      # 다중 출발지 PPA
│   ├── 04_representative_selection.py  # 대표 집계구 선정
│   ├── 05_isochrone_stp.py         # 등시선 STP 시각화
│   ├── 06_stp_3d_prism.py          # 3D 프리즘
│   ├── 07_stp_3d_daily.py          # 3D 하루 시간대별 프리즘
│   ├── 08_thermal_score_ppa_overlay.py  # 열환경 점수 × PPA 중첩
│   ├── classic_ppa_summary.json
│   ├── thermal_ppa_summary.json
│   ├── multi_origin_summary.json
│   └── representative_nodes.json
└── ROADMAP.ipynb                   # 연구 진행 로드맵 및 체크리스트
```

---

## 예비 결과 (시뮬레이션 기반, 실측 데이터 적용 예정)

| 지역 | Classic PPA | Thermal PPA (폭염 피크) | **감소율** |
|---|---|---|---|
| 응봉동 대표 집계구 | 63.2% | 21.1% | **▼ 66.6%** |
| 성수동 대표 집계구 | 20.5% | 10.5% | **▼ 48.8%** |

응봉동은 폭염 피크 시 **전 집계구에서 체육센터 접근 불가**
성수동은 동일 조건에서 **77% 집계구가 여전히 접근 가능**

---

## 실행 방법

```bash
# 의존성 설치
pip install osmnx networkx geopandas matplotlib numpy pyproj pythermalcomfort

# 분석 순서
cd 01_네트워크 && python 01_download_network.py
cd ../04_분석결과 && python 01_classic_ppa.py
python 02_thermal_ppa.py
python 03_multi_origin_ppa.py
python 04_representative_selection.py
python 05_isochrone_stp.py
python 07_stp_3d_daily.py
python 08_thermal_score_ppa_overlay.py
```

---

## 학회 발표 목표
**2026년 5월** — 분석 프레임워크 + 예비 결과 발표
