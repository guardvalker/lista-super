"""Scraper de precios de referencia (Precios Claros). Corre cada 2 semanas
(1 y 15 de cada mes, ver .github/workflows/scrape-diario.yml).

Para cada producto de interés (scrapers/common/productos_interes.py) más
los términos que el uso real fue sumando a `ls_ingredientes_conocidos`
(ver get_terminos_aprendidos), consulta el endpoint de búsqueda de Precios
Claros contra las sucursales más cercanas ya guardadas en la tabla
`sucursales`, y guarda un precio_min/precio_max agregado del día.

Uso:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python fetch_precios.py

Sin esas variables de entorno corre en dry-run (ver common/supabase_client.py):
en ese caso, como tampoco hay sucursales reales guardadas en una base, vuelve
a pedirlas en vivo con fetch_sucursales.fetch_sucursales_en_radio() para
poder probar el scraping end-to-end sin credenciales.

Nota sobre la API (importante, no es lo que asume el spec original): probado
en vivo, el endpoint /productos NO devuelve precio por sucursal individual.
Su respuesta trae `maxCantSucursalesPermitido: 50` -- solo compara contra
como mucho 50 sucursales por request -- y da un `precioMin`/`precioMax`
agregados entre esas sucursales, más `cantSucursalesDisponible` (cuántas de
las consultadas tenían el producto). Por eso `precios` guarda un rango
agregado por producto/día, referido a "las 50 sucursales más cercanas",
no una fila por sucursal.
"""

import datetime
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from supabase_client import get_client, is_configured  # noqa: E402
from productos_interes import PRODUCTOS_INTERES  # noqa: E402
from precios_claros_http import BASE_URL, HEADERS  # noqa: E402

MAX_SUCURSALES_POR_QUERY = 50  # tope real de la API (maxCantSucursalesPermitido)
PRODUCTOS_POR_QUERY = 20  # cuántos resultados por término de búsqueda nos quedamos
RATE_LIMIT_SECONDS = 0.4  # entre 300-500ms recomendado por el spec


def get_terminos_aprendidos(client):
    """Ingredientes que el usuario tipeó a mano y no estaban en el
    diccionario fijo (ver `learnIngredient()` en index.html) -- crecen solos
    con el uso, vía `ls_ingredientes_conocidos`. `key` ya viene normalizado
    (mismo `normalize()` del cliente: sin tildes, en minúscula).
    """
    if not is_configured():
        return []  # dry-run: no hay base real de la que leer esto
    res = client.table("ls_ingredientes_conocidos").select("key").execute()
    return sorted({r["key"] for r in res.data if r.get("key")})


def get_sucursal_ids(client):
    if is_configured():
        res = client.table("sucursales").select("id, distancia_km").order("distancia_km").limit(
            MAX_SUCURSALES_POR_QUERY
        ).execute()
        return [r["id"] for r in res.data]

    # Dry-run: no hay una base real de la que leer sucursales ya guardadas,
    # así que las volvemos a pedir en vivo para poder probar el resto del
    # flujo sin credenciales.
    print("[dry-run] no hay sucursales en una base real -- pidiéndolas en vivo para probar...")
    import fetch_sucursales

    rows = fetch_sucursales.fetch_sucursales_en_radio()
    rows.sort(key=lambda r: (r.get("distancia_km") if r.get("distancia_km") is not None else 999999))
    return [r["id"] for r in rows[:MAX_SUCURSALES_POR_QUERY]]


def buscar_producto(termino, sucursal_ids):
    params = {
        "string": termino,
        "array_sucursales": ",".join(sucursal_ids),
        "offset": 0,
        "limit": PRODUCTOS_POR_QUERY,
        "sort": "-cant_sucursales_disponible",
    }
    resp = requests.get(f"{BASE_URL}/productos", params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("productos", [])


def main():
    client = get_client()
    sucursal_ids = get_sucursal_ids(client)
    print(f"Usando {len(sucursal_ids)} sucursales más cercanas para las queries")
    if not sucursal_ids:
        print("ADVERTENCIA: no hay sucursales cargadas -- correr fetch_sucursales.py primero.")
        return

    terminos_aprendidos = [t for t in get_terminos_aprendidos(client) if t not in PRODUCTOS_INTERES]
    if terminos_aprendidos:
        print(f"Sumando {len(terminos_aprendidos)} términos aprendidos desde ls_ingredientes_conocidos")
    terminos = PRODUCTOS_INTERES + terminos_aprendidos

    hoy = datetime.date.today().isoformat()
    productos_rows = []
    precios_rows = []
    precios_termino_rows = []
    vistos = set()

    for i, termino in enumerate(terminos):
        try:
            resultados = buscar_producto(termino, sucursal_ids)
        except requests.RequestException as e:
            print(f"  [error] '{termino}': {e}")
            continue

        # Precio de referencia del término (mediana de precio_min entre TODOS
        # los resultados de esta búsqueda, no solo los que quedan después del
        # dedup global por EAN de más abajo -- acá nos importa "qué precios
        # trae buscar este término hoy", sin importar si ese producto ya
        # apareció buscando otro término antes). Mediana en vez de promedio
        # para no dejar que un outlier de presentación (ej. un pack x6 entre
        # unidades sueltas) tironee mucho el número.
        precios_validos = sorted(p.get("precioMin") for p in resultados if p.get("precioMin") is not None)
        if precios_validos:
            n = len(precios_validos)
            mediana = (
                precios_validos[n // 2]
                if n % 2 == 1
                else (precios_validos[n // 2 - 1] + precios_validos[n // 2]) / 2
            )
            precios_termino_rows.append(
                {
                    "termino": termino,
                    "fecha": hoy,
                    "precio_promedio": mediana,
                    "cant_productos": n,
                }
            )

        for p in resultados:
            pid = p.get("id")
            if not pid or pid in vistos:
                continue
            vistos.add(pid)
            productos_rows.append(
                {
                    "id": pid,
                    "nombre": p.get("nombre"),
                    "marca": p.get("marca"),
                    "presentacion": p.get("presentacion"),
                }
            )
            precios_rows.append(
                {
                    "producto_id": pid,
                    "fecha": hoy,
                    "precio_min": p.get("precioMin"),
                    "precio_max": p.get("precioMax"),
                    "cant_sucursales": p.get("cantSucursalesDisponible"),
                }
            )

        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(terminos)} términos consultados")
        time.sleep(RATE_LIMIT_SECONDS)

    print(f"Encontrados {len(productos_rows)} productos distintos, {len(precios_rows)} precios de hoy")
    if not productos_rows:
        print("ADVERTENCIA: 0 productos -- revisar la API o la lista de términos.")
        return

    client.table("productos").upsert(productos_rows, on_conflict="id").execute()
    client.table("precios").upsert(precios_rows, on_conflict="producto_id,fecha").execute()
    if precios_termino_rows:
        client.table("precios_termino").upsert(precios_termino_rows, on_conflict="termino,fecha").execute()
    print(f"Listo. {len(precios_termino_rows)} términos con precio de referencia.")


if __name__ == "__main__":
    main()
