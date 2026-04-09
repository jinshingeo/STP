"""
Thermal Catchment 분석 — 응봉역 / 성수역 도보 접근 가능 주민 범위
==================================================================
연구 질문: 폭염 시 도보로 역에 갈 수 없게 되는 주민은 어디에 사는가?

방법:
  1. 역에서 역방향 다익스트라 (한 번만 실행, 효율적)
  2. Classic catchment: travel_time ≤ 30분인 모든 노드
  3. Thermal catchment: effective_cost = travel_time × (1 + α × penalty(UTCI)) ≤ 30분
  4. 차이 = 폭염으로 도보 접근성을 잃는 주민 범위

Thermal Score 정의 (UTCI 국제 카테고리 기준):
  UTCI < 26°C  → penalty 0 (쾌적)
  26~32°C      → penalty 1 (약한 열스트레스)
  32~38°C      → penalty 2 (강한 열스트레스)
  38~46°C      → penalty 3 (매우 강한 열스트레스)
  > 46°C       → penalty 4 (극한)

effective_cost(link) = base_time × (1 + α × penalty)
  α = 0.3 (기본값, 민감도 분석 가능)
"""

import os
import json
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib
import contextily as ctx
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── 경로 설정 ──────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
NET_PATH  = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
UTCI_PATH = os.path.join(BASE, 'link_utci_by_hour_v3.csv')
FIG_DIR   = os.path.join(BASE, 'figures')
OUT_DIR   = BASE
os.makedirs(FIG_DIR, exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────────────
WALK_SPEED   = 4.5 * 1000 / 3600   # m/s
TIME_BUDGET  = 30 * 60             # 초 (30분)
ALPHA        = 0.15                # 열 패널티 가중치 (민감도 분석 가능)

TARGET_HOURS = [7, 10, 13, 16]

STATIONS = {
    '응봉역': {'lat': 37.5435, 'lon': 127.0361, 'color': '#E53935'},  # 정밀 좌표
    '성수역': {'lat': 37.5447, 'lon': 127.0561, 'color': '#1E88E5'},
}


def utci_to_penalty(utci: float) -> int:
    """UTCI → 열 불쾌 패널티 (0~4)"""
    if utci < 26:   return 0
    elif utci < 32: return 1
    elif utci < 38: return 2
    elif utci < 46: return 3
    else:           return 4


def compute_catchment(G: nx.Graph, station_node: int, utci_lookup: dict,
                      hour: int, alpha: float):
    """
    Classic / Thermal catchment 계산
    역방향 다익스트라: 역 → 모든 주거 노드 (한 번만 실행)
    undirected 그래프이므로 reverse = 동일
    """
    # Classic: 순수 이동시간
    for u, v, data in G.edges(data=True):
        data['classic_time'] = data.get('length', 0) / WALK_SPEED

    classic_dist = nx.single_source_dijkstra_path_length(
        G, station_node, cutoff=TIME_BUDGET, weight='classic_time'
    )

    # Thermal: effective_cost = base_time × (1 + α × penalty)
    for u, v, data in G.edges(data=True):
        base_time = data.get('length', 0) / WALK_SPEED
        utci = utci_lookup.get((str(u), str(v), hour),
               utci_lookup.get((str(v), str(u), hour), 35.0))
        penalty = utci_to_penalty(utci)
        data['thermal_time'] = base_time * (1 + alpha * penalty)

    thermal_dist = nx.single_source_dijkstra_path_length(
        G, station_node, cutoff=TIME_BUDGET, weight='thermal_time'
    )

    classic_nodes = set(classic_dist.keys())
    thermal_nodes = set(thermal_dist.keys())
    lost_nodes    = classic_nodes - thermal_nodes   # 폭염으로 접근성 상실한 노드

    return {
        'classic_nodes': classic_nodes,
        'thermal_nodes': thermal_nodes,
        'lost_nodes':    lost_nodes,
        'classic_count': len(classic_nodes),
        'thermal_count': len(thermal_nodes),
        'lost_count':    len(lost_nodes),
        'reduction_pct': round(len(lost_nodes) / len(classic_nodes) * 100, 1),
    }


def plot_catchment_map(ax, nodes_wm, edges_wm, result, station_node,
                       station_name, hour, alpha, add_basemap=True):
    """Catchment 지도 그리기 (Web Mercator + 베이스맵)"""
    classic = result['classic_nodes']
    thermal = result['thermal_nodes']

    # 엣지 분류 및 색상
    def etype(idx):
        u, v = idx[0], idx[1]
        if u in thermal and v in thermal: return 'thermal'
        if u in classic  and v in classic: return 'lost'
        return 'outside'

    e = edges_wm.copy()
    e['etype'] = e.index.map(etype)

    e[e['etype'] == 'outside'].plot(
        ax=ax, color='#bbbbbb', linewidth=0.3, alpha=0.4, zorder=1)
    e[e['etype'] == 'lost'].plot(
        ax=ax, color='#EF9A9A', linewidth=1.0, alpha=0.85, zorder=2)
    e[e['etype'] == 'thermal'].plot(
        ax=ax, color='#2E7D32', linewidth=1.2, alpha=0.9, zorder=3)

    # 역 마커
    sg = nodes_wm.loc[station_node].geometry
    ax.plot(sg.x, sg.y, '*', color='#FFD600', markersize=16, zorder=8,
            markeredgecolor='black', markeredgewidth=0.6)

    # 베이스맵
    if add_basemap:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik,
                        zoom=14, alpha=0.5)

    ax.set_title(
        f"{station_name} | {hour:02d}시\n"
        f"접근 가능(초록): {result['thermal_count']:,}  "
        f"상실(빨강): {result['lost_count']:,} ({result['reduction_pct']}%)",
        fontsize=9
    )
    ax.set_axis_off()


