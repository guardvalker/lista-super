"""Helper de timestamp para los scrapers de bancos.

El upsert de `promos_bancarias` ahora tiene un `on_conflict` explícito
(ver `bancos/run_all.py`) para no reinsertar la misma promo cada corrida.
Postgrest hace merge-duplicates: en un conflicto solo actualiza las
columnas presentes en el payload -- si un scraper no manda `scraped_at`
en el dict, la columna queda pegada para siempre en la fecha de la
primera vez que se vio esa promo, y se pierde la noción de "hace cuánto
se confirmó por última vez". Por eso cada scraper de bancos debe incluir
`scraped_at` explícito en cada promo.
"""

from datetime import datetime, timezone


def scraped_at():
    return datetime.now(timezone.utc).isoformat()
