"""
STP(Space-Time Prism) 3D 구현 — Classic vs Thermal 비교
=========================================================
Miller(1991) 기반 네트워크 STP 구현

개념:
  - 출발지(집) → 도착지(응봉역), 시간예산 T=30분
  - 시각 t에서 프리즘 slice = forward_reach(t) ∩ backward_reach(T-t)
  - 모든 slice를 z축(시간)으로 쌓으면 → 3D 프리즘
  - PPA = 프리즘의 x-y 평면 투영 (바닥 그림자)

Thermal 버전:
  - 링크 비용 = travel_time + α × penalty(UTCI)
  - 쾌적 링크는 비용 그대로, 폭염 링크는 비용 증가 → 회피
  - 프리즘이 열노출 방향으로 찌그러짐
"""

import os
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib
from mpl_toolkits.mplot3d import Axes3D
from pyproj import Transformer

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── 경로 설정 ──────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
NET_PATH  = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
UTCI_PATH = os.path.join(BASE, 'link_utci_by_hour_v3.csv')
FIG_DIR   = os.path.join(BASE, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────────────
WALK_SPEED    = 4.5 * 1000 / 3600   # m/s
TIME_BUDGET   = 30 * 60             # 초 (30분)
TIME_STEPS    = list(range(0, 31, 1))  # 0~30분 1분 단위 슬라이스
ALPHA         = 0.15                # 열 패널티 가중치 (민감도 분석 가능)
TARGET_HOUR   = 13                  # 폭염 피크

# 좌표계 변환 (WGS84 → UTM-K, 단위: 미터)
transformer = Transformer.from_crs("epsg:4326", "epsg:5186", always_xy=True)

# Origin: 응봉동 대표 주거지 (응봉역에서 약 12분 도보 거리, 북쪽)
ORIGIN_LAT, ORIGIN_LON   = 37.5511, 127.0353
# Destination: 응봉역
DEST_LAT, DEST_LON       = 37.5428, 127.0357


def utci_to_penalty(utci: float) -> int:
    """UTCI 값을 열 불쾌 패널티로 변환 (국제 UTCI 카테고리 기준)"""
    if utci < 26:   return 0   # 쾌적
    elif utci < 32: return 1   # 약한 열스트레스
    elif utci < 38: return 2   # 강한 열스트레스
    elif utci < 46: return 3   # 매우 강한 열스트레스
    else:           return 4   # 극한 열스트레스


def build_classic_graph(G_base: nx.Graph) -> nx.Graph:
    """Classic 그래프: travel_time = 거리 / 보행속도"""
    G = G_base.copy()
    for u, v, data in G.edges(data=True):
        data['travel_time'] = data.get('length', 0) / WALK_SPEED
    return G


def build_thermal_graph(G_base: nx.Graph, utci_lookup: dict, hour: int) -> nx.Graph:
    """Thermal 그래프: travel_time += α × penalty(UTCI) × base_time"""
    G = G_base.copy()
    for u, v, data in G.edges(data=True):
        length = data.get('length', 0)
        base_time = length / WALK_SPEED
        utci = utci_lookup.get((str(u), str(v), hour),
               utci_lookup.get((str(v), str(u), hour), 35.0))
        penalty = utci_to_penalty(utci)
        data['travel_time'] = base_time * (1 + ALPHA * penalty)
    return G


def compute_stp_slices(G: nx.Graph, origin: int, dest: int) -> dict:
    """
    각 시간 슬라이스에서의 STP 노드 집합 반환
    forward_dist[n] + backward_dist[n] <= T 인 노드가 프리즘에 포함
    """
    forward_dist  = nx.single_source_dijkstra_path_length(
        G, origin, cutoff=TIME_BUDGET, weight='travel_time')
    backward_dist = nx.single_source_dijkstra_path_length(
        G, dest, cutoff=TIME_BUDGET, weight='travel_time')

    slices = {}
    for t_min in TIME_STEPS:
        t_sec = t_min * 60
        remaining = TIME_BUDGET - t_sec
        in_slice = [
            n for n in forward_dist
            if n in backward_dist
            and forward_dist[n] <= t_sec
            and backward_dist[n] <= remaining
        ]
        slices[t_min] = in_slice

    return slices, forward_dist, backward_dist


def node_to_meters(G: nx.Graph, node: int):
    """노드 좌표를 미터 단위로 변환"""
    d = G.nodes[node]
    x_m, y_m = transformer.transform(d['x'], d['y'])
    return x_m, y_m


def plot_stp_3d(ax, G, slices, origin, dest, title, color_map='viridis'):
    """3D STP 프리즘 그리기"""
    ox_m, oy_m = node_to_meters(G, origin)
    dx_m, dy_m = node_to_meters(G, dest)

    # 좌표 중심 이동 (상대 좌표)
    cx = (ox_m + dx_m) / 2
    cy = (oy_m + dy_m) / 2

    cmap = plt.get_cmap(color_map)
    t_max = max(TIME_STEPS)

    for t_min, nodes in slices.items():
        if not nodes:
            continue
        xs = []
        ys = []
        for n in nodes:
            xm, ym = node_to_meters(G, n)
            xs.append((xm - cx) / 1000)   # km 단위
            ys.append((ym - cy) / 1000)
        color = cmap(t_min / t_max)
        ax.scatter(xs, ys, zs=t_min, zdir='z',
                   s=4, c=[color], alpha=0.5)

    # Origin, Destination 표시
    ax.scatter([(ox_m - cx) / 1000], [(oy_m - cy) / 1000], zs=0,
               s=120, c='blue', marker='^', zorder=5, label='출발지 (주거)')
    ax.scatter([(dx_m - cx) / 1000], [(dy_m - cy) / 1000], zs=TIME_BUDGET / 60,
               s=120, c='red', marker='*', zorder=5, label='도착지 (응봉역)')

    ax.set_xlabel('X (km)', fontsize=8)
    ax.set_ylabel('Y (km)', fontsize=8)
    ax.set_zlabel('시간 (분)', fontsize=8)
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.legend(fontsize=7, loc='upper left')


def plot_ppa_2d(ax, G, slices, origin, dest, title, color):
    """PPA 2D 투영 (프리즘 바닥 그림자)"""
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)

    # 프리즘에 포함된 모든 노드 (시간 무관 합집합)
    ppa_nodes = set()
    for nodes in slices.values():
        ppa_nodes.update(nodes)

    edges_gdf['in_ppa'] = edges_gdf.index.map(
        lambda idx: idx[0] in ppa_nodes and idx[1] in ppa_nodes
    )

    edges_gdf[~edges_gdf['in_ppa']].plot(
        ax=ax, color='#e0e0e0', linewidth=0.4, alpha=0.6)
    if edges_gdf['in_ppa'].any():
        edges_gdf[edges_gdf['in_ppa']].plot(
            ax=ax, color=color, linewidth=1.0, alpha=0.85)

    origin_geom = nodes_gdf.loc[origin].geometry
    dest_geom   = nodes_gdf.loc[dest].geometry
    ax.plot(origin_geom.x, origin_geom.y, '^', color='blue',
            markersize=10, zorder=5, label='출발지 (주거)')
    ax.plot(dest_geom.x, dest_geom.y, '*', color='red',
            markersize=12, zorder=5, label='도착지 (응봉역)')
    ax.set_title(
        f"{title}\nPPA 노드: {len(ppa_nodes):,}개", fontsize=9)
    ax.legend(fontsize=7)
    ax.set_axis_off()


