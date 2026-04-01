"""
3D Space-Time Prism — v3_asos (S-DoT 실측 기반)
=================================================
버전 히스토리:
  v1 (2026-03-18): 시간대 → A/B/C 시나리오 고정 매핑, 하드코딩 speed_factor
  v3_asos (2026-04-01): link_utci_by_hour_v3.csv 실측 speed_factor 사용
                        슬라이스 색상 = 시간대별 실측 평균 UTCI 연속 컬러맵

Z축 : 시각 (07~21시)
XY축: 공간 (UTM 좌표 상대값, 미터)
바닥: 성동구 보행 네트워크

출력: figures/stp_3d_daily_v3_asos.png
"""

import os, json
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
import pyproj
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
from shapely.geometry import MultiPoint

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

BASE         = os.path.dirname(os.path.abspath(__file__))
NET_PATH     = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
LINK_UTCI    = os.path.join(BASE, "link_utci_by_hour_v3.csv")
REP_NODES    = os.path.join(BASE, "representative_nodes.json")
FIG_DIR      = os.path.join(BASE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

WALK_SPEED   = 4.5 * 1000 / 3600
TIME_BUDGET  = 30 * 60
GYM_LAT, GYM_LON = 37.546419, 127.044641
HOURS        = list(range(7, 22))   # 07~21시

# UTCI 컬러맵 설정 (32°C=주황, 39°C=진빨강)
CMAP   = cm.get_cmap('RdYlGn_r')
NORM   = mcolors.Normalize(vmin=30, vmax=42)

def utci_to_rgba(utci_val, alpha_face=0.42, alpha_edge=0.90):
    r, g, b, _ = CMAP(NORM(utci_val))
    return (r, g, b, alpha_face), (r, g, b, alpha_edge)

# Classic PPA: 면 채움 없이 윤곽선만 → Thermal 슬라이스가 가려지지 않도록
CLASSIC_STYLE = {"face": (0.40, 0.60, 0.90, 0.0), "edge": (0.20, 0.40, 0.75, 0.55)}

# ── 1. link_utci 로드 → (u, v, hour) → speed_factor ─────────────────
print("링크 UTCI 로드...")
link_df = pd.read_csv(LINK_UTCI, encoding='utf-8-sig')
link_df['u'] = link_df['u'].astype(str)
link_df['v'] = link_df['v'].astype(str)

speed_lookup = {}
for _, row in link_df.iterrows():
    h = int(row['hour'])
    speed_lookup[(row['u'], row['v'], h)] = row['speed_factor']
    speed_lookup[(row['v'], row['u'], h)] = row['speed_factor']

# 시간대별 성동구 평균 UTCI (슬라이스 색상용)
hour_avg_utci = link_df.groupby('hour')['utci_idw'].mean().to_dict()
print(f"  로드 완료 / 시간대별 평균 UTCI: {hour_avg_utci.get(7,0):.1f}°C(07시) ~ {hour_avg_utci.get(13,0):.1f}°C(13시)")

# ── 2. 네트워크 로드 ─────────────────────────────────────────────────
print("네트워크 로드...")
G_base     = ox.load_graphml(NET_PATH)
G_base     = G_base.to_undirected()
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)
gym_node   = ox.distance.nearest_nodes(G_base, GYM_LON, GYM_LAT)

transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32652", always_xy=True)
nodes_utm  = {nid: transformer.transform(row.geometry.x, row.geometry.y)
              for nid, row in nodes_gdf.iterrows()}
cx = np.mean([v[0] for v in nodes_utm.values()])
cy = np.mean([v[1] for v in nodes_utm.values()])
nodes_norm = {n: (x - cx, y - cy) for n, (x, y) in nodes_utm.items()}

with open(REP_NODES, encoding='utf-8') as f:
    rep_info = json.load(f)
origins = {"응봉동": rep_info["응봉동"], "성수동": rep_info["성수동"]}

# ── 3. convex hull 계산 헬퍼 ────────────────────────────────────────
def get_hull(G, origin, budget):
    try:
        lengths = nx.single_source_dijkstra_path_length(G, origin, cutoff=budget, weight='travel_time')
    except Exception:
        return None, 0
    coords = [nodes_norm[n] for n in lengths if n in nodes_norm]
    if len(coords) < 3:
        return None, len(lengths)
    hull = MultiPoint(coords).convex_hull
    if hull.geom_type == 'Polygon':
        xs, ys = hull.exterior.coords.xy
        return list(zip(xs, ys)), len(lengths)
    return None, len(lengths)

# ── 4. Classic PPA hull (시간 무관 — v1과 동일 방법) ────────────────
print("Classic PPA hull 계산...")
G_classic = G_base.copy()
for u, v, k, data in G_classic.edges(keys=True, data=True):
    data['travel_time'] = float(data.get('length', 0)) / WALK_SPEED

