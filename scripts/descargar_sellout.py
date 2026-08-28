"""
scripts/descargar_sellout.py — Version para GitHub Actions del automatizador de
"DATA PARA ANALISIS SELLOUT" (Tableau, econored/distribuidores independientes).
Copia deliberada de scripts/descargar.py -- MISMO login, MISMA mecánica de
verificación de checkboxes de Mes/Año, MISMA descarga de tabulación cruzada --
adaptada solo en 2 puntos reales:

  1. La vista es otra pestaña del MISMO workbook (Reportera_Comercial), así que
     la URL cambia de DATAPARAANALISIS a DATAPARAANALISISSELLOUT (confirmado
     por el usuario: mismo sitio, mismo libro, otra pestaña).
  2. Además de nomb_sucursal hay que pasar nomb_compania, cod_zona_cliente y
     cod_ruta_cliente. Los cuatro filtros de esta vista vienen guardados apuntando
     a HUEHUETENANGO y los tres últimos son DEPENDIENTES: si el conjunto da cero
     filas caen a "(Ninguno)" y ni siquiera se dibuja el panel de Mes. Los mapas
     territorio -> compañías / zonas / rutas viven en scripts/companias_sellout.py,
     zonas_sellout.py y rutas_sellout.py.
     ⚠️ Las comas dentro de un valor van ESCAPADAS (ver _param_filtro): la coma es
     el separador de valores múltiples de Tableau, así que sin escapar
     "CORPORACION EKELES, S.A." se parte en dos valores que no existen.

CORREGIDO 2026-08-27 (primera corrida real, run 33085005587: los 40 jobs
terminaron en error_sin_panel_territorio.png y cero CSV). La versión original
asumía que "nomb_sucursal" era un panel de checkboxes multi-select con botón
Aplicar y trataba de abrirlo a click. Es falso: el diagnóstico
(explorar_panel_sucursal.py, run 31844365516) mostró que la página tiene
exactamente 10 checkboxes -- Mes (6) y Año (4) -- y que sucursal, compañía y
zona son desplegables colapsados. Ahora el territorio se elige por PARÁMETRO DE
URL, igual que scripts/descargar.py ya hace para ventas, y se borraron las dos
funciones que clickeaban el desplegable.

Variables de entorno esperadas:
    TABLEAU_USER             usuario de Tableau (secret, mismo que descargar.py)
    TABLEAU_PASSWORD         clave de Tableau (secret, mismo que descargar.py)
    TERRITORIO                VACIO (default) = las 40 sucursales en UNA descarga.
                              Con un nombre (ver scripts/sucursales_sellout.py) baja
                              solo ese territorio -- se conserva para depurar.
    MES_OBJETIVO              default: "agosto"
    MES_A_DESMARCAR           default: "" (si vacio, no desmarca nada)
    ANIO_OBJETIVO             default: año actual UTC
    SALIDA_DIR                default: "./salida"

El filtrado por URL sí está verificado contra el servidor real (2026-08-27, vía
la API de Tableau con los mismos parámetros): CHIQUIMULA daba vacío con el
filtro por defecto y devuelve 128,874 filas al pasar su compañía; PETEN, SOLOLA
y MORALES también devuelven datos. Lo que no se pudo probar fuera de GitHub
Actions es la parte de navegador (login + checkboxes de Mes/Año + descarga),
porque las credenciales son secrets del repo -- ahí siguen valiendo las capturas
de SALIDA_DIR como diagnóstico, mismo criterio que descargar.py.
"""
import io
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from companias_sellout import COMPANIAS_POR_SUCURSAL  # noqa: E402
from zonas_sellout import ZONAS_POR_SUCURSAL  # noqa: E402
from rutas_sellout import RUTAS_POR_SUCURSAL  # noqa: E402
from sucursales_sellout import SUCURSALES_SELLOUT  # noqa: E402

TERRITORIO = os.environ.get("TERRITORIO", "")
MES_OBJETIVO = os.environ.get("MES_OBJETIVO", "agosto")
MES_A_DESMARCAR = os.environ.get("MES_A_DESMARCAR", "")
ANIO_OBJETIVO = os.environ.get("ANIO_OBJETIVO") or str(datetime.now(timezone.utc).year)
SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

