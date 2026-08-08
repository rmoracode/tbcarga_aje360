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


def click_con_fallback(locator, timeout=30000):
    """El overlay 'tab-glass clear-glass' de esta vista intercepta clicks incluso
    después de esperar a que 'desaparezca' (visto en corridas #2 y #3, siempre en
    el mismo punto) -- se intenta normal primero, y si Playwright lo bloquea por
    intercepción se fuerza (bypassa el chequeo de actionability)."""
    try:
        locator.click(timeout=timeout)
    except Exception as e:
        print(f"    click normal falló ({type(e).__name__}), forzando...", flush=True)
        locator.click(force=True)


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


def click_checkbox_conteniendo(scope, texto_buscado: str, estado_deseado: bool = None, reintentos=3) -> bool:
    """Igual que click_checkbox_por_texto de descargar.py, pero por SUBSTRING (acá
    la etiqueta es 'agosto de 2026', no solo 'agosto').

    estado_deseado: si se indica, NO clickea si el checkbox ya está en ese estado --
    corridas para bajar varios meses seguidos (backfill histórico) usan la misma
    cuenta de Tableau una tras otra, y no está confirmado si el servidor recuerda la
    última selección entre sesiones. Clickear a ciegas un checkbox que ya está en el
    estado que se quiere (ej. 'desmarcar mayo' cuando mayo ya estaba desmarcado)
    haría lo contrario -- lo marcaría, dejando dos meses seleccionados a la vez."""
    for intento in range(reintentos):
        try:
            checks = scope.locator("input[type=checkbox]")
            for i in range(checks.count()):
                if texto_buscado.lower() in texto_de_checkbox(checks.nth(i)).lower():
                    if estado_deseado is not None and checks.nth(i).is_checked() == estado_deseado:
                        return True  # ya está como se quiere, no tocar
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
        print("  no se encontraron checkboxes en el popup abierto.", flush=True)
        return False

    checks = popup_scope.locator("input[type=checkbox]")
    print(f"  {checks.count()} checkboxes en el popup:", flush=True)
    for i in range(checks.count()):
        try:
            print(f"    [{i}] {texto_de_checkbox(checks.nth(i))!r} checked={checks.nth(i).is_checked()}", flush=True)
        except Exception as e:
            print(f"    [{i}] (no se pudo leer: {e})", flush=True)

    click_checkbox_conteniendo(popup_scope, mes_objetivo, estado_deseado=True)
    time.sleep(1)
    # Corridas anteriores asumían éxito solo porque el click no reventó -- acá se
    # RELEE el estado real del checkbox después de clickear, en vez de confiar en
    # que click() sin excepción significa que de verdad quedó marcado.
    objetivo_marcado = False
    for i in range(checks.count()):
        try:
            if mes_objetivo.lower() in texto_de_checkbox(checks.nth(i)).lower():
                objetivo_marcado = checks.nth(i).is_checked()
        except Exception:
            pass
    print(f"  '{mes_objetivo}' quedó marcado: {objetivo_marcado}", flush=True)
    if not objetivo_marcado:
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_checkbox_no_marco.png"))
        return False

    if mes_a_desmarcar:
        click_checkbox_conteniendo(popup_scope, mes_a_desmarcar, estado_deseado=False)
        time.sleep(1)

    # Desmarcar cualquier OTRO mes que haya quedado marcado -- no solo mes_a_desmarcar.
    # Backfill histórico dispara varias corridas seguidas con la misma cuenta de
    # Tableau; si el servidor recuerda selecciones de una corrida a otra, un solo
    # mes_a_desmarcar fijo no alcanza para limpiar selecciones más viejas.
    for i in range(checks.count()):
        try:
            texto = texto_de_checkbox(checks.nth(i))
            if texto.lower() == "(todo)" or mes_objetivo.lower() in texto.lower():
                continue
            if checks.nth(i).is_checked():
                print(f"  desmarcando mes viejo encontrado: {texto!r}", flush=True)
                checks.nth(i).click(timeout=10000)
                time.sleep(1)
        except Exception:
            pass

    pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_mes_marcado.png"))

    aplicado = False
    for scope in (popup_scope, pagina, fr):
        try:
            boton = scope.get_by_text("Aplicar", exact=True)
            if boton.count() > 0:
                try:
                    print(f"  botón 'Aplicar' encontrado, disabled={boton.first.is_disabled()}", flush=True)
                except Exception:
                    pass
                click_con_fallback(boton.first)
                aplicado = True
                break
        except Exception as e:
            print(f"  error buscando 'Aplicar': {e}", flush=True)
    if not aplicado:
        print("  no se encontró el botón 'Aplicar'.", flush=True)
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_sin_aplicar.png"))
        return False

    # Corridas #5 y #6 (2026-08-08) probaron algo clave con el screenshot real: el
    # filtro SÍ se aplica de verdad (la tabla de fondo ya mostraba agosto completo,
    # con incentivos nuevos que no estaban en mayo) -- lo que nunca pasa es que el
    # PANEL del dropdown se cierre solo, ni esperando 120s. No hay que esperar a que
    # cierre; hay que cerrarlo (Escape), y seguir. El dato ya está bien desde el
    # click en 'Aplicar'.
    time.sleep(5)  # margen para que el click de Aplicar termine de procesar
    try:
        pagina.keyboard.press("Escape")
    except Exception:
        pass
    time.sleep(1)
    try:
        # Si Escape no lo cerró, clickear en un área neutra (el título de la vista)
        # como respaldo -- cualquiera de los dos saca el foco del popup.
        if popup_scope.locator("input[type=checkbox]:visible").count() > 0:
            pagina.mouse.click(50, 50)
            time.sleep(1)
    except Exception:
        pass
    pagina.screenshot(path=os.path.join(SALIDA_DIR, "dropdown_tras_aplicar.png"))
    return True