classic_hulls = {}
for district, origin in origins.items():
    classic_hulls[district], n = get_hull(G_classic, origin, TIME_BUDGET)
    print(f"  Classic {district}: {n:,}노드")

# ── 5. Thermal PPA hull — 시간대별 실측 speed_factor ─────────────────
print("Thermal PPA hull 계산 (시간대별 실측)...")
thermal_hulls = {d: {} for d in origins}

G_work = G_base.copy()  # 재사용할 그래프 (travel_time만 시간별 갱신)

for h in HOURS:
    # 해당 시간대 speed_factor 적용
    for u, v, k, data in G_work.edges(keys=True, data=True):
        length = float(data.get('length', 0))
        factor = speed_lookup.get((str(u), str(v), h), 0.75)
        data['travel_time'] = float('inf') if factor <= 0.05 else length / (WALK_SPEED * factor)

    for district, origin in origins.items():
        hull, n = get_hull(G_work, origin, TIME_BUDGET)
        thermal_hulls[district][h] = {'hull': hull, 'n': n, 'utci': hour_avg_utci.get(h, 35.0)}

    avg_u = hour_avg_utci.get(h, 0)
    print(f"  {h:02d}시 완료 — 평균 UTCI {avg_u:.1f}°C | 응봉동 {thermal_hulls['응봉동'][h]['n']:,}노드")

# ── 6. 바닥면 네트워크 세그먼트 ─────────────────────────────────────
base_z = 6.0
base_segs = []
for u, v, k, _ in G_base.edges(keys=True, data=True):
    if u in nodes_norm and v in nodes_norm:
        x0, y0 = nodes_norm[u]
        x1, y1 = nodes_norm[v]
        base_segs.append([(x0, y0, base_z), (x1, y1, base_z)])

# ── 7. 3D 렌더링 ────────────────────────────────────────────────────
print("3D 렌더링...")
fig = plt.figure(figsize=(24, 11))

district_info = {
    "응봉동": {"title": "응봉동 (열환경 취약 — 중랑천 교량 bottleneck)", "color": "#1565C0"},
    "성수동": {"title": "성수동 (비교군 — 교량 없음, 서울숲 인접)",      "color": "#2E7D32"},
}

