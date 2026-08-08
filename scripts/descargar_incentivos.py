"""
scripts/descargar_incentivos.py — Descarga la vista IncentivosComerciales/
DetalleClienteIncentivo de Tableau (plan de ajecam360, Fase 9-10 "Incentivos": por
fin saber POR QUÉ se dio el descuento). Mismo mecanismo probado en
scripts/descargar.py (login usuario/clave + control de navegador real, porque el
filtro de mes de estos workbooks no se puede mover por la API REST normal) —
adaptado a este workbook, que es DISTINTO al de ventas.

✅ VERIFICADO contra el workbook real (2026-08-08, corrida #1): login y navegación
funcionan, y la data confirma exactamente el esquema del plan (cod_cliente/cod_zona/
cod_ruta/Sucursal/Segmento/cod_incentivo IC-xxxxxx/inc_acciones/inc_condiciones/
Usos Incentivo/Importe Incentivo/% Incentivo). Lo que falló fue el selector de
filtro: a diferencia de la vista de ventas (checkboxes), IncentivosComerciales usa
filtros de UN SOLO VALOR tipo dropdown ("Mes, Año", "mundo", "Regiones", "Sucursal",
"Zona", "Ruta", "Segmento", "Canal", "Marca") — confirmado con el screenshot de
diagnóstico que dejó la corrida #1 (error_sin_filtros.png). Este archivo ya está
adaptado a ese patrón (seleccionar_mes_dropdown), pero el selector exacto del popup
de opciones SIGUE sin confirmar en vivo (no se puede inspeccionar el DOM real fuera
de una corrida) — si falla, deja error_dropdown_no_encontrado.png + el texto de
todo lo clickeable que encontró, mismo patrón diagnóstico que ya destrabó
descargar.py en varias iteraciones.

Corrección sobre la primera corrida (run #2, 2026-08-08): el dropdown, al abrirse,
resultó ser la MISMA lista de checkboxes que la vista de ventas (no un selector de
valor único) -- así que MES_A_DESMARCAR sí aplica, igual que en descargar.py.

Variables de entorno esperadas:
    TABLEAU_USER             usuario de Tableau (secret, el mismo de descargar.py)
    TABLEAU_PASSWORD         clave de Tableau (secret, el mismo de descargar.py)
    MES_OBJETIVO              default: "agosto"
    MES_A_DESMARCAR           default: "" (si vacío, no desmarca nada)
    SALIDA_DIR                default: "./salida"
"""
import os
import re
import sys
import time

RE_DESCARGAR = re.compile(r"Descargar|Download", re.IGNORECASE)
# Detecta el valor ACTUAL del filtro (ej. "mayo de 2026") sin importar cuál mes esté
# seleccionado al momento de correr -- eso es lo que hay que clickear para abrir el dropdown.
RE_MES_ANIO_ACTUAL = re.compile(
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|"
    r"noviembre|diciembre)\s+de\s+\d{4}",
    re.IGNORECASE,
)

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


def encontrar_frame_con_filtro_mes(pagina, intentos=18, espera_s=10):
    """A diferencia de descargar.py (cuenta checkboxes), acá se busca el frame que
    contenga el valor actual del filtro de mes (ej. 'mayo de 2026') -- confirmado
    por screenshot que ese es el patrón real de esta vista (dropdown, no checkboxes)."""
    for i in range(intentos):
        time.sleep(espera_s)
        for f in pagina.frames:
            try:
                if f.get_by_text(RE_MES_ANIO_ACTUAL).count() > 0:
                    print(f"  {(i + 1) * espera_s}s -- frame de filtros encontrado", flush=True)
                    return f
            except Exception:
                pass
        print(f"  {(i + 1) * espera_s}s -- todavía sin encontrar el filtro de mes", flush=True)
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


def click_checkbox_conteniendo(scope, texto_buscado: str, reintentos=3) -> bool:
    """Igual que click_checkbox_por_texto de descargar.py, pero por SUBSTRING (acá
    la etiqueta es 'agosto de 2026', no solo 'agosto')."""
    for intento in range(reintentos):
        try:
            checks = scope.locator("input[type=checkbox]")
            for i in range(checks.count()):
                if texto_buscado.lower() in texto_de_checkbox(checks.nth(i)).lower():
                    checks.nth(i).click(timeout=10000)
                    return True
            return False
        except Exception as e:
            print(f"    (reintento {intento + 1}/{reintentos} tras: {type(e).__name__})", flush=True)
            time.sleep(2)
    return False


def seleccionar_mes_dropdown(pagina, fr, mes_objetivo: str, mes_a_desmarcar: str) -> bool:
    """El filtro 'Mes, Año' es un dropdown COLAPSADO que, al abrirse, muestra la
    MISMA lista de checkboxes que la vista de ventas (confirmado por screenshot:
    '(Todo)', 'mayo de 2026' ✓, 'junio de 2026', 'julio de 2026', 'agosto de 2026',
    más los botones 'Cancelar'/'Aplicar'). La corrida anterior clickeaba el TEXTO de
    la opción en vez de su checkbox -- no marcaba nada y el popup se quedaba abierto
    bloqueando todo lo demás (el 'tab-glass' que interceptó el click de 'Descargar').
    Acá se usan checkboxes reales + se confirma con 'Aplicar'."""
    try:
        trigger = fr.get_by_text(RE_MES_ANIO_ACTUAL).first
        trigger.click(timeout=10000)
    except Exception as e:
        print(f"  no se pudo clickear el valor actual del filtro: {e}", flush=True)
        return False

    time.sleep(2)
    pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_mes_abierto.png"))

    popup_scope = None
    for scope in (fr, pagina):
        try:
            if scope.locator("input[type=checkbox]").count() > 0:
                popup_scope = scope
                break
        except Exception:
            pass
    if popup_scope is None:
        return False

    marcado = click_checkbox_conteniendo(popup_scope, mes_objetivo)
    if not marcado:
        return False
    time.sleep(1)
    if mes_a_desmarcar:
        click_checkbox_conteniendo(popup_scope, mes_a_desmarcar)
        time.sleep(1)

    pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_mes_marcado.png"))

    aplicado = False
    for scope in (popup_scope, pagina, fr):
        try:
            boton = scope.get_by_text("Aplicar", exact=True)
            if boton.count() > 0:
                boton.first.click(timeout=5000)
                aplicado = True
                break
        except Exception:
            pass
    if not aplicado:
        print("  no se encontró el botón 'Aplicar' -- se sigue de todas formas.", flush=True)
    return True


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1600, "height": 1000},
                                          accept_downloads=True, locale="es-GT")
        pagina = contexto.new_page()
        iniciar_sesion(pagina)
        print(f"Navegando: {URL_VISTA}", flush=True)
        pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

        print("Buscando el frame con el filtro de mes...", flush=True)
        fr = encontrar_frame_con_filtro_mes(pagina)
        if fr is None:
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_filtros.png"))
            if pagina.locator("text=/Nombre de usuario|Username/i").count() > 0:
                raise SystemExit("La sesion parece haber vencido a mitad de la corrida (aparece pantalla de login).")
            raise SystemExit(
                "No se encontró el filtro 'Mes, Año' (patrón 'agosto de 2026') en esta vista "
                "-- ver error_sin_filtros.png. El layout puede haber cambiado."
            )

        print(f"Abriendo dropdown y marcando '{MES_OBJETIVO}'...", flush=True)
        if not seleccionar_mes_dropdown(pagina, fr, MES_OBJETIVO, MES_A_DESMARCAR):
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_dropdown_no_encontrado.png"))
            # Diagnóstico: todo el texto visible en la página + el frame, para ajustar
            # el selector en un commit puntual en vez de adivinar a ciegas.
            try:
                print("TEXTO VISIBLE en la página (para ajustar el selector):", flush=True)
                print(pagina.inner_text("body")[:3000], flush=True)
            except Exception:
                pass
            raise SystemExit(
                f"No se pudo seleccionar '{MES_OBJETIVO}' en el dropdown de mes "
                "-- ver error_dropdown_no_encontrado.png y el texto arriba"
            )
        time.sleep(2)

        print("Esperando 60s fijos a que la tabla recargue...", flush=True)
        time.sleep(60)
        # Defensa extra: si el overlay de carga de Tableau ('tab-glass') sigue
        # visible, esperar hasta que desaparezca antes de clickear nada más -- fue
        # justo ese overlay el que interceptó el click de 'Descargar' en la corrida
        # anterior (el popup del filtro había quedado abierto de fondo).
        try:
            for f in pagina.frames:
                glass = f.locator(".tab-glass")
                if glass.count() > 0:
                    print("  overlay de carga detectado, esperando a que desaparezca...", flush=True)
                    glass.first.wait_for(state="hidden", timeout=30000)
        except Exception:
            pass
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
        with pagina.expect_download(timeout=150000) as info_descarga:
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
