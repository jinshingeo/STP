"""
응봉동 vs 성수동 Thermal PPA 비교 시각화 — v3_asos
=======================================================
출력:
  figures/comparison_ppa_maps_v3.png   — 2×3 지도 (두 지역 × 3 시간대)
  figures/comparison_ppa_chart_v3.png  — PPA 감소율 비교 차트
"""

import os, json
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

BASE     = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
LINK_UTCI = os.path.join(BASE, 'link_utci_by_hour_v3.csv')
FIG_DIR  = os.path.join(BASE, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

WALK_SPEED  = 4.5 * 1000 / 3600
TIME_BUDGET = 30 * 60

TARGET_HOURS = {7: '07시\n(이른 아침)', 10: '10시\n(오전 더위)', 13: '13시\n(폭염 피크)'}

COLORS = {
    '응봉동': {'reach': '#1565C0', 'classic': '#90CAF9', 'marker': '#0D47A1'},
    '성수동': {'reach': '#2E7D32', 'classic': '#A5D6A7', 'marker': '#1B5E20'},
}

# ── 1. 데이터 로드 ───────────────────────────────────────────────────
print("데이터 로드...")
link_df = pd.read_csv(LINK_UTCI, encoding='utf-8-sig')
link_df['u'] = link_df['u'].astype(str)
link_df['v'] = link_df['v'].astype(str)
speed_lookup = {}
for _, row in link_df.iterrows():
    h = int(row['hour'])
    speed_lookup[(row['u'], row['v'], h)] = row['speed_factor']
    speed_lookup[(row['v'], row['u'], h)] = row['speed_factor']

G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)
total_nodes = G_base.number_of_nodes()

with open(os.path.join(BASE, 'representative_nodes.json')) as f:
    rep = json.load(f)
origins  = {'응봉동': rep['응봉동'], '성수동': rep['성수동']}
gym_node = rep['gym_node']

# ── 2. PPA 계산 ──────────────────────────────────────────────────────
print("PPA 계산...")
G_classic = G_base.copy()
for u, v, k, data in G_classic.edges(keys=True, data=True):
    data['travel_time'] = float(data.get('length', 0)) / WALK_SPEED

classic_reach = {}
for district, origin in origins.items():
    lengths = nx.single_source_dijkstra_path_length(
        G_classic, origin, cutoff=TIME_BUDGET, weight='travel_time')
    classic_reach[district] = set(lengths.keys())

thermal_reach = {d: {} for d in origins}
G_work = G_base.copy()

for hour in TARGET_HOURS:
    for u, v, k, data in G_work.edges(keys=True, data=True):
        length = float(data.get('length', 0))
        factor = speed_lookup.get((str(u), str(v), hour), 0.75)
        data['travel_time'] = float('inf') if factor <= 0.05 else length / (WALK_SPEED * factor)
    for district, origin in origins.items():
        lengths = nx.single_source_dijkstra_path_length(
            G_work, origin, cutoff=TIME_BUDGET, weight='travel_time')
        thermal_reach[district][hour] = set(lengths.keys())
    print(f"  {hour:02d}시 완료")

# 결과 정리
def ppa_stats(district, hour):
    c = len(classic_reach[district])
    t = len(thermal_reach[district][hour])
    return {
        'classic_n': c, 'classic_pct': round(c/total_nodes*100, 1),
        'thermal_n': t, 'thermal_pct': round(t/total_nodes*100, 1),
        'decline':   round((c - t) / c * 100, 1)
    }

stats = {d: {h: ppa_stats(d, h) for h in TARGET_HOURS} for d in origins}

# ── 3. 비교 지도 (2×3) ──────────────────────────────────────────────
print("지도 시각화...")

fig, axes = plt.subplots(2, 3, figsize=(21, 14))
fig.patch.set_facecolor('#F8F9FA')

