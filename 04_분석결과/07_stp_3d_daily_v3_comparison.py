"""
3D Space-Time Prism — v3_comparison (응봉동 vs 성수동 비교)
============================================================
버전 히스토리:
  v1      (2026-03-18): 시나리오 하드코딩, 응봉동만
  v2_sdot (2026-04-01): S-DoT 실측, 응봉동+성수동 (색상 개선)
  v3_comparison (2026-04-01): 두 지역 비교 강조, 핵심 시각 주석 추가

개선사항 (v2→v3):
  - 07시/13시/21시 주요 시각에 감소율 텍스트 주석
  - 두 지역 PPA 크기 비교 강조 (Classic 윤곽선 색 구분)
  - 13시 very strong heat 구간 수평 강조면 추가

출력: figures/stp_3d_daily_v3_comparison.png
"""

import os, json, pickle
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
import pyproj, networkx as nx, osmnx as ox

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

BASE    = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, '../01_네트워크/seongdong_walk_network.graphml')
FIG_DIR = os.path.join(BASE, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

WALK_SPEED  = 4.5 * 1000 / 3600
TIME_BUDGET = 30 * 60
HOURS       = list(range(7, 22))
ANNOT_HOURS = {7, 13, 21}   # 감소율 텍스트 표시할 시각

CMAP = matplotlib.colormaps['RdYlGn_r']
NORM = mcolors.Normalize(vmin=30, vmax=42)

def utci_rgba(utci, alpha_face=0.42, alpha_edge=0.92):
    r, g, b, _ = CMAP(NORM(utci))
    return (r, g, b, alpha_face), (r, g, b, alpha_edge)

# Classic 스타일: 지역별 색 구분 (응봉동=파랑 와이어, 성수동=초록 와이어)
CLASSIC = {
    '응봉동': {'edge': (0.13, 0.38, 0.70, 0.60), 'face': (0.13, 0.38, 0.70, 0.0)},
    '성수동': {'edge': (0.18, 0.49, 0.20, 0.60), 'face': (0.18, 0.49, 0.20, 0.0)},
}

# ── 1. 데이터 로드 ──────────────────────────────────────────────────
print("데이터 로드...")
with open('/tmp/stp3d_data.pkl', 'rb') as f:
    dat = pickle.load(f)

classic_data   = dat['classic']
thermal_data   = dat['thermal']
nodes_norm     = dat['nodes_norm']
origins        = dat['origins']
rep            = dat['rep']
hour_avg_utci  = dat['hour_avg_utci']

# 네트워크 엣지 (바닥면)
print("네트워크 바닥면 준비...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()
nodes_gdf, _ = ox.graph_to_gdfs(G_base)

gym_node = rep['gym_node']

base_z    = 6.0
base_segs = []
for u, v, k, _ in G_base.edges(keys=True, data=True):
    if u in nodes_norm and v in nodes_norm:
        x0, y0 = nodes_norm[u]
        x1, y1 = nodes_norm[v]
        base_segs.append([(x0, y0, base_z), (x1, y1, base_z)])

# ── 2. 3D 렌더링 ────────────────────────────────────────────────────
print("3D 렌더링...")
fig = plt.figure(figsize=(24, 12))
fig.patch.set_facecolor('#F5F5F5')

DISTRICT_META = {
    '응봉동': {
        'title':  '응봉동  |  열환경 취약\n중랑천 교량(고산자로) 필수 통과',
        'tcolor': '#0D47A1',
        'tag':    '교량 bottleneck ↑',
    },
    '성수동': {
        'title':  '성수동  |  비교군\n교량 없음 · 서울숲 인접',
        'tcolor': '#1B5E20',
        'tag':    '교량 없음',
    },
}

for col, (district, origin) in enumerate(origins.items()):
    ax = fig.add_subplot(1, 2, col+1, projection='3d')
    ax.set_facecolor('#ECEFF1')

    meta     = DISTRICT_META[district]
    c_style  = CLASSIC[district]
    ox_n, oy_n = nodes_norm[origin]
    gym_xy   = nodes_norm.get(gym_node)

    # ── 바닥면 네트워크
    lc = Line3DCollection(base_segs, colors=[(0.50, 0.50, 0.50, 0.65)],
                          linewidths=0.55, zorder=1)
    ax.add_collection3d(lc)
    ax.scatter([ox_n], [oy_n], [base_z], color='black', s=70,
               zorder=10, depthshade=False)
    if gym_xy:
        ax.scatter([gym_xy[0]], [gym_xy[1]], [base_z], color='#E53935',
                   marker='^', s=90, zorder=10, depthshade=False)

    # ── Classic PPA 원기둥 (와이어프레임)
    c_hull = classic_data[district]['hull']
    c_n    = classic_data[district]['n']
    if c_hull:
        for h in HOURS:
            verts = [(x, y, h) for x, y in c_hull]
            ax.add_collection3d(Poly3DCollection([verts],
                facecolor=c_style['face'], edgecolor=c_style['edge'],
                linewidth=0.5, zorder=2))
        # 수직 와이어
        step = max(1, len(c_hull) // 12)
        for i in range(0, len(c_hull), step):
            px, py = c_hull[i]
            ax.plot([px, px], [py, py], [HOURS[0], HOURS[-1]],
                    color=c_style['edge'][:3], linewidth=0.7,
                    alpha=c_style['edge'][3], zorder=2)

    # ── Thermal PPA 슬라이스
    prev = None
    for h in HOURS:
        td   = thermal_data[district][h]
        hull_verts = td['hull']
        if hull_verts is None:
            prev = None
            continue

        fc, ec = utci_rgba(td['utci'])
        verts  = [(x, y, h) for x, y in hull_verts]

        ax.add_collection3d(Poly3DCollection([verts],
            facecolor=fc, edgecolor=ec, linewidth=1.2, zorder=4))

        # 윤곽선
        hx = [v[0] for v in verts] + [verts[0][0]]
        hy = [v[1] for v in verts] + [verts[0][1]]
        ax.plot(hx, hy, [h]*(len(verts)+1), color=ec[:3],
                linewidth=1.8, alpha=ec[3], zorder=5)

        # 이전 슬라이스 연결
        if prev:
            pv, ph = prev
            step = max(1, len(hull_verts) // 10)
            for i in range(0, len(hull_verts), step):
                px, py = hull_verts[i]
                dists  = [(px-p[0])**2+(py-p[1])**2 for p in pv]
                cp     = pv[np.argmin(dists)]
                ax.plot([px, cp[0]], [py, cp[1]], [h, ph],
                        color=ec[:3], linewidth=0.45, alpha=0.38, zorder=3)

        # 주요 시각 감소율 주석
        if h in ANNOT_HOURS and hull_verts:
            xs = [p[0] for p in hull_verts]
            xmax = max(xs) + 200
            ax.text(xmax, oy_n, h,
                    f"  -{td['decline']}%",
                    fontsize=8.5, color='#B71C1C', fontweight='bold',
                    va='center', zorder=10)

        prev = (hull_verts, h)

    # ── 13시 very strong heat 수평 강조면
    if c_hull:
        xs = [p[0] for p in c_hull] + [c_hull[0][0]]
        ys = [p[1] for p in c_hull] + [c_hull[0][1]]
        ax.plot(xs, ys, [13]*len(xs), color='#B71C1C',
                linewidth=1.2, linestyle='--', alpha=0.5, zorder=6)
        ax.plot(xs, ys, [16]*len(xs), color='#E65100',
                linewidth=0.8, linestyle=':', alpha=0.4, zorder=6)

    # ── 출발지/체육센터 수직선
    ax.plot([ox_n, ox_n], [oy_n, oy_n], [base_z, HOURS[-1]],
            color='black', linewidth=0.9, linestyle=':', alpha=0.55, zorder=6)
    if gym_xy:
        ax.plot([gym_xy[0], gym_xy[0]], [gym_xy[1], gym_xy[1]], [base_z, HOURS[-1]],
                color='#E53935', linewidth=1.4, linestyle='--', alpha=0.6, zorder=6)

    # ── Classic 크기 텍스트
    if c_hull:
        cx_txt = np.mean([p[0] for p in c_hull])
        cy_txt = np.mean([p[1] for p in c_hull])
        ax.text(cx_txt, cy_txt, HOURS[-1]+0.8,
                f'Classic\n{round(c_n/G_base.number_of_nodes()*100,1)}%',
                fontsize=8, color=c_style['edge'][:3], ha='center',
                va='bottom', zorder=10, alpha=0.85)

    # ── 축
    ax.set_zlim(base_z, 22.5)
    ax.set_zticks(HOURS)
    ax.set_zticklabels([f"{h:02d}:00" for h in HOURS], fontsize=7)
    ax.set_xlabel("서 ← → 동 (m)", fontsize=9, labelpad=8)
    ax.set_ylabel("남 ← → 북 (m)", fontsize=9, labelpad=8)
    ax.set_zlabel("시각", fontsize=9, labelpad=12)
    ax.tick_params(axis='x', labelsize=6)
    ax.tick_params(axis='y', labelsize=6)
    ax.view_init(elev=22, azim=-50)
    ax.set_title(meta['title'], fontsize=11, fontweight='bold',
                 pad=14, color=meta['tcolor'])
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('0.82')
    ax.yaxis.pane.set_edgecolor('0.82')
    ax.zaxis.pane.set_edgecolor('0.82')

# ── 컬러바
sm = cm.ScalarMappable(cmap=CMAP, norm=NORM)
sm.set_array([])
cbar = fig.colorbar(sm, ax=fig.get_axes(), orientation='vertical',
                    fraction=0.011, pad=0.04, shrink=0.48)
cbar.set_label('평균 UTCI (°C)', fontsize=9)
cbar.ax.tick_params(labelsize=8)
for utci_val, label in [(32, 'strong\nheat'), (38, 'very strong\nheat')]:
    cbar.ax.axhline(NORM(utci_val), color='white', linewidth=1.2, alpha=0.7)
    cbar.ax.text(1.6, NORM(utci_val), label, va='center', fontsize=7,
                 color='#555', transform=cbar.ax.transAxes)

# ── 범례
legend_items = [
    mpatches.Patch(facecolor=(0.13,0.38,0.70,0.4), edgecolor=(0.13,0.38,0.70),
                   linewidth=1, label='Classic PPA — 응봉동 (와이어프레임)'),
    mpatches.Patch(facecolor=(0.18,0.49,0.20,0.4), edgecolor=(0.18,0.49,0.20),
                   linewidth=1, label='Classic PPA — 성수동 (와이어프레임)'),
    mpatches.Patch(facecolor=CMAP(NORM(33)), label='Thermal PPA — strong heat (32~38°C)'),
    mpatches.Patch(facecolor=CMAP(NORM(39)), label='Thermal PPA — very strong heat (≥38°C)'),
    plt.Line2D([0],[0], color='#B71C1C', lw=1.2, ls='--',
               label='13시 very strong heat 시작 경계'),
    plt.Line2D([0],[0], marker='o', color='#B71C1C', lw=0, markersize=7,
               label='숫자 = Classic 대비 PPA 감소율 (07/13/21시)'),
]
fig.legend(handles=legend_items, loc='lower center', ncol=3, fontsize=9,
           framealpha=0.95, bbox_to_anchor=(0.5, -0.04),
           title="데이터: S-DoT 2025.07.28~08.03 평균 | 시간예산 30분 | ▲빨간점: 성동구민종합체육센터",
           title_fontsize=8)

fig.suptitle(
    "Space-Time Prism 3D — v3 비교: 응봉동(교량 취약) vs 성수동(비교군)\n"
    "슬라이스 색상 = 실측 UTCI | 13시 폭염 피크 응봉동 -81.6% vs 성수동 -67.6% (Δ14.0%p)",
    fontsize=12, fontweight='bold', y=1.02
)

plt.tight_layout()
out = os.path.join(FIG_DIR, 'stp_3d_daily_v3_comparison.png')
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"저장: {out}")
