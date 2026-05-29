# src/viz/maps.py
"""
Two map renderers:
  build_map()        -> interactive folium.Map for Streamlit (st_folium)
  build_export_map() -> static PNG bytes via matplotlib/geopandas (for PDF export)

Data sources:
  - Background relief:  ch.swisstopo.swissalti3d-reliefschattierung  (WMS)
  - Drought index:      ch.bafu.trockenheitsindex                     (WMS, time=1)
  - Canton polygon:     ch.swisstopo.swissboundaries3d-kanton-flaeche.fill
                        fetched via identify endpoint (point-in-polygon, EPSG:2056)

Opacity design
--------------
Relief always shines through.
  Inside canton polygon:  OPACITY_INSIDE  (more prominent)
  Outside canton polygon: OPACITY_OUTSIDE (faded context)

Folium approximation (Leaflet cannot clip WMS tiles):
  Layer A: drought at OPACITY_OUTSIDE  everywhere
  Layer B: drought at (OPACITY_INSIDE – OPACITY_OUTSIDE)  everywhere
  Mask:    world.difference(canton) as black GeoJSON at same delta opacity
           → cancels Layer B outside the canton
  Net:  inside  = A + B = OPACITY_INSIDE
        outside = A     = OPACITY_OUTSIDE
"""
from __future__ import annotations

import io
from typing import Optional

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import requests
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

from config.settings import CDI_COLOURS
from src.models import CantonReport, MapSpec, RegionReport

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWISSTOPO_WMS = "https://wms.geo.admin.ch/"

# Verified layer names from WMS GetCapabilities / opendata.swiss
LAYER_RELIEF  = "ch.swisstopo.swissalti3d-reliefschattierung"
LAYER_DROUGHT = "ch.bafu.trockenheitsindex"
DROUGHT_TIME  = "1"   # time=1 → current situation

# Canton boundary: identify endpoint uses this layer
LAYER_CANTONS = "ch.swisstopo.swissboundaries3d-kanton-flaeche.fill"

# A point guaranteed to be inside canton Bern (LV95 / EPSG:2056)
# Used for the identify call – change if targeting a different canton
CANTON_IDENTIFY_POINTS = {
    2: (2600000, 1200000),   # Bern – Belpberg area
}
CANTON_IDENTIFY_DEFAULT = (2600000, 1200000)

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
    px, py = CANTON_IDENTIFY_POINTS.get(canton_id, CANTON_IDENTIFY_DEFAULT)
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


def _lv95_bbox(lon_min, lat_min, lon_max, lat_max):
    x_min, y_min = _to_lv95.transform(lon_min, lat_min)
    x_max, y_max = _to_lv95.transform(lon_max, lat_max)
    return x_min, y_min, x_max, y_max


# ---------------------------------------------------------------------------
# Interactive map (folium)
# ---------------------------------------------------------------------------

