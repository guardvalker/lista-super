-- ============================================================================
-- Migración incremental: origen de una receta cuando viene de una
-- "pre-receta" del catálogo (assets/pre-recetas.json, ver feature
-- Pre-recetas). Ejecutar en el SQL Editor del dashboard de Supabase
-- (Database > SQL Editor > New query > pegar todo > Run).
--
-- source_id: id de la pre-receta en el catálogo estático, mientras la
-- receta no se haya editado (editarla la "bifurca" a propia y limpia este
-- campo, ver saveRecipe() en index.html).
-- source_url: link a la receta original en paulinacocina.net, se conserva
-- aunque se edite (referencia inofensiva).
-- No rompe nada existente: ambas columnas son nullable y las recetas ya
-- guardadas quedan con estos campos en NULL (recetas propias, como siempre).
-- ============================================================================

alter table ls_recetas add column if not exists source_id text;
alter table ls_recetas add column if not exists source_url text;

-- Hace falta también reemplazar replace_receta(): la versión vieja no
-- conoce source_id/source_url, así que aunque existan las columnas de
-- arriba, el RPC las va a seguir dejando en NULL en cada push. Sin este
-- reemplazo, el link a la receta original se pierde en el primer
-- ida-y-vuelta con Supabase aunque el agregado se vea bien en el momento.
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
  insert into ls_recetas (id, lista_id, nombre, source_id, source_url, updated_at)
  values (p_receta_id, p_lista_id, p_payload->>'nombre', p_payload->>'sourceId', p_payload->>'sourceUrl', now())
  on conflict (id) do update set
    nombre = excluded.nombre,
    source_id = excluded.source_id,
    source_url = excluded.source_url,
    updated_at = now();

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
