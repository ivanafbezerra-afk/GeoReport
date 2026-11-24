# -*- coding: utf-8 -*-
"""GeoReport | Automatic territorial diagnostics. Run main.py in Spyder (F5)."""

from pathlib import Path
from contextlib import contextmanager
import math

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter
from rasterio.mask import mask
from rasterio.features import geometry_mask, geometry_window
from rasterio.windows import Window
from rasterio.transform import Affine
from rasterio.transform import array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from shapely.geometry import box
from earth_engine_mapbiomas import download_mapbiomas_raster, PendingDriveExport
from earth_engine_config import EARTH_ENGINE_PROJECT
from technical_report import generate_technical_report


# ============================================================
# 1. MAPBIOMAS CONFIGURATION AND CLASSIFICATION
# ============================================================

ANALYSIS_YEAR = 2025
DEFAULT_RASTER_FILE = "mapbiomas_df_utm.tif"

# Class codes and colors for the MapBiomas land-cover legend.
MAPBIOMAS_COLORS = {
    3: "#1f8d49", 4: "#7dc975", 9: "#7a5900",
    11: "#519799", 12: "#d6bc74", 15: "#edde8e",
    19: "#C27BA0", 21: "#ffefc3", 24: "#d4271e",
    25: "#db4d4f", 30: "#9c0027", 31: "#091077",
    33: "#2532e4", 36: "#d082de",
    5: "#04381d", 6: "#007785", 7: "#228c70",
    23: "#ffa07a", 29: "#ad5100", 32: "#fc8114",
    49: "#02d659", 50: "#ffaa5f", 75: "#757272",
    77: "#86b074", 84: "#81dbbf", 91: "#403d3e",
}







MAPBIOMAS_CLASS_NAMES = {
    3: "Forest formation", 4: "Savanna formation", 9: "Forest plantation",
    11: "Wetland", 12: "Grassland", 15: "Pasture",
    19: "Temporary cropland", 21: "Mosaic of uses",
    24: "Urban area", 25: "Other non-vegetated areas",
    30: "Mining", 31: "Aquaculture", 33: "River, lake and ocean",
    36: "Perennial cropland", 5: "Mangrove", 6: "Flooded forest",
    7: "Flooded savanna", 23: "Beach, dune and sand",
    29: "Rocky outcrop", 32: "Salt flat", 49: "Wooded restinga",
    50: "Herbaceous/shrubby restinga", 75: "Solar power plant",
    77: "Herbaceous-shrub formation", 84: "Salt marsh", 91: "Wind farm",
}

MAP_LABELS = {'title': 'GEOREPORT | TERRITORIAL DIAGNOSTICS',
 'theme': 'Land use and land cover',
 'easting': 'Easting (m)',
 'northing': 'Northing (m)',
 'land_cover_legend': 'LEGEND | LAND USE AND LAND COVER',
 'legend': 'LEGEND',
 'study_area_boundary': 'Study area boundary',
 'location': 'STUDY AREA LOCATION',
 'missing_state_boundaries': 'State boundaries unavailable',
 'territorial_info': 'TERRITORIAL INFORMATION',
 'total_area': 'Total area',
 'classes_identified': 'Classes identified',
 'vector_features': 'Vector features',
 'main_classes': 'MAIN CLASSES',
 'indicators': 'INDICATORS',
 'perimeter': 'Perimeter',
 'north': 'NORTH',
 'scale_bar': 'SCALE BAR',
 'sources': 'SOURCES AND METHODS',
 'boundaries': 'Boundaries',
 'land_cover': 'Land cover',
 'prepared_by': 'Prepared by'}



def map_label(key, language="en"):
    'Return an English map label.'
    return MAP_LABELS[key]



def land_cover_class_name(class_code, language="en"):
    'Look up the English MapBiomas land-cover class name.'
    return MAPBIOMAS_CLASS_NAMES.get(int(class_code), f"Class {class_code}")



def format_map_number(value, decimals=2, language="en"):
    'Format map values using English thousands and decimal separators.'
    return f"{float(value):,.{decimals}f}"



def format_scale_label(value, language="en"):
    'Format scale labels using English decimal points.'
    return f"{value:g}"




# ============================================================
# 2. VECTOR INPUT, VALIDATION AND PROCESSING
# ============================================================

