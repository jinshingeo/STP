"""
STP(Space-Time Prism) 3D 구현 v2 — 개선된 시각화 + 베이스맵
=============================================================
개선 사항:
  - 3D 프리즘: convex hull 슬라이스 + Poly3DCollection → 모래시계 형태 명확
  - 2D PPA 비교: contextily 베이스맵 (OpenStreetMap) 추가
  - 응봉역 좌표 정밀화
"""

import os
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import ConvexHull
from pyproj import Transformer
import contextily as ctx

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── 경로 설정 ──────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
NET_PATH  = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
UTCI_PATH = os.path.join(BASE, 'link_utci_by_hour_v3.csv')
FIG_DIR   = os.path.join(BASE, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────────────
WALK_SPEED  = 4.5 * 1000 / 3600
TIME_BUDGET = 30 * 60
ALPHA       = 0.15
TARGET_HOUR = 13

# 좌표계 변환: WGS84 → UTM-K (미터 단위)
to_utm = Transformer.from_crs("epsg:4326", "epsg:5186", always_xy=True)
# Web Mercator (contextily 베이스맵용)
to_webm = Transformer.from_crs("epsg:4326", "epsg:3857", always_xy=True)

# Origin: 응봉동 주거지 (역에서 ~12분)
ORIGIN_LAT, ORIGIN_LON = 37.5511, 127.0353
# Destination: 응봉역 (정밀 좌표)
DEST_LAT, DEST_LON     = 37.5435, 127.0361


# ── 유틸 함수 ──────────────────────────────────────────────────────────
def utci_to_penalty(utci):
    if utci < 26:   return 0
    elif utci < 32: return 1
    elif utci < 38: return 2
    elif utci < 46: return 3
    else:           return 4


def node_xy_utm(G, node):
    d = G.nodes[node]
    return to_utm.transform(d['x'], d['y'])   # (x_m, y_m)


def node_xy_webm(G, node):
    d = G.nodes[node]
    return to_webm.transform(d['x'], d['y'])  # (x_m, y_m)


def compute_dists(G, origin, dest):
    """forward / backward dijkstra 한 번씩만 실행"""
    fd = nx.single_source_dijkstra_path_length(
        G, origin, cutoff=TIME_BUDGET, weight='travel_time')
    bd = nx.single_source_dijkstra_path_length(
        G, dest,   cutoff=TIME_BUDGET, weight='travel_time')
    return fd, bd


def ppa_nodes(fd, bd):
    return {n for n in fd if n in bd and fd[n] + bd[n] <= TIME_BUDGET}


def slice_nodes(fd, bd, t_sec):
    remaining = TIME_BUDGET - t_sec
    return {n for n in fd if n in bd
            and fd[n] <= t_sec and bd[n] <= remaining}


# ── 그래프 구성 ────────────────────────────────────────────────────────
print("네트워크 + UTCI 로드 중...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()

link_df = pd.read_csv(UTCI_PATH, encoding='utf-8-sig')
utci_lut = {}
for _, row in link_df.iterrows():
    key = (str(row['u']), str(row['v']), int(row['hour']))
    utci_lut[key] = row['utci_idw']
    utci_lut[(str(row['v']), str(row['u']), int(row['hour']))] = row['utci_idw']

origin_node = ox.distance.nearest_nodes(G_base, ORIGIN_LON, ORIGIN_LAT)
dest_node   = ox.distance.nearest_nodes(G_base, DEST_LON,   DEST_LAT)
print(f"  출발: {origin_node} ({G_base.nodes[origin_node]['y']:.4f}, {G_base.nodes[origin_node]['x']:.4f})")
print(f"  응봉역: {dest_node} ({G_base.nodes[dest_node]['y']:.4f}, {G_base.nodes[dest_node]['x']:.4f})")

# Classic 그래프
G_c = G_base.copy()
for u, v, d in G_c.edges(data=True):
    d['travel_time'] = d.get('length', 0) / WALK_SPEED

# Thermal 그래프
G_t = G_base.copy()
for u, v, d in G_t.edges(data=True):
    base = d.get('length', 0) / WALK_SPEED
    utci = utci_lut.get((str(u), str(v), TARGET_HOUR),
           utci_lut.get((str(v), str(u), TARGET_HOUR), 38.0))
    d['travel_time'] = base * (1 + ALPHA * utci_to_penalty(utci))

print("Dijkstra 계산 중...")
cf, cb = compute_dists(G_c, origin_node, dest_node)
tf, tb = compute_dists(G_t, origin_node, dest_node)

c_ppa = ppa_nodes(cf, cb)
t_ppa = ppa_nodes(tf, tb)
reduction = round((len(c_ppa) - len(t_ppa)) / len(c_ppa) * 100, 1)
print(f"  Classic PPA: {len(c_ppa):,}노드  |  Thermal PPA: {len(t_ppa):,}노드  ({-reduction}%)")


# ════════════════════════════════════════════════════════════════════════
# 시각화 1 — 3D STP 프리즘 (Convex Hull 슬라이스)
# ════════════════════════════════════════════════════════════════════════
print("\n3D 프리즘 시각화 생성 중...")

def build_prism_3d(ax, G, fd, bd, face_color, edge_color, label, n_slices=20):
    """Convex hull 기반 3D 프리즘"""

    # 중심 좌표 계산 (정규화용)
    ox_m, oy_m = node_xy_utm(G, origin_node)
    dx_m, dy_m = node_xy_utm(G, dest_node)
    cx = (ox_m + dx_m) / 2
    cy = (oy_m + dy_m) / 2

    polys = []
    t_vals = np.linspace(0, TIME_BUDGET, n_slices)

    for t_sec in t_vals:
        t_min = t_sec / 60
        nodes = slice_nodes(fd, bd, t_sec)
        if len(nodes) < 3:
            continue

        pts = np.array([
            ((node_xy_utm(G, n)[0] - cx) / 1000,
             (node_xy_utm(G, n)[1] - cy) / 1000)
            for n in nodes
        ])

        try:
            hull = ConvexHull(pts)
            verts = pts[hull.vertices]
            # z = 시간(분)
            poly3d = [(v[0], v[1], t_min) for v in verts]
            polys.append(poly3d)
        except Exception:
            continue

    coll = Poly3DCollection(polys, alpha=0.18,
                            facecolor=face_color, edgecolor=edge_color,
                            linewidth=0.3)
    ax.add_collection3d(coll)

    # Origin / Destination 마커
    ox_n, oy_n = (ox_m - cx) / 1000, (oy_m - cy) / 1000
    dx_n, dy_n = (dx_m - cx) / 1000, (dy_m - cy) / 1000
    ax.scatter([ox_n], [oy_n], [0], s=100, c='royalblue',
               marker='^', zorder=10, depthshade=False)
    ax.scatter([dx_n], [dy_n], [30], s=150, c='crimson',
               marker='*', zorder=10, depthshade=False)

    ppa_count = len(ppa_nodes(fd, bd))
    ax.set_title(f"{label}\nPPA {ppa_count:,}노드", fontsize=10, fontweight='bold', pad=6)
    ax.set_xlabel('X (km)', fontsize=8, labelpad=4)
    ax.set_ylabel('Y (km)', fontsize=8, labelpad=4)
    ax.set_zlabel('시간 (분)', fontsize=8, labelpad=4)
    ax.set_zlim(0, 30)
    ax.view_init(elev=22, azim=-60)
    ax.tick_params(labelsize=7)


fig = plt.figure(figsize=(16, 8))
ax1 = fig.add_subplot(121, projection='3d')
ax2 = fig.add_subplot(122, projection='3d')

build_prism_3d(ax1, G_c, cf, cb, '#90CAF9', '#1565C0', 'Classic STP\n(열환경 제약 없음)')
build_prism_3d(ax2, G_t, tf, tb, '#FFCDD2', '#B71C1C',
               f'Thermal STP (UTCI 기반, {TARGET_HOUR}시)\nα={ALPHA} | -{reduction}%')

# 공통 범례
legend_elems = [
    mpatches.Patch(facecolor='#90CAF9', edgecolor='#1565C0', label='Classic 프리즘'),
    mpatches.Patch(facecolor='#FFCDD2', edgecolor='#B71C1C', label='Thermal 프리즘'),
    plt.Line2D([0],[0], marker='^', color='w', markerfacecolor='royalblue',
               markersize=9, label='출발지 (주거)'),
    plt.Line2D([0],[0], marker='*', color='w', markerfacecolor='crimson',
               markersize=11, label='도착지 (응봉역)'),
]
fig.legend(handles=legend_elems, loc='lower center', ncol=4, fontsize=9,
           bbox_to_anchor=(0.5, 0.01))

fig.suptitle(
    "Space-Time Prism — Classic vs Thermal\n"
    f"출발: 응봉동 주거지 → 응봉역 | 시간예산 30분 | 분석 시각 {TARGET_HOUR}시",
    fontsize=13, fontweight='bold'
)
plt.tight_layout(rect=[0, 0.07, 1, 0.95])
fig.savefig(os.path.join(FIG_DIR, 'stp_prism_3d_v2.png'), dpi=180, bbox_inches='tight')
plt.close()
print("  저장: figures/stp_prism_3d_v2.png")


# ════════════════════════════════════════════════════════════════════════
# 시각화 2 — 2D PPA + 베이스맵
# ════════════════════════════════════════════════════════════════════════
print("\n2D PPA 베이스맵 시각화 생성 중...")

nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

# Web Mercator 변환 (contextily 필요)
nodes_wm = nodes_gdf.to_crs(epsg=3857)
edges_wm = edges_gdf.to_crs(epsg=3857)

fig, axes = plt.subplots(1, 2, figsize=(18, 10))

for ax, (fd_, bd_, ppa_set, label, color, lw) in zip(axes, [
    (cf, cb, c_ppa, 'Classic PPA (열환경 제약 없음)', '#1565C0', 1.2),
    (tf, tb, t_ppa, f'Thermal PPA ({TARGET_HOUR}시 폭염, UTCI 기반)', '#B71C1C', 1.4),
]):
    mask_ppa  = edges_wm.index.map(lambda i: i[0] in ppa_set  and i[1] in ppa_set)
    mask_rest = ~mask_ppa

    edges_wm[mask_rest].plot(ax=ax, color='#cccccc', linewidth=0.4, alpha=0.5, zorder=1)
    if mask_ppa.any():
        edges_wm[mask_ppa].plot(ax=ax, color=color, linewidth=lw, alpha=0.9, zorder=2)

    # 역 / 출발지 마커
    dest_wm   = nodes_wm.loc[dest_node]
    origin_wm = nodes_wm.loc[origin_node]
    ax.plot(dest_wm.geometry.x,   dest_wm.geometry.y,
            '*', color='#FFD600', markersize=16, zorder=6,
            markeredgecolor='black', markeredgewidth=0.6, label='응봉역')
    ax.plot(origin_wm.geometry.x, origin_wm.geometry.y,
            '^', color='royalblue', markersize=11, zorder=6,
            markeredgecolor='white', markeredgewidth=0.6, label='출발지 (주거)')

    # 베이스맵
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik,
                    zoom=15, alpha=0.55)

    ax.set_title(
        f"{label}\nPPA 노드: {len(ppa_set):,}개"
        + (f"  |  Classic 대비 -{reduction}%" if 'Thermal' in label else ""),
        fontsize=10, fontweight='bold'
    )
    ax.legend(fontsize=9, loc='upper left')
    ax.set_axis_off()

fig.suptitle(
    "STP → PPA 2D 투영 비교\n출발: 응봉동 주거지 → 응봉역  |  시간예산 30분",
    fontsize=13, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'stp_ppa_2d_basemap.png'), dpi=180, bbox_inches='tight')
