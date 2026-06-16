import polars as pl
import os

from config_rutas import DATOS_ZOPICLONA, ZOPICLONA_FILTRADOS

# =========================================================
# Instituciones municipales adicionales a INCLUIR aunque no
# contengan las palabras clave municipales (muni / corp / desam).
# Cada sublista son palabras que deben aparecer TODAS en
# OrganismoPublico (en minúsculas), sin distinguir mayúsculas.
# =========================================================
INSTITUCIONES_INCLUIR = [
    ["miraflores"],            # Consultorio Miraflores (no entra por el filtro municipal)
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
            "descartes": os.path.join(ruta_salida_base, anio, "5_AUDITORIA_DESCARTADOS"),
            "no_zopi": os.path.join(ruta_salida_base, anio, "6_NO_ES_ZOPICLONA")
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

                # Palabras clave del mundo municipal + allowlist de instituciones
                # extra (Miraflores, Antofagasta). Se anclan con límite de palabra (\b)
                # para evitar colisiones de substring: sin el \b, "muni" matchea dentro
                # de "comunitaria"/"comunidad" y colaba hospitales y centros de salud
                # mental comunitarios que NO son municipales.
                es_municipal = (
                    comprador_min.str.contains(r"\bmuni")  |   # Municipalidad, I. MUNICIPALIDAD, CORP MUNIC
                    comprador_min.str.contains(r"\bcorp")  |   # Corporación (Municipal) de...
                    comprador_min.str.contains(r"\bdesam") |   # Depto de Salud Municipal (DESAM)
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

                # 2. Lógica de Cascada (Zopiclona PURA vs Eszopiclona DERIVADO)
                #
                # OJO: en Mercado Público existe un único código ONU (51141810
                # "Zopiclona") para TODA la familia, por lo que NombreroductoGenerico
                # dice "Zopiclona" casi siempre, AUNQUE la compra real sea Eszopiclona.
                # Además el dato de origen viene MUY sucio: genéricos equivocados
                # (p. ej. "Clorhidrato de lincomicina"), el nombre escrito mal
                # ("eszoplicona", "ezopiclona") y la palabra correcta a veces SOLO en
                # la especificación del PROVEEDOR. Por eso se busca en los tres campos
                # (genérico + comprador + proveedor) y con tolerancia a erratas.
                gen  = pl.col("NombreroductoGenerico").str.to_lowercase().fill_null("")
                esp  = pl.col("EspecificacionComprador").str.to_lowercase().fill_null("")
                prov = pl.col("EspecificacionProveedor").str.to_lowercase().fill_null("")
                texto = gen + " | " + esp + " | " + prov

                # Familia ESZOPICLONA tolerante a las erratas frecuentes (eszopiclona,
                # ezopiclona, eszoplicona, eszopiclina...). El \b (límite de palabra) es
                # CLAVE: evita matchear "ezopiclona" dentro de "bezopiclona" (= "BE
                # zopiclona" = bioequivalente zopiclona PURA). La terminación [oi]na
                # acepta tanto "...clona" como la errata "...clina" (eszopiclina).
                RE_ESZOPICLONA = r"\be[sz][sz]?o?p[ilc]+[oi]na"
                # Zopiclona pura (+ erratas zoplicona/zopliclona/zopiclina), SIN prefijo "e".
                RE_ZOPICLONA = r"zo?pl?i?cl?[oi]na"

                # Marcas comerciales de ESZOPICLONA que no traen la palabra (se clasifican
                # como derivado). Marcas de ZOPICLONA PURA: solo se listan para reconocer
                # que la fila SÍ es de la familia (su clasificación pura sale del genérico).
                MARCAS_ESZOPICLONA   = ["valnoc", "zopinom", "nirvan", "plessir",
                                        "zopinon", "ziponom", "insomnium", "eszop"]
                MARCAS_ZOPICLONA_PURA = ["zometic", "zoperil", "losopil", "lisopil",
                                         "imovane", "zomeril", "noctidem"]

                def _contiene(col, palabras, regex=False):
                    m = pl.lit(False)
                    for w in palabras:
                        m = m | (col.str.contains(w) if regex else col.str.contains(w, literal=True))
                    return m

                # --- 2a. Filtro ANTI-CONTAMINACIÓN ---
                # Bajo el código ONU 51141810 ("Zopiclona") se cuelan OTROS fármacos
                # (modafinilo, morfina, amiodarona, melissa/passiflora, etc.) porque el
                # genérico dice "Zopiclona" aunque el producto real sea distinto. Se
                # apartan a 6_NO_ES_ZOPICLONA las filas que nombran un fármaco distinto
                # conocido Y no tienen señal de la familia zopiclona en las
                # especificaciones (comprador/proveedor). Es conservador: ante cualquier
                # señal de la familia, la fila se conserva (no se pierde zopiclona real).
                OTROS_FARMACOS = [
                    # Otro Z-fármaco (zolpidem) y sus marcas: NO es zopiclona.
                    "zolpidem", "zubam", "zaviana", "somno",
                    # Estimulantes / opioides / cardiología
                    "modafinilo", "armodafinilo", "morfina", "amiodarona", "isosorbide",
                    "propranolol", "propanolol", "diltiazem", "tildiem",
                    # Psicofármacos (otros)
                    "clorpromazina", "mirtazapina", "memantina", "sertralina", "quetiapina",
                    "quietiapina", "risperidona", "escitalopram", "amitriptilina", "amitriplina",
                    "aripiprazol", "aripripazol", "alprazolam", "valpax", "clonazepam",
                    "diazepam", "fluoxetina",
                    # Analgésicos / AINEs
                    "ibuprofeno", "ibupirac", "paracetamol", "tramadol", "ketoprofeno",
                    "profenid", "metamizol", "panagesic", "mio relax", "miorelax",
                    # Antibióticos / antifúngicos / antivirales
                    "flucloxacilina", "penicilina", "terbinafina", "aciclovir",
                    # Otros (gastro, gota, tiroides, óseo, vitaminas, tópicos, fitofármacos)
                    "gastrole", "febuxostat", "fexurix", "ondansetron", "raltegravir",
                    "metformina", "losartan", "omeprazol", "tiamazol", "damixan",
                    "aldrox", "alendronato", "konakion", "fitoquinona", "vitamina b",
                    "arnica", "arnikaderm", "repariven", "clorfenamina",
                    "melissa", "passiflora",
                ]
                senal_familia = (
                    _contiene(esp,  [RE_ZOPICLONA, RE_ESZOPICLONA], regex=True)
                    | _contiene(prov, [RE_ZOPICLONA, RE_ESZOPICLONA], regex=True)
                    | _contiene(esp,  MARCAS_ESZOPICLONA + MARCAS_ZOPICLONA_PURA)
                    | _contiene(prov, MARCAS_ESZOPICLONA + MARCAS_ZOPICLONA_PURA)
                )
                nombra_otro_farmaco = _contiene(esp, OTROS_FARMACOS) | _contiene(prov, OTROS_FARMACOS)
                es_no_zopiclona = nombra_otro_farmaco & ~senal_familia

                df_no_zopi = df_validos.filter(es_no_zopiclona)
                df_zopi    = df_validos.filter(~es_no_zopiclona)

                # --- 2b. Cascada PURA vs ESZOPICLONA (sobre lo que SÍ es zopiclona) ---
                # Las marcas de eszopiclona se buscan SIEMPRE en la esp. del COMPRADOR, y
                # en la del PROVEEDOR solo si NO menciona la dosis 7,5 mg (la de la pura).
                esp_marca_eszop  = _contiene(esp,  MARCAS_ESZOPICLONA)
                prov_marca_eszop = _contiene(prov, MARCAS_ESZOPICLONA)
                prov_sin_dosis_pura = ~(
                    prov.str.contains("7.5", literal=True)
                    | prov.str.contains("7,5", literal=True)
                )

                # Es DERIVADO si la familia eszopiclona aparece en CUALQUIERA de los tres
                # campos, o si una marca de eszopiclona aparece en el comprador, o en el
                # proveedor cuando éste no menciona la dosis pura (7,5 mg).
                es_eszopiclona = (
                    texto.str.contains(RE_ESZOPICLONA)
                    | esp_marca_eszop
                    | (prov_marca_eszop & prov_sin_dosis_pura)
                )

                # Es PURA si se menciona zopiclona (en cualquier campo) y NO es eszopiclona.
                # El guard ~es_eszopiclona resuelve el hecho de que "eszopiclona"
                # contenga "zopiclona" como substring.
                menciona_zopiclona = texto.str.contains(RE_ZOPICLONA)
                es_pura = menciona_zopiclona & ~es_eszopiclona

                df_pura = df_zopi.filter(es_pura)
                df_der  = df_zopi.filter(~es_pura)

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

                # Contaminación (otros fármacos bajo el código ONU de Zopiclona): se
                # guarda completa, con sus columnas crudas, para auditoría/trazabilidad.
                if not df_no_zopi.is_empty():
                    df_no_zopi.write_csv(os.path.join(rutas["no_zopi"], archivo.replace(".csv", "_NO_ZOPI.csv")), separator=';')

                print(f"Municipio filtrado y clasificado: {archivo}")

            except Exception as e:
                print(f"Error en {archivo}: {e}")

if __name__ == "__main__":
    procesador_zopiclona_cascada()