def load_vector_data(caminho):
    """Load a vector file and return its GeoDataFrame."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"Vector file not found: {caminho}")
    gdf = gpd.read_file(caminho)
    print(f"\nFile loaded: {caminho.name}")
    return gdf


def inspect_vector_data(gdf):
    """Print a concise inspection of input features, attributes and CRS."""
    print("\n--- DATA INSPECTION ---")
    print("Features:", len(gdf))
    print("Columns:", list(gdf.columns))
    print("CRS:", gdf.crs)
    print("Geometry types:", gdf.geom_type.unique())
    print("Bounds:", gdf.total_bounds)


def validate_vector_data(gdf):
    """Check CRS, nonempty polygon geometries and topological validity."""
    print("\n--- AUTOMATIC VALIDATION ---")

    if gdf.empty or gdf.crs is None:
        print("FAILED: dataset is empty or has no defined CRS.")
        return False

    ausentes = int(gdf.geometry.isna().sum())
    vazias = int(gdf.geometry.is_empty.sum())
    invalidas = int((~gdf.geometry.is_valid).sum())
    poligonos = bool(gdf.geom_type.isin(["Polygon", "MultiPolygon"]).all())

    print("Missing geometries:", ausentes)
    print("Empty geometries:", vazias)
    print("Invalid geometries:", invalidas)
    print("Polygons only:", poligonos)

    aprovado = (ausentes == 0 and vazias == 0 and invalidas == 0
                and poligonos)
    print("Validation:", "PASSED" if aprovado else "FAILED")
    return aprovado


def reproject_vector_data(gdf):
    """Estimate a UTM CRS for local analyses and reproject polygons."""
    crs_estimado = gdf.estimate_utm_crs()
    if crs_estimado is None:
        raise ValueError("Could not estimate a suitable UTM CRS.")

    projetado = gdf.to_crs(crs_estimado)
    print("\nOriginal CRS:", gdf.crs)
    print("Projected CRS:", projetado.crs)
    return projetado


def compare_areas(original, projetado):
    """Compare computed area with an optional reference-area attribute."""
    area_calculada = projetado.geometry.union_all().area / 1_000_000
    print(f"\nVector area: {area_calculada:.4f} km²")

    if "AREA_KM2" in original.columns and len(original) == 1:
        referencia = pd.to_numeric(original["AREA_KM2"], errors="coerce").iloc[0]
        if pd.notna(referencia) and referencia > 0:
            diferenca = abs(area_calculada - referencia)
            print(f"Reference area: {referencia:.2f} km²")
            print(f"Difference: {diferenca:.2f} km² "
                  f"({100 * diferenca / referencia:.4f}%)")

    return area_calculada


def export_vector_data(gdf, output_dir):
    """Save validated polygon features to GeoPackage."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / "processed_study_area.gpkg"
    gdf.to_file(file_path, layer="area_estudo", driver="GPKG")
    print("GeoPackage saved:", file_path)
    return file_path


def select_vector_file():
    """Open a desktop file dialog to select a polygon dataset."""
    from tkinter import Tk, filedialog

    janela = Tk()
    janela.withdraw()
    janela.attributes("-topmost", True)
    try:
        file_path = filedialog.askopenfilename(
            title="Select the study area",
            filetypes=[
                ("Geospatial files", "*.shp *.gpkg *.geojson"),
                ("Shapefile", "*.shp"),
                ("GeoPackage", "*.gpkg"),
                ("GeoJSON", "*.geojson"),
            ],
        )
    finally:
        janela.destroy()

    if not file_path:
        print("No file selected.")
        return None
    return Path(file_path)


# ============================================================
# 3. RASTER SELECTION - ANY LOCATION IN BRAZIL
# ============================================================

def raster_covers_area(raster_path, gdf):
    """Check whether raster bounds fully contain the study geometry."""
    try:
        with rasterio.open(raster_path) as src:
            if src.crs is None or src.count != 1:
                return False
            geometria = gdf.to_crs(src.crs).geometry.union_all()
            # Allow a tiny tolerance for floating-point bounds comparisons.
            extensao = box(*src.bounds)
            largura = src.bounds.right - src.bounds.left
            tolerancia = abs(largura) * 1e-9
            return extensao.buffer(tolerancia).covers(geometria)
    except (OSError, ValueError, rasterio.errors.RasterioError):
        return False


def locate_raster_for_area(project_dir, area):
    """Find a suitable local GeoTIFF or request a manual selection."""
    pastas = [
        project_dir / "data" / "rasters",
        project_dir / "data" / "processed",
    ]
    candidatos = []
    for folder in pastas:
        if folder.is_dir():
            candidatos.extend(folder.glob("*.tif"))
            candidatos.extend(folder.glob("*.tiff"))

    # Do not confuse previous study-area clips with source rasters.
    candidatos = [
        p for p in set(candidatos)
        if "clipped" not in p.stem.lower()
        and "clipped_land_cover" not in p.stem.lower()
    ]
    # Prefer the smallest suitable raster that covers the geometry.
    possiveis = []
    for file_path in candidatos:
        if raster_covers_area(file_path, area):
            with rasterio.open(file_path) as src:
                tamanho = (src.bounds.right - src.bounds.left) * (
                    src.bounds.top - src.bounds.bottom
                )
            possiveis.append((tamanho, file_path))

    if possiveis:
        selecionado = min(possiveis, key=lambda a: a[0])[1]
        print("Raster automatically selected:", selecionado)
        return selecionado

    print("\nNo local raster fully covers the selected study area.")
    print("Download a MapBiomas 10 m / Collection 4 / 2025 extract")
    print("for the region and select the GeoTIFF in the next window.")
    from tkinter import Tk, filedialog
    janela = Tk()
    janela.withdraw()
    janela.attributes("-topmost", True)
    try:
        escolhido = filedialog.askopenfilename(
            title="Select a MapBiomas raster that covers the study area",
            filetypes=[("Raster GeoTIFF", "*.tif *.tiff")],
        )
    finally:
        janela.destroy()
    if not escolhido:
        raise FileNotFoundError(
            "Analysis canceled: no MapBiomas raster is available for this area."
        )
    escolhido = Path(escolhido)
    if not raster_covers_area(escolhido, area):
        raise ValueError(
            "The selected raster does not fully cover the area. "
            "Export a GeoTIFF covering a larger extent from Earth Engine."
        )
    print("Raster selected:", escolhido)
    return escolhido


def select_raster_or_earth_engine(project_dir, area, output_dir):
    """Prefer a local raster; otherwise request data from Earth Engine."""
    pastas = [
        project_dir / "data" / "rasters",
        project_dir / "data" / "processed",
        Path(output_dir),
    ]
    candidatos = []
    for folder in pastas:
        if folder.is_dir():
            candidatos.extend(folder.glob("*.tif"))
            candidatos.extend(folder.glob("*.tiff"))
    candidatos = [
        p for p in set(candidatos)
        if "clipped" not in p.stem.lower()
    ]
    possiveis = [p for p in candidatos if raster_covers_area(p, area)]
    if possiveis:
        escolhido = min(possiveis, key=lambda p: p.stat().st_size)
        print("Using local raster:", escolhido)
        return escolhido

    if EARTH_ENGINE_PROJECT == "YOUR_EARTH_ENGINE_PROJECT_ID":
        print("\nEarth Engine project is not configured; using manual raster selection.")
        return locate_raster_for_area(project_dir, area)

    return download_mapbiomas_raster(
        area=area,
        output_dir=project_dir / "data" / "rasters" / "earth_engine_cache" / str(ANALYSIS_YEAR),
        earth_engine_project=EARTH_ENGINE_PROJECT,
        year=ANALYSIS_YEAR,
    )


