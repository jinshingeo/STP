"""
열환경 노출 점수 지도 + PPA 중첩 시각화

목적:
  - 각 네트워크 링크에 열환경 노출 점수 부여 (0=완전노출/빨강 ~ 1=쾌적/초록)
  - 그 위에 시나리오별 PPA 경계를 중첩
  - 'PPA가 빨간 링크(고노출 구간)에서 수축한다'는 인과관계를 직관적으로 시각화

패널 구성:
  행: 응봉동 대표 / 성수동 대표
  열: ① 열환경 점수 지도 ② 시나리오A PPA ③ 시나리오C PPA

출력: thermal_score_ppa_overlay.png
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.patches as mpatches
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np
import json, os

BASE     = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
OUT_DIR  = BASE

WALK_SPEED_BASE = 4.5 * 1000 / 3600
TIME_BUDGET_SEC = 30 * 60
GYM_LAT, GYM_LON = 37.546419, 127.044641

# 열환경 노출 점수 (높을수록 쾌적·보행 유리)
THERMAL_SCORE = {
    "bridge":     0.10,   # 완전 노출 — 교량
    "major_road": 0.40,   # 부분 노출 — 간선도로
    "local":      0.80,   # 상대적 쾌적 — 이면도로/보행로
}

SCENARIOS = {
    "A_쾌적_07시": {
        "label": "시나리오 A\n쾌적 (07:00, UTCI<26°C)",
        "ppa_color": "#1565C0",
        "speed_factor": {"bridge": 1.0, "major_road": 1.0, "local": 1.0},
    },
    "C_폭염피크_13시": {
        "label": "시나리오 C\n폭염 피크 (13:00, UTCI>38°C)",
        "ppa_color": "#B71C1C",
        "speed_factor": {"bridge": 0.0, "major_road": 0.4, "local": 0.7},
    },
}

def classify_edge(data):
    bridge  = data.get("bridge", None)
    highway = data.get("highway", "")
    if isinstance(highway, list): highway = highway[0]
    if bridge and bridge not in [None, "nan"]: return "bridge"
    if highway in ["trunk","trunk_link","primary","primary_link","secondary","secondary_link"]:
        return "major_road"
    return "local"

# ── 네트워크 로드 ─────────────────────────────────────────────────────
print("네트워크 로드...")
G_base     = ox.load_graphml(NET_PATH)
G_base     = G_base.to_undirected()
edge_types = {(u,v,k): classify_edge(d) for u,v,k,d in G_base.edges(keys=True, data=True)}
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)
gym_node   = ox.distance.nearest_nodes(G_base, GYM_LON, GYM_LAT)

# 엣지별 열환경 점수 부여
edges_gdf["thermal_score"] = edges_gdf.index.map(
    lambda idx: THERMAL_SCORE[edge_types.get(idx, "local")]
)
edges_gdf["edge_type"] = edges_gdf.index.map(
    lambda idx: edge_types.get(idx, "local")
)

# 색상 정규화 (0~1 → 초록~빨강)
cmap   = plt.cm.RdYlGn          # 빨강-노랑-초록
norm   = mcolors.Normalize(vmin=0, vmax=1)
edges_gdf["score_color"] = edges_gdf["thermal_score"].apply(
    lambda s: cmap(norm(s))
)

# ── 시나리오 그래프 ───────────────────────────────────────────────────
def make_graph(speed_factor):
    G = G_base.copy()
    for u,v,k,data in G.edges(keys=True, data=True):
        factor = speed_factor[edge_types.get((u,v,k),"local")]
        data["travel_time"] = float("inf") if factor==0 else \
                              data.get("length",0)/(WALK_SPEED_BASE*factor)
    return G

graphs = {sid: make_graph(sc["speed_factor"]) for sid, sc in SCENARIOS.items()}

# 대표 노드
with open(os.path.join(OUT_DIR, "representative_nodes.json"), encoding="utf-8") as f:
    rep_info = json.load(f)
origins = {"응봉동": rep_info["응봉동"], "성수동": rep_info["성수동"]}

# ── PPA 계산 ─────────────────────────────────────────────────────────
def get_reachable(G, origin, budget):
    try:
        lengths = nx.single_source_dijkstra_path_length(
            G, origin, cutoff=budget, weight="travel_time")
        return set(lengths.keys())
    except:
        return set()

# ── 시각화 ───────────────────────────────────────────────────────────
print("시각화 생성...")

# 링크 굵기 설정
lw_map = {"bridge": 2.2, "major_road": 1.2, "local": 0.7}
edges_gdf["linewidth"] = edges_gdf["edge_type"].map(lw_map)

n_rows = 2   # 응봉동, 성수동
n_cols = 3   # 열환경 점수 / A PPA / C PPA
fig, axes = plt.subplots(n_rows, n_cols, figsize=(24, 15))

district_labels = {
    "응봉동": "응봉동 대표 집계구\n(교량 bottleneck 구간)",
    "성수동": "성수동 대표 집계구\n(비교군)",
}

for row_i, (district, origin) in enumerate(origins.items()):
    origin_geom = nodes_gdf.loc[origin].geometry
    gym_geom    = nodes_gdf.loc[gym_node].geometry

    # ── 패널 0: 열환경 노출 점수 지도 ──────────────────────────────
    ax = axes[row_i][0]
    for etype, lw in lw_map.items():
        subset = edges_gdf[edges_gdf["edge_type"] == etype]
        if len(subset) == 0:
            continue
        colors = [c for c in subset["score_color"]]
        subset.plot(ax=ax, color=colors, linewidth=lw, alpha=0.85)

    # 출발지/체육센터 표시
    ax.plot(origin_geom.x, origin_geom.y, "o", color="black",
            markersize=9, zorder=6, label="출발지")
    ax.plot(gym_geom.x, gym_geom.y, "^", color="purple",
            markersize=10, zorder=6, markeredgecolor="white",
            markeredgewidth=1, label="체육센터")

    ax.set_title(f"{district_labels[district]}\n열환경 노출 점수",
                 fontsize=11, fontweight="bold")
    ax.set_axis_off()
    ax.legend(loc="upper left", fontsize=8, framealpha=0.85)

    # ── 패널 1, 2: 시나리오별 PPA 중첩 ─────────────────────────────
    for col_j, (sid, sc) in enumerate(SCENARIOS.items(), start=1):
        ax = axes[row_i][col_j]
        reachable = get_reachable(graphs[sid], origin, TIME_BUDGET_SEC)
        gym_ok    = gym_node in reachable

        edges_gdf["reachable"] = edges_gdf.index.map(
            lambda idx: idx[0] in reachable and idx[1] in reachable
        )

        # 배경: 미도달 구간 → 열환경 점수 색상 (흐리게)
        not_reach = edges_gdf[~edges_gdf["reachable"]]
        for etype, lw in lw_map.items():
            sub = not_reach[not_reach["edge_type"] == etype]
            if len(sub) == 0: continue
            colors = [(*c[:3], 0.25) for c in sub["score_color"]]
            sub.plot(ax=ax, color=colors, linewidth=lw*0.7)

        # 도달 구간 → 열환경 점수 색상 (진하게) + 테두리 강조
        reach = edges_gdf[edges_gdf["reachable"]]
        for etype, lw in lw_map.items():
            sub = reach[reach["edge_type"] == etype]
            if len(sub) == 0: continue
            colors = [(*c[:3], 0.92) for c in sub["score_color"]]
            sub.plot(ax=ax, color=colors, linewidth=lw*1.5)

        # PPA 경계 강조 (도달/미도달 경계 엣지를 굵은 선으로)
        # 한쪽 노드만 도달 가능한 경계 엣지
        boundary = edges_gdf[edges_gdf.index.map(
            lambda idx: (idx[0] in reachable) != (idx[1] in reachable)
        )]
        if len(boundary) > 0:
            boundary.plot(ax=ax, color=sc["ppa_color"],
                         linewidth=2.5, alpha=0.7, zorder=5)

        # 차단된 bridge 구간 명시 (빨간 굵은 선)
        blocked_bridge = edges_gdf[
            (edges_gdf["edge_type"] == "bridge") &
            (~edges_gdf["reachable"])
        ]
        if len(blocked_bridge) > 0:
            blocked_bridge.plot(ax=ax, color="#B71C1C", linewidth=4,
                               linestyle="--", zorder=7, alpha=0.9,
                               label="차단 교량")

        # 출발지 / 체육센터
        ax.plot(origin_geom.x, origin_geom.y, "o", color="black",
                markersize=9, zorder=8)
        ax.plot(gym_geom.x, gym_geom.y,
                "^" if gym_ok else "x",
                color="lime" if gym_ok else "black",
                markersize=12, zorder=8,
                markeredgecolor="black", markeredgewidth=1.2,
                label=f"체육센터 {'접근 가능' if gym_ok else '접근 불가'}")

        n_reach = len(reachable)
        n_total = len(G_base.nodes)
        ax.set_title(
            f"{district_labels[district].split(chr(10))[0]}\n"
            f"{sc['label']}\n"
            f"PPA: {n_reach:,}/{n_total:,} 노드 ({n_reach/n_total*100:.1f}%)",
            fontsize=10, fontweight="bold"
        )
        ax.set_axis_off()
        ax.legend(loc="upper left", fontsize=8, framealpha=0.85)

# ── 열환경 점수 컬러바 ────────────────────────────────────────────────
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar_ax = fig.add_axes([0.35, 0.02, 0.30, 0.018])
cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
cbar.set_label("열환경 노출 점수  (0 = 완전 노출/빨강  →  1 = 쾌적/초록)", fontsize=10)
cbar.set_ticks([0.1, 0.4, 0.8])
cbar.set_ticklabels(["0.1  교량\n(완전 노출)", "0.4  간선도로\n(부분 노출)", "0.8  이면도로·보행로\n(상대적 쾌적)"])

# 범례 패치
legend_items = [
    mpatches.Patch(color="#1565C0", alpha=0.7, label="PPA 경계 — 시나리오 A (쾌적)"),
    mpatches.Patch(color="#B71C1C", alpha=0.7, label="PPA 경계 — 시나리오 C (폭염 피크)"),
    mpatches.Patch(facecolor="white", edgecolor="gray", linewidth=0.5,
                   label="흐린 색 = PPA 미도달 구간"),
    mpatches.Patch(facecolor="white", edgecolor="gray", linewidth=1.5,
                   label="진한 색 = PPA 도달 구간"),
]
fig.legend(handles=legend_items, loc="lower right",
           bbox_to_anchor=(0.98, 0.04), fontsize=9, framealpha=0.92,
           title="PPA 범례", title_fontsize=9)

plt.suptitle(
    "열환경 노출 점수 지도 × PPA 중첩 분석\n"
    "링크별 열환경 노출 점수(초록=쾌적, 빨강=고노출)와 시나리오별 PPA가 대응하는 패턴 확인",
    fontsize=13, fontweight="bold", y=1.01
)
plt.tight_layout(rect=[0, 0.06, 1, 1])
out = os.path.join(FIG_DIR, "thermal_score_ppa_overlay.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out}")
print("완료.")
