"""
Classic PPA 분석
- Origin: 응봉역 (hard constraint만 적용)
- Time Budget: 30분
- Walking Speed: 4.5 km/h (75 m/min)
- 결과: 시간대별 도달 가능 네트워크 시각화

나중에 thermal soft constraint 추가 시
→ 이 결과와 비교하는 Classic PPA 기준선(baseline)으로 사용
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np
import os

# ── 경로 설정 ──────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
OUT_DIR = BASE

# ── 파라미터 ───────────────────────────────────────
WALK_SPEED_MPS = 4.5 * 1000 / 3600   # 4.5 km/h → m/s = 1.25 m/s
TIME_BUDGET_SEC = 30 * 60             # 30분 = 1800초

# 응봉역 좌표
EUNGBONG_LAT = 37.5428
EUNGBONG_LON = 127.0357

print("네트워크 로드 중...")
G = ox.load_graphml(NET_PATH)

# 엣지 통행 시간 계산 (초 단위)
for u, v, data in G.edges(data=True):
    length = data.get("length", 0)
    data["travel_time"] = length / WALK_SPEED_MPS  # 초

# 응봉역에서 가장 가까운 노드
origin_node = ox.distance.nearest_nodes(G, EUNGBONG_LON, EUNGBONG_LAT)
print(f"Origin 노드 ID: {origin_node}")

# ── Classic PPA: Dijkstra로 도달 가능 노드 계산 ────
print("Classic PPA 계산 중...")
# 단방향 그래프로 변환 (보행은 양방향)
G_undirected = G.to_undirected()

lengths = nx.single_source_dijkstra_path_length(
    G_undirected,
    origin_node,
    cutoff=TIME_BUDGET_SEC,
    weight="travel_time"
)

reachable_nodes = set(lengths.keys())
reachable_edges = [
    (u, v, k, data)
    for u, v, k, data in G_undirected.edges(keys=True, data=True)
    if u in reachable_nodes and v in reachable_nodes
]

print(f"  도달 가능 노드: {len(reachable_nodes):,} / 전체 {len(G.nodes):,}")
print(f"  도달 가능 엣지: {len(reachable_edges):,} / 전체 {len(G.edges):,}")

# ── 시각화 ────────────────────────────────────────
print("시각화 생성 중...")
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_undirected)

# 도달 가능 여부 표시
edges_gdf["reachable"] = edges_gdf.index.map(
    lambda idx: idx[0] in reachable_nodes and idx[1] in reachable_nodes
)
nodes_gdf["reachable"] = nodes_gdf.index.isin(reachable_nodes)

# 잔여 시간 (도달 가능 노드의 여유 시간)
nodes_gdf["time_left"] = nodes_gdf.index.map(
    lambda n: TIME_BUDGET_SEC - lengths.get(n, TIME_BUDGET_SEC + 1)
    if n in reachable_nodes else np.nan
)

# 그림 그리기
fig, axes = plt.subplots(1, 2, figsize=(16, 10))

for ax, show_gradient in zip(axes, [False, True]):
    # 전체 네트워크 (회색 배경)
    edges_gdf[~edges_gdf["reachable"]].plot(
        ax=ax, color="#d0d0d0", linewidth=0.4, alpha=0.6
    )

    if show_gradient:
        # 잔여 시간으로 색상 그라디언트
        reachable_edges_gdf = edges_gdf[edges_gdf["reachable"]].copy()
        reachable_edges_gdf["avg_time_left"] = reachable_edges_gdf.index.map(
            lambda idx: (
                (lengths.get(idx[0], 0) + lengths.get(idx[1], 0)) / 2
            ) if idx[0] in lengths and idx[1] in lengths else 0
        )
        reachable_edges_gdf["time_pct"] = 1 - reachable_edges_gdf["avg_time_left"] / TIME_BUDGET_SEC
        reachable_edges_gdf.plot(
            ax=ax, column="time_pct",
            cmap="RdYlGn_r", linewidth=1.2, alpha=0.9,
            legend=True,
            legend_kwds={"label": "출발지로부터의 상대 거리\n(초록=가까움, 빨강=멀음)"}
        )
        ax.set_title("Classic PPA — 거리 그라디언트\n(기준: 응봉역, 30분 시간예산)", fontsize=13)
    else:
        # 단순 도달/미도달
        edges_gdf[edges_gdf["reachable"]].plot(
            ax=ax, color="#2196F3", linewidth=1.0, alpha=0.85
        )
        ax.set_title("Classic PPA — 도달 가능 네트워크\n(기준: 응봉역, 30분 시간예산)", fontsize=13)

    # 출발지 표시
    origin_data = nodes_gdf.loc[origin_node]
    ax.plot(
        origin_data.geometry.x, origin_data.geometry.y,
        "r*", markersize=14, zorder=5, label="응봉역 (출발)"
    )

    # 살곶이다리 표시 (핵심 케이스 링크)
    bridge_edges = edges_gdf[
        edges_gdf.index.map(lambda idx: edges_gdf.loc[idx, "name"] == "살곶이다리(전곡교)"
                            if idx in edges_gdf.index else False)
    ] if "name" in edges_gdf.columns else gpd.GeoDataFrame()

    # 이름으로 찾기
    if "name" in edges_gdf.columns:
        bridge_e = edges_gdf[edges_gdf["name"] == "살곶이다리(전곡교)"]
        if len(bridge_e) > 0:
            bridge_e.plot(ax=ax, color="orange", linewidth=3.5, zorder=4, label="살곶이다리(전곡교)")

    ax.legend(loc="upper left", fontsize=9)
    ax.set_axis_off()

plt.suptitle(
    "성동구 보행 접근성 — Classic PPA (하드 제약만 적용)\n"
    "출발지: 응봉역 | 시간예산: 30분 | 보행속도: 4.5 km/h",
    fontsize=14, fontweight="bold"
)
plt.tight_layout()

out_path = os.path.join(OUT_DIR, "classic_ppa_eungbong.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"\n저장 완료: {out_path}")

# ── 결과 요약 저장 ──────────────────────────────────
summary = {
    "origin": "응봉역",
    "time_budget_min": 30,
    "walk_speed_kmh": 4.5,
    "total_nodes": len(G.nodes),
    "reachable_nodes": len(reachable_nodes),
    "reachable_pct": round(len(reachable_nodes) / len(G.nodes) * 100, 1),
    "total_edges": len(G.edges),
    "reachable_edges": len(reachable_edges),
}
import json
with open(os.path.join(OUT_DIR, "classic_ppa_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n=== Classic PPA 결과 요약 ===")
for k, v in summary.items():
    print(f"  {k}: {v}")
