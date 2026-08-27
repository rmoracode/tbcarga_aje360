"""scripts/companias_sellout.py -- mapa nomb_sucursal -> nomb_compania.

Generado el 2026-08-27 desde la vista 'Data Estructura_Sellout' de Tableau.
Existe porque la vista 'DATA PARA ANALISIS SELLOUT' trae un filtro guardado de
nomb_compania (COMERCIOS SIMAJ HUEHUETENANGO) que devuelve VACIO para cualquier
otra sucursal: para bajar un territorio hay que pasar tambien, por parametro de
URL, las companias que operan en el.

Si econored suma un distribuidor nuevo, hay que regenerar este archivo (misma
consulta) -- igual criterio que scripts/sucursales_sellout.py."""
COMPANIAS_POR_SUCURSAL = {
    'CHIQUIMULA': [
        'DISTRIBUCIONES Y GLOBALIZACIONES DE ORIENTE S.A',
    ],
    'CHIQUIMULILLA': [
        'DESARROLLOS COMERCIALES DEL SUR, SOCIEDAD ANONIMA',
    ],
    'COATEPEQUE': [
        'DIAZ ESCOBAR , OBISPO',
    ],
    'COBAN': [
        'CORPORACION EKELES, S.A.',
    ],
    'CUBULCO': [
        'JULIO CAMAJA GARCIA,',
    ],
    'EL ESTOR': [
        'CORPORACION HG, SOCIEDAD ANONIMA - CORPORACIÓN HG',
    ],
    'ESCUINTLA': [
        'MAYOREO ELECTRONICO, S.A',
    ],
    'HUEHUETENANGO': [
        'COMERCIOS SIMAJ HUEHUETENANGO',
    ],
    'JALAPA': [
        'COMERCIALIZADORA DE BEBIDAS DE GUATEMALA S.A.',
    ],
    'JOYABAJ': [
        'DISTRIBUIDORA MAENI S.A',
    ],
    'JUTIAPA': [
        'PIROPEPA S.A',
    ],
    'LA GOMERA': [
        'COMERCIALIZADORA FA, SOCIEDAD ANONIMA',
    ],
    'LA TINTA': [
        'FIGUEROA GUILLERMO , BRYAN ADAN MANOLO',
    ],
    'LAS CRUCES': [
        'AGUSTIN VENTURA DE GONZALEZ , OTILIA FLORENTINA',
    ],
    'MALACATAN': [
        'CORPORACION PEES, S.A.',
    ],
    'MELCHOR DE MENCOS': [
        'MONTENEGRO RAMIREZ , ELMER JOEL',
    ],
    'MORALES': [
        'DISTRIBUIDORA JYM',
    ],
    'PAJAPITA': [
        'DIAZ VELASQUEZ , STHALLCY',
    ],
    'PETEN': [
        'MAYOREO ELECTRONICO S.A - PETEN',
    ],
    'PLAYA GRANDE': [
        'DISTRIBUIDORA MIGUELITO',
    ],
    'POPTUN': [
        'INTERIANO BUESO , CARLOS MAURICIO',
    ],
    'PUERTO BARRIOS': [
        'NARVAEZ GARCIA , OSCAR ALEJANDRO',
    ],
    'PUERTO SAN JOSE': [
        'MAYOREO ELECTRONICO, S.A',
    ],
    'QUICHE': [
        'COMERCIOS SIMAJ, S.A.',
    ],
    'RAXRUHA': [
        'DISTRIBUIDORA AURORITAS',
    ],
    'RIO DULCE': [
        'CORPORACION HG, SOCIEDAD ANONIMA - MARIA ESCOBAR',
    ],
    'SALAMA': [
        'DISTRIBUIDORA KAIROS',
    ],
    'SAN MARCOS': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SAN MARCOS  - CONCEPCION TUTUAPA': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SAN MARCOS  - SANTA IRENE': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SAN MARCOS  - SERCHIL': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SAN MARCOS  - TACANA': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SAN MARCOS - SAN RAFAEL PIE DE LA CUESTA': [
        'COMERCIALIZADORA SAN FELIPE, SOCIENDAD ANONIMA',
    ],
    'SANTIAGO ATITLAN': [
        'PABLO AJUCHAN , FRANCISCO',
    ],
    'SOLOLA': [
        'DISTRO SOCIEDAD ANONIMA',
    ],
    'TECULUTAN': [
        'DISTRIBUIDORA R & C , SOCIEDAD ANONIMA.',
    ],
    'TELEMAN': [
        'TREI SANCHU COMPANY, S.A',
    ],
    'TIQUISATE': [
        'MAYOREO ELECTRONICO, SOCIEDAD ANONIMA - TIQUISATE',
    ],
    'TOTONICAPAN': [
        'GRUPO EMPRESARIAL EL OLAM, SOCIEDAD ANONIMA',
    ],
    'USPANTAN': [
        'MALDONADO TOJIN , JUAN',
    ],
}
