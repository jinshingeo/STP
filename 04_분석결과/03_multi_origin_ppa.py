"""
다중 출발지 Thermal-Inclusive PPA 분석
- 출발지: 응봉동 집계구 중심점 (33개) vs 성수동 집계구 중심점 (122개)
- 도착지: 성동구민종합체육센터 (37.546419, 127.044641)
- 시간예산: 30분
- 시나리오 A/B/C: 열환경 조건별 도로 임피던스 적용

핵심 질문: 폭염 시 어느 집계구에서 체육센터 접근이 불가능해지는가?
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
NET_PATH = os.path.join(BASE, "../01_네트워크/seongdong_walk_network.graphml")
JIBGU_PATH = "/Users/jin/석사논문/통계지역경계/집계구.shp"
OUT_DIR = BASE

# ── 파라미터 ────────────────────────────────────────────────────────
WALK_SPEED_BASE = 4.5 * 1000 / 3600   # m/s
TIME_BUDGET_SEC = 30 * 60

# 성동구민종합체육센터
GYM_LAT, GYM_LON = 37.546419, 127.044641

# ── 시나리오 정의 ────────────────────────────────────────────────────
SCENARIOS = {
    "A_쾌적_07시": {
        "label": "시나리오 A\n쾌적 (07:00)\nUTCI < 26°C",
        "short": "A (쾌적)",
        "color": "#2196F3",
        "speed_factor": {"bridge": 1.0, "major_road": 1.0, "local": 1.0},
    },
    "B_보통더위_10시": {
        "label": "시나리오 B\n보통 더위 (10:00)\nUTCI 26~32°C",
        "short": "B (보통 더위)",
        "color": "#FF9800",
        "speed_factor": {"bridge": 0.5, "major_road": 0.8, "local": 0.9},
    },
    "C_폭염피크_13시": {
        "label": "시나리오 C\n폭염 피크 (13:00)\nUTCI > 38°C",
        "short": "C (폭염 피크)",
        "color": "#F44336",
        "speed_factor": {"bridge": 0.0, "major_road": 0.4, "local": 0.7},
    },
}

# ── 도로 유형 분류 ────────────────────────────────────────────────────
def classify_edge(data):
    bridge = data.get("bridge", None)
    highway = data.get("highway", "")
    if isinstance(highway, list):
        highway = highway[0]
    if bridge and bridge not in [None, "nan"]:
        return "bridge"
    if highway in ["trunk", "trunk_link", "primary", "primary_link",
                   "secondary", "secondary_link"]:
        return "major_road"
    return "local"

# ── 네트워크 로드 ────────────────────────────────────────────────────
print("네트워크 로드...")
G_base = ox.load_graphml(NET_PATH)
G_base = G_base.to_undirected()

# 엣지 유형 사전 분류
edge_types = {}
for u, v, k, data in G_base.edges(keys=True, data=True):
    edge_types[(u, v, k)] = classify_edge(data)

bridge_count = sum(1 for t in edge_types.values() if t == "bridge")
print(f"  bridge 엣지: {bridge_count}개 | major_road: {sum(1 for t in edge_types.values() if t=='major_road')}개")

# 체육센터 노드
gym_node = ox.distance.nearest_nodes(G_base, GYM_LON, GYM_LAT)
print(f"성동구민종합체육센터 노드: {gym_node}")

# ── 집계구 로드 ──────────────────────────────────────────────────────
print("\n집계구 로드...")
jibgu = gpd.read_file(JIBGU_PATH)

# 한국 표준 TM 좌표계 설정 후 재투영
jibgu = jibgu.set_crs("EPSG:5179", allow_override=True)
jibgu_wgs84 = jibgu.to_crs("EPSG:4326")

# 응봉동 / 성수동 필터
eungbong_gdf = jibgu_wgs84[jibgu_wgs84["ADM_NM"] == "응봉동"].copy()
sungsu_gdf   = jibgu_wgs84[jibgu_wgs84["ADM_NM"].str.contains("성수", na=False)].copy()

print(f"  응봉동 집계구: {len(eungbong_gdf)}개")
print(f"  성수동 집계구: {len(sungsu_gdf)}개")

# 중심점 계산 (UTM 투영 후 centroid)
jibgu_utm = jibgu.to_crs("EPSG:32652")  # UTM Zone 52N
eungbong_utm = jibgu_utm[jibgu["ADM_NM"] == "응봉동"].copy()
sungsu_utm   = jibgu_utm[jibgu["ADM_NM"].str.contains("성수", na=False)].copy()

eungbong_gdf["centroid_wgs"] = eungbong_utm.centroid.to_crs("EPSG:4326").values
sungsu_gdf["centroid_wgs"]   = sungsu_utm.centroid.to_crs("EPSG:4326").values

# 네트워크 최근접 노드 스냅
def snap_to_node(G, geom):
    return ox.distance.nearest_nodes(G, geom.x, geom.y)

eungbong_gdf["origin_node"] = eungbong_gdf["centroid_wgs"].apply(lambda g: snap_to_node(G_base, g))
sungsu_gdf["origin_node"]   = sungsu_gdf["centroid_wgs"].apply(lambda g: snap_to_node(G_base, g))

# 동일 origin_node로 스냅된 집계구 통합 (중복 제거)
eungbong_nodes = eungbong_gdf["origin_node"].unique()
sungsu_nodes   = sungsu_gdf["origin_node"].unique()
print(f"  응봉동 고유 origin 노드: {len(eungbong_nodes)}개")
print(f"  성수동 고유 origin 노드: {len(sungsu_nodes)}개")

# ── 시나리오별 그래프 준비 ────────────────────────────────────────────
print("\n시나리오별 travel_time 계산...")
scenario_graphs = {}
for sid, scenario in SCENARIOS.items():
    G = G_base.copy()
    for u, v, k, data in G.edges(keys=True, data=True):
        length = data.get("length", 0)
        etype  = edge_types.get((u, v, k), "local")
        factor = scenario["speed_factor"][etype]
        data["travel_time"] = float("inf") if factor == 0 else length / (WALK_SPEED_BASE * factor)
    scenario_graphs[sid] = G

# ── 다중 출발지 PPA 계산 ─────────────────────────────────────────────
print("\nPPA 계산 중...")

def compute_ppa_results(origin_nodes, G_dict, gym_node, time_budget):
    """각 origin_node × 시나리오별 (도달가능여부, 체육센터접근가능여부) 계산"""
    records = []
    for node in origin_nodes:
        row = {"origin_node": node}
        for sid, G in G_dict.items():
            try:
                lengths = nx.single_source_dijkstra_path_length(
                    G, node, cutoff=time_budget, weight="travel_time"
                )
                reachable = set(lengths.keys())
                gym_accessible = gym_node in reachable
                gym_time = lengths.get(gym_node, None)
            except Exception:
                reachable = set()
                gym_accessible = False
                gym_time = None
            row[f"{sid}_reachable_count"] = len(reachable)
            row[f"{sid}_gym_accessible"] = gym_accessible
            row[f"{sid}_gym_time_min"] = round(gym_time / 60, 1) if gym_time else None
        records.append(row)
    return records

eungbong_records = compute_ppa_results(eungbong_nodes, scenario_graphs, gym_node, TIME_BUDGET_SEC)
sungsu_records   = compute_ppa_results(sungsu_nodes,   scenario_graphs, gym_node, TIME_BUDGET_SEC)

import pandas as pd
eungbong_df = pd.DataFrame(eungbong_records)
sungsu_df   = pd.DataFrame(sungsu_records)

# ── 요약 출력 ────────────────────────────────────────────────────────
print("\n=== 체육센터 접근 가능 비율 ===")
for sid in SCENARIOS:
    col = f"{sid}_gym_accessible"
    e_pct = eungbong_df[col].mean() * 100
    s_pct = sungsu_df[col].mean() * 100
    print(f"  {SCENARIOS[sid]['short']:12s}  응봉동: {e_pct:5.1f}%  |  성수동: {s_pct:5.1f}%")

# ── 시각화 1: 시나리오별 접근 가능/불가 맵 (응봉동) ──────────────────
print("\n시각화 생성 중...")
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_base)

# 각 집계구에 시나리오별 접근 여부 병합
eungbong_plot = eungbong_gdf.merge(eungbong_df, on="origin_node", how="left")

fig, axes = plt.subplots(1, 3, figsize=(21, 9))

for ax, sid in zip(axes, SCENARIOS):
    col = f"{sid}_gym_accessible"
    scenario = SCENARIOS[sid]

    # 배경 네트워크
    edges_gdf.plot(ax=ax, color="#e0e0e0", linewidth=0.4, alpha=0.6)

    # 집계구: 접근 가능(파랑) / 불가(빨강) / NaN(회색)
    accessible = eungbong_plot[eungbong_plot[col] == True]
    blocked    = eungbong_plot[eungbong_plot[col] == False]

    if len(blocked) > 0:
        blocked.plot(ax=ax, color="#F44336", alpha=0.65, edgecolor="darkred", linewidth=0.6, zorder=3)
    if len(accessible) > 0:
        accessible.plot(ax=ax, color="#2196F3", alpha=0.55, edgecolor="#1565C0", linewidth=0.6, zorder=3)

    # 체육센터 위치
    gym_geom = nodes_gdf.loc[gym_node].geometry
    ax.plot(gym_geom.x, gym_geom.y, "g^", markersize=12, zorder=7,
            label=f"체육센터")

    # 고산자로 bridge 강조
    bridge_edges = edges_gdf[edges_gdf["bridge"].notna() &
                             edges_gdf["highway"].astype(str).str.contains("primary")]
    if len(bridge_edges) > 0:
        bridge_edges.plot(ax=ax, color="purple", linewidth=2.5, zorder=5, alpha=0.8,
                         label="주요 교량\n(열환경 노출)")

    n_accessible = eungbong_plot[col].sum()
    n_total = len(eungbong_plot)
    ax.set_title(
        f"{scenario['label']}\n"
        f"접근 가능: {int(n_accessible)}/{n_total} 집계구 ({n_accessible/n_total*100:.0f}%)",
        fontsize=11
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.set_axis_off()

plt.suptitle(
    "응봉동 집계구별 성동구민종합체육센터 접근 가능성 변화\n"
    "시나리오 A(쾌적) → B(보통 더위) → C(폭염 피크): 열환경에 따른 접근 불가 집계구 증가",
    fontsize=13, fontweight="bold"
)
plt.tight_layout()
out1 = os.path.join(OUT_DIR, "multi_origin_eungbong_accessibility.png")
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out1}")

# ── 시각화 2: 응봉동 vs 성수동 비교 막대그래프 ──────────────────────
sungsu_plot = sungsu_gdf.merge(sungsu_df, on="origin_node", how="left")

fig, axes = plt.subplots(1, 2, figsize=(14, 7))
district_data = {
    "응봉동": eungbong_plot,
    "성수동": sungsu_plot,
}
colors_accessible = {"응봉동": "#1565C0", "성수동": "#2E7D32"}
colors_blocked    = {"응봉동": "#C62828", "성수동": "#E65100"}

for ax, (district, df) in zip(axes, district_data.items()):
    scenario_labels = [SCENARIOS[s]["short"] for s in SCENARIOS]
    acc_rates = []
    blk_rates = []
    for sid in SCENARIOS:
        col = f"{sid}_gym_accessible"
        if col in df.columns:
            acc = df[col].mean() * 100
        else:
            acc = 0
        acc_rates.append(acc)
        blk_rates.append(100 - acc)

    x = np.arange(len(SCENARIOS))
    width = 0.5
    bars_acc = ax.bar(x, acc_rates, width, label="접근 가능", color=colors_accessible[district], alpha=0.85)
    bars_blk = ax.bar(x, blk_rates, width, bottom=acc_rates, label="접근 불가", color=colors_blocked[district], alpha=0.7)

    for bar, val in zip(bars_acc, acc_rates):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2,
                f"{val:.0f}%", ha="center", va="center", fontsize=12, fontweight="bold", color="white")
    for bar, val, acc in zip(bars_blk, blk_rates, acc_rates):
        if val > 5:
            ax.text(bar.get_x() + bar.get_width()/2, acc + val/2,
                    f"{val:.0f}%", ha="center", va="center", fontsize=12, fontweight="bold", color="white")

    ax.set_title(f"{district} — 체육센터 접근 가능성", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_labels, fontsize=11)
    ax.set_ylim(0, 110)
    ax.set_ylabel("집계구 비율 (%)", fontsize=11)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

plt.suptitle(
    "열환경 시나리오별 성동구민종합체육센터 접근 가능 집계구 비율\n"
    "응봉동(교량 bottleneck 존재) vs 성수동(비교군)",
    fontsize=13, fontweight="bold"
)
plt.tight_layout()
out2 = os.path.join(OUT_DIR, "multi_origin_district_comparison.png")
plt.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print(f"저장: {out2}")

# ── 결과 JSON 저장 ───────────────────────────────────────────────────
summary = {}
for sid in SCENARIOS:
    col = f"{sid}_gym_accessible"
    summary[sid] = {
        "응봉동": {
            "origin_nodes": len(eungbong_nodes),
            "gym_accessible": int(eungbong_plot[col].sum()) if col in eungbong_plot.columns else 0,
            "gym_accessible_pct": round(eungbong_plot[col].mean() * 100, 1) if col in eungbong_plot.columns else 0,
        },
        "성수동": {
            "origin_nodes": len(sungsu_nodes),
            "gym_accessible": int(sungsu_plot[col].sum()) if col in sungsu_plot.columns else 0,
            "gym_accessible_pct": round(sungsu_plot[col].mean() * 100, 1) if col in sungsu_plot.columns else 0,
        }
    }

with open(os.path.join(OUT_DIR, "multi_origin_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n=== 최종 요약 ===")
for sid, res in summary.items():
    label = SCENARIOS[sid]["short"]
    e = res["응봉동"]
    s = res["성수동"]
    print(f"  {label}: 응봉동 {e['gym_accessible']}/{e['origin_nodes']} ({e['gym_accessible_pct']}%) "
          f"| 성수동 {s['gym_accessible']}/{s['origin_nodes']} ({s['gym_accessible_pct']}%)")

print("\n완료.")
