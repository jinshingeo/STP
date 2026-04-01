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
| S-DoT 환경정보 (2025.07.28~08.03) | 서울 열린데이터광장 | ✅ 완료 (57개 센서) |
| ASOS 풍속·일사량 (2025.07.28~08.03) | 기상청 서울 108 | ✅ 완료 |
| 건물 footprint | OSM | ✅ 완료 (높이 33% 커버) |
| SVF (하늘열림계수) | — | ⏳ 예정 (v4) |
| 유동인구 (검증용) | 서울 생활인구 (행안부×SKT) | 🔲 교수님 논의 후 결정 |

---

## 분석 파이프라인

```
① S-DoT 실측 온습도 + ASOS 풍속·일사량
   → pythermalcomfort UTCI 계산 (v3_asos)

② IDW 보간 (p=2)
   57개 센서 → 15,608개 링크 × 24시간 UTCI 매핑

③ 속도계수 변환
   UTCI < 26°C → 1.0 / 26~32 → 0.9 / 32~38 → 0.75
   38~46 → 0.5 / ≥46 → 0.2 / 교량 × 0.7 추가 패널티

④ Thermal PPA (Dijkstra, 30분 예산)
   시간대별 보행 가능 공간 계산

⑤ 비교: 응봉동 vs 성수동 PPA 감소율 + 3D STP 시각화
```

---

## 핵심 결과 (v3_asos 기준, 2026-04-01)

| 지역 | Classic PPA | 07시 | 10시 | 13시 (폭염 피크) |
|---|---|---|---|---|
| **응봉동** | 63.2% | 29.5% (**▼53.4%**) | 22.6% (**▼64.2%**) | 11.1% (**▼82.4%**) |
| **성수동** | 20.5% | 12.2% (**▼40.1%**) | 12.0% (**▼41.6%**) | 6.3% (**▼69.2%**) |
| **격차 Δ** | +42.7%p | +17.3%p | +10.6%p | +4.8%p |

> **10시가 핵심 전환 구간**: UTCI 38°C 임계 첫 돌파 시점 → PPA 급감 시작  
> **실측 일사량 반영(v3) 효과**: 10시 기준 v2 대비 −102노드 추가 감소

---

## 버전 히스토리

| 버전 | 날짜 | 핵심 변경 |
|---|---|---|
| v1_sim | 2026-03-18 | 링크 유형별 시나리오 하드코딩 |
| v2_sdot | 2026-04-01 | S-DoT 57개 실측 UTCI + IDW 보간 |
| **v3_asos** | **2026-04-01** | **ASOS 풍속·일사량 실측 MRT 보정 (현재)** |
| v4_svf | 예정 | SVF 기반 그늘 효과 공간 차등 MRT |

---

## 디렉토리 구조

```
성동구_STP연구/
├── 01_네트워크/
│   ├── 01_download_network.py
│   ├── 02_check_bridges.py
│   └── seongdong_walk_network.graphml   (gitignore)
├── 02_기상데이터/
│   ├── 01_sdot_utci.ipynb               # UTCI v2 (S-DoT + UV)
│   ├── 02_utci_link_interpolation.ipynb # IDW 보간 v2
│   ├── 03_utci_v3_asos.ipynb            # UTCI v3 (S-DoT + ASOS)
│   └── OBS_ASOS_TIM_*.csv               # ASOS 실측 데이터
├── 03_건물데이터/
│   └── 01_download_buildings.py
├── 04_분석결과/
│   ├── 01_classic_ppa.py
│   ├── 02_thermal_ppa_v2_sdot.py        # Thermal PPA v2
│   ├── 02_thermal_ppa_v3_asos.py        # Thermal PPA v3 (현재)
│   ├── 02_utci_link_interpolation_v3.py # IDW v3
│   ├── 07_stp_3d_daily_v4_asos.py       # 3D STP v3
│   ├── 09_comparison_ppa_v3.py          # 응봉동 vs 성수동 v3
│   ├── link_utci_by_hour_v3.csv         # 링크별 속도계수 (v3)
│   ├── sdot_utci_v3_seongdong.csv       # UTCI v3 결과
│   ├── thermal_ppa_v3_asos_summary.json
│   └── figures/                         # 시각화 결과물
├── 05_시각화/
│   └── utci_v2_vs_v3.png
├── docs/
│   └── 2026-04-01_research_report.md   # 연구 레포트
└── ROADMAP.ipynb                        # 연구 로드맵 + 작업 로그
```

---

## 실행 방법

```bash
pip install osmnx networkx geopandas matplotlib numpy pyproj pythermalcomfort pandas openpyxl

# 1. UTCI v3 계산
jupyter nbconvert --to notebook --execute 02_기상데이터/03_utci_v3_asos.ipynb

# 2. IDW 링크 보간
cd 04_분석결과 && python 02_utci_link_interpolation_v3.py

# 3. Thermal PPA v3
python 02_thermal_ppa_v3_asos.py

# 4. 응봉동 vs 성수동 비교
python 09_comparison_ppa_v3.py

# 5. 3D STP 시각화
python 07_stp_3d_daily_v4_asos.py
```

---

## 연구 레포트

- [2026-04-01 연구 레포트](docs/2026-04-01_research_report.md) — v3_asos 분석 완성, 기여점·결론·TODO

---

## 학회 발표 목표
**2026년 5월** — 분석 프레임워크 + 실측 기반 결과 발표
