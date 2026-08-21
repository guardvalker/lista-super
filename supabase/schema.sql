-- ============================================================================
-- lista-super — schema Supabase para sync compartido (items, recetas, menú
-- semanal). Ejecutar completo en el SQL Editor del dashboard del proyecto
-- (Database > SQL Editor > New query > pegar todo > Run), o con
-- `supabase db push` si preferís tenerlo versionado vía CLI.
--
-- No requiere PostGIS ni ninguna extensión más allá de pgcrypto (para
-- gen_random_uuid()), que Supabase trae habilitada por defecto.
-- ============================================================================

create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
-- Tablas
-- ----------------------------------------------------------------------------

create table if not exists ls_listas (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  creado_por uuid not null references auth.users(id),
  creado_en timestamptz not null default now()
);

create table if not exists ls_miembros (
  lista_id uuid not null references ls_listas(id) on delete cascade,
  usuario_id uuid not null references auth.users(id) on delete cascade,
  display_name text,
  agregado_en timestamptz not null default now(),
  primary key (lista_id, usuario_id)
);

create table if not exists ls_items (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  text text not null,
  checked boolean not null default false,
  category text not null,
  qty text,
  agregado_por uuid references auth.users(id),
  updated_at timestamptz not null default now()
);

-- Nota: no hay columna recipe_count. Es un valor derivado (suma de entradas
-- activas del menú semanal que referencian el ingrediente) y se recalcula
-- client-side después de cada sync para no desincronizarse entre dispositivos.

create table if not exists ls_recetas (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  nombre text not null,
  updated_at timestamptz not null default now()
);

create table if not exists ls_receta_ingredientes (
  id uuid primary key default gen_random_uuid(),
  receta_id uuid not null references ls_recetas(id) on delete cascade,
  text text not null,
  category text
);

create table if not exists ls_receta_subrecetas (
  receta_id uuid not null references ls_recetas(id) on delete cascade,
  sub_receta_id uuid not null references ls_recetas(id) on delete cascade,
  primary key (receta_id, sub_receta_id)
);

create table if not exists ls_receta_pasos (
  id uuid primary key default gen_random_uuid(),
  receta_id uuid not null references ls_recetas(id) on delete cascade,
  step_number int not null,
  time_value numeric,
  time_unit text,
  acciones text[] not null default '{}'
);

create table if not exists ls_paso_ingredientes (
  paso_id uuid not null references ls_receta_pasos(id) on delete cascade,
  ingrediente_id uuid not null references ls_receta_ingredientes(id) on delete cascade,
  quantity_amount numeric,
  quantity_unit text,
  primary key (paso_id, ingrediente_id)
);

create table if not exists ls_weekly_plan_entries (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  day_key text not null,
  receta_id uuid not null references ls_recetas(id) on delete cascade,
  active boolean not null default false,
  updated_at timestamptz not null default now()
);

-- Catálogo de ingredientes "aprendidos": todo texto no reconocido por el
-- diccionario fijo del cliente (PRODUCT_MAP) que el usuario categorizó a
-- mano alguna vez, para que el autocompletado lo siga sugiriendo aunque el
-- item se borre de la lista o de todas las recetas — editable y borrable
-- desde la pantalla "Ingredientes". `key` es el texto normalizado (sin
-- tildes, en minúscula); el dedupe entre dispositivos es client-side
-- (getIngredientCatalogEntries), no una constraint acá, para no pelearse con
-- ediciones que cambian el texto (y por lo tanto el key) de una fila ya
-- sincronizada.
create table if not exists ls_ingredientes_conocidos (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  key text not null,
  text text not null,
  category text not null,
  updated_at timestamptz not null default now()
);

create index if not exists ls_items_lista_id_idx on ls_items (lista_id);
create index if not exists ls_recetas_lista_id_idx on ls_recetas (lista_id);
create index if not exists ls_receta_ingredientes_receta_id_idx on ls_receta_ingredientes (receta_id);
create index if not exists ls_receta_subrecetas_sub_receta_id_idx on ls_receta_subrecetas (sub_receta_id);
create index if not exists ls_receta_pasos_receta_id_idx on ls_receta_pasos (receta_id);
create index if not exists ls_paso_ingredientes_ingrediente_id_idx on ls_paso_ingredientes (ingrediente_id);
create index if not exists ls_weekly_plan_entries_lista_id_idx on ls_weekly_plan_entries (lista_id);
create index if not exists ls_weekly_plan_entries_receta_id_idx on ls_weekly_plan_entries (receta_id);
create index if not exists ls_ingredientes_conocidos_lista_id_idx on ls_ingredientes_conocidos (lista_id);

