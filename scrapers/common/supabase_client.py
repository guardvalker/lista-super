"""Wrapper fino sobre el cliente de Supabase para los scrapers.

Lee las credenciales de SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (las mismas
que se cargan como secrets en el workflow de GitHub Actions). Si no estan
seteadas -- por ejemplo corriendo el script a mano en una compu sin la
service_role key -- entra en modo "dry run": en vez de escribir a la base,
imprime en consola las filas que hubiera hecho upsert. Esto permite probar
el scraping/parseo de cada fuente sin tener la key real a mano.
"""

import os
import sys


def is_configured():
    return bool(os.environ.get("SUPABASE_URL")) and bool(
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


class DryRunTable:
    """Simula la interfaz mínima de postgrest-py que usan los scrapers
    (`.upsert(rows, on_conflict=...).execute()`), pero solo imprime."""

    def __init__(self, name):
        self.name = name

    def upsert(self, rows, on_conflict=None):
        if not isinstance(rows, list):
            rows = [rows]
        print(f"[dry-run] {self.name}: upsert de {len(rows)} fila(s) (on_conflict={on_conflict})")
        for row in rows[:5]:
            print(f"  {row}")
        if len(rows) > 5:
            print(f"  ... y {len(rows) - 5} más")
        return self

    def execute(self):
        return self


class DryRunClient:
    def table(self, name):
        return DryRunTable(name)


def get_client():
    """Devuelve un cliente real de supabase-py si hay credenciales, o un
    DryRunClient que solo imprime si no las hay."""
    if not is_configured():
        print(
            "[dry-run] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY no están seteadas -- "
            "no se va a escribir nada a la base real.",
            file=sys.stderr,
        )
        return DryRunClient()

    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)