# ── 메인 ──────────────────────────────────────────────────────────────
print("네트워크 로드 중...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()

origin_node = ox.distance.nearest_nodes(G_base, ORIGIN_LON, ORIGIN_LAT)
dest_node   = ox.distance.nearest_nodes(G_base, DEST_LON, DEST_LAT)
print(f"  출발 노드: {origin_node} (응봉동 주거지)")
print(f"  도착 노드: {dest_node} (응봉역)")

# UTCI 데이터 로드
print("UTCI 데이터 로드 중...")
link_df = pd.read_csv(UTCI_PATH, encoding='utf-8-sig')
utci_lookup = {}
for _, row in link_df.iterrows():
    # str 키로 통일 (그래프 노드 ID와 타입 일치시키기 위해)
    utci_lookup[(str(row['u']), str(row['v']), int(row['hour']))] = row['utci_idw']
    utci_lookup[(str(row['v']), str(row['u']), int(row['hour']))] = row['utci_idw']
print(f"  로드 완료: {len(utci_lookup):,}개 (링크×시간대)")

# 그래프 구성
print(f"그래프 구성 중 (Classic / Thermal {TARGET_HOUR:02d}시)...")
G_classic = build_classic_graph(G_base)
G_thermal = build_thermal_graph(G_base, utci_lookup, TARGET_HOUR)

# STP 슬라이스 계산
print("STP 슬라이스 계산 중...")
classic_slices, cf_dist, cb_dist = compute_stp_slices(G_classic, origin_node, dest_node)
thermal_slices, tf_dist, tb_dist = compute_stp_slices(G_thermal, origin_node, dest_node)

# PPA = forward[n] + backward[n] <= T (정확한 조건)
classic_ppa = {n for n in cf_dist if n in cb_dist
               and cf_dist[n] + cb_dist[n] <= TIME_BUDGET}
thermal_ppa = {n for n in tf_dist if n in tb_dist
               and tf_dist[n] + tb_dist[n] <= TIME_BUDGET}
reduction   = round((len(classic_ppa) - len(thermal_ppa)) / max(len(classic_ppa), 1) * 100, 1)
print(f"  Classic PPA: {len(classic_ppa):,}노드")
print(f"  Thermal PPA ({TARGET_HOUR}시): {len(thermal_ppa):,}노드 (감소율: -{reduction}%)")

# ── 시각화: 3D 프리즘 ───────────────────────────────────────────────────
print("3D 프리즘 시각화 생성 중...")
fig = plt.figure(figsize=(18, 8))

ax1 = fig.add_subplot(121, projection='3d')
ax2 = fig.add_subplot(122, projection='3d')

plot_stp_3d(ax1, G_classic, classic_slices, origin_node, dest_node,
            f"Classic STP\n(열환경 제약 없음)", color_map='Blues')

plot_stp_3d(ax2, G_thermal, thermal_slices, origin_node, dest_node,
            f"Thermal STP (UTCI 기반, {TARGET_HOUR}시)\n"
            f"α={ALPHA}, 패널티 적용", color_map='Reds')

fig.suptitle(
    "Space-Time Prism — Classic vs Thermal\n"
    f"출발: 응봉동 주거지 → 도착: 응봉역 | 시간예산: 30분 | 분석 시각: {TARGET_HOUR}시",
    fontsize=13, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'stp_prism_3d.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  저장: figures/stp_prism_3d.png")

# ── 시각화: 슬라이스별 변화 (타임랩스) ──────────────────────────────────
print("슬라이스별 타임랩스 생성 중...")
key_times = [0, 10, 15, 20, 30]
fig, axes = plt.subplots(2, len(key_times), figsize=(22, 10))

nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

for col, t_min in enumerate(key_times):
    t_sec = t_min * 60
    remaining = TIME_BUDGET - t_sec
    c_nodes = {n for n in cf_dist if n in cb_dist
               and cf_dist[n] <= t_sec and cb_dist[n] <= remaining}
    t_nodes = {n for n in tf_dist if n in tb_dist
               and tf_dist[n] <= t_sec and tb_dist[n] <= remaining}

    for row, (nodes_set, color, label) in enumerate([
        (c_nodes, '#2196F3', 'Classic'),
        (t_nodes, '#F44336', 'Thermal'),
    ]):
        ax = axes[row, col]
        mask = edges_gdf.index.map(
            lambda idx: idx[0] in nodes_set and idx[1] in nodes_set
        ).fillna(False)
        edges_gdf[~mask].plot(ax=ax, color='#eeeeee', linewidth=0.3)
        if mask.any():
            edges_gdf[mask].plot(ax=ax, color=color, linewidth=0.8, alpha=0.9)

        origin_geom = nodes_gdf.loc[origin_node].geometry
        dest_geom   = nodes_gdf.loc[dest_node].geometry
        ax.plot(origin_geom.x, origin_geom.y, '^b', markersize=7, zorder=5)
        ax.plot(dest_geom.x, dest_geom.y, '*r', markersize=9, zorder=5)

        remaining = TIME_BUDGET // 60 - t_min
        ax.set_title(
            f"{label} | t={t_min}분\n"
            f"프리즘 노드: {len(nodes_set):,}개\n잔여: {remaining}분",
            fontsize=8
        )
        ax.set_axis_off()

fig.suptitle(
    f"STP 시간 슬라이스 — 시각 t별 이동 가능 공간\n"
    f"(위: Classic / 아래: Thermal {TARGET_HOUR}시 | α={ALPHA})",
    fontsize=12, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'stp_slices_timelapse.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  저장: figures/stp_slices_timelapse.png")

# ── 시각화: PPA 2D 비교 ────────────────────────────────────────────────
print("PPA 2D 비교 지도 생성 중...")
fig, axes = plt.subplots(1, 2, figsize=(16, 9))

plot_ppa_2d(axes[0], G_classic, classic_slices, origin_node, dest_node,
            "Classic PPA (열환경 제약 없음)", '#2196F3')
plot_ppa_2d(axes[1], G_thermal, thermal_slices, origin_node, dest_node,
            f"Thermal PPA ({TARGET_HOUR}시, UTCI 기반)\n"
            f"Classic 대비 -{reduction}%", '#F44336')

fig.suptitle(
    "STP의 2D 투영 — PPA 비교\n"
    f"출발: 응봉동 주거지 → 도착: 응봉역 | 시간예산: 30분",
    fontsize=13, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'stp_ppa_2d_comparison.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  저장: figures/stp_ppa_2d_comparison.png")

print("\n=== 완료 ===")
print(f"Classic PPA:  {len(classic_ppa):,}노드")
print(f"Thermal PPA:  {len(thermal_ppa):,}노드  (α={ALPHA}, {TARGET_HOUR}시)")
print(f"감소율:       -{reduction}%")
