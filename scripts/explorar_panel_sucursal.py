"""
scripts/explorar_panel_sucursal.py — Exploración pura (sin descargar nada): loguea,
navega a DATAPARAANALISISSELLOUT, y en vez de asumir que el panel de nomb_sucursal
ya está abierto (lo que falló en el primer intento real, 2026-08-14 -- el panel de
40 territorios no aparece en el DOM hasta que algo lo abre), esto:

  1. Toma una captura de pantalla COMPLETA apenas la vista termina de cargar --
     así se ve el panel de filtros en su estado CERRADO por defecto.
  2. Lista, en TODOS los frames, cada elemento cuyo texto sea "(Todo)"/"(All)"
     (candidatos a ser el control cerrado de cada filtro: nomb_compania,
     nomb_sucursal, cod_zona_cliente, cod_ruta_cliente todos empiezan así) junto
     con su posición (bounding box) y el texto que tiene cerca arriba -- para
     poder identificar CUÁL "(Todo)" corresponde a nomb_sucursal sin adivinar.
  3. Si encuentra un texto "nomb_sucursal" en el DOM, también reporta su posición,
     para cruzar cuál "(Todo)" está más cerca.

No descarga ningún CSV -- el resultado es la captura + un texto en el log/artifact,
para escribir el selector correcto de una sin gastar otro intento a ciegas.
"""
import os
import time

from playwright.sync_api import sync_playwright

SALIDA_DIR = os.environ.get("SALIDA_DIR", "./salida")
os.makedirs(SALIDA_DIR, exist_ok=True)

URL_VISTA = "https://bitableau.ajegroup.com/#/site/Cam/views/Reportera_Comercial/DATAPARAANALISISSELLOUT?:iid=3"
URL_LOGIN = "https://bitableau.ajegroup.com/#/signin"