@contextmanager
def open_metric_raster(raster_path, crs_destino):
    """Open a categorical raster in a projected CRS with metre units."""
    with rasterio.open(raster_path) as src:
        if src.crs is None or src.count != 1:
            raise ValueError("Raster must have a valid CRS and one classification band.")
        if (src.crs.is_projected and
                src.crs.linear_units.lower() in
                {"metre", "meter", "metres", "meters"}):
            yield src
        else:
            # Virtual reprojection reads only the raster window needed for the clip.
            with WarpedVRT(
                src, crs=crs_destino,
                resampling=Resampling.nearest,
                src_nodata=src.nodata if src.nodata is not None else 0,
                nodata=0,
            ) as vrt:
                yield vrt


# ============================================================
# 3. RASTER ANALYSIS AND CLASS STATISTICS
# ============================================================

def validate_metric_raster(src):
    """Ensure that raster pixels can be measured in square metres."""
    if src.crs is None or not src.crs.is_projected:
        raise ValueError("The raster must use a projected CRS in metres.")
    if src.count != 1:
        raise ValueError("The thematic raster must contain exactly one band.")
    if src.crs.linear_units.lower() not in {"metre", "meter", "metres", "meters"}:
        raise ValueError("The raster linear unit must be metres.")


def analyze_land_cover(gdf, raster_path, output_dir):
    """Clip raster by polygon in windows and calculate class statistics."""
    print("\n--- AUTOMATED LAND-COVER ANALYSIS ---")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raster_path = Path(raster_path)
    if not raster_path.is_file():
        raise FileNotFoundError(f"Source raster not found: {raster_path}")

    tif_path = output_dir / "clipped_land_cover.tif"
    # Limit each processing window to roughly one million pixels.
    janela_maxima = 1024
    totais = np.zeros(256, dtype=np.int64)

    with open_metric_raster(raster_path, gdf.crs) as src:
        validate_metric_raster(src)
        area_raster = gdf.to_crs(src.crs)
        geometria = area_raster.geometry.union_all()
        formas = [geometria.__geo_interface__]
        try:
            janela_area = geometry_window(src, formas)
        except (ValueError, rasterio.errors.WindowError) as erro:
            raise ValueError("The selected area does not intersect the raster footprint.") from erro

        largura = int(janela_area.width)
        altura = int(janela_area.height)
        if largura <= 0 or altura <= 0:
            raise ValueError("Empty raster extent.")

        transformacao = src.window_transform(janela_area)
        area_pixel_m2 = abs(
            transformacao.a * transformacao.e
            - transformacao.b * transformacao.d
        )
        area_vetorial = geometria.area / 1_000_000
        perfil = src.profile.copy()
        perfil.update(
            driver="GTiff", height=altura, width=largura,
            count=1, transform=transformacao, nodata=0,
            compress="deflate", tiled=True, blockxsize=256,
            blockysize=256, BIGTIFF="IF_SAFER",
        )
        print(f"Processing raster in blocks of up to {janela_maxima} pixels...")
        print(f"Output raster dimensions: {largura:,} x {altura:,} pixels")

        parcial = tif_path.with_name("clipped_land_cover.partial.tif")
        try:
            with rasterio.open(parcial, "w", **perfil) as destino:
                for row in range(0, altura, janela_maxima):
                    for coluna in range(0, largura, janela_maxima):
                        h = min(janela_maxima, altura - row)
                        w = min(janela_maxima, largura - coluna)
                        janela_origem = Window(
                            int(janela_area.col_off) + coluna,
                            int(janela_area.row_off) + row,
                            w, h
                        )
                        janela_destino = Window(coluna, row, w, h)
                        bloco = src.read(1, window=janela_origem, masked=True)
                        dentro = geometry_mask(
                            formas, out_shape=(h, w),
                            transform=src.window_transform(janela_origem),
                            invert=True, all_touched=False
                        )
                        valido = (
                            dentro & ~np.ma.getmaskarray(bloco)
                            & (bloco.data != 0)
                        )
                        if valido.any():
                            classes, contagens = np.unique(
                                bloco.data[valido], return_counts=True
                            )
                            if int(max(classes)) > 255:
                                raise ValueError("Classification values exceed the expected 0–255 code range.")
                            totais[classes.astype(int)] += contagens
                        resultado = np.where(valido, bloco.data, 0)
                        destino.write(
                            resultado.astype(src.dtypes[0]),
                            1, window=janela_destino
                        )
            parcial.replace(tif_path)
        except Exception:
            parcial.unlink(missing_ok=True)
            raise

    classes = np.flatnonzero(totais)
    desconhecidas = set(map(int, classes)) - set(MAPBIOMAS_COLORS)
    if desconhecidas:
        raise ValueError(f"MapBiomas class codes without legend: {sorted(desconhecidas)}")
    if len(classes) == 0:
        raise ValueError("No classified pixels found inside the area.")

    table = pd.DataFrame({
        "Class_ID": classes.astype(int),
        "Pixels": totais[classes],
    })
    table["Class"] = table["Class_ID"].map(MAPBIOMAS_CLASS_NAMES)
    table["Area_km2"] = table["Pixels"] * area_pixel_m2 / 1_000_000
    table["Percentage"] = table["Area_km2"] / table["Area_km2"].sum() * 100
    table = table.sort_values("Area_km2", ascending=False)
    csv_path = output_dir / "land_cover_statistics.csv"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")

    classificada = table["Area_km2"].sum()
    cobertura = classificada / area_vetorial * 100
    print(table.to_string(index=False))
    print(f"\nVector area: {area_vetorial:,.4f} km²")
    print(f"Classified area: {classificada:,.4f} km²")
    print(f"Classified-to-vector area ratio: {cobertura:.2f}%")
    if cobertura < 90:
        raise ValueError(
            "Insufficient classified coverage ("
            f"{cobertura:.1f}%). Check whether the source raster covers the entire area."
        )
    if cobertura > 105:
        print("WARNING: large boundary or raster-resolution discrepancy.")
    print("Clipped raster:", tif_path)
    print("CSV table:", csv_path)
    return tif_path, csv_path, table