# El territorio y su(s) compania(s) se eligen por PARAMETRO DE URL, igual que hace
# scripts/descargar.py con nomb_sucursal para ventas -- no clickeando el desplegable.
# Cambio 2026-08-27, tras el fallo de la primera corrida real: la version anterior
# intentaba abrir el desplegable de nomb_sucursal y buscar 30+ checkboxes, pero el
# diagnostico (explorar_panel_sucursal.py, run 31844365516) mostro que en la pagina
# solo hay 10 checkboxes -- Mes (6) y Anio (4). Sucursal/compania/zona son
# desplegables colapsados, no paneles de checkboxes, asi que ese camino nunca podia
# funcionar y las 40 corridas terminaban en error_sin_panel_territorio.png.
#
# nomb_compania hace falta ADEMAS de nomb_sucursal porque la vista trae un filtro
# guardado de compania (COMERCIOS SIMAJ HUEHUETENANGO): sin sobreescribirlo,
# cualquier territorio que no sea HUEHUETENANGO devuelve vacio -- verificado contra
# el servidor real el 2026-08-27 (CHIQUIMULA vacio con el filtro por defecto,
# 128,874 filas al pasar su compania).
# Red de seguridad: si el territorio no esta en el mapa (nombre nuevo, o un
# distribuidor que cambio de territorio), se pasan TODAS las companias. Dejar el
# parametro vacio seria peor: sin el, manda el filtro guardado de la vista y el
# territorio devuelve vacio en silencio.
_TODAS_LAS_COMPANIAS = sorted({c for v in COMPANIAS_POR_SUCURSAL.values() for c in v})


def _param_filtro(valores) -> str:
    """Une varios valores para un filtro de Tableau en la URL, ESCAPANDO las comas
    que vengan dentro de un valor.

    Sin esto, 'DESARROLLOS COMERCIALES DEL SUR, SOCIEDAD ANONIMA' se parte en dos
    valores inexistentes (la coma es el separador de valores multiples de
    Tableau), el filtro queda vacio, y con cero filas los filtros dependientes
    (zona, ruta) caen a "(Ninguno)" y el panel de Mes ni se dibuja -- el
    "mejor frame: 4 checkboxes" con el que morian 9 de los 14 territorios de los
    runs 33114619647 y 33116367726. Son exactamente los territorios cuya compania
    lleva coma en el nombre: CHIQUIMULILLA, COBAN, ESCUINTLA, COATEPEQUE, CUBULCO,
    EL ESTOR... mientras que CHIQUIMULA ('DISTRIBUCIONES Y GLOBALIZACIONES DE
    ORIENTE S.A', sin coma) siempre habia funcionado.

    Verificado contra el servidor real el 2026-08-27: CHIQUIMULILLA da VACIO sin
    escapar y 17,502 filas con la coma escapada."""
    return ",".join(str(v).replace(",", "\\,") for v in valores)


# MODO TODOS (TERRITORIO vacio): baja las 40 sucursales de una sola vez, en vez de
# una corrida por territorio. Es lo que el dueno del dato hace a mano -- sus CSV
# historicos traen las 40 sucursales y ~380k filas en un solo archivo, o sea que la
# descarga de tabulacion cruzada aguanta el pais entero.
#
# Motivo del cambio (2026-08-27): la matriz de 40 jobs tardaba 38 min y quemaba unos
# 200 minutos de GitHub Actions POR DIA solo para econored -- el plan del repo
# privado se agota en ~10 dias, y ya hubo un incidente por quedarse sin minutos.
# Ademas el bot esperaba como maximo 40 min, o sea 2 min de margen sobre los 38
# reales: cualquier demora en la cola lo hacia fallar.
MODO_TODOS = not TERRITORIO.strip()
# Etiqueta para logs, nombre del CSV y marcadores SIN_DATOS.
ETIQUETA = "TODOS" if MODO_TODOS else TERRITORIO

