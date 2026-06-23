# src/viz/maps.py
"""
Interactive Folium map for the static site generator.
  build_map(canton_id, wms_time) -> folium.Map

Data sources:
  - Background relief:  ch.swisstopo.swissalti3d-reliefschattierung  (WMS)
  - Drought index:      ch.bafu.trockenheitsindex                     (WMS)
  - Canton polygon:     ch.swisstopo.swissboundaries3d-kanton-flaeche.fill
                        fetched via identify endpoint (EPSG:2056)

Opacity design (Folium approximation — Leaflet cannot clip WMS tiles):
  Layer A: drought at OPACITY_OUTSIDE everywhere
  Layer B: drought at (OPACITY_INSIDE – OPACITY_OUTSIDE) everywhere
  Mask:    world minus canton polygon as black GeoJSON at same delta opacity
           → cancels Layer B outside the canton
  Net:  inside  = A + B = OPACITY_INSIDE
        outside = A     = OPACITY_OUTSIDE
"""
from __future__ import annotations

import folium
import geopandas as gpd
import requests
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

from config.settings import CANTON_CENTER_POINTS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWISSTOPO_WMS = "https://wms.geo.admin.ch/"

# Verified layer names from WMS GetCapabilities / opendata.swiss
LAYER_RELIEF  = "ch.swisstopo.swissalti3d-reliefschattierung"
LAYER_DROUGHT = "ch.bafu.trockenheitsindex"

# Canton boundary: identify endpoint uses this layer
LAYER_CANTONS = "ch.swisstopo.swissboundaries3d-kanton-flaeche.fill"

CANTON_IDENTIFY_DEFAULT = (2614322, 1185492)  # central Bern LV95 – fallback only

CANTON_BUFFER_M = 5_000   # metres – zoom bbox buffer only, polygon is exact

OPACITY_INSIDE  = 0.65   # drought opacity inside canton (relief shines through)
OPACITY_OUTSIDE = 0.25   # drought opacity outside canton (faded context)

_to_wgs84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
_to_lv95  = Transformer.from_crs("EPSG:4326",  "EPSG:2056", always_xy=True)


# ---------------------------------------------------------------------------
# Canton geometry via identify endpoint
# ---------------------------------------------------------------------------

def _fetch_canton_geometry(canton_id: int = 2) -> tuple[gpd.GeoDataFrame, list[float]]:
    """
    Use the geo.admin.ch identify endpoint with a point inside the canton.
    This is the documented reliable way to get a canton polygon.

    Returns
    -------
    gdf    : GeoDataFrame (EPSG:4326) – actual canton polygon
    bounds : [lon_min, lat_min, lon_max, lat_max] – buffered bbox for zoom
    """
    px, py = CANTON_CENTER_POINTS.get(canton_id, CANTON_IDENTIFY_DEFAULT)
    geom = None

    try:
        # identify with a point (LV95) and a generous map extent covering all of CH
        url = (
            "https://api3.geo.admin.ch/rest/services/all/MapServer/identify"
            f"?geometryType=esriGeometryPoint"
            f"&geometry={px},{py}"
            f"&imageDisplay=1920,1080,96"
            f"&mapExtent=2420000,1030000,2900000,1350000"
            f"&tolerance=0"
            f"&layers=all:{LAYER_CANTONS}"
            f"&geometryFormat=geojson"
            f"&returnGeometry=true"
            f"&sr=2056"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])

        # Filter to the requested canton by kantonsnum attribute
        for res in results:
            attrs = res.get("attributes", {})
            if str(attrs.get("kantonsnum", "")) == str(canton_id):
                raw = res.get("geometry")
                if raw:
                    geom = shape(raw)
                break

        # Fallback: take first result if attribute match failed
        if geom is None and results:
            raw = results[0].get("geometry")
            if raw:
                geom = shape(raw)
                print(f"[maps] Took first identify result (no kantonsnum={canton_id} match)")

    except Exception as exc:
        print(f"[maps] identify call failed: {exc}")

    if geom is None:
        print("[maps] Falling back to hardcoded Bern polygon bbox")
        geom = box(6.86, 46.32, 8.40, 47.32)

    # The identify endpoint returns LV95 – reproject to WGS84
    gdf_lv95 = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:2056")
    gdf = gdf_lv95.to_crs("EPSG:4326")

    # Buffered bbox for zoom (polygon boundary is not buffered)
    minx, miny, maxx, maxy = gdf_lv95.geometry.iloc[0].bounds
    buf = CANTON_BUFFER_M
    lon_min, lat_min = _to_wgs84.transform(minx - buf, miny - buf)
    lon_max, lat_max = _to_wgs84.transform(maxx + buf, maxy + buf)

    return gdf, [lon_min, lat_min, lon_max, lat_max]