# Filtros que la vista trae preseleccionados a un valor puntual (no "(Todo)") por
# defecto -- confirmado con una descarga real: sin resetear estos, el CSV sale
# acotado a una sola ruta/zona en vez de traer TODO el país (plan: "la misma
# cascada sucursal/zona/ruta/cliente" -- necesita el dato completo, no un recorte).
FILTROS_A_RESETEAR = ["mundo", "Regiones", "Zona", "Ruta", "Canal"]


def resetear_filtro_a_todo(pagina, fr, etiqueta: str) -> bool:
    """Abre un filtro dropdown POR SU ETIQUETA (no por su valor actual, que puede
    ser cualquier zona/ruta/región -- a diferencia del filtro de mes no hay un
    patrón de texto conocido de antemano) y marca '(Todo)'."""
    try:
        label = fr.get_by_text(etiqueta, exact=True).first
        box = label.bounding_box()
        if box is None:
            print(f"  '{etiqueta}': no se encontró la etiqueta.", flush=True)
            return False
        pagina.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] + 15)
    except Exception as e:
        print(f"  '{etiqueta}': no se pudo abrir ({e}).", flush=True)
        return False

    time.sleep(2)
    popup_scope = None
    for scope in (fr, pagina):
        try:
            if scope.locator("input[type=checkbox]:visible").count() > 0:
                popup_scope = scope
                break
        except Exception:
            pass
    if popup_scope is None:
        print(f"  '{etiqueta}': no se encontraron checkboxes al abrir -- puede que ya esté en (Todo).", flush=True)
        try:
            pagina.keyboard.press("Escape")
        except Exception:
            pass
        return False

    marcado = click_checkbox_conteniendo(popup_scope, "(Todo)", estado_deseado=True)
    time.sleep(1)
    if not marcado:
        print(f"  '{etiqueta}': no tiene opción '(Todo)' -- se deja como está.", flush=True)
        try:
            pagina.keyboard.press("Escape")
        except Exception:
            pass
        return False

    aplicado = False
    for scope in (popup_scope, pagina, fr):
        try:
            boton = scope.get_by_text("Aplicar", exact=True)
            if boton.count() > 0:
                click_con_fallback(boton.first)
                aplicado = True
                break
        except Exception:
            pass
    time.sleep(4)
    try:
        pagina.keyboard.press("Escape")
    except Exception:
        pass
    time.sleep(1)
    # Mismo respaldo que seleccionar_mes_dropdown: si Escape no alcanzó, un click en
    # área neutra -- corrida #9 (2026-08-08) mostró que dejar un popup de estos sin
    # cerrar del todo termina bloqueando el click de 'Descargar' varios pasos después
    # (mismo overlay 'tab-glass' de siempre).
    try:
        if popup_scope.locator("input[type=checkbox]:visible").count() > 0:
            pagina.mouse.click(50, 50)
            time.sleep(1)
    except Exception:
        pass
    print(f"  '{etiqueta}' reseteado a (Todo): aplicado={aplicado}", flush=True)
    return aplicado


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

        print("Reseteando filtros de región/zona/ruta/canal a '(Todo)' (sin esto el CSV sale acotado a una sola ruta)...", flush=True)
        for etiqueta in FILTROS_A_RESETEAR:
            resetear_filtro_a_todo(pagina, fr, etiqueta)
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "filtros_reseteados.png"))

        print("Esperando a que la tabla recargue y el overlay de carga desaparezca...", flush=True)
        # Corridas #2 y #3 (2026-08-08) mostraron que 60s + una sola espera de 30s
        # NO alcanzan -- el reporte cruza cliente x incentivo x mes y es pesado. Se
        # sondea de verdad (hasta 3 min) en vez de una espera fija: 'ausente' = 0
        # elementos .tab-glass visibles en NINGÚN frame, dos lecturas seguidas.
        estable_seguidas = 0
        for i in range(36):  # 36 x 5s = 180s tope
            time.sleep(5)
            hay_glass = False
            for f in pagina.frames:
                try:
                    if f.locator(".tab-glass:visible").count() > 0:
                        hay_glass = True
                        break
                except Exception:
                    pass
            estable_seguidas = 0 if hay_glass else estable_seguidas + 1
            if estable_seguidas >= 2:
                print(f"  {(i + 1) * 5}s -- overlay ausente, se sigue.", flush=True)
                break
            print(f"  {(i + 1) * 5}s -- overlay de carga todavía visible...", flush=True)
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
        click_con_fallback(fr.get_by_text(RE_DESCARGAR).first)
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
        click_con_fallback(opcion)
        time.sleep(4)

        for scope in (fr, pagina):
            try:
                radio_csv = scope.get_by_text("CSV", exact=True)
                if radio_csv.count() > 0:
                    click_con_fallback(radio_csv.first)
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
            click_con_fallback(boton_final)
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
