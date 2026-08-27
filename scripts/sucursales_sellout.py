"""
scripts/sucursales_sellout.py — Lista única de territorios de la vista "DATA PARA
ANALISIS SELLOUT" (Reportera_Comercial, econored/distribuidores independientes,
pedido explícito 2026-08-14). Mismo patrón que scripts/sucursales.py: nada más la
conoce y da con qué validar que el combinado quedó completo.

Estos NO son las mismas 10 sucursales de AJEMAYA (scripts/sucursales.py) -- son
territorios/municipios distintos, la estructura propia de la red de econored. Lista
tomada directo del panel de filtros "nomb_sucursal" de esa vista (capturas del
2026-08-14), no adivinada ni scrapeada -- si econored agrega un territorio nuevo,
hay que actualizar esta lista a mano (mismo criterio que la lista de AJEMAYA)."""
SUCURSALES_SELLOUT = [
    "CHIQUIMULA",
    "CHIQUIMULILLA",
    "COATEPEQUE",
    "COBAN",
    "CUBULCO",
    "EL ESTOR",
    "ESCUINTLA",
    "HUEHUETENANGO",
    "JALAPA",
    "JOYABAJ",
    "JUTIAPA",
    "LA GOMERA",
    "LA TINTA",
    "LAS CRUCES",
    "MALACATAN",
    "MELCHOR DE MENCOS",
    "MORALES",
    "PAJAPITA",
    "PETEN",
    "PLAYA GRANDE",
    "POPTUN",
    "PUERTO BARRIOS",
    "PUERTO SAN JOSE",
    "QUICHE",
    "RAXRUHA",
    "RIO DULCE",
    "SALAMA",
    "SAN MARCOS",
    "SAN MARCOS  - CONCEPCION TUTUAPA",
    "SAN MARCOS - SAN RAFAEL PIE DE LA CUESTA",
    "SAN MARCOS  - SANTA IRENE",
    "SAN MARCOS  - SERCHIL",
    "SAN MARCOS  - TACANA",
    "SANTIAGO ATITLAN",
    "SOLOLA",
    "TECULUTAN",
    "TELEMAN",
    "TIQUISATE",
    "TOTONICAPAN",
    "USPANTAN",
]

if __name__ == "__main__":
    import sys
    if "--json" in sys.argv:
        import json
        print(json.dumps(SUCURSALES_SELLOUT))
    else:
        for s in SUCURSALES_SELLOUT:
            print(s)
