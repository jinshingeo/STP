"""
3D Space-Time Prism 시각화

X, Y: 공간 (UTM 투영)
Z   : 시간 (0 → 30분)

각 5분 슬라이스의 도달 가능 노드 convex hull을 폴리곤으로 쌓아올려
Classic PPA(파랑)와 Thermal PPA(빨강) 프리즘을 같은 공간에 비교.

출력: stp_3d_prism.png
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import MultiPoint
import numpy as np
import json, os
import pyproj
from functools import partial

BASE     = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
OUT_DIR  = BASE

WALK_SPEED_BASE = 4.5 * 1000 / 3600
TIME_BUDGET_SEC = 30 * 60
TIME_STEPS_SEC  = [0, 300, 600, 900, 1200, 1500, 1800]  # 0~30분, 5분 간격
TIME_STEPS_MIN  = [t // 60 for t in TIME_STEPS_SEC]

GYM_LAT, GYM_LON = 37.546419, 127.044641

SCENARIOS = {
    "classic": {
        "label": "Classic PPA (열환경 미적용)",
        "face_color": (0.13, 0.47, 0.71),   # 파랑
        "edge_color": (0.06, 0.25, 0.45),
        "alpha_face": 0.18,
        "alpha_edge": 0.6,
        "speed_factor": {"bridge": 1.0, "major_road": 1.0, "local": 1.0},
    },
    "thermal": {
        "label": "Thermal PPA (폭염 피크, UTCI>38°C)",
        "face_color": (0.84, 0.15, 0.16),   # 빨강
        "edge_color": (0.55, 0.06, 0.06),
        "alpha_face": 0.22,
        "alpha_edge": 0.7,
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

# WGS84 → UTM 변환 (미터 단위)
transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32652", always_xy=True)

nodes_utm = {}
for nid, row in nodes_gdf.iterrows():
    x, y = transformer.transform(row.geometry.x, row.geometry.y)
    nodes_utm[nid] = (x, y)

# 원점 기준 정규화 (시각화 편의)
all_x = [v[0] for v in nodes_utm.values()]
all_y = [v[1] for v in nodes_utm.values()]
cx, cy = np.mean(all_x), np.mean(all_y)
nodes_utm_norm = {n: (x - cx, y - cy) for n, (x, y) in nodes_utm.items()}

# 대표 노드 로드
with open(os.path.join(OUT_DIR, "representative_nodes.json"), encoding="utf-8") as f:
    rep_info = json.load(f)

origins = {"응봉동": rep_info["응봉동"], "성수동": rep_info["성수동"]}

# ── 그래프 준비 ──────────────────────────────────────────────────────
def make_graph(speed_factor):
    G = G_base.copy()
    for u,v,k,data in G.edges(keys=True, data=True):
        factor = speed_factor[edge_types.get((u,v,k),"local")]
        data["travel_time"] = float("inf") if factor==0 else data.get("length",0)/(WALK_SPEED_BASE*factor)
    return G

graphs = {sid: make_graph(sc["speed_factor"]) for sid, sc in SCENARIOS.items()}

# ── convex hull 계산 함수 ────────────────────────────────────────────
def get_hull_at_time(G, origin, cutoff_sec, nodes_utm_norm):
    """시간 cutoff까지 도달 가능한 노드의 convex hull 꼭짓점 반환"""
    try:
        lengths = nx.single_source_dijkstra_path_length(
            G, origin, cutoff=cutoff_sec, weight="travel_time")
    except:
        return None, set()

    reachable = set(lengths.keys())
    coords = [nodes_utm_norm[n] for n in reachable if n in nodes_utm_norm]

    if len(coords) < 3:
        return None, reachable

    hull = MultiPoint(coords).convex_hull
    if hull.geom_type == "Polygon":
        xs, ys = hull.exterior.coords.xy
        return list(zip(xs, ys)), reachable
    return None, reachable

# ── 3D 시각화 ────────────────────────────────────────────────────────
print("3D 프리즘 시각화 생성...")

import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

fig = plt.figure(figsize=(22, 10))

district_titles = {
    "응봉동": "응봉동 대표 집계구\n(교량 통과 필요 — bottleneck 효과)",
    "성수동": "성수동 대표 집계구\n(비교군 — 교량 bottleneck 없음)",
}

for col, (district, origin) in enumerate(origins.items()):
    ax = fig.add_subplot(1, 2, col+1, projection="3d")

    # 출발지 UTM 좌표
    ox_utm, oy_utm = nodes_utm_norm[origin]
    gym_utm_x, gym_utm_y = nodes_utm_norm.get(gym_node, (None, None))

    for sid, sc in SCENARIOS.items():
        G = graphs[sid]
        hull_polygons = []
        hull_times    = []

        prev_hull = None
        for t_sec, t_min in zip(TIME_STEPS_SEC[1:], TIME_STEPS_MIN[1:]):
            hull_verts, reachable = get_hull_at_time(G, origin, t_sec, nodes_utm_norm)
            if hull_verts is None:
                continue

            z = t_min  # z축 = 분 단위 시간

            # 수평 폴리곤 (해당 시간 슬라이스)
            verts_3d = [(x, y, z) for x, y in hull_verts]
            poly = Poly3DCollection([verts_3d],
                                    alpha=sc["alpha_face"],
                                    facecolor=sc["face_color"],
                                    edgecolor=sc["edge_color"],
                                    linewidth=0.8)
            ax.add_collection3d(poly)

            # 윤곽선만 별도로 그리기 (더 선명하게)
            hx = [v[0] for v in hull_verts]
            hy = [v[1] for v in hull_verts]
            hz = [z] * len(hull_verts)
            ax.plot(hx, hy, hz, color=sc["edge_color"],
                    linewidth=1.2, alpha=sc["alpha_edge"])

            # 이전 슬라이스와 수직 벽으로 연결 (프리즘 측면)
            if prev_hull is not None:
                prev_verts, prev_z = prev_hull
                # 샘플링해서 수직 선 그리기 (대략 8개 점)
                step = max(1, len(hull_verts) // 8)
                for i in range(0, len(hull_verts), step):
                    # 현재 슬라이스 점 → 이전 슬라이스에서 가장 가까운 점
                    px, py = hull_verts[i]
                    # 이전 hull에서 가장 가까운 점 찾기
                    dists = [(px - pv[0])**2 + (py - pv[1])**2 for pv in prev_verts]
                    closest_prev = prev_verts[np.argmin(dists)]
                    ax.plot([px, closest_prev[0]], [py, closest_prev[1]],
                            [z, prev_z],
                            color=sc["edge_color"], linewidth=0.5,
                            alpha=sc["alpha_edge"] * 0.6)

            prev_hull = (hull_verts, z)

        # 라벨용 더미 패치
        ax.plot([], [], [], color=sc["face_color"],
                linewidth=3, label=sc["label"])

    # 출발지 표시 (z=0 바닥에)
    ax.scatter([ox_utm], [oy_utm], [0],
               color="black", s=80, zorder=10, depthshade=False)
    ax.text(ox_utm, oy_utm, 0.5, "출발지", fontsize=8, color="black",
            ha="center", va="bottom")

    # 체육센터 수직선 (바닥 ~ 꼭대기)
    if gym_utm_x is not None:
        ax.plot([gym_utm_x, gym_utm_x], [gym_utm_y, gym_utm_y], [0, 30],
                color="green", linewidth=2, linestyle="--",
                alpha=0.8, label="체육센터 위치")
        ax.scatter([gym_utm_x], [gym_utm_y], [0],
                   color="green", marker="^", s=100, zorder=10, depthshade=False)

    ax.set_xlabel("서-동 (m)", fontsize=9, labelpad=8)
    ax.set_ylabel("남-북 (m)", fontsize=9, labelpad=8)
    ax.set_zlabel("시간 (분)", fontsize=9, labelpad=8)
    ax.set_zlim(0, 32)
    ax.set_zticks(TIME_STEPS_MIN)
    ax.tick_params(axis='both', labelsize=7)
    ax.view_init(elev=28, azim=-55)
    ax.set_title(district_titles[district], fontsize=12, fontweight="bold", pad=12)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.85)

plt.suptitle(
    "Space-Time Prism 3D 비교: Classic PPA vs Thermal-Inclusive PPA\n"
    "파랑=Classic(열환경 미적용)  |  빨강=Thermal(폭염 피크, UTCI>38°C)  |  Z축=시간예산(분)",
    fontsize=13, fontweight="bold", y=1.01
)
plt.tight_layout()
out = os.path.join(OUT_DIR, "stp_3d_prism.png")
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out}")
print("완료.")
