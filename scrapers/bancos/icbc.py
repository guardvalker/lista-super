"""Scraper de promos bancarias de ICBC para supermercados (rubro id 4).

A diferencia de Provincia, acá no hace falta Playwright ni parsear texto
libre: detrás de la SPA de https://www.beneficios.icbc.com.ar/promo/super
hay una API JSON pública sin login real -- la auth son dos headers
estáticos hardcodeados en el propio frontend (`apikey`/`accesstoken`, son
claves de app públicas, no una sesión de usuario -- mismo espíritu que la
anon key de Supabase), capturados inspeccionando la request real que hace
la página. El JWT de `accesstoken` decodifica a un `exp` del año 2409, o
sea fijo en la práctica.

Endpoint: GET /api/web/v1/beneficios/get?heading_id=4 (heading_id 4 =
rubro "SUPER", confirmado contra /api/web/v1/beneficios/rubros). Devuelve
un array ya estructurado por promo -- cadena, días, %, tope de reintegro,
texto legal -- sin necesidad de regex. Todos los campos numéricos vienen
como strings en el JSON (ej. "ahorro_maximo": "20").
"""

import os
import sys
import traceback

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from dedupe import unicos_por_clave  # noqa: E402
from timestamps import scraped_at  # noqa: E402

FUENTE = "icbc"

API_URL = "https://prod-utilidades-icbc.pisol.net/api/web/v1/beneficios/get"
HEADING_ID_SUPER = "4"
PAGE_SIZE = 100
MAX_PAGINAS = 10  # tope de seguridad, no debería hacer falta tanto

HEADERS = {
    "apikey": "KlmhP3K1T5zowSqRIMMao6BSHrU48mCX",
    "accesstoken": (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
        "eyJhdXRoS2V5IjoiNTdiN2M0MmFiOGFlMmQ1MzA2ODk5NmQwODkwYWI5MGIiLCJleHAiOjI0MDkzOTc3NjN9."
        "FGjs7O-bjiFPUwdiE-GQGDBXkVq0nXhAtR35CwbyaxY"
    ),
    "Referer": "https://www.beneficios.icbc.com.ar/",
}

DIAS = {
    "LU": "lunes", "MA": "martes", "MI": "miercoles", "JU": "jueves",
    "VI": "viernes", "SA": "sabado", "DO": "domingo",
}


def _dias_semana(item):
    return sorted({DIAS[d] for d in item.get("days") or [] if d in DIAS})


def _tope_reintegro(item):
    """`saving` + `type_saving` vienen por segmento (ej. distinto tope
    para nómina vs. no-nómina) -- nos quedamos con el segmento GENERAL, o
    el primero si no hay uno marcado así."""
    segments = item.get("segments") or []
    if not segments:
        return None
    seg = next((s for s in segments if s.get("segment") == "GENERAL"), segments[0])
    if "SIN TOPE" in (seg.get("type_saving") or "").upper():
        return None
    try:
        return float(seg.get("saving") or 0) or None
    except (TypeError, ValueError):
        return None


def _medio_pago(item):
    partes = [c.lower() for c in (item.get("cards") or [])] + [
        s.lower() for s in (item.get("system") or [])
    ]
    return ",".join(dict.fromkeys(partes))


def _fecha(s):
    return s[:10] if s else None


def _parse_item(item):
    try:
        pct = int(float(item.get("ahorro_maximo") or 0))
    except (TypeError, ValueError):
        pct = 0
    if not pct:
        return None  # promos de cuotas sin %, fuera de alcance por ahora

    return {
        "fuente": FUENTE,
        "supermercado": (item.get("store") or "").strip().lower().replace(" ", "_") or "sin_dato",
        "descuento_pct": pct,
        "tope_reintegro": _tope_reintegro(item),
        "dias_semana": _dias_semana(item),
        "medio_pago": _medio_pago(item),
        "vigencia_desde": _fecha(item.get("date_start")),
        "vigencia_hasta": _fecha(item.get("date_end")),
        "condiciones_texto": (item.get("legal") or "").strip(),
        "raw_text": (item.get("legal") or "").strip(),
        "scraped_at": scraped_at(),
    }


def run():
    promos = []
    try:
        offset = 0
        for _ in range(MAX_PAGINAS):
            resp = requests.get(
                API_URL,
                params={"limit": PAGE_SIZE, "orden": 0, "offset": offset, "heading_id": HEADING_ID_SUPER},
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or []

            for item in data:
                if (item.get("rubro") or "").upper() != "SUPER":
                    continue
                promo = _parse_item(item)
                if promo:
                    promos.append(promo)

            if len(data) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    except Exception:
        print(f"[{FUENTE}] ERROR -- se omite esta fuente, no se tumba el resto del pipeline:")
        traceback.print_exc(file=sys.stdout)
        return []

    promos = unicos_por_clave(promos)

    if not promos:
        print(f"[{FUENTE}] ADVERTENCIA: no se encontró ninguna promo de super -- revisar si cambió la API.")

    return promos


if __name__ == "__main__":
    for p in run():
        print(p)