def prepare_thematic_raster(raster_path, gdf, max_dimensao=2400):
    """Build a lightweight, nearest-neighbour visualization raster."""
    with rasterio.open(raster_path) as src:
        validate_metric_raster(src)
        limite = gdf.to_crs(src.crs)
        geometrias = [limite.geometry.union_all().__geo_interface__]
        janela = geometry_window(src, geometrias)
        largura = int(janela.width)
        altura = int(janela.height)
        fator = min(1.0, max_dimensao / max(largura, altura))
        w = max(1, round(largura * fator))
        h = max(1, round(altura * fator))
        matriz = src.read(
            1, window=janela, out_shape=(h, w),
            masked=True, resampling=Resampling.nearest
        )
        transformacao = src.window_transform(janela) * Affine.scale(
            largura / w, altura / h
        )
        dentro = geometry_mask(
            geometrias, out_shape=(h, w),
            transform=transformacao, invert=True, all_touched=False
        )

    mascara = (~dentro) | np.ma.getmaskarray(matriz) | (matriz.data == 0)
    presentes = sorted(int(c) for c in np.unique(matriz.data[~mascara]))
    desconhecidas = set(presentes) - set(MAPBIOMAS_COLORS)
    if desconhecidas:
        raise ValueError(f"Classes without mapped colors: {sorted(desconhecidas)}")
    if not presentes:
        raise ValueError("The visualization contains no classified raster pixels.")

    codigos = sorted(MAPBIOMAS_COLORS)
    indices = np.full(matriz.shape, -1, dtype=np.int16)
    for indice, class_code in enumerate(codigos):
        indices[(matriz.data == class_code) & ~mascara] = indice
    indices = np.ma.masked_where(indices < 0, indices)
    paleta = ListedColormap([MAPBIOMAS_COLORS[c] for c in codigos])
    paleta.set_bad("white", alpha=0)
    norm = BoundaryNorm(np.arange(-0.5, len(codigos) + 0.5), paleta.N)
    oeste, sul, leste, norte = array_bounds(h, w, transformacao)
    print("Visualization pixels:", int(indices.count()))
    print("Map preview sample:", f"{w} x {h} (nearest).")
    return indices, paleta, norm, (oeste, leste, sul, norte), presentes


# Official Brazilian state abbreviations indexed by IBGE codes.
STATE_CODE_LOOKUP = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}

STATE_NAME_LOOKUP = {
    "RONDÔNIA": "RO", "ACRE": "AC", "AMAZONAS": "AM",
    "RORAIMA": "RR", "PARÁ": "PA", "AMAPÁ": "AP",
    "TOCANTINS": "TO", "MARANHÃO": "MA", "PIAUÍ": "PI",
    "CEARÁ": "CE", "RIO GRANDE DO NORTE": "RN", "PARAÍBA": "PB",
    "PERNAMBUCO": "PE", "ALAGOAS": "AL", "SERGIPE": "SE",
    "BAHIA": "BA", "MINAS GERAIS": "MG", "ESPÍRITO SANTO": "ES",
    "RIO DE JANEIRO": "RJ", "SÃO PAULO": "SP", "PARANÁ": "PR",
    "SANTA CATARINA": "SC", "RIO GRANDE DO SUL": "RS",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT",
    "GOIÁS": "GO", "DISTRITO FEDERAL": "DF",
}


def state_code_from_row(row):
    """Read the Brazilian state abbreviation from an IBGE record."""
    for coluna in ("SIGLA_UF", "SIGLA", "UF", "sigla_uf"):
        if coluna in row.index and pd.notna(row[coluna]):
            sigla = str(row[coluna]).strip().upper()
            if sigla in STATE_CODE_LOOKUP.values():
                return sigla
    if "CD_UF" in row.index and pd.notna(row["CD_UF"]):
        class_code = str(row["CD_UF"]).strip().split(".")[0]
        if class_code in STATE_CODE_LOOKUP:
            return STATE_CODE_LOOKUP[class_code]
    for coluna in ("NM_UF", "NOME", "nome", "name"):
        if coluna in row.index and pd.notna(row[coluna]):
            name = str(row[coluna]).strip().upper()
            if name in STATE_NAME_LOOKUP:
                return STATE_NAME_LOOKUP[name]
    return None


