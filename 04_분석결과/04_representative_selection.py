"""
대표 집계구 선정 + 4-panel PPA 비교 지도

선정 기준:
  응봉동: 시나리오 A 접근 가능 & 시나리오 C 접근 불가 → 가장 극적인 변화
  성수동: 시나리오 A 접근 가능 & 응봉동 대표와 체육센터까지 거리 유사 → 공정한 비교

출력:
  - representative_nodes.json  (다음 스크립트에서 재사용)
  - 4panel_ppa_comparison.png
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
import json, os
import pandas as pd

BASE      = os.path.dirname(os.path.abspath(__file__))
NET_PATH  = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
JIBGU_PATH = "/Users/jin/석사논문/통계지역경계/집계구.shp"
OUT_DIR   = BASE

WALK_SPEED_BASE = 4.5 * 1000 / 3600
TIME_BUDGET_SEC = 30 * 60
GYM_LAT, GYM_LON = 37.546419, 127.044641

SCENARIOS = {
    "A_쾌적_07시":   {"label": "Classic PPA\n(열환경 미적용)", "color": "#2196F3",
                     "speed_factor": {"bridge": 1.0, "major_road": 1.0, "local": 1.0}},
    "C_폭염피크_13시": {"label": "Thermal PPA\n(폭염 피크, 13:00)", "color": "#F44336",
                     "speed_factor": {"bridge": 0.0, "major_road": 0.4, "local": 0.7}},
}

def classify_edge(data):
    bridge  = data.get("bridge", None)
    highway = data.get("highway", "")
    if isinstance(highway, list): highway = highway[0]
    if bridge and bridge not in [None, "nan"]: return "bridge"
    if highway in ["trunk","trunk_link","primary","primary_link","secondary","secondary_link"]:
        return "major_road"
    return "local"

# ── 네트워크 ─────────────────────────────────────────────────────────
print("네트워크 로드...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()
edge_types = {(u,v,k): classify_edge(d) for u,v,k,d in G_base.edges(keys=True, data=True)}
gym_node   = ox.distance.nearest_nodes(G_base, GYM_LON, GYM_LAT)
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

# 시나리오별 그래프
def make_graph(scenario):
    G = G_base.copy()
    for u,v,k,data in G.edges(keys=True, data=True):
        factor = scenario["speed_factor"][edge_types.get((u,v,k),"local")]
        data["travel_time"] = float("inf") if factor==0 else data.get("length",0)/(WALK_SPEED_BASE*factor)
    return G

graphs = {sid: make_graph(sc) for sid, sc in SCENARIOS.items()}

# ── 집계구 로드 ──────────────────────────────────────────────────────
print("집계구 로드...")
jibgu = gpd.read_file(JIBGU_PATH).set_crs("EPSG:5179", allow_override=True)
jibgu_wgs = jibgu.to_crs("EPSG:4326")
jibgu_utm = jibgu.to_crs("EPSG:32652")

eungbong_wgs = jibgu_wgs[jibgu_wgs["ADM_NM"] == "응봉동"].copy()
sungsu_wgs   = jibgu_wgs[jibgu_wgs["ADM_NM"].str.contains("성수", na=False)].copy()
eungbong_utm = jibgu_utm[jibgu["ADM_NM"] == "응봉동"].copy()
sungsu_utm   = jibgu_utm[jibgu["ADM_NM"].str.contains("성수", na=False)].copy()

eungbong_wgs["centroid"] = eungbong_utm.centroid.to_crs("EPSG:4326").values
sungsu_wgs["centroid"]   = sungsu_utm.centroid.to_crs("EPSG:4326").values

eungbong_wgs["origin_node"] = eungbong_wgs["centroid"].apply(
    lambda g: ox.distance.nearest_nodes(G_base, g.x, g.y))
sungsu_wgs["origin_node"] = sungsu_wgs["centroid"].apply(
    lambda g: ox.distance.nearest_nodes(G_base, g.x, g.y))

# ── 접근성 계산 ──────────────────────────────────────────────────────
print("접근성 계산...")
def compute_access(origin_nodes, graphs, gym_node, budget):
    records = []
    for node in origin_nodes:
        row = {"origin_node": node}
        for sid, G in graphs.items():
            try:
                lengths = nx.single_source_dijkstra_path_length(
                    G, node, cutoff=budget, weight="travel_time")
                reachable = set(lengths.keys())
                row[f"{sid}_accessible"] = gym_node in reachable
                row[f"{sid}_gym_min"]    = lengths.get(gym_node, None)
                row[f"{sid}_node_count"] = len(reachable)
            except:
                row[f"{sid}_accessible"] = False
                row[f"{sid}_gym_min"]    = None
                row[f"{sid}_node_count"] = 0
        records.append(row)
    return pd.DataFrame(records)

e_nodes = eungbong_wgs["origin_node"].unique()
s_nodes = sungsu_wgs["origin_node"].unique()
e_df = compute_access(e_nodes, graphs, gym_node, TIME_BUDGET_SEC)
s_df = compute_access(s_nodes, graphs, gym_node, TIME_BUDGET_SEC)

# ── 대표 집계구 선정 ─────────────────────────────────────────────────
# 응봉동: A 접근 가능 & C 접근 불가 → 교량에 가장 가까운 노드
A_sid = "A_쾌적_07시"
C_sid = "C_폭염피크_13시"

e_dramatic = e_df[e_df[f"{A_sid}_accessible"] & ~e_df[f"{C_sid}_accessible"]]
print(f"응봉동 극적 변화 집계구: {len(e_dramatic)}개")

# 고산자로 교량 노드 기준 (287287152)
bridge_ref_node = 287287152
bridge_geom = nodes_gdf.loc[bridge_ref_node].geometry if bridge_ref_node in nodes_gdf.index else None

if bridge_geom and len(e_dramatic) > 0:
    e_dramatic = e_dramatic.copy()
    e_dramatic["dist_to_bridge"] = e_dramatic["origin_node"].apply(
        lambda n: nodes_gdf.loc[n].geometry.distance(bridge_geom)
        if n in nodes_gdf.index else 9999)
    rep_eungbong_node = e_dramatic.sort_values("dist_to_bridge").iloc[0]["origin_node"]
else:
    # 폴백: A 접근 가능한 것 중 gym_min 기준
    fallback = e_df[e_df[f"{A_sid}_accessible"]]
    rep_eungbong_node = fallback.sort_values(f"{A_sid}_gym_min").iloc[-1]["origin_node"]

# 성수동: A 접근 가능 & 응봉동 대표와 gym_min 유사
e_rep_gym_min = e_df[e_df["origin_node"]==rep_eungbong_node][f"{A_sid}_gym_min"].values
e_rep_gym_min = float(e_rep_gym_min[0]) if len(e_rep_gym_min) > 0 else 1000

s_accessible = s_df[s_df[f"{A_sid}_accessible"]].copy()
s_accessible["gym_min_diff"] = (s_accessible[f"{A_sid}_gym_min"] - e_rep_gym_min).abs()
rep_sungsu_node = s_accessible.sort_values("gym_min_diff").iloc[0]["origin_node"]

print(f"대표 응봉동 origin 노드: {rep_eungbong_node}")
print(f"대표 성수동 origin 노드: {rep_sungsu_node}")

# 선정 결과 저장
rep_info = {
    "응봉동": int(rep_eungbong_node),
    "성수동": int(rep_sungsu_node),
    "gym_node": int(gym_node),
}
with open(os.path.join(OUT_DIR, "representative_nodes.json"), "w", encoding="utf-8") as f:
    json.dump(rep_info, f, ensure_ascii=False, indent=2)

# ── 4-panel PPA 비교 지도 ────────────────────────────────────────────
print("\n4-panel PPA 지도 생성...")

def get_reachable(G, origin, budget):
    try:
        lengths = nx.single_source_dijkstra_path_length(G, origin, cutoff=budget, weight="travel_time")
        return set(lengths.keys()), lengths
    except:
        return set(), {}

panels = [
    {"district": "응봉동", "origin": rep_eungbong_node, "scenario": A_sid},
    {"district": "응봉동", "origin": rep_eungbong_node, "scenario": C_sid},
    {"district": "성수동", "origin": rep_sungsu_node,   "scenario": A_sid},
    {"district": "성수동", "origin": rep_sungsu_node,   "scenario": C_sid},
]

fig, axes = plt.subplots(2, 2, figsize=(20, 16))
axes = axes.flatten()

district_colors = {"응봉동": "#1565C0", "성수동": "#2E7D32"}

for ax, panel in zip(axes, panels):
    origin  = panel["origin"]
    sid     = panel["scenario"]
    sc      = SCENARIOS[sid]
    district= panel["district"]

    reachable, lengths = get_reachable(graphs[sid], origin, TIME_BUDGET_SEC)

    # 엣지 도달 여부
    edges_gdf["reachable"] = edges_gdf.index.map(
        lambda idx: idx[0] in reachable and idx[1] in reachable)

    # 배경
    edges_gdf[~edges_gdf["reachable"]].plot(
        ax=ax, color="#e8e8e8", linewidth=0.4, alpha=0.7)
    # 도달 가능
    edges_gdf[edges_gdf["reachable"]].plot(
        ax=ax, color=sc["color"], linewidth=1.1, alpha=0.85)

    # 주요 교량 강조 (bridge=yes, primary)
    bridge_mask = (
        edges_gdf["bridge"].notna() &
        edges_gdf["highway"].astype(str).str.contains("primary", na=False)
    )
    if bridge_mask.any():
        edges_gdf[bridge_mask].plot(ax=ax, color="purple", linewidth=2.5,
                                    zorder=5, alpha=0.9, label="주요 교량")

    # 출발지
    origin_geom = nodes_gdf.loc[origin].geometry
    ax.plot(origin_geom.x, origin_geom.y, "o", color=district_colors[district],
            markersize=10, zorder=7, label=f"{district} 출발지")

    # 체육센터
    gym_geom = nodes_gdf.loc[gym_node].geometry
    gym_color = "lime" if gym_node in reachable else "black"
    gym_marker = "^" if gym_node in reachable else "x"
    ax.plot(gym_geom.x, gym_geom.y, gym_marker, color=gym_color,
            markersize=12, zorder=7, markeredgecolor="black", markeredgewidth=1.2,
            label="체육센터 " + ("(접근 가능)" if gym_node in reachable else "(접근 불가)"))

    n_reach = len(reachable)
    n_total = len(G_base.nodes)
    ax.set_title(
        f"{district} — {sc['label']}\n"
        f"도달 노드 {n_reach:,}/{n_total:,} ({n_reach/n_total*100:.1f}%)",
        fontsize=12, fontweight="bold"
    )
    ax.legend(loc="upper left", fontsize=8, framealpha=0.8)
    ax.set_axis_off()

# 행 레이블
fig.text(0.01, 0.73, "응봉동\n(교량 통과 필요)", va="center", ha="center",
         rotation=90, fontsize=13, fontweight="bold", color="#1565C0")
fig.text(0.01, 0.27, "성수동\n(비교군)", va="center", ha="center",
         rotation=90, fontsize=13, fontweight="bold", color="#2E7D32")

plt.suptitle(
    "Classic PPA vs Thermal-Inclusive PPA 비교\n"
    "출발지: 응봉동 / 성수동 대표 집계구 중심점 | 도착지: 성동구민종합체육센터 | 시간예산: 30분",
    fontsize=14, fontweight="bold", y=1.01
)
plt.tight_layout()
out = os.path.join(FIG_DIR, "4panel_ppa_comparison.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out}")
print("완료.")