for col, (district, origin) in enumerate(origins.items()):
    ax = fig.add_subplot(1, 2, col+1, projection='3d')
    ox_n, oy_n = nodes_norm[origin]
    gym_x, gym_y = nodes_norm.get(gym_node, (None, None))

    # 바닥면 네트워크
    lc = Line3DCollection(base_segs, colors=[(0.45, 0.45, 0.45, 0.7)], linewidths=0.6, zorder=1)
    ax.add_collection3d(lc)
    ax.scatter([ox_n], [oy_n], [base_z], color='black', s=60, zorder=10, depthshade=False)
    if gym_x is not None:
        ax.scatter([gym_x], [gym_y], [base_z], color='green', marker='^', s=80, zorder=10, depthshade=False)

    # Classic PPA 원기둥
    c_hull = classic_hulls[district]
    if c_hull:
        for h in HOURS:
            verts = [(x, y, h) for x, y in c_hull]
            ax.add_collection3d(Poly3DCollection([verts],
                facecolor=CLASSIC_STYLE["face"], edgecolor=CLASSIC_STYLE["edge"],
                linewidth=0.5, zorder=2))
        step = max(1, len(c_hull) // 10)
        for i in range(0, len(c_hull), step):
            px, py = c_hull[i]
            ax.plot([px, px], [py, py], [HOURS[0], HOURS[-1]],
                    color=(0.20, 0.40, 0.75), linewidth=0.7, alpha=0.55, zorder=2)

    # Thermal PPA 슬라이스 (시간대별 실측 UTCI 색상)
    prev_hull_data = None
    for h in HOURS:
        td  = thermal_hulls[district][h]
        hull_verts = td['hull']
        utci_val   = td['utci']
        face_c, edge_c = utci_to_rgba(utci_val)

        if hull_verts is None:
            prev_hull_data = None
            continue

        verts = [(x, y, h) for x, y in hull_verts]
        ax.add_collection3d(Poly3DCollection([verts],
            facecolor=face_c, edgecolor=edge_c, linewidth=1.2, zorder=4))

        # 윤곽선
        hx = [v[0] for v in verts] + [verts[0][0]]
        hy = [v[1] for v in verts] + [verts[0][1]]
        ax.plot(hx, hy, [h]*(len(verts)+1), color=edge_c[:3],
                linewidth=1.8, alpha=edge_c[3], zorder=5)

        # 이전 슬라이스와 연결선
        if prev_hull_data is not None:
            prev_verts, prev_h = prev_hull_data
            step = max(1, len(hull_verts) // 10)
            for i in range(0, len(hull_verts), step):
                px, py = hull_verts[i]
                dists = [(px-pv[0])**2 + (py-pv[1])**2 for pv in prev_verts]
                cpv = prev_verts[np.argmin(dists)]
                ax.plot([px, cpv[0]], [py, cpv[1]], [h, prev_h],
                        color=edge_c[:3], linewidth=0.45, alpha=0.4, zorder=3)

        prev_hull_data = (hull_verts, h)

    # 출발지·체육센터 수직선
    ax.plot([ox_n, ox_n], [oy_n, oy_n], [base_z, HOURS[-1]],
            color='black', linewidth=0.9, linestyle=':', alpha=0.6, zorder=6)
    if gym_x is not None:
        ax.plot([gym_x, gym_x], [gym_y, gym_y], [base_z, HOURS[-1]],
                color='green', linewidth=1.4, linestyle='--', alpha=0.65, zorder=6)

    # very strong heat 구간 표시 (12~16시)
    for h_mark, label, clr in [(12, "← very strong heat 시작", "#b71c1c"),
                                (17, "← very strong heat 완화", "#e65100")]:
        if c_hull:
            hx2 = [x for x, y in c_hull]
            hy2 = [y for x, y in c_hull]
            ax.plot(hx2 + [hx2[0]], hy2 + [hy2[0]], [h_mark]*(len(hx2)+1),
                    color=clr, linewidth=0.8, linestyle='--', alpha=0.45)
        xmax = ox_n + 1300
        ax.text(xmax, oy_n, h_mark, label, fontsize=7, color=clr, va='center', zorder=10)

    ax.set_zlim(base_z, 22)
    ax.set_zticks(HOURS)
    ax.set_zticklabels([f"{h:02d}:00" for h in HOURS], fontsize=7)
    ax.set_xlabel("서 ← → 동 (m)", fontsize=9, labelpad=8)
    ax.set_ylabel("남 ← → 북 (m)", fontsize=9, labelpad=8)
    ax.set_zlabel("시각", fontsize=9, labelpad=12)
    ax.tick_params(axis='x', labelsize=6)
    ax.tick_params(axis='y', labelsize=6)
    ax.view_init(elev=22, azim=-50)
    ax.set_title(district_info[district]["title"], fontsize=11, fontweight='bold',
                 pad=14, color=district_info[district]["color"])
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('0.85')
    ax.yaxis.pane.set_edgecolor('0.85')
    ax.zaxis.pane.set_edgecolor('0.85')

# 컬러바 (UTCI 수치 범례)
sm = cm.ScalarMappable(cmap=CMAP, norm=NORM)
sm.set_array([])
cbar = fig.colorbar(sm, ax=fig.get_axes(), orientation='vertical',
                    fraction=0.012, pad=0.04, shrink=0.5)
cbar.set_label('평균 UTCI (°C)', fontsize=9)
cbar.ax.tick_params(labelsize=8)

# 범례
legend_items = [
    mpatches.Patch(facecolor=(0.40,0.60,0.90,0.5), edgecolor=(0.20,0.40,0.75),
                   linewidth=1.2, label="Classic PPA — 열환경 미적용 (원기둥)"),
    mpatches.Patch(facecolor=CMAP(NORM(32.5)), edgecolor='gray',
                   linewidth=1.2, label="Thermal PPA — strong heat (32~38°C)"),
    mpatches.Patch(facecolor=CMAP(NORM(39.0)), edgecolor='gray',
                   linewidth=1.2, label="Thermal PPA — very strong heat (≥38°C)"),
]
fig.legend(handles=legend_items, loc='lower center', ncol=3, fontsize=9,
           framealpha=0.92, bbox_to_anchor=(0.5, -0.04),
           title="범례 | 데이터: S-DoT 2025.07.28~08.03 평균 | 출발지: 집계구 대표점 | 시간예산 30분 | ▲녹색: 성동구민종합체육센터",
           title_fontsize=8)

plt.suptitle(
    "Space-Time Prism 3D — v2 (S-DoT 실측 기반): 하루 시간대별 보행 접근 공간 변화\n"
    "슬라이스 색상 = 성동구 평균 UTCI 실측값 (오렌지→빨강: 열 스트레스 증가)",
    fontsize=12, fontweight='bold', y=1.02
)

plt.tight_layout()
out = os.path.join(FIG_DIR, "stp_3d_daily_v3_asos.png")
plt.savefig(out, dpi=150, bbox_inches='tight')
plt.close()
print(f"\n저장: {out}")
