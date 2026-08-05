"""
scripts/login.py — Corre esto LOCAL (no en GitHub Actions) cada vez que haya
que renovar la sesion de Tableau. Abre una ventana real de Chrome, iniciás
sesion vos, y el script exporta el estado (cookies + localStorage) a
estado_sesion.json -- ese contenido es lo que va como GitHub Secret
TABLEAU_STORAGE_STATE.

Uso:
    py scripts/login.py
    (iniciar sesion en la ventana que se abre; se toman capturas cada 15s
     durante 5 min, el estado se guarda automaticamente en cada vuelta)

Despues de correrlo:
    1. Abrir estado_sesion.json y copiar TODO el contenido.
    2. GitHub -> tu repo -> Settings -> Secrets and variables -> Actions
       -> New repository secret -> nombre: TABLEAU_STORAGE_STATE -> pegar.
"""
import os
import time

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.abspath(__file__))
PERFIL_DIR = os.path.join(RAIZ, "..", "chrome_profile_tableau")
ESTADO_SESION = os.path.join(RAIZ, "..", "estado_sesion.json")
URL_VISTA = "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISIS?:iid=1"

os.makedirs(PERFIL_DIR, exist_ok=True)

with sync_playwright() as p:
    contexto = p.chromium.launch_persistent_context(
        PERFIL_DIR, channel="chrome", headless=False,
        viewport={"width": 1400, "height": 900},
    )
    pagina = contexto.new_page()
    print(f"Abriendo: {URL_VISTA}")
    pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

    print("\nIniciá sesión en la ventana que se abrió (tu usuario normal de AJE).")
    print("Se guarda el estado de sesión cada 15s durante 5 min -- no hace falta")
    print("hacer nada más acá, solo esperar a que termines de loguearte.\n")

    for i in range(20):
        pagina.wait_for_timeout(15000)
        contexto.storage_state(path=ESTADO_SESION)
        print(f"  vuelta #{i+1}: estado guardado")

    print(f"\nListo: {ESTADO_SESION}")
    print("Copiá TODO el contenido de ese archivo y pegalo como el secret")
    print("TABLEAU_STORAGE_STATE en GitHub (Settings > Secrets and variables > Actions).")
    contexto.close()