for row, (district, origin) in enumerate(origins.items()):
    col_district = COLORS[district]
    origin_geom  = nodes_gdf.loc[origin].geometry
    gym_geom     = nodes_gdf.loc[gym_node].geometry

    for col, (hour, hour_label) in enumerate(TARGET_HOURS.items()):
        ax = axes[row][col]
        ax.set_facecolor('#F0F4F8')

        c_reach = classic_reach[district]
        t_reach = thermal_reach[district][hour]

        # 엣지 분류
        def edge_state(idx):
            u, v = idx[0], idx[1]
            in_c = (u in c_reach and v in c_reach)
            in_t = (u in t_reach and v in t_reach)
            if in_t:   return 'thermal'
            if in_c:   return 'lost'      # classic엔 있지만 thermal엔 없음
            return 'background'

        edges_gdf['state'] = edges_gdf.index.map(edge_state)

        # 배경
        edges_gdf[edges_gdf['state'] == 'background'].plot(
            ax=ax, color='#CBD5E0', linewidth=0.3, alpha=0.6)
        # Classic에선 닿지만 Thermal에선 못 가는 구간 (열로 인해 잃은 영역)
        edges_gdf[edges_gdf['state'] == 'lost'].plot(
            ax=ax, color=col_district['classic'], linewidth=0.8, alpha=0.55,
            label='열 노출로 접근 불가')
        # Thermal에서도 도달 가능
        edges_gdf[edges_gdf['state'] == 'thermal'].plot(
            ax=ax, color=col_district['reach'], linewidth=1.0, alpha=0.85,
            label='도달 가능')

        # 출발지 / 체육센터
        ax.plot(origin_geom.x, origin_geom.y, '*', color='black',
                markersize=12, zorder=10, label='출발지')
        ax.plot(gym_geom.x, gym_geom.y, '^', color='#E53935',
                markersize=9, zorder=10, label='체육센터')

        s = stats[district][hour]
        ax.set_title(
            f"{hour_label}",
            fontsize=12, fontweight='bold', pad=6
        )
        ax.text(0.02, 0.98,
                f"Thermal PPA: {s['thermal_pct']}%\nClassic 대비 -{s['decline']}%",
                transform=ax.transAxes, fontsize=9, va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85))
        ax.set_axis_off()

    # 행 레이블
    c_n   = len(classic_reach[district])
    c_pct = round(c_n / total_nodes * 100, 1)
    axes[row][0].set_ylabel(
        f"{district}\nClassic PPA {c_pct}%",
        fontsize=12, fontweight='bold',
        color=col_district['marker'], labelpad=10
    )
    axes[row][0].yaxis.set_visible(True)

# 공통 범례
legend_items = [
    mpatches.Patch(color='#1565C0', alpha=0.85, label='도달 가능 (응봉동)'),
    mpatches.Patch(color='#90CAF9', alpha=0.7,  label='열로 인해 접근 불가 (응봉동)'),
    mpatches.Patch(color='#2E7D32', alpha=0.85, label='도달 가능 (성수동)'),
    mpatches.Patch(color='#A5D6A7', alpha=0.7,  label='열로 인해 접근 불가 (성수동)'),
    plt.Line2D([0],[0], marker='*', color='black', markersize=10, lw=0, label='출발지'),
    plt.Line2D([0],[0], marker='^', color='#E53935', markersize=9, lw=0, label='성동구민종합체육센터'),
]
fig.legend(handles=legend_items, loc='lower center', ncol=6, fontsize=9,
           framealpha=0.95, bbox_to_anchor=(0.5, -0.02))

fig.suptitle(
    "Thermal PPA 비교: 응봉동(열 취약) vs 성수동(비교군) — v3_asos\n"
    "데이터: S-DoT 2025.07.28~08.03 | 시간예산 30분 | 밝은색 = 열로 인해 상실된 접근 공간",
    fontsize=13, fontweight='bold', y=1.01
)
plt.tight_layout(rect=[0, 0.04, 1, 1])
out_map = os.path.join(FIG_DIR, 'comparison_ppa_maps_v3.png')
plt.savefig(out_map, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"저장: {out_map}")

# ── 4. 비교 차트 ─────────────────────────────────────────────────────
print("비교 차트 시각화...")

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.patch.set_facecolor('#F8F9FA')

hours_list   = list(TARGET_HOURS.keys())
hours_labels = ['07시\n(이른 아침)', '10시\n(오전 더위)', '13시\n(폭염 피크)']
x = np.arange(len(hours_list))
w = 0.32

# ── (A) PPA 감소율 막대 그래프
ax1 = axes[0]
ax1.set_facecolor('#FAFAFA')

eung_declines = [stats['응봉동'][h]['decline'] for h in hours_list]
seong_declines = [stats['성수동'][h]['decline'] for h in hours_list]

bars1 = ax1.bar(x - w/2, eung_declines, w, label='응봉동 (교량 노출)',
                color='#1565C0', alpha=0.85, edgecolor='white', linewidth=0.8)
bars2 = ax1.bar(x + w/2, seong_declines, w, label='성수동 (비교군)',
                color='#2E7D32', alpha=0.85, edgecolor='white', linewidth=0.8)

