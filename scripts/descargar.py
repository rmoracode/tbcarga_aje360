"""
scripts/descargar.py — Version para GitHub Actions del automatizador de
'DATA PARA ANALISIS' (Tableau). Mismo flujo probado localmente en ajecam360/
version360/navegador/descargar_agosto.py, adaptado para correr headless en CI:

  - La sesion NO vive en un archivo del repo (nunca se commitea) -- se recibe
    por la variable de entorno TABLEAU_STORAGE_STATE (JSON completo, el mismo
    contenido que genera login.py localmente), guardada como GitHub Secret.
  - headless=True (sin pantalla en el runner).
  - Sucursal / mes objetivo / mes a desmarcar por variables de entorno, para
    poder correr el mismo script una vez por sucursal desde el workflow.

Variables de entorno esperadas:
    TABLEAU_STORAGE_STATE   JSON completo de la sesion (contenido, no ruta)
    SUCURSAL                default: "AJEMAYA SUCURSAL BARBERENA"
    MES_OBJETIVO             default: "agosto"
    MES_A_DESMARCAR          default: "" (si vacio, no desmarca nada)
    SALIDA_DIR               default: "./salida"
"""
import json
import os
import sys
import tempfile
import time
import urllib.parse

from playwright.sync_api import sync_playwright

SUCURSAL = os.environ.get("SUCURSAL", "AJEMAYA SUCURSAL BARBERENA")
MES_OBJETIVO = os.environ.get("MES_OBJETIVO", "agosto")
MES_A_DESMARCAR = os.environ.get("MES_A_DESMARCAR", "")
SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

SUCURSAL_Q = urllib.parse.quote(SUCURSAL)
URL_VISTA = (
    "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISIS"
    f"?:iid=1&nomb_sucursal={SUCURSAL_Q}"
)


def _escribir_estado_sesion() -> str:
    contenido = os.environ.get("TABLEAU_STORAGE_STATE", "").strip()
    if not contenido:
        raise SystemExit(
            "Falta TABLEAU_STORAGE_STATE (secret de GitHub Actions) -- "
            "generalo localmente con login.py y pegalo como secret."
        )
    # Validar que sea JSON valido antes de escribirlo, para dar un error claro
    # en vez de que Playwright falle mas adelante con un mensaje confuso.
    try:
        json.loads(contenido)
    except json.JSONDecodeError as e:
        raise SystemExit(f"TABLEAU_STORAGE_STATE no es JSON valido: {e}")
    fd, ruta = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta


def encontrar_frame_con_checkboxes(pagina, minimo=10, intentos=18, espera_s=10):
    for i in range(intentos):
        time.sleep(espera_s)
        mejor, mejor_n = None, 0
        for f in pagina.frames:
            try:
                n = f.locator("input[type=checkbox]").count()
                if n > mejor_n:
                    mejor, mejor_n = f, n
            except Exception:
                pass
        print(f"  {(i+1)*espera_s}s -- mejor frame: {mejor_n} checkboxes", flush=True)
        if mejor_n >= minimo:
            return mejor
    return None


def texto_de_checkbox(el) -> str:
    return el.evaluate("""
        e => {
            let l = e.closest('label');
            if (l) return l.innerText.trim();
            let p = e.parentElement;
            for (let k=0;k<4 && p;k++){ if(p.innerText && p.innerText.trim()) return p.innerText.trim().slice(0,60); p=p.parentElement; }
            return '';
        }
    """)


def click_checkbox_por_texto(fr, texto_buscado):
    checks = fr.locator("input[type=checkbox]")
    for i in range(checks.count()):
        if texto_de_checkbox(checks.nth(i)) == texto_buscado:
            checks.nth(i).click()
            return True
    return False