plt.close()
print("  저장: figures/stp_ppa_2d_basemap.png")


# ════════════════════════════════════════════════════════════════════════
# 시각화 3 — 타임 슬라이스 (4컷) + 베이스맵
# ════════════════════════════════════════════════════════════════════════
print("\n타임 슬라이스 시각화 생성 중...")

key_times = [10, 15, 20, 25]
fig, axes = plt.subplots(2, len(key_times), figsize=(22, 12))

for col, t_min in enumerate(key_times):
    t_sec     = t_min * 60
    remaining = TIME_BUDGET - t_sec

    c_sl = slice_nodes(cf, cb, t_sec)
    t_sl = slice_nodes(tf, tb, t_sec)

    for row, (sl, color, label) in enumerate([
        (c_sl, '#1565C0', 'Classic'),
        (t_sl, '#B71C1C', 'Thermal'),
    ]):
        ax = axes[row, col]
        mask = edges_wm.index.map(lambda i: i[0] in sl and i[1] in sl).fillna(False)

        edges_wm[~mask].plot(ax=ax, color='#dddddd', linewidth=0.3, alpha=0.6, zorder=1)
        if mask.any():
            edges_wm[mask].plot(ax=ax, color=color, linewidth=1.2, alpha=0.9, zorder=2)

        # 마커
        dest_wm   = nodes_wm.loc[dest_node]
        origin_wm = nodes_wm.loc[origin_node]
        ax.plot(dest_wm.geometry.x,   dest_wm.geometry.y,
                '*', color='#FFD600', markersize=12, zorder=6,
                markeredgecolor='black', markeredgewidth=0.5)
        ax.plot(origin_wm.geometry.x, origin_wm.geometry.y,
                '^', color='royalblue', markersize=9, zorder=6,
                markeredgecolor='white', markeredgewidth=0.5)

        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik,
                        zoom=15, alpha=0.45)

        ax.set_title(
            f"{label}  |  t = {t_min}분 경과\n"
            f"슬라이스 노드: {len(sl):,}  |  잔여: {remaining//60}분",
            fontsize=8.5
        )
        ax.set_axis_off()

fig.suptitle(
    f"STP 시간 슬라이스 — 시각 t별 이동 가능 공간\n"
    f"위: Classic  |  아래: Thermal ({TARGET_HOUR}시, α={ALPHA})",
    fontsize=12, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'stp_slices_basemap.png'), dpi=180, bbox_inches='tight')
plt.close()
print("  저장: figures/stp_slices_basemap.png")

print(f"\n=== 완료 ===")
print(f"Classic PPA: {len(c_ppa):,}노드  |  Thermal PPA: {len(t_ppa):,}노드  (-{reduction}%)")
