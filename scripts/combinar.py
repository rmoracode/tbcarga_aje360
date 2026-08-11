"""
scripts/combinar.py — Une los CSV descargados (uno por sucursal, formato
crosstab UTF-16 de Tableau) en UN SOLO archivo CSV limpio (UTF-8), para subir
a Drive como un unico entregable en vez de 10 archivos sueltos.

Antes esto aceptaba silenciosamente lo que hubiera en la carpeta -- si 4 de 10
sucursales fallaban aguas arriba, igual armaba "el combinado" con las 6 que
llegaron y lo subia a Drive reemplazando el archivo completo del dia anterior,
sin ninguna senal de que quedo incompleto (2026-08-07, run #12: exactamente
esto paso). --esperadas hace la validacion explicita: cada sucursal de
scripts/sucursales.py tiene que tener un .csv O un .marker (SIN_DATOS_*,
ver scripts/descargar.py) en la carpeta; si falta alguna, sale con error y
sys.exit(1) ANTES de escribir el combinado -- el workflow no llega al paso
de rclone y Drive se queda con la version buena anterior.

--mes-objetivo "<mes> de <anio>" agrega una SEGUNDA red de seguridad, esta vez
de CORRECCION, no solo de completitud: 2026-08-09 se detecto que 3/10
sucursales (las de mayor volumen) entregaron su CSV con DOS meses mezclados
(el objetivo + uno viejo que debia haberse desmarcado) -- el filtro de
scripts/descargar.py fallo silenciosamente para esas 3, y como SI habia CSV
(no vacio, no marker), --esperadas no lo detectaba. Con --mes-objetivo, cada
CSV se filtra a SOLO las filas de ese mes antes de combinar -- si algun
archivo traia otros meses, se descartan esas filas y se imprime una alerta
con el detalle (cuantas filas, de que sucursal) para que quede visible en el
log aunque el combinado en si ya haya quedado correcto.

Uso: python scripts/combinar.py <carpeta_con_los_csv> <archivo_salida.csv> [--esperadas] [--mes-objetivo "agosto de 2026"]
"""
import glob
import io
import os
import sys

import pandas as pd

from sucursales import SUCURSALES


def _tiene_csv(carpeta: str, sucursal: str) -> bool:
    slug = sucursal.replace(" ", "_")
    return bool(glob.glob(os.path.join(carpeta, "**", f"*{slug}*.csv"), recursive=True))


def _sucursal_resuelta(carpeta: str, sucursal: str) -> bool:
    slug = sucursal.replace(" ", "_")
    tiene_marcador = bool(glob.glob(os.path.join(carpeta, "**", f"SIN_DATOS_{slug}.marker"), recursive=True))
    return _tiene_csv(carpeta, sucursal) or tiene_marcador


def validar_completo(carpeta: str) -> list[str]:
    """Devuelve la lista de sucursales SIN csv ni marker -- vacia si todo resolvió."""
    return [s for s in SUCURSALES if not _sucursal_resuelta(carpeta, s)]


