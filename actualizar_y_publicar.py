#!/usr/bin/env python3
"""
actualizar_y_publicar.py
========================
Orquestador único del proyecto. Reprocesa los datos, regenera ambos dashboards
y arma la carpeta `docs/` que GitHub Pages publica como sitio web.

Sirve igual en tu PC y en la nube (GitHub Actions). El mismo comando hace todo.

Uso:
    python actualizar_y_publicar.py                # publica con los datos actuales
    python actualizar_y_publicar.py --extraer-recientes   # baja meses recientes y reprocesa
    python actualizar_y_publicar.py --completo     # re-extrae TODO el histórico (lento)

Pasos:
    1. (opcional) Extracción de OC de zopiclona y melatonina.
    2. Filtrado/clasificación de ambos fármacos.
    3. Generación de los dos dashboards HTML.
    4. Copia de los HTML a docs/ + índice docs/index.html.
"""

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

from config_rutas import (
    BASE_ADRI,
    DATOS_ZOPICLONA,
    DATOS_MELATONINA,
    ZOPICLONA_FILTRADOS,
    MELATONINA_FILTRADOS,
    ANIO_INICIO,
    ANIO_FIN,
)
from extractor_comun import extraer_farmaco

DOCS = BASE_ADRI / "docs"
DASH_ZOPI = ZOPICLONA_FILTRADOS / "Dashboard_Zopiclona_SOLO_LICITACION_Pura_Derivados.html"
DASH_MELA = MELATONINA_FILTRADOS / "Dashboard_Melatonina_Licitacion.html"

# Evita que los scripts intenten abrir un navegador al generarse.
os.environ.setdefault("ADRI_NO_BROWSER", "1")


def _run(descripcion, comando):
    """Ejecuta un subproceso python y aborta si falla."""
    print(f"\n=== {descripcion} ===")
    res = subprocess.run([sys.executable, *comando], cwd=str(BASE_ADRI))
    if res.returncode != 0:
        raise SystemExit(f"[!] Falló: {descripcion}")


def extraer(modo: str):
    """modo: 'no' | 'recientes' | 'completo'."""
    if modo == "no":
        print("Extracción omitida (se usan los datos ya guardados).")
        return

    if modo == "completo":
        ai, af, meses = ANIO_INICIO, ANIO_FIN, None
    else:  # recientes: año en curso, últimos 3 meses
        hoy = dt.date.today()
        ai = af = hoy.year
        meses = sorted({max(1, hoy.month - 2), max(1, hoy.month - 1), hoy.month})

    extraer_farmaco("zopiclona", DATOS_ZOPICLONA, "zopiclona", ai, af, meses=meses)
    extraer_farmaco("melatonin", DATOS_MELATONINA, "melatonina", ai, af, meses=meses)


def filtrar():
    # Zopiclona (cascada pura/derivados)
    from Filtrado import procesador_zopiclona_cascada
    procesador_zopiclona_cascada()
    # Melatonina (fase 2 de su pipeline)
    _run("Filtrado melatonina", ["melatonina_pipeline.py", "--fase", "2"])


def generar_dashboards():
    _run("Dashboard zopiclona", ["dashboardzo.py"])
    _run("Dashboard melatonina", ["melatonina_pipeline.py", "--fase", "3"])


def publicar():
    """Copia los dashboards a docs/ y escribe el índice."""
    DOCS.mkdir(parents=True, exist_ok=True)

    publicados = []
    if DASH_ZOPI.exists():
        shutil.copy2(DASH_ZOPI, DOCS / "zopiclona.html")
        publicados.append(("zopiclona.html", "Zopiclona (pura + derivados)"))
    if DASH_MELA.exists():
        shutil.copy2(DASH_MELA, DOCS / "melatonina.html")
        publicados.append(("melatonina.html", "Melatonina"))

    fecha = dt.datetime.now().strftime("%d-%m-%Y %H:%M")
    tarjetas = "\n".join(
        f'      <a class="card" href="{archivo}">'
        f'<span class="pill">Dashboard</span><h2>{titulo}</h2>'
        f'<p>Adjudicaciones por licitación &middot; compras públicas municipales</p></a>'
        for archivo, titulo in publicados
    )

    index = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Compras públicas municipales de hipnóticos — Tesis</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:'Segoe UI',Tahoma,sans-serif; background:#0f172a; color:#e2e8f0;
         min-height:100vh; display:flex; flex-direction:column; align-items:center; padding:48px 20px; }}
  h1 {{ font-size:26px; margin:0 0 6px; text-align:center; }}
  .sub {{ color:#94a3b8; margin:0 0 36px; text-align:center; max-width:640px; line-height:1.5; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:20px; width:100%; max-width:760px; }}
  .card {{ background:#1e293b; border:1px solid #334155; border-radius:14px; padding:24px; text-decoration:none;
          color:inherit; transition:transform .12s, border-color .12s; display:block; }}
  .card:hover {{ transform:translateY(-3px); border-color:#818cf8; }}
  .card h2 {{ margin:10px 0 6px; font-size:19px; }}
  .card p {{ margin:0; color:#94a3b8; font-size:13px; line-height:1.4; }}
  .pill {{ font-size:11px; text-transform:uppercase; letter-spacing:.6px; color:#818cf8; font-weight:bold; }}
  footer {{ margin-top:40px; color:#64748b; font-size:12px; text-align:center; }}
</style>
</head>
<body>
  <h1>Compras públicas municipales de hipnóticos</h1>
  <p class="sub">Análisis de adjudicaciones por licitación en Mercado Público
     ({ANIO_INICIO}–{ANIO_FIN}). Selecciona un principio activo.</p>
  <div class="grid">
{tarjetas}
  </div>
  <footer>Actualizado: {fecha}</footer>
</body>
</html>"""

    (DOCS / "index.html").write_text(index, encoding="utf-8")
    # .nojekyll evita que GitHub Pages procese el sitio con Jekyll.
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    # robots.txt: pide a los buscadores que NO indexen el sitio (solo por link).
    (DOCS / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    print(f"\nSitio publicado en: {DOCS}")
    for a, t in publicados:
        print(f"  - {a}  ({t})")


def main():
    p = argparse.ArgumentParser(description="Reprocesa y publica los dashboards en docs/.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--extraer-recientes", action="store_true",
                   help="Descarga los meses recientes antes de reprocesar.")
    g.add_argument("--completo", action="store_true",
                   help="Re-extrae todo el histórico (lento).")
    p.add_argument("--solo-publicar", action="store_true",
                   help="Solo arma docs/ con los dashboards ya generados.")
    args = p.parse_args()

    if args.solo_publicar:
        publicar()
        return

    modo = "completo" if args.completo else ("recientes" if args.extraer_recientes else "no")
    extraer(modo)
    filtrar()
    generar_dashboards()
    publicar()
    print("\n✔ Listo. Sube la carpeta docs/ (o deja que GitHub Actions lo haga).")


if __name__ == "__main__":
    main()
