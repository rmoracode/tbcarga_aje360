"""
scripts/combinar_sellout.py — Copia de scripts/combinar.py apuntada a
SUCURSALES_SELLOUT (40 territorios de econored) en vez de las 10 sucursales
de AJEMAYA. Misma lógica de validación de completitud y de mes limpio -- ver
combinar.py para el detalle de cada red de seguridad.

Uso: python scripts/combinar_sellout.py <carpeta_con_los_csv> <archivo_salida.csv> [--esperadas] [--mes-objetivo "agosto de 2026"]
"""
import glob
import io
import os
import sys

import pandas as pd

from sucursales_sellout import SUCURSALES_SELLOUT as SUCURSALES


def _tiene_csv(carpeta: str, sucursal: str) -> bool:
    slug = sucursal.replace(" ", "_")
    return bool(glob.glob(os.path.join(carpeta, "**", f"*{slug}*.csv"), recursive=True))


def _sucursal_resuelta(carpeta: str, sucursal: str) -> bool:
    slug = sucursal.replace(" ", "_")
    tiene_marcador = bool(glob.glob(os.path.join(carpeta, "**", f"SIN_DATOS_{slug}.marker"), recursive=True))
    return _tiene_csv(carpeta, sucursal) or tiene_marcador


def validar_completo(carpeta: str) -> list[str]:
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
            print(f"FALTAN {len(faltantes)} territorio(s) (ni CSV ni marker de sin-datos):")
            for s in faltantes:
                print(f"  - {s}")
            raise SystemExit(
                f"Combinado incompleto -- no se sube nada. Faltan: {', '.join(faltantes)}"
            )
        sin_csv_real = [s for s in SUCURSALES if not _tiene_csv(carpeta, s)]
        if len(sin_csv_real) == len(SUCURSALES):
            raise SystemExit(
                f"Los {len(SUCURSALES)} territorios resolvieron solo con marker 'SIN_DATOS' -- cero "
                f"CSV real en NINGUNO. Casi nunca es real -- revisar filtro aguas arriba antes de "
                f"reintentar a ciegas."
            )
        print(f"Completo: los {len(SUCURSALES)} territorios tienen CSV o marker de sin-datos.")

    rutas = sorted(glob.glob(os.path.join(carpeta, "**", "*.csv"), recursive=True))
    print(f"CSV encontrados: {len(rutas)}")
    if not rutas:
        raise SystemExit(f"No se encontraron CSV en {carpeta}")

    partes = []
    territorios_sucios = []
    territorios_vacios_tras_filtro = []
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
                    territorios_sucios.append((os.path.basename(ruta), int(sucio.sum()), otros_meses))
                    df = df[~sucio]
                if df.empty:
                    print(f"  ⚠ {os.path.basename(ruta)}: quedó SIN filas de '{mes_objetivo}' tras filtrar")
                    territorios_vacios_tras_filtro.append(os.path.basename(ruta))
                    continue

        print(f"  {os.path.basename(ruta)}: {len(df):,} filas" + (f" (de {antes:,} originales)" if len(df) != antes else ""))
        partes.append(df)

    if not partes:
        raise SystemExit("Todos los CSV quedaron vacíos tras filtrar por --mes-objetivo -- no se sube nada.")

    combinado = pd.concat(partes, ignore_index=True)
    combinado.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nOK -- {salida}: {len(combinado):,} filas totales, {os.path.getsize(salida):,} bytes")

    if territorios_sucios:
        print(f"\n⚠ RESUMEN: {len(territorios_sucios)} territorio(s) traían meses mezclados "
              f"(auto-corregido, el combinado subido SÍ quedó correcto):")
        for nombre, n, meses in territorios_sucios:
            print(f"    - {nombre}: {n:,} filas descartadas ({meses})")
    if territorios_vacios_tras_filtro:
        print(f"\n⚠ {len(territorios_vacios_tras_filtro)} territorio(s) quedaron sin ninguna fila "
              f"del mes objetivo tras filtrar: {territorios_vacios_tras_filtro}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
