#!/usr/bin/env python3
"""
melatonina_pipeline.py
======================
Pipeline unificado para Melatonina — Trabajo de Tesis
Reemplaza: Estractor.py + Filtrado.py + dashboardzo.py

Fases:
  1. EXTRACCIÓN  — Descarga ZIPs desde Mercado Público y filtra filas de melatonina.
  2. FILTRADO    — Valida municipios/estado y separa en Con/Sin Licitación.
                   (Melatonina no tiene derivados → sin cascada pura/eszo.)
  3. DASHBOARD   — Genera HTML interactivo con Plotly (se abre en el navegador).

Uso:
  python melatonina_pipeline.py            # corre las 3 fases en orden
  python melatonina_pipeline.py --fase 1   # solo extracción
  python melatonina_pipeline.py --fase 2   # solo filtrado
  python melatonina_pipeline.py --fase 3   # solo dashboard
"""

import argparse
import glob
import json
import os
import webbrowser

import pandas as pd
import polars as pl
from pathlib import Path

from config_rutas import DATOS_MELATONINA, MELATONINA_FILTRADOS, ANIO_INICIO, ANIO_FIN
from extractor_comun import extraer_farmaco

# =============================================================
# CONFIGURACIÓN GLOBAL  (las rutas viven en config_rutas.py)
# =============================================================

CARPETA_RAIZ    = str(DATOS_MELATONINA)
CARPETA_FILTRO  = str(MELATONINA_FILTRADOS)
DASHBOARD_HTML  = os.path.join(CARPETA_FILTRO, "Dashboard_Melatonina_Licitacion.html")

PATRON_BUSQUEDA = "melatonin"          # captura "melatonina", "melatonin", etc.

# Columnas del CSV crudo → nombres finales para análisis
MAPEO_COLUMNAS = {
    "CodigoLicitacion": "LICITACIÓN",
    "OrganismoPublico": "COMPRADOR",
    "NombreProveedor":  "PROVEEDOR",
    "UnidadCompra":     "¿Para quién?",
    "FechaEnvio":       "FECHA O.C",
    "cantidad":         "CANTIDAD",
    "precioNeto":       "VALOR C/U",
    "totalLineaNeto":   "TOTAL",
    "Link":             "LINK",
}

# (Las columnas de producto para la búsqueda viven en extractor_comun.COLS_PRODUCTO)

# Instituciones adicionales a INCLUIR aunque no contengan las palabras
# clave municipales (muni / corp / desam). Cada sublista son palabras que
# deben aparecer TODAS en OrganismoPublico (en minúsculas). "corp" ya cubre
# "Corporación Antofagasta", pero se deja explícita para documentar la
# intención y blindar variantes del nombre.
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


# =============================================================
# FASE 1 — EXTRACCIÓN
# =============================================================

def fase_extraccion():
    """
    Fase 1 — Extracción de Melatonina.

    Delega en extractor_comun.extraer_farmaco() (la misma rutina que usa el
    pipeline de Zopiclona), conservando solo las filas cuyo principio activo
    aparece en las columnas de producto.
    Resultado: <BASE>/Datos_Melatonina/<año>/melatonina_<año>_<mes>.csv
    """
    print("\n" + "=" * 60)
    print("  FASE 1 — EXTRACCIÓN DE MELATONINA")
    print("=" * 60)

    return extraer_farmaco(
        patron=PATRON_BUSQUEDA,
        carpeta_destino=CARPETA_RAIZ,
        prefijo_archivo="melatonina",
        anio_inicio=ANIO_INICIO,
        anio_fin=ANIO_FIN,
    )


# =============================================================
# FASE 2 — FILTRADO Y CLASIFICACIÓN
# =============================================================

