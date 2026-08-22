"""Constantes HTTP compartidas para pegarle a la API de Precios Claros,
usadas por fetch_sucursales.py y fetch_precios.py.

Los headers están calcados de un scraper de referencia que sí funciona
contra esta misma API en producción (un Space de Hugging Face), después
de que la primera versión (con un set de headers más chico, calcado del
spec original) diera 403 Forbidden específicamente al correr desde un
runner de GitHub Actions -- pero no desde otros entornos. Sospecha: un
WAF/CloudFront usando la ausencia de headers que un browser real siempre
manda (Sec-Fetch-*, Accept-Encoding, Connection) como señal de bot, más
que un bloqueo puro de rango de IP.
"""

BASE_URL = "https://d3e6htiiul5ek9.cloudfront.net/prod"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Origin": "https://www.preciosclaros.gob.ar",
    "Connection": "keep-alive",
    "Referer": "https://www.preciosclaros.gob.ar/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "TE": "trailers",
}
