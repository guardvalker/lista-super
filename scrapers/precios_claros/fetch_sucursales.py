"""Carga inicial de sucursales de Precios Claros para Zona Norte / GBA.

Se corre manualmente (no es parte del cron diario) para armar la lista de
sucursales relevantes. Volver a correr solo si hace falta ampliar/actualizar
el radio cubierto.

Uso:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python fetch_sucursales.py

Sin esas variables de entorno corre en dry-run (ver common/supabase_client.py).

Nota sobre la API: probada en vivo, `limit` no controla el tamaño de
página -- el endpoint siempre devuelve de a 30 resultados por página
(campo `totalPagina` en la respuesta), ordenados por distancia ascendente
(`distanciaNumero`, en km) al punto lat/lng pedido. Hay que paginar con
`offset` y cortar cuando la distancia supera el radio que nos interesa,
en vez de confiar en `limit` o en una lista fija de nombres de localidad
(que además vienen con capitalización/acentos inconsistentes en la API,
ej. "ACASSUSO" vs "Acassuso").

También se guarda `distancia_km`: el endpoint de productos (ver
fetch_precios.py) solo acepta comparar contra 50 sucursales por request
(`maxCantSucursalesPermitido: 50` en su respuesta), así que fetch_precios.py
usa esta columna para quedarse con las 50 sucursales más cercanas al
armar cada query, en vez de mandar las ~900 que hay en el radio completo.
"""

import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from supabase_client import get_client  # noqa: E402

BASE_URL = "https://d3e6htiiul5ek9.cloudfront.net/prod"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Origin": "https://www.preciosclaros.gob.ar",
    "Referer": "https://www.preciosclaros.gob.ar/",
}

# La Lucila / Martínez, zona norte GBA -- la zona real del usuario.
LAT = -34.4839
LNG = -58.5008

# Radio de interés en km. La API ordena por distancia ascendente, así que
# apenas una página trae una sucursal más lejos que esto, se puede cortar.
RADIO_KM = 20
PAGE_SIZE = 30  # tamaño real de página que devuelve la API, no configurable


def to_row(s):
    return {
        "id": s.get("id"),
        "cadena": s.get("banderaDescripcion"),
        "direccion": s.get("direccion"),
        "localidad": s.get("localidad"),
        "lat": s.get("lat"),
        "lng": s.get("lng"),
        "distancia_km": s.get("distanciaNumero"),
    }


def fetch_sucursales_en_radio():
    rows = []
    offset = 0
    while True:
        params = {"lat": LAT, "lng": LNG, "limit": PAGE_SIZE, "offset": offset}
        resp = requests.get(f"{BASE_URL}/sucursales", params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pagina = data.get("sucursales", [])
        if not pagina:
            break

        corto = False
        for s in pagina:
            dist = s.get("distanciaNumero")
            if dist is not None and dist > RADIO_KM:
                corto = True
                break
            if not s.get("id"):
                continue
            rows.append(to_row(s))

        if corto or len(pagina) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.35)  # mismo rate-limit prudente que fetch_precios.py

    return rows


def main():
    print(f"Buscando sucursales a menos de {RADIO_KM}km de ({LAT}, {LNG})...")
    rows = fetch_sucursales_en_radio()
    print(f"Encontradas {len(rows)} sucursales dentro del radio")

    if not rows:
        print("ADVERTENCIA: 0 sucursales -- revisar LAT/LNG/RADIO_KM o si la API cambió de forma.")
        return

    client = get_client()
    client.table("sucursales").upsert(rows, on_conflict="id").execute()
    print("Listo.")


if __name__ == "__main__":
    main()
