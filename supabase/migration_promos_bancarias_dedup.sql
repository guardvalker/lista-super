-- ============================================================================
-- Migración incremental: dedup de promos_bancarias. Ejecutar en el SQL
-- Editor del dashboard de Supabase (Database > SQL Editor > New query >
-- pegar todo > Run).
--
-- Bug que corrige: run_all.py hacía upsert() de promos_bancarias SIN
-- on_conflict. Sin un unique constraint que lo respalde, un upsert sin
-- conflict target es un INSERT de toda la vida -- cada corrida diaria del
-- cron reinsertaba las mismas promos en vez de actualizarlas, la tabla
-- crecía sin límite. Con este constraint + on_conflict explícito en
-- run_all.py (ya en el código), cada corrida actualiza la fila existente
-- de la misma promo en vez de duplicarla.
--
-- Antes de agregar el constraint, borra los duplicados existentes
-- quedándose con la fila más nueva (id más alto) de cada grupo -- NO borra
-- todo, solo colapsa cada grupo de duplicados a una sola fila. Usa `IS NOT
-- DISTINCT FROM` en vez de `=` para tratar los NULL existentes en
-- `supermercado`/`medio_pago` como iguales entre sí a fines de esta
-- limpieza puntual (los scrapers ya no van a mandar NULL de acá en más).
-- ============================================================================

delete from promos_bancarias a
using promos_bancarias b
where a.id < b.id
  and a.fuente = b.fuente
  and a.supermercado is not distinct from b.supermercado
  and a.descuento_pct is not distinct from b.descuento_pct
  and a.dias_semana = b.dias_semana
  and a.medio_pago is not distinct from b.medio_pago;

alter table promos_bancarias
  add constraint promos_bancarias_dedup_key
  unique (fuente, supermercado, descuento_pct, dias_semana, medio_pago);
