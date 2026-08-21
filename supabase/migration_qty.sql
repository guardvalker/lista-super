-- ============================================================================
-- Migración incremental: cantidad/peso a comprar por item de la lista.
-- Ejecutar en el SQL Editor del dashboard de Supabase (Database > SQL
-- Editor > New query > pegar todo > Run).
--
-- Agrega la columna `qty` (texto libre, ej: "500g", "1kg", "2 docenas") a
-- ls_items. No rompe nada existente: la columna es nullable y los items ya
-- guardados quedan con qty = NULL hasta que alguien la complete.
-- ============================================================================

alter table ls_items add column if not exists qty text;
