-- ============================================================================
-- Migración incremental: catálogo de ingredientes "aprendidos".
-- Ejecutar en el SQL Editor del dashboard de Supabase (Database > SQL
-- Editor > New query > pegar todo > Run). Es seguro correrlo de nuevo si ya
-- la habías corrido antes (todo usa `if not exists` / `if exists`) — de
-- hecho conviene volver a correrla si ya la habías corrido: se sacó una
-- constraint que rompía el guardado al editar el texto de un ingrediente.
--
-- Qué resuelve: las sugerencias de autocompletado salían del diccionario
-- fijo del código más lo que hubiera en ese momento en la lista de compras o
-- en alguna receta — si borrabas el item o la receta, el ingrediente que
-- habías tipeado a mano desaparecía de las sugerencias. Esta tabla guarda
-- ese aprendizaje aparte, editable/borrable desde la pantalla
-- "Ingredientes", y sincroniza entre dispositivos como el resto de la lista.
--
-- Si en la app seguís viendo el error "could not find the table ... in the
-- schema cache" después de correr esto, es que PostgREST todavía no
-- refrescó su cache — el NOTIFY del final debería forzarlo al toque, pero
-- si persiste probá también Settings > API > "Reload schema cache" en el
-- dashboard.
-- ============================================================================

create table if not exists ls_ingredientes_conocidos (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  key text not null,
  text text not null,
  category text not null,
  updated_at timestamptz not null default now()
);

-- por si quedó de una corrida anterior de esta misma migración, antes de
-- sacarla: rompía el upsert al editar el texto (y por lo tanto el key) de
-- una fila ya sincronizada, y sin especificar bien la constraint de
-- conflicto en el upsert daba "no unique or exclusion constraint matching
-- the on conflict specification". Recorre pg_constraint en vez de asumir el
-- nombre exacto, para no depender de cómo Postgres lo haya generado.
do $$
declare
  r record;
begin
  for r in
    select conname from pg_constraint
    where conrelid = 'public.ls_ingredientes_conocidos'::regclass and contype = 'u'
  loop
    execute format('alter table ls_ingredientes_conocidos drop constraint %I', r.conname);
  end loop;
end $$;

create index if not exists ls_ingredientes_conocidos_lista_id_idx on ls_ingredientes_conocidos (lista_id);

alter table ls_ingredientes_conocidos enable row level security;

grant select, insert, update, delete on ls_ingredientes_conocidos to authenticated;

drop policy if exists "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos;
create policy "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

notify pgrst, 'reload schema';
