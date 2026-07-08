"""
filtros_comunes.py
==================
Reglas de exclusión compartidas por los pipelines de Zopiclona (Filtrado.py)
y Melatonina (melatonina_pipeline.py) — Fase 2.

EXCLUSIÓN DE FARMACIAS POPULARES / COMUNALES
--------------------------------------------
El estudio se limita a las compras de la red asistencial municipal (CESFAM,
consultorios, DESAM). Las OC destinadas a farmacias populares/comunales
(venta directa a vecinos) NO forman parte del universo y se envían a
AUDITORIA_DESCARTADOS.

La señal de destino "farmacia popular" no está en una columna única: aparece
en el nombre de la OC ("COMPRA DE MEDICAMENTOS FARM. COMUNAL ENERO 2022"),
en la descripción, en el financiamiento ("FARMACIA POPULAR N° 146") o en la
unidad de compra ("FARMACIA MUNICIPAL", "Abastecimiento Farmacias Junto a Ti").
Por eso se busca en las cuatro columnas.

Para ajustar la regla en el futuro basta editar DENOMINACIONES_FARMACIA o
PATRONES_FARMACIA_EXTRA (p. ej. agregar/quitar una denominación).
"""

import polars as pl

# Columnas del CSV crudo donde puede aparecer la señal de destino.
COLS_SENAL_FARMACIA = [
    "Nombre",
    "Descripcion/Obervaciones",   # (sic — así viene de Mercado Público)
    "Financiamiento",
    "UnidadCompra",
]

# Denominaciones con que los municipios nombran su farmacia popular/comunal.
# Se acepta "farmacia", "farmacias", "farm." y erratas tipo "famacia" gracias
# al patrón: farm + letras opcionales + punto opcional + espacio(s).
DENOMINACIONES_FARMACIA = [
    "popular",
    "comunal",
    "comunitaria",
    "municipal",
    "ciudadana",
    "vecina",
    "solidaria",
]

# Patrones independientes (regex, sobre texto en minúsculas).
PATRONES_FARMACIA_EXTRA = [
    r"junto\s+a\s+ti",            # "Farmacias Junto a Ti" (Talca)
]


def _regex_farmacia() -> str:
    denominaciones = "|".join(DENOMINACIONES_FARMACIA)
    return rf"\bfarm[a-z]*\.?\s+({denominaciones})"


def mask_farmacia_popular(df: pl.DataFrame) -> pl.Expr:
    """
    Máscara booleana: True para las filas cuya OC está destinada a una
    farmacia popular/comunal. Busca en COLS_SENAL_FARMACIA (las que existan).
    """
    texto = pl.lit("")
    for col in COLS_SENAL_FARMACIA:
        if col in df.columns:
            texto = texto + " | " + pl.col(col).cast(pl.Utf8).str.to_lowercase().fill_null("")

    mask = texto.str.contains(_regex_farmacia())
    for patron in PATRONES_FARMACIA_EXTRA:
        mask = mask | texto.str.contains(patron)
    return mask
