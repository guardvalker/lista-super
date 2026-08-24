-- ============================================================================
-- Migración incremental: precios_termino, para el "¿esto es caro o barato?"
-- de la lista de compras. Ejecutar en el SQL Editor del dashboard de
-- Supabase (Database > SQL Editor > New query > pegar todo > Run).
--
-- Guarda un precio de referencia por TÉRMINO de búsqueda (no por EAN
-- puntual como `precios`): la mediana de precio_min entre todos los
-- productos que matchean ese término en Precios Claros ese día. El
-- término es el mismo texto que usa PRODUCT_MAP en index.html (y que
-- scrapers/common/productos_interes.py copia de ahí), así que un item de
-- la lista de compras se resuelve al mismo término sin necesitar ninguna
-- tabla de mapeo aparte -- ver detectCategory()/resolverTerminoPrecio()
-- en index.html, que usan exactamente la misma lógica de matching.
-- ============================================================================

create table if not exists precios_termino (
  id bigserial primary key,
  termino text not null,
  fecha date not null,
  precio_promedio numeric not null,
  cant_productos integer,
  created_at timestamptz not null default now(),
  unique (termino, fecha)
);

create index if not exists precios_termino_idx on precios_termino (termino, fecha desc);

alter table precios_termino enable row level security;
grant select on precios_termino to anon, authenticated;
create policy "precios_termino_select" on precios_termino for select using (true);
