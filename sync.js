// Motor de sync con Supabase para lista-super. Capa de servicio pura (sin
// tocar el DOM) — index.html la consume vía window.Sync y decide qué pintar.
// Si window.SUPABASE_CONFIG sigue con los placeholders, todo el módulo queda
// inerte y la app funciona exactamente igual que sin este archivo.
window.Sync = (function () {
  const LISTA_ID_KEY = 'lista_super_lista_id';
  const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

  let sb = null;
  let cb = {};
  let currentUser = null;
  let listaId = null;
  let listaInfo = null; // { id, nombre }
  let channel = null;
  let refetchTimer = null;

  // Snapshots de lo último que se sabe que llegó a Supabase (o vino de ahí),
  // para diffear en cada push y no reescribir filas que no cambiaron.
  let lastSyncedItems = null;
  let lastSyncedRecipeSig = null; // Map<recipeId, string>
  let lastSyncedPlanFlat = null; // Map<entryId, string>

  // Últimos argumentos pasados a cada push, para poder reintentar al volver
  // la conexión sin que index.html tenga que saber nada de reintentos.
  let lastItemsArg = null;
  let lastRecipesArg = null;
  let lastPlanArg = null;

  function isConfigured() {
    const c = window.SUPABASE_CONFIG;
    return !!(c && c.url && c.anonKey && !c.url.includes('TU-PROYECTO'));
  }

  function fail(err) {
    console.error('[Sync]', err);
    cb.onSyncError && cb.onSyncError(err && err.message ? err.message : String(err));
  }

  function getStoredListaId() {
    try { return localStorage.getItem(LISTA_ID_KEY); } catch (e) { return null; }
  }
  function setStoredListaId(id) {
    try { localStorage.setItem(LISTA_ID_KEY, id); } catch (e) {}
  }
  function clearStoredListaId() {
    try { localStorage.removeItem(LISTA_ID_KEY); } catch (e) {}
  }

  function extractListaId(input) {
    const m = String(input || '').match(UUID_RE);
    return m ? m[0] : null;
  }

  function pendingJoinCodeFromUrl() {
    try {
      const url = new URL(window.location.href);
      return extractListaId(url.searchParams.get('lista'));
    } catch (e) { return null; }
  }

  // ---- Auth ----

  async function sendOtp(email) {
    if (!sb) throw new Error('Supabase no está configurado');
    const { error } = await sb.auth.signInWithOtp({ email });
    if (error) throw error;
  }

  async function verifyOtp(email, token) {
    if (!sb) throw new Error('Supabase no está configurado');
    const { error } = await sb.auth.verifyOtp({ email, token, type: 'email' });
    if (error) throw error;
  }

  async function signOut() {
    if (!sb) return;
    unsubscribeRealtime();
    await sb.auth.signOut();
    listaId = null;
    listaInfo = null;
    lastSyncedItems = null;
    lastSyncedRecipeSig = null;
    lastSyncedPlanFlat = null;
    cb.onListaChange && cb.onListaChange(null);
  }

  function getUser() {
    return currentUser;
  }

  // ---- Lista (crear / unirse / salir) ----

  function getListaId() { return listaId; }
  function getListaNombre() { return listaInfo ? listaInfo.nombre : null; }
  function getShareLink() {
    if (!listaId) return null;
    return `${window.location.origin}${window.location.pathname}?lista=${listaId}`;
  }

  // Si se perdió el localStorage (ej. se borraron los datos del sitio) pero
  // la sesión sigue viva o se vuelve a loguear, la membresía sobrevive en
  // Supabase — la recuperamos de ahí en vez de pedir de nuevo el link de
  // invitación.
  async function findMyListaId() {
    if (!sb || !currentUser) return null;
    const { data, error } = await sb
      .from('ls_miembros')
      .select('lista_id')
      .eq('usuario_id', currentUser.id)
      .limit(1)
      .maybeSingle();
    if (error || !data) return null;
    return data.lista_id;
  }

  async function refreshListaInfo() {
    if (!sb || !listaId) return;
    const { data, error } = await sb.from('ls_listas').select('id, nombre').eq('id', listaId).single();
    if (!error && data) listaInfo = data;
  }

  async function getMembers() {
    if (!sb || !listaId) return [];
    const { data, error } = await sb.from('ls_miembros').select('*').eq('lista_id', listaId);
    if (error) { fail(error); return []; }
    return data || [];
  }

  async function createLista(nombre) {
    if (!sb || !currentUser) throw new Error('Iniciá sesión primero');
    // Generamos el id acá en vez de encadenar .select() al insert: la
    // política de SELECT de ls_listas exige ser miembro, y todavía no lo
    // sos en este mismo statement (te agregás a ls_miembros recién abajo) —
    // con RETURNING, Postgres aplica esa política sobre la fila insertada y
    // aborta todo con "new row violates row-level security policy" si no
    // la pasa. Insertando el id conocido de antemano evitamos depender de
    // ese RETURNING por completo.
    const id = crypto.randomUUID();
    const { error } = await sb.from('ls_listas').insert({ id, nombre, creado_por: currentUser.id });
    if (error) throw error;
    const { error: memErr } = await sb
      .from('ls_miembros')
      .insert({ lista_id: id, usuario_id: currentUser.id, display_name: currentUser.email });
    if (memErr) throw memErr;
    await linkLista(id, { autoPull: false });
    return id;
  }

  async function joinLista(rawInput) {
    if (!sb || !currentUser) throw new Error('Iniciá sesión primero');
    const id = extractListaId(rawInput);
    if (!id) throw new Error('No reconocí un código/link de lista válido ahí');
    const { error } = await sb
      .from('ls_miembros')
      .insert({ lista_id: id, usuario_id: currentUser.id, display_name: currentUser.email });
    if (error) throw error;
    await linkLista(id, { autoPull: false });
    return id;
  }

  async function leaveLista() {
    if (!sb || !currentUser || !listaId) return;
    await sb.from('ls_miembros').delete().eq('lista_id', listaId).eq('usuario_id', currentUser.id);
    unsubscribeRealtime();
    listaId = null;
    listaInfo = null;
    lastSyncedItems = null;
    lastSyncedRecipeSig = null;
    lastSyncedPlanFlat = null;
    clearStoredListaId();
    cb.onListaChange && cb.onListaChange(null);
  }

  // autoPull=false para el flujo de crear/unirse recién ahora: el caller
  // (index.html) necesita decidir primero si ofrece migrar datos locales
  // antes de que un pull remoto los pise. autoPull=true es para cuando se
  // restaura una sesión que ya estaba vinculada a una lista.
  async function linkLista(id, { autoPull = true } = {}) {
    listaId = id;
    setStoredListaId(id);
    await refreshListaInfo();
    subscribeRealtime();
    cb.onListaChange && cb.onListaChange(listaInfo);
    if (autoPull) await refetchAll();
  }

  async function pullNow() {
    await refetchAll();
  }

  // ---- Pull remoto (fetch completo + reensamblado a la forma del cliente) ----

  async function fetchListaState() {
    const [itemsRes, recetasRes, planRes] = await Promise.all([
      sb.from('ls_items').select('*').eq('lista_id', listaId),
      sb.from('ls_recetas').select('*').eq('lista_id', listaId),
      sb.from('ls_weekly_plan_entries').select('*').eq('lista_id', listaId),
    ]);
    if (itemsRes.error) throw itemsRes.error;
    if (recetasRes.error) throw recetasRes.error;
    if (planRes.error) throw planRes.error;

    const recetaIds = recetasRes.data.map((r) => r.id);
    const [ingRes, subRes, pasosRes] = await Promise.all([
      recetaIds.length ? sb.from('ls_receta_ingredientes').select('*').in('receta_id', recetaIds) : { data: [] },
      recetaIds.length ? sb.from('ls_receta_subrecetas').select('*').in('receta_id', recetaIds) : { data: [] },
      recetaIds.length ? sb.from('ls_receta_pasos').select('*').in('receta_id', recetaIds) : { data: [] },
    ]);
    if (ingRes.error) throw ingRes.error;
    if (subRes.error) throw subRes.error;
    if (pasosRes.error) throw pasosRes.error;

    const pasoIds = pasosRes.data.map((p) => p.id);
    const pasoIngRes = pasoIds.length
      ? await sb.from('ls_paso_ingredientes').select('*').in('paso_id', pasoIds)
      : { data: [] };
    if (pasoIngRes.error) throw pasoIngRes.error;

    const items = itemsRes.data.map((i) => ({ id: i.id, text: i.text, checked: i.checked, category: i.category }));

    const recipes = recetasRes.data.map((r) => ({
      id: r.id,
      name: r.nombre,
      ingredients: ingRes.data
        .filter((i) => i.receta_id === r.id)
        .map((i) => ({ id: i.id, text: i.text, category: i.category })),
      subRecipeIds: subRes.data.filter((s) => s.receta_id === r.id).map((s) => s.sub_receta_id),
      instructionBlocks: pasosRes.data
        .filter((p) => p.receta_id === r.id)
        .sort((a, b) => a.step_number - b.step_number)
        .map((p) => ({
          id: p.id,
          stepNumber: p.step_number,
          timeValue: p.time_value,
          timeUnit: p.time_unit,
          actions: p.acciones || [],
          items: pasoIngRes.data
            .filter((pi) => pi.paso_id === p.id)
            .map((pi) => ({
              ingredientId: pi.ingrediente_id,
              quantityAmount: pi.quantity_amount,
              quantityUnit: pi.quantity_unit,
            })),
        })),
    }));

    const weeklyPlan = {};
    planRes.data.forEach((e) => {
      if (!weeklyPlan[e.day_key]) weeklyPlan[e.day_key] = [];
      weeklyPlan[e.day_key].push({ id: e.id, recipeId: e.receta_id, active: e.active });
    });

    return { items, recipes, weeklyPlan };
  }

  async function refetchAll() {
    if (!sb || !listaId) return;
    try {
      const state = await fetchListaState();
      lastSyncedItems = clone(state.items);
      lastSyncedRecipeSig = new Map(state.recipes.map((r) => [r.id, recipeSignature(r)]));
      lastSyncedPlanFlat = new Map(flattenPlan(state.weeklyPlan).map((e) => [e.id, JSON.stringify(e)]));
      cb.onRemoteData && cb.onRemoteData(state);
    } catch (err) {
      fail(err);
    }
  }

  function debouncedRefetch() {
    clearTimeout(refetchTimer);
    refetchTimer = setTimeout(refetchAll, 300);
  }

  function subscribeRealtime() {
    unsubscribeRealtime();
    const filter = `lista_id=eq.${listaId}`;
    channel = sb.channel(`lista-${listaId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_items', filter }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_recetas', filter }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_weekly_plan_entries', filter }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_receta_ingredientes' }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_receta_subrecetas' }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_receta_pasos' }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_paso_ingredientes' }, debouncedRefetch)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'ls_miembros', filter }, () => {
        refreshListaInfo();
        cb.onMembersChange && getMembers().then(cb.onMembersChange);
      })
      .subscribe();
  }

  function unsubscribeRealtime() {
    if (channel) { sb.removeChannel(channel); channel = null; }
    clearTimeout(refetchTimer);
  }

  // ---- Push local -> remoto ----

  function clone(x) { return JSON.parse(JSON.stringify(x)); }

  function recipeSignature(r) {
    return JSON.stringify({
      name: r.name,
      ingredients: r.ingredients || [],
      subRecipeIds: r.subRecipeIds || [],
      instructionBlocks: r.instructionBlocks || [],
    });
  }

  function flattenPlan(weeklyPlan) {
    const out = [];
    Object.keys(weeklyPlan || {}).forEach((dayKey) => {
      (weeklyPlan[dayKey] || []).forEach((e) => {
        out.push({ id: e.id, dayKey, recipeId: e.recipeId, active: !!e.active });
      });
    });
    return out;
  }

  let pushItemsTimer = null;
  function pushItems(items) {
    lastItemsArg = items;
    if (!sb || !listaId) return;
    clearTimeout(pushItemsTimer);
    pushItemsTimer = setTimeout(() => doPushItems(items), 400);
  }

  async function doPushItems(items) {
    const lastById = new Map((lastSyncedItems || []).map((i) => [i.id, i]));
    const currentIds = new Set(items.map((i) => i.id));
    const toDelete = [...lastById.keys()].filter((id) => !currentIds.has(id));
    const toUpsert = items.filter((i) => JSON.stringify(i) !== JSON.stringify(lastById.get(i.id)));

    if (!toDelete.length && !toUpsert.length) return;
    try {
      if (toDelete.length) {
        const { error } = await sb.from('ls_items').delete().in('id', toDelete);
        if (error) throw error;
      }
      if (toUpsert.length) {
        const nowIso = new Date().toISOString();
        const rows = toUpsert.map((i) => ({
          id: i.id,
          lista_id: listaId,
          text: i.text,
          checked: !!i.checked,
          category: i.category,
          agregado_por: currentUser ? currentUser.id : null,
          updated_at: nowIso,
        }));
        const { error } = await sb.from('ls_items').upsert(rows);
        if (error) throw error;
      }
      lastSyncedItems = clone(items);
    } catch (err) {
      fail(err);
    }
  }

  let pushRecipesTimer = null;
  function pushRecipesAndPlan(recipes, weeklyPlan) {
    lastRecipesArg = recipes;
    lastPlanArg = weeklyPlan;
    if (!sb || !listaId) return;
    clearTimeout(pushRecipesTimer);
    pushRecipesTimer = setTimeout(() => doPushRecipesAndPlan(recipes, weeklyPlan), 300);
  }

  async function doPushRecipesAndPlan(recipes, weeklyPlan) {
    try {
      const prevSig = lastSyncedRecipeSig || new Map();
      const currentIds = new Set(recipes.map((r) => r.id));
      const toDeleteRecipes = [...prevSig.keys()].filter((id) => !currentIds.has(id));
      const changedRecipes = recipes.filter((r) => prevSig.get(r.id) !== recipeSignature(r));

      for (const r of changedRecipes) {
        const payload = {
          nombre: r.name,
          ingredientes: (r.ingredients || []).map((i) => ({ id: i.id, text: i.text, category: i.category })),
          subRecetaIds: r.subRecipeIds || [],
          pasos: (r.instructionBlocks || []).map((b) => ({
            id: b.id,
            stepNumber: b.stepNumber,
            timeValue: b.timeValue,
            timeUnit: b.timeUnit,
            actions: b.actions || [],
            items: (b.items || []).map((it) => ({
              ingredientId: it.ingredientId,
              quantityAmount: it.quantityAmount,
              quantityUnit: it.quantityUnit,
            })),
          })),
        };
        const { error } = await sb.rpc('replace_receta', {
          p_receta_id: r.id,
          p_lista_id: listaId,
          p_payload: payload,
        });
        if (error) throw error;
      }
      if (toDeleteRecipes.length) {
        const { error } = await sb.from('ls_recetas').delete().in('id', toDeleteRecipes);
        if (error) throw error;
      }
      lastSyncedRecipeSig = new Map(recipes.map((r) => [r.id, recipeSignature(r)]));

      const prevPlan = lastSyncedPlanFlat || new Map();
      const flat = flattenPlan(weeklyPlan);
      const currentEntryIds = new Set(flat.map((e) => e.id));
      const toDeleteEntries = [...prevPlan.keys()].filter((id) => !currentEntryIds.has(id));
      const changedEntries = flat.filter((e) => prevPlan.get(e.id) !== JSON.stringify(e));

      if (toDeleteEntries.length) {
        const { error } = await sb.from('ls_weekly_plan_entries').delete().in('id', toDeleteEntries);
        if (error) throw error;
      }
      if (changedEntries.length) {
        const nowIso = new Date().toISOString();
        const rows = changedEntries.map((e) => ({
          id: e.id,
          lista_id: listaId,
          day_key: e.dayKey,
          receta_id: e.recipeId,
          active: e.active,
          updated_at: nowIso,
        }));
        const { error } = await sb.from('ls_weekly_plan_entries').upsert(rows);
        if (error) throw error;
      }
      lastSyncedPlanFlat = new Map(flat.map((e) => [e.id, JSON.stringify(e)]));
    } catch (err) {
      fail(err);
    }
  }

  function retryPending() {
    if (lastItemsArg) pushItems(lastItemsArg);
    if (lastRecipesArg) pushRecipesAndPlan(lastRecipesArg, lastPlanArg || {});
  }

  // ---- Migración de datos locales existentes a una lista recién vinculada ----

  const ID_RE_VALID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  function isValidUuid(id) { return typeof id === 'string' && ID_RE_VALID.test(id); }

  // Los ids viejos (uid() pre-sync) no son UUIDs válidos y no entran en las
  // columnas `uuid` de Postgres. Se regeneran acá, una sola vez, remapeando
  // todas las referencias cruzadas (subRecipeIds, ingredientId, recipeId) —
  // mismo criterio que ya usa importRecipesFromPayload() en index.html.
  function normalizeIds(items, recipes, weeklyPlan) {
    const remap = new Map();
    const fresh = (oldId) => {
      if (!remap.has(oldId)) remap.set(oldId, crypto.randomUUID());
      return remap.get(oldId);
    };

    items.forEach((it) => { if (!isValidUuid(it.id)) it.id = fresh(it.id); });

    recipes.forEach((r) => {
      if (!isValidUuid(r.id)) r.id = fresh(r.id);
      (r.ingredients || []).forEach((ing) => { if (!isValidUuid(ing.id)) ing.id = fresh(ing.id); });
      (r.instructionBlocks || []).forEach((b) => { if (!isValidUuid(b.id)) b.id = fresh(b.id); });
    });
    recipes.forEach((r) => {
      r.subRecipeIds = (r.subRecipeIds || []).map((id) => remap.get(id) || id);
      (r.instructionBlocks || []).forEach((b) => {
        (b.items || []).forEach((it) => { it.ingredientId = remap.get(it.ingredientId) || it.ingredientId; });
      });
    });
    Object.values(weeklyPlan || {}).forEach((entries) => {
      (entries || []).forEach((e) => {
        if (!isValidUuid(e.id)) e.id = fresh(e.id);
        e.recipeId = remap.get(e.recipeId) || e.recipeId;
      });
    });
  }

  async function hasRemoteData() {
    if (!sb || !listaId) return false;
    const [itemsRes, recetasRes] = await Promise.all([
      sb.from('ls_items').select('id', { count: 'exact', head: true }).eq('lista_id', listaId),
      sb.from('ls_recetas').select('id', { count: 'exact', head: true }).eq('lista_id', listaId),
    ]);
    return (itemsRes.count || 0) > 0 || (recetasRes.count || 0) > 0;
  }

  // Muta items/recipes/weeklyPlan in-place (normaliza ids) y sube todo.
  // index.html debe llamar a sus propios save()/saveRecipesData()/
  // saveWeeklyPlan() después de esto para persistir los ids corregidos.
  async function uploadLocalData(items, recipes, weeklyPlan) {
    normalizeIds(items, recipes, weeklyPlan);
    lastSyncedItems = [];
    lastSyncedRecipeSig = new Map();
    lastSyncedPlanFlat = new Map();
    await doPushItems(items);
    await doPushRecipesAndPlan(recipes, weeklyPlan);
  }

  // ---- Init ----

  function init(callbacks) {
    cb = callbacks || {};
    if (!isConfigured()) return;
    sb = window.supabase.createClient(window.SUPABASE_CONFIG.url, window.SUPABASE_CONFIG.anonKey);

    const handleSession = (session) => {
      currentUser = session ? session.user : null;
      cb.onAuthChange && cb.onAuthChange(currentUser);
      if (currentUser && !listaId) {
        const stored = getStoredListaId();
        if (stored) {
          linkLista(stored).catch(fail);
        } else {
          findMyListaId().then((id) => { if (id) linkLista(id).catch(fail); }, fail);
        }
      }
    };

    sb.auth.onAuthStateChange((_event, session) => handleSession(session));
    sb.auth.getSession().then(({ data }) => handleSession(data.session));

    window.addEventListener('online', retryPending);
  }

  return {
    isConfigured,
    init,
    sendOtp,
    verifyOtp,
    signOut,
    getUser,
    getListaId,
    getListaNombre,
    getShareLink,
    getMembers,
    createLista,
    joinLista,
    leaveLista,
    pendingJoinCodeFromUrl,
    pushItems,
    pushRecipesAndPlan,
    hasRemoteData,
    uploadLocalData,
    pullNow,
  };
})();
