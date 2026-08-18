// Config de Supabase para lista-super. Se commitea tal cual (la anon key
// está diseñada por Supabase para ser pública — la seguridad real la dan las
// políticas RLS en supabase/schema.sql, no ocultar esta key).
//
// Completar con los valores reales de Settings > API en el dashboard del
// proyecto Supabase. Mientras queden los placeholders, la app funciona
// exactamente igual que antes (100% localStorage, sin sync).
window.SUPABASE_CONFIG = {
  url: 'https://TU-PROYECTO.supabase.co',
  anonKey: 'TU-ANON-KEY',
};
