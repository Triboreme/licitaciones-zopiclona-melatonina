"""
extractor_comun.py
==================
Extractor único de Órdenes de Compra (OC) de Mercado Público / ChileCompra.

Reemplaza a los extractores duplicados previos (Estractor.py y
Codigo/Estractor.py) con una sola implementación parametrizada por principio
activo. Tanto el pipeline de Zopiclona como el de Melatonina la reutilizan.

Metodología de extracción (Fase 1):
  1. Para cada mes del rango se descarga el ZIP mensual de OC.
  2. Se lee el CSV de detalle (delimitador ';', codificación latin-1).
  3. Se conservan únicamente las filas cuyo principio activo aparece en alguna
     de las columnas de producto (COLS_PRODUCTO), evitando "acoples" de
     productos no relacionados incluidos en la misma OC.
  4. El subconjunto mensual se guarda como CSV (UTF-8 con BOM) en la carpeta
     del año correspondiente.

El filtrado institucional, de estado y de licitación NO ocurre aquí: es
responsabilidad de la Fase 2 (Filtrado.py / melatonina_pipeline.py).
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

from config_rutas import PREFIJO_URL, ANIO_INICIO, ANIO_FIN

# Columnas del CSV de origen donde se busca el principio activo.
# El nombre "NombreroductoGenerico" está escrito así (sic) en la fuente.
COLS_PRODUCTO = [
    "NombreroductoGenerico",
    "EspecificacionComprador",
    "EspecificacionProveedor",
    "RubroN3",
]


def extraer_farmaco(
    patron: str,
    carpeta_destino,
    prefijo_archivo: str,
    anio_inicio: int = ANIO_INICIO,
    anio_fin: int = ANIO_FIN,
    meses=None,
    timeout: int = 45,
) -> dict:
    """
    Descarga y filtra las OC que contienen `patron` en las columnas de producto.

    Parámetros
    ----------
    patron : str
        Subcadena del principio activo a buscar (case-insensitive),
        p. ej. "zopiclona" o "melatonin".
    carpeta_destino : str | Path
        Carpeta raíz de salida; se crea un subdirectorio por año.
    prefijo_archivo : str
        Prefijo de los CSV de salida, p. ej. "zopiclona" → zopiclona_2024_5.csv.
    anio_inicio, anio_fin : int
        Rango de años (inclusive) a procesar.
    meses : list[int] | None
        Meses a procesar (1–12). Si es None, procesa los 12. Útil en la nube
        para descargar solo los meses recientes y no re-bajar todo el histórico.
    timeout : int
        Timeout por solicitud HTTP, en segundos.

    Retorna
    -------
    dict
        Resumen {"filas": int, "meses_con_datos": int, "errores": int}.
    """
    carpeta_destino = Path(carpeta_destino)
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    meses_a_procesar = list(meses) if meses else list(range(1, 13))
    resumen = {"filas": 0, "meses_con_datos": 0, "errores": 0}

    print("=" * 60)
    print(f"  EXTRACCIÓN — patrón '{patron}'  ({anio_inicio}–{anio_fin})  meses={meses_a_procesar}")
    print("=" * 60)

    for anio in range(anio_inicio, anio_fin + 1):
        ruta_anio = carpeta_destino / str(anio)
        ruta_anio.mkdir(parents=True, exist_ok=True)
        print(f"\n--- AÑO {anio} ---")

        for mes in meses_a_procesar:
            url = f"{PREFIJO_URL}/{anio}-{mes}.zip"
            try:
                r = requests.get(url, timeout=timeout)
                if r.status_code != 200:
                    print(f"  [--] Mes {mes:>2}: no disponible (HTTP {r.status_code})")
                    continue

                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    nombre_csv = z.namelist()[0]
                    with z.open(nombre_csv) as f:
                        df_mes = pd.read_csv(
                            f, sep=";", encoding="latin-1", low_memory=False
                        )

                cols_validas = [c for c in COLS_PRODUCTO if c in df_mes.columns]
                if not cols_validas:
                    print(f"  [!] Mes {mes:>2}: sin columnas de producto reconocidas.")
                    continue

                mask = (
                    df_mes[cols_validas]
                    .astype(str)
                    .apply(lambda col: col.str.contains(patron, case=False, na=False))
                    .any(axis=1)
                )
                df_filtrado = df_mes[mask].copy()

                if df_filtrado.empty:
                    print(f"  [  ] Mes {mes:>2}: sin coincidencias.")
                    continue

                nombre_salida = f"{prefijo_archivo}_{anio}_{mes}.csv"
                df_filtrado.to_csv(
                    ruta_anio / nombre_salida,
                    index=False,
                    sep=";",
                    encoding="utf-8-sig",
                )
                resumen["filas"] += len(df_filtrado)
                resumen["meses_con_datos"] += 1
                print(f"  [OK] Mes {mes:>2}: {len(df_filtrado):,} filas → {nombre_salida}")

            except Exception as e:
                resumen["errores"] += 1
                print(f"  [!] Error en {anio}-{mes}: {e}")

    print(
        f"\nExtracción finalizada. Carpeta: {carpeta_destino}\n"
        f"Total filas: {resumen['filas']:,} | "
        f"Meses con datos: {resumen['meses_con_datos']} | "
        f"Errores: {resumen['errores']}"
    )
    return resumen
