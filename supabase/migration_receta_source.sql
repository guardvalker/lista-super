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
