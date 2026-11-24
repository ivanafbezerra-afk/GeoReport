# -*- coding: utf-8 -*-
"""GeoReport | Resume Earth Engine exports and download Google Drive GeoTIFF files."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import time


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomically(caminho, data):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def register_export_task(
    state_file, task_id, prefix, drive_folder="GeoReport",
    expected_file_count=1
):
    """Store metadata for resuming a remote export safely."""
    if not task_id or not prefix:
        raise ValueError("Task ID and export prefix are required.")
    data = {
        "task_id": str(task_id),
        "prefix": prefix,
        "drive_folder": drive_folder,
        "started_at": _iso(_utc_now() - timedelta(seconds=30)),
        "expected_file_count": int(expected_file_count),
    }
    _write_json_atomically(state_file, data)
    return data


def read_export_task(state_file):
    caminho = Path(state_file)
    if not caminho.exists():
        return None
    data = json.loads(caminho.read_text(encoding="utf-8"))
    for campo in ("task_id", "prefix", "started_at"):
        if not data.get(campo):
            raise ValueError(f"Invalid task file: missing field {campo}.")
    return data


def connect_drive():
    """Connect to Google Drive using Earth Engine credentials."""
    import ee
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Install google-api-python-client in the Spyder environment: "
            "conda install -c conda-forge google-api-python-client"
        ) from exc
    # Earth Engine authentication normally includes the Google Drive scope.
    # If needed, renew permissions locally with ee.Authenticate(force=True).
    credenciais = ee.data.get_persistent_credentials()
    return build("drive", "v3", credentials=credenciais, cache_discovery=False)


def get_earth_engine_task_status(ee, task_id):
    """Read the current status of an Earth Engine task."""
    lista = ee.data.getTaskStatus([task_id])
    if not lista:
        raise RuntimeError(f"The task {task_id} was not found in Earth Engine.")
    return lista[0]


def wait_for_earth_engine_task(ee, task_id, espera_max_s=600, intervalo_s=20):
    """Wait a bounded amount of time for a remote Earth Engine task."""
    prazo = time.monotonic() + max(0, espera_max_s)
    anterior = None
    ultimo_relatorio = 0.0
    while True:
        status = get_earth_engine_task_status(ee, task_id)
        estado = status.get("state", "UNKNOWN")
        if estado != anterior or time.monotonic() - ultimo_relatorio >= 60:
            print(f"Earth Engine task {task_id}: {estado}")
            anterior = estado
            ultimo_relatorio = time.monotonic()
        if estado == "COMPLETED":
            return True
        if estado in ("FAILED", "CANCELLED", "CANCEL_REQUESTED"):
            raise RuntimeError(
                "Earth Engine export did not complete: "
                f"{estado} - {status.get('error_message') or status.get('errorMessage') or ''}"
            )
        if estado not in ("READY", "RUNNING"):
            raise RuntimeError(f"Unexpected Earth Engine task status: {estado}")
        if time.monotonic() >= prazo:
            return False
        time.sleep(min(intervalo_s, max(0, prazo - time.monotonic())))


def _parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def list_export_tiffs(servico, prefix, iniciado_em):
    """Find GeoTIFF files associated with a Drive export."""
    inicio = _parse_utc(iniciado_em) - timedelta(minutes=2)
    seguro = prefix.replace("\\", "\\\\").replace("'", "\\'")
    consulta = f"trashed = false and name contains '{seguro}'"
    encontrados = []
    pagina = None
    while True:
        resultado = servico.files().list(
            q=consulta,
            spaces="drive",
            fields="nextPageToken,files(id,name,mimeType,size,createdTime)",
            pageSize=1000,
            pageToken=pagina,
        ).execute()
        for f in resultado.get("files", []):
            name = f.get("name", "")
            if not (name.startswith(prefix) and name.lower().endswith((".tif", ".tiff"))):
                continue
            if not f.get("createdTime") or _parse_utc(f["createdTime"]) < inicio:
                continue
            encontrados.append(f)
        pagina = resultado.get("nextPageToken")
        if not pagina:
            break
    return sorted(encontrados, key=lambda f: f["name"])


def wait_for_drive_files(
    servico, prefix, iniciado_em, espera_max_s=100, minimo_arquivos=1
):
    """Poll Drive for all pieces of a completed export."""
    limite = time.monotonic() + espera_max_s
    while True:
        arquivos = list_export_tiffs(servico, prefix, iniciado_em)
        if len(arquivos) >= minimo_arquivos:
            return arquivos
        if time.monotonic() >= limite:
            return []
        time.sleep(min(10, max(0, limite - time.monotonic())))


def download_drive_file(servico, file_path, destino):
    """Download one file from Google Drive."""
    import rasterio
    from googleapiclient.http import MediaIoBaseDownload

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    if destino.exists() and destino.stat().st_size > 0:
        with rasterio.open(destino) as src:
            if src.count != 1 or src.crs is None:
                raise ValueError(f"Invalid locally cached GeoTIFF: {destino}")
        return destino
    requisicao = servico.files().get_media(fileId=file_path["id"])
    try:
        with parcial.open("wb") as saida:
            downloader = MediaIoBaseDownload(saida, requisicao, chunksize=8*1024*1024)
            concluido = False
            while not concluido:
                _, concluido = downloader.next_chunk(num_retries=5)
        if parcial.stat().st_size <= 0:
            raise RuntimeError("Downloaded file is empty.")
        with rasterio.open(parcial) as src:
            if src.crs is None or src.count != 1:
                raise ValueError("Google Drive raster must have a CRS and one band.")
        parcial.replace(destino)
        print(f"Download complete: {destino.name}")
        return destino
    except Exception:
        parcial.unlink(missing_ok=True)
        raise


def merge_geotiffs(arquivos, destino):
    """Mosaic exported GeoTIFF tiles into a single raster."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.merge import merge

    arquivos = [Path(p) for p in arquivos]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".mosaic.partial.tif")

    if len(arquivos) == 1:
        copia = destino.with_suffix(".copy.partial.tif")
        shutil.copyfile(arquivos[0], copia)
        copia.replace(destino)
        return destino

    try:
        with ExitStack() as pilha:
            fontes = [pilha.enter_context(rasterio.open(p)) for p in arquivos]
            crs = fontes[0].crs
            resolucao = fontes[0].res
            tipo = fontes[0].dtypes[0]
            for fonte in fontes:
                if fonte.crs != crs or fonte.count != 1 or fonte.res != resolucao or fonte.dtypes[0] != tipo:
                    raise ValueError("Exported tiles have incompatible CRS or pixel resolution.")
            merge(
                fontes, nodata=0, method="first", resampling=Resampling.nearest,
                mem_limit=64, dst_path=parcial,
                dst_kwds={"driver": "GTiff", "compress": "LZW", "BIGTIFF": "IF_SAFER"},
            )
        with rasterio.open(parcial) as src:
            if src.count != 1 or src.crs is None:
                raise RuntimeError("The saved mosaic is not a valid GeoTIFF.")
        parcial.replace(destino)
        print(f"Mosaic created from {len(arquivos)} tiles: {destino}")
        return destino
    except Exception:
        parcial.unlink(missing_ok=True)
        raise


def complete_drive_export(ee, state_file, destino, espera_max_s=600):
    """Resume an export and download its final GeoTIFF."""
    data = read_export_task(state_file)
    if data is None:
        raise ValueError("Export task state file does not exist.")
    if not wait_for_earth_engine_task(ee, data["task_id"], espera_max_s=espera_max_s):
        print("The export is still active. GeoReport will resume the saved task on its next run.")
        return None
    servico = connect_drive()
    minimo = int(data.get("expected_file_count", 1))
    arquivos = wait_for_drive_files(
        servico, data["prefix"], data["started_at"],
        minimo_arquivos=minimo
    )
    if not arquivos:
        print("Earth Engine export completed, but not all GeoTIFF files are available in Drive yet.")
        print(f"Expected files: {minimo}. GeoReport will retry on its next run.")
        return None
    print(f"Found {len(arquivos)} GeoTIFF file(s) for this export in Drive.")
    pasta_partes = Path(destino).parent / (Path(destino).stem + "_tiles")
    arquivos_locais = [download_drive_file(servico, arq, pasta_partes / arq["name"]) for arq in arquivos]
    merge_geotiffs(arquivos_locais, destino)
    return Path(destino)
