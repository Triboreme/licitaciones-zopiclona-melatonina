import pandas as pd
import json
from pathlib import Path
import os
import glob
import webbrowser

from config_rutas import ZOPICLONA_FILTRADOS
from filtros_comunes import corregir_comprador

# =========================================================
# 1. CONFIGURACIÓN (rutas centralizadas en config_rutas.py)
# =========================================================

ROOT = ZOPICLONA_FILTRADOS
OUT_HTML = ROOT / "Dashboard_Zopiclona_SOLO_LICITACION_Pura_Eszopiclona.html"

# =========================================================
# 2. FUNCIONES PYTHON
# =========================================================

def convertir_numero_robusto(serie):
    def limpiar(x):
        if pd.isna(x):
            return 0

        s = str(x).strip()

        if s == "":
            return 0

        # Formato chileno con miles y decimal: 1.234,56 -> 1234.56
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")

        # Solo coma decimal: 1234,56 -> 1234.56
        elif "," in s:
            s = s.replace(",", ".")

        # Varios puntos = separadores de miles: 1.234.567 -> 1234567
        elif s.count(".") > 1:
            s = s.replace(".", "")

        # Un solo punto: desambiguar miles vs decimal.
        # "1.234"/"100.000" (3 dígitos tras el punto) es separador de miles;
        # "12250.0"/"21.73" (1-2 dígitos) es decimal y se conserva tal cual.
        elif "." in s:
            entero, _, dec = s.partition(".")
            if len(dec) == 3:
                s = entero + dec

        try:
            return float(s)
        except:
            return 0

    return serie.apply(limpiar)


def limpiar_texto(x):
    if pd.isna(x):
        return "Sin dato"

    s = str(x).strip()

    if s == "" or s.lower() in ["nan", "none"]:
        return "Sin dato"

    return s


def limpiar_licitacion(x):
    if pd.isna(x):
        return ""

    s = str(x).strip()

    if s == "" or s.lower() in ["nan", "none", "sin dato"]:
        return ""

    return s


def detectar_categoria_solo_licitacion(nombre_archivo):
    nombre = nombre_archivo.upper()

    # IMPORTANTE:
    # Este dashboard SOLO considera archivos con licitación.
    # Ignora PURA_SIN y DERIV_SIN.
    if "PURA_LIC" in nombre:
        return "Zopiclona con Licitación", "Zopiclona", "Con Licitación"

    elif "DERIV_LIC" in nombre:
        return "Eszopiclona con Licitación", "Eszopiclona", "Con Licitación"

    else:
        return None, None, None


# =========================================================
# 3. CARGA DE DATOS
# =========================================================

archivos = glob.glob(str(ROOT / "**" / "*.csv"), recursive=True)

dfs = []

for archivo in archivos:
    nombre_archivo = os.path.basename(archivo)

    categoria, tipo_producto, mecanismo = detectar_categoria_solo_licitacion(nombre_archivo)

    if categoria is None:
        continue

    try:
        df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")

        df["CATEGORIA"] = categoria
        df["TIPO_PRODUCTO"] = tipo_producto
        df["MECANISMO"] = mecanismo
        df["ARCHIVO"] = nombre_archivo

        dfs.append(df)

    except Exception as e:
        print(f"Error cargando {archivo}: {e}")


if not dfs:
    raise FileNotFoundError(
        "No se encontraron archivos con licitación. "
        "Revisa que existan archivos con nombres tipo *_PURA_LIC.csv o *_DERIV_LIC.csv."
    )


df_total = pd.concat(dfs, ignore_index=True)

# =========================================================
# 4. LIMPIEZA SIN BORRAR INFORMACIÓN
# =========================================================

columnas_necesarias = [
    "LICITACIÓN",
    "COMPRADOR",
    "PROVEEDOR",
    "¿Para quién?",
    "FECHA O.C",
    "CANTIDAD",
    "VALOR C/U",
    "TOTAL",
    "LINK"
]

for col in columnas_necesarias:
    if col not in df_total.columns:
        df_total[col] = ""

# Numéricos
for col in ["CANTIDAD", "VALOR C/U", "TOTAL"]:
    df_total[col] = convertir_numero_robusto(df_total[col])

# Textos
df_total["COMPRADOR"] = df_total["COMPRADOR"].apply(limpiar_texto).apply(corregir_comprador)
df_total["PROVEEDOR"] = df_total["PROVEEDOR"].apply(limpiar_texto)
df_total["¿Para quién?"] = df_total["¿Para quién?"].apply(limpiar_texto)
df_total["LICITACIÓN_LIMPIA"] = df_total["LICITACIÓN"].apply(limpiar_licitacion)

# =========================================================
# 4.1 FECHA ROBUSTA
# =========================================================

df_total["FECHA O.C"] = df_total["FECHA O.C"].astype(str).str.strip()

fecha_1 = pd.to_datetime(
    df_total["FECHA O.C"],
    format="%Y-%m-%d",
    errors="coerce"
)

fecha_2 = pd.to_datetime(
    df_total["FECHA O.C"],
    errors="coerce"
)

fecha_3 = pd.to_datetime(
    df_total["FECHA O.C"],
    errors="coerce",
    dayfirst=True
)

df_total["FECHA_PARSEADA"] = fecha_1.fillna(fecha_2).fillna(fecha_3)

df_total["AÑO_NUM"] = df_total["FECHA_PARSEADA"].dt.year
df_total["MES_NUM"] = df_total["FECHA_PARSEADA"].dt.month

df_total["AÑO"] = df_total["AÑO_NUM"].apply(
    lambda x: str(int(x)) if pd.notna(x) else "Sin año"
)

df_total["PERIODO_MENSUAL"] = df_total["FECHA_PARSEADA"].dt.strftime("%Y-%m")
df_total["PERIODO_MENSUAL"] = df_total["PERIODO_MENSUAL"].fillna("Sin mes")

meses_es = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre"
}

df_total["MES_NOMBRE"] = df_total["MES_NUM"].map(meses_es).fillna("Sin mes")
df_total["MES_NUM"] = df_total["MES_NUM"].fillna(0)

# Por seguridad: eliminar filas sin licitación real
df_total = df_total[df_total["LICITACIÓN_LIMPIA"] != ""].copy()

# Para evitar problemas con JSON
df_total["FECHA_PARSEADA"] = df_total["FECHA_PARSEADA"].astype(str)

# Orden base
df_total = df_total.sort_values(
    by=[
        "TIPO_PRODUCTO",
        "AÑO",
        "MES_NUM",
        "COMPRADOR",
        "LICITACIÓN",
        "FECHA O.C",
        "PROVEEDOR"
    ],
    ascending=True
).reset_index(drop=True)

payload = json.dumps(df_total.to_dict(orient="records"), ensure_ascii=False)

