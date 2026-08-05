"""
scripts/combinar.py — Une los CSV descargados (uno por sucursal, formato
crosstab UTF-16 de Tableau) en UN SOLO archivo CSV limpio (UTF-8), para subir
a Drive como un unico entregable en vez de 10 archivos sueltos.

Uso: python scripts/combinar.py <carpeta_con_los_csv> <archivo_salida.csv>
"""
import glob
import io
import os
import sys

import pandas as pd


def _decodificar(raw: bytes) -> str:
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le", errors="replace")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def main() -> int:
    carpeta = sys.argv[1] if len(sys.argv) > 1 else "todos"
    salida = sys.argv[2] if len(sys.argv) > 2 else "combinado.csv"

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
