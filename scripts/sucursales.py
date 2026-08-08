"""
scripts/sucursales.py — Lista única de sucursales del pipeline de descarga. Antes vivía
solo hardcodeada en `matrix.sucursal` de .github/workflows/descargar.yml, así que nada
más la conocía y no había contra qué validar que el combinado quedó completo. Ahora el
workflow (matriz + job de reintento + validación en combinar_y_subir) lee de acá.
"""
SUCURSALES = [
    "AJEMAYA SUCURSAL BARBERENA",
    "AJEMAYA SUCURSAL MIXCO",
    "AJEMAYA SUCURSAL QUETZALTENANGO",
    "CEDI AMATITLAN",
    "CEDIS CHIMALTENANGO",
    "CEDIS MAZATENANGO",
    "CEDIS TECULUTAN",
    "PLANTA AMATITLAN - BEBIDAS",
    "RUTA EL ATLANTICO",
    "VILLA NUEVA",
]

if __name__ == "__main__":
    # Usado por el workflow para alimentar tanto la matriz (JSON) como pasos de shell
    # (una por línea) sin duplicar la lista en YAML.
    import sys
    if "--json" in sys.argv:
        import json
        print(json.dumps(SUCURSALES))
    else:
        for s in SUCURSALES:
            print(s)