def iniciar_sesion(pagina):
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
        raise SystemExit("No se encontraron los campos de login.")
    campo_usuario.fill(usuario)
    campo_clave.fill(clave)
    campo_clave.press("Enter")
    pagina.wait_for_timeout(10000)
    if pagina.locator("input[type='password']").count() > 0:
        raise SystemExit("Login rechazado.")
    print("Sesion iniciada OK.", flush=True)


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1600, "height": 1000},
                                          accept_downloads=True, locale="es-GT")
        pagina = contexto.new_page()
        iniciar_sesion(pagina)
        print(f"Navegando: {URL_VISTA}", flush=True)
        pagina.goto(URL_VISTA, wait_until="domcontentloaded", timeout=60000)

        print("Esperando 45s a que renderice (sin buscar nada todavia)...", flush=True)
        pagina.wait_for_timeout(45000)

        pagina.screenshot(path=os.path.join(SALIDA_DIR, "panel_cerrado_full.png"), full_page=True)
        print("Captura de pantalla completa guardada: panel_cerrado_full.png", flush=True)

        print(f"\nTotal de frames en la pagina: {len(pagina.frames)}", flush=True)
        for idx, fr in enumerate(pagina.frames):
            try:
                n_check = fr.locator("input[type=checkbox]").count()
                print(f"  frame[{idx}] url={fr.url[:80]} -- checkboxes visibles: {n_check}", flush=True)
            except Exception as e:
                print(f"  frame[{idx}] error leyendo: {e}", flush=True)

        print("\n--- Elementos con texto '(Todo)' o '(All)' en cada frame ---", flush=True)
        for idx, fr in enumerate(pagina.frames):
            try:
                for patron in ["(Todo)", "(All)"]:
                    loc = fr.get_by_text(patron, exact=True)
                    n = loc.count()
                    if n == 0:
                        continue
                    print(f"\nframe[{idx}]: '{patron}' -> {n} coincidencia(s)", flush=True)
                    for i in range(min(n, 10)):
                        el = loc.nth(i)
                        try:
                            box = el.bounding_box()
                            # Texto de un elemento hermano/padre cercano arriba, que suele
                            # ser la ETIQUETA del filtro (ej. "nomb_sucursal") en las tarjetas
                            # de filtro de Tableau.
                            contexto_cercano = el.evaluate("""
                                e => {
                                    let p = e.closest('[role], div, td, th') || e.parentElement;
                                    for (let k=0; k<5 && p; k++) {
                                        const txt = (p.innerText || '').trim();
                                        if (txt && txt.length < 200) return txt.slice(0, 150);
                                        p = p.parentElement;
                                    }
                                    return '(sin contexto)';
                                }
                            """)
                            print(f"   [{i}] box={box} contexto_cercano={contexto_cercano!r}", flush=True)
                        except Exception as e:
                            print(f"   [{i}] error: {e}", flush=True)
            except Exception as e:
                print(f"  frame[{idx}]: error buscando '(Todo)': {e}", flush=True)

        print("\n--- Buscando texto 'nomb_sucursal' literal en cada frame ---", flush=True)
        posiciones_etiqueta = []
        for idx, fr in enumerate(pagina.frames):
            try:
                loc = fr.get_by_text("nomb_sucursal", exact=False)
                n = loc.count()
                if n:
                    print(f"frame[{idx}]: 'nomb_sucursal' -> {n} coincidencia(s)", flush=True)
                    for i in range(min(n, 5)):
                        try:
                            box = loc.nth(i).bounding_box()
                            print(f"   [{i}] box={box}", flush=True)
                            if box:
                                posiciones_etiqueta.append((idx, fr, box))
                        except Exception:
                            pass
            except Exception:
                pass

        # NUEVO: en vez de solo buscar texto exacto "(Todo)" cerca de la etiqueta
        # (lo que en el primer intento asumió mal la distancia -- resultó estar a
        # 116px, no <60px), esto lista TODOS los elementos con texto visible en
        # una franja generosa debajo de la etiqueta "nomb_sucursal", sea lo que
        # sea que digan -- para ver exactamente qué hay ahí sin adivinar más.
        print("\n--- TODOS los elementos con texto visible, 0-250px debajo de 'nomb_sucursal' ---", flush=True)
        for idx, fr, box_etiqueta in posiciones_etiqueta:
            try:
                candidatos = fr.evaluate("""
                    ([xEtiqueta, yEtiqueta]) => {
                        const elementos = document.querySelectorAll('div, span, td, button, [role="button"], [role="listbox"], [role="combobox"]');
                        const resultado = [];
                        for (const el of elementos) {
                            const r = el.getBoundingClientRect();
                            if (r.width < 15 || r.height < 8) continue;
                            const dy = r.top - yEtiqueta;
                            const dx = Math.abs((r.left + r.width/2) - xEtiqueta);
                            if (dy >= -5 && dy < 250 && dx < 250) {
                                const texto = (el.innerText || '').trim().slice(0, 60);
                                if (texto) resultado.push({dy: Math.round(dy), dx: Math.round(dx), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), texto});
                            }
                        }
                        resultado.sort((a,b) => a.dy - b.dy);
                        return resultado.slice(0, 25);
                    }
                """, [box_etiqueta["x"] + box_etiqueta["width"] / 2, box_etiqueta["y"] + box_etiqueta["height"]])
                print(f"\nframe[{idx}], debajo de la etiqueta en x={box_etiqueta['x']:.0f} y={box_etiqueta['y']:.0f}:", flush=True)
                for c in candidatos:
                    print(f"   dy={c['dy']:4d} dx={c['dx']:4d}  pos=({c['x']},{c['y']}) size=({c['w']}x{c['h']})  texto={c['texto']!r}", flush=True)
            except Exception as e:
                print(f"  error listando candidatos en frame[{idx}]: {e}", flush=True)

        contexto.close()
        navegador.close()
        print("\nExploracion terminada -- revisar el log completo + panel_cerrado_full.png", flush=True)
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