def build_map(
    selected_report: Optional[RegionReport] = None,
    all_reports: Optional[list[RegionReport]] = None,
    canton_id: int = 2,
) -> folium.Map:
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

    # ── 2. Drought index Layer A – full extent at OPACITY_OUTSIDE ────────────
    folium.WmsTileLayer(
        url=SWISSTOPO_WMS,
        layers=LAYER_DROUGHT,
        fmt="image/png",
        transparent=True,
        version="1.3.0",
        attr="© BAFU / swisstopo",
        name="Trockenheitsindex (Basis)",
        overlay=True,
        opacity=OPACITY_OUTSIDE,
        extra_params={"time": DROUGHT_TIME},
    ).add_to(m)

    # ── 3. Drought index Layer B – full extent at delta opacity ──────────────
    folium.WmsTileLayer(
        url=SWISSTOPO_WMS,
        layers=LAYER_DROUGHT,
        fmt="image/png",
        transparent=True,
        version="1.3.0",
        attr="© BAFU / swisstopo",
        name="Trockenheitsindex (innen)",
        overlay=True,
        opacity=delta_opacity,
        extra_params={"time": DROUGHT_TIME},
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


def build_canton_map(canton: CantonReport, map_spec: MapSpec) -> folium.Map:
    """Render an interactive folium map for the given CantonReport and MapSpec."""
    return build_map(canton_id=canton.canton_id)


# ---------------------------------------------------------------------------
# Static export map (matplotlib + WMS GetMap)
# ---------------------------------------------------------------------------

def build_export_map(
    selected_report: Optional[RegionReport] = None,
    all_reports: Optional[list[RegionReport]] = None,
    canton_id: int = 2,
) -> bytes:
    """
    Static PNG for PDF export.
    Pixel-level alpha: OPACITY_INSIDE inside canton, OPACITY_OUTSIDE outside.
    """
    canton_gdf, bounds_wgs84 = _fetch_canton_geometry(canton_id)
    canton_gdf_lv95 = canton_gdf.to_crs("EPSG:2056")

    lon_min, lat_min, lon_max, lat_max = bounds_wgs84
    x_min, y_min, x_max, y_max = _lv95_bbox(lon_min, lat_min, lon_max, lat_max)
    bbox_lv95 = f"{x_min},{y_min},{x_max},{y_max}"
    img_w, img_h = 1200, 900
    extent = [x_min, x_max, y_min, y_max]

    def _get_wms(layer: str, time: str | None = None) -> np.ndarray | None:
        url = (
            f"{SWISSTOPO_WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
            f"&LAYERS={layer}&STYLES=default"
            f"&CRS=EPSG:2056&BBOX={bbox_lv95}"
            f"&WIDTH={img_w}&HEIGHT={img_h}"
            f"&FORMAT=image/png&TRANSPARENT=TRUE"
        )
        if time is not None:
            url += f"&time={time}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            from PIL import Image
            return np.array(Image.open(io.BytesIO(r.content)).convert("RGBA"))
        except Exception as exc:
            print(f"[maps] WMS GetMap failed for {layer}: {exc}")
            return None

    relief_arr  = _get_wms(LAYER_RELIEF)
    drought_arr = _get_wms(LAYER_DROUGHT, time=DROUGHT_TIME)

    fig, ax = plt.subplots(figsize=(12, 9), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    ax.set_aspect("equal")

    # ── Relief background ─────────────────────────────────────────────────────
    if relief_arr is not None:
        ax.imshow(relief_arr, extent=extent, origin="upper", zorder=1)

    if drought_arr is not None:
        # Build a per-pixel inside-canton boolean mask
        from matplotlib.path import Path as MplPath

        canton_geom = canton_gdf_lv95.geometry.iloc[0]

        def _to_mpl_path(geom) -> MplPath:
            polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            verts, codes = [], []
            for poly in polys:
                for ring in [poly.exterior] + list(poly.interiors):
                    xy = np.array(ring.coords)
                    verts.append(xy)
                    codes += ([MplPath.MOVETO]
                               + [MplPath.LINETO] * (len(xy) - 2)
                               + [MplPath.CLOSEPOLY])
            return MplPath(np.concatenate(verts), np.array(codes))

        mpl_path = _to_mpl_path(canton_geom)

        xs = np.linspace(x_min, x_max, img_w)
        ys = np.linspace(y_max, y_min, img_h)   # origin="upper" → decreasing y
        grid_x, grid_y = np.meshgrid(xs, ys)
        pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])
        inside_mask = mpl_path.contains_points(pts).reshape(img_h, img_w)

        drought_float = drought_arr.astype(float)
        alpha = drought_float[..., 3].copy()
        alpha[inside_mask]  *= OPACITY_INSIDE
        alpha[~inside_mask] *= OPACITY_OUTSIDE
        drought_float[..., 3] = alpha
        ax.imshow(drought_float.astype(np.uint8), extent=extent, origin="upper", zorder=2)

    # ── Canton border ─────────────────────────────────────────────────────────
    canton_gdf_lv95.boundary.plot(
        ax=ax, color="#e8a020", linewidth=2.0, linestyle="--", zorder=5,
    )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_axis_off()
    ax.set_title("Trockenheitsindex – Kanton Bern", color="white", fontsize=11, pad=8)
    plt.tight_layout(pad=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    buf.seek(0)
    return buf.read()