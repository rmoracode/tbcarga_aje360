"""
scripts/descargar.py — Version para GitHub Actions del automatizador de
'DATA PARA ANALISIS' (Tableau). Mismo flujo probado localmente en ajecam360/
version360/navegador/descargar_agosto.py, adaptado para correr headless en CI:

  - INICIA SESION EL MISMO con usuario/clave (GitHub Secrets). Antes usaba una
    sesion exportada (TABLEAU_STORAGE_STATE) pero esa vence en ~18h sin avisar,
    y el cron diario fallaba en cuanto expiraba. Loguearse de cero en cada
    corrida elimina ese problema de raiz: no hay nada que renovar a mano.
  - headless=True (sin pantalla en el runner).
  - Sucursal / mes objetivo / mes a desmarcar por variables de entorno, para
    poder correr el mismo script una vez por sucursal desde el workflow.

Variables de entorno esperadas:
    TABLEAU_USER             usuario de Tableau (secret)
    TABLEAU_PASSWORD         clave de Tableau (secret)
    SUCURSAL                default: "AJEMAYA SUCURSAL BARBERENA"
    MES_OBJETIVO             default: "agosto"
    MES_A_DESMARCAR          default: "" (si vacio, no desmarca nada)
    ANIO_OBJETIVO            default: año actual UTC
    SALIDA_DIR               default: "./salida"
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone

# Con la UI en ingles (visto en el runner de CI) 'Descargar' aparece como
# 'Download' -- se busca con este patron en vez de texto exacto en espanol.
RE_DESCARGAR = re.compile(r"Descargar|Download", re.IGNORECASE)

from playwright.sync_api import sync_playwright

SUCURSAL = os.environ.get("SUCURSAL", "AJEMAYA SUCURSAL BARBERENA")
MES_OBJETIVO = os.environ.get("MES_OBJETIVO", "agosto")
MES_A_DESMARCAR = os.environ.get("MES_A_DESMARCAR", "")
ANIO_OBJETIVO = os.environ.get("ANIO_OBJETIVO") or str(datetime.now(timezone.utc).year)
SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

SUCURSAL_Q = urllib.parse.quote(SUCURSAL)
URL_VISTA = (
    "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISIS"
    f"?:iid=1&nomb_sucursal={SUCURSAL_Q}"
)


URL_LOGIN = "https://bitableau.ajegroup.com/#/signin"


def iniciar_sesion(pagina):
    """Login con usuario/clave en el formulario nativo de Tableau.

    Es un formulario normal (sin SSO ni 2FA), asi que se puede automatizar sin
    depender de una sesion pre-generada que caduque.
    """
    usuario = os.environ.get("TABLEAU_USER", "").strip()
    clave = os.environ.get("TABLEAU_PASSWORD", "")
    if not usuario or not clave:
        raise SystemExit("Faltan TABLEAU_USER / TABLEAU_PASSWORD (secrets de GitHub).")

    print("Iniciando sesion en Tableau...", flush=True)
    pagina.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60000)
    pagina.wait_for_timeout(5000)

    # Los campos no siempre tienen ids estables entre versiones: se buscan por
    # tipo/atributos en varias variantes antes de rendirse.
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

    # Si el formulario sigue visible, las credenciales no fueron aceptadas.
    if pagina.locator("input[type='password']").count() > 0:
        pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_login_rechazado.png"))
        raise SystemExit("Login rechazado -- revisar usuario/clave (ver error_login_rechazado.png)")
    print("Sesion iniciada OK.", flush=True)


def encontrar_frame_con_checkboxes(pagina, minimo=10, intentos=18, espera_s=10):
    # El numero total de checkboxes varia por sucursal (la lista de dias con
    # datos de 'fecha_liquidacion' es mas larga o corta segun cuanta actividad
    # tenga esa sucursal) -- un umbral fijo (ej. >=10) puede cumplirse ANTES de
    # que el panel termine de renderizar del todo, y el checkbox que se clickea
    # despues queda obsoleto (el DOM se re-arma mientras tanto). En vez de un
    # minimo fijo, se espera a que el conteo se ESTABILICE: dos lecturas
    # seguidas iguales (y >0) antes de dar por lista la pagina.
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


# El idioma de la UI de Tableau sigue el Accept-Language/locale del NAVEGADOR,
# no solo la cookie de sesion guardada -- en un runner de Linux limpio (sin el
# mismo perfil/idioma del Chrome local) se vio renderizar todo en ingles
# ('August' en vez de 'agosto', '(All)' en vez de '(Todo)'), aunque la sesion
# siguiera siendo valida. Se fuerza locale=es-GT al crear el contexto (deberia
# resolverlo) Y ademas se acepta el equivalente en ingles como respaldo, para
# que el script no dependa de que esa configuracion siga funcionando igual.
MESES_EN = {
    "enero": "January", "febrero": "February", "marzo": "March", "abril": "April",
    "mayo": "May", "junio": "June", "julio": "July", "agosto": "August",
    "septiembre": "September", "octubre": "October", "noviembre": "November",
    "diciembre": "December",
}
MESES_LISTA = set(MESES_EN.keys()) | {v.lower() for v in MESES_EN.values()}


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
            # El elemento pudo quedar obsoleto si el DOM se re-armo justo en
            # medio del clic -- se relocaliza desde cero en vez de fallar.
            print(f"    (reintento {intento+1}/{reintentos} tras: {type(e).__name__})", flush=True)
            time.sleep(2)
    return False


def estado_de_meses(fr, mes_objetivo: str) -> tuple[bool, list[str]]:
    """(mes_objetivo quedó marcado?, lista de OTROS MESES que quedaron marcados).
    A diferencia de click_checkbox_por_texto (que solo confirma que ENCONTRÓ y
    CLICKEÓ un checkbox, no que el click surtió el efecto esperado), esto LEE
    el estado real (is_checked()) de cada checkbox después del click -- la única
    forma de detectar un click que no se aplicó a tiempo.

    Solo cuenta como "otro marcado" un checkbox cuyo texto es un nombre de mes
    (MESES_LISTA) -- 2026-08-11 se detectó que, sin este filtro, el checkbox de
    AÑO (ej. '2026', mismo frame/lista que el de Mes) se colaba acá como "extra"
    y el loop de limpieza en main() lo desmarcaba pensando que era un mes
    sobrante. Eso dejaba el filtro de Año vacío y la tabulación cruzada salía
    vacía para TODAS las sucursales por igual, sin ningún error visible (ver la
    verificación de año en main())."""
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
    """True si el checkbox de ANIO_OBJETIVO (ej. '2026') está marcado. No hace
    falta "desmarcar otros años" como con el mes -- el dato ya viene acotado
    por el filtro de mes, así que un año de más marcado no mezcla períodos;
    lo único que importa es que el año correcto SÍ esté marcado."""
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


def main() -> int:
    with sync_playwright() as p:
        if True:  # (bloque conservado para no re-indentar todo el cuerpo)
            navegador = p.chromium.launch(headless=True)
            contexto = navegador.new_context(viewport={"width": 1600, "height": 1000},
                                              accept_downloads=True,
                                              locale="es-GT")
            pagina = contexto.new_page()
            iniciar_sesion(pagina)
            print(f"Navegando: {URL_VISTA}", flush=True)
            # 'networkidle' es poco confiable para apps como Tableau (espera
            # que la red quede en TOTAL silencio, y cualquier ping de fondo
            # -telemetria, polling- puede impedir que eso pase nunca). Con 10
            # jobs pegandole al mismo servidor a la vez, uno la sufrio como
            # timeout de 60s. 'domcontentloaded' es mas robusto -- de todas
            # formas el script ya espera explicitamente (sleeps) a que el
            # contenido real aparezca despues de esto.
            pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

            print("Buscando el frame con los filtros...", flush=True)
            fr = encontrar_frame_con_checkboxes(pagina)
            if fr is None:
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_sin_filtros.png"))
                # Chequeo rapido: si aparece la pantalla de login, el secret esta vencido.
                if pagina.locator("text=/Nombre de usuario|Username/i").count() > 0:
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
            time.sleep(2)

            # Verificacion real de estado (no solo "se encontro y se clickeo"):
            # 2026-08-09 se detecto que 3/10 sucursales (las de mayor volumen,
            # con render mas lento) terminaban con MES_A_DESMARCAR todavia
            # marcado ademas del objetivo -- el click se registraba pero no
            # alcanzaba a aplicarse antes de leer el estado. Sin esto, la
            # tabulacion cruzada sale con DOS meses mezclados y nadie se entera
            # hasta que alguien audita los datos a mano. Se reintenta desmarcar
            # cualquier mes extra (no solo MES_A_DESMARCAR) hasta 4 veces con
            # espera creciente; si sigue sucio, se aborta con SystemExit --
            # eso deja esta sucursal SIN csv, que reintentar_faltantes
            # (descargar.yml) recoge y reintenta automaticamente en vez de
            # subir un archivo con datos incorrectos.
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
                    f"extras_todavia_marcados={extras}. Se aborta sin descargar (mejor sin csv que con "
                    f"datos de mas de un mes mezclados) -- reintentar_faltantes lo reintenta solo."
                )

            # Verificacion explicita del filtro de AÑO -- el script nunca lo
            # tocaba antes (solo manejaba Mes), confiando en que quedara
            # marcado de una sesion anterior. El bug de arriba (estado_de_meses
            # desmarcando el año por error) demostro que ese supuesto es
            # fragil: sin esto, un año en blanco deja la tabulacion cruzada
            # vacia para TODAS las sucursales sin ningun error visible.
            print(f"Marcando año '{ANIO_OBJETIVO}'...", flush=True)
            for intento_anio in range(4):
                if estado_de_anio(fr, ANIO_OBJETIVO):
                    print(f"Filtro de año verificado: '{ANIO_OBJETIVO}' marcado.", flush=True)
                    break
                click_checkbox_por_texto(fr, ANIO_OBJETIVO)
                time.sleep(5 * (intento_anio + 1))
            else:
                pagina.screenshot(path=os.path.join(SALIDA_DIR, "error_filtro_anio.png"))
                raise SystemExit(
                    f"No se pudo dejar marcado el año '{ANIO_OBJETIVO}' tras 4 intentos -- ver "
                    f"error_filtro_anio.png. Se aborta sin descargar (mejor sin csv que con la "
                    f"tabulacion cruzada vacia por filtro de año en blanco) -- reintentar_faltantes "
                    f"lo reintenta solo."
                )

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

            # El boton queda DESHABILITADO cuando la tabulacion cruzada sale
            # vacia -- pasa en sucursales sin ventas del canal TRADICIONAL (ej.
            # centros de distribucion/plantas, no puntos de venta). No es un
            # error: no hay nada que descargar para esa sucursal ese mes. Se
            # sale limpio (exit 0) en vez de reventar con un timeout confuso.
            #
            # Se deja un marcador en SALIDA_DIR (no solo el print): sin esto,
            # el workflow no podia distinguir "confirmado sin datos" de "el job
            # crasheo antes de llegar aca" -- ambos casos terminaban sin ningun
            # CSV, y combinar.py no tenia forma de saber cual de los dos paso.
            if boton_final.is_disabled():
                print(f"SIN DATOS -- '{SUCURSAL}' no tiene filas para "
                      f"{MES_OBJETIVO} en canal TRADICIONAL (botón deshabilitado, "
                      f"tabulación cruzada vacía). No es un error.", flush=True)
                marcador = os.path.join(SALIDA_DIR, f"SIN_DATOS_{SUCURSAL.replace(' ', '_')}.marker")
                open(marcador, "w").close()
                contexto.close()
                navegador.close()
                return 0

            # 150s (antes 90s): bajo carga de 10 sesiones simultaneas se vio a
            # Tableau tardar mas en disparar la descarga y el timeout de 90s se
            # cumplia justo antes de que llegara -- el reintento serial
            # (.github/workflows/descargar.yml, job reintentar_faltantes) es la
            # red de seguridad real, esto solo reduce cuantas veces hace falta.
            print("Click final, esperando el archivo...", flush=True)
            with pagina.expect_download(timeout=150000) as info_descarga:
                boton_final.click()
            descarga = info_descarga.value
            nombre = f"{MES_OBJETIVO}_{SUCURSAL.replace(' ', '_')}.csv"
            ruta_salida = os.path.join(SALIDA_DIR, nombre)
            descarga.save_as(ruta_salida)
            print(f"OK -- Archivo descargado: {ruta_salida} ({os.path.getsize(ruta_salida):,} bytes)", flush=True)

            contexto.close()
            navegador.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