-- ----------------------------------------------------------------------------
-- Helper: ¿el usuario autenticado actual es miembro de esta lista?
-- security definer para poder usarse dentro de las políticas RLS de
-- ls_miembros sin caer en recursión (la función esquiva el RLS de la propia
-- tabla que consulta).
-- ----------------------------------------------------------------------------

create or replace function ls_is_member(p_lista_id uuid)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from ls_miembros m
    where m.lista_id = p_lista_id and m.usuario_id = auth.uid()
  );
$$;

grant execute on function ls_is_member(uuid) to authenticated;

-- ----------------------------------------------------------------------------
-- RLS
-- ----------------------------------------------------------------------------

alter table ls_listas enable row level security;
alter table ls_miembros enable row level security;
alter table ls_items enable row level security;
alter table ls_recetas enable row level security;
alter table ls_receta_ingredientes enable row level security;
alter table ls_receta_subrecetas enable row level security;
alter table ls_receta_pasos enable row level security;
alter table ls_paso_ingredientes enable row level security;
alter table ls_weekly_plan_entries enable row level security;
alter table ls_ingredientes_conocidos enable row level security;

-- Grants explícitos de nivel tabla, para no depender de que el proyecto
-- Supabase tenga configurados los default privileges esperados — RLS por sí
-- sola no alcanza si el rol `authenticated` no tiene ni el permiso base.
grant select, insert, update, delete on
  ls_listas, ls_miembros, ls_items, ls_recetas, ls_receta_ingredientes,
  ls_receta_subrecetas, ls_receta_pasos, ls_paso_ingredientes, ls_weekly_plan_entries,
  ls_ingredientes_conocidos
to authenticated;

-- ls_listas: ver las que integrás; crear libre (te agregás como miembro
-- después, desde el cliente, en la misma operación de "crear lista");
-- cualquier miembro puede renombrarla; solo quien la creó puede borrarla.
create policy "ls_listas_select" on ls_listas
  for select using (ls_is_member(id));

create policy "ls_listas_insert" on ls_listas
  for insert with check (creado_por = auth.uid());

create policy "ls_listas_update" on ls_listas
  for update using (ls_is_member(id));

create policy "ls_listas_delete" on ls_listas
  for delete using (creado_por = auth.uid());

-- ls_miembros: ver miembros de tus propias listas; unirte a una lista
-- (insertar tu propia fila — "unirse" = conocer el lista_id compartido por
-- link/código); salir vos mismo.
create policy "ls_miembros_select" on ls_miembros
  for select using (ls_is_member(lista_id));

create policy "ls_miembros_insert" on ls_miembros
  for insert with check (usuario_id = auth.uid());

create policy "ls_miembros_delete" on ls_miembros
  for delete using (usuario_id = auth.uid());

-- ls_items / ls_recetas / ls_weekly_plan_entries: acceso completo si sos
-- miembro de la lista.
create policy "ls_items_all" on ls_items
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

create policy "ls_recetas_all" on ls_recetas
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

create policy "ls_weekly_plan_entries_all" on ls_weekly_plan_entries
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

create policy "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

-- Tablas hijas de receta: la membresía se resuelve subiendo hasta la receta
-- padre (y de ahí a la lista).
create policy "ls_receta_ingredientes_all" on ls_receta_ingredientes
  for all using (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  ) with check (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  );

create policy "ls_receta_subrecetas_all" on ls_receta_subrecetas
  for all using (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  ) with check (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  );

create policy "ls_receta_pasos_all" on ls_receta_pasos
  for all using (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  ) with check (
    exists (select 1 from ls_recetas r where r.id = receta_id and ls_is_member(r.lista_id))
  );

create policy "ls_paso_ingredientes_all" on ls_paso_ingredientes
  for all using (
    exists (
      select 1 from ls_receta_pasos p
      join ls_recetas r on r.id = p.receta_id
      where p.id = paso_id and ls_is_member(r.lista_id)
    )
  ) with check (
    exists (
      select 1 from ls_receta_pasos p
      join ls_recetas r on r.id = p.receta_id
      where p.id = paso_id and ls_is_member(r.lista_id)
    )
  );

