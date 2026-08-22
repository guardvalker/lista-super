"""Orquesta todos los scrapers de bancos/billeteras, tolerando fallos
individuales: si uno se rompe (cambió el HTML, la página no responde),
se loguea y se sigue con los demás -- no debe tumbar todo el pipeline.

Fase 1: solo Banco Provincia (prueba de concepto). Fase 2 va a sumar acá
galicia.run, icbc.run, mercadopago.run, carrefour.run con el mismo patrón.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from supabase_client import get_client  # noqa: E402

import provincia  # noqa: E402

SCRAPERS = [
    provincia,
    # galicia, icbc, mercadopago, carrefour -- fase 2
]


def main():
    client = get_client()
    total = 0

    for modulo in SCRAPERS:
        nombre = modulo.__name__
        print(f"=== {nombre} ===")
        try:
            promos = modulo.run()
        except Exception:
            print(f"[{nombre}] ERROR no capturado por el scraper -- se omite, sigue el resto:")
            traceback.print_exc(file=sys.stdout)
            continue

        if not promos:
            print(f"[{nombre}] 0 promos encontradas")
            continue

        try:
            client.table("promos_bancarias").upsert(promos).execute()
            print(f"[{nombre}] {len(promos)} promo(s) guardadas")
            total += len(promos)
        except Exception:
            print(f"[{nombre}] ERROR guardando en Supabase -- se omite, sigue el resto:")
            traceback.print_exc(file=sys.stdout)

    print(f"Total: {total} promo(s) guardadas en esta corrida")


if __name__ == "__main__":
    main()
