"""Scraper de promos de Banco Galicia para supermercados (categoría id 8).

Igual que ICBC, es una API JSON pública sin login detrás de una SPA
(`https://www.galicia.ar/personas/buscador-de-promociones`, que en
realidad embebe el buscador real en un iframe de
`https://beneficios.galicia.ar/`). A diferencia de los otros 3 bancos, acá
ni siquiera hace falta `Referer`/`Origin` -- el endpoint responde 200 con
un `User-Agent` de navegador normal y nada más.

Limitación real de este endpoint (a diferencia de ICBC): no trae ningún
campo de texto legal ni de tope de reintegro, solo el título de la promo
("15% de ahorro"), la cadena, los días (en texto libre tipo "Jueves a
Domingo", hay que parsear) y los medios de pago. `condiciones_texto` se
arma componiendo esos campos, no es un texto legal real como en los otros
scrapers -- si más adelante hace falta el legal completo habría que
investigar el detalle de cada promo por separado (no confirmado que
exista).
"""

import os
import re
import sys
import traceback
import unicodedata

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from dedupe import unicos_por_clave  # noqa: E402
from timestamps import scraped_at  # noqa: E402

FUENTE = "galicia"

API_URL = "https://loyalty.bff.bancogalicia.com.ar/api/portal/personalizacion/v1/promociones/catalogo"
ID_CATEGORIA_SUPERMERCADOS = 8
PAGE_SIZE = 200  # alcanza para traer todo en una sola página (totalSize ~37)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

PCT_RE = re.compile(r"(\d{1,2})\s*%")

DIAS_ORDEN = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _normalizar(s):
    sin_acentos = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return sin_acentos.strip().lower()


def _dias_semana(leyenda):
    if not leyenda:
        return []
    texto = _normalizar(leyenda)

    if "todos los dias" in texto:
        return sorted(DIAS_ORDEN)

    if " a " in texto:
        ini, fin = (p.strip() for p in texto.split(" a ", 1))
        if ini in DIAS_ORDEN and fin in DIAS_ORDEN:
            i, j = DIAS_ORDEN.index(ini), DIAS_ORDEN.index(fin)
            if i <= j:
                return DIAS_ORDEN[i : j + 1]

    partes = re.split(r"\s*(?:,|\by\b)\s*", texto)
    return sorted({p for p in partes if p in DIAS_ORDEN})


def _medio_pago(item):
    partes = []
    for medio in item.get("mediosDePago") or []:
        marca = re.sub(r"(?i)^tarjeta\s+", "", (medio.get("tarjeta") or "").strip())
        marca = marca.lower().replace(" ", "_")
        tipo = (medio.get("tipoTarjeta") or "").strip().lower()
        if marca:
            partes.append(f"{marca}_{tipo}" if tipo else marca)
    return ",".join(dict.fromkeys(partes))


def _parse_item(item):
    promocion = (item.get("promocion") or "").strip()
    pct_m = PCT_RE.search(promocion)
    if not pct_m:
        return None  # promos de cuotas sin %, fuera de alcance por ahora

    titulo = (item.get("titulo") or "").strip()
    supermercado = re.sub(r"(?i)^supermercados?\s+", "", titulo).strip().lower().replace(" ", "_")

    leyenda_dias = (item.get("leyendaDiasAplicacion") or "").strip()
    vigencia_hasta = (item.get("fechaHasta") or "")[:10] or None

    condiciones = (
        f"{promocion} en {titulo}. Días: {leyenda_dias or 'no informado'}. "
        f"Válido hasta {vigencia_hasta or 'sin fecha informada'}."
    )

    return {
        "fuente": FUENTE,
        "supermercado": supermercado or "sin_dato",
        "descuento_pct": int(pct_m.group(1)),
        "tope_reintegro": None,
        "dias_semana": _dias_semana(leyenda_dias),
        "medio_pago": _medio_pago(item),
        "vigencia_desde": None,
        "vigencia_hasta": vigencia_hasta,
        "condiciones_texto": condiciones,
        "raw_text": condiciones,
        "scraped_at": scraped_at(),
    }


def run():
    promos = []
    try:
        resp = requests.get(
            API_URL,
            params={"page": 1, "pageSize": PAGE_SIZE, "IdCategoria": ID_CATEGORIA_SUPERMERCADOS},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        items = (resp.json().get("data") or {}).get("list") or []

        for item in items:
            promo = _parse_item(item)
            if promo:
                promos.append(promo)
    except Exception:
        print(f"[{FUENTE}] ERROR -- se omite esta fuente, no se tumba el resto del pipeline:")
        traceback.print_exc(file=sys.stdout)
        return []

    promos = unicos_por_clave(promos)

    if not promos:
        print(f"[{FUENTE}] ADVERTENCIA: no se encontró ninguna promo con %% -- revisar si cambió la API.")

    return promos


if __name__ == "__main__":
    for p in run():
        print(p)
