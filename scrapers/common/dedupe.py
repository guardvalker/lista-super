"""Dedup de promos antes de subirlas, para no romper el upsert.

`run_all.py` hace `upsert(promos, on_conflict="fuente,supermercado,
descuento_pct,dias_semana,medio_pago")` para no reinsertar la misma promo
en cada corrida diaria. Pero si un mismo scraper devuelve dos filas con
esa misma clave en una sola llamada (ej. la página repite el texto de una
promo dos veces), Postgres tira "ON CONFLICT DO UPDATE command cannot
affect row a second time" -- el conflicto tiene que resolverse antes de
mandarlas, no lo resuelve Supabase por vos.
"""


def unicos_por_clave(promos):
    """Se queda con una fila por (supermercado, descuento_pct, dias_semana,
    medio_pago) -- la de `condiciones_texto` más largo, asumiendo que es
    la más completa."""
    mejores = {}
    for promo in promos:
        key = (
            promo["supermercado"],
            promo["descuento_pct"],
            tuple(promo["dias_semana"]),
            promo["medio_pago"],
        )
        actual = mejores.get(key)
        actual_len = len(actual.get("condiciones_texto") or "") if actual else -1
        if len(promo.get("condiciones_texto") or "") >= actual_len:
            mejores[key] = promo
    return list(mejores.values())