if MODO_TODOS:
    _SUCURSALES = SUCURSALES_SELLOUT
    _COMPANIAS = _TODAS_LAS_COMPANIAS
    _ZONAS = sorted({z for v in ZONAS_POR_SUCURSAL.values() for z in v})
    # Las rutas NO se mandan en este modo: serian ~1600 valores (>9000 chars) y la
    # URL no lo aguanta. Con todas las zonas seleccionadas el filtro de ruta deberia
    # autorresolverse a "(Todo)", que es como quedo en los territorios que si
    # funcionaron. Si no lo hace, se ve en error_sin_filtros.png y se vuelve al modo
    # por territorio (basta con restaurar la matriz en el workflow).
    _RUTAS = []
    print(f"MODO TODOS: {len(_SUCURSALES)} sucursales, {len(_COMPANIAS)} companias, "
          f"{len(_ZONAS)} zonas, en una sola descarga.", flush=True)
else:
    _SUCURSALES = [TERRITORIO]
    _COMPANIAS = COMPANIAS_POR_SUCURSAL.get(TERRITORIO) or _TODAS_LAS_COMPANIAS
    _ZONAS = ZONAS_POR_SUCURSAL.get(TERRITORIO, [])
    _RUTAS = RUTAS_POR_SUCURSAL.get(TERRITORIO, [])
    if TERRITORIO not in COMPANIAS_POR_SUCURSAL:
        print(f"AVISO: '{TERRITORIO}' no esta en companias_sellout.py -- se pasan las "
              f"{len(_TODAS_LAS_COMPANIAS)} companias conocidas. Conviene regenerar ese mapa.",
              flush=True)

# cod_zona_cliente TAMBIEN va en la URL. Es un filtro dependiente que viene
# guardado en 50000 (zona de HUEHUETENANGO): al cambiar de sucursal por URL esa
# zona deja de ser valida y el filtro cae a "(Ninguno)" -- cero filas, y como la
# tabla queda vacia el panel de Mes ni se dibuja, que es como morian 9 de los 14
# territorios del run 33114619647 ("mejor frame: 4 checkboxes", solo el de Anio).
# Confirmado comparando las capturas: CHIQUIMULA ok con zona 40400 autorresuelta,
# CHIQUIMULILLA fallido con zona en (Ninguno).
#
# Se mandan TODAS las zonas del territorio, no una: 9 territorios tienen dos
# (CHIQUIMULA 40400 y 40401, PETEN 44600/44601, ...) y en la corrida que si
# funciono la vista habia autoseleccionado solo una, o sea que ese CSV venia
# incompleto sin que nada lo avisara.
URL_VISTA = (
    "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISISSELLOUT"
    "?:iid=3&nomb_sucursal=" + urllib.parse.quote(_param_filtro(_SUCURSALES))
    + "&nomb_compania=" + urllib.parse.quote(_param_filtro(_COMPANIAS))
)
if _ZONAS:
    URL_VISTA += "&cod_zona_cliente=" + urllib.parse.quote(_param_filtro(_ZONAS))
else:
    print(f"AVISO: sin zonas para '{TERRITORIO}' en zonas_sellout.py -- se deja el "
          f"filtro como venga. Conviene regenerar ese mapa.", flush=True)

# cod_ruta_cliente es el TERCER filtro dependiente (ver rutas_sellout.py): con la
# zona ya corregida, CHIQUIMULILLA seguia muriendo porque la ruta quedaba en
# "(Ninguno)" -- captura del run 33116367726. En el territorio que si funcionaba
# la vista la habia autorresuelto a "(Todo)".
if _RUTAS:
    URL_VISTA += "&cod_ruta_cliente=" + urllib.parse.quote(_param_filtro(_RUTAS))
else:
    print("Sin filtro de ruta en la URL (modo todos, o territorio sin rutas "
          "mapeadas): se deja como lo resuelva la vista.", flush=True)

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