# ── 메인 ──────────────────────────────────────────────────────────────
print("네트워크 로드 중...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

# Web Mercator 변환 (contextily 베이스맵용)
nodes_wm = nodes_gdf.to_crs(epsg=3857)
edges_wm = edges_gdf.to_crs(epsg=3857)

print("UTCI 데이터 로드 중...")
link_df = pd.read_csv(UTCI_PATH, encoding='utf-8-sig')
utci_lookup = {}
for _, row in link_df.iterrows():
    utci_lookup[(str(row['u']), str(row['v']), int(row['hour']))] = row['utci_idw']
    utci_lookup[(str(row['v']), str(row['u']), int(row['hour']))] = row['utci_idw']
print(f"  {len(utci_lookup):,}개 로드 완료")

# 역 노드 탐색
for name, info in STATIONS.items():
    info['node'] = ox.distance.nearest_nodes(G_base, info['lon'], info['lat'])
    print(f"  {name}: 노드 {info['node']}")

# ── 분석 실행 ──────────────────────────────────────────────────────────
all_results = {}
for station_name, sinfo in STATIONS.items():
    all_results[station_name] = {}
    for hour in TARGET_HOURS:
        print(f"  [{station_name}] {hour:02d}시 catchment 계산 중...")
        G = G_base.copy()
        result = compute_catchment(G, sinfo['node'], utci_lookup, hour, ALPHA)
        all_results[station_name][hour] = result
        print(f"    Classic: {result['classic_count']:,} / "
              f"Thermal: {result['thermal_count']:,} / "
              f"상실: {result['lost_count']:,} (-{result['reduction_pct']}%)")

# ── 시각화 1: 시간대별 Catchment 지도 (각 역별) ───────────────────────
for station_name, sinfo in STATIONS.items():
    print(f"\n{station_name} catchment 지도 생성 중...")
    fig, axes = plt.subplots(1, len(TARGET_HOURS), figsize=(22, 8))

    for ax, hour in zip(axes, TARGET_HOURS):
        G = G_base.copy()
        result = all_results[station_name][hour]
        plot_catchment_map(ax, nodes_wm, edges_wm, result,
                           sinfo['node'], station_name, hour, ALPHA)

    # 범례
    handles = [
        mpatches.Patch(color='#43A047', label=f'폭염에도 접근 가능 (Thermal catchment)'),
        mpatches.Patch(color='#E53935', label=f'접근성 상실 (Classic에는 있었으나 Thermal에서 제외)'),
        plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='#FFD600',
                   markersize=12, markeredgecolor='black', label=f'{station_name}'),
    ]
    fig.legend(handles=handles, loc='lower center', ncol=3, fontsize=9,
               bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(
        f"{station_name} 도보 접근성 — Thermal Catchment 분석\n"
        f"UTCI 기반 열 패널티 적용 (α={ALPHA}) | 시간예산: 30분",
        fontsize=13, fontweight='bold'
    )
    plt.tight_layout()
    fname = f'catchment_{station_name.replace("역","")}.png'
    fig.savefig(os.path.join(FIG_DIR, fname), dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  저장: figures/{fname}")

# ── 시각화 2: 두 역 13시 비교 지도 ────────────────────────────────────
print("\n응봉역 vs 성수역 13시 비교 지도 생성 중...")
fig, axes = plt.subplots(1, 2, figsize=(18, 9))

for ax, (station_name, sinfo) in zip(axes, STATIONS.items()):
    G = G_base.copy()
    result = all_results[station_name][13]
    plot_catchment_map(ax, nodes_gdf, edges_gdf, result,
                       sinfo['node'], station_name, 13, ALPHA)

handles = [
    mpatches.Patch(color='#43A047', label='폭염에도 접근 가능'),
    mpatches.Patch(color='#E53935', label='폭염으로 접근성 상실'),
]
fig.legend(handles=handles, loc='lower center', ncol=2, fontsize=10,
           bbox_to_anchor=(0.5, -0.02))

fig.suptitle(
    "응봉역 vs 성수역 — 폭염(13시) 시 도보 Catchment 비교\n"
    "열취약(응봉) vs 열완충(성수/서울숲 인접) | UTCI 기반 패널티",
    fontsize=13, fontweight='bold'
)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'catchment_comparison_13h.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  저장: figures/catchment_comparison_13h.png")

# ── 시각화 3: 감소율 시계열 그래프 ─────────────────────────────────────
print("\n감소율 시계열 그래프 생성 중...")
fig, ax = plt.subplots(figsize=(9, 5))

for station_name, sinfo in STATIONS.items():
    hours  = TARGET_HOURS
    losses = [all_results[station_name][h]['reduction_pct'] for h in hours]
    ax.plot(hours, losses, 'o-', label=station_name,
            color=sinfo['color'], linewidth=2, markersize=8)

ax.axhline(0, color='gray', linewidth=0.8, linestyle='--')
ax.set_xlabel('시각 (시)', fontsize=11)
ax.set_ylabel('접근성 상실 노드 비율 (%)', fontsize=11)
ax.set_title(
    f'시간대별 도보 Catchment 감소율\n(Classic 대비 Thermal, α={ALPHA})',
    fontsize=12, fontweight='bold'
)
ax.legend(fontsize=10)
ax.set_xticks(TARGET_HOURS)
ax.set_xticklabels([f'{h}시' for h in TARGET_HOURS])
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(os.path.join(FIG_DIR, 'catchment_reduction_timeseries.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  저장: figures/catchment_reduction_timeseries.png")

# ── 결과 저장 ──────────────────────────────────────────────────────────
summary = {'alpha': ALPHA, 'time_budget_min': 30, 'walk_speed_kmh': 4.5}
for station_name in STATIONS:
    summary[station_name] = {}
    for hour in TARGET_HOURS:
        r = all_results[station_name][hour]
        summary[station_name][f'h{hour:02d}'] = {
            'classic_nodes': r['classic_count'],
            'thermal_nodes': r['thermal_count'],
            'lost_nodes':    r['lost_count'],
            'reduction_pct': r['reduction_pct'],
        }

out_json = os.path.join(OUT_DIR, 'thermal_catchment_summary.json')
with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"\n결과 저장: {out_json}")

# ── 콘솔 요약 ──────────────────────────────────────────────────────────
print("\n=== 최종 결과 요약 ===")
print(f"{'역':<8} {'시각':<6} {'Classic':>10} {'Thermal':>10} {'상실':>8} {'감소율':>8}")
print("-" * 55)
for station_name in STATIONS:
    for hour in TARGET_HOURS:
        r = all_results[station_name][hour]
        print(f"{station_name:<8} {hour:02d}시    "
              f"{r['classic_count']:>8,}   "
              f"{r['thermal_count']:>8,}   "
              f"{r['lost_count']:>6,}   "
              f"-{r['reduction_pct']:>5.1f}%")
