"""Orquesta todos los scrapers de bancos/billeteras, tolerando fallos
individuales: si uno se rompe (cambió el HTML, la página no responde),
se loguea y se sigue con los demás -- no debe tumbar todo el pipeline.

Fase 2: Provincia, ICBC y Carrefour. Mercado Pago quedó descartado (no
tiene página pública de descuentos de super, ver memoria del proyecto).
Galicia queda pendiente -- tiene API real pero falta el endpoint exacto
de la categoría Supermercados.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from supabase_client import get_client  # noqa: E402

import carrefour  # noqa: E402
import icbc  # noqa: E402
import provincia  # noqa: E402

SCRAPERS = [
    provincia,
    icbc,
    carrefour,
    # galicia -- pendiente, falta el endpoint de la categoría Supermercados
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
