# 연구 방향 재정립 보고서
**작성일**: 2026-04-09
**현재 버전**: v3_asos 이후 방향 전환 시점

---

## 1. 교수님 피드백 요약 (2026-04 미팅)

| 항목 | 교수님 지적 |
|------|------------|
| STP 구현 여부 | "STP를 코드로 구현한 게 아니다" — 프리즘 자체를 만들어야 함 |
| 링크 스코어 지도 | Kar et al.(2024) Fig.4처럼 도로 네트워크 전체에 링크별 스코어 시각화 필요 |
| 링크 가중치 | 각 링크에 열환경 가중치를 부여하는 방안 모색 필요 |
| 극단값 민감도 | "얼마나 극단적인 값이 나와야 STP가 동심원이 아닌 모양으로 줄어드는가" (킵) |
| 변수 선택 | 열 노출 완화 변수(나무, 그늘막, 바람길) → PCA/SVM으로 영향력 높은 변수 선택 |

---

## 2. 현재 작업과 요구사항의 차이

### 내가 지금까지 한 것: PPA 시각적 중첩

```
dijkstra(origin, T/2) → 도달 가능 노드 집합 A
dijkstra(destination, T/2) → 도달 가능 노드 집합 B
A ∩ B = PPA → 2D 지도에 색칠
```

- 결과물: **2D 지도 (Classic PPA vs Thermal PPA 색상 차이)**
- 열환경: UTCI 기반 penalty를 링크 비용에 반영
- 한계: 시간의 흐름이 없음. "어느 시점에 어디 있을 수 있는가"를 표현 못 함

### 교수님이 요구하는 것: 진짜 STP (Miller 1991)

Miller(1991)에 따르면 STP(Space-Time Prism)는 3차원 구조물이다.

```
z축 = 시간
x, y축 = 공간

시간 t가 t_출발 → t_도착으로 흐를 때:
  forward_cone(t)  = origin에서 (t - t_출발) 시간 동안 이동 가능한 공간
  backward_cone(t) = destination에서 (t_도착 - t) 시간 동안 거슬러 오는 공간
  STP_slice(t) = forward_cone(t) ∩ backward_cone(t)

모든 slice를 z축으로 쌓으면 → 3D 프리즘 (다이아몬드/모래시계 형태)
PPA = 이 프리즘의 x-y 평면 투영 (바닥 그림자)
```

**핵심 차이**: STP는 *시간의 흐름에 따라 이동 가능 공간이 어떻게 변하는지*를 담은 3D 구조물이다. 현재 코드는 최종 결과(PPA)만 생성하고, 그 과정인 프리즘 자체를 구현하지 않았다.

---

## 3. 선행연구와 연구 방향의 교차점

### STP 구현 참고: Miller (1991)
- **논문**: "Modelling accessibility using space-time prism concepts within geographical information systems"
- **핵심 개념**: PPS(Potential Path Space) = 3D 프리즘, PPA = 2D 투영
- **구현 요소**: origin/destination 위치, 시간예산(T), 이동속도(v), 네트워크 arc/node
- **입력 데이터**: 출발/도착 위치, 활동 위치, 링크 길이 + 시간대별 이동속도

### 링크 스코어 지도 참고: Kar et al. (2024)
- **논문**: "Inclusive accessibility: Analyzing socio-economic disparities in perceived accessibility"
- **Fig.4**: 도로 네트워크 전체에 보행 인식 점수(1~5, 빨강→초록)를 링크별로 시각화
- **방법**: SVR ensemble로 보행 인식 점수 예측 → soft constraint로 활용
- **Jin의 연구에 적용**: UTCI 기반 열노출 스코어(1~5)를 링크별로 산출 → 동일한 방식의 시각화

---

## 4. 재구성된 분석 파이프라인 (제안)