# ---------------------------------------------------------------------------
# Interactive map (folium)
# ---------------------------------------------------------------------------

def build_map(canton_id: int = 2, wms_time: str = "1") -> folium.Map:
    """
    Layer stack (bottom → top):
      1. Relief shading          – opaque WMS base layer
      2. Drought index Layer A   – full extent, OPACITY_OUTSIDE
      3. Drought index Layer B   – full extent, delta opacity
      4. Outside mask            – world minus canton polygon, cancels Layer B outside
      5. Canton border           – actual polygon boundary, no fill
    """
    canton_gdf, bounds = _fetch_canton_geometry(canton_id)
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles=None)
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    # ── 1. Relief shading – opaque base ──────────────────────────────────────
    folium.WmsTileLayer(
        url=SWISSTOPO_WMS,
        layers=LAYER_RELIEF,
        fmt="image/png",
        transparent=False,
        version="1.3.0",
        attr="© swisstopo",
        name="Reliefschattierung",
        overlay=False,
    ).add_to(m)

    delta_opacity = max(0.0, OPACITY_INSIDE - OPACITY_OUTSIDE)
    drought_url = f"{SWISSTOPO_WMS}?time={wms_time}"

    # ── 2. Drought index Layer A – full extent at OPACITY_OUTSIDE ────────────
    folium.WmsTileLayer(
        url=drought_url,
        layers=LAYER_DROUGHT,
        fmt="image/png",
        transparent=True,
        version="1.3.0",
        attr="© BAFU / swisstopo",
        name="Trockenheitsindex (Basis)",
        overlay=True,
        opacity=OPACITY_OUTSIDE,
    ).add_to(m)

    # ── 3. Drought index Layer B – full extent at delta opacity ──────────────
    folium.WmsTileLayer(
        url=drought_url,
        layers=LAYER_DROUGHT,
        fmt="image/png",
        transparent=True,
        version="1.3.0",
        attr="© BAFU / swisstopo",
        name="Trockenheitsindex (innen)",
        overlay=True,
        opacity=delta_opacity,
        show=True,
    ).add_to(m)

    # ── 4. Outside mask – cancels Layer B beyond the canton border ────────────
    # Build inverted polygon: large bbox minus the actual canton shape
    world = box(-180, -90, 180, 90)
    canton_geom_wgs84 = canton_gdf.geometry.iloc[0]
    outside_geom = world.difference(canton_geom_wgs84)

    folium.GeoJson(
        mapping(outside_geom),
        style_function=lambda _: {
            "fillColor": "#000000",
            "fillOpacity": delta_opacity,
            "color": "none",
            "weight": 0,
        },
        name="Aussenmaske",
        show=True,
        overlay=True,
    ).add_to(m)

    # ── 5. Canton border – actual polygon, no fill ────────────────────────────
    folium.GeoJson(
        canton_gdf.__geo_interface__,
        style_function=lambda _: {
            "fillColor": "none",
            "fillOpacity": 0,
            "color": "#e8a020",
            "weight": 2.5,
            "opacity": 1.0,
            "dashArray": "6 3",
        },
        tooltip=f"Kanton (BFS-Nr. {canton_id})",
        name="Kantonsgrenze",
    ).add_to(m)

    return m