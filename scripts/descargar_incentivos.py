"""
scripts/descargar_incentivos.py — Descarga la vista IncentivosComerciales/
DetalleClienteIncentivo de Tableau (plan de ajecam360, Fase 9-10 "Incentivos": por
fin saber POR QUÉ se dio el descuento). Mismo mecanismo probado en
scripts/descargar.py (login usuario/clave + control de navegador real, porque el
filtro de mes de estos workbooks no se puede mover por la API REST normal) —
adaptado a este workbook, que es DISTINTO al de ventas.

⚠️ SIN VERIFICAR contra el workbook real: nunca se ha corrido esto contra
IncentivosComerciales en vivo (no hay credenciales disponibles fuera de GitHub
Actions). Se reutiliza toda la lógica ya probada de descargar.py (login, ubicar el
frame con checkboxes, exportar como CSV vía "Tabulación cruzada"), pero el nombre
exacto del filtro de mes en ESTE workbook es una suposición razonable (misma
convención que el resto de reportes de AJE sobre fecha_liquidacion), no un hecho
confirmado. Si la primera corrida no encuentra el filtro esperado, el script
imprime los textos reales de los checkboxes que sí encontró (mismo patrón
diagnóstico de descargar.py) en vez de fallar a ciegas — de ahí se ajusta en un
commit de una línea, no hay que rediseñar nada.

Variables de entorno esperadas:
    TABLEAU_USER             usuario de Tableau (secret, el mismo de descargar.py)
    TABLEAU_PASSWORD         clave de Tableau (secret, el mismo de descargar.py)
    MES_OBJETIVO             default: "agosto"
    MES_A_DESMARCAR          default: "" (si vacío, no desmarca nada)
    SALIDA_DIR               default: "./salida"
"""
import os
import re
import sys
import time
import urllib.parse

RE_DESCARGAR = re.compile(r"Descargar|Download", re.IGNORECASE)

from playwright.sync_api import sync_playwright  # noqa: E402

MES_OBJETIVO = os.environ.get("MES_OBJETIVO", "agosto")
MES_A_DESMARCAR = os.environ.get("MES_A_DESMARCAR", "")
SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

# Workbook DISTINTO al de ventas (Reportería_Comercial) — este es IncentivosComerciales,
# vista DetalleClienteIncentivo (plan: cod_cliente/cod_zona/cod_ruta/Sucursal/Segmento/
# cod_incentivo/inc_acciones/inc_condiciones/Usos Incentivo/Importe Incentivo/% Incentivo).
URL_VISTA = "https://bitableau.ajegroup.com/#/site/Cam/views/IncentivosComerciales/DetalleClienteIncentivo?:iid=1"
URL_LOGIN = "https://bitableau.ajegroup.com/#/signin"

MESES_EN = {
    "enero": "January", "febrero": "February", "marzo": "March", "abril": "April",
    "mayo": "May", "junio": "June", "julio": "July", "agosto": "August",
    "septiembre": "September", "octubre": "October", "noviembre": "November",
    "diciembre": "December",
}


def iniciar_sesion(pagina):
    """Idéntico a descargar.py — login usuario/clave nativo de Tableau, sin SSO/2FA,
    de cero en cada corrida (una sesión pre-guardada vence en ~18h sin avisar)."""
    usuario = os.environ.get("TABLEAU_USER", "").strip()
    clave = os.environ.get("TABLEAU_PASSWORD", "")
    if not usuario or not clave:
        raise SystemExit("Faltan TABLEAU_USER / TABLEAU_PASSWORD (secrets de GitHub).")

    print("Iniciando sesion en Tableau...", flush=True)
    pagina.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60000)
    pagina.wait_for_timeout(5000)

    campo_usuario = None
    for sel in ["input[name='username']", "input#username", "input[type='text']"]:
        if pagina.locator(sel).count() > 0:
            campo_usuario = pagina.locator(sel).first
            break
    campo_clave = None
    for sel in ["input[name='password']", "input#password", "input[type='password']"]:
        if pagina.locator(sel).count() > 0:
            campo_clave = pagina.locator(sel).first
            break
    if campo_usuario is None or campo_clave is None:
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_login_sin_campos.png"))
        raise SystemExit("No se encontraron los campos de login -- ver error_login_sin_campos.png")

    campo_usuario.fill(usuario)
    campo_clave.fill(clave)
    campo_clave.press("Enter")
    pagina.wait_for_timeout(10000)

    if pagina.locator("input[type='password']").count() > 0:
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_login_rechazado.png"))
        raise SystemExit("Login rechazado -- revisar usuario/clave (ver error_login_rechazado.png)")
    print("Sesion iniciada OK.", flush=True)


def encontrar_frame_con_checkboxes(pagina, minimo=1, intentos=18, espera_s=10):
    """minimo=1 (no >=10 como en ventas): IncentivosComerciales puede tener MENOS
    meses con datos que la vista de ventas (los incentivos no necesariamente
    corren desde febrero) — un umbral de 10 asumiría de más."""
    anterior = -1
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
        print(f"  {(i + 1) * espera_s}s -- mejor frame: {mejor_n} checkboxes", flush=True)
        if mejor_n >= minimo and mejor_n == anterior:
            return mejor
        anterior = mejor_n
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


def click_checkbox_por_texto(fr, texto_buscado, reintentos=3):
    candidatos = {texto_buscado, MESES_EN.get(texto_buscado.lower(), texto_buscado)}
    for intento in range(reintentos):
        try:
            checks = fr.locator("input[type=checkbox]")
            for i in range(checks.count()):
                if texto_de_checkbox(checks.nth(i)) in candidatos:
                    checks.nth(i).click(timeout=10000)
                    return True
            return False
        except Exception as e:
            print(f"    (reintento {intento + 1}/{reintentos} tras: {type(e).__name__})", flush=True)
            time.sleep(2)
    return False


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1600, "height": 1000},
                                          accept_downloads=True, locale="es-GT")
        pagina = contexto.new_page()
        iniciar_sesion(pagina)
        print(f"Navegando: {URL_VISTA}", flush=True)
        pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

        print("Buscando el frame con los filtros...", flush=True)
        fr = encontrar_frame_con_checkboxes(pagina)
        if fr is None:
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_filtros.png"))
            if pagina.locator("text=/Nombre de usuario|Username/i").count() > 0:
                raise SystemExit("La sesion parece haber vencido a mitad de la corrida (aparece pantalla de login).")
            raise SystemExit(
                "No se encontraron checkboxes de filtro en esta vista -- ver error_sin_filtros.png. "
                "Puede que IncentivosComerciales filtre distinto a Reportería_Comercial (ej. dropdown "
                "en vez de checkboxes) -- si es así, este script necesita un selector distinto acá."
            )

        print(f"Marcando '{MES_OBJETIVO}'...", flush=True)
        if not click_checkbox_por_texto(fr, MES_OBJETIVO):
            checks = fr.locator("input[type=checkbox]")
            textos = [texto_de_checkbox(checks.nth(i)) for i in range(checks.count())]
            print("TEXTOS REALES de los checkboxes encontrados (para ajustar el filtro):", flush=True)
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
                n = f.get_by_text(RE_DESCARGAR).count()
                if n > mejor_n:
                    mejor, mejor_n = f, n
            except Exception:
                pass
        if mejor is not None:
            fr = mejor

        print("Click en 'Descargar'/'Download'...", flush=True)
        fr.get_by_text(RE_DESCARGAR).first.click()
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
                loc = scope.locator("button").filter(has_text=RE_DESCARGAR)
                if loc.count() > 0:
                    boton_final = loc.last
                    break
            except Exception:
                pass
        if boton_final is None:
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_boton_final.png"))
            raise SystemExit("No se encontro boton Descargar/Download del dialogo")

        if boton_final.is_disabled():
            print(f"SIN DATOS -- IncentivosComerciales no tiene filas para "
                  f"{MES_OBJETIVO} (botón deshabilitado, tabulación cruzada vacía). No es un error.",
                  flush=True)
            contexto.close()
            navegador.close()
            return 0

        print("Click final, esperando el archivo...", flush=True)
        with pagina.expect_download(timeout=90000) as info_descarga:
            boton_final.click()
        descarga = info_descarga.value
        nombre = f"incentivos_{MES_OBJETIVO}.csv"
        ruta_salida = os.path.join(SALIDA_DIR, nombre)
        descarga.save_as(ruta_salida)
        print(f"OK -- Archivo descargado: {ruta_salida} ({os.path.getsize(ruta_salida):,} bytes)", flush=True)

        contexto.close()
        navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
