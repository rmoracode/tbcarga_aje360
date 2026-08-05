# tbcarga_aje360

Automatiza la descarga de la vista **DATA PARA ANALISIS** de Tableau
(`bitableau.ajegroup.com`), porque el filtro de mes de esa vista no se puede
mover por la API normal de Tableau (es un control tipo parámetro, no un
filtro real) — la única forma confiable es controlando el navegador como lo
haría una persona. Eso es lo que hace este repo, corriendo en GitHub Actions.

## Cómo funciona

1. **Localmente, una vez (y cada vez que la sesión venza):** corrés
   `scripts/login.py`, iniciás sesión vos en la ventana de Chrome que se
   abre, y el script guarda el estado de la sesión en `estado_sesion.json`
   (nunca se sube al repo — está en `.gitignore`).
2. Copiás el contenido completo de ese archivo como un **GitHub Secret**
   llamado `TABLEAU_STORAGE_STATE`.
3. El workflow (`.github/workflows/descargar.yml`) corre en la nube, usa esa
   sesión guardada, cambia el filtro de mes por clics reales, y descarga el
   crosstab en CSV.
4. El resultado queda como **artifact** de la corrida (por ahora — el
   siguiente paso es subirlo automáticamente a Google Drive).

## Configurar el secret (primera vez)

```
py -m pip install playwright
py -m playwright install chrome
py scripts/login.py
```

Cuando termine, abrí `estado_sesion.json`, copiá todo el contenido, y pegalo
en: **Settings → Secrets and variables → Actions → New repository secret**,
con el nombre exacto `TABLEAU_STORAGE_STATE`.

## Probar

En GitHub: pestaña **Actions** → workflow "Descargar DATA PARA ANALISIS
(Tableau)" → **Run workflow** (botón manual — el cron diario está
comentado en el YAML hasta confirmar que la primera corrida funciona).

## Cuando la sesión venza

Va a fallar con un mensaje claro ("La sesión venció..."). Ahí hay que
repetir el paso de `login.py` y actualizar el secret. No sabemos todavía
cuánto dura la sesión — hay que observarlo en la práctica.

## Pendiente

- Subida automática del CSV a Google Drive (rclone o API directa).
- Loop sobre las 13 sucursales (hoy corre una por ejecución, vía el input
  `sucursal` del workflow manual).
- Activar el cron diario una vez confirmado que la corrida manual funciona.
