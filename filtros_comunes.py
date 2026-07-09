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

# ---------------------------------------------------------------------------
# CORRECCIONES DE NOMBRE DE COMPRADOR (solo para visualización en dashboards)
# ---------------------------------------------------------------------------
# Mercado Público trunca algunos nombres de organismo (corte a 40 caracteres).
# Aquí se mapea el nombre truncado → nombre completo verificado. Los datos
# crudos y filtrados NO se modifican; la corrección se aplica al generar los
# dashboards. Para agregar otro caso basta añadir una línea al diccionario.
CORRECCIONES_COMPRADOR = {
    "CORP MUNICIPAL DE DESARROLLO SOCIAL DE A":
        "CORP MUNICIPAL DE DESARROLLO SOCIAL DE ANTOFAGASTA",
    "CORP MUNICIPAL DE SERVICIOS PUBLICOS TRASPASADOS DE RANCAGUA":
        "Ilustre Municipalidad de Rancagua",
    "CORP MUNICIPAL SAN FERNANDO PARA LA ATENCION MENORES Y LAS A DE E Y S":
        "Ilustre Municipalidad de San Fernando",
    "CORPORACION MUNICIPAL DE EDUCACION Y SALUD DE SAN BERNARDO":
        "Corp. Municipal de San Bernardo",
}


def corregir_comprador(nombre):
    """Devuelve el nombre completo del comprador si está en la tabla de correcciones."""
    if nombre is None:
        return nombre
    return CORRECCIONES_COMPRADOR.get(str(nombre).strip(), nombre)

# Columnas del CSV crudo donde puede aparecer la señal de destino.
COLS_SENAL_FARMACIA = [
    "Nombre",
    "Descripcion/Obervaciones",   # (sic — así viene de Mercado Público)
    "Financiamiento",
    "UnidadCompra",
]

# Denominaciones con que los municipios nombran su farmacia popular/comunal.
DENOMINACIONES_FARMACIA = [
    "popular",
    "comunal",
    "comunitaria",
    "municipal",
    "ciudadana",
    "vecina",
    "solidaria",
    r"del\s+pueblo",              # "Farmacia del Pueblo"
    r"del\s+carb[oó]n",           # "Botica del Carbón" (Lota)
]

# Sinónimos de "farmacia" usados como prefijo. "farm[a-z]*\.?" acepta
# "farmacia", "farmacias", "farm." y erratas tipo "famacia".
PREFIJOS_FARMACIA = [
    r"farm[a-z]*\.?",
    r"boticas?",
    r"droguer[ií]as?",
]

# Patrones independientes (regex, sobre texto en minúsculas).
PATRONES_FARMACIA_EXTRA = [
    r"junto\s+a\s+ti",            # "Farmacias Junto a Ti" (Talca)
    r"\bfarm[a-z]*\.?\s+boti",    # "Farmacia Botica ...", "Farmacia Botiquín"
    r"\bboticas?\b",              # "Botica" municipal a secas
]


def _regex_farmacia() -> str:
    prefijos = "|".join(PREFIJOS_FARMACIA)
    denominaciones = "|".join(DENOMINACIONES_FARMACIA)
    return rf"\b({prefijos})\s+({denominaciones})"


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