def fase_filtrado():
    """
    Lee los CSV crudos (Fase 1), aplica filtros de institución y estado,
    y separa en Con Licitación / Sin Licitación.

    Melatonina NO tiene derivados, por lo que no hay cascada pura/eszo.
    Todo registro válido es simplemente "melatonina".

    Resultado por año:
      1_CON_LICITACION/   → *_MELA_LIC.csv
      2_SIN_LICITACION/   → *_MELA_SIN.csv
      3_AUDITORIA_DESCARTADOS/ → *_DESC.csv
    """
    print("\n" + "=" * 60)
    print("  FASE 2 — FILTRADO Y CLASIFICACIÓN")
    print("=" * 60)

    if not os.path.exists(CARPETA_RAIZ):
        print(f"[!] No existe la carpeta de entrada: {CARPETA_RAIZ}")
        print("    Ejecuta primero la Fase 1 (extracción).")
        return

    anios_disponibles = sorted(
        d for d in os.listdir(CARPETA_RAIZ)
        if os.path.isdir(os.path.join(CARPETA_RAIZ, d))
    )

    if not anios_disponibles:
        print("[!] La carpeta de extracción está vacía. Ejecuta la Fase 1.")
        return

    for anio in anios_disponibles:
        ruta_anio_in = os.path.join(CARPETA_RAIZ, anio)

        rutas = {
            "con_lic":   os.path.join(CARPETA_FILTRO, anio, "1_CON_LICITACION"),
            "sin_lic":   os.path.join(CARPETA_FILTRO, anio, "2_SIN_LICITACION"),
            "descartes": os.path.join(CARPETA_FILTRO, anio, "3_AUDITORIA_DESCARTADOS"),
        }
        for p in rutas.values():
            os.makedirs(p, exist_ok=True)

        print(f"\n--- AÑO {anio} ---")

        archivos_csv = sorted(
            f for f in os.listdir(ruta_anio_in) if f.endswith(".csv")
        )

        if not archivos_csv:
            print("  (sin archivos CSV en esta carpeta)")
            continue

        for archivo in archivos_csv:
            ruta_archivo = os.path.join(ruta_anio_in, archivo)
            try:
                df = pl.read_csv(
                    ruta_archivo,
                    separator=";",
                    encoding="utf-8-sig",
                    infer_schema_length=10_000,
                )

                # ---- 1. Filtro de institución (solo mundo municipal) ----
                if "OrganismoPublico" not in df.columns:
                    print(f"  [!] {archivo}: columna OrganismoPublico ausente, omitido.")
                    continue

                comprador_min = pl.col("OrganismoPublico").str.to_lowercase().fill_null("")
                es_municipal = (
                    comprador_min.str.contains("muni")   |   # Municipalidad, I. MUNICIPALIDAD
                    comprador_min.str.contains("corp")   |   # Corporación Municipal
                    comprador_min.str.contains("desam")  |   # Depto. de Salud Municipal
                    _mask_instituciones_extra(comprador_min) # Consultorio Miraflores, Corp. Antofagasta
                )

                # ---- 2. Validación de estado y deduplicación SEGURA ----
                estados_validos = ["Aceptada", "Recepcion Conforme"]
                if "Estado" not in df.columns:
                    mask_estado = pl.lit(True)
                else:
                    mask_estado = pl.col("Estado").is_in(estados_validos)

                mask_calidad = es_municipal & mask_estado

                # .unique(keep="first") conserva una copia de cada fila repetida.
                # (El antiguo ~df.is_duplicated() borraba TODAS las copias, incluida la
                # legítima → riesgo de pérdida de información.) maintain_order=True da
                # reproducibilidad.
                df_validos     = df.filter(mask_calidad).unique(keep="first", maintain_order=True)
                df_descartados = df.filter(~mask_calidad)

                # ---- 3. Separar Con Licitación / Sin Licitación ----
                if "CodigoLicitacion" not in df_validos.columns:
                    df_con_lic = df_validos.filter(pl.lit(False))
                    df_sin_lic = df_validos
                else:
                    tiene_licitacion = (
                        pl.col("CodigoLicitacion").is_not_null() &
                        (pl.col("CodigoLicitacion").cast(pl.Utf8).str.strip_chars() != "")
                    )
                    df_con_lic = df_validos.filter(tiene_licitacion)
                    df_sin_lic = df_validos.filter(~tiene_licitacion)

                # ---- 4. Guardar con columnas renombradas ----
                def guardar(df_sub: pl.DataFrame, ruta_dir: str, sufijo: str):
                    if df_sub.is_empty():
                        return
                    cols_presentes = [c for c in MAPEO_COLUMNAS if c in df_sub.columns]
                    df_final = df_sub.select(cols_presentes).rename(
                        {c: MAPEO_COLUMNAS[c] for c in cols_presentes}
                    )
                    nombre_salida = archivo.replace(".csv", f"{sufijo}.csv")
                    df_final.write_csv(
                        os.path.join(ruta_dir, nombre_salida), separator=";"
                    )

                guardar(df_con_lic,    rutas["con_lic"],   "_MELA_LIC")
                guardar(df_sin_lic,    rutas["sin_lic"],   "_MELA_SIN")
                guardar(df_descartados, rutas["descartes"], "_DESC")

                print(
                    f"  [OK] {archivo} → "
                    f"con_lic={len(df_con_lic):,}  "
                    f"sin_lic={len(df_sin_lic):,}  "
                    f"desc={len(df_descartados):,}"
                )

            except Exception as e:
                print(f"  [!]  Error en {archivo}: {e}")

    print(f"\nFiltrado finalizado. Carpeta: {CARPETA_FILTRO}")


# =============================================================
# FASE 3 — DASHBOARD HTML
# =============================================================

# ---- Utilidades de limpieza ----

def _convertir_numero_robusto(serie: pd.Series) -> pd.Series:
    """Convierte una columna con números en formato chileno (1.234,56) a float."""
    def limpiar(x):
        if pd.isna(x):
            return 0.0
        s = str(x).strip()
        if not s:
            return 0.0
        if "." in s and "," in s:          # formato 1.234,56
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:                     # formato 1234,56
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0
    return serie.apply(limpiar)


def _limpiar_texto(x) -> str:
    if pd.isna(x):
        return "Sin dato"
    s = str(x).strip()
    return "Sin dato" if (not s or s.lower() in {"nan", "none"}) else s


