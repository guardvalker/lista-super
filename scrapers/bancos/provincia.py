"""Scraper de promos bancarias de Banco Provincia (Cuenta DNI).

La página oficial de beneficios que suele documentarse
(bancoprovincia.com.ar/Ciudadanos/BeneficiosBancoProvincia) está caída
("Página no Disponible") -- probado en vivo. La página real y vigente con
las promos de supermercados de Cuenta DNI es:

    https://www.bancoprovincia.com.ar/cuentadni/buscadores/supermercados

Es una SPA (single-spa/React) -- el HTML crudo viene vacío, hace falta
un navegador real (Playwright) para que el contenido se renderice. El
texto de la(s) promo(s) vigente(s) está en el DOM como texto libre (no
hay un campo JSON separado con el %/días/tope), así que se parsea con
regex sobre el texto visible de la página. Puede haber más de una promo
mostrada a la vez (la general de Cuenta DNI + alguna específica de una
cadena puntual) -- se capturan todos los bloques que matcheen el patrón,
no solo el primero.

Como cualquier scraper de este directorio: si algo falla (cambió el HTML,
cambió la promo, la página no carga), se loguea el error y se devuelve
una lista vacía en vez de tirar una excepción -- así un banco roto no
tumba el resto del pipeline (ver run_all.py).
"""

import re
import sys
import traceback

URL = "https://www.bancoprovincia.com.ar/cuentadni/buscadores/supermercados"
FUENTE = "provincia"

DIAS = {
    "lunes": "lunes", "martes": "martes", "miercoles": "miercoles",
    "miércoles": "miercoles", "jueves": "jueves", "viernes": "viernes",
    "sabado": "sabado", "sábado": "sabado", "domingo": "domingo",
}

CADENAS_CONOCIDAS = [
    "carrefour", "coto", "dia", "chango mas", "chango más", "jumbo",
    "disco", "vea", "toledo", "la anonima", "la anónima", "makro",
]

# Bloques de texto candidatos a ser una promo: tienen que mencionar un %.
PROMO_HINT_RE = re.compile(r"\d{1,2}\s*%")
PCT_RE = re.compile(r"(\d{1,2})\s*%")
TOPE_RE = re.compile(r"tope[^\$]*\$\s*([\d.,]+)", re.IGNORECASE)
DIA_RE = re.compile(
    r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b", re.IGNORECASE
)


def _parse_monto(s):
    if not s:
        return None
    limpio = s.replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def _parse_bloque(texto):
    pct_m = PCT_RE.search(texto)
    if not pct_m:
        return None

    dias = sorted({DIAS[d.lower()] for d in DIA_RE.findall(texto)})
    tope_m = TOPE_RE.search(texto)

    supermercado = "todos"
    texto_low = texto.lower()
    for cadena in CADENAS_CONOCIDAS:
        # \b de palabra completa: un match tipo "dia" (cadena Día) no debe
        # saltar por matchear adentro de "mediante", "diario", etc.
        if re.search(r"\b" + re.escape(cadena) + r"\b", texto_low):
            supermercado = cadena.replace(" ", "_")
            break

    return {
        "fuente": FUENTE,
        "supermercado": supermercado,
        "descuento_pct": int(pct_m.group(1)),
        "tope_reintegro": _parse_monto(tope_m.group(1)) if tope_m else None,
        "dias_semana": dias,
        "medio_pago": "cuenta_dni",
        "vigencia_desde": None,
        "vigencia_hasta": None,
        "condiciones_texto": texto.strip(),
        "raw_text": texto.strip(),
    }


def _extraer_bloques_promo(page):
    """Devuelve los textos de los nodos que probablemente describan una
    promo (mencionan un %), evitando duplicar texto anidado: se queda con
    el nodo de texto más chico que ya contiene el %, no sus ancestros."""
    candidatos = page.eval_on_selector_all(
        "body *",
        """(els) => els
            .filter(el => el.children.length === 0)  // solo nodos hoja
            .filter(el => !['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName))
            .map(el => el.innerText || '')
            .filter(t => t && t.trim().length > 0)
        """,
    )
    return [t for t in candidatos if PROMO_HINT_RE.search(t)]


def run():
    from playwright.sync_api import sync_playwright

    promos = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(2000)

            bloques = _extraer_bloques_promo(page)
            vistos = set()
            for texto in bloques:
                promo = _parse_bloque(texto)
                if not promo:
                    continue
                key = (promo["descuento_pct"], tuple(promo["dias_semana"]), promo["raw_text"])
                if key in vistos:
                    continue
                vistos.add(key)
                promos.append(promo)

            browser.close()
    except Exception:
        print(f"[{FUENTE}] ERROR -- se omite esta fuente, no se tumba el resto del pipeline:")
        traceback.print_exc(file=sys.stdout)
        return []

    if not promos:
        print(f"[{FUENTE}] ADVERTENCIA: no se encontró ningún bloque de promo con %% -- revisar si cambió el HTML.")

    return promos


if __name__ == "__main__":
    for p in run():
        print(p)
