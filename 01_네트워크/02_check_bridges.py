"""
한강 대교 링크 확인
- 응봉역 → 뚝섬유원지 경로상의 대교(bridge) 엣지 식별
- 이 링크들이 폭염 시간대 PPA 분석의 핵심 케이스
"""

import osmnx as ox
import geopandas as gpd
import pandas as pd

# 저장된 네트워크 로드
G = ox.load_graphml("seongdong_walk_network.graphml")
nodes, edges = ox.graph_to_gdfs(G)

print("=== 대교(bridge) 엣지 현황 ===")
bridges = edges[edges["bridge"].notna()]
print(f"bridge 속성 있는 엣지 수: {len(bridges)}")
print(bridges[["name", "bridge", "length", "highway"]].drop_duplicates("name").to_string())

print("\n=== highway 타입 분포 ===")
print(edges["highway"].value_counts().head(15))

print("\n=== 도로명 상위 20개 ===")
print(edges["name"].value_counts().head(20))

# 성수대교, 영동대교 확인
for keyword in ["성수", "영동", "한강", "살곶이", "bridge"]:
    matched = edges[edges["name"].fillna("").str.contains(keyword, na=False)]
    if len(matched) > 0:
        print(f"\n['{keyword}' 포함 엣지]")
        print(matched[["name", "length", "highway", "bridge"]].drop_duplicates("name"))