# 값 레이블
for bar in bars1:
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
             f'{bar.get_height():.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold', color='#1565C0')
for bar in bars2:
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
             f'{bar.get_height():.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold', color='#2E7D32')

# 차이 화살표
for i, h in enumerate(hours_list):
    e, s = eung_declines[i], seong_declines[i]
    diff = round(e - s, 1)
    ax1.annotate('', xy=(x[i]-w/2, e+3), xytext=(x[i]+w/2, s+3),
                 arrowprops=dict(arrowstyle='<->', color='#B71C1C', lw=1.5))
    ax1.text(x[i], max(e, s)+5.5, f'Δ{diff}%p',
             ha='center', fontsize=9, color='#B71C1C', fontweight='bold')

ax1.set_xticks(x)
ax1.set_xticklabels(hours_labels, fontsize=11)
ax1.set_ylabel('Classic PPA 대비 감소율 (%)', fontsize=11)
ax1.set_title('시간대별 PPA 감소율 비교', fontsize=13, fontweight='bold', pad=12)
ax1.set_ylim(0, 100)
ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d%%'))
ax1.legend(fontsize=10, loc='upper left')
ax1.grid(axis='y', alpha=0.3, linestyle='--')
ax1.spines[['top', 'right']].set_visible(False)

# ── (B) Thermal PPA 절대값 (%) 꺾은선
ax2 = axes[1]
ax2.set_facecolor('#FAFAFA')

eung_pcts   = [stats['응봉동'][h]['thermal_pct'] for h in hours_list]
seong_pcts  = [stats['성수동'][h]['thermal_pct'] for h in hours_list]
eung_c_pct  = stats['응봉동'][7]['classic_pct']
seong_c_pct = stats['성수동'][7]['classic_pct']

ax2.axhline(eung_c_pct, color='#90CAF9', linestyle='--', linewidth=1.5,
            label=f'응봉동 Classic PPA ({eung_c_pct}%)', alpha=0.8)
ax2.axhline(seong_c_pct, color='#A5D6A7', linestyle='--', linewidth=1.5,
            label=f'성수동 Classic PPA ({seong_c_pct}%)', alpha=0.8)

ax2.plot(x, eung_pcts, 'o-', color='#1565C0', linewidth=2.5, markersize=9,
         label='응봉동 Thermal PPA', zorder=5)
ax2.plot(x, seong_pcts, 's-', color='#2E7D32', linewidth=2.5, markersize=9,
         label='성수동 Thermal PPA', zorder=5)

for i, (ep, sp) in enumerate(zip(eung_pcts, seong_pcts)):
    ax2.text(x[i]+0.05, ep+0.5, f'{ep}%', fontsize=9, color='#1565C0', fontweight='bold')
    ax2.text(x[i]+0.05, sp-1.5, f'{sp}%', fontsize=9, color='#2E7D32', fontweight='bold')

ax2.set_xticks(x)
ax2.set_xticklabels(hours_labels, fontsize=11)
ax2.set_ylabel('도달 가능 노드 비율 (%)', fontsize=11)
ax2.set_title('시간대별 Thermal PPA 절대값', fontsize=13, fontweight='bold', pad=12)
ax2.set_ylim(0, 75)
ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d%%'))
ax2.legend(fontsize=9, loc='upper right')
ax2.grid(axis='y', alpha=0.3, linestyle='--')
ax2.spines[['top', 'right']].set_visible(False)

fig.suptitle(
    '응봉동 vs 성수동 PPA 비교 — v3_asos (S-DoT 실측 기반)\n'
    '출발지: 각 지역 대표 집계구 | 시간예산 30분 | 목적지: 성동구민종합체육센터',
    fontsize=12, fontweight='bold', y=1.02
)
plt.tight_layout()
out_chart = os.path.join(FIG_DIR, 'comparison_ppa_chart_v3.png')
plt.savefig(out_chart, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"저장: {out_chart}")

# ── 5. 결과 요약 출력 ────────────────────────────────────────────────
print('\n===== 최종 비교 결과 =====')
print(f"{'':10} {'Classic':>10} {'07시':>12} {'10시':>12} {'13시':>12}")
for district in origins:
    c_pct = stats[district][7]['classic_pct']
    row_vals = [stats[district][h]['thermal_pct'] for h in hours_list]
    declines  = [stats[district][h]['decline']      for h in hours_list]
    print(f"{district:6} PPA(%)  {c_pct:>10.1f} " +
          "  ".join(f"{v:>5.1f}({d:>4.1f}%↓)" for v, d in zip(row_vals, declines)))
