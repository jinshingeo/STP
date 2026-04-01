"""
IDW 링크 보간 — v3 (ASOS 풍속·일사량 기반 UTCI)
================================================
v2와 동일한 IDW 로직, 입력 데이터만 v3로 교체:
  - 입력: sdot_utci_v3_seongdong.csv (utci_v3 컬럼)
  - 출력: link_utci_by_hour_v3.csv
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import LineString

BASE         = Path(__file__).parent
NETWORK_FILE = BASE / '../01_네트워크/seongdong_walk_network.graphml'
UTCI_FILE    = BASE / 'sdot_utci_v3_seongdong.csv'
OUT_DIR      = BASE
FIG_DIR      = BASE / 'figures'
FIG_DIR.mkdir(exist_ok=True)

IDW_POWER = 2
wgs_to_5186 = Transformer.from_crs('EPSG:4326', 'EPSG:5186', always_xy=True)

# ── 1. 네트워크 로드 ─────────────────────────────────────────────────
print('네트워크 로드...')
G = nx.read_graphml(NETWORK_FILE)
print(f'  노드: {G.number_of_nodes():,} / 엣지: {G.number_of_edges():,}')

node_xy = {}
for nid, d in G.nodes(data=True):
    x5186, y5186 = wgs_to_5186.transform(float(d['x']), float(d['y']))
    node_xy[nid] = (x5186, y5186)

edge_rows = []
for u, v, d in G.edges(data=True):
    x_u, y_u = node_xy[u]
    x_v, y_v = node_xy[v]
    mx, my = (x_u + x_v) / 2, (y_u + y_v) / 2
    edge_rows.append({
        'u': u, 'v': v,
        'mx': mx, 'my': my,
        'highway': d.get('highway', 'unknown'),
        'bridge': d.get('bridge', 'no'),
        'length': float(d.get('length', 0)),
        'name': d.get('name', '')
    })

edges_df = pd.DataFrame(edge_rows)
print(f'  링크 수: {len(edges_df):,} / 교량: {(edges_df["bridge"] == "yes").sum()}개')

# ── 2. v3 UTCI 센서 데이터 로드 ──────────────────────────────────────
print('\nUTCI v3 데이터 로드...')
utci_df = pd.read_csv(UTCI_FILE, encoding='utf-8-sig')

sensor_hourly = (
    utci_df
    .groupby(['serial', 'hour', 'lat', 'lon'])['utci_v3']
    .mean()
    .reset_index()
    .rename(columns={'utci_v3': 'utci_mean'})
)

sx, sy = wgs_to_5186.transform(
    sensor_hourly['lon'].values,
    sensor_hourly['lat'].values
)
sensor_hourly['sx'] = sx
sensor_hourly['sy'] = sy

print(f'  센서-시간대 조합: {len(sensor_hourly):,}개')
print(f'  시간대: {sensor_hourly["hour"].nunique()}개 / 센서: {sensor_hourly["serial"].nunique()}개')

# ── 3. IDW 보간 함수 ─────────────────────────────────────────────────
def idw_interpolate(qx, qy, sensor_x, sensor_y, sensor_vals, power=2):
    dx = sensor_x - qx
    dy = sensor_y - qy
    dist = np.sqrt(dx**2 + dy**2)
    if dist.min() < 1.0:
        return sensor_vals[dist.argmin()]
    w = 1.0 / (dist ** power)
    return np.sum(w * sensor_vals) / np.sum(w)

def utci_to_speed_factor(utci_val, is_bridge=False):
    if utci_val < 26:   sf = 1.00
    elif utci_val < 32: sf = 0.90
    elif utci_val < 38: sf = 0.75
    elif utci_val < 46: sf = 0.50
    else:               sf = 0.20
    if is_bridge:
        sf *= 0.7
    return round(sf, 4)

# ── 4. 전체 시간대 IDW 실행 ──────────────────────────────────────────
print('\nIDW 보간 실행 중...')
hours = sorted(sensor_hourly['hour'].unique())
all_results = []

for hour in hours:
    h_df = sensor_hourly[sensor_hourly['hour'] == hour]
    sx_h = h_df['sx'].values
    sy_h = h_df['sy'].values
    uv_h = h_df['utci_mean'].values

    for _, row in edges_df.iterrows():
        utci_idw = idw_interpolate(row['mx'], row['my'], sx_h, sy_h, uv_h, IDW_POWER)
        is_bridge = row['bridge'] == 'yes'
        sf = utci_to_speed_factor(utci_idw, is_bridge)
        all_results.append({
            'u': row['u'], 'v': row['v'],
            'hour': hour,
            'utci_idw': round(utci_idw, 2),
            'speed_factor': sf,
            'bridge': row['bridge'],
            'highway': row['highway'],
        })

    if hour % 6 == 0:
        print(f'  {hour:02d}시 완료')

link_utci = pd.DataFrame(all_results)
print(f'\nIDW 완료: {len(link_utci):,}행 (링크×시간대)')

# ── 5. 결과 저장 ─────────────────────────────────────────────────────
out_path = OUT_DIR / 'link_utci_by_hour_v3.csv'
link_utci.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f'저장: {out_path}')

print('\n핵심 시간대 링크 평균 UTCI (v3):')
for h in [7, 10, 13, 17, 20]:
    sub = link_utci[link_utci['hour'] == h]
    all_avg = sub['utci_idw'].mean()
    brg = sub[sub['bridge'] == 'yes']
    brg_avg = brg['utci_idw'].mean() if len(brg) > 0 else float('nan')
    brg_sf  = brg['speed_factor'].mean() if len(brg) > 0 else float('nan')
    print(f'  {h:02d}시 — 전체 {all_avg:.1f}°C | 교량 {brg_avg:.1f}°C (속도계수 {brg_sf:.2f})')
