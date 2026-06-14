import polars as pl
import os

from config_rutas import DATOS_ZOPICLONA, ZOPICLONA_FILTRADOS

# =========================================================
# Instituciones adicionales a INCLUIR aunque no contengan
# las palabras clave municipales (muni / corp / desam).
# Cada sublista son palabras que deben aparecer TODAS en
# OrganismoPublico (en minúsculas). Se comparan sin distinguir
# mayúsculas; "corp" ya cubre "Corporación Antofagasta", pero se
# deja explícita para documentar la intención y blindar variantes.
# =========================================================
INSTITUCIONES_INCLUIR = [
    ["miraflores"],            # Consultorio Miraflores (antes se descartaba)
    ["corp", "antofagasta"],   # Corporación Municipal de Antofagasta
]


def _mask_instituciones_extra(comprador_min: pl.Expr) -> pl.Expr:
    """Construye una máscara OR para la allowlist de instituciones extra."""
    mask = pl.lit(False)
    for palabras in INSTITUCIONES_INCLUIR:
        cond = pl.lit(True)
        for palabra in palabras:
            cond = cond & comprador_min.str.contains(palabra)
        mask = mask | cond
    return mask


def procesador_zopiclona_cascada():
    ruta_entrada = str(DATOS_ZOPICLONA)
    ruta_salida_base = str(ZOPICLONA_FILTRADOS)
    
    mapeo_columnas = {
        "CodigoLicitacion": "LICITACIÓN",
        "OrganismoPublico": "COMPRADOR",
        "NombreProveedor": "PROVEEDOR",
        "UnidadCompra": "¿Para quién?",
        "FechaEnvio": "FECHA O.C",
        "cantidad": "CANTIDAD",
        "precioNeto": "VALOR C/U",
        "totalLineaNeto": "TOTAL",
        "Link": "LINK" 
    }

    for anio in sorted(os.listdir(ruta_entrada)):
        ruta_anio_in = os.path.join(ruta_entrada, anio)
        if not os.path.isdir(ruta_anio_in): continue
        
        rutas = {
            "pura_lic": os.path.join(ruta_salida_base, anio, "1_PURA_CON_LICITACION"),
            "pura_sin": os.path.join(ruta_salida_base, anio, "2_PURA_SIN_LICITACION"),
            "der_lic": os.path.join(ruta_salida_base, anio, "3_DERIVADOS_CON_LICITACION"),
            "der_sin": os.path.join(ruta_salida_base, anio, "4_DERIVADOS_SIN_LICITACION"),
            "descartes": os.path.join(ruta_salida_base, anio, "5_AUDITORIA_DESCARTADOS")
        }
        for p in rutas.values(): os.makedirs(p, exist_ok=True)

        for archivo in sorted(os.listdir(ruta_anio_in)):
            if not archivo.endswith(".csv"): continue
            
            try:
                df = pl.read_csv(os.path.join(ruta_anio_in, archivo), separator=';', encoding='utf-8-sig', infer_schema_length=10000)

                # Guarda: si falta la columna de institución, se omite el archivo
                if "OrganismoPublico" not in df.columns:
                    print(f"Omitido (sin OrganismoPublico): {archivo}")
                    continue

                # --- NUEVA LÓGICA DE FILTRO MUNICIPAL ---
                # Creamos una columna temporal en minúsculas para buscar
                comprador_min = pl.col("OrganismoPublico").str.to_lowercase().fill_null("")

                # Definimos las palabras clave que identifican al mundo municipal
                # + la allowlist de instituciones extra (Miraflores, Antofagasta).
                es_municipal = (
                    comprador_min.str.contains("muni") |       # Municipalidad, I. MUNICIPALIDAD
                    comprador_min.str.contains("corp") |       # Corporación Municipal, CORP.
                    comprador_min.str.contains("desam") |      # Depto de Salud Municipal
                    _mask_instituciones_extra(comprador_min)   # Consultorio Miraflores, Corp. Antofagasta
                )

                # Estado válido (si la columna no existe, no se filtra por estado)
                if "Estado" in df.columns:
                    mask_estado = pl.col("Estado").is_in(["Aceptada", "Recepcion Conforme"])
                else:
                    mask_estado = pl.lit(True)

                # 1. Filtro de calidad: institución municipal/allowlist + estado confirmado.
                mask_calidad = es_municipal & mask_estado

                # 2. Deduplicación SEGURA.
                #    El antiguo ~df.is_duplicated() marcaba TODAS las copias de una fila
                #    repetida y, al negarlo, las eliminaba todas (incluida la legítima),
                #    con riesgo de pérdida de información. .unique(keep="first") conserva
                #    una copia de cada fila. maintain_order=True garantiza reproducibilidad.
                df_validos     = df.filter(mask_calidad).unique(keep="first", maintain_order=True)
                df_descartados = df.filter(~mask_calidad)

                # 2. Lógica de Cascada (Zopiclona vs Eszopiclona)
                gen = pl.col("NombreroductoGenerico").str.to_lowercase().fill_null("")
                esp = pl.col("EspecificacionComprador").str.to_lowercase().fill_null("")

                es_pura_gen = gen.str.contains("zopiclona") & ~gen.str.contains("eszopiclona")
                es_pura_esp = (~gen.str.contains("zopiclona")) & (esp.str.contains("zopiclona") & ~esp.str.contains("eszopiclona"))

                df_pura = df_validos.filter(es_pura_gen | es_pura_esp)
                df_der = df_validos.filter(~(es_pura_gen | es_pura_esp))

                def guardar_formateado(df_sub, ruta_dir, sufijo):
                    if not df_sub.is_empty():
                        cols_finales = [c for c in mapeo_columnas.keys() if c in df_sub.columns]
                        df_final = df_sub.select(cols_finales).rename({c: mapeo_columnas[c] for c in mapeo_columnas if c in df_sub.columns})
                        df_final.write_csv(os.path.join(ruta_dir, archivo.replace(".csv", f"{sufijo}.csv")), separator=';')

                # Una licitación es "real" solo si no es nula NI cadena vacía
                # (antes, los códigos "" se clasificaban erróneamente como CON licitación).
                if "CodigoLicitacion" in df_validos.columns:
                    tiene_licitacion = (
                        pl.col("CodigoLicitacion").is_not_null() &
                        (pl.col("CodigoLicitacion").cast(pl.Utf8).str.strip_chars() != "")
                    )
                else:
                    tiene_licitacion = pl.lit(False)

                guardar_formateado(df_pura.filter(tiene_licitacion), rutas["pura_lic"], "_PURA_LIC")
                guardar_formateado(df_pura.filter(~tiene_licitacion), rutas["pura_sin"], "_PURA_SIN")
                guardar_formateado(df_der.filter(tiene_licitacion), rutas["der_lic"], "_DERIV_LIC")
                guardar_formateado(df_der.filter(~tiene_licitacion), rutas["der_sin"], "_DERIV_SIN")

                if not df_descartados.is_empty():
                    df_descartados.write_csv(os.path.join(rutas["descartes"], archivo.replace(".csv", "_DESC.csv")), separator=';')

                print(f"Municipio filtrado y clasificado: {archivo}")

            except Exception as e:
                print(f"Error en {archivo}: {e}")

if __name__ == "__main__":
    procesador_zopiclona_cascada()