# =========================================================
# 5. HTML
# =========================================================

html = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="robots" content="noindex, nofollow">
<title>Zopiclona en compras públicas municipales — Análisis de adjudicaciones por licitación</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>

<style>
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
    width: 330px;
    background: #0f172a;
    color: white;
    overflow-y: auto;
}

.sidebar h2 {
    text-align: center;
    padding: 22px;
    margin: 0;
    background: #020617;
    font-size: 20px;
}

.menu-item {
    padding: 15px 24px;
    cursor: pointer;
    border-left: 4px solid transparent;
}

.menu-item:hover {
    background: #1e293b;
}

.menu-item.active {
    background: #1e293b;
    border-left: 4px solid #3b82f6;
    font-weight: bold;
}

.main {
    flex: 1;
    overflow-y: auto;
}

.header {
    background: white;
    padding: 20px 30px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.08);
    position: sticky;
    top: 0;
    z-index: 10;
}

.header h1 {
    margin: 0;
}

.content {
    padding: 30px;
}

.section {
    display: none;
}

.section.active {
    display: block;
}

.kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 20px;
    margin-bottom: 25px;
}

.card {
    background: white;
    padding: 20px;
    border-radius: 12px;
    border-top: 5px solid #3b82f6;
    box-shadow: 0 4px 8px rgba(0,0,0,0.06);
}

.card h3 {
    margin: 0;
    color: #64748b;
    font-size: 13px;
    text-transform: uppercase;
}

.card p {
    margin: 10px 0 0;
    font-size: 24px;
    font-weight: bold;
}

.chart {
    background: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 25px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.06);
}

.chart h2 {
    margin-top: 0;
    font-size: 19px;
    border-left: 5px solid #3b82f6;
    padding-left: 12px;
}

.analysis {
    background: #eff6ff;
    border-left: 5px solid #2563eb;
    padding: 18px;
    border-radius: 10px;
    margin-bottom: 25px;
    line-height: 1.5;
}

.grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 25px;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

th {
    background: #1e293b;
    color: white;
    padding: 10px;
    position: sticky;
    top: 0;
    z-index: 2;
}

td {
    border-bottom: 1px solid #e2e8f0;
    padding: 8px;
    vertical-align: top;
}

.table-wrap {
    max-height: 560px;
    overflow: auto;
}

.search-box {
    width: 100%;
    padding: 12px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-bottom: 15px;
    font-size: 14px;
}

.tab-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 18px;
}

.tab-btn {
    background: #e2e8f0;
    color: #0f172a;
    border: none;
    padding: 10px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: bold;
}

.tab-btn.active {
    background: #0f172a;
    color: white;
}

.base-subsection {
    display: none;
}

.base-subsection.active {
    display: block;
}

.control-panel {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    margin-bottom: 18px;
    align-items: center;
}

.control-panel label {
    font-weight: bold;
    color: #334155;
}

.control-panel select {
    padding: 10px 12px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 14px;
    min-width: 280px;
    background: white;
}

</style>
</head>

<body>

<div class="sidebar">
    <h2>Zopiclona</h2>
    <div class="menu-item active" onclick="setView('resumen', this)">Resumen Solo Licitación</div>
    <div class="menu-item" onclick="setView('comparativo', this)">Zopiclona vs Eszopiclona</div>
    <div class="menu-item" onclick="setView('pura', this)">Zopiclona con Licitación</div>
    <div class="menu-item" onclick="setView('derivados', this)">Eszopiclona con Licitación</div>
    <div class="menu-item" onclick="setView('licitaciones', this)">Licitaciones por Municipalidad</div>
    <div class="menu-item" onclick="setView('proveedores', this)">Proveedores</div>
    <div class="menu-item" onclick="setView('anual', this)">Desglose Anual</div>
    <div class="menu-item" onclick="setView('mensual', this)">Desglose Mensual</div>
    <div class="menu-item" onclick="setView('base', this)">Base Completa</div>
</div>

<div class="main">
    <div class="header">
        <h1 id="titulo">Resumen Solo Licitación</h1>
    </div>

    <div class="content">
        <section id="resumen" class="section active"></section>
        <section id="comparativo" class="section"></section>
        <section id="pura" class="section"></section>
        <section id="derivados" class="section"></section>
        <section id="licitaciones" class="section"></section>
        <section id="proveedores" class="section"></section>
        <section id="anual" class="section"></section>
        <section id="mensual" class="section"></section>
        <section id="base" class="section"></section>
    </div>
</div>

<script>
const DATA = __PAYLOAD__;

function formatCLP(x) {
    return "$" + Math.round(Number(x) || 0).toLocaleString("es-CL");
}

function formatNum(x) {
    return Math.round(Number(x) || 0).toLocaleString("es-CL");
}

function setView(id, el) {
    document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");

    document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("active"));
    el.classList.add("active");

    const titulos = {
        resumen: "Resumen Solo Licitación",
        comparativo: "Comparativo Zopiclona vs Eszopiclona",
        pura: "Zopiclona con Licitación",
        derivados: "Eszopiclona con Licitación",
        licitaciones: "Licitaciones por Municipalidad",
        proveedores: "Proveedores",
        anual: "Desglose Anual",
        mensual: "Desglose Mensual",
        base: "Base Completa Solo Licitación"
    };

    document.getElementById("titulo").innerText = titulos[id];
}

function unique(arr) {
    return [...new Set(
        arr.filter(x => x !== null && x !== undefined && String(x).trim() !== "")
    )];
}

function resumenGlobal(data) {
    const total = data.reduce((a,b) => a + Number(b["TOTAL"] || 0), 0);
    const cantidad = data.reduce((a,b) => a + Number(b["CANTIDAD"] || 0), 0);
    const municipalidades = unique(data.map(r => r["COMPRADOR"]));
    const licitaciones = unique(data.map(r => r["LICITACIÓN_LIMPIA"]));
    const anios = unique(data.map(r => r["AÑO"]));
    const meses = unique(data.map(r => r["PERIODO_MENSUAL"]));

    return {
        total,
        cantidad,
        municipalidades: municipalidades.length,
        licitaciones: licitaciones.length,
        anios: anios.length,
        meses: meses.length,
        registros: data.length,
        precioPromedio: cantidad > 0 ? total / cantidad : 0
    };
}

function kpisHTML(data) {
    const r = resumenGlobal(data);

    return `
    <div class="kpis">
        <div class="card">
            <h3>Total comprado</h3>
            <p>${formatCLP(r.total)}</p>
        </div>
        <div class="card" style="border-top-color:#10b981">
            <h3>Municipalidades</h3>
            <p>${formatNum(r.municipalidades)}</p>
        </div>
        <div class="card" style="border-top-color:#f59e0b">
            <h3>Licitaciones</h3>
            <p>${formatNum(r.licitaciones)}</p>
        </div>
        <div class="card" style="border-top-color:#8b5cf6">
            <h3>Registros</h3>
            <p>${formatNum(r.registros)}</p>
        </div>
    </div>`;
}

function filtrarTabla(inputId, contenedorId) {
    const filtro = document.getElementById(inputId).value.toLowerCase();
    const filas = document.querySelectorAll(`#${contenedorId} tbody tr`);

    filas.forEach(fila => {
        const texto = fila.innerText.toLowerCase();
        fila.style.display = texto.includes(filtro) ? "" : "none";
    });
}

function tableFromRows(rows, columns) {
    let html = `
    <div class="table-wrap">
        <table>
            <thead>
                <tr>${columns.map(c => `<th>${c.label}</th>`).join("")}</tr>
            </thead>
            <tbody>
    `;

    rows.forEach(r => {
        html += "<tr>";

        columns.forEach(c => {
            let val = r[c.key];

            if (c.type === "money") {
                val = formatCLP(val);
            } else if (c.type === "num") {
                val = formatNum(val);
            } else {
                val = val ?? "";
            }

            html += `<td>${escapeHTML(String(val))}</td>`;
        });

        html += "</tr>";
    });

    html += `
            </tbody>
        </table>
    </div>`;

    return html;
}

function resumenMunicipalidad(data) {
    let out = {};

    data.forEach(r => {
        const muni = r["COMPRADOR"] || "Sin dato";

        if (!out[muni]) {
            out[muni] = {
                municipalidad: muni,
                total: 0,
                cantidad: 0,
                registros: 0,
                licitacionesSet: new Set()
            };
        }

        out[muni].total += Number(r["TOTAL"] || 0);
        out[muni].cantidad += Number(r["CANTIDAD"] || 0);
        out[muni].registros += 1;

        if (r["LICITACIÓN_LIMPIA"]) {
            out[muni].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        municipalidad: x.municipalidad,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        licitaciones: x.licitacionesSet.size,
        precioPromedio: x.cantidad > 0 ? x.total / x.cantidad : 0
    }));
}

function resumenProveedor(data) {
    let out = {};

    data.forEach(r => {
        const prov = r["PROVEEDOR"] || "Sin dato";

        if (!out[prov]) {
            out[prov] = {
                proveedor: prov,
                total: 0,
                cantidad: 0,
                registros: 0,
                municipalidadesSet: new Set(),
                licitacionesSet: new Set()
            };
        }

        out[prov].total += Number(r["TOTAL"] || 0);
        out[prov].cantidad += Number(r["CANTIDAD"] || 0);
        out[prov].registros += 1;
        out[prov].municipalidadesSet.add(r["COMPRADOR"]);

        if (r["LICITACIÓN_LIMPIA"]) {
            out[prov].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        proveedor: x.proveedor,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        municipalidades: x.municipalidadesSet.size,
        licitaciones: x.licitacionesSet.size,
        precioPromedio: x.cantidad > 0 ? x.total / x.cantidad : 0
    }));
}

function resumenCategoria(data) {
    let out = {};

    data.forEach(r => {
        const cat = r["TIPO_PRODUCTO"] || "Sin dato";

        if (!out[cat]) {
            out[cat] = {
                categoria: cat,
                total: 0,
                cantidad: 0,
                registros: 0,
                municipalidadesSet: new Set(),
                licitacionesSet: new Set()
            };
        }

        out[cat].total += Number(r["TOTAL"] || 0);
        out[cat].cantidad += Number(r["CANTIDAD"] || 0);
        out[cat].registros += 1;
        out[cat].municipalidadesSet.add(r["COMPRADOR"]);

        if (r["LICITACIÓN_LIMPIA"]) {
            out[cat].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        categoria: x.categoria,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        municipalidades: x.municipalidadesSet.size,
        licitaciones: x.licitacionesSet.size,
        precioPromedio: x.cantidad > 0 ? x.total / x.cantidad : 0
    }));
}

function resumenCategoriaAnio(data) {
    let out = {};

    data.forEach(r => {
        const cat = r["TIPO_PRODUCTO"] || "Sin dato";
        const anio = r["AÑO"] || "Sin año";
        const key = cat + "||" + anio;

        if (!out[key]) {
            out[key] = {
                categoria: cat,
                anio: anio,
                total: 0,
                cantidad: 0,
                registros: 0,
                municipalidadesSet: new Set(),
                licitacionesSet: new Set()
            };
        }

        out[key].total += Number(r["TOTAL"] || 0);
        out[key].cantidad += Number(r["CANTIDAD"] || 0);
        out[key].registros += 1;
        out[key].municipalidadesSet.add(r["COMPRADOR"]);

        if (r["LICITACIÓN_LIMPIA"]) {
            out[key].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        categoria: x.categoria,
        anio: x.anio,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        municipalidades: x.municipalidadesSet.size,
        licitaciones: x.licitacionesSet.size
    })).sort((a,b) => String(a.anio).localeCompare(String(b.anio)) || String(a.categoria).localeCompare(String(b.categoria)));
}

function resumenCategoriaMes(data) {
    let out = {};

    data.forEach(r => {
        const cat = r["TIPO_PRODUCTO"] || "Sin dato";
        const mes = r["PERIODO_MENSUAL"] || "Sin mes";
        const key = cat + "||" + mes;

        if (!out[key]) {
            out[key] = {
                categoria: cat,
                mes: mes,
                total: 0,
                cantidad: 0,
                registros: 0,
                municipalidadesSet: new Set(),
                licitacionesSet: new Set()
            };
        }

        out[key].total += Number(r["TOTAL"] || 0);
        out[key].cantidad += Number(r["CANTIDAD"] || 0);
        out[key].registros += 1;
        out[key].municipalidadesSet.add(r["COMPRADOR"]);

        if (r["LICITACIÓN_LIMPIA"]) {
            out[key].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        categoria: x.categoria,
        mes: x.mes,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        municipalidades: x.municipalidadesSet.size,
        licitaciones: x.licitacionesSet.size
    })).sort((a,b) => String(a.mes).localeCompare(String(b.mes)) || String(a.categoria).localeCompare(String(b.categoria)));
}

function resumenMunicipalidadAnio(data) {
    let out = {};

    data.forEach(r => {
        const muni = r["COMPRADOR"] || "Sin dato";
        const anio = r["AÑO"] || "Sin año";
        const cat = r["TIPO_PRODUCTO"] || "Sin dato";
        const key = muni + "||" + anio + "||" + cat;

        if (!out[key]) {
            out[key] = {
                municipalidad: muni,
                anio: anio,
                categoria: cat,
                total: 0,
                cantidad: 0,
                registros: 0,
                licitacionesSet: new Set()
            };
        }

        out[key].total += Number(r["TOTAL"] || 0);
        out[key].cantidad += Number(r["CANTIDAD"] || 0);
        out[key].registros += 1;

        if (r["LICITACIÓN_LIMPIA"]) {
            out[key].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        municipalidad: x.municipalidad,
        anio: x.anio,
        categoria: x.categoria,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        licitaciones: x.licitacionesSet.size
    })).sort((a,b) => String(a.anio).localeCompare(String(b.anio)) || String(a.municipalidad).localeCompare(String(b.municipalidad)));
}

