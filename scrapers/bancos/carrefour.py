"""Scraper de promos de Banco de Servicios Financieros Carrefour (tarjeta
Carrefour), para descuentos en supermercados Carrefour.

A diferencia de Provincia e ICBC, acá es HTML estático real (WordPress) en
https://carrefourbanco.com.ar/promociones-carrefour/, sin bloqueos ni WAF
ni necesidad de Playwright. Cada promo viene en un
`div.promociones_container` con atributos `data-*` ya estructurados
(días, medios de pago), y el texto completo de condiciones en un modal
asociado (`h5.modal-title` + párrafos de `.modal-body`).

No todos los `promociones_container` tienen modal -- algunos son banners
de imagen que linkean a otra página (ej. la app), sin texto parseable; se
descartan si no tienen `.modal-title`. También se descartan promos sin un
% explícito en el título (ej. "3 cuotas sin interés"), que quedan fuera de
alcance de esta fase igual que en los otros scrapers de este directorio.
"""

import os
import re
import sys
import traceback

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from dedupe import unicos_por_clave  # noqa: E402
from timestamps import scraped_at  # noqa: E402

FUENTE = "carrefour"

URL = "https://carrefourbanco.com.ar/promociones-carrefour/"

PCT_RE = re.compile(r"(\d{1,2})\s*%")
TOPE_RE = re.compile(r"tope[^\$]*\$\s*([\d.,]+)", re.IGNORECASE)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _parse_monto(s):
    if not s:
        return None
    limpio = s.replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def _split_attr(value):
    return sorted({v for v in (value or "").strip().split() if v})


def _parse_container(container):
    modal_title = container.select_one(".modal-title")
    if not modal_title:
        return None

    titulo = modal_title.get_text(strip=True)
    pct_m = PCT_RE.search(titulo)
    if not pct_m:
        return None

    parrafos = container.select(".modal-body p")
    texto_legal = " ".join(
        p.get_text(" ", strip=True) for p in parrafos if p.get_text(strip=True)
    ) or titulo

    tope_m = TOPE_RE.search(texto_legal)

    return {
        "fuente": FUENTE,
        "supermercado": "carrefour",
        "descuento_pct": int(pct_m.group(1)),
        "tope_reintegro": _parse_monto(tope_m.group(1)) if tope_m else None,
        "dias_semana": _split_attr(container.get("data-dia_de_la_semana")),
        "medio_pago": ",".join(_split_attr(container.get("data-medios_de_pago"))),
        "vigencia_desde": None,
        "vigencia_hasta": None,
        "condiciones_texto": texto_legal,
        "raw_text": f"{titulo} -- {texto_legal}",
        "scraped_at": scraped_at(),
    }


def run():
    promos = []
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for container in soup.select("div.promociones_container"):
            promo = _parse_container(container)
            if promo:
                promos.append(promo)
    except Exception:
        print(f"[{FUENTE}] ERROR -- se omite esta fuente, no se tumba el resto del pipeline:")
        traceback.print_exc(file=sys.stdout)
        return []

    promos = unicos_por_clave(promos)

    if not promos:
        print(f"[{FUENTE}] ADVERTENCIA: no se encontró ninguna promo con %% -- revisar si cambió el HTML.")

    return promos


if __name__ == "__main__":
    for p in run():
        print(p)