def _decodificar(raw: bytes) -> str:
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le", errors="replace")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _arg_valor(nombre: str) -> str:
    """--mes-objetivo "agosto de 2026" -> "agosto de 2026" (soporta = y espacio)."""
    for i, a in enumerate(sys.argv):
        if a == nombre and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(nombre + "="):
            return a.split("=", 1)[1]
    return ""


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    carpeta = args[0] if len(args) > 0 else "todos"
    salida = args[1] if len(args) > 1 else "combinado.csv"
    validar = "--esperadas" in sys.argv
    mes_objetivo = _arg_valor("--mes-objetivo")

    if validar:
        faltantes = validar_completo(carpeta)
        if faltantes:
            print(f"FALTAN {len(faltantes)} sucursal(es) (ni CSV ni marker de sin-datos):")
            for s in faltantes:
                print(f"  - {s}")
            raise SystemExit(
                f"Combinado incompleto -- no se sube nada. Faltan: {', '.join(faltantes)}"
            )
        # Cero tolerancia a "todas resolvieron por marker": que las N sucursales
        # queden SIN_DATOS el mismo día es estadísticamente casi imposible en
        # operación normal y casi siempre significa que algo aguas arriba
        # (típicamente el filtro de año/mes en Tableau, ver scripts/descargar.py)
        # quedó mal aplicado para todas por igual -- no que de verdad no hubo
        # ventas en ninguna sucursal (visto 2026-08-11: año del filtro en blanco).
        sin_csv_real = [s for s in SUCURSALES if not _tiene_csv(carpeta, s)]
        if len(sin_csv_real) == len(SUCURSALES):
            raise SystemExit(
                f"Las {len(SUCURSALES)} sucursales resolvieron solo con marker 'SIN_DATOS' -- cero CSV "
                f"real en NINGUNA. Esto casi nunca es real, es señal de un filtro mal aplicado aguas "
                f"arriba (ver scripts/descargar.py). No se sube nada -- revisar antes de reintentar a ciegas."
            )
        print(f"Completo: las {len(SUCURSALES)} sucursales tienen CSV o marker de sin-datos.")

    rutas = sorted(glob.glob(os.path.join(carpeta, "**", "*.csv"), recursive=True))
    print(f"CSV encontrados: {len(rutas)}")
    if not rutas:
        raise SystemExit(f"No se encontraron CSV en {carpeta}")

    partes = []
    sucursales_sucias = []
    sucursales_vacias_tras_filtro = []
    for ruta in rutas:
        raw = open(ruta, "rb").read()
        texto = _decodificar(raw)
        sep = "\t" if "\t" in texto.splitlines()[0] else ","
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
        df.columns = [str(c).strip() for c in df.columns]
        antes = len(df)

        if mes_objetivo:
            col_mes = next((c for c in df.columns if "fecha_liquidacion" in c), None)
            if col_mes is not None:
                sucio = df[col_mes] != mes_objetivo
                if sucio.any():
                    otros_meses = sorted(df.loc[sucio, col_mes].unique())
                    print(f"  ⚠ {os.path.basename(ruta)}: {sucio.sum():,} filas de OTRO mes "
                          f"({otros_meses}) -- se descartan, se conservan solo las de '{mes_objetivo}'")
                    sucursales_sucias.append((os.path.basename(ruta), int(sucio.sum()), otros_meses))
                    df = df[~sucio]
                if df.empty:
                    print(f"  ⚠ {os.path.basename(ruta)}: quedó SIN filas de '{mes_objetivo}' tras filtrar")
                    sucursales_vacias_tras_filtro.append(os.path.basename(ruta))
                    continue

        print(f"  {os.path.basename(ruta)}: {len(df):,} filas" + (f" (de {antes:,} originales)" if len(df) != antes else ""))
        partes.append(df)

    if not partes:
        raise SystemExit("Todos los CSV quedaron vacíos tras filtrar por --mes-objetivo -- no se sube nada.")

    combinado = pd.concat(partes, ignore_index=True)
    combinado.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nOK -- {salida}: {len(combinado):,} filas totales, {os.path.getsize(salida):,} bytes")

    if sucursales_sucias:
        print(f"\n⚠ RESUMEN: {len(sucursales_sucias)} sucursal(es) traían meses mezclados "
              f"(auto-corregido, el combinado subido SÍ quedó correcto):")
        for nombre, n, meses in sucursales_sucias:
            print(f"    - {nombre}: {n:,} filas descartadas ({meses})")
        print("  Esto indica que scripts/descargar.py no logró aplicar el filtro de mes "
              "limpio para esas sucursales -- si se repite seguido, hay que revisar la "
              "verificación de estado ahí (estado_de_meses/reintentos).")
    if sucursales_vacias_tras_filtro:
        print(f"\n⚠ {len(sucursales_vacias_tras_filtro)} sucursal(es) quedaron sin ninguna fila "
              f"del mes objetivo tras filtrar: {sucursales_vacias_tras_filtro}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