```
[Step 1] 링크별 Thermal Score 산출
  UTCI → 0~1 정규화 → "열 노출 스코어" per link per hour
  → Kar et al. Fig.4 스타일로 성동구 전체 도로망 시각화 (시간대별)

[Step 2] Classic STP 구현 (Miller 1991 기반)
  출발지 + 도착지 + 시간예산 T 고정
  시간을 슬라이스 → forward cone + backward cone 계산
  → 3D 프리즘 시각화 (x,y=공간, z=시간)
  → 동심원 형태의 baseline

[Step 3] Thermal STP 구현
  Step 1 스코어를 링크 이동 비용에 반영 (soft constraint)
  → UTCI 높은 링크 = 이동 속도 감소 or 비용 증가
  → 동일 구조로 Thermal STP 생성
  → Classic vs Thermal 프리즘 크기/모양 비교

[Step 4] 응봉동 vs 성수동 비교
  동일 시간예산 하에서 두 지역 프리즘의 차이
  → PPA 감소율, 프리즘 형태 비그림 비교
  → "열취약 지역(응봉동)에서 이동 가능성이 더 크게 제약된다"는 논증
```

---

## 5. 아직 결정 안 된 핵심 사항 (미팅 전 검토 필요)

### Q1. Origin-Destination 설정
STP는 반드시 출발지와 목적지가 있어야 한다. 연구에서 이를 어떻게 설정할 것인가?
- 옵션 A: 고정점 — 아파트 단지 → 지하철역 (현실적 O/D)
- 옵션 B: 대표 노드 — 각 지역 중심점 → 주변 서비스 시설
- 옵션 C: 단일 origin, 목적지 없음 (pure PPA, STP가 아님)

**→ 옵션 A 또는 B 중 하나를 결정해야 Step 2 착수 가능**

### Q2. Soft Constraint 적용 방식
UTCI 임계값 초과 링크를 어떻게 처리할 것인가?
- (a) **링크 제거** (hard constraint처럼): 38°C 이상 링크 통행 불가
- (b) **속도 감소** (soft constraint): UTCI에 비례해 보행속도 감소
- (c) **스코어 산출** (후속 분석용): 링크 접근성 지수에만 반영

이 선택이 프리즘 모양을 결정한다. (b)가 가장 현실적이고, Miller의 "속도 가변" 개념과도 일치함.

### Q3. 변수 확장 범위
교수님 메모의 "나무, 그늘막, 바람길 + PCA/SVM"을 논문 본체에 포함시킬 것인가?
- 포함 시: 데이터 수집 필요 (성동구 가로수 위치, 그늘시설 위치, 건물 높이)
- 제외 시: "향후 연구" 섹션으로 이동, SVF만 v4에서 반영

### Q4. 논문의 핵심 주장
두 가지 방향 중 어느 쪽인가?
- **방향 A**: "열환경이 STP를 얼마나 제약하는가" → STP 크기 변화가 핵심
- **방향 B**: "두 지역의 열 노출 형평성 차이" → 응봉동 vs 성수동 비교가 핵심

현재 v3_asos 결과는 방향 B에 가깝다. 방향 A로 가면 단일 지역, 시간대별 프리즘 변화에 집중.

---

## 6. 우선순위별 TODO

| 우선순위 | 작업 | 필요 조건 |
|----------|------|----------|
| **1** | Classic STP 프리즘 코드 구현 | Origin-Destination 결정 (Q1) |
| **2** | 링크별 Thermal Score 지도 (Fig.4 스타일) | UTCI → 스코어 변환 규칙 결정 (Q2) |
| **3** | Thermal STP 구현 및 비교 | Step 1+2 완료 후 |
| **4** | 응봉동 vs 성수동 프리즘 비교 | Step 3 완료 후 |
| **킵** | SVF 반영(v4), PCA/SVM 변수 선택 | Q3 결정 후 |

---

## 7. 참고 문헌

- Miller, H. J. (1991). Modelling accessibility using space-time prism concepts within geographical information systems. *International Journal of Geographical Information Systems*, 5(3), 287–301.
- Kar, A., Xiao, N., Miller, H. J., & Le, H. T. K. (2024). Inclusive accessibility: Analyzing socio-economic disparities in perceived accessibility. *Computers, Environment and Urban Systems*, 114, 102202.
