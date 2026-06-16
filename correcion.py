"""
correcion.py
============
Diagnóstico de control de calidad (solo lectura). Recorre los CSV ya filtrados
y marca precios unitarios anómalos —típicamente errores de carga, p. ej. una
línea con CANTIDAD = 1 pero TOTAL de una caja completa— para revisión manual.

No modifica ningún dato: únicamente reporta en consola.

Uso:
    python correcion.py
"""

import glob
import os

import pandas as pd

from config_rutas import ZOPICLONA_FILTRADOS

# Precio unitario (VALOR C/U) por sobre el cual una línea es casi con seguridad
# un error de carga: ni un comprimido ni una caja de zopiclona/eszopiclona cuesta
# más de $100.000, así que un precio unitario mayor delata que se cargó el total
# del contrato/caja como precio unitario con CANTIDAD = 1.
UMBRAL_PRECIO_UNITARIO = 100_000
# Cuántos valores más altos mostrar cuando ninguno supera el umbral.
TOP_N = 10
# Archivo CSV donde se exportan las anomalías (con su LINK) para revisión manual.
ARCHIVO_AUDITORIA = ZOPICLONA_FILTRADOS / "ANOMALIAS_PRECIO_revisar.csv"


def limpiar_precio(valor):
    """Convierte un precio en formato chileno a float (0.0 si no se puede)."""
    if pd.isna(valor):
        return 0.0
    s = str(valor).strip()
    if not s:
        return 0.0
    if "." in s and "," in s:            # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                       # 1234,56 -> 1234.56
        s = s.replace(",", ".")
    elif s.count(".") > 1:               # 1.234.567 (puntos de miles)
        s = s.replace(".", "")
    elif "." in s:                       # un punto: miles si hay 3 dígitos tras él
        entero, _, dec = s.partition(".")
        if len(dec) == 3:                # 1.234 / 100.000 -> miles; 21.73 -> decimal
            s = entero + dec
    try:
        return float(s)
    except ValueError:
        return 0.0


def escanear():
    archivos = glob.glob(str(ZOPICLONA_FILTRADOS / "**" / "*.csv"), recursive=True)
    hallazgos = []

    print(f"--- Escaneando precios unitarios en: {ZOPICLONA_FILTRADOS} ---")

    for archivo in archivos:
        try:
            df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")
            if df.empty or "VALOR C/U" not in df.columns:
                continue
            df["VALOR_LIMPIO"] = df["VALOR C/U"].apply(limpiar_precio)
            df["ARCHIVO_DONDE_ESTA"] = os.path.basename(archivo)
            hallazgos.append(df)
        except Exception as e:
            print(f"Error leyendo {os.path.basename(archivo)}: {e}")

    if not hallazgos:
        print("No se encontraron archivos legibles con columna 'VALOR C/U'.")
        return

    todo = pd.concat(hallazgos, ignore_index=True)
    columnas = [c for c in
                ["ARCHIVO_DONDE_ESTA", "COMPRADOR", "VALOR C/U", "TOTAL", "CANTIDAD", "LINK"]
                if c in todo.columns]

    anomalos = todo[todo["VALOR_LIMPIO"] > UMBRAL_PRECIO_UNITARIO].copy()

    if not anomalos.empty:
        print("\n" + "!" * 50)
        print(f"VALORES ANÓMALOS — precio unitario > {UMBRAL_PRECIO_UNITARIO:,}")
        print("!" * 50)
        anomalos = anomalos.sort_values("VALOR_LIMPIO", ascending=False)
        print(anomalos[columnas].to_string(index=False))
        print("\nRevisa esas líneas en su CSV: suele ocurrir que CANTIDAD dice 1")
        print("pero TOTAL corresponde a una caja/contrato completo.")
        # Exporta la lista con el LINK de cada OC para verificarla en Mercado Público.
        anomalos[columnas].to_csv(ARCHIVO_AUDITORIA, sep=";", index=False, encoding="utf-8-sig")
        print(f"\nExportadas {len(anomalos)} anomalías a:\n  {ARCHIVO_AUDITORIA}")
    else:
        print(f"\nNingún precio unitario supera {UMBRAL_PRECIO_UNITARIO:,}.")
        print(f"Top {TOP_N} valores más altos encontrados (para inspección):")
        top = todo.sort_values("VALOR_LIMPIO", ascending=False).head(TOP_N)
        print(top[columnas].to_string(index=False))


if __name__ == "__main__":
    escanear()
