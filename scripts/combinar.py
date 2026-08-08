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

Uso: python scripts/combinar.py <carpeta_con_los_csv> <archivo_salida.csv> [--esperadas]
"""
import glob
import io
import os
import sys

import pandas as pd

from sucursales import SUCURSALES


def _sucursal_resuelta(carpeta: str, sucursal: str) -> bool:
    slug = sucursal.replace(" ", "_")
    tiene_csv = bool(glob.glob(os.path.join(carpeta, "**", f"*{slug}*.csv"), recursive=True))
    tiene_marcador = bool(glob.glob(os.path.join(carpeta, "**", f"SIN_DATOS_{slug}.marker"), recursive=True))
    return tiene_csv or tiene_marcador


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


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    carpeta = args[0] if len(args) > 0 else "todos"
    salida = args[1] if len(args) > 1 else "combinado.csv"
    validar = "--esperadas" in sys.argv

    if validar:
        faltantes = validar_completo(carpeta)
        if faltantes:
            print(f"FALTAN {len(faltantes)} sucursal(es) (ni CSV ni marker de sin-datos):")
            for s in faltantes:
                print(f"  - {s}")
            raise SystemExit(
                f"Combinado incompleto -- no se sube nada. Faltan: {', '.join(faltantes)}"
            )
        print(f"Completo: las {len(SUCURSALES)} sucursales tienen CSV o marker de sin-datos.")

    rutas = sorted(glob.glob(os.path.join(carpeta, "**", "*.csv"), recursive=True))
    print(f"CSV encontrados: {len(rutas)}")
    if not rutas:
        raise SystemExit(f"No se encontraron CSV en {carpeta}")

    partes = []
    for ruta in rutas:
        raw = open(ruta, "rb").read()
        texto = _decodificar(raw)
        sep = "\t" if "\t" in texto.splitlines()[0] else ","
        df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
        df.columns = [str(c).strip() for c in df.columns]
        print(f"  {os.path.basename(ruta)}: {len(df):,} filas")
        partes.append(df)

    combinado = pd.concat(partes, ignore_index=True)
    combinado.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nOK -- {salida}: {len(combinado):,} filas totales, {os.path.getsize(salida):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
