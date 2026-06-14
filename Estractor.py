"""
Estractor.py
============
Fase 1 — Extracción de Zopiclona desde Mercado Público.

Wrapper delgado sobre extractor_comun.extraer_farmaco(). La lógica de descarga
y filtrado por principio activo vive ahora en un único módulo reutilizable,
compartido con el pipeline de Melatonina.

Uso:
    python Estractor.py
"""

from config_rutas import DATOS_ZOPICLONA, ANIO_INICIO, ANIO_FIN
from extractor_comun import extraer_farmaco


def extractor_zopiclona_organizado(anio_inicio=ANIO_INICIO, anio_fin=ANIO_FIN):
    """Extrae las OC de zopiclona al árbol Datos_Zopiclona/<año>/."""
    return extraer_farmaco(
        patron="zopiclona",
        carpeta_destino=DATOS_ZOPICLONA,
        prefijo_archivo="zopiclona",
        anio_inicio=anio_inicio,
        anio_fin=anio_fin,
    )


if __name__ == "__main__":
    extractor_zopiclona_organizado()
