# Publicar los dashboards en un link permanente (GitHub Pages)

Esta guía deja tus dashboards en una URL pública que está **siempre disponible**,
sin necesidad de tener tu computador encendido. Una vez al mes, GitHub baja los
datos nuevos, reprocesa y republica **solo**, en sus servidores.

Solo tienes que hacer la configuración inicial **una vez**. Tiempo: ~15 minutos.

---

## Qué hace cada cosa (resumen)

- `actualizar_y_publicar.py` → reprocesa todo y arma la carpeta `docs/` (el sitio web).
- `docs/` → es lo que GitHub Pages publica: `index.html` + `zopiclona.html` + `melatonina.html`.
- `.github/workflows/actualizar.yml` → la automatización: corre cada mes y en cada subida.

---

## Paso 1 — Comprueba que tienes Git

Abre la **Terminal** y escribe:

```bash
git --version
```

Si responde un número de versión, ya lo tienes. Si dice "command not found",
instálalo con `xcode-select --install` (acepta la ventana que aparece) y reintenta.

---

## Paso 2 — Crea el repositorio en GitHub

1. Entra a <https://github.com/new>.
2. **Repository name**: por ejemplo `tesis-farmacos-municipales`.
3. Déjalo en **Public** (es lo más simple para Pages y los datos ya son públicos).
4. **NO** marques "Add a README". Deja todo lo demás vacío.
5. Clic en **Create repository**.
6. En la página que aparece, copia la URL que termina en `.git`
   (algo como `https://github.com/TU_USUARIO/tesis-farmacos-municipales.git`).

---

## Paso 3 — Sube el proyecto

En la Terminal, ejecuta estos comandos **uno por uno**. Reemplaza la URL del
último por la que copiaste.

```bash
cd "/Users/benjabautista/Desktop/macbook air 2026/Adri"
git init
git branch -M main
git add .
git commit -m "Proyecto inicial: pipelines y dashboards"
git remote add origin https://github.com/TU_USUARIO/tesis-farmacos-municipales.git
git push -u origin main
```

Si te pide usuario y contraseña, la "contraseña" es un **token**: ve a
<https://github.com/settings/tokens> → *Generate new token (classic)* → marca
`repo` → genéralo y pégalo cuando lo pida. (O instala **GitHub Desktop**, que
maneja el login por ti.)

---

## Paso 4 — Activa GitHub Pages

1. En tu repositorio, ve a **Settings** (arriba) → **Pages** (menú izquierdo).
2. En **Build and deployment → Source**, elige **GitHub Actions**.
3. Listo, no toques nada más ahí.

---

## Paso 5 — Lanza la primera publicación

1. Ve a la pestaña **Actions** del repositorio.
2. Si te pide habilitar los workflows, acepta (**I understand my workflows, enable them**).
3. Elige **"Actualizar y publicar dashboards"** → botón **Run workflow** → **Run workflow**.
4. Espera a que termine (un par de minutos, círculo verde ✓).

Tu link quedará en **Settings → Pages**, arriba ("Your site is live at …").
Será algo como:

```
https://TU_USUARIO.github.io/tesis-farmacos-municipales/
```

Ese es el link que le pasas a tu profesor. Abre una portada con los dos dashboards.

---

## ¿Cómo se mantiene actualizado?

- **Automático:** el día 5 de cada mes, GitHub baja los meses recientes,
  reprocesa y republica solo. No haces nada.
- **A mano cuando quieras:** Actions → Run workflow.
- **Si cambias el código localmente:** vuelve a subir con
  ```bash
  git add .
  git commit -m "Cambios"
  git push
  ```
  y el sitio se reconstruye solo con cada push.

---

## Notas

- El repositorio guarda los datos ya extraídos (livianos). La automatización
  **no** vuelve a descargar todo el histórico cada vez: solo los meses recientes.
- Si prefieres que el repo sea privado, Pages igual funciona, pero la URL del
  sitio sigue siendo pública (cualquiera con el link lo ve). El código quedaría oculto.
- Para cambiar la frecuencia, edita la línea `cron` en
  `.github/workflows/actualizar.yml`.
