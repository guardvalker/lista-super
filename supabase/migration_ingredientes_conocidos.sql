-- ============================================================================
-- Migración incremental: catálogo de ingredientes "aprendidos".
-- Ejecutar una sola vez en el SQL Editor del dashboard de Supabase
-- (Database > SQL Editor > New query > pegar todo > Run). Es seguro
-- correrlo aunque ya hayas corrido schema.sql completo antes — usa
-- `if not exists` en todo salvo la policy, que se dropea primero por si
-- ya existiera de una corrida anterior de esta misma migración.
--
-- Qué resuelve: hasta ahora las sugerencias de autocompletado salían del
-- diccionario fijo del código más lo que hubiera en la lista de compras o en
-- alguna receta en ese momento — si borrabas el item o la receta, el
-- ingrediente que habías tipeado a mano desaparecía de las sugerencias. Esta
-- tabla guarda ese aprendizaje aparte, para siempre (nunca se borra desde el
-- cliente), y sincroniza entre dispositivos como el resto de la lista.
-- ============================================================================

create table if not exists ls_ingredientes_conocidos (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  key text not null,
  text text not null,
  category text not null,
  updated_at timestamptz not null default now(),
  unique (lista_id, key)
);

create index if not exists ls_ingredientes_conocidos_lista_id_idx on ls_ingredientes_conocidos (lista_id);

alter table ls_ingredientes_conocidos enable row level security;

grant select, insert, update, delete on ls_ingredientes_conocidos to authenticated;

drop policy if exists "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos;
create policy "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));
