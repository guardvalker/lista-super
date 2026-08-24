# lista-super

PWA de lista de supermercado con precios de referencia actualizados. Ver el skill
`bona-ecosystem` para las convenciones compartidas con el resto de las apps
de Bona (patrón sin build, versionado, etc.) — este archivo es solo lo
específico de este repo.

## Backend

Supabase, proyecto compartido `bonapps` (ver `config.js`). Auth por OTP de
email (`sync.js`: `signInWithOtp` / `verifyOtp`) — nunca magic link, no es
viable en PWA instalada en iOS.

## Scrapers (`scrapers/`)

Python, corren vía GitHub Actions:

- `fetch-sucursales.yml` — manual, carga inicial de la tabla `sucursales`.
  No corre por cron, solo hace falta una vez (o al ampliar cobertura).
- `scrape-diario.yml` — cron el 1 y el 15 de cada mes, 9:00 UTC (6:00 ARG).
  Scrapea precios de referencia (Precios Claros) y escribe a Supabase con la
  service role key. El universo de términos que busca es
  `PRODUCTOS_INTERES` (fijo) más lo que haya en `ls_ingredientes_conocidos`
  (crece solo con el uso, ver `get_terminos_aprendidos` en
  `fetch_precios.py`). Las promos bancarias (Provincia/ICBC/Carrefour/
  Galicia) se sacaron por completo: mezclaban comercios chicos con las
  cadenas grandes y no había forma simple de filtrar por distancia real.

## Por qué el runner es self-hosted (`runs-on: self-hosted`)

**No es un problema de rate limit de la API de GitHub** — este repo no hace
ninguna llamada a `api.github.com` ni `raw.githubusercontent.com`, ni desde
el cliente ni desde los scrapers. Si algo alguna vez sugiere ese diagnóstico,
está equivocado; verificado directamente contra el código el 2026-08-23.

El problema real: los scrapers le pegan a la API de **Precios Claros**
(`https://d3e6htiiul5ek9.cloudfront.net/prod`, detrás de CloudFront/WAF), no
a GitHub. La primera versión, con un set de headers chico calcado del spec
original, daba **403 Forbidden específicamente al correr desde runners de
GitHub Actions hosteados** — pero no desde otros entornos. La sospecha
documentada en `scrapers/common/precios_claros_http.py`: el WAF usa la
ausencia de headers típicos de un browser real (`Sec-Fetch-*`,
`Accept-Encoding`, `Connection`) como señal de bot, más que un bloqueo puro
de rango de IP.

**Ya está resuelto**, no es una decisión pendiente: el runner corre en el
CachyOS de Bona (`~/actions-runner`, agente `cachyos-bona`, registrado
específicamente contra este repo), con headers de browser real calcados de
un scraper de referencia que sí funciona en producción contra la misma API.
El commit `2026-08-23 "Sacar actions/setup-python del runner self-hosted,
usar venv propio"` es limpieza posterior a esa migración, no un cambio de
arquitectura.

Si en algún momento se necesita tocar esto: el diagnóstico está en el
docstring de `precios_claros_http.py`, no hace falta re-investigar desde
cero.
