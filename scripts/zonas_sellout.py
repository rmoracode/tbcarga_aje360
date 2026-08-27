"""scripts/zonas_sellout.py -- mapa nomb_sucursal -> cod_zona_cliente.

Generado el 2026-08-27 desde el historico real de econored (feb-julio 2026).

Existe por un comportamiento de la vista 'DATA PARA ANALISIS SELLOUT': su
filtro cod_zona_cliente es dependiente y viene guardado en 50000 (zona de
HUEHUETENANGO). Al cambiar nomb_sucursal por URL, esa zona deja de ser valida y
el filtro queda en '(Ninguno)' -- cero filas, y el panel de Mes ni siquiera se
dibuja, con lo que el scraper moria en 'error_sin_filtros'. Confirmado
comparando las capturas de CHIQUIMULA (ok, zona 40400 autorresuelta) y
CHIQUIMULILLA (fallo, zona en Ninguno) del run 33114619647.

Si econored agrega zonas, regenerar este archivo desde el historico."""
ZONAS_POR_SUCURSAL = {
    'CHIQUIMULA': ['40400', '40401'],
    'CHIQUIMULILLA': ['41800'],
    'COATEPEQUE': ['42900'],
    'COBAN': ['40000'],
    'CUBULCO': ['41500', '41501'],
    'EL ESTOR': ['45000', '45001'],
    'ESCUINTLA': ['43000', '43001'],
    'HUEHUETENANGO': ['50000'],
    'JALAPA': ['41100'],
    'JOYABAJ': ['43700'],
    'JUTIAPA': ['40300'],
    'KAREN SANDOVAL RIO HONDO': ['44800'],
    'LA GOMERA': ['42700'],
    'LA TINTA': ['43800'],
    'LAS CRUCES': ['44900'],
    'LOS AMATES': ['44200'],
    'MALACATAN': ['43400'],
    'MELCHOR DE MENCOS': ['44500', '44501'],
    'MORALES': ['41900'],
    'PAJAPITA': ['40800'],
    'PETEN': ['44600', '44601'],
    'PLAYA GRANDE': ['44400'],
    'POPTUN': ['44300'],
    'PROGRESO': ['41200'],
    'PUERTO BARRIOS': ['42300'],
    'PUERTO SAN JOSE': ['44000', '44001'],
    'QUICHE': ['45100'],
    'RAXRUHA': ['45500'],
    'RIO DULCE': ['43300'],
    'SALAMA': ['41600'],
    'SAN MARCOS': ['42500'],
    'SAN MARCOS  - CONCEPCION TUTUAPA': ['45800'],
    'SAN MARCOS  - SANTA IRENE': ['45400'],
    'SAN MARCOS  - SERCHIL': ['45300'],
    'SAN MARCOS  - TACANA': ['45700'],
    'SAN MARCOS - SAN RAFAEL PIE DE LA CUESTA': ['45900'],
    'SANTIAGO ATITLAN': ['42000'],
    'SOLOLA': ['40200', '40201'],
    'TECULUTAN': ['41000'],
    'TELEMAN': ['43100'],
    'TIQUISATE': ['45200', '45201'],
    'TOTONICAPAN': ['40700'],
    'USPANTAN': ['41700'],
}
