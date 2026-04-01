"""
Thermal-Inclusive PPA 분석 — v3 (ASOS 풍속·일사량 실측 기반)
=============================================================
버전 히스토리:
  v1_sim  (2026-03-18): 링크 유형 기반 시나리오 하드코딩
  v2_sdot (2026-04-01): S-DoT 실측 UTCI, 풍속 1.5m/s 가정, MRT=UV 기반
  v3_asos (2026-04-01): v2 + 풍속 ASOS 실측 + MRT=일사량 기반 (현재)

변경점 (v2 → v3):
  - UTCI 입력: link_utci_by_hour_v3.csv (ASOS 풍속·일사량 반영)
  - 주간(09~17시) UTCI +1.5~2.0°C 상승 → 속도계수 추가 하락 예상
  - 그 외 분석 로직 동일
"""

import os, json
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

BASE         = os.path.dirname(os.path.abspath(__file__))
NET_PATH     = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
LINK_UTCI    = os.path.join(BASE, 'link_utci_by_hour_v3.csv')
OUT_DIR      = BASE
FIG_DIR      = os.path.join(BASE, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

VERSION      = 'v3_asos'
WALK_SPEED   = 4.5 * 1000 / 3600
TIME_BUDGET  = 30 * 60
EUNGBONG_LAT, EUNGBONG_LON = 37.5428, 127.0357

TARGET_HOURS = {
    7:  {'label': '07시 (이른 아침)', 'color': '#2196F3'},
    10: {'label': '10시 (오전 더위)',  'color': '#FF9800'},
    13: {'label': '13시 (폭염 피크)',  'color': '#F44336'},
}

# ── 1. 링크별 속도계수 로드 ──────────────────────────────────────────
print('링크 UTCI v3 데이터 로드...')
link_df = pd.read_csv(LINK_UTCI, encoding='utf-8-sig')
link_df['u'] = link_df['u'].astype(str)
link_df['v'] = link_df['v'].astype(str)

speed_lookup = {}
for _, row in link_df.iterrows():
    speed_lookup[(row['u'], row['v'], int(row['hour']))] = row['speed_factor']
    speed_lookup[(row['v'], row['u'], int(row['hour']))] = row['speed_factor']

print(f'  링크-시간대 조합: {len(speed_lookup):,}개 로드 완료')

# ── 2. 네트워크 로드 ─────────────────────────────────────────────────
print('네트워크 로드...')
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()
origin_node = ox.distance.nearest_nodes(G_base, EUNGBONG_LON, EUNGBONG_LAT)
print(f'  노드: {G_base.number_of_nodes():,} / 엣지: {G_base.number_of_edges():,}')
print(f'  출발 노드: {origin_node}')

# ── 3. 시간대별 Thermal PPA 계산 ────────────────────────────────────
results = {}

for hour, meta in TARGET_HOURS.items():
    print(f"\n[{meta['label']}] 계산 중...")
    G = G_base.copy()
    matched, fallback = 0, 0

    for u, v, k, data in G.edges(keys=True, data=True):
        length = float(data.get('length', 0))
        u_str, v_str = str(u), str(v)

        if (u_str, v_str, hour) in speed_lookup:
            factor = speed_lookup[(u_str, v_str, hour)]
            matched += 1
        else:
            factor = 0.75
            fallback += 1

        if factor <= 0.05:
            data['travel_time'] = float('inf')
        else:
            data['travel_time'] = length / (WALK_SPEED * factor)

    print(f'  매칭: {matched:,}개 / 폴백: {fallback:,}개')

    lengths = nx.single_source_dijkstra_path_length(
        G, origin_node, cutoff=TIME_BUDGET, weight='travel_time'
    )
    reachable = set(lengths.keys())
    pct = round(len(reachable) / G.number_of_nodes() * 100, 1)
    print(f'  도달 가능 노드: {len(reachable):,}개 ({pct}%)')

    results[hour] = {
        'hour': hour,
        'label': meta['label'],
        'color': meta['color'],
        'reachable': reachable,
        'reachable_count': len(reachable),
        'reachable_pct': pct,
    }

# ── 4. Classic PPA + v2 비교 로드 ────────────────────────────────────
with open(os.path.join(OUT_DIR, 'classic_ppa_summary.json'), encoding='utf-8') as f:
    classic = json.load(f)
with open(os.path.join(OUT_DIR, 'thermal_ppa_v2_sdot_summary.json'), encoding='utf-8') as f:
    v2_summary = json.load(f)

# ── 5. 시각화 ───────────────────────────────────────────────────────
print('\n시각화 생성 중...')
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

fig, axes = plt.subplots(1, 3, figsize=(21, 9))

for ax, (hour, res) in zip(axes, results.items()):
    reachable = res['reachable']
    edges_gdf['reachable'] = edges_gdf.index.map(
        lambda idx: idx[0] in reachable and idx[1] in reachable
    )

    edges_gdf[~edges_gdf['reachable']].plot(ax=ax, color='#e0e0e0', linewidth=0.4, alpha=0.7)
    edges_gdf[edges_gdf['reachable']].plot(ax=ax, color=res['color'], linewidth=1.0, alpha=0.85)

    if 'bridge' in edges_gdf.columns:
        bridge_e = edges_gdf[edges_gdf['bridge'] == 'yes']
        if len(bridge_e) > 0:
            bridge_e[bridge_e['reachable']].plot(ax=ax, color='lime', linewidth=3, zorder=5)
            bridge_e[~bridge_e['reachable']].plot(ax=ax, color='black', linewidth=3, linestyle='--', zorder=5)

    origin_geom = nodes_gdf.loc[origin_node].geometry
    ax.plot(origin_geom.x, origin_geom.y, 'r*', markersize=14, zorder=6)

    decline_classic = round((classic['reachable_nodes'] - res['reachable_count']) / classic['reachable_nodes'] * 100, 1)

    # v2 비교
    v2_key = f"h{hour:02d}_{res['label'].split('(')[0].strip()}"
    v2_nodes = v2_summary.get(v2_key, {}).get('reachable_nodes', None)
    v2_diff_str = ''
    if v2_nodes:
        diff = res['reachable_count'] - v2_nodes
        sign = '+' if diff >= 0 else ''
        v2_diff_str = f' | v2 대비 {sign}{diff}노드'

    ax.set_title(
        f"{res['label']}\n"
        f"도달 가능: {res['reachable_count']:,}개 ({res['reachable_pct']}%) | Classic 대비 -{decline_classic}%{v2_diff_str}",
        fontsize=9
    )
    ax.set_axis_off()

plt.suptitle(
    f'Thermal PPA {VERSION} — ASOS 풍속·일사량 실측 기반\n'
    '출발지: 응봉역 | 시간예산: 30분 | MRT=일사량 보정, 풍속=ASOS 실측',
    fontsize=13, fontweight='bold'
)
plt.tight_layout()

fig_path = os.path.join(FIG_DIR, f'thermal_ppa_{VERSION}_scenarios.png')
plt.savefig(fig_path, dpi=150, bbox_inches='tight')
plt.close()
print(f'저장: {fig_path}')

# ── 6. 결과 저장 ────────────────────────────────────────────────────
summary = {
    '_version': VERSION,
    '_date': '2026-04-01',
    '_data_source': 'S-DoT + ASOS 2025.07.28-08.03, IDW 보간',
    '_improvements_over_v2': 'MRT=일사량 기반(UV→solar), 풍속=ASOS 실측(1.5m/s 가정 제거)',
    'classic_ppa_nodes': classic['reachable_nodes'],
    'classic_ppa_pct': classic['reachable_pct'],
}

print(f'\n=== PPA 결과 요약 ({VERSION}) ===')
print(f"Classic PPA: {classic['reachable_nodes']:,}노드 ({classic['reachable_pct']}%)")

for hour, res in results.items():
    key = f"h{hour:02d}_{res['label'].split('(')[0].strip()}"
    decline = round((classic['reachable_nodes'] - res['reachable_count']) / classic['reachable_nodes'] * 100, 1)

    v2_key = key
    v2_nodes = v2_summary.get(v2_key, {}).get('reachable_nodes', None)
    v2_decline = v2_summary.get(v2_key, {}).get('decline_from_classic_pct', None)

    summary[key] = {
        'hour': hour,
        'reachable_nodes': res['reachable_count'],
        'reachable_pct': res['reachable_pct'],
        'decline_from_classic_pct': decline,
        'v2_reachable_nodes': v2_nodes,
        'v2_decline_pct': v2_decline,
        'delta_vs_v2_nodes': (res['reachable_count'] - v2_nodes) if v2_nodes else None,
    }

    v2_str = f" | v2: {v2_nodes:,}노드(-{v2_decline}%)" if v2_nodes else ''
    print(f"  {res['label']}: {res['reachable_count']:,}노드 ({res['reachable_pct']}%) → -{decline}%{v2_str}")

out_json = os.path.join(OUT_DIR, f'thermal_ppa_{VERSION}_summary.json')
with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f'\n결과 저장: {out_json}')
