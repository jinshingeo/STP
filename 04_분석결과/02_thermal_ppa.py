"""
Thermal-Inclusive PPA 분석
- 열환경(체감온도)을 시간대별 soft constraint로 적용
- 기상 데이터 없이 시뮬레이션 시나리오 3개 비교:
    A) 쾌적 (아침 07:00, UTCI < 26°C)  → 임피던스 없음
    B) 보통 더위 (오전 10:00, UTCI 26~32°C) → 노출 구간 속도 감소
    C) 폭염 피크 (오후 13:00, UTCI > 38°C) → 노출 구간 통행 불가

열환경 임피던스 분류 기준:
  - bridge = yes : 완전 노출 (한강/중랑천 위)
  - highway in [trunk, primary, secondary] : 부분 노출
  - footway/residential : 건물/나무 그늘 많음 → 쾌적

나중에 실제 기상 데이터 + LST + 그늘 계산으로 대체 가능
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
OUT_DIR = BASE

# ── 파라미터 ────────────────────────────────────────────────────────
WALK_SPEED_BASE = 4.5 * 1000 / 3600   # 기본 보행속도 m/s
TIME_BUDGET_SEC = 30 * 60

EUNGBONG_LAT, EUNGBONG_LON = 37.5428, 127.0357

# ── 시나리오 정의 ────────────────────────────────────────────────────
# 각 도로 유형별 폭염 시 속도 감소율 (0 = 통행 불가)
SCENARIOS = {
    "A_쾌적_07시": {
        "label": "시나리오 A: 쾌적 (07:00)\nUTCI < 26°C",
        "color": "#2196F3",
        "speed_factor": {
            "bridge":     1.0,   # 영향 없음
            "major_road": 1.0,
            "local":      1.0,
        }
    },
    "B_보통더위_10시": {
        "label": "시나리오 B: 보통 더위 (10:00)\nUTCI 26~32°C",
        "color": "#FF9800",
        "speed_factor": {
            "bridge":     0.5,   # 속도 50% 감소 (불쾌감)
            "major_road": 0.8,
            "local":      0.9,
        }
    },
    "C_폭염피크_13시": {
        "label": "시나리오 C: 폭염 피크 (13:00)\nUTCI > 38°C",
        "color": "#F44336",
        "speed_factor": {
            "bridge":     0.0,   # 통행 불가 (임피던스 무한대)
            "major_road": 0.4,
            "local":      0.7,
        }
    }
}

# ── 도로 유형 분류 함수 ───────────────────────────────────────────────
def classify_edge(data):
    """엣지를 열환경 노출 수준으로 분류"""
    bridge = data.get("bridge", None)
    highway = data.get("highway", "")
    if isinstance(highway, list):
        highway = highway[0]

    if bridge and bridge not in [None, "nan"]:
        return "bridge"
    if highway in ["trunk", "trunk_link", "primary", "primary_link",
                   "secondary", "secondary_link"]:
        return "major_road"
    return "local"

# ── 네트워크 로드 ────────────────────────────────────────────────────
print("네트워크 로드...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()

origin_node = ox.distance.nearest_nodes(G_base, EUNGBONG_LON, EUNGBONG_LAT)

# 엣지 분류
edge_types = {}
for u, v, k, data in G_base.edges(keys=True, data=True):
    edge_types[(u, v, k)] = classify_edge(data)

bridge_count = sum(1 for t in edge_types.values() if t == "bridge")
major_count = sum(1 for t in edge_types.values() if t == "major_road")
print(f"  bridge 엣지: {bridge_count}개")
print(f"  major_road 엣지: {major_count}개")
print(f"  local 엣지: {len(edge_types) - bridge_count - major_count}개")

# ── 시나리오별 PPA 계산 ──────────────────────────────────────────────
results = {}

for scenario_id, scenario in SCENARIOS.items():
    print(f"\n{scenario['label'].split(chr(10))[0]} 계산 중...")

    G = G_base.copy()

    # 시나리오별 이동 시간 재계산
    for u, v, k, data in G.edges(keys=True, data=True):
        length = data.get("length", 0)
        etype = edge_types.get((u, v, k), "local")
        factor = scenario["speed_factor"][etype]

        if factor == 0:
            # 통행 불가 → travel_time을 무한대로 설정
            data["travel_time"] = float("inf")
        else:
            data["travel_time"] = length / (WALK_SPEED_BASE * factor)

    # Dijkstra (inf 엣지는 자동으로 제외됨)
    try:
        lengths = nx.single_source_dijkstra_path_length(
            G, origin_node,
            cutoff=TIME_BUDGET_SEC,
            weight="travel_time"
        )
    except Exception as e:
        print(f"  오류: {e}")
        lengths = {}

    reachable = set(lengths.keys())
    results[scenario_id] = {
        "lengths": lengths,
        "reachable": reachable,
        "scenario": scenario,
        "reachable_count": len(reachable),
        "reachable_pct": round(len(reachable) / len(G.nodes) * 100, 1),
    }
    print(f"  도달 가능 노드: {len(reachable):,} ({results[scenario_id]['reachable_pct']}%)")

# ── Classic PPA 불러오기 (비교용) ────────────────────────────────────
with open(os.path.join(OUT_DIR, "classic_ppa_summary.json"), encoding="utf-8") as f:
    classic_summary = json.load(f)

# ── 시각화 ──────────────────────────────────────────────────────────
print("\n시각화 생성 중...")
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

fig, axes = plt.subplots(1, 3, figsize=(21, 9))

for ax, (scenario_id, res) in zip(axes, results.items()):
    scenario = res["scenario"]
    reachable = res["reachable"]

    edges_gdf["reachable"] = edges_gdf.index.map(
        lambda idx: idx[0] in reachable and idx[1] in reachable
    )

    # 배경 네트워크
    edges_gdf[~edges_gdf["reachable"]].plot(
        ax=ax, color="#e0e0e0", linewidth=0.4, alpha=0.7
    )
    # 도달 가능 네트워크
    edges_gdf[edges_gdf["reachable"]].plot(
        ax=ax, color=scenario["color"], linewidth=1.0, alpha=0.85
    )

    # 살곶이다리 강조
    if "name" in edges_gdf.columns:
        bridge_e = edges_gdf[edges_gdf["name"] == "살곶이다리(전곡교)"]
        if len(bridge_e) > 0:
            bridge_reachable = bridge_e[bridge_e["reachable"]]
            bridge_blocked = bridge_e[~bridge_e["reachable"]]
            if len(bridge_reachable) > 0:
                bridge_reachable.plot(ax=ax, color="lime", linewidth=4, zorder=5)
            if len(bridge_blocked) > 0:
                bridge_blocked.plot(ax=ax, color="black", linewidth=4,
                                    linestyle="--", zorder=5, label="살곶이다리 (차단)")

    # 출발지
    origin_geom = nodes_gdf.loc[origin_node].geometry
    ax.plot(origin_geom.x, origin_geom.y, "r*", markersize=14, zorder=6)

    ax.set_title(
        f"{scenario['label']}\n"
        f"도달 가능 노드: {res['reachable_count']:,}개 ({res['reachable_pct']}%)",
        fontsize=11
    )
    ax.set_axis_off()
    if len(bridge_blocked) > 0:
        ax.legend(loc="upper left", fontsize=8)

plt.suptitle(
    "Thermal-Inclusive PPA 시나리오 비교\n"
    "출발지: 응봉역 | 시간예산: 30분 | 체감온도에 따른 도로 임피던스 적용",
    fontsize=13, fontweight="bold"
)
plt.tight_layout()

out_path = os.path.join(OUT_DIR, "thermal_ppa_scenarios.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장 완료: {out_path}")

# ── 비교 요약 저장 ──────────────────────────────────────────────────
summary = {
    "classic_ppa_nodes": classic_summary["reachable_nodes"],
    "classic_ppa_pct": classic_summary["reachable_pct"],
}
for sid, res in results.items():
    summary[sid] = {
        "reachable_nodes": res["reachable_count"],
        "reachable_pct": res["reachable_pct"],
        "decline_from_classic_pct": round(
            (classic_summary["reachable_nodes"] - res["reachable_count"])
            / classic_summary["reachable_nodes"] * 100, 1
        )
    }

with open(os.path.join(OUT_DIR, "thermal_ppa_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n=== PPA 비교 요약 ===")
print(f"Classic PPA: {summary['classic_ppa_nodes']:,}노드 ({summary['classic_ppa_pct']}%)")
for sid, res in results.items():
    sid_label = sid.split("_")[1]
    s = summary[sid]
    print(f"  {sid_label}: {s['reachable_nodes']:,}노드 ({s['reachable_pct']}%)"
          f" → Classic 대비 {s['decline_from_classic_pct']}% 감소")
