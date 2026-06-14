import pandas as pd
import glob
import os

from config_rutas import ZOPICLONA_FILTRADOS

# =========================================================
# 1. RUTA DE TUS ARCHIVOS (centralizada en config_rutas.py)
# =========================================================
ROOT = ZOPICLONA_FILTRADOS

def limpiar_precio(valor):
    """Limpia puntos y comas de los precios chilenos"""
    if pd.isna(valor): return 0
    s = str(valor).strip()
    if "." in s and "," in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0

# =========================================================
# 2. ESCANEO DE ARCHIVOS
# =========================================================
archivos = glob.glob(str(ROOT / "**" / "*.csv"), recursive=True)
hallazgos = []

print(f"--- Iniciando escaneo en: {ROOT} ---")

for archivo in archivos:
    try:
        # Cargamos el archivo
        df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")
        
        if df.empty: continue

        # Limpiamos la columna de Valor Unitario para poder comparar
        df["VALOR_LIMPIO"] = df["VALOR C/U"].apply(limpiar_precio)

        # BUSCAMOS EL ERROR: Cualquier precio unitario mayor a 500.000 
        # (Ajusté el filtro para capturar el de 2.5M que viste)
        errores = df[df["VALOR_LIMPIO"] > 200].copy()

        if not errores.empty:
            errores["ARCHIVO_DONDE_ESTA"] = os.path.basename(archivo)
            hallazgos.append(errores)
            
    except Exception as e:
        print(f"Error leyendo {os.path.basename(archivo)}: {e}")

# =========================================================
# 3. RESULTADOS
# =========================================================
if hallazgos:
    resultado_final = pd.concat(hallazgos, ignore_index=True)
    
    print("\n" + "!"*50)
    print("¡DATO ANÓMALO ENCONTRADO!")
    print("!"*50)
    
    # Mostramos los datos clave para que lo ubiques
    columnas_interes = ["ARCHIVO_DONDE_ESTA", "COMPRADOR", "VALOR C/U", "TOTAL", "CANTIDAD", "LINK"]
    print(resultado_final[columnas_interes].to_string(index=False))
    
    print("\n" + "="*50)
    print("CONSEJO: Ve a ese archivo CSV, búscalo y corrígelo.")
    print("Suele ser que la CANTIDAD dice 1 pero el TOTAL es el de una caja grande.")
    print("="*50)
else:
    print("\nNo se encontraron valores mayores a 500.000.")
    print("Intentando mostrar los 3 valores más altos encontrados por si acaso:")
    # (Este bloque es solo por si el filtro de 500k fue muy alto)