def aplicar_filtros(fr) -> int:
    """Click en los botones 'Aplicar' de los paneles de Mes/Año.

    Corregido 2026-08-27 (run 33113079979): CHIQUIMULA bajó un CSV real y con el
    territorio correcto, pero con 'mayo de 2026' -- el mes que la vista trae
    guardado -- aunque el script había marcado agosto y verificado los checkboxes.
    La causa: en ESTA vista los filtros de Mes y Año son de aplicación DIFERIDA
    (tienen sus propios botones Cancelar/Aplicar, visibles en las capturas del
    panel), así que marcar el checkbox no toca la tabla hasta apretar Aplicar. El
    docstring original afirmaba lo contrario ("esas SÍ aplican el cambio al
    vuelo") -- cierto en la vista de ventas, falso en la de sellout.

    Se reconsulta el locator en cada vuelta porque al aplicar un panel el otro
    puede re-renderizarse y dejar el handle viejo obsoleto."""
    clicks = 0
    for _ in range(4):
        try:
            botones = fr.get_by_text(RE_APLICAR, exact=False)
            total = botones.count()
        except Exception:
            break
        clickeado_esta_vuelta = False
        for i in range(total):
            try:
                boton = botones.nth(i)
                if not boton.is_visible() or boton.is_disabled():
                    continue
                boton.click(timeout=5000)
                clicks += 1
                clickeado_esta_vuelta = True
                print(f"  click en 'Aplicar' ({clicks})", flush=True)
                time.sleep(4)
                break  # el DOM cambia: se vuelve a consultar desde cero
            except Exception as e:
                print(f"  (no se pudo clickear un 'Aplicar': {str(e)[:80]})", flush=True)
        if not clickeado_esta_vuelta:
            break
    if clicks == 0:
        print("  AVISO: ningún botón 'Aplicar' habilitado -- puede que el filtro ya "
              "estuviera aplicado, o que el selector no lo encontró.", flush=True)
    return clicks