def identify_states(gdf, malha_ufs, min_percentual=0.1):
    """Identify all Brazilian states significantly intersecting an area."""
    if malha_ufs.crs is None:
        raise ValueError("The IBGE state boundaries do not have a defined CRS.")
    area_equal = gdf.to_crs("EPSG:6933").geometry.union_all()
    ufs_equal = malha_ufs.to_crs("EPSG:6933")
    total = area_equal.area
    if total <= 0:
        raise ValueError("The selected area does not have a valid extent.")

    encontradas = {}
    for (_, row), geom_uf in zip(malha_ufs.iterrows(), ufs_equal.geometry):
        sigla = state_code_from_row(row)
        if sigla is None or not geom_uf.intersects(area_equal):
            continue
        area_intersecao = geom_uf.intersection(area_equal).area
        percentual = 100 * area_intersecao / total
        if percentual >= min_percentual:
            encontradas[sigla] = encontradas.get(sigla, 0) + percentual

    if not encontradas:
        raise ValueError(
            "No significant overlap with a Brazilian state was found. "
            "Check the study geometry and the IBGE state boundaries."
        )
    return sorted(encontradas, key=encontradas.get, reverse=True)


def identify_state_codes(gdf, malha_ufs):
    """Return the abbreviations of states intersecting the area."""
    return " / ".join(identify_states(gdf, malha_ufs))


# ============================================================
# 4. CARTOGRAPHIC HELPERS
# ============================================================

