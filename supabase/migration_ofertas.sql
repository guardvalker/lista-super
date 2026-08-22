-- ============================================================================
-- Migración incremental: precios de supermercados + promos bancarias, para
-- alimentar el botón "% Ofertas" de la app. Ejecutar en el SQL Editor del
-- dashboard de Supabase (Database > SQL Editor > New query > pegar todo >
-- Run).
--
-- A diferencia de las tablas `ls_*` (datos de una lista compartida puntual),
-- estas son tablas de referencia globales, compartidas por todos los
-- usuarios de la app: no van scopeadas a una lista_id ni tienen prefijo
-- `ls_`. Se escriben SOLO desde los scrapers de scrapers/ (GitHub Actions,
-- con la service_role key -- eso ignora RLS por diseño). El cliente de la
-- PWA (anon key) solo puede leerlas.
--
-- Nota sobre `precios`: el endpoint de Precios Claros que usamos
-- (scrapers/precios_claros/fetch_precios.py) NO da precio por sucursal
-- individual -- solo compara contra un máximo de 50 sucursales por request
-- y devuelve un precio_min/precio_max agregado entre esas. Por eso esta
-- tabla guarda un rango agregado por producto/día (referido a las 50
-- sucursales más cercanas al usuario), no una fila por sucursal.
-- ============================================================================

create table if not exists sucursales (
  id text primary key,              -- id de Precios Claros, ej "9-1-485"
  cadena text not null,
  direccion text,
  localidad text,
  lat double precision,
  lng double precision,
  distancia_km numeric,             -- distancia al punto de referencia (La Lucila/Martínez)
  updated_at timestamptz not null default now()
);

create table if not exists productos (
  id text primary key,              -- EAN/código de barras de Precios Claros
  nombre text not null,
  marca text,
  presentacion text,
  updated_at timestamptz not null default now()
);

create table if not exists precios (
  id bigserial primary key,
  producto_id text not null references productos(id) on delete cascade,
  fecha date not null,
  precio_min numeric not null,
  precio_max numeric not null,
  cant_sucursales integer,          -- cuántas de las sucursales consultadas tenían el producto
  created_at timestamptz not null default now(),
  unique (producto_id, fecha)
);

create table if not exists promos_bancarias (
  id bigserial primary key,
  fuente text not null,             -- provincia, galicia, icbc, mercadopago, carrefour, etc.
  supermercado text,                -- cadena aplicable, "todos" si aplica a cualquiera
  descuento_pct numeric,
  tope_reintegro numeric,
  dias_semana text[],               -- ['martes','miercoles']
  medio_pago text,
  vigencia_desde date,
  vigencia_hasta date,
  condiciones_texto text,
  raw_text text,
  scraped_at timestamptz not null default now()
);

create index if not exists precios_producto_idx on precios (producto_id, fecha desc);
create index if not exists promos_bancarias_vigencia_idx on promos_bancarias (vigencia_desde, vigencia_hasta);
create index if not exists promos_bancarias_super_idx on promos_bancarias (supermercado);

-- ----------------------------------------------------------------------------
-- RLS: lectura pública (igual filosofía que el resto del proyecto: la anon
-- key es segura de exponer porque RLS es el gate real), sin insert/update/
-- delete para anon/authenticated -- esas tablas solo se escriben con la
-- service_role key desde los scrapers, que bypassea RLS.
-- ----------------------------------------------------------------------------

alter table sucursales enable row level security;
alter table productos enable row level security;
alter table precios enable row level security;
alter table promos_bancarias enable row level security;

grant select on sucursales to anon, authenticated;
grant select on productos to anon, authenticated;
grant select on precios to anon, authenticated;
grant select on promos_bancarias to anon, authenticated;

create policy "sucursales_select" on sucursales for select using (true);
create policy "productos_select" on productos for select using (true);
create policy "precios_select" on precios for select using (true);
create policy "promos_bancarias_select" on promos_bancarias for select using (true);