-- ----------------------------------------------------------------------------
-- replace_receta: reemplazo atómico de una receta completa (ingredientes,
-- subrecetas, pasos armados y sus ingredientes) a partir de un payload JSON
-- con la misma forma que el objeto `recipe` del cliente. security invoker
-- (no definer) para que las políticas RLS de arriba sigan aplicando con el
-- usuario que llama — si no es miembro de la lista, los inserts/deletes
-- fallan solos.
--
-- Payload esperado:
-- {
--   "nombre": "...",
--   "ingredientes": [{"id": uuid, "text": "...", "category": "..."}],
--   "subRecetaIds": [uuid, ...],
--   "pasos": [{
--     "id": uuid, "stepNumber": 1, "timeValue": 10, "timeUnit": "min",
--     "actions": ["picar", "saltear"],
--     "items": [{"ingredientId": uuid, "quantityAmount": 2, "quantityUnit": "u"}]
--   }]
-- }
-- ----------------------------------------------------------------------------

create or replace function replace_receta(p_receta_id uuid, p_lista_id uuid, p_payload jsonb)
returns void
language plpgsql
security invoker
as $$
declare
  v_ing jsonb;
  v_paso jsonb;
  v_item jsonb;
  v_paso_id uuid;
begin
  insert into ls_recetas (id, lista_id, nombre, updated_at)
  values (p_receta_id, p_lista_id, p_payload->>'nombre', now())
  on conflict (id) do update set nombre = excluded.nombre, updated_at = now();

  delete from ls_paso_ingredientes
    where paso_id in (select id from ls_receta_pasos where receta_id = p_receta_id);
  delete from ls_receta_pasos where receta_id = p_receta_id;
  delete from ls_receta_subrecetas where receta_id = p_receta_id;
  delete from ls_receta_ingredientes where receta_id = p_receta_id;

  for v_ing in select * from jsonb_array_elements(coalesce(p_payload->'ingredientes', '[]'::jsonb))
  loop
    insert into ls_receta_ingredientes (id, receta_id, text, category)
    values ((v_ing->>'id')::uuid, p_receta_id, v_ing->>'text', v_ing->>'category');
  end loop;

  insert into ls_receta_subrecetas (receta_id, sub_receta_id)
  select p_receta_id, (value #>> '{}')::uuid
  from jsonb_array_elements(coalesce(p_payload->'subRecetaIds', '[]'::jsonb));

  for v_paso in select * from jsonb_array_elements(coalesce(p_payload->'pasos', '[]'::jsonb))
  loop
    v_paso_id := (v_paso->>'id')::uuid;
    insert into ls_receta_pasos (id, receta_id, step_number, time_value, time_unit, acciones)
    values (
      v_paso_id,
      p_receta_id,
      (v_paso->>'stepNumber')::int,
      nullif(v_paso->>'timeValue', '')::numeric,
      v_paso->>'timeUnit',
      coalesce(
        (select array_agg(x) from jsonb_array_elements_text(coalesce(v_paso->'actions', '[]'::jsonb)) x),
        '{}'
      )
    );

    for v_item in select * from jsonb_array_elements(coalesce(v_paso->'items', '[]'::jsonb))
    loop
      insert into ls_paso_ingredientes (paso_id, ingrediente_id, quantity_amount, quantity_unit)
      values (
        v_paso_id,
        (v_item->>'ingredientId')::uuid,
        nullif(v_item->>'quantityAmount', '')::numeric,
        v_item->>'quantityUnit'
      );
    end loop;
  end loop;
end;
$$;

grant execute on function replace_receta(uuid, uuid, jsonb) to authenticated;

-- ----------------------------------------------------------------------------
-- Realtime: exponer las tablas para que supabase-js pueda suscribirse a
-- postgres_changes filtrado por lista_id.
-- ----------------------------------------------------------------------------

alter publication supabase_realtime add table
  ls_items, ls_recetas, ls_receta_ingredientes, ls_receta_subrecetas,
  ls_receta_pasos, ls_paso_ingredientes, ls_weekly_plan_entries, ls_miembros;