def verificar_mes_del_csv(ruta: str, mes_objetivo: str, anio_objetivo: str) -> None:
    """Falla fuerte si el CSV no trae EXACTAMENTE el mes pedido.

    Sin esto, el bug del run 33113079979 pasaba en silencio: el archivo se subía
    como artifact con nombre 'agosto_CHIQUIMULA.csv' pero contenía mayo, y el
    pipeline de grandes_perdidas_bot lo habría metido al parquet como si fuera
    agosto. Mismo criterio de cero tolerancia a mezcla de meses que ya aplica
    servicios/sincronizador_datos.py del otro lado."""
    import csv as _csv

    esperado = f"{mes_objetivo} de {anio_objetivo}"
    col_mes = "Mes, Año de fecha_liquidacion"
    with io.open(ruta, encoding="utf-16", newline="") as f:
        lector = _csv.DictReader(f, delimiter="\t")
        if lector.fieldnames is None or col_mes not in lector.fieldnames:
            raise SystemExit(
                f"El CSV no trae la columna {col_mes!r}. Columnas: {lector.fieldnames}"
            )
        meses = set()
        filas = 0
        for fila in lector:
            filas += 1
            valor = (fila.get(col_mes) or "").strip()
            if valor:
                meses.add(valor)
    print(f"  verificación: {filas:,} filas, meses en el archivo: {sorted(meses)}", flush=True)
    if meses != {esperado}:
        raise SystemExit(
            f"MES INCORRECTO: se pidió {esperado!r} pero el CSV trae {sorted(meses)}. "
            f"Se aborta sin publicar el archivo -- mejor sin datos que con el mes "
            f"equivocado metido al parquet como si fuera el correcto."
        )


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

        # El territorio ya viene aplicado en la URL (ver URL_VISTA arriba) -- no hay
        # panel que abrir ni checkbox que clickear para esto.
        print(f"Alcance '{ETIQUETA}' aplicado por URL "
              f"(companias: {_COMPANIAS or 'todas'})", flush=True)

        print("Buscando el panel de Mes/Año...", flush=True)
        # minimo=5, no el 10 por defecto: ese 10 asume Anio (4) + los 6 meses de la
        # ventana, pero el panel de Mes solo lista los meses CON DATOS de ese
        # territorio. TECULUTAN, el unico fallo de los 40 del run 33119137340, se
        # quedaba estable en 7 (Anio 4 + 3 meses) y el script lo daba por "sin
        # filtros" cuando en realidad la pagina habia cargado bien. Con 5 alcanza
        # para exigir el panel de Anio mas al menos un mes; si el mes objetivo no
        # esta entre ellos, click_checkbox_por_texto() falla igual mas abajo e
        # imprime los textos reales, que es el error util.
        fr = encontrar_frame_con_checkboxes(pagina, minimo=5)
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

            # El panel de Mes lista SOLO los meses con datos de este territorio. Si
            # cargo bien (hay meses listados) pero el objetivo no esta entre ellos,
            # es que el territorio no vendio ese mes -- no es un fallo. TECULUTAN,
            # el unico caso de los 40 (run 33123846906), solo ofrece abril y mayo y
            # tiene 0 filas de julio/agosto tambien en el historico: es un
            # territorio sin movimiento, y hacerlo fallar a diario ensuciaria el
            # pipeline sin motivo. Mismo marcador SIN_DATOS que ya usa mas abajo el
            # caso de "boton de descarga deshabilitado".
            meses_ofrecidos = [t for t in textos if t.strip().lower() in MESES_LISTA]
            if meses_ofrecidos:
                print(f"SIN DATOS -- '{ETIQUETA}' no tiene {MES_OBJETIVO}; el panel solo "
                      f"ofrece {meses_ofrecidos}. No es un error.", flush=True)
                marcador = os.path.join(
                    SALIDA_DIR, f"SIN_DATOS_{ETIQUETA.replace(' ', '_')}.marker")
                open(marcador, "w").close()
                contexto.close()
                navegador.close()
                return 0

            raise SystemExit(
                f"No se encontro el checkbox de mes '{MES_OBJETIVO}' y el panel tampoco "
                f"lista ningun mes -- la pagina no cargo bien. Ver textos arriba."
            )
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

        # Mes y Año son de aplicación diferida en esta vista: sin este click la
        # tabla sigue mostrando el mes guardado (ver aplicar_filtros).
        print("Aplicando los filtros de Mes/Año...", flush=True)
        aplicar_filtros(fr)

        # En modo todos la tabla es el pais entero (~380k filas), no un territorio
        # (~20k): tarda bastante mas en repintarse despues de aplicar el filtro.
        espera_recarga = 150 if MODO_TODOS else 60
        print(f"Esperando {espera_recarga}s fijos a que la tabla recargue...", flush=True)
        time.sleep(espera_recarga)
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
            print(f"SIN DATOS -- '{ETIQUETA}' no tiene filas para "
                  f"{MES_OBJETIVO}. No es un error.", flush=True)
            marcador = os.path.join(SALIDA_DIR, f"SIN_DATOS_{ETIQUETA.replace(' ', '_')}.marker")
            open(marcador, "w").close()
            contexto.close()
            navegador.close()
            return 0

        print("Click final, esperando el archivo...", flush=True)
        # Timeout del archivo: 15 min en modo todos, 2.5 min por territorio. El
        # run 33140887999 llego hasta aca correctamente (filtros aplicados, agosto
        # marcado, Aplicar apretado) y murio en "Timeout 150000ms exceeded while
        # waiting for event download": generar la tabulacion cruzada del pais entero
        # tarda mucho mas que la de un solo territorio.
        timeout_descarga = 900000 if MODO_TODOS else 150000
        with pagina.expect_download(timeout=timeout_descarga) as info_descarga:
            boton_final.click()
        descarga = info_descarga.value
        nombre = f"{MES_OBJETIVO}_{ETIQUETA.replace(' ', '_')}.csv"
        ruta_salida = os.path.join(SALIDA_DIR, nombre)
        descarga.save_as(ruta_salida)
        print(f"OK -- Archivo descargado: {ruta_salida} ({os.path.getsize(ruta_salida):,} bytes)", flush=True)

        # Se valida DESPUÉS de guardar: si el mes no es el pedido, el archivo queda
        # en SALIDA_DIR para poder inspeccionarlo, pero el job falla y el artifact
        # no se toma como bueno.
        verificar_mes_del_csv(ruta_salida, MES_OBJETIVO, ANIO_OBJETIVO)

        contexto.close()
        navegador.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
