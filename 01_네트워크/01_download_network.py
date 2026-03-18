"""
성동구 보행자 도로 네트워크 수집 (OSM 기반)
- walk 네트워크: 보행자가 이용 가능한 모든 도로
- 결과: GeoPackage + GraphML 형식으로 저장
"""

import osmnx as ox
import geopandas as gpd
import os

# 저장 경로
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

print("성동구 보행자 네트워크 다운로드 시작...")

# 성동구 전체 + 인접 한강 포함 (대교 건너기 케이스 위해 버퍼 포함)
PLACE = "성동구, 서울특별시, 대한민국"

# walk 네트워크 (보행자용)
G_walk = ox.graph_from_place(PLACE, network_type="walk", retain_all=True)

print(f"  노드 수: {len(G_walk.nodes):,}")
print(f"  엣지 수: {len(G_walk.edges):,}")

# GeoDataFrame으로 변환
nodes, edges = ox.graph_to_gdfs(G_walk)

print(f"\n  좌표계: {edges.crs}")
print(f"  엣지 컬럼: {list(edges.columns)}")

# 저장
graphml_path = os.path.join(OUTPUT_DIR, "seongdong_walk_network.graphml")
gpkg_path = os.path.join(OUTPUT_DIR, "seongdong_walk_network.gpkg")

ox.save_graphml(G_walk, graphml_path)
edges.to_file(gpkg_path, layer="edges", driver="GPKG")
nodes.to_file(gpkg_path, layer="nodes", driver="GPKG")

print(f"\n저장 완료:")
print(f"  GraphML: {graphml_path}")
print(f"  GeoPackage: {gpkg_path}")

# 기본 통계
print(f"\n엣지 길이 통계 (미터):")
print(edges["length"].describe().round(1))
