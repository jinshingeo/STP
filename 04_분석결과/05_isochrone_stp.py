"""
등시선(Isochrone) 기반 Space-Time Prism 비교 시각화

대표 집계구(응봉동 vs 성수동) × Classic vs Thermal PPA
5분 단위 등시선 레이어로 '프리즘이 줄어드는' 효과를 표현

출력: isochrone_stp_comparison.png
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.cm as cm
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
TIME_BANDS_SEC  = [300, 600, 900, 1200, 1500, 1800]  # 5, 10, 15, 20, 25, 30분
BAND_COLORS     = ["#1a9641", "#78c679", "#c2e699", "#fed976", "#fd8d3c", "#e31a1c"]
# 초록(가까움) → 빨강(멀음)

GYM_LAT, GYM_LON = 37.546419, 127.044641

SCENARIOS = {
    "classic": {
        "label": "Classic PPA\n(열환경 미적용)",
        "speed_factor": {"bridge": 1.0, "major_road": 1.0, "local": 1.0},
    },
    "thermal": {
        "label": "Thermal PPA\n(폭염 피크, 13:00, UTCI>38°C)",
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

# 대표 노드 로드
rep_path = os.path.join(OUT_DIR, "representative_nodes.json")
with open(rep_path, encoding="utf-8") as f:
    rep_info = json.load(f)

origins = {
    "응봉동": rep_info["응봉동"],
    "성수동": rep_info["성수동"],
}

# ── 시나리오별 그래프 ─────────────────────────────────────────────────
def make_graph(speed_factor):
    G = G_base.copy()
    for u,v,k,data in G.edges(keys=True, data=True):
        factor = speed_factor[edge_types.get((u,v,k),"local")]
        data["travel_time"] = float("inf") if factor==0 else data.get("length",0)/(WALK_SPEED_BASE*factor)
    return G

graphs = {sid: make_graph(sc["speed_factor"]) for sid, sc in SCENARIOS.items()}

# ── 등시선 계산 함수 ──────────────────────────────────────────────────
def compute_isochrone_edges(G, origin, time_bands):
    """
    각 엣지에 시간 밴드 번호를 할당.
    엣지 양 끝 노드의 평균 도달시간으로 분류.
    """
    try:
        lengths = nx.single_source_dijkstra_path_length(
            G, origin, cutoff=time_bands[-1], weight="travel_time")
    except:
        return {}, set()

    reachable = set(lengths.keys())

    edge_band = {}
    for u,v,k in G.edges(keys=True):
        if u not in reachable or v not in reachable:
            continue
        avg_t = (lengths[u] + lengths[v]) / 2
        for i, cutoff in enumerate(time_bands):
            if avg_t <= cutoff:
                edge_band[(u,v,k)] = i
                break

    return edge_band, reachable

# ── 2×2 패널 시각화 ──────────────────────────────────────────────────
print("등시선 시각화 생성...")
fig, axes = plt.subplots(2, 2, figsize=(20, 16))

district_list  = ["응봉동", "성수동"]
scenario_list  = ["classic", "thermal"]
district_colors = {"응봉동": "#1565C0", "성수동": "#2E7D32"}

for row_i, district in enumerate(district_list):
    origin = origins[district]
    origin_geom = nodes_gdf.loc[origin].geometry
    gym_geom    = nodes_gdf.loc[gym_node].geometry

    for col_j, sid in enumerate(scenario_list):
        ax = axes[row_i][col_j]
        sc = SCENARIOS[sid]

        edge_band, reachable = compute_isochrone_edges(
            graphs[sid], origin, TIME_BANDS_SEC)

        # 배경 (미도달)
        bg_edges = edges_gdf[edges_gdf.index.map(
            lambda idx: idx[0] not in reachable or idx[1] not in reachable)]
        bg_edges.plot(ax=ax, color="#ececec", linewidth=0.4, alpha=0.8)

        # 등시선 레이어 (멀리서부터 그려야 가까운 것이 위에 올라옴)
        for band_i in reversed(range(len(TIME_BANDS_SEC))):
            band_edges_idx = [idx for idx, b in edge_band.items() if b == band_i]
            if not band_edges_idx:
                continue
            # edges_gdf에서 해당 엣지 필터
            mask = edges_gdf.index.map(
                lambda idx: edge_band.get(idx) == band_i)
            if mask.any():
                edges_gdf[mask].plot(
                    ax=ax, color=BAND_COLORS[band_i],
                    linewidth=1.4 - band_i * 0.1, alpha=0.9, zorder=band_i+2)

        # 주요 교량 강조
        bridge_mask = (
            edges_gdf["bridge"].notna() &
            edges_gdf["highway"].astype(str).str.contains("primary", na=False)
        )
        if bridge_mask.any():
            edges_gdf[bridge_mask].plot(ax=ax, color="purple", linewidth=2.5,
                                        zorder=10, alpha=0.9)

        # 출발지
        ax.plot(origin_geom.x, origin_geom.y, "o",
                color=district_colors[district], markersize=11,
                zorder=12, markeredgecolor="white", markeredgewidth=1.5,
                label=f"{district} 출발지")

        # 체육센터
        gym_accessible = gym_node in reachable
        ax.plot(gym_geom.x, gym_geom.y,
                "^" if gym_accessible else "x",
                color="lime" if gym_accessible else "black",
                markersize=13, zorder=12,
                markeredgecolor="black", markeredgewidth=1.5,
                label="체육센터 " + ("(도달 가능 O)" if gym_accessible else "(도달 불가 X)"))

        n_reach = len(reachable)
        n_total = len(G_base.nodes)
        ax.set_title(
            f"{sc['label']}\n"
            f"도달 노드 {n_reach:,} / {n_total:,}  ({n_reach/n_total*100:.1f}%)",
            fontsize=11, fontweight="bold", pad=8
        )
        ax.legend(loc="upper left", fontsize=8, framealpha=0.85)
        ax.set_axis_off()

# 행 레이블
fig.text(0.005, 0.73, "응봉동\n(교량 통과 필요)", va="center", ha="left",
         rotation=90, fontsize=13, fontweight="bold", color="#1565C0")
fig.text(0.005, 0.27, "성수동\n(비교군)", va="center", ha="left",
         rotation=90, fontsize=13, fontweight="bold", color="#2E7D32")

# 등시선 범례 (공통)
legend_patches = [
    mpatches.Patch(color=BAND_COLORS[i],
                   label=f"{TIME_BANDS_SEC[i]//60}분 이내")
    for i in range(len(TIME_BANDS_SEC))
]
legend_patches.append(mpatches.Patch(color="purple", label="주요 교량 (열환경 노출)"))
fig.legend(handles=legend_patches, loc="lower center", ncol=7,
           fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, -0.02),
           title="등시선 (출발지로부터의 도달 시간)", title_fontsize=10)

plt.suptitle(
    "Space-Time Prism 등시선 비교: Classic PPA vs Thermal-Inclusive PPA\n"
    "응봉동 대표 집계구(교량 bottleneck) vs 성수동 대표 집계구(비교군) | 시간예산: 30분",
    fontsize=14, fontweight="bold", y=1.02
)
plt.tight_layout()
out = os.path.join(OUT_DIR, "isochrone_stp_comparison.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out}")

# ── 정량 비교 요약 ────────────────────────────────────────────────────
print("\n=== 대표 집계구 정량 비교 ===")
for district, origin in origins.items():
    print(f"\n{district} (origin: {origin})")
    for sid, sc in SCENARIOS.items():
        _, reachable = compute_isochrone_edges(graphs[sid], origin, TIME_BANDS_SEC)
        gym_ok = "O 가능" if gym_node in reachable else "X 불가"
        n = len(reachable)
        gym_ok = "O 가능" if gym_node in reachable else "X 불가"
        print(f"  {sc['label'].split(chr(10))[0]:25s}: {n:4d} 노드 ({n/len(G_base.nodes)*100:4.1f}%) | 체육센터 {gym_ok}")

print("\n완료.")