def style_panel(ax, title, tamanho_titulo=10):
    """Style a fixed-position panel in the cartographic composition."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("#F7F8F7")
    for borda in ax.spines.values():
        borda.set_edgecolor("#A0A9A5")
        borda.set_linewidth(0.8)
    if title:
        ax.text(
            0.05, 0.92, title, transform=ax.transAxes,
            fontsize=tamanho_titulo, fontweight="bold",
            color="#234F43", va="top"
        )


def calculate_scale(distancia_maxima_m):
    """Choose an appropriately rounded scale-bar length in metres."""
    if distancia_maxima_m <= 0:
        raise ValueError("Invalid maximum scale-bar distance.")
    ordem = 10 ** math.floor(math.log10(distancia_maxima_m))
    normalizado = distancia_maxima_m / ordem
    fator = 5 if normalizado >= 5 else 2 if normalizado >= 2 else 1
    return fator * ordem


def draw_location_inset(ax_local, gdf, states_path, language="en"):
    """Draw Brazilian states and highlight the selected area."""
    style_panel(ax_local, map_label("location", language),
                     tamanho_titulo=11.4)
    if states_path is None:
        ax_local.text(0.5, 0.45, map_label("missing_state_boundaries", language),
                      ha="center", va="center", fontsize=9)
        return

    brasil = gpd.read_file(states_path)
    if brasil.crs is None:
        raise ValueError("The state boundaries do not have a defined CRS.")
    state_codes = identify_states(gdf, brasil)
    brasil = brasil.to_crs(4674)
    area_geografica = gdf.to_crs(4674)
    rotulo = " / ".join(state_codes)

    # Show all state boundaries and highlight intersected states.
    ax_br = ax_local.inset_axes([0.02, 0.02, 0.96, 0.81])
    brasil.plot(ax=ax_br, color="#AAAAAA", edgecolor="white", linewidth=0.45)
    filtro = brasil.apply(lambda row: state_code_from_row(row) in state_codes, axis=1)
    brasil.loc[filtro].plot(
        ax=ax_br, color="#E9A38E", edgecolor="white",
        linewidth=0.55, zorder=2
    )
    area_geografica.plot(ax=ax_br, color="#F26445", linewidth=0.6, zorder=3)

    ponto = area_geografica.geometry.union_all().representative_point()
    ax_br.scatter([ponto.x], [ponto.y], s=23, color="#DF4B30",
                  edgecolors="white", linewidths=0.7, zorder=5)
    ax_br.annotate(rotulo, xy=(ponto.x, ponto.y), xytext=(5, 3),
                   textcoords="offset points", fontsize=10,
                   fontweight="bold", color="#AF3D28", zorder=6)
    oeste, sul, leste, norte = brasil.total_bounds
    mx = (leste - oeste) * 0.035
    my = (norte - sul) * 0.035
    ax_br.set_xlim(oeste - mx, leste + mx)
    ax_br.set_ylim(sul - my, norte + my)
    ax_br.set_aspect("equal")
    ax_br.axis("off")


def draw_scale_bar(fig, ax_mapa, ax_escala, language="en"):
    """Draw a scale bar calibrated to the map coordinates."""
    style_panel(ax_escala, map_label("scale_bar", language), tamanho_titulo=10.6)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    largura_mapa = ax_mapa.get_window_extent(renderer).width
    largura_painel = ax_escala.get_window_extent(renderer).width
    largura_utm = ax_mapa.get_xlim()[1] - ax_mapa.get_xlim()[0]

    maxima = largura_utm * 0.54 * largura_painel / largura_mapa
    distancia = calculate_scale(maxima)
    fracao = distancia / largura_utm * largura_mapa / largura_painel
    x0, x1 = (1 - fracao) / 2, (1 + fracao) / 2
    xm = (x0 + x1) / 2

    for esquerda, color in [(x0, "black"), (xm, "white")]:
        ax_escala.add_patch(Rectangle(
            (esquerda, 0.34), fracao / 2, 0.12,
            transform=ax_escala.transAxes,
            facecolor=color, edgecolor="black", linewidth=1,
        ))

    total, unidade = (distancia / 1000, "km") if distancia >= 1000 \
        else (distancia, "m")
    # Small scale bars may not accommodate three labels without overlap.
    # Use endpoint labels only when space is limited.
    rotulos = [
        (x0, "0"),
        (x1, f"{format_scale_label(total, language)} {unidade}"),
    ]
    if fracao >= 0.54:
        rotulos.insert(1, (xm, format_scale_label(total / 2, language)))
    for x, rotulo in rotulos:
        ax_escala.text(x, 0.54, rotulo,
                       transform=ax_escala.transAxes,
                       ha="center", fontsize=9.7 if fracao < 0.54 else 10.5)


# ============================================================
# 5. THEMATIC MAP EXPORT TO PDF AND PNG
# ============================================================

def fit_area_to_fixed_frame(ax, gdf, fig, margem=0.065):
    """Fit the study area inside a fixed map frame without distortion."""
    xmin, ymin, xmax, ymax = gdf.total_bounds
    dx, dy = xmax - xmin, ymax - ymin
    if dx <= 0 or dy <= 0:
        raise ValueError("Invalid spatial extent (zero width or height).")

    # get_position(original=True) preserves the intended frame dimensions,
    # even when GeoPandas or imshow changes the axes aspect temporarily.
    pos = ax.get_position(original=True)
    largura_fisica = pos.width * fig.get_figwidth()
    altura_fisica = pos.height * fig.get_figheight()
    proporcao_quadro = largura_fisica / altura_fisica

    largura_dados = dx * (1 + 2 * margem)
    altura_dados = dy * (1 + 2 * margem)

    if largura_dados / altura_dados > proporcao_quadro:
        altura_dados = largura_dados / proporcao_quadro
    else:
        largura_dados = altura_dados * proporcao_quadro

    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2

    ax.set_xlim(cx - largura_dados / 2, cx + largura_dados / 2)
    ax.set_ylim(cy - altura_dados / 2, cy + altura_dados / 2)
    ax.set_aspect("equal", adjustable="box")
    ax.set_anchor("C")

    print(
        "Fixed map frame (figure):",
        f"x={pos.x0:.3f}, y={pos.y0:.3f},",
        f"width={pos.width:.3f}, height={pos.height:.3f}"
    )


def draw_panel_text(ax, x, y, text, tamanho=10.3, **kwargs):
    """Place a text label using panel-relative coordinates."""
    return ax.text(
        x, y, text, transform=ax.transAxes,
        fontsize=tamanho, va="center", **kwargs
    )


# ============================================================
# 5. FIXED MAP FRAME AND ENLARGED INFORMATION PANELS
# ============================================================

def generate_thematic_map(
    gdf, output_dir, area_name, north_arrow_path,
    states_path=None, raster_path=None,
    table_path=None, boundary_name=None, language="en"
):
    """Generate an English land-cover map in PNG and PDF."""
    print(f"\n--- CARTOGRAPHIC MAP ({language.upper()}) ---")
    map_label("title", language)  

    if not validate_vector_data(gdf):
        raise ValueError("Vector validation failed.")
    if not gdf.crs.is_projected:
        raise ValueError("The map requires a projected CRS in metres.")
    unidades = [e.unit_name.lower() for e in gdf.crs.axis_info]
    if not unidades or any(u not in {"metre", "meter", "metres", "meters"}
                           for u in unidades):
        raise ValueError("The map coordinate units must be metres.")

    north_arrow_path = Path(north_arrow_path)
    if not north_arrow_path.is_file():
        raise FileNotFoundError(f"North-arrow image not found: {north_arrow_path}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if boundary_name is None:
        boundary_name = area_name.split("|", 1)[0].strip()

    geometria = gdf.geometry.union_all()
    area_km2 = geometria.area / 1_000_000
    perimetro_km = geometria.length / 1_000

    table = None
    if table_path is not None:
        table = pd.read_csv(table_path)
        colunas = {"Class_ID", "Class", "Area_km2", "Percentage"}
        if not colunas.issubset(table.columns):
            raise ValueError("CSV is missing the expected columns.")
        table = table.sort_values("Area_km2", ascending=False)

    # --------------------------------------------------------
    # FIXED LAYOUT: all positions are expressed as page fractions.
    # Adjust only these values to change the overall composition.
    # --------------------------------------------------------
    fig = plt.figure(figsize=(16, 10), facecolor="white")

    try:
        # [left, bottom, width, height]
        # Keep the coordinate frame in the same position and size.
        ax_mapa = fig.add_axes([0.072, 0.285, 0.606, 0.520])
        ax_legenda = fig.add_axes([0.072, 0.075, 0.606, 0.157])

        # Align the enlarged information panels along the right margin.
        ax_local = fig.add_axes([0.705, 0.609, 0.265, 0.196])
        ax_info = fig.add_axes([0.705, 0.404, 0.265, 0.187])
        ax_norte = fig.add_axes([0.705, 0.251, 0.125, 0.135])
        ax_escala = fig.add_axes([0.845, 0.251, 0.125, 0.135])
        ax_fontes = fig.add_axes([0.705, 0.075, 0.265, 0.157])

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------
        fig.text(
            0.072, 0.955, map_label("title", language),
            fontsize=25, fontweight="bold", ha="left", va="top"
        )
        fig.text(
            0.072, 0.906, f"{boundary_name} | {map_label('theme', language)} - {ANALYSIS_YEAR}",
            fontsize=18, ha="left", va="top"
        )

        # ----------------------------------------------------
        # MAIN MAP
        # ----------------------------------------------------
        presentes = []
        if raster_path is not None:
            indices, paleta, norma, extensao, presentes = (
                prepare_thematic_raster(raster_path, gdf)
            )
            ax_mapa.imshow(
                indices, cmap=paleta, norm=norma,
                extent=extensao, interpolation="nearest", origin="upper"
            )
            gdf.boundary.plot(ax=ax_mapa, color="#21312C", linewidth=0.85)
        else:
            gdf.plot(
                ax=ax_mapa, facecolor="#A8D5BA",
                edgecolor="#235347", linewidth=1.4
            )

        # Fit the DATA within the FRAME before setting the map aspect.
        # Never use an automatic aspect ratio; this would distort the map.
        fit_area_to_fixed_frame(ax_mapa, gdf, fig, margem=0.065)
        ax_mapa.set_axisbelow(True)
        ax_mapa.grid(
            True, linestyle="-", color="#B0B7B4", linewidth=0.55,
            alpha=0.55
        )
        ax_mapa.set_xlabel(map_label("easting", language), fontsize=11, labelpad=7)
        ax_mapa.set_ylabel(map_label("northing", language), fontsize=11, labelpad=8)
        ax_mapa.xaxis.set_major_formatter(
            FuncFormatter(lambda x, _: format_map_number(x, 0, language))
        )
        ax_mapa.yaxis.set_major_formatter(
            FuncFormatter(lambda y, _: format_map_number(y, 0, language))
        )
        ax_mapa.tick_params(axis="both", labelsize=9.5, pad=5)
        ax_mapa.set_facecolor("white")
        for sp in ax_mapa.spines.values():
            sp.set_color("#58625E")
            sp.set_linewidth(0.9)

        # ----------------------------------------------------
        # LEGEND: title and class entries with dynamic spacing.
        # ----------------------------------------------------
        style_panel(ax_legenda, "")
        titulo_legenda = map_label(
            "land_cover_legend" if raster_path is not None else "legend", language
        )
        ax_legenda.text(
            0.5, 0.88, titulo_legenda, ha="center", va="center",
            transform=ax_legenda.transAxes, fontsize=12.5,
            fontweight="bold", color="#234F43"
        )
        if raster_path is not None:
            # Include every class from the full-resolution CSV even if the preview is downsampled.
            if table is not None:
                presentes = sorted(table["Class_ID"].astype(int).unique())
            simbolos = [
                Patch(facecolor=MAPBIOMAS_COLORS[c], label=land_cover_class_name(c, language))
                for c in presentes
            ]
            n = len(simbolos)
            colunas = 3 if n <= 9 else 4 if n <= 20 else 5
            letra = 10.1 if n <= 9 else 9.2 if n <= 20 else 8.2
            ax_legenda.legend(
                handles=simbolos, loc="center",
                bbox_to_anchor=(0.50, 0.52 if n <= 9 else 0.45 if n <= 20 else 0.40),
                ncol=colunas,
                fontsize=letra, frameon=False,
                labelspacing=0.42 if n <= 20 else 0.24,
                columnspacing=1.0, handlelength=1.7,
                handletextpad=0.45, borderaxespad=0,
            )
        else:
            ax_legenda.legend(
                handles=[Patch(
                    facecolor="#A8D5BA", edgecolor="#235347",
                    label=map_label("study_area_boundary", language)
                )],
                loc="center", bbox_to_anchor=(0.50, 0.42),
                fontsize=11.0, frameon=False
            )

        # ----------------------------------------------------
        # LOCATION: state identification in the enlarged inset panel.
        # ----------------------------------------------------
        draw_location_inset(ax_local, gdf, states_path, language=language)

        # ----------------------------------------------------
        # TERRITORIAL INFORMATION: large, well-spaced labels and statistics.
        # ----------------------------------------------------
        style_panel(ax_info, map_label("territorial_info", language),
                         tamanho_titulo=12.2)
        draw_panel_text(
            ax_info, 0.07, 0.76, map_label("total_area", language), tamanho=11.2,
            color="#303E38"
        )
        draw_panel_text(
            ax_info, 0.93, 0.76, f"{format_map_number(area_km2, 2, language)} km²", tamanho=12.0,
            color="#234F43", fontweight="bold", ha="right"
        )
        draw_panel_text(
            ax_info, 0.07, 0.63, map_label("classes_identified" if table is not None else "vector_features", language), tamanho=10.8, color="#303E38"
        )
        draw_panel_text(
            ax_info, 0.93, 0.63,
            str(len(table)) if table is not None else str(len(gdf)),
            tamanho=11.8, color="#234F43", fontweight="bold", ha="right"
        )
        ax_info.plot(
            [0.065, 0.935], [0.565, 0.565],
            transform=ax_info.transAxes, color="#CCD4CF", linewidth=0.9
        )
        draw_panel_text(
            ax_info, 0.07, 0.49,
            map_label("main_classes" if table is not None else "indicators", language),
            tamanho=10.7, fontweight="bold", color="#234F43"
        )
        if table is not None:
            for i, (_, row) in enumerate(table.head(4).iterrows()):
                name = land_cover_class_name(row["Class_ID"], language)
                if len(name) > 32:
                    name = name[:30] + "…"
                y = 0.385 - i * 0.092
                class_code = int(row["Class_ID"])
                ax_info.add_patch(Rectangle(
                    (0.07, y - 0.024), 0.032, 0.040,
                    transform=ax_info.transAxes,
                    facecolor=MAPBIOMAS_COLORS.get(class_code, "#888888"),
                    edgecolor="none"
                ))
                draw_panel_text(
                    ax_info, 0.123, y, name,
                    tamanho=9.6, color="#1D2823"
                )
                draw_panel_text(
                    ax_info, 0.93, y, f"{format_map_number(row['Percentage'], 1, language)}%",
                    tamanho=10.2, fontweight="bold", ha="right",
                    color="#234F43"
                )
        else:
            draw_panel_text(
                ax_info, 0.07, 0.37,
                f"{map_label('perimeter', language)}: {format_map_number(perimetro_km, 2, language)} km", tamanho=11
            )

        # ----------------------------------------------------
        # NORTH ARROW AND SCALE BAR: larger labels.
        # ----------------------------------------------------
        style_panel(ax_norte, map_label("north", language), tamanho_titulo=11.2)
        imagem = plt.imread(north_arrow_path)
        ax_norte.add_artist(AnnotationBbox(
            OffsetImage(imagem, zoom=0.057), (0.5, 0.42),
            xycoords="axes fraction", box_alignment=(0.5, 0.5),
            frameon=False,
        ))
        draw_scale_bar(fig, ax_mapa, ax_escala, language=language)

        # ----------------------------------------------------
        # SOURCES AND METHODS: larger text without overlap.
        # ----------------------------------------------------
        style_panel(ax_fontes, map_label("sources", language),
                         tamanho_titulo=12.2)
        informacoes = [
            f"{map_label('boundaries', language)}: {boundary_name}",
            f"{map_label('land_cover', language)}: MapBiomas ({ANALYSIS_YEAR})",
            f"CRS: {gdf.crs.to_string()}",
            f"{map_label('prepared_by', language)}: GEOREPORT - IVANA BEZERRA",
        ]
        for y, row in zip([0.72, 0.56, 0.40, 0.24], informacoes):
            draw_panel_text(
                ax_fontes, 0.06, y, row, tamanho=10.3,
                color="#26342F"
            )

        # ----------------------------------------------------
        # EXPORT: save PNG and PDF files.
        # ----------------------------------------------------
        png = output_dir / f"land_cover_map.png"
        pdf = output_dir / f"land_cover_map.pdf"
        fig.savefig(png, dpi=300, facecolor="white")
        fig.savefig(pdf, facecolor="white")
        print("Map PNG:", png)
        print("Map PDF:", pdf)
        plt.show()
        return pdf
    finally:
        plt.close(fig)

# ============================================================
# 6. UNIFIED EXECUTION WORKFLOW FOR ANY STUDY AREA
# ============================================================

def run_diagnostics(
    project_dir, area_path, output_dir,
    area_name, boundary_name=None, vector_output_dir=None
):
    """Validate, process and export all territorial diagnostic products."""
    entrada = project_dir / "data" / "input"
    # Select the raster only after validating the study-area geometry.
    imagem_norte = project_dir / "assets" / "north_arrow.png"
    states_path = entrada / "BR_UF_2024.shp"

    area = load_vector_data(area_path)
    inspect_vector_data(area)
    if not validate_vector_data(area):
        print("Processing stopped: invalid data.")
        return

    caminho_brasil_disponivel = states_path if states_path.is_file() else None
    if caminho_brasil_disponivel is None:
        raise FileNotFoundError(
            "The state boundary file is required at data/input/BR_UF_2024.shp "
            "to identify the area state."
        )
    malha = gpd.read_file(caminho_brasil_disponivel)
    state_codes = identify_states(area, malha)
    print("\nState(s) identified:", ", ".join(state_codes))

    try:
        raster_base = select_raster_or_earth_engine(project_dir, area, output_dir)
    except PendingDriveExport as pendente:
        print("\n--- PENDING / RESUMABLE EARTH ENGINE EXPORT ---")
        print(pendente)
        return
    area_utm = reproject_vector_data(area)
    compare_areas(area, area_utm)
    export_vector_data(
        area_utm, output_dir if vector_output_dir is None else vector_output_dir
    )

    # Always calculate new raster and CSV results for the selected area.
    clipped_raster, csv_path, _ = analyze_land_cover(
        area_utm, raster_base, output_dir
    )

    # Use the raster CRS for the map and the scale bar.
    with rasterio.open(clipped_raster) as src:
        map_area = area_utm.to_crs(src.crs)

    # Generate products from the same raster and class statistics.
    # Run the computationally intensive raster analysis only once.
    report_name = boundary_name or area_name.split("|", 1)[0].strip()
    area_vetorial = map_area.geometry.union_all().area / 1_000_000
    # Export the map and technical report in English from a single raster analysis.
    generate_thematic_map(
        gdf=map_area,
        output_dir=output_dir,
        area_name=area_name,
        north_arrow_path=imagem_norte,
        states_path=states_path,
        raster_path=clipped_raster,
        table_path=csv_path,
        boundary_name=report_name,
        language="en",
    )
    generate_technical_report(
        map_path=output_dir / "land_cover_map.png",
        table_path=csv_path,
        output_dir=output_dir,
        area_name=report_name,
        vector_area_km2=area_vetorial,
        crs=map_area.crs.to_string(),
        year=ANALYSIS_YEAR,
        states=state_codes,
        language="en",
    )

    print("\nGeoReport completed successfully!")
    print("Outputs saved to:", output_dir)


def main():
    'Launch the console menu for the full Federal District or a chosen area.'
    project_dir = Path(__file__).resolve().parent
    print("\n===== GEOREPORT =====")
    print("1 - Federal District territorial diagnostics")
    print("2 - Process a new study area")
    modo = input("Choose an option (1 or 2): ").strip()

    if modo == "1":
        area_path = (
            project_dir / "data" / "input" / "DF_Municipios_2024.shp"
        )
        output_dir = project_dir / "outputs" / "maps"
        run_diagnostics(
            project_dir, area_path, output_dir,
            area_name=f"Federal District | Land use and land cover - {ANALYSIS_YEAR}",
            boundary_name="Federal District",
            vector_output_dir=project_dir / "data" / "processed",
        )
    elif modo == "2":
        area_path = select_vector_file()
        if area_path is None:
            return
        output_dir = (
            project_dir / "outputs" / "study_areas" / area_path.stem
        )
        run_diagnostics(
            project_dir, area_path, output_dir,
            area_name=f"{area_path.stem} | Land use and land cover - {ANALYSIS_YEAR}",
            # Use the supplied filename as a readable boundary label.
        )
    else:
        print("Invalid option. Choose 1 or 2.")


if __name__ == "__main__":
    main()
