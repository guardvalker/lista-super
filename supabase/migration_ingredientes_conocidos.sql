-- ============================================================================
-- Migración incremental: catálogo de ingredientes "aprendidos".
-- Ejecutar en el SQL Editor del dashboard de Supabase (Database > SQL
-- Editor > New query > pegar todo > Run).
--
-- Esta versión arranca borrando la tabla si ya existe (DROP TABLE) y la
-- recrea de cero. Los intentos anteriores de esta migración le fueron
-- parchando constraints en vez de recrearla, y algo quedó mal (el error
-- "no unique or exclusion constraint matching the on conflict
-- specification" indica que la primary key de `id` no está sana). Como
-- esta tabla nunca llegó a sincronizar nada con éxito, no hay datos reales
-- que perder — es segura de borrar y recrear. Si por algún motivo ya tenés
-- ingredientes guardados ahí que te importen, avisame antes de correr esto.
--
-- Qué resuelve: las sugerencias de autocompletado salían del diccionario
-- fijo del código más lo que hubiera en ese momento en la lista de compras o
-- en alguna receta — si borrabas el item o la receta, el ingrediente que
-- habías tipeado a mano desaparecía de las sugerencias. Esta tabla guarda
-- ese aprendizaje aparte, editable/borrable desde la pantalla
-- "Ingredientes", y sincroniza entre dispositivos como el resto de la lista.
-- ============================================================================

drop table if exists ls_ingredientes_conocidos cascade;

create table ls_ingredientes_conocidos (
  id uuid primary key default gen_random_uuid(),
  lista_id uuid not null references ls_listas(id) on delete cascade,
  key text not null,
  text text not null,
  category text not null,
  updated_at timestamptz not null default now()
);

create index ls_ingredientes_conocidos_lista_id_idx on ls_ingredientes_conocidos (lista_id);

alter table ls_ingredientes_conocidos enable row level security;

grant select, insert, update, delete on ls_ingredientes_conocidos to authenticated;

create policy "ls_ingredientes_conocidos_all" on ls_ingredientes_conocidos
  for all using (ls_is_member(lista_id)) with check (ls_is_member(lista_id));

notify pgrst, 'reload schema';
