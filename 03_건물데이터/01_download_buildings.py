"""
성동구 건물 데이터 수집 (OSM 기반)
- 건물 footprint + 높이 정보 (그늘 계산용)
"""

import osmnx as ox
import geopandas as gpd
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
PLACE = "성동구, 서울특별시, 대한민국"

print("건물 데이터 다운로드...")
tags = {"building": True}
buildings = ox.features_from_place(PLACE, tags=tags)

# 건물만 필터 (Polygon/MultiPolygon)
buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
buildings = buildings.reset_index()

print(f"  건물 수: {len(buildings):,}")

# 높이 정보 확인
height_cols = [c for c in buildings.columns if "height" in c.lower() or c == "building:levels"]
print(f"  높이 관련 컬럼: {height_cols}")
for col in height_cols:
    filled = buildings[col].notna().sum()
    print(f"    {col}: {filled}개 ({filled/len(buildings)*100:.1f}%) 값 있음")

# 저장
out_path = os.path.join(OUTPUT_DIR, "seongdong_buildings.gpkg")
save_cols = ["geometry", "building", "name"] + height_cols
save_cols = [c for c in save_cols if c in buildings.columns]
buildings[save_cols].to_file(out_path, driver="GPKG")
print(f"\n저장 완료: {out_path}")