def _limpiar_licitacion(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    return "" if (not s or s.lower() in {"nan", "none", "sin dato"}) else s


# ---- Función principal de la Fase 3 ----

def fase_dashboard():
    """
    Carga todos los *_MELA_LIC.csv generados en la Fase 2,
    los procesa y genera un dashboard HTML interactivo.
    """
    print("\n" + "=" * 60)
    print("  FASE 3 — GENERACIÓN DE DASHBOARD")
    print("=" * 60)

    patron   = str(Path(CARPETA_FILTRO) / "**" / "*_MELA_LIC.csv")
    archivos = glob.glob(patron, recursive=True)

    if not archivos:
        print(f"[!] No se encontraron archivos *_MELA_LIC.csv en: {CARPETA_FILTRO}")
        print("    Ejecuta primero la Fase 2 (filtrado).")
        return

    # ---- Cargar y concatenar ----
    dfs = []
    for archivo in archivos:
        try:
            df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")
            df["ARCHIVO"] = os.path.basename(archivo)
            dfs.append(df)
        except Exception as e:
            print(f"  [!]  Error cargando {archivo}: {e}")

    if not dfs:
        print("[!] No se pudo cargar ningún archivo.")
        return

    df = pd.concat(dfs, ignore_index=True)

    # ---- Asegurar columnas necesarias ----
    for col in ["LICITACIÓN", "COMPRADOR", "PROVEEDOR", "¿Para quién?",
                "FECHA O.C", "CANTIDAD", "VALOR C/U", "TOTAL", "LINK"]:
        if col not in df.columns:
            df[col] = ""

    # ---- Numéricos ----
    for col in ["CANTIDAD", "VALOR C/U", "TOTAL"]:
        df[col] = _convertir_numero_robusto(df[col])

    # ---- Textos ----
    df["COMPRADOR"]       = df["COMPRADOR"].apply(_limpiar_texto)
    df["PROVEEDOR"]       = df["PROVEEDOR"].apply(_limpiar_texto)
    df["¿Para quién?"]    = df["¿Para quién?"].apply(_limpiar_texto)
    df["LICITACIÓN_LIMPIA"] = df["LICITACIÓN"].apply(_limpiar_licitacion)

    # ---- Fecha robusta (intenta 3 formatos) ----
    raw = df["FECHA O.C"].astype(str).str.strip()
    df["FECHA_PARSEADA"] = (
        pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
        .fillna(pd.to_datetime(raw, errors="coerce"))
        .fillna(pd.to_datetime(raw, errors="coerce", dayfirst=True))
    )

    df["AÑO_NUM"]        = df["FECHA_PARSEADA"].dt.year
    df["MES_NUM"]        = df["FECHA_PARSEADA"].dt.month
    df["AÑO"]            = df["AÑO_NUM"].apply(
        lambda x: str(int(x)) if pd.notna(x) else "Sin año"
    )
    df["PERIODO_MENSUAL"] = df["FECHA_PARSEADA"].dt.strftime("%Y-%m").fillna("Sin mes")

    _MESES_ES = {
        1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril", 5:"Mayo", 6:"Junio",
        7:"Julio", 8:"Agosto", 9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"
    }
    df["MES_NOMBRE"] = df["MES_NUM"].map(_MESES_ES).fillna("Sin mes")
    df["MES_NUM"]    = df["MES_NUM"].fillna(0)

    # Descartar filas sin código de licitación real
    df = df[df["LICITACIÓN_LIMPIA"] != ""].copy()

    df["FECHA_PARSEADA"] = df["FECHA_PARSEADA"].astype(str)

    df = df.sort_values(
        by=["AÑO", "MES_NUM", "COMPRADOR", "LICITACIÓN", "FECHA O.C", "PROVEEDOR"],
        ascending=True
    ).reset_index(drop=True)

    payload = json.dumps(df.to_dict(orient="records"), ensure_ascii=False)
    print(f"  Registros en dashboard: {len(df):,}")

    # ---- Construir y guardar HTML ----
    os.makedirs(os.path.dirname(DASHBOARD_HTML), exist_ok=True)
    html = _construir_html(payload)

    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDashboard generado: {DASHBOARD_HTML}")

    # No intentar abrir el navegador en entornos sin pantalla (GitHub Actions/CI).
    if not (os.environ.get("CI") or os.environ.get("ADRI_NO_BROWSER")):
        webbrowser.open("file://" + os.path.realpath(DASHBOARD_HTML))


def _construir_html(payload: str) -> str:
    """Retorna el HTML completo del dashboard de Melatonina."""

    # Usamos marcadores para los valores Python; el resto del JS usa {{ }} escapado
    # dentro de un raw-string para evitar conflictos con f-string.
    ANIO_RANGO = f"{ANIO_INICIO}–{ANIO_FIN}"

    template = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Melatonina en compras públicas municipales — Análisis de adjudicaciones por licitación</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: 'Segoe UI', Tahoma, sans-serif;
    background: #f1f5f9;
    color: #0f172a;
    display: flex;
    height: 100vh;
    overflow: hidden;
}
.sidebar {
    width: 270px;
    background: #0f172a;
    color: white;
    overflow-y: auto;
    flex-shrink: 0;
}
.sidebar h2 {
    text-align: center;
    padding: 20px;
    margin: 0;
    background: #020617;
    font-size: 17px;
    letter-spacing: .5px;
}
.menu-item {
    padding: 14px 22px;
    cursor: pointer;
    border-left: 4px solid transparent;
    font-size: 14px;
    transition: background .15s;
}
.menu-item:hover  { background: #1e293b; }
.menu-item.active { background: #1e293b; border-left-color: #818cf8; font-weight: bold; }
.main   { flex: 1; overflow-y: auto; }
.header {
    background: white;
    padding: 16px 28px;
    box-shadow: 0 2px 5px rgba(0,0,0,.08);
    position: sticky;
    top: 0;
    z-index: 10;
}
.header h1 { margin: 0; font-size: 20px; }
.content   { padding: 26px; }
.section        { display: none; }
.section.active { display: block; }
.kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 16px;
    margin-bottom: 22px;
}
.card {
    background: white;
    padding: 18px;
    border-radius: 12px;
    border-top: 5px solid #6366f1;
    box-shadow: 0 4px 8px rgba(0,0,0,.06);
}
.card h3 { margin: 0; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.card p  { margin: 10px 0 0; font-size: 22px; font-weight: bold; }
.chart {
    background: white;
    padding: 22px;
    border-radius: 12px;
    margin-bottom: 22px;
    box-shadow: 0 4px 8px rgba(0,0,0,.06);
}
.chart h2 { margin-top: 0; font-size: 16px; border-left: 5px solid #6366f1; padding-left: 12px; }
.analysis {
    background: #eef2ff;
    border-left: 5px solid #4f46e5;
    padding: 14px 18px;
    border-radius: 10px;
    margin-bottom: 20px;
    line-height: 1.6;
    font-size: 14px;
}
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
table  { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
    background: #1e293b;
    color: white;
    padding: 10px 8px;
    position: sticky;
    top: 0;
    z-index: 2;
    text-align: left;
}
td { border-bottom: 1px solid #e2e8f0; padding: 7px 8px; vertical-align: top; }
tr:hover td { background: #f8fafc; }
.table-wrap  { max-height: 520px; overflow: auto; border-radius: 8px; }
.search-box  {
    width: 100%;
    padding: 10px 14px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-bottom: 14px;
    font-size: 14px;
}
.tab-buttons { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.tab-btn { background: #e2e8f0; color: #0f172a; border: none; padding: 9px 16px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 13px; }
.tab-btn.active { background: #0f172a; color: white; }
.base-subsection        { display: none; }
.base-subsection.active { display: block; }
.control-panel { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 16px; align-items: center; }
.control-panel label  { font-weight: bold; color: #334155; font-size: 13px; }
.control-panel select {
    padding: 8px 12px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 13px;
    min-width: 240px;
    background: white;
}
a { color: #4f46e5; }
</style>
</head>

<body>
<div class="sidebar">
    <h2>🌙 Melatonina</h2>
    <div class="menu-item active"  onclick="setView('resumen',this)">Resumen General</div>
    <div class="menu-item"         onclick="setView('municipalidades',this)">Municipalidades</div>
    <div class="menu-item"         onclick="setView('proveedores',this)">Proveedores</div>
    <div class="menu-item"         onclick="setView('licitaciones',this)">Licitaciones</div>
    <div class="menu-item"         onclick="setView('anual',this)">Desglose Anual</div>
    <div class="menu-item"         onclick="setView('mensual',this)">Desglose Mensual</div>
    <div class="menu-item"         onclick="setView('base',this)">Base Completa</div>
</div>

<div class="main">
    <div class="header"><h1 id="titulo">Resumen General</h1></div>
    <div class="content">
        <section id="resumen"         class="section active"></section>
        <section id="municipalidades" class="section"></section>
        <section id="proveedores"     class="section"></section>
        <section id="licitaciones"    class="section"></section>
        <section id="anual"           class="section"></section>
        <section id="mensual"         class="section"></section>
        <section id="base"            class="section"></section>
    </div>
</div>

<script>
// =====================================================================
// DATOS
// =====================================================================
const DATA = __PAYLOAD__;

// =====================================================================
// UTILIDADES
// =====================================================================
function formatCLP(x) { return "$" + Math.round(Number(x) || 0).toLocaleString("es-CL"); }
function formatNum(x)  { return Math.round(Number(x) || 0).toLocaleString("es-CL"); }
function unique(arr)   { return [...new Set(arr.filter(x => x != null && String(x).trim() !== ""))]; }

function escapeHTML(v) {
    return String(v ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function setView(id, el) {
    document.querySelectorAll(".section").forEach(s  => s.classList.remove("active"));
    document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("active"));
    document.getElementById(id).classList.add("active");
    el.classList.add("active");
    const titulos = {
        resumen:"Resumen General",
        municipalidades:"Municipalidades",
        proveedores:"Proveedores",
        licitaciones:"Licitaciones por Municipalidad",
        anual:"Desglose Anual",
        mensual:"Desglose Mensual",
        base:"Base Completa"
    };
    document.getElementById("titulo").innerText = titulos[id] || id;
}

function filtrarTabla(inputId, contenedorId) {
    const filtro = document.getElementById(inputId).value.toLowerCase();
    document.querySelectorAll("#" + contenedorId + " tbody tr").forEach(fila => {
        fila.style.display = fila.innerText.toLowerCase().includes(filtro) ? "" : "none";
    });
}

function tableFromRows(rows, columns) {
    let html = '<div class="table-wrap"><table><thead><tr>';
    html += columns.map(c => "<th>" + c.label + "</th>").join("");
    html += "</tr></thead><tbody>";
    rows.forEach(r => {
        html += "<tr>";
        columns.forEach(c => {
            let val = r[c.key];
            if      (c.type === "money") val = formatCLP(val);
            else if (c.type === "num")   val = formatNum(val);
            else                         val = val ?? "";
            if (c.key === "LINK" && val && val !== "") {
                html += '<td><a href="' + escapeHTML(String(val)) + '" target="_blank">Abrir</a></td>';
            } else {
                html += "<td>" + escapeHTML(String(val)) + "</td>";
            }
        });
        html += "</tr>";
    });
    html += "</tbody></table></div>";
    return html;
}

// =====================================================================
// FUNCIONES DE AGREGACIÓN
// =====================================================================

function resumenGlobal(data) {
    const total    = data.reduce((a, b) => a + Number(b["TOTAL"]    || 0), 0);
    const cantidad = data.reduce((a, b) => a + Number(b["CANTIDAD"] || 0), 0);
    return {
        total,
        cantidad,
        municipalidades: unique(data.map(r => r["COMPRADOR"])).length,
        proveedores:     unique(data.map(r => r["PROVEEDOR"])).length,
        licitaciones:    unique(data.map(r => r["LICITACIÓN_LIMPIA"])).length,
        registros:       data.length,
        precioPromedio:  cantidad > 0 ? total / cantidad : 0
    };
}

function kpisHTML(data) {
    const r = resumenGlobal(data);
    return `
    <div class="kpis">
        <div class="card"><h3>Total comprado</h3><p>${formatCLP(r.total)}</p></div>
        <div class="card" style="border-top-color:#10b981"><h3>Municipalidades</h3><p>${formatNum(r.municipalidades)}</p></div>
        <div class="card" style="border-top-color:#f59e0b"><h3>Licitaciones únicas</h3><p>${formatNum(r.licitaciones)}</p></div>
        <div class="card" style="border-top-color:#8b5cf6"><h3>Proveedores únicos</h3><p>${formatNum(r.proveedores)}</p></div>
        <div class="card" style="border-top-color:#ef4444"><h3>Registros</h3><p>${formatNum(r.registros)}</p></div>
        <div class="card" style="border-top-color:#0ea5e9"><h3>Precio promedio unit.</h3><p>${formatCLP(r.precioPromedio)}</p></div>
    </div>`;
}

function agruparPor(data, keyfn, valorfn) {
    /* Agrupador genérico. keyfn(row)->string, valorfn(acum, row)->void */
    const out = {};
    data.forEach(r => {
        const k = keyfn(r);
        if (!out[k]) out[k] = { _key: k, total: 0, cantidad: 0, registros: 0, _munis: new Set(), _lics: new Set(), _provs: new Set() };
        out[k].total    += Number(r["TOTAL"]    || 0);
        out[k].cantidad += Number(r["CANTIDAD"] || 0);
        out[k].registros++;
        out[k]._munis.add(r["COMPRADOR"]);
        out[k]._provs.add(r["PROVEEDOR"]);
        if (r["LICITACIÓN_LIMPIA"]) out[k]._lics.add(r["LICITACIÓN_LIMPIA"]);
        if (valorfn) valorfn(out[k], r);
    });
    return Object.values(out).map(x => ({
        ...x,
        municipalidades: x._munis.size,
        proveedores:     x._provs.size,
        licitaciones:    x._lics.size,
        precioPromedio:  x.cantidad > 0 ? x.total / x.cantidad : 0
    }));
}

function resumenMunicipalidad(data) {
    return agruparPor(data, r => r["COMPRADOR"] || "Sin dato")
        .map(x => ({ municipalidad: x._key, ...x }));
}

function resumenProveedor(data) {
    return agruparPor(data, r => r["PROVEEDOR"] || "Sin dato")
        .map(x => ({ proveedor: x._key, ...x }));
}

function resumenAnio(data) {
    return agruparPor(data, r => r["AÑO"] || "Sin año")
        .map(x => ({ anio: x._key, ...x }))
        .sort((a, b) => String(a.anio).localeCompare(String(b.anio)));
}

function resumenMes(data) {
    return agruparPor(data, r => r["PERIODO_MENSUAL"] || "Sin mes")
        .map(x => ({ mes: x._key, ...x }))
        .sort((a, b) => String(a.mes).localeCompare(String(b.mes)));
}

function resumenMunicipalidadAnio(data) {
    return agruparPor(data, r => (r["COMPRADOR"] || "Sin dato") + "||" + (r["AÑO"] || "Sin año"))
        .map(x => {
            const [municipalidad, anio] = x._key.split("||");
            return { municipalidad, anio, ...x };
        })
        .sort((a, b) => String(a.anio).localeCompare(String(b.anio)) || String(a.municipalidad).localeCompare(String(b.municipalidad)));
}

function resumenMunicipalidadMes(data) {
    return agruparPor(data, r => (r["COMPRADOR"] || "Sin dato") + "||" + (r["PERIODO_MENSUAL"] || "Sin mes"))
        .map(x => {
            const [municipalidad, mes] = x._key.split("||");
            return { municipalidad, mes, ...x };
        })
        .sort((a, b) => String(a.mes).localeCompare(String(b.mes)) || String(a.municipalidad).localeCompare(String(b.municipalidad)));
}

function obtenerMunicipalidades() {
    return unique(DATA.map(r => r["COMPRADOR"]))
        .filter(x => x !== "Sin dato")
        .sort((a, b) => String(a).localeCompare(String(b)));
}

function obtenerAnios() {
    return ["2021","2022","2023","2024","2025","2026"];
}

function obtenerMeses() {
    return [
        {num:1,nombre:"Enero"}, {num:2,nombre:"Febrero"}, {num:3,nombre:"Marzo"},
        {num:4,nombre:"Abril"}, {num:5,nombre:"Mayo"},    {num:6,nombre:"Junio"},
        {num:7,nombre:"Julio"}, {num:8,nombre:"Agosto"},  {num:9,nombre:"Septiembre"},
        {num:10,nombre:"Octubre"},{num:11,nombre:"Noviembre"},{num:12,nombre:"Diciembre"}
    ];
}

// =====================================================================
// SECCIÓN — RESUMEN GENERAL
// =====================================================================
function renderResumen() {
    const div     = document.getElementById("resumen");
    const porAnio = resumenAnio(DATA);
    const porMes  = resumenMes(DATA);
    const porMuni = resumenMunicipalidad(DATA).sort((a, b) => b.total - a.total);
    const top15   = porMuni.slice(0, 15).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Resumen ejecutivo — adquisiciones de melatonina bajo procedimiento licitatorio.</b><br>
            Universo de análisis: órdenes de compra (OC) de melatonina cursadas por la
            administración municipal de salud y entidades de atención primaria habilitadas,
            registradas en Mercado Público durante el periodo __ANIO_RANGO__. Criterios de
            inclusión: (i) comprador del subsector municipal o entidad de la red habilitada;
            (ii) estado de la OC <i>Aceptada</i> o <i>Recepción Conforme</i>; (iii) deduplicación
            exacta; y (iv) código de licitación válido. A diferencia de la zopiclona, la
            melatonina no presenta derivados, por lo que el principio activo es homogéneo y
            no requiere clasificación por presentación. Montos en pesos chilenos (CLP),
            total neto por línea.
        </div>

        ${kpisHTML(DATA)}

        <div class="grid2">
            <div class="chart">
                <h2>Gasto total por año</h2>
                <div id="res_anual"></div>
            </div>
            <div class="chart">
                <h2>Evolución mensual de gasto</h2>
                <div id="res_mensual"></div>
            </div>
        </div>

        <div class="chart">
            <h2>Top 15 municipalidades por gasto total</h2>
            <div id="res_top_muni"></div>
        </div>
    `;

    Plotly.newPlot("res_anual", [{
        x: porAnio.map(x => x.anio),
        y: porAnio.map(x => x.total),
        type: "bar",
        marker: { color: "#6366f1" },
        text: porAnio.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], { template: "plotly_white", yaxis: { title: "Total comprado (CLP)" }, xaxis: { title: "Año" } });

    Plotly.newPlot("res_mensual", [{
        x: porMes.map(x => x.mes),
        y: porMes.map(x => x.total),
        type: "scatter",
        mode: "lines+markers",
        fill: "tozeroy",
        line: { color: "#6366f1" },
        marker: { color: "#6366f1" }
    }], { template: "plotly_white", yaxis: { title: "Total comprado (CLP)" }, xaxis: { title: "Mes" } });

    Plotly.newPlot("res_top_muni", [{
        x: top15.map(x => x.total),
        y: top15.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        marker: { color: "#6366f1" },
        text: top15.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], { template: "plotly_white", margin: { l: 390, t: 10 }, xaxis: { title: "Total comprado (CLP)" } });
}

// =====================================================================
// SECCIÓN — MUNICIPALIDADES
// =====================================================================
function renderMunicipalidades() {
    const div    = document.getElementById("municipalidades");
    const porMuni = resumenMunicipalidad(DATA).sort((a, b) => b.total - a.total);
    const top20  = porMuni.slice(0, 20).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Caracterización de la demanda por comprador municipal.</b><br>
            Distribución del gasto adjudicado entre las entidades municipales que
            adquirieron melatonina por licitación. El precio promedio se calcula ponderado
            por unidades (gasto total / cantidad total), evitando el sesgo del promedio
            simple ante volúmenes heterogéneos. Permite identificar a los compradores que
            concentran el gasto y comparar su nivel de precios efectivo.
        </div>
        ${kpisHTML(DATA)}
        <div class="chart">
            <h2>Top 20 municipalidades por gasto total</h2>
            <div id="muni_top"></div>
        </div>
        <div class="chart">
            <h2>Tabla detallada de municipalidades</h2>
            <input class="search-box" id="search_muni" placeholder="Buscar municipalidad..."
                   onkeyup="filtrarTabla('search_muni','tabla_muni')">
            <div id="tabla_muni"></div>
        </div>
    `;

    Plotly.newPlot("muni_top", [{
        x: top20.map(x => x.total),
        y: top20.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        marker: { color: "#6366f1" },
        text: top20.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], { template: "plotly_white", margin: { l: 390, t: 10 }, xaxis: { title: "Total comprado (CLP)" } });

    document.getElementById("tabla_muni").innerHTML = tableFromRows(porMuni, [
        { key: "municipalidad",  label: "Municipalidad" },
        { key: "total",          label: "Total comprado",           type: "money" },
        { key: "cantidad",       label: "Unidades compradas",       type: "num" },
        { key: "licitaciones",   label: "Licitaciones únicas",      type: "num" },
        { key: "proveedores",    label: "Proveedores distintos",    type: "num" },
        { key: "registros",      label: "Registros",                type: "num" },
        { key: "precioPromedio", label: "Precio promedio pond.",    type: "money" },
    ]);
}

// =====================================================================
// SECCIÓN — PROVEEDORES
// =====================================================================
function renderProveedores() {
    const div    = document.getElementById("proveedores");
    const porProv = resumenProveedor(DATA).sort((a, b) => b.total - a.total);
    const top20  = porProv.slice(0, 20).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Estructura de la oferta: proveedores adjudicatarios.</b><br>
            Empresas que resultaron adjudicatarias del suministro de melatonina por
            licitación, ordenadas por monto total adjudicado. El precio promedio ponderado
            por proveedor permite detectar dispersión de precios entre oferentes y evaluar
            el grado de concentración del mercado (número de proveedores frente a la
            participación de los principales en el gasto total).
        </div>
        <div class="chart">
            <h2>Top 20 proveedores por gasto total adjudicado</h2>
            <div id="prov_top"></div>
        </div>
        <div class="chart">
            <h2>Tabla de proveedores</h2>
            <input class="search-box" id="search_prov" placeholder="Buscar proveedor..."
                   onkeyup="filtrarTabla('search_prov','tabla_prov')">
            <div id="tabla_prov"></div>
        </div>
    `;

    Plotly.newPlot("prov_top", [{
        x: top20.map(x => x.total),
        y: top20.map(x => x.proveedor),
        type: "bar",
        orientation: "h",
        marker: { color: "#10b981" },
        text: top20.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], { template: "plotly_white", margin: { l: 390, t: 10 }, xaxis: { title: "Total adjudicado (CLP)" } });

    document.getElementById("tabla_prov").innerHTML = tableFromRows(porProv, [
        { key: "proveedor",      label: "Proveedor" },
        { key: "total",          label: "Total adjudicado",         type: "money" },
        { key: "cantidad",       label: "Unidades vendidas",        type: "num" },
        { key: "municipalidades",label: "Municipalidades atendidas",type: "num" },
        { key: "licitaciones",   label: "Licitaciones",             type: "num" },
        { key: "registros",      label: "Registros",                type: "num" },
        { key: "precioPromedio", label: "Precio promedio pond.",    type: "money" },
    ]);
}

// =====================================================================
// SECCIÓN — LICITACIONES
// =====================================================================
function renderLicitaciones() {
    const div  = document.getElementById("licitaciones");
    const rows = resumenMunicipalidad(DATA).sort((a, b) => b.licitaciones - a.licitaciones || b.total - a.total);
    const top20 = rows.slice(0, 20).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Concentración de procesos licitatorios por comprador.</b><br>
            Recuento de licitaciones únicas (identificadas por su código) adjudicadas a
            cada entidad municipal. Dado que una licitación puede originar múltiples
            órdenes de compra, este indicador mide actividad contractual y no volumen
            transado; opera como proxy de la intensidad de uso del mecanismo licitatorio.
        </div>
        <div class="chart">
            <h2>Ranking: licitaciones adjudicadas por municipalidad</h2>
            <div id="lic_chart"></div>
        </div>
        <div class="chart">
            <h2>Tabla de licitaciones por municipalidad</h2>
            <input class="search-box" id="search_lic" placeholder="Buscar municipalidad..."
                   onkeyup="filtrarTabla('search_lic','tabla_lic')">
            <div id="tabla_lic"></div>
        </div>
    `;

    Plotly.newPlot("lic_chart", [{
        x: top20.map(x => x.licitaciones),
        y: top20.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        marker: { color: "#10b981" },
        text: top20.map(x => x.licitaciones),
        textposition: "auto"
    }], { template: "plotly_white", margin: { l: 390, t: 10 }, xaxis: { title: "Licitaciones adjudicadas" } });

    document.getElementById("tabla_lic").innerHTML = tableFromRows(rows, [
        { key: "municipalidad",  label: "Municipalidad" },
        { key: "licitaciones",   label: "Licitaciones únicas",   type: "num" },
        { key: "total",          label: "Total comprado",        type: "money" },
        { key: "cantidad",       label: "Unidades",              type: "num" },
        { key: "registros",      label: "Registros",             type: "num" },
        { key: "precioPromedio", label: "Precio promedio pond.", type: "money" },
    ]);
}

// =====================================================================
// SECCIÓN — DESGLOSE ANUAL
// =====================================================================
function actualizarGraficoAnual() {
    const muni     = document.getElementById("sel_muni_anual").value;
    const metrica  = document.getElementById("sel_met_anual").value;
    const dataMuni = DATA.filter(r => r["COMPRADOR"] === muni);
    const anios    = obtenerAnios();
    const isTotal  = metrica === "total";

    const y = anios.map(a => {
        const rows = dataMuni.filter(r => r["AÑO"] === a);
        if (isTotal) return rows.reduce((s, r) => s + Number(r["TOTAL"] || 0), 0);
        if (metrica === "licitaciones") return new Set(rows.filter(r => r["LICITACIÓN_LIMPIA"]).map(r => r["LICITACIÓN_LIMPIA"])).size;
        return rows.length; // registros
    });

    Plotly.newPlot("graf_anual", [{
        x: anios,
        y: y,
        type: "bar",
        marker: { color: "#6366f1" },
        text: y.map(v => v > 0 ? (isTotal ? formatCLP(v) : formatNum(v)) : ""),
        textposition: "outside",
        cliponaxis: false
    }], {
        template: "plotly_white",
        title: (isTotal ? "Gasto total" : metrica === "licitaciones" ? "Licitaciones" : "Registros") + " por año — " + muni,
        xaxis: { title: "Año", type: "category", categoryorder: "array", categoryarray: anios },
        yaxis: { title: isTotal ? "Total comprado (CLP)" : (metrica === "licitaciones" ? "Licitaciones" : "Registros"), rangemode: "tozero" },
        margin: { l: 80, r: 40, t: 80, b: 80 }
    }, { responsive: true });
}

function renderAnual() {
    const div    = document.getElementById("anual");
    const rows   = resumenMunicipalidadAnio(DATA);
    const munis  = obtenerMunicipalidades();
    const m0     = munis[0] || "";

    const porAnioGlobal = resumenAnio(DATA);

    div.innerHTML = `
        <div class="analysis">
            <b>Serie anual: agregado del sistema y desagregado por comprador.</b><br>
            La vista global describe la trayectoria interanual del gasto en melatonina del
            conjunto del subsector municipal; el selector permite aislar el comportamiento
            de una entidad específica. Facilita distinguir tendencias sistémicas de
            dinámicas particulares y detectar la incorporación de nuevos compradores a lo
            largo de la serie.
        </div>

        <div class="chart">
            <h2>Gasto global por año (todas las municipalidades)</h2>
            <div id="graf_anual_global"></div>
        </div>

        <div class="chart">
            <h2>Gráfico por municipalidad</h2>
            <div class="control-panel">
                <label>Municipalidad:</label>
                <select id="sel_muni_anual" onchange="actualizarGraficoAnual()">
                    ${munis.map(m => `<option value="${escapeHTML(m)}">${escapeHTML(m)}</option>`).join("")}
                </select>
                <label>Métrica:</label>
                <select id="sel_met_anual" onchange="actualizarGraficoAnual()">
                    <option value="total">Total comprado</option>
                    <option value="licitaciones">Licitaciones</option>
                    <option value="registros">Registros</option>
                </select>
            </div>
            <div id="graf_anual"></div>
        </div>

        <div class="chart">
            <h2>Tabla anual por municipalidad</h2>
            <input class="search-box" id="search_anual" placeholder="Buscar municipalidad o año..."
                   onkeyup="filtrarTabla('search_anual','tabla_anual')">
            <div id="tabla_anual"></div>
        </div>
    `;

    // Gráfico global
    Plotly.newPlot("graf_anual_global", [{
        x: porAnioGlobal.map(x => x.anio),
        y: porAnioGlobal.map(x => x.total),
        type: "bar",
        marker: { color: "#6366f1" },
        text: porAnioGlobal.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], { template: "plotly_white", yaxis: { title: "Total comprado (CLP)" }, xaxis: { title: "Año" } });

    document.getElementById("tabla_anual").innerHTML = tableFromRows(rows, [
        { key: "anio",          label: "Año" },
        { key: "municipalidad", label: "Municipalidad" },
        { key: "total",         label: "Total comprado", type: "money" },
        { key: "cantidad",      label: "Cantidad",       type: "num" },
        { key: "licitaciones",  label: "Licitaciones",   type: "num" },
        { key: "registros",     label: "Registros",      type: "num" },
    ]);

    if (m0) {
        document.getElementById("sel_muni_anual").value = m0;
        actualizarGraficoAnual();
    }
}

// =====================================================================
// SECCIÓN — DESGLOSE MENSUAL
// =====================================================================
function actualizarGraficoMensual() {
    const muni       = document.getElementById("sel_muni_mensual").value;
    const anio       = document.getElementById("sel_anio_mensual").value;
    const metrica    = document.getElementById("sel_met_mensual").value;
    const isTotal    = metrica === "total";
    const meses      = obtenerMeses();
    const dataMuniAnio = DATA.filter(r => r["COMPRADOR"] === muni && r["AÑO"] === anio);

    const y = meses.map(m => {
        const rows = dataMuniAnio.filter(r => Number(r["MES_NUM"]) === m.num);
        if (isTotal) return rows.reduce((s, r) => s + Number(r["TOTAL"] || 0), 0);
        if (metrica === "licitaciones") return new Set(rows.filter(r => r["LICITACIÓN_LIMPIA"]).map(r => r["LICITACIÓN_LIMPIA"])).size;
        return rows.length;
    });

    Plotly.newPlot("graf_mensual", [{
        x: meses.map(m => m.nombre),
        y: y,
        type: "bar",
        marker: { color: "#6366f1" },
        text: y.map(v => v > 0 ? (isTotal ? formatCLP(v) : formatNum(v)) : ""),
        textposition: "outside",
        cliponaxis: false
    }], {
        template: "plotly_white",
        title: (isTotal ? "Gasto total" : metrica === "licitaciones" ? "Licitaciones" : "Registros") + " mensual — " + muni + " — " + anio,
        xaxis: { title: "Mes", type: "category", categoryorder: "array", categoryarray: meses.map(m => m.nombre) },
        yaxis: { title: isTotal ? "Total comprado (CLP)" : (metrica === "licitaciones" ? "Licitaciones" : "Registros"), rangemode: "tozero" },
        margin: { l: 80, r: 40, t: 80, b: 100 }
    }, { responsive: true });
}

function renderMensual() {
    const div   = document.getElementById("mensual");
    const rows  = resumenMunicipalidadMes(DATA);
    const munis = obtenerMunicipalidades();
    const anios = obtenerAnios();
    const m0 = munis[0] || "";
    const a0 = anios[0] || "";

    div.innerHTML = `
        <div class="analysis">
            <b>Resolución mensual intra-anual.</b><br>
            Distribución del gasto a nivel mensual para la entidad y el año seleccionados.
            Permite examinar la estacionalidad de la demanda, la concentración de
            adjudicaciones en periodos puntuales y la regularidad del abastecimiento dentro
            del ejercicio presupuestario.
        </div>
        <div class="chart">
            <h2>Gráfico mensual por municipalidad y año</h2>
            <div class="control-panel">
                <label>Municipalidad:</label>
                <select id="sel_muni_mensual" onchange="actualizarGraficoMensual()">
                    ${munis.map(m => `<option value="${escapeHTML(m)}">${escapeHTML(m)}</option>`).join("")}
                </select>
                <label>Año:</label>
                <select id="sel_anio_mensual" onchange="actualizarGraficoMensual()">
                    ${anios.map(a => `<option value="${escapeHTML(a)}">${escapeHTML(a)}</option>`).join("")}
                </select>
                <label>Métrica:</label>
                <select id="sel_met_mensual" onchange="actualizarGraficoMensual()">
                    <option value="total">Total comprado</option>
                    <option value="licitaciones">Licitaciones</option>
                    <option value="registros">Registros</option>
                </select>
            </div>
            <div id="graf_mensual"></div>
        </div>
        <div class="chart">
            <h2>Tabla mensual por municipalidad</h2>
            <input class="search-box" id="search_mensual" placeholder="Buscar municipalidad o mes..."
                   onkeyup="filtrarTabla('search_mensual','tabla_mensual')">
            <div id="tabla_mensual"></div>
        </div>
    `;

    document.getElementById("tabla_mensual").innerHTML = tableFromRows(rows, [
        { key: "mes",           label: "Mes" },
        { key: "municipalidad", label: "Municipalidad" },
        { key: "total",         label: "Total comprado", type: "money" },
        { key: "cantidad",      label: "Cantidad",       type: "num" },
        { key: "licitaciones",  label: "Licitaciones",   type: "num" },
        { key: "registros",     label: "Registros",      type: "num" },
    ]);

    if (m0 && a0) {
        document.getElementById("sel_muni_mensual").value = m0;
        document.getElementById("sel_anio_mensual").value = a0;
        actualizarGraficoMensual();
    }
}

// =====================================================================
// SECCIÓN — BASE COMPLETA
// =====================================================================
function setBaseTab(id, el) {
    document.querySelectorAll(".base-subsection").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
}

function renderTablaBase(id, titulo, data) {
    const columnas = [
        "AÑO", "PERIODO_MENSUAL", "COMPRADOR", "LICITACIÓN",
        "PROVEEDOR", "¿Para quién?", "FECHA O.C",
        "CANTIDAD", "VALOR C/U", "TOTAL", "LINK", "ARCHIVO"
    ];
    let html = `<div id="${id}" class="base-subsection">
        <div class="analysis"><b>${titulo}</b><br>Registros: <b>${formatNum(data.length)}</b>. Solo compras con licitación.</div>
        <input class="search-box" id="search_${id}" placeholder="Buscar dentro de ${titulo}..."
               onkeyup="filtrarTabla('search_${id}','${id}')">
        <div class="table-wrap"><table><thead><tr>`;
    html += columnas.map(c => `<th>${c}</th>`).join("");
    html += "</tr></thead><tbody>";

    data.forEach(r => {
        html += "<tr>";
        columnas.forEach(c => {
            let val = r[c] ?? "";
            if ((c === "TOTAL" || c === "VALOR C/U") && val !== "") {
                val = Number(val || 0).toLocaleString("es-CL");
            }
            if (c === "LINK" && val !== "") {
                html += `<td><a href="${escapeHTML(String(val))}" target="_blank">Abrir</a></td>`;
            } else {
                html += `<td>${escapeHTML(String(val))}</td>`;
            }
        });
        html += "</tr>";
    });
    html += "</tbody></table></div></div>";
    return html;
}

function renderBase() {
    const div = document.getElementById("base");
    div.innerHTML = `
        <div class="analysis">
            <b>Base de datos analítica — registro a nivel de línea de orden de compra.</b><br>
            Conjunto depurado y trazable que sustenta todos los indicadores del tablero.
            Cada fila corresponde a una línea de OC de melatonina con licitación válida,
            confirmada y no duplicada. El buscador permite filtrar por cualquier campo y el
            enlace de cada registro remite a la OC original en Mercado Público, asegurando
            la verificabilidad de la fuente.
        </div>
        <div class="chart">
            <div class="tab-buttons">
                <button class="tab-btn active" onclick="setBaseTab('base_todo',this)">Todos los registros</button>
            </div>
            ${renderTablaBase("base_todo", "Base completa — Melatonina con licitación", DATA)}
        </div>
    `;
    document.getElementById("base_todo").classList.add("active");
}

// =====================================================================
// RENDER INICIAL
// =====================================================================
renderResumen();
renderMunicipalidades();
renderProveedores();
renderLicitaciones();
renderAnual();
renderMensual();
renderBase();

</script>
</body>
</html>"""

    html = template.replace("__PAYLOAD__", payload)
    html = html.replace("__ANIO_RANGO__", ANIO_RANGO)
    return html


# =============================================================
# MAIN
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline unificado de Melatonina — Tesis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python melatonina_pipeline.py           # corre las 3 fases\n"
            "  python melatonina_pipeline.py --fase 1  # solo extracción\n"
            "  python melatonina_pipeline.py --fase 2  # solo filtrado\n"
            "  python melatonina_pipeline.py --fase 3  # solo dashboard\n"
        )
    )
    parser.add_argument(
        "--fase",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Fase a ejecutar (1, 2 o 3). Sin argumento: ejecuta las 3 en orden."
    )
    args = parser.parse_args()

    if args.fase is None:
        fase_extraccion()
        fase_filtrado()
        fase_dashboard()
    elif args.fase == 1:
        fase_extraccion()
    elif args.fase == 2:
        fase_filtrado()
    elif args.fase == 3:
        fase_dashboard()


if __name__ == "__main__":
    main()
