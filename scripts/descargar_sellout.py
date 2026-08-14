"""
scripts/descargar_sellout.py — Version para GitHub Actions del automatizador de
"DATA PARA ANALISIS SELLOUT" (Tableau, econored/distribuidores independientes).
Copia deliberada de scripts/descargar.py -- MISMO login, MISMA mecánica de
verificación de checkboxes de Mes/Año, MISMA descarga de tabulación cruzada --
adaptada solo en 2 puntos reales:

  1. La vista es otra pestaña del MISMO workbook (Reportera_Comercial), así que
     la URL cambia de DATAPARAANALISIS a DATAPARAANALISISSELLOUT (confirmado
     por el usuario: mismo sitio, mismo libro, otra pestaña).
  2. A diferencia de la vista de ventas (donde nomb_sucursal se filtra por
     parámetro de URL), acá "nomb_sucursal" es un panel de checkboxes MULTI-
     SELECT con "(Todo)" + 40 territorios, con botones Cancelar/Aplicar propios
     (confirmado con capturas reales del panel, 2026-08-14) -- necesita su
     propia función de selección (seleccionar_solo_territorio), no la reutiliza
     de Mes/Año porque esas SÍ aplican el cambio al vuelo, sin botón "Aplicar".

Variables de entorno esperadas:
    TABLEAU_USER             usuario de Tableau (secret, mismo que descargar.py)
    TABLEAU_PASSWORD         clave de Tableau (secret, mismo que descargar.py)
    TERRITORIO                default: "CHIQUIMULA" (ver scripts/sucursales_sellout.py)
    MES_OBJETIVO              default: "agosto"
    MES_A_DESMARCAR           default: "" (si vacio, no desmarca nada)
    ANIO_OBJETIVO             default: año actual UTC
    SALIDA_DIR                default: "./salida"

NO PROBADO todavía contra la vista real (no hay forma de verificarlo sin correr
en GitHub Actions con las credenciales reales) -- si algún selector no matchea,
las capturas de pantalla que deja en SALIDA_DIR son la forma de diagnosticar
qué cambiar, mismo criterio que descargar.py.
"""
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone

RE_DESCARGAR = re.compile(r"Descargar|Download", re.IGNORECASE)
RE_APLICAR = re.compile(r"Aplicar|Apply", re.IGNORECASE)
RE_TODO = re.compile(r"^\(Todo\)$|^\(All\)$", re.IGNORECASE)

from playwright.sync_api import sync_playwright

TERRITORIO = os.environ.get("TERRITORIO", "CHIQUIMULA")
MES_OBJETIVO = os.environ.get("MES_OBJETIVO", "agosto")
MES_A_DESMARCAR = os.environ.get("MES_A_DESMARCAR", "")
ANIO_OBJETIVO = os.environ.get("ANIO_OBJETIVO") or str(datetime.now(timezone.utc).year)
SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

URL_VISTA = "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISISSELLOUT?:iid=3"
URL_LOGIN = "https://bitableau.ajegroup.com/#/signin"


def iniciar_sesion(pagina):
    """Idéntico a scripts/descargar.py::iniciar_sesion -- mismo formulario nativo,
    sin SSO ni 2FA, mismos secrets."""
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


def encontrar_frame_con_checkboxes(pagina, minimo=10, intentos=18, espera_s=10):
    """Idéntico a descargar.py -- ver ese archivo para el porqué de esperar a que
    el conteo se estabilice en vez de un mínimo fijo."""
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
        print(f"  {(i+1)*espera_s}s -- mejor frame: {mejor_n} checkboxes", flush=True)
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


MESES_EN = {
    "enero": "January", "febrero": "February", "marzo": "March", "abril": "April",
    "mayo": "May", "junio": "June", "julio": "July", "agosto": "August",
    "septiembre": "September", "octubre": "October", "noviembre": "November",
    "diciembre": "December",
}
MESES_LISTA = set(MESES_EN.keys()) | {v.lower() for v in MESES_EN.values()}


def click_checkbox_por_texto(fr, texto_buscado, reintentos=3):
    """Idéntico a descargar.py."""
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
            print(f"    (reintento {intento+1}/{reintentos} tras: {type(e).__name__})", flush=True)
            time.sleep(2)
    return False


