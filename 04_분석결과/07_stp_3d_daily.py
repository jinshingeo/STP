"""
3D Space-Time Prism — 하루 시간대별 비교 (07:00 ~ 21:00)

Z축  : 시각 (time of day, 07시 ~ 21시)
XY축 : 공간 (UTM 좌표 기준, 미터)
바닥 : 성동구 보행 네트워크 지도

Classic PPA  → 시간대 무관 원기둥 (보행속도 고정, 시간대 변수 없음)
Thermal PPA  → 폭염 시간대에 허리가 잘록해지는 동적 프리즘

폭염일 시간대별 UTCI 시나리오 매핑 (여름철 기상청 폭염특보 기준):
  07~08시  : 시나리오 A — 쾌적 (UTCI < 26°C)
  09~10시  : 시나리오 B — 보통 더위 (UTCI 26~32°C)
  11~16시  : 시나리오 C — 폭염 피크 (UTCI > 38°C)
  17~18시  : 시나리오 B — 완화 중
  19~21시  : 시나리오 A — 야간 쾌적

출력: stp_3d_daily.png
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
from shapely.geometry import MultiPoint
import numpy as np
import json, os
import pyproj

import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

BASE     = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
OUT_DIR  = BASE

WALK_SPEED_BASE = 4.5 * 1000 / 3600
TIME_BUDGET_SEC = 30 * 60
GYM_LAT, GYM_LON = 37.546419, 127.044641

HOURS = list(range(7, 22))   # 07 ~ 21시

# 시간대 → 시나리오 매핑
def hour_to_scenario(h):
    if h in [7, 8]:          return "A"
    elif h in [9, 10]:       return "B"
    elif 11 <= h <= 16:      return "C"
    elif h in [17, 18]:      return "B"
    else:                    return "A"   # 19~21

SPEED_FACTORS = {
    "A": {"bridge": 1.0, "major_road": 1.0, "local": 1.0},
    "B": {"bridge": 0.5, "major_road": 0.8, "local": 0.9},
    "C": {"bridge": 0.0, "major_road": 0.4, "local": 0.7},
}

# 시간대별 색상 (쾌적=파랑, 보통=주황, 폭염=빨강)
SCENARIO_COLORS = {
    "A": {"face": (0.13, 0.47, 0.71, 0.20), "edge": (0.08, 0.30, 0.55, 0.70)},
    "B": {"face": (0.99, 0.60, 0.10, 0.22), "edge": (0.80, 0.40, 0.00, 0.75)},
    "C": {"face": (0.84, 0.15, 0.16, 0.25), "edge": (0.60, 0.05, 0.05, 0.80)},
}

CLASSIC_STYLE = {"face": (0.40, 0.60, 0.90, 0.10), "edge": (0.20, 0.40, 0.75, 0.45)}

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

# WGS84 → UTM 변환
transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32652", always_xy=True)
nodes_utm = {nid: transformer.transform(row.geometry.x, row.geometry.y)
             for nid, row in nodes_gdf.iterrows()}
all_x = [v[0] for v in nodes_utm.values()]
all_y = [v[1] for v in nodes_utm.values()]
cx, cy = np.mean(all_x), np.mean(all_y)
nodes_norm = {n: (x - cx, y - cy) for n, (x, y) in nodes_utm.items()}

# 대표 노드 로드
with open(os.path.join(OUT_DIR, "representative_nodes.json"), encoding="utf-8") as f:
    rep_info = json.load(f)
origins = {"응봉동": rep_info["응봉동"], "성수동": rep_info["성수동"]}

# ── 시나리오별 그래프 (A/B/C 3개만) ──────────────────────────────────
def make_graph(speed_factor):
    G = G_base.copy()
    for u,v,k,data in G.edges(keys=True, data=True):
        factor = speed_factor[edge_types.get((u,v,k),"local")]
        data["travel_time"] = float("inf") if factor==0 else data.get("length",0)/(WALK_SPEED_BASE*factor)
    return G

print("시나리오 그래프 준비...")
scenario_graphs = {sid: make_graph(sf) for sid, sf in SPEED_FACTORS.items()}

# ── convex hull 계산 ─────────────────────────────────────────────────
def get_hull(G, origin, budget, nodes_norm):
    try:
        lengths = nx.single_source_dijkstra_path_length(G, origin, cutoff=budget, weight="travel_time")
    except:
        return None, 0
    reachable = set(lengths.keys())
    coords = [nodes_norm[n] for n in reachable if n in nodes_norm]
    if len(coords) < 3:
        return None, len(reachable)
    hull = MultiPoint(coords).convex_hull
    if hull.geom_type == "Polygon":
        xs, ys = hull.exterior.coords.xy
        return list(zip(xs, ys)), len(reachable)
    return None, len(reachable)

# Classic hull (시간 무관 — 한 번만 계산)
print("Classic PPA hull 계산...")
classic_hull, classic_n = get_hull(scenario_graphs["A"], None, TIME_BUDGET_SEC, nodes_norm)
# 응봉동/성수동 각각 계산
classic_hulls = {}
for district, origin in origins.items():
    classic_hulls[district], _ = get_hull(scenario_graphs["A"], origin, TIME_BUDGET_SEC, nodes_norm)

# Thermal hull (시간대별)
print("Thermal PPA hull 계산 (시간대별)...")
thermal_hulls = {district: {} for district in origins}
for district, origin in origins.items():
    for h in HOURS:
        sc = hour_to_scenario(h)
        hull, n = get_hull(scenario_graphs[sc], origin, TIME_BUDGET_SEC, nodes_norm)
        thermal_hulls[district][h] = {"hull": hull, "n": n, "scenario": sc}
    print(f"  {district} 완료")

# ── 바닥면 네트워크 엣지 준비 ────────────────────────────────────────
print("바닥면 네트워크 준비...")
base_z = 6.5   # 시간 축 07시 바로 아래
base_segs = []
for u, v, k, data in G_base.edges(keys=True, data=True):
    if u in nodes_norm and v in nodes_norm:
        x0, y0 = nodes_norm[u]
        x1, y1 = nodes_norm[v]
        base_segs.append([(x0, y0, base_z), (x1, y1, base_z)])

# ── 3D 시각화 ────────────────────────────────────────────────────────
print("3D 시각화 렌더링...")

fig = plt.figure(figsize=(24, 11))

district_info = {
    "응봉동": {"title": "응봉동 대표 집계구\n(중랑천 교량 통과 필요 — bottleneck 구간)",
               "label_color": "#1565C0"},
    "성수동": {"title": "성수동 대표 집계구\n(비교군 — 교량 bottleneck 없음)",
               "label_color": "#2E7D32"},
}

for col, (district, origin) in enumerate(origins.items()):
    ax = fig.add_subplot(1, 2, col+1, projection="3d")
    info = district_info[district]

    ox_n, oy_n   = nodes_norm[origin]
    gym_x, gym_y = nodes_norm.get(gym_node, (None, None))

    # ── 바닥면 네트워크 (성동구 지도) ──────────────────────────────
    lc = Line3DCollection(base_segs, colors=[(0.45,0.45,0.45,0.75)],
                          linewidths=0.7, zorder=1)
    ax.add_collection3d(lc)

    # 출발지 바닥 점
    ax.scatter([ox_n], [oy_n], [base_z], color="black", s=60,
               zorder=10, depthshade=False)

    # 체육센터 바닥 표시
    if gym_x is not None:
        ax.scatter([gym_x], [gym_y], [base_z], color="green",
                   marker="^", s=80, zorder=10, depthshade=False)

    # ── Classic PPA 원기둥 (시간 무관) ─────────────────────────────
    c_hull = classic_hulls[district]
    if c_hull:
        for h in HOURS:
            verts = [(x, y, h) for x, y in c_hull]
            poly  = Poly3DCollection([verts],
                                     facecolor=CLASSIC_STYLE["face"],
                                     edgecolor=CLASSIC_STYLE["edge"],
                                     linewidth=0.6, zorder=2)
            ax.add_collection3d(poly)
        # 원기둥 수직 윤곽선 (양쪽 끝 연결)
        step = max(1, len(c_hull) // 10)
        for i in range(0, len(c_hull), step):
            px, py = c_hull[i]
            ax.plot([px, px], [py, py], [HOURS[0], HOURS[-1]],
                    color=CLASSIC_STYLE["edge"][:3], linewidth=0.5,
                    alpha=0.4, zorder=2)

    # ── Thermal PPA 프리즘 (시간대별) ──────────────────────────────
    prev_hull_data = None
    for h in HOURS:
        td = thermal_hulls[district][h]
        hull_verts = td["hull"]
        sc         = td["scenario"]
        style      = SCENARIO_COLORS[sc]

        if hull_verts is None:
            prev_hull_data = None
            continue

        verts = [(x, y, h) for x, y in hull_verts]
        poly  = Poly3DCollection([verts],
                                 facecolor=style["face"],
                                 edgecolor=style["edge"],
                                 linewidth=1.0, zorder=4)
        ax.add_collection3d(poly)

        # 윤곽선 강조
        hx = [v[0] for v in verts] + [verts[0][0]]
        hy = [v[1] for v in verts] + [verts[0][1]]
        hz = [h] * (len(verts)+1)
        ax.plot(hx, hy, hz, color=style["edge"][:3],
                linewidth=1.3, alpha=style["edge"][3], zorder=5)

        # 이전 슬라이스와 수직 연결선
        if prev_hull_data is not None:
            prev_verts, prev_h = prev_hull_data
            step = max(1, len(hull_verts) // 10)
            for i in range(0, len(hull_verts), step):
                px, py = hull_verts[i]
                dists = [(px-pv[0])**2 + (py-pv[1])**2 for pv in prev_verts]
                cpv = prev_verts[np.argmin(dists)]
                ax.plot([px, cpv[0]], [py, cpv[1]], [h, prev_h],
                        color=style["edge"][:3], linewidth=0.5,
                        alpha=0.45, zorder=3)

        prev_hull_data = (hull_verts, h)

    # ── 출발지 수직선 ────────────────────────────────────────────
    ax.plot([ox_n, ox_n], [oy_n, oy_n], [base_z, HOURS[-1]],
            color="black", linewidth=1.0, linestyle=":", alpha=0.6, zorder=6)

    # ── 체육센터 수직선 ──────────────────────────────────────────
    if gym_x is not None:
        ax.plot([gym_x, gym_x], [gym_y, gym_y], [base_z, HOURS[-1]],
                color="green", linewidth=1.5, linestyle="--", alpha=0.7, zorder=6)

    # ── 폭염 구간 표시선 (11시, 17시) ────────────────────────────
    for h_mark, label, color in [(11, "← 폭염 시작", "#b71c1c"), (17, "← 폭염 완화", "#e65100")]:
        # 해당 시간 수평면에 점선 테두리
        if classic_hulls[district]:
            hx = [x for x, y in classic_hulls[district]]
            hy = [y for x, y in classic_hulls[district]]
            ax.plot(hx + [hx[0]], hy + [hy[0]], [h_mark]*(len(hx)+1),
                    color=color, linewidth=0.8, linestyle="--", alpha=0.5)
        xmax = max(nodes_norm[origin][0], 0) + 1200
        ax.text(xmax, oy_n, h_mark, label, fontsize=7.5,
                color=color, va="center", zorder=10)

    # ── 축 설정 ─────────────────────────────────────────────────
    ax.set_zlim(base_z, 22)
    ax.set_zticks(HOURS)
    ax.set_zticklabels([f"{h:02d}:00" for h in HOURS], fontsize=7)
    ax.set_xlabel("서 ← → 동 (m)", fontsize=9, labelpad=8)
    ax.set_ylabel("남 ← → 북 (m)", fontsize=9, labelpad=8)
    ax.set_zlabel("시각 (time of day)", fontsize=9, labelpad=12)
    ax.tick_params(axis='x', labelsize=6)
    ax.tick_params(axis='y', labelsize=6)
    ax.view_init(elev=22, azim=-50)
    ax.set_title(info["title"], fontsize=12, fontweight="bold", pad=14,
                 color=info["label_color"])

    # 격자 제거 (깔끔하게)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('0.85')
    ax.yaxis.pane.set_edgecolor('0.85')
    ax.zaxis.pane.set_edgecolor('0.85')

# ── 공통 범례 ────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(facecolor=(0.40,0.60,0.90,0.5), edgecolor=(0.20,0.40,0.75),
                   linewidth=1.2, label="Classic PPA (열환경 미적용 — 시간대 무관 원기둥)"),
    mpatches.Patch(facecolor=SCENARIO_COLORS["A"]["face"], edgecolor=SCENARIO_COLORS["A"]["edge"][:3],
                   linewidth=1.2, label="Thermal PPA — 쾌적 (07~08, 19~21시, UTCI<26°C)"),
    mpatches.Patch(facecolor=SCENARIO_COLORS["B"]["face"], edgecolor=SCENARIO_COLORS["B"]["edge"][:3],
                   linewidth=1.2, label="Thermal PPA — 보통 더위 (09~10, 17~18시, UTCI 26~32°C)"),
    mpatches.Patch(facecolor=SCENARIO_COLORS["C"]["face"], edgecolor=SCENARIO_COLORS["C"]["edge"][:3],
                   linewidth=1.2, label="Thermal PPA — 폭염 피크 (11~16시, UTCI>38°C)"),
    mpatches.Patch(facecolor=(0.75,0.75,0.75,0.5), edgecolor="gray",
                   linewidth=0.5, label="성동구 보행 네트워크 (바닥면)"),
]
fig.legend(handles=legend_items, loc="lower center", ncol=3,
           fontsize=9, framealpha=0.92, bbox_to_anchor=(0.5, -0.04),
           title="범례  |  출발지: 집계구 대표 중심점  |  시간예산: 30분  |  녹색 점선: 성동구민종합체육센터",
           title_fontsize=9)

plt.suptitle(
    "Space-Time Prism 3D: 하루 시간대별 보행 접근 공간 변화 (07:00 ~ 21:00)\n"
    "Classic PPA는 시간대 무관 원기둥 — Thermal PPA는 폭염 시간대에 공간이 수축하는 동적 프리즘",
    fontsize=13, fontweight="bold", y=1.02
)

plt.tight_layout()
out = os.path.join(FIG_DIR, "stp_3d_daily.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"\n저장: {out}")
print("완료.")