function resumenMunicipalidadMes(data) {
    let out = {};

    data.forEach(r => {
        const muni = r["COMPRADOR"] || "Sin dato";
        const mes = r["PERIODO_MENSUAL"] || "Sin mes";
        const cat = r["TIPO_PRODUCTO"] || "Sin dato";
        const key = muni + "||" + mes + "||" + cat;

        if (!out[key]) {
            out[key] = {
                municipalidad: muni,
                mes: mes,
                categoria: cat,
                total: 0,
                cantidad: 0,
                registros: 0,
                licitacionesSet: new Set()
            };
        }

        out[key].total += Number(r["TOTAL"] || 0);
        out[key].cantidad += Number(r["CANTIDAD"] || 0);
        out[key].registros += 1;

        if (r["LICITACIÓN_LIMPIA"]) {
            out[key].licitacionesSet.add(r["LICITACIÓN_LIMPIA"]);
        }
    });

    return Object.values(out).map(x => ({
        municipalidad: x.municipalidad,
        mes: x.mes,
        categoria: x.categoria,
        total: x.total,
        cantidad: x.cantidad,
        registros: x.registros,
        licitaciones: x.licitacionesSet.size
    })).sort((a,b) => String(a.mes).localeCompare(String(b.mes)) || String(a.municipalidad).localeCompare(String(b.municipalidad)));
}