def estado_de_meses(fr, mes_objetivo: str) -> tuple[bool, list[str]]:
    """Idéntico a descargar.py."""
    candidatos_objetivo = {mes_objetivo, MESES_EN.get(mes_objetivo.lower(), mes_objetivo)}
    objetivo_marcado = False
    otros_marcados = []
    checks = fr.locator("input[type=checkbox]")
    for i in range(checks.count()):
        el = checks.nth(i)
        try:
            if not el.is_checked():
                continue
        except Exception:
            continue
        texto = texto_de_checkbox(el)
        if texto in candidatos_objetivo:
            objetivo_marcado = True
        elif texto.lower() in MESES_LISTA:
            otros_marcados.append(texto)
    return objetivo_marcado, otros_marcados


def estado_de_anio(fr, anio_objetivo: str) -> bool:
    """Idéntico a descargar.py."""
    checks = fr.locator("input[type=checkbox]")
    for i in range(checks.count()):
        el = checks.nth(i)
        try:
            if not el.is_checked():
                continue
        except Exception:
            continue
        if texto_de_checkbox(el) == anio_objetivo:
            return True
    return False


def abrir_desplegable_sucursal(pagina) -> bool:
    """NUEVO -- corrige el bug real del primer intento (run #1, 2026-08-14): a
    diferencia de Mes/Año (checkboxes YA visibles al cargar la página),
    nomb_sucursal arranca COLAPSADO -- un cuadrito que muestra el valor actual
    (ej. "(Todo)" o "HUEHUETENANGO") con una flechita, y la lista de 40
    territorios con checkboxes recién aparece en el DOM después de hacer click
    ahí (confirmado con captura real del usuario, 2026-08-14: se ve la etiqueta
    "nomb_sucursal" con el cuadro clickeable justo debajo).

    Estrategia: buscar el texto EXACTO "nomb_sucursal" en cada frame (es la
    etiqueta del filtro, no el valor), y clickear el primer elemento clickeable
    que aparece DEBAJO de esa etiqueta (mismo eje X, Y mayor, la distancia más
    chica) -- ese es el cuadro colapsado. Nunca vi el DOM real, así que esto
    puede necesitar un ajuste más si el layout no es exactamente ese; por eso
    _renderizar_torre dejó capturas de diagnóstico en cada paso."""
    for fr in pagina.frames:
        try:
            etiqueta = fr.get_by_text("nomb_sucursal", exact=True)
            if etiqueta.count() == 0:
                continue
            box_etiqueta = etiqueta.first.bounding_box()
            if box_etiqueta is None:
                continue

            # Busca, en el mismo frame, el elemento clickeable más cercano
            # DEBAJO de la etiqueta (heurística de posición, no de selector --
            # más resiliente a cambios de clase/id que Tableau no expone estables).
            # evaluate_handle (no evaluate) para quedarse con una REFERENCIA real
            # al elemento del DOM -- clickearlo vía Playwright (no coordenadas de
            # mouse a mano) evita el problema de mezclar coordenadas relativas al
            # frame con coordenadas de la página si el iframe no arranca en (0,0).
            handle = fr.evaluate_handle("""
                ([xEtiqueta, yEtiqueta]) => {
                    const elementos = document.querySelectorAll('div, span, td, [role="button"], [role="listbox"]');
                    let mejor = null, mejorDist = Infinity;
                    for (const el of elementos) {
                        const r = el.getBoundingClientRect();
                        if (r.width < 20 || r.height < 10) continue;
                        const dy = r.top - yEtiqueta;
                        const dx = Math.abs((r.left + r.width/2) - xEtiqueta);
                        if (dy > 0 && dy < 60 && dx < 150) {
                            const dist = dy + dx;
                            if (dist < mejorDist) { mejorDist = dist; mejor = el; }
                        }
                    }
                    return mejor;
                }
            """, [box_etiqueta["x"] + box_etiqueta["width"] / 2, box_etiqueta["y"] + box_etiqueta["height"]])
            elemento = handle.as_element()
            if elemento is None:
                continue
            texto_candidato = elemento.evaluate("e => e.innerText?.slice(0,60) || ''")
            print(f"  Click en cuadro colapsado de nomb_sucursal (texto: {texto_candidato!r})...", flush=True)
            elemento.click(timeout=10000)
            time.sleep(3)
            return True
        except Exception as e:
            print(f"  (error probando frame para abrir nomb_sucursal: {e})", flush=True)
    return False


