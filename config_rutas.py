"""
config_rutas.py
===============
Configuración central de rutas y parámetros del proyecto de tesis.

Un único punto de verdad para las rutas evita las inconsistencias previas
(algunos módulos apuntaban a ~/Desktop/Adri y otros a
~/Desktop/macbook air 2026/Adri, generando árboles de datos paralelos).

Todos los módulos del proyecto importan desde aquí.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Carpeta raíz real del proyecto (donde residen efectivamente los datos).
#
# Por defecto apunta a tu Escritorio (uso local). En la nube (GitHub Actions)
# se define la variable de entorno ADRI_BASE para apuntar a la carpeta del
# repositorio; así el MISMO código corre en tu PC y en el servidor sin cambios.
# ---------------------------------------------------------------------------
_DEFAULT_BASE = Path.home() / "Desktop" / "macbook air 2026" / "Adri"
BASE_ADRI = Path(os.environ.get("ADRI_BASE", _DEFAULT_BASE))

# ---------------------------------------------------------------------------
# Datos crudos por principio activo (salida de la Fase 1 — Extracción).
# ---------------------------------------------------------------------------
DATOS_ZOPICLONA  = BASE_ADRI / "Datos_Zopiclona"
DATOS_MELATONINA = BASE_ADRI / "Datos_Melatonina"

# ---------------------------------------------------------------------------
# Datos filtrados y clasificados (salida de la Fase 2 — Filtrado).
# ---------------------------------------------------------------------------
ZOPICLONA_FILTRADOS  = BASE_ADRI / "Datos_Zopiclona_Filtrados"
MELATONINA_FILTRADOS = BASE_ADRI / "Datos_Melatonina_Filtrados"

# ---------------------------------------------------------------------------
# Fuente de datos: repositorio público de Órdenes de Compra de ChileCompra
# (Mercado Público), expuesto vía Azure Blob Storage. Cada archivo mensual
# se publica como "<AAAA>-<M>.zip".
# ---------------------------------------------------------------------------
PREFIJO_URL = "https://transparenciachc.blob.core.windows.net/oc-da"

# Ventana temporal de análisis de la tesis.
ANIO_INICIO = 2021
ANIO_FIN    = 2026