function renderResumen() {
    const div = document.getElementById("resumen");

    const pura = DATA.filter(r => r["TIPO_PRODUCTO"] === "Zopiclona");
    const derivados = DATA.filter(r => r["TIPO_PRODUCTO"] === "Eszopiclona");

    const porCategoria = resumenCategoria(DATA);
    const porMunicipalidad = resumenMunicipalidad(DATA).sort((a,b) => b.total - a.total);
    const top = porMunicipalidad.slice(0, 15).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Resumen ejecutivo — adquisiciones bajo procedimiento licitatorio.</b><br>
            Universo de análisis: órdenes de compra (OC) de zopiclona y eszopiclona
            cursadas por la administración municipal de salud y registradas
            en Mercado Público. Criterios de inclusión: (i) comprador del subsector
            municipal o entidad de la red de atención primaria habilitada; (ii) estado
            de la OC <i>Aceptada</i> o <i>Recepción Conforme</i> (transacción efectivamente
            perfeccionada); (iii) deduplicación exacta de registros; y (iv) asociación a
            un código de licitación válido. Las compras sin licitación y las no
            confirmadas se excluyen del cómputo y se conservan para auditoría. Los montos
            se expresan en pesos chilenos (CLP) sobre el total neto de cada línea.
        </div>

        ${kpisHTML(DATA)}

        <div class="grid2">
            <div class="chart">
                <h2>Total por tipo: Zopiclona vs Eszopiclona</h2>
                <div id="resumen_tipo_total"></div>
            </div>

            <div class="chart">
                <h2>Registros por tipo</h2>
                <div id="resumen_tipo_registros"></div>
            </div>
        </div>

        <div class="chart">
            <h2>Top municipalidades por gasto total con licitación</h2>
            <div id="resumen_top_muni"></div>
        </div>
    `;

    Plotly.newPlot("resumen_tipo_total", [{
        labels: porCategoria.map(x => x.categoria),
        values: porCategoria.map(x => x.total),
        type: "pie",
        hole: 0.45
    }], {
        template: "plotly_white"
    });

    Plotly.newPlot("resumen_tipo_registros", [{
        x: porCategoria.map(x => x.categoria),
        y: porCategoria.map(x => x.registros),
        type: "bar",
        text: porCategoria.map(x => formatNum(x.registros)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        yaxis: {title: "Registros"}
    });

    Plotly.newPlot("resumen_top_muni", [{
        x: top.map(x => x.total),
        y: top.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        text: top.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Total comprado"}
    });
}

function renderComparativo() {
    const div = document.getElementById("comparativo");

    const anual = resumenCategoriaAnio(DATA);
    const mensual = resumenCategoriaMes(DATA);

    const anios = unique(DATA.map(r => r["AÑO"])).sort();
    const meses = unique(DATA.map(r => r["PERIODO_MENSUAL"])).sort();

    const categorias = ["Zopiclona", "Eszopiclona"];

    const tracesAnual = categorias.map(cat => ({
        x: anios,
        y: anios.map(anio => {
            const fila = anual.find(r => r.categoria === cat && String(r.anio) === String(anio));
            return fila ? fila.total : 0;
        }),
        type: "bar",
        name: cat
    }));

    const tracesMensual = categorias.map(cat => ({
        x: meses,
        y: meses.map(mes => {
            const fila = mensual.find(r => r.categoria === cat && String(r.mes) === String(mes));
            return fila ? fila.total : 0;
        }),
        type: "scatter",
        mode: "lines+markers",
        name: cat
    }));

    div.innerHTML = `
        <div class="analysis">
            <b>Análisis comparativo: zopiclona pura vs. eszopiclona.</b><br>
            Desagregación del gasto adjudicado según presentación del principio activo,
            con resolución anual y mensual. Dado que Mercado Público asigna un único código
            ONU a toda la familia (el genérico declarado siempre dice "Zopiclona"), la
            clasificación se apoya en lo que efectivamente especificó el comprador: una
            línea es <i>eszopiclona</i> cuando esa palabra aparece en el genérico o en la
            especificación del comprador, o cuando ésta nombra una marca de eszopiclona
            (Valnoc, Zopinom); de lo contrario, si se menciona zopiclona, se clasifica como
            <i>zopiclona</i> (pura). Permite contrastar la sustitución entre presentaciones y su
            incidencia en el gasto a lo largo de la serie temporal.
        </div>

        <div class="grid2">
            <div class="chart">
                <h2>Comparativo anual de gasto</h2>
                <div id="comparativo_anual"></div>
            </div>

            <div class="chart">
                <h2>Comparativo mensual de gasto</h2>
                <div id="comparativo_mensual"></div>
            </div>
        </div>

        <div class="grid2">
            <div class="chart">
                <h2>Tabla anual Zopiclona vs Eszopiclona</h2>
                <div id="tabla_comp_anual"></div>
            </div>

            <div class="chart">
                <h2>Tabla mensual Zopiclona vs Eszopiclona</h2>
                <div id="tabla_comp_mensual"></div>
            </div>
        </div>
    `;

    Plotly.newPlot("comparativo_anual", tracesAnual, {
        template: "plotly_white",
        barmode: "group",
        yaxis: {title: "Total comprado"},
        xaxis: {title: "Año"}
    });

    Plotly.newPlot("comparativo_mensual", tracesMensual, {
        template: "plotly_white",
        yaxis: {title: "Total comprado"},
        xaxis: {title: "Mes"}
    });

    document.getElementById("tabla_comp_anual").innerHTML = tableFromRows(anual, [
        {key:"anio", label:"Año"},
        {key:"categoria", label:"Tipo"},
        {key:"total", label:"Total", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"municipalidades", label:"Municipalidades", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"}
    ]);

    document.getElementById("tabla_comp_mensual").innerHTML = tableFromRows(mensual, [
        {key:"mes", label:"Mes"},
        {key:"categoria", label:"Tipo"},
        {key:"total", label:"Total", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"municipalidades", label:"Municipalidades", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"}
    ]);
}

function renderTipo(sectionId, tipo) {
    const data = DATA.filter(r => r["TIPO_PRODUCTO"] === tipo);
    const div = document.getElementById(sectionId);

    const porMuni = resumenMunicipalidad(data).sort((a,b) => b.total - a.total);
    const top = porMuni.slice(0, 20).reverse();

    const anual = resumenCategoriaAnio(data);
    const mensual = resumenCategoriaMes(data);

    div.innerHTML = `
        <div class="analysis">
            <b>Detalle por presentación: ${tipo}.</b><br>
            Subconjunto restringido a registros clasificados como <b>${tipo}</b> bajo
            procedimiento licitatorio. Las métricas agregadas (gasto total, unidades,
            licitaciones y proveedores únicos) se calculan exclusivamente sobre este
            estrato, permitiendo caracterizar su estructura de mercado de forma aislada.
        </div>

        ${kpisHTML(data)}

        <div class="chart">
            <h2>Top municipalidades por gasto total - ${tipo}</h2>
            <div id="top_${sectionId}"></div>
        </div>

        <div class="grid2">
            <div class="chart">
                <h2>Gasto anual - ${tipo}</h2>
                <div id="anio_${sectionId}"></div>
            </div>

            <div class="chart">
                <h2>Gasto mensual - ${tipo}</h2>
                <div id="mes_${sectionId}"></div>
            </div>
        </div>

        <div class="chart">
            <h2>Tabla municipalidades - ${tipo}</h2>
            <input class="search-box" id="search_${sectionId}" placeholder="Buscar municipalidad..." onkeyup="filtrarTabla('search_${sectionId}', 'tabla_${sectionId}')">
            <div id="tabla_${sectionId}"></div>
        </div>
    `;

    Plotly.newPlot("top_" + sectionId, [{
        x: top.map(x => x.total),
        y: top.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        text: top.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Total comprado"}
    });

    Plotly.newPlot("anio_" + sectionId, [{
        x: anual.map(x => x.anio),
        y: anual.map(x => x.total),
        type: "bar",
        text: anual.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        yaxis: {title: "Total comprado"}
    });

    Plotly.newPlot("mes_" + sectionId, [{
        x: mensual.map(x => x.mes),
        y: mensual.map(x => x.total),
        type: "scatter",
        mode: "lines+markers",
        fill: "tozeroy"
    }], {
        template: "plotly_white",
        yaxis: {title: "Total comprado"},
        xaxis: {title: "Mes"}
    });

    document.getElementById("tabla_" + sectionId).innerHTML = tableFromRows(porMuni, [
        {key:"municipalidad", label:"Municipalidad"},
        {key:"total", label:"Total comprado", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"},
        {key:"precioPromedio", label:"Precio promedio ponderado", type:"money"}
    ]);
}

function renderProveedores() {
    const div = document.getElementById("proveedores");

    const porProv = resumenProveedor(DATA).sort((a,b) => b.total - a.total);
    const topTodo = porProv.slice(0, 20).reverse();

    const provZopi = resumenProveedor(DATA.filter(r => r["TIPO_PRODUCTO"] === "Zopiclona"))
        .sort((a,b) => b.total - a.total).slice(0, 15).reverse();
    const provEszo = resumenProveedor(DATA.filter(r => r["TIPO_PRODUCTO"] === "Eszopiclona"))
        .sort((a,b) => b.total - a.total).slice(0, 15).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Estructura de la oferta: proveedores adjudicatarios.</b><br>
            Empresas adjudicatarias del suministro por licitación, ordenadas por monto
            total adjudicado, para el universo completo y desagregadas por presentación
            (zopiclona y eszopiclona). El precio promedio ponderado por proveedor permite
            detectar dispersión de precios entre oferentes y evaluar el grado de
            concentración del mercado.
        </div>

        <div class="chart">
            <h2>Top 20 proveedores por gasto total adjudicado</h2>
            <div id="prov_top_todo"></div>
        </div>

        <div class="grid2">
            <div class="chart">
                <h2>Top proveedores - Zopiclona</h2>
                <div id="prov_top_zopi"></div>
            </div>

            <div class="chart">
                <h2>Top proveedores - Eszopiclona</h2>
                <div id="prov_top_eszo"></div>
            </div>
        </div>

        <div class="chart">
            <h2>Tabla de proveedores</h2>
            <input class="search-box" id="search_proveedores" placeholder="Buscar proveedor..." onkeyup="filtrarTabla('search_proveedores', 'tabla_proveedores')">
            <div id="tabla_proveedores"></div>
        </div>
    `;

    Plotly.newPlot("prov_top_todo", [{
        x: topTodo.map(x => x.total),
        y: topTodo.map(x => x.proveedor),
        type: "bar",
        orientation: "h",
        text: topTodo.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Total adjudicado"}
    });

    Plotly.newPlot("prov_top_zopi", [{
        x: provZopi.map(x => x.total),
        y: provZopi.map(x => x.proveedor),
        type: "bar",
        orientation: "h",
        text: provZopi.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Total adjudicado"}
    });

    Plotly.newPlot("prov_top_eszo", [{
        x: provEszo.map(x => x.total),
        y: provEszo.map(x => x.proveedor),
        type: "bar",
        orientation: "h",
        text: provEszo.map(x => formatCLP(x.total)),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Total adjudicado"}
    });

    document.getElementById("tabla_proveedores").innerHTML = tableFromRows(porProv, [
        {key:"proveedor", label:"Proveedor"},
        {key:"total", label:"Total adjudicado", type:"money"},
        {key:"cantidad", label:"Unidades vendidas", type:"num"},
        {key:"municipalidades", label:"Municipalidades atendidas", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"},
        {key:"precioPromedio", label:"Precio promedio ponderado", type:"money"}
    ]);
}

function renderLicitaciones() {
    const div = document.getElementById("licitaciones");

    const rows = resumenMunicipalidad(DATA)
        .sort((a,b) => b.licitaciones - a.licitaciones || b.total - a.total);

    const top = rows.slice(0, 20).reverse();

    div.innerHTML = `
        <div class="analysis">
            <b>Concentración de procesos licitatorios por comprador.</b><br>
            Recuento de licitaciones únicas (identificadas por su código) adjudicadas a
            cada entidad municipal. Una misma licitación puede originar múltiples órdenes
            de compra, por lo que este indicador mide actividad contractual y no volumen
            transado. Es un proxy de la intensidad de uso del mecanismo licitatorio
            frente a otras modalidades de compra.
        </div>

        <div class="chart">
            <h2>Ranking de municipalidades por licitaciones adjudicadas</h2>
            <div id="chart_licitaciones"></div>
        </div>

        <div class="chart">
            <h2>Tabla de licitaciones por municipalidad</h2>
            <input class="search-box" id="search_licitaciones" placeholder="Buscar municipalidad..." onkeyup="filtrarTabla('search_licitaciones', 'tabla_licitaciones')">
            <div id="tabla_licitaciones"></div>
        </div>
    `;

    Plotly.newPlot("chart_licitaciones", [{
        x: top.map(x => x.licitaciones),
        y: top.map(x => x.municipalidad),
        type: "bar",
        orientation: "h",
        text: top.map(x => x.licitaciones),
        textposition: "auto"
    }], {
        template: "plotly_white",
        margin: {t: 10},
        yaxis: {automargin: true},
        xaxis: {title: "Licitaciones adjudicadas"}
    });

    document.getElementById("tabla_licitaciones").innerHTML = tableFromRows(rows, [
        {key:"municipalidad", label:"Municipalidad"},
        {key:"licitaciones", label:"Licitaciones adjudicadas", type:"num"},
        {key:"total", label:"Total comprado", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"registros", label:"Registros", type:"num"},
        {key:"precioPromedio", label:"Precio promedio ponderado", type:"money"}
    ]);
}

function escapeHTML(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function obtenerMunicipalidades(data) {
    return unique(data.map(r => r["COMPRADOR"]))
        .filter(x => x !== "Sin dato")
        .sort((a,b) => String(a).localeCompare(String(b)));
}

function obtenerAnios(data) {
    // Forzamos el eje anual completo para que siempre aparezcan todos los años,
    // aunque una municipalidad no tenga compras en algunos períodos.
    return ["2021", "2022", "2023", "2024", "2025", "2026"];
}

function obtenerMesesBase() {
    return [
        {num: 1, nombre: "Enero"},
        {num: 2, nombre: "Febrero"},
        {num: 3, nombre: "Marzo"},
        {num: 4, nombre: "Abril"},
        {num: 5, nombre: "Mayo"},
        {num: 6, nombre: "Junio"},
        {num: 7, nombre: "Julio"},
        {num: 8, nombre: "Agosto"},
        {num: 9, nombre: "Septiembre"},
        {num: 10, nombre: "Octubre"},
        {num: 11, nombre: "Noviembre"},
        {num: 12, nombre: "Diciembre"}
    ];
}

function sumarTotal(rows) {
    return rows.reduce((acc, r) => acc + Number(r["TOTAL"] || 0), 0);
}

function contarRegistros(rows) {
    return rows.length;
}

function contarLicitaciones(rows) {
    const setLic = new Set(
        rows
            .filter(r => r["LICITACIÓN_LIMPIA"])
            .map(r => r["LICITACIÓN_LIMPIA"])
    );
    return setLic.size;
}

function valorMetricaConteo(rows, metrica) {
    if (metrica === "licitaciones") {
        return contarLicitaciones(rows);
    }
    return contarRegistros(rows);
}

function etiquetaMetricaConteo(metrica) {
    if (metrica === "licitaciones") {
        return "Licitaciones";
    }
    return "Registros";
}

function actualizarGraficoAnualTotal() {
    const muni = document.getElementById("select_muni_anual").value;
    const dataMuni = DATA.filter(r => r["COMPRADOR"] === muni);
    const anios = obtenerAnios(DATA);
    const categorias = ["Zopiclona", "Eszopiclona"];

    const traces = categorias.map(cat => ({
        x: anios,
        y: anios.map(anio => {
            const rows = dataMuni.filter(r => r["AÑO"] === anio && r["TIPO_PRODUCTO"] === cat);
            return sumarTotal(rows);
        }),
        type: "bar",
        name: cat,
        text: anios.map(anio => {
            const rows = dataMuni.filter(r => r["AÑO"] === anio && r["TIPO_PRODUCTO"] === cat);
            const total = sumarTotal(rows);
            return total > 0 ? formatCLP(total) : "";
        }),
        textposition: "outside",
        textangle: 0,
        cliponaxis: false
    }));

    Plotly.newPlot("grafico_anual_muni_total", traces, {
        template: "plotly_white",
        barmode: "group",
        bargap: 0.25,
        bargroupgap: 0.08,
        title: "Total comprado por año - " + muni,
        xaxis: {
            title: "Año",
            type: "category",
            categoryorder: "array",
            categoryarray: anios
        },
        yaxis: {
            title: "Total comprado",
            rangemode: "tozero"
        },
        margin: {l: 80, r: 40, t: 80, b: 80},
        legend: {orientation: "h", x: 0, y: -0.2},
        uniformtext: {mode: "hide", minsize: 10}
    }, {responsive: true});
}

function actualizarGraficoAnualConteo() {
    const muni = document.getElementById("select_muni_anual").value;
    const metrica = document.getElementById("select_metrica_anual").value;
    const label = etiquetaMetricaConteo(metrica);

    const dataMuni = DATA.filter(r => r["COMPRADOR"] === muni);
    const anios = obtenerAnios(DATA);
    const categorias = ["Zopiclona", "Eszopiclona"];

    const traces = categorias.map(cat => ({
        x: anios,
        y: anios.map(anio => {
            const rows = dataMuni.filter(r => r["AÑO"] === anio && r["TIPO_PRODUCTO"] === cat);
            return valorMetricaConteo(rows, metrica);
        }),
        type: "bar",
        name: cat,
        text: anios.map(anio => {
            const rows = dataMuni.filter(r => r["AÑO"] === anio && r["TIPO_PRODUCTO"] === cat);
            const valor = valorMetricaConteo(rows, metrica);
            return valor > 0 ? formatNum(valor) : "";
        }),
        textposition: "outside",
        textangle: 0,
        cliponaxis: false
    }));

    Plotly.newPlot("grafico_anual_muni_conteo", traces, {
        template: "plotly_white",
        barmode: "group",
        bargap: 0.25,
        bargroupgap: 0.08,
        title: label + " por año - " + muni,
        xaxis: {
            title: "Año",
            type: "category",
            categoryorder: "array",
            categoryarray: anios
        },
        yaxis: {
            title: label,
            rangemode: "tozero",
            dtick: 1
        },
        margin: {l: 80, r: 40, t: 80, b: 80},
        legend: {orientation: "h", x: 0, y: -0.2},
        uniformtext: {mode: "hide", minsize: 10}
    }, {responsive: true});
}

function actualizarGraficosAnualesMunicipalidad() {
    actualizarGraficoAnualTotal();
    actualizarGraficoAnualConteo();
}

function actualizarGraficoMensualTotal() {
    const muni = document.getElementById("select_muni_mensual").value;
    const anio = document.getElementById("select_anio_mensual").value;

    const dataMuniAnio = DATA.filter(r =>
        r["COMPRADOR"] === muni &&
        r["AÑO"] === anio
    );

    const meses = obtenerMesesBase();
    const categorias = ["Zopiclona", "Eszopiclona"];

    const traces = categorias.map(cat => ({
        x: meses.map(m => m.nombre),
        y: meses.map(m => {
            const rows = dataMuniAnio.filter(r => Number(r["MES_NUM"]) === m.num && r["TIPO_PRODUCTO"] === cat);
            return sumarTotal(rows);
        }),
        type: "bar",
        name: cat,
        text: meses.map(m => {
            const rows = dataMuniAnio.filter(r => Number(r["MES_NUM"]) === m.num && r["TIPO_PRODUCTO"] === cat);
            const total = sumarTotal(rows);
            return total > 0 ? formatCLP(total) : "";
        }),
        textposition: "outside",
        textangle: 0,
        cliponaxis: false
    }));

    Plotly.newPlot("grafico_mensual_muni_total", traces, {
        template: "plotly_white",
        barmode: "group",
        bargap: 0.25,
        bargroupgap: 0.08,
        title: "Total comprado mensual - " + muni + " - " + anio,
        xaxis: {
            title: "Mes",
            type: "category",
            categoryorder: "array",
            categoryarray: meses.map(m => m.nombre)
        },
        yaxis: {
            title: "Total comprado",
            rangemode: "tozero"
        },
        margin: {l: 80, r: 40, t: 80, b: 100},
        legend: {orientation: "h", x: 0, y: -0.25},
        uniformtext: {mode: "hide", minsize: 10}
    }, {responsive: true});
}

function actualizarGraficoMensualConteo() {
    const muni = document.getElementById("select_muni_mensual").value;
    const anio = document.getElementById("select_anio_mensual").value;
    const metrica = document.getElementById("select_metrica_mensual").value;
    const label = etiquetaMetricaConteo(metrica);

    const dataMuniAnio = DATA.filter(r =>
        r["COMPRADOR"] === muni &&
        r["AÑO"] === anio
    );

    const meses = obtenerMesesBase();
    const categorias = ["Zopiclona", "Eszopiclona"];

    const traces = categorias.map(cat => ({
        x: meses.map(m => m.nombre),
        y: meses.map(m => {
            const rows = dataMuniAnio.filter(r => Number(r["MES_NUM"]) === m.num && r["TIPO_PRODUCTO"] === cat);
            return valorMetricaConteo(rows, metrica);
        }),
        type: "bar",
        name: cat,
        text: meses.map(m => {
            const rows = dataMuniAnio.filter(r => Number(r["MES_NUM"]) === m.num && r["TIPO_PRODUCTO"] === cat);
            const valor = valorMetricaConteo(rows, metrica);
            return valor > 0 ? formatNum(valor) : "";
        }),
        textposition: "outside",
        textangle: 0,
        cliponaxis: false
    }));

    Plotly.newPlot("grafico_mensual_muni_conteo", traces, {
        template: "plotly_white",
        barmode: "group",
        bargap: 0.25,
        bargroupgap: 0.08,
        title: label + " por mes - " + muni + " - " + anio,
        xaxis: {
            title: "Mes",
            type: "category",
            categoryorder: "array",
            categoryarray: meses.map(m => m.nombre)
        },
        yaxis: {
            title: label,
            rangemode: "tozero",
            dtick: 1
        },
        margin: {l: 80, r: 40, t: 80, b: 100},
        legend: {orientation: "h", x: 0, y: -0.25},
        uniformtext: {mode: "hide", minsize: 10}
    }, {responsive: true});
}

function actualizarGraficosMensualesMunicipalidad() {
    actualizarGraficoMensualTotal();
    actualizarGraficoMensualConteo();
}

function renderAnual() {
    const div = document.getElementById("anual");

    const rows = resumenMunicipalidadAnio(DATA);
    const municipalidades = obtenerMunicipalidades(DATA);
    const muniInicial = municipalidades.length > 0 ? municipalidades[0] : "";

    div.innerHTML = `
        <div class="analysis">
            <b>Serie anual desagregada por comprador.</b><br>
            Evolución interanual del gasto adjudicado, estratificada por presentación
            (pura vs. eszopiclona). El selector permite el análisis individual por entidad;
            la métrica secundaria alterna entre número de registros (líneas de OC) y
            licitaciones únicas. Útil para identificar tendencias, estacionalidad
            estructural y posibles puntos de quiebre en la conducta de compra.
        </div>

        <div class="chart">
            <h2>Gráfico anual por municipalidad: total comprado</h2>

            <div class="control-panel">
                <label>Municipalidad:</label>
                <select id="select_muni_anual" onchange="actualizarGraficosAnualesMunicipalidad()">
                    ${municipalidades.map(m => `<option value="${escapeHTML(m)}">${escapeHTML(m)}</option>`).join("")}
                </select>
            </div>

            <div id="grafico_anual_muni_total"></div>
        </div>

        <div class="chart">
            <h2>Gráfico anual por municipalidad: registros o licitaciones</h2>

            <div class="control-panel">
                <label>Métrica:</label>
                <select id="select_metrica_anual" onchange="actualizarGraficoAnualConteo()">
                    <option value="registros">Registros</option>
                    <option value="licitaciones">Licitaciones</option>
                </select>
            </div>

            <div id="grafico_anual_muni_conteo"></div>
        </div>

        <div class="chart">
            <h2>Tabla anual por municipalidad y tipo</h2>
            <input class="search-box" id="search_anual" placeholder="Buscar municipalidad, año o tipo..." onkeyup="filtrarTabla('search_anual', 'tabla_anual')">
            <div id="tabla_anual"></div>
        </div>
    `;

    document.getElementById("tabla_anual").innerHTML = tableFromRows(rows, [
        {key:"anio", label:"Año"},
        {key:"municipalidad", label:"Municipalidad"},
        {key:"categoria", label:"Tipo"},
        {key:"total", label:"Total comprado", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"}
    ]);

    if (muniInicial !== "") {
        document.getElementById("select_muni_anual").value = muniInicial;
        actualizarGraficosAnualesMunicipalidad();
    }
}

function renderMensual() {
    const div = document.getElementById("mensual");

    const rows = resumenMunicipalidadMes(DATA);
    const municipalidades = obtenerMunicipalidades(DATA);
    const anios = obtenerAnios(DATA);

    const muniInicial = municipalidades.length > 0 ? municipalidades[0] : "";
    const anioInicial = anios.length > 0 ? anios[0] : "";

    div.innerHTML = `
        <div class="analysis">
            <b>Resolución mensual intra-anual.</b><br>
            Distribución del gasto a nivel mensual para una entidad y año seleccionados,
            estratificada por presentación. Permite examinar la estacionalidad de la
            demanda, la concentración de adjudicaciones en periodos específicos y la
            regularidad del abastecimiento dentro del ejercicio presupuestario.
        </div>

        <div class="chart">
            <h2>Gráfico mensual por municipalidad y año: total comprado</h2>

            <div class="control-panel">
                <label>Municipalidad:</label>
                <select id="select_muni_mensual" onchange="actualizarGraficosMensualesMunicipalidad()">
                    ${municipalidades.map(m => `<option value="${escapeHTML(m)}">${escapeHTML(m)}</option>`).join("")}
                </select>

                <label>Año:</label>
                <select id="select_anio_mensual" onchange="actualizarGraficosMensualesMunicipalidad()">
                    ${anios.map(a => `<option value="${escapeHTML(a)}">${escapeHTML(a)}</option>`).join("")}
                </select>
            </div>

            <div id="grafico_mensual_muni_total"></div>
        </div>

        <div class="chart">
            <h2>Gráfico mensual por municipalidad y año: registros o licitaciones</h2>

            <div class="control-panel">
                <label>Métrica:</label>
                <select id="select_metrica_mensual" onchange="actualizarGraficoMensualConteo()">
                    <option value="registros">Registros</option>
                    <option value="licitaciones">Licitaciones</option>
                </select>
            </div>

            <div id="grafico_mensual_muni_conteo"></div>
        </div>

        <div class="chart">
            <h2>Tabla mensual por municipalidad y tipo</h2>
            <input class="search-box" id="search_mensual" placeholder="Buscar municipalidad, mes o tipo..." onkeyup="filtrarTabla('search_mensual', 'tabla_mensual')">
            <div id="tabla_mensual"></div>
        </div>
    `;

    document.getElementById("tabla_mensual").innerHTML = tableFromRows(rows, [
        {key:"mes", label:"Mes"},
        {key:"municipalidad", label:"Municipalidad"},
        {key:"categoria", label:"Tipo"},
        {key:"total", label:"Total comprado", type:"money"},
        {key:"cantidad", label:"Cantidad", type:"num"},
        {key:"licitaciones", label:"Licitaciones", type:"num"},
        {key:"registros", label:"Registros", type:"num"}
    ]);

    if (muniInicial !== "" && anioInicial !== "") {
        document.getElementById("select_muni_mensual").value = muniInicial;
        document.getElementById("select_anio_mensual").value = anioInicial;
        actualizarGraficosMensualesMunicipalidad();
    }
}

function setBaseTab(id, el) {
    document.querySelectorAll(".base-subsection").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");

    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
}

function renderTablaBase(id, titulo, data) {
    const columnas = [
        "TIPO_PRODUCTO",
        "AÑO",
        "PERIODO_MENSUAL",
        "COMPRADOR",
        "LICITACIÓN",
        "PROVEEDOR",
        "¿Para quién?",
        "FECHA O.C",
        "CANTIDAD",
        "VALOR C/U",
        "TOTAL",
        "LINK",
        "ARCHIVO"
    ];

    let html = `
        <div id="${id}" class="base-subsection">
            <div class="analysis">
                <b>${titulo}</b><br>
                Registros: <b>${formatNum(data.length)}</b>.
                Esta base solo considera compras con licitación.
            </div>

            <input class="search-box" id="search_${id}" placeholder="Buscar dentro de ${titulo}..." onkeyup="filtrarTabla('search_${id}', '${id}')">

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>${columnas.map(c => `<th>${c}</th>`).join("")}</tr>
                    </thead>
                    <tbody>
    `;

    data.forEach(r => {
        html += "<tr>";

        columnas.forEach(c => {
            let val = r[c] ?? "";

            if (c === "TOTAL" || c === "VALOR C/U") {
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

    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;

    return html;
}

function renderBase() {
    const div = document.getElementById("base");

    const pura = DATA.filter(r => r["TIPO_PRODUCTO"] === "Zopiclona");
    const derivados = DATA.filter(r => r["TIPO_PRODUCTO"] === "Eszopiclona");

    div.innerHTML = `
        <div class="analysis">
            <b>Base de datos analítica — registro a nivel de línea de orden de compra.</b><br>
            Conjunto depurado y trazable que sustenta todos los indicadores del tablero.
            Cada fila corresponde a una línea de OC con licitación válida, confirmada y
            no duplicada. Las pestañas permiten segmentar entre el universo completo y las
            presentaciones pura y eszopiclona. El enlace de cada registro remite a la OC
            original en Mercado Público, garantizando la verificabilidad de la fuente.
        </div>

        <div class="chart">
            <h2>Base completa</h2>

            <div class="tab-buttons">
                <button class="tab-btn active" onclick="setBaseTab('base_todo', this)">Todo con licitación</button>
                <button class="tab-btn" onclick="setBaseTab('base_pura', this)">Zopiclona con licitación</button>
                <button class="tab-btn" onclick="setBaseTab('base_derivados', this)">Eszopiclona con licitación</button>
            </div>

            ${renderTablaBase("base_todo", "Todo con licitación", DATA)}
            ${renderTablaBase("base_pura", "Zopiclona con licitación", pura)}
            ${renderTablaBase("base_derivados", "Eszopiclona con licitación", derivados)}
        </div>
    `;

    document.getElementById("base_todo").classList.add("active");
}

renderResumen();
renderComparativo();
renderTipo("pura", "Zopiclona");
renderTipo("derivados", "Eszopiclona");
renderLicitaciones();
renderProveedores();
renderAnual();
renderMensual();
renderBase();

</script>
</body>
</html>
"""

html = html.replace("__PAYLOAD__", payload)

# =========================================================
# 6. GUARDAR Y ABRIR
# =========================================================

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard generado correctamente en: {OUT_HTML}")

# No intentar abrir el navegador en entornos sin pantalla (GitHub Actions/CI).
if not (os.environ.get("CI") or os.environ.get("ADRI_NO_BROWSER")):
    webbrowser.open("file://" + os.path.realpath(OUT_HTML))