def seleccionar_solo_territorio(pagina, territorio: str) -> bool:
    """NUEVO -- no existe en descargar.py. El panel de nomb_sucursal de esta vista
    trae 40 territorios + '(Todo)', con botones propios Cancelar/Aplicar
    (confirmado con capturas reales) -- a diferencia de Mes/Año, que aplican el
    cambio al vuelo. Arranca COLAPSADO (ver abrir_desplegable_sucursal): hay que
    abrirlo primero, y RECIÉN AHÍ desmarcar '(Todo)', marcar solo el territorio
    pedido, y click en 'Aplicar'.

    Devuelve True si encontró y aplicó el filtro, False si no encontró el panel
    (en cuyo caso el llamador debe abortar con una captura -- mejor eso que
    descargar TODOS los territorios mezclados sin que nadie se entere)."""
    if not abrir_desplegable_sucursal(pagina):
        print("  AVISO: no se pudo abrir el desplegable de nomb_sucursal por posición -- "
              "intentando de todas formas por si ya estaba abierto.", flush=True)

    # intentos=6 (60s), no los 18 (180s) por defecto: si ya se hizo click para
    # abrir el desplegable, el panel debería aparecer rápido -- esperar 3 minutos
    # enteros acá (como pasó en el run #1, que igual terminó fallando) solo
    # alarga un fallo real sin ganar nada.
    fr = encontrar_frame_con_checkboxes(pagina, minimo=30, intentos=6)  # el panel de territorios tiene >30 opciones
    if fr is None:
        return False

    print(f"  Desmarcando '(Todo)'...", flush=True)
    checks = fr.locator("input[type=checkbox]")
    desmarcado_todo = False
    for i in range(checks.count()):
        el = checks.nth(i)
        texto = texto_de_checkbox(el)
        if RE_TODO.match(texto):
            try:
                if el.is_checked():
                    el.click(timeout=10000)
                desmarcado_todo = True
            except Exception:
                pass
            break
    if not desmarcado_todo:
        print("  AVISO: no se encontró el checkbox '(Todo)' -- puede que ya no esté todo marcado.", flush=True)
    time.sleep(2)

    print(f"  Marcando solo '{territorio}'...", flush=True)
    if not click_checkbox_por_texto(fr, territorio):
        return False
    time.sleep(2)

    # Verificación real de estado (mismo criterio que estado_de_meses en descargar.py):
    # confirmar que SOLO el territorio pedido quedó marcado antes de aplicar.
    for intento in range(4):
        checks = fr.locator("input[type=checkbox]")
        marcados = []
        for i in range(checks.count()):
            el = checks.nth(i)
            try:
                if el.is_checked():
                    marcados.append(texto_de_checkbox(el))
            except Exception:
                pass
        marcados_reales = [m for m in marcados if not RE_TODO.match(m)]
        if marcados_reales == [territorio]:
            print(f"  Filtro de territorio verificado limpio: solo '{territorio}' marcado.", flush=True)
            break
        print(f"  verificación {intento+1}/4: marcados={marcados_reales}", flush=True)
        time.sleep(3 * (intento + 1))
    else:
        print(f"  AVISO: no se pudo confirmar que SOLO '{territorio}' quedó marcado -- "
              f"último estado: {marcados_reales}. Se continúa igual pero revisar el CSV resultante.",
              flush=True)

    # Click en "Aplicar" -- a diferencia de Mes/Año, este panel SÍ necesita
    # confirmación explícita (visto en las capturas: botones Cancelar/Aplicar
    # propios al pie del panel).
    aplicado = False
    for scope in (fr, pagina):
        try:
            boton = scope.get_by_text(RE_APLICAR, exact=False)
            if boton.count() > 0:
                boton.first.click(timeout=10000)
                aplicado = True
                break
        except Exception:
            pass
    if not aplicado:
        print("  AVISO: no se encontró botón 'Aplicar' -- puede que el filtro ya se haya "
              "aplicado solo, o que el selector no lo encontró (revisar captura).", flush=True)
    time.sleep(3)
    return True


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1600, "height": 1000},
                                          accept_downloads=True,
                                          locale="es-GT")
        pagina = contexto.new_page()
        iniciar_sesion(pagina)
        print(f"Navegando: {URL_VISTA}", flush=True)
        pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

        print("Buscando el panel de territorios (nomb_sucursal)...", flush=True)
        if not seleccionar_solo_territorio(pagina, TERRITORIO):
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_panel_territorio.png"))
            raise SystemExit(
                f"No se encontró/aplicó el panel de territorio para '{TERRITORIO}' -- "
                f"ver error_sin_panel_territorio.png. Abortado SIN descargar (mejor sin CSV "
                f"que con TODOS los territorios mezclados)."
            )

        print("Buscando el panel de Mes/Año...", flush=True)
        fr = encontrar_frame_con_checkboxes(pagina)
        if fr is None:
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_filtros.png"))
            raise SystemExit("No se encontraron checkboxes de Mes/Año -- ver error_sin_filtros.png")

        print(f"Marcando '{MES_OBJETIVO}'...", flush=True)
        if not click_checkbox_por_texto(fr, MES_OBJETIVO):
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
        time.sleep(2)

        for intento_verif in range(4):
            objetivo_ok, extras = estado_de_meses(fr, MES_OBJETIVO)
            if objetivo_ok and not extras:
                print(f"Filtro de mes verificado limpio: solo '{MES_OBJETIVO}' marcado.", flush=True)
                break
            print(f"  verificacion {intento_verif+1}/4: objetivo_marcado={objetivo_ok} "
                  f"extras_marcados={extras}", flush=True)
            if not objetivo_ok:
                click_checkbox_por_texto(fr, MES_OBJETIVO)
            for extra in extras:
                click_checkbox_por_texto(fr, extra)
            time.sleep(5 * (intento_verif + 1))
        else:
            objetivo_ok, extras = estado_de_meses(fr, MES_OBJETIVO)
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_filtro_mes_sucio.png"))
            raise SystemExit(
                f"Filtro de mes no quedo limpio tras 4 intentos -- objetivo_marcado={objetivo_ok} "
                f"extras_todavia_marcados={extras}. Se aborta sin descargar."
            )

        print(f"Marcando año '{ANIO_OBJETIVO}'...", flush=True)
        for intento_anio in range(4):
            if estado_de_anio(fr, ANIO_OBJETIVO):
                print(f"Filtro de año verificado: '{ANIO_OBJETIVO}' marcado.", flush=True)
                break
            click_checkbox_por_texto(fr, ANIO_OBJETIVO)
            time.sleep(5 * (intento_anio + 1))
        else:
            pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_filtro_anio.png"))
            raise SystemExit(f"No se pudo dejar marcado el año '{ANIO_OBJETIVO}' tras 4 intentos.")

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
            print(f"SIN DATOS -- '{TERRITORIO}' no tiene filas para "
                  f"{MES_OBJETIVO}. No es un error.", flush=True)
            marcador = os.path.join(SALIDA_DIR, f"SIN_DATOS_{TERRITORIO.replace(' ', '_')}.marker")
            open(marcador, "w").close()
            contexto.close()
            navegador.close()
            return 0

        print("Click final, esperando el archivo...", flush=True)
        with pagina.expect_download(timeout=150000) as info_descarga:
            boton_final.click()
        descarga = info_descarga.value
        nombre = f"{MES_OBJETIVO}_{TERRITORIO.replace(' ', '_')}.csv"
        ruta_salida = os.path.join(SALIDA_DIR, nombre)
        descarga.save_as(ruta_salida)
        print(f"OK -- Archivo descargado: {ruta_salida} ({os.path.getsize(ruta_salida):,} bytes)", flush=True)

        contexto.close()
        navegador.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