def main() -> int:
    ruta_estado = _escribir_estado_sesion()
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            contexto = navegador.new_context(storage_state=ruta_estado,
                                              viewport={"width": 1600, "height": 1000},
                                              accept_downloads=True)
            pagina = contexto.new_page()
            print(f"Navegando: {URL_VISTA}", flush=True)
            pagina.goto(URL_VISTA, wait_until="networkidle", timeout=60000)

            print("Buscando el frame con los filtros...", flush=True)
            fr = encontrar_frame_con_checkboxes(pagina)
            if fr is None:
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_filtros.png"))
                # Chequeo rapido: si aparece la pantalla de login, el secret esta vencido.
                if pagina.locator("text=/Nombre de usuario/i").count() > 0:
                    raise SystemExit(
                        "La sesion vencio (aparece pantalla de login). "
                        "Hay que regenerar TABLEAU_STORAGE_STATE localmente."
                    )
                raise SystemExit("No se encontraron checkboxes -- ver error_sin_filtros.png")

            print(f"Marcando '{MES_OBJETIVO}'...", flush=True)
            if not click_checkbox_por_texto(fr, MES_OBJETIVO):
                # Diagnostico: mostrar los textos REALES de todos los checkboxes
                # en vez de fallar a ciegas -- puede ser un tema de idioma/locale
                # distinto entre el runner de CI y el Chrome local donde se probo.
                checks = fr.locator("input[type=checkbox]")
                textos = [texto_de_checkbox(checks.nth(i)) for i in range(checks.count())]
                print("TEXTOS REALES de los checkboxes encontrados:", flush=True)
                for i, t in enumerate(textos):
                    print(f"  [{i}] {t!r}", flush=True)
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_checkbox_no_encontrado.png"))
                raise SystemExit(f"No se encontro el checkbox de mes '{MES_OBJETIVO}' -- ver textos arriba")
            time.sleep(2)
            if MES_A_DESMARCAR:
                print(f"Desmarcando '{MES_A_DESMARCAR}'...", flush=True)
                click_checkbox_por_texto(fr, MES_A_DESMARCAR)

            print("Esperando 60s fijos a que la tabla recargue...", flush=True)
            time.sleep(60)
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "antes_de_descargar.png"))

            mejor, mejor_n = None, 0
            for f in pagina.frames:
                try:
                    n = f.locator("button", has_text="Descargar").count()
                    if n > mejor_n:
                        mejor, mejor_n = f, n
                except Exception:
                    pass
            if mejor is not None:
                fr = mejor

            print("Click en 'Descargar'...", flush=True)
            fr.locator("text=Descargar").first.click()
            time.sleep(2)

            opcion = None
            for scope in (pagina, fr):
                for patron in ["cruzada", "Crosstab"]:
                    try:
                        loc = scope.get_by_text(patron, exact=False)
                        if loc.count() > 0:
                            opcion = loc.first
                            break
                    except Exception:
                        pass
                if opcion is not None:
                    break
            if opcion is None:
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_menu.png"))
                raise SystemExit("No se encontro 'Tabulación cruzada' -- ver error_sin_menu.png")

            print("Click en 'Tabulación cruzada'...", flush=True)
            opcion.click()
            time.sleep(4)

            for scope in (fr, pagina):
                try:
                    radio_csv = scope.get_by_text("CSV", exact=True)
                    if radio_csv.count() > 0:
                        radio_csv.first.click()
                        break
                except Exception:
                    pass
            time.sleep(1)

            boton_final = None
            for scope in (fr, pagina):
                try:
                    loc = scope.locator("button:has-text('Descargar')")
                    if loc.count() > 0:
                        boton_final = loc.last
                        break
                except Exception:
                    pass
            if boton_final is None:
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_boton_final.png"))
                raise SystemExit("No se encontro boton Descargar del dialogo")

            print("Click final, esperando el archivo...", flush=True)
            with pagina.expect_download(timeout=90000) as info_descarga:
                boton_final.click()
            descarga = info_descarga.value
            nombre = f"{MES_OBJETIVO}_{SUCURSAL.replace(' ', '_')}.csv"
            ruta_salida = os.path.join(SALIDA_DIR, nombre)
            descarga.save_as(ruta_salida)
            print(f"OK -- Archivo descargado: {ruta_salida} ({os.path.getsize(ruta_salida):,} bytes)", flush=True)

            contexto.close()
            navegador.close()
        return 0
    finally:
        try:
            os.remove(ruta_estado)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
