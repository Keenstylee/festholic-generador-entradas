const EVENT_FIELDS = [
  "id", "name", "event_date", "venue", "status", "image_url",
  "messages_json", "flyer_object_key", "flyer_file_name", "flyer_file_type",
  "flyer_file_size", "created_at", "updated_at", "deleted_at", "owner_id",
];

const TICKET_FIELDS = [
  "id", "event_id", "internal_code", "format", "zone", "base_price",
  "sale_price", "status", "payment_status", "payment_method", "buyer_name",
  "buyer_phone", "buyer_email", "buyer_document", "external_operation_id", "notes", "code_value", "object_key",
  "file_name", "file_type", "file_size", "created_at", "updated_at",
  "deleted_at", "shared_at", "checked_in_at", "source_platform", "owner_id",
];

const CLIENT_FIELDS = [
  "id", "phone", "name", "document", "event_id", "stage", "tags_json", "notes",
  "interactions_json", "last_contact_at", "created_at", "updated_at",
  "owner_id",
];

const EVENT_STATUSES = new Set(["active", "archived", "cancelled"]);
const TICKET_STATUSES = new Set(["available", "reserved", "sold", "delivered", "cancelled"]);
const PAYMENT_STATUSES = new Set(["pending", "partial", "paid", "refunded"]);
const FORMATS = new Set(["pdf", "image", "code", "list"]);
const CLIENT_STAGES = new Set(["new", "info", "pending", "paid", "delivery", "delivered", "inactive"]);
const SESSION_COOKIE = "iampromote_session";
const GOOGLE_OAUTH_COOKIE = "festholic_google_oauth";
const GOOGLE_OAUTH_MAX_AGE = 60 * 10;
const SESSION_MAX_AGE = 60 * 60 * 24 * 30;
const OWNER_USER_ID = "owner-keenscy";
// Cloudflare Workers Web Crypto admite hasta 100 000 iteraciones PBKDF2.
const PASSWORD_ITERATIONS = 100000;
const EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24;
const EMAIL_RESEND_COOLDOWN = 60;
const PASSWORD_RESET_MAX_AGE = 60 * 30;
const EMAIL_CHANGE_MAX_AGE = 60 * 60;
const EXPERIENCES = new Set(["promoter", "attendee", "media"]);
const WORKSPACE_MAX_BYTES = 1024 * 1024;
const USER_FILE_MAX_BYTES = 20 * 1024 * 1024;
const QR_IMAGE_MAX_BYTES = 12 * 1024 * 1024;
const qrValidationWindows = new Map();

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.hostname.toLowerCase() === "www.festholic.com") {
      url.hostname = "festholic.com";
      return Response.redirect(url.toString(), 308);
    }

    if (url.pathname === "/" && (request.method === "GET" || request.method === "HEAD")) {
      url.pathname = "/experiencia";
      return Response.redirect(url.toString(), 302);
    }

    const cors = corsHeaders(request, env);
    if (url.pathname === "/api/integrations/livefest/review-history" && request.method === "GET") {
      try { return await handleLiveFestReviewHistoryExport(request, env); }
      catch (error) { return json({ error: "No se pudo consultar el historial de Festholic", diagnostic: {
        code: /no such table: outbound_livefest_emails/i.test(String(error?.message || ""))
          ? "MISSING_OUTBOUND_EMAIL_TABLE" : "FESTHOLIC_HISTORY_READ_FAILED",
      } }, 503); }
    }

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (url.pathname === "/api/health") {
      return json({ ok: true, service: "iampromote-api" }, 200, cors);
    }

    if (url.pathname === "/api/whatsapp/webhook") {
      return handleWhatsAppWebhook(request, env, url);
    }

    if (url.pathname === "/api/auth/google" && request.method === "GET") {
      return handleGoogleStart(request, env, url);
    }

    if (url.pathname === "/api/auth/google/callback" && request.method === "GET") {
      return handleGoogleCallback(request, env, url);
    }

    if (url.pathname === "/api/auth/login" && request.method === "POST") {
      return handleLogin(request, env, cors);
    }

    if (url.pathname === "/api/auth/register" && request.method === "POST") {
      return handleRegister(request, env, cors);
    }

    if (url.pathname === "/api/auth/resend-verification" && request.method === "POST") {
      return handleResendVerification(request, env, cors);
    }

    if (url.pathname === "/api/auth/forgot-password" && request.method === "POST") {
      return handleForgotPassword(request, env, cors);
    }

    if (url.pathname === "/api/auth/reset-password" && request.method === "POST") {
      return handleResetPassword(request, env, cors);
    }

    if (url.pathname === "/api/auth/verify" && request.method === "GET") {
      return handleVerifyEmail(request, env, url);
    }

    if (url.pathname === "/api/auth/verify-email-change" && request.method === "GET") {
      return handleVerifyEmailChange(request, env, url);
    }

    if (url.pathname === "/api/auth/logout" && request.method === "POST") {
      return json({ ok: true }, 200, { ...cors, "Set-Cookie": clearSessionCookie() });
    }

    if (url.pathname === "/api/auth/session" && request.method === "GET") {
      const auth = await getAuthContext(request, env);
      return auth
        ? json({ authenticated: true, user: publicUser(auth) }, 200, cors)
        : json({ authenticated: false }, 401, cors);
    }

    if (url.pathname === "/api/digitalizer/verify" && request.method === "POST") {
      return handleDigitalizerVerify(request, env, cors);
    }

    if (url.pathname === "/api/digitalizer/generation" && request.method === "POST") {
      return handleDigitalizerGeneration(request, env, cors);
    }

    const auth = await getAuthContext(request, env);
    if (!auth) {
      return json({ error: "No autorizado" }, 401, cors);
    }

    try {
      const response = await route(request, env, url, auth);
      Object.entries(cors).forEach(([key, value]) => response.headers.set(key, value));
      return response;
    } catch (error) {
      console.error(error);
      return json({ error: "Error interno" }, 500, cors);
    }
  },
};

function liveFestEmailBridgeEnabled(env) {
  return String(env.LIVEFEST_EMAIL_BRIDGE_ENABLED || '').toLowerCase() === 'true';
}
function liveFestBridgeFailure(error, env) {
  return {
    error: "No se pudo consultar el puente de correo de Live Fest",
    diagnostic: {
      code: error?.bridgeCode || "LIVEFEST_BRIDGE_REQUEST_FAILED",
      httpStatus: error?.bridgeStatus || null,
      transport: env.LIVEFEST_SERVICE?.fetch ? "service_binding" : "public_fetch",
    },
  };
}
async function liveFestEmailBridgeFetch(env, path, body) {
  function fail(code, status) {
    return Object.assign(new Error(code), { bridgeCode: code, bridgeStatus: status || null });
  }
  if (!env.LIVEFEST_FESTHOLIC_SYNC_TOKEN) throw fail("LIVEFEST_SYNC_TOKEN_MISSING");
  const root = String(env.LIVEFEST_API_URL || 'https://frosty-math-d40e.keenscy10.workers.dev').replace(/\/+$/, '');
  let response;
  try {
    const request = new Request(`${root}/api/integrations/festholic/${path}`, {
      method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(25000),
      headers: { 'X-Livefest-Sync-Token': env.LIVEFEST_FESTHOLIC_SYNC_TOKEN, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    response = env.LIVEFEST_SERVICE?.fetch
      ? await env.LIVEFEST_SERVICE.fetch(request)
      : await fetch(request);
  } catch (error) {
    const code = /1042/.test(String(error?.message || "")) ? "CLOUDFLARE_WORKER_FETCH_1042"
      : ["AbortError", "TimeoutError"].includes(error?.name) ? "LIVEFEST_BRIDGE_TIMEOUT" : "LIVEFEST_BRIDGE_REQUEST_FAILED";
    throw fail(code);
  }
  try { await response.clone().json(); }
  catch { throw fail("LIVEFEST_NON_JSON_RESPONSE", response.status); }
  return response;
}
async function handleLiveFestReviewHistoryExport(request, env) {
  const supplied = request.headers.get('X-Livefest-Sync-Token') || '';
  if (!env.LIVEFEST_FESTHOLIC_SYNC_TOKEN || !supplied) return json({ error: 'No autorizado' }, 403);
  const [actual, expected] = await Promise.all([sha256Base64Url(supplied),sha256Base64Url(env.LIVEFEST_FESTHOLIC_SYNC_TOKEN)]);
  let difference = 0;
  for (let i=0;i<expected.length;i++) difference |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  if (difference) return json({ error: 'No autorizado' }, 403);
  if (!liveFestEmailBridgeEnabled(env)) return json({ error: 'Activa LIVEFEST_EMAIL_BRIDGE_ENABLED en Festholic' }, 503);
  const after = new URL(request.url).searchParams.get('after') || '';
  if (after.length > 200) return json({ error: 'Cursor inválido' }, 400);
  const result = await env.DB.prepare(`SELECT id,recipient_email,state,created_at,sent_at FROM outbound_livefest_emails
    WHERE owner_id = ? AND purpose = 'review' AND state IN ('sent','sending','uncertain') AND id > ? ORDER BY id LIMIT 101`)
    .bind(OWNER_USER_ID,after).all();
  const rows = result.results || [];
  return json({ emails: rows.slice(0,100), next: rows.length > 100 ? rows[99].id : null });
}

function digitalizerExpiry(value) {
  if (value === null || value === undefined) return null;
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  return amount < 1e12 ? amount * 1000 : amount;
}
async function digitalizerAccessForUser(env, userId) {
  const user = await env.DB.prepare(`SELECT u.id,u.email,u.name,u.status,u.session_version,
      a.status AS access_status,a.expires_at AS access_expires_at
    FROM users u LEFT JOIN digitalizer_access a ON a.user_id = u.id WHERE u.id = ?`)
    .bind(userId).first();
  const expiresAt = digitalizerExpiry(user?.access_expires_at);
  const allowed = Boolean(user && user.status === "active" && user.access_status === "active"
    && (expiresAt === null || expiresAt > Date.now()));
  return { allowed, user, expiresAt };
}
async function digitalizerIdentity(env, token) {
  if (!env.SESSION_SECRET || typeof token !== "string" || token.length > 4096
      || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) return null;
  const claim = await verifyDigitalizerToken(token, env.SESSION_SECRET);
  if (!claim || typeof claim.jti !== "string") return null;
  const access = await digitalizerAccessForUser(env, claim.userId);
  if (!access.allowed || Number(access.user.session_version || 1) !== Number(claim.version || 1)) return null;
  const issued = await env.DB.prepare("SELECT id FROM digitalizer_tokens WHERE id = ? AND user_id = ? AND expires_at > ?")
    .bind(claim.jti, claim.userId, Date.now()).first();
  return issued ? { claim, ...access } : null;
}
async function handleDigitalizerVerify(request, env, cors) {
  const headers = { ...cors, "Cache-Control": "no-store" };
  if (!env.SESSION_SECRET) return json({ allowed: false, error: "La verificación del digitalizador no está configurada." }, 503, headers);
  try {
    const body = await readJson(request);
    const identity = await digitalizerIdentity(env, body.token);
    if (!identity) return json({ allowed: false, error: "Acceso no autorizado o vencido. Vuelve a abrir el digitalizador desde Festholic; si persiste, revisa su permiso en el admin." }, 403, headers);
    await env.DB.prepare("UPDATE digitalizer_tokens SET used_at = COALESCE(used_at, ?) WHERE id = ? AND user_id = ?")
      .bind(Date.now(), identity.claim.jti, identity.user.id).run();
    return json({ allowed: true, user: { email: identity.user.email, name: identity.user.name } }, 200, headers);
  } catch (error) {
    console.error(JSON.stringify({ event: "digitalizer_access_verification_failed", errorType: error?.name || "Error" }));
    return json({ allowed: false, error: "No se pudo verificar el permiso del digitalizador. Intenta nuevamente." }, 503, headers);
  }
}
async function issueDigitalizerAccessToken(env, auth) {
  if (!env.SESSION_SECRET) return json({ error: "El sistema de sesiones no está configurado" }, 503);
  const access = await digitalizerAccessForUser(env, auth.userId);
  if (!access.allowed) return json({ allowed: false, error: "Tu cuenta no tiene un permiso vigente para el digitalizador. Solicita la autorización al administrador." }, 403, { "Cache-Control": "no-store" });
  const id = crypto.randomUUID();
  const expiresAt = Math.min(Date.now() + 12 * 60 * 60 * 1000, access.expiresAt ?? Infinity);
  const token = await createDigitalizerToken({ ...auth, sessionVersion: access.user.session_version }, env.SESSION_SECRET, { id, expiresAt });
  await env.DB.prepare("INSERT INTO digitalizer_tokens (id,user_id,expires_at,created_at) VALUES (?,?,?,?)")
    .bind(id, auth.userId, expiresAt, Date.now()).run();
  const usage = await env.DB.prepare("SELECT COALESCE(SUM(entry_count), 0) AS total FROM digitalizer_generations WHERE user_id = ?")
    .bind(auth.userId).first();
  return json({ token, generatedCount: Number(usage?.total || 0) }, 200, { "Cache-Control": "no-store" });
}
async function updateDigitalizerAccess(request, env, auth, targetId) {
  // Explicit grant is required for every user, including administrators.
  if (auth.role !== "owner") return json({ error: "Acceso exclusivo para administradores" }, 403);
  const target = await env.DB.prepare("SELECT id FROM users WHERE id = ?").bind(targetId).first();
  if (!target) return json({ error: "Usuario no encontrado" }, 404);
  const body = await readJson(request);
  if (typeof body.allowed !== "boolean") return json({ error: "Selecciona si el acceso está autorizado" }, 400);
  const prior = await env.DB.prepare("SELECT expires_at FROM digitalizer_access WHERE user_id = ?").bind(targetId).first();
  const expiresAt = Object.prototype.hasOwnProperty.call(body, "expiresAt") ? body.expiresAt : prior?.expires_at ?? null;
  if (expiresAt !== null && (typeof expiresAt !== "number" || !Number.isSafeInteger(expiresAt)
      || (body.allowed && digitalizerExpiry(expiresAt) <= Date.now())))
    return json({ error: "La fecha de vencimiento debe ser futura o quedar vacía" }, 400);
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO digitalizer_access (user_id,status,expires_at,granted_by,created_at,updated_at)
      VALUES (?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status,expires_at=excluded.expires_at,
      granted_by=excluded.granted_by,updated_at=excluded.updated_at`)
      .bind(targetId, body.allowed ? "active" : "revoked", expiresAt, auth.userId, now, now),
    env.DB.prepare("UPDATE digitalizer_tokens SET expires_at = MIN(expires_at, ?) WHERE user_id = ?").bind(now, targetId),
  ]);
  await writeSecurityAudit(request, env, { userId: targetId, actorUserId: auth.userId,
    action: "digitalizer_access_changed", detail: body.allowed ? "Acceso al digitalizador autorizado" : "Acceso al digitalizador revocado" });
  return json({ ok: true, allowed: body.allowed, expiresAt: digitalizerExpiry(expiresAt) });
}

async function handleDigitalizerGeneration(request, env, cors) {
  if (!env.SESSION_SECRET) return json({ error: "Seguimiento no configurado" }, 503, cors);
  try {
    const body = await readJson(request);
    const token = String(body.token || "");
    const eventId = String(body.eventId || "").trim();
    const mode = String(body.mode || "");
    const entryCount = Number(body.entryCount);
    if (!/^[0-9a-f-]{36}$/i.test(eventId)) return json({ error: "Identificador de descarga no valido" }, 400, cors);
    if (!Number.isInteger(entryCount) || entryCount < 1 || entryCount > 20) return json({ error: "Cantidad de entradas no valida" }, 400, cors);
    if (!new Set(["single", "batch"]).has(mode)) return json({ error: "Modo de descarga no valido" }, 400, cors);

    const identity = await digitalizerIdentity(env, token);
    if (!identity) return json({ error: "Acceso al digitalizador revocado, vencido o no autorizado" }, 403, cors);
    const claim = identity.claim;

    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO digitalizer_generations
       (id, user_id, entry_count, mode, created_at) VALUES (?, ?, ?, ?, ?)`
    ).bind(eventId, claim.userId, entryCount, mode, Date.now()).run();
    const usage = await env.DB.prepare(
      "SELECT COALESCE(SUM(entry_count), 0) AS total FROM digitalizer_generations WHERE user_id = ?"
    ).bind(claim.userId).first();
    return json({ ok: true, recorded: Number(result.meta?.changes || 0) > 0, generatedCount: Number(usage?.total || 0) }, 200, cors);
  } catch (error) {
    console.error(JSON.stringify({ message: "digitalizer_generation_failed", error: String(error) }));
    return json({ error: "No se pudo registrar la generación" }, 400, cors);
  }
}

// Live Fest checkout remains authoritative for payment; Festholic owns ticket inventory.
async function liveFestOrdersFromSource(env) {
  if (!env.LIVEFEST_FESTHOLIC_SYNC_TOKEN) throw Object.assign(new Error("Falta el secreto de sincronización"), { status: 503 });
  const endpoint = String(env.LIVEFEST_API_URL || "https://frosty-math-d40e.keenscy10.workers.dev").replace(/\/+$/, "");
  const orders = [];
  for (let offset = 0; offset <= 1800; offset += 200) {
    const response = await fetch(`${endpoint}/api/integrations/festholic/orders?offset=${offset}`, {
      headers: { "X-Livefest-Sync-Token": env.LIVEFEST_FESTHOLIC_SYNC_TOKEN },
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw Object.assign(new Error("Live Fest no respondió a la sincronización"), { status: response.status === 403 ? 503 : 502 });
    const data = await response.json();
    if (!Array.isArray(data.orders)) throw Object.assign(new Error("Respuesta de compras inválida"), { status: 502 });
    orders.push(...data.orders);
    if (!data.more) return orders;
  }
  throw Object.assign(new Error("Hay más de 2000 compras. Amplía la paginación antes de importar."), { status: 409 });
}

async function liveFestStableId(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].slice(0, 16).map(n => n.toString(16).padStart(2, "0")).join("");
}

function liveFestTicketItems(order) {
  const items = Array.isArray(order.items) ? order.items : [];
  const result = [];
  for (const [index, item] of items.entries()) {
    const quantity = Number(item.quantity || 0);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 20) continue;
    const title = String(item.type || item.title || "Entrada");
    const zone = title.startsWith(`${order.event_title} - `) ? title.slice(order.event_title.length + 3) : title;
    for (let number = 1; number <= quantity; number++) {
      result.push({ index, number, zone: zone.slice(0, 100), price: Number(item.unit_price || 0) });
    }
  }
  if (result.length > 20) throw Object.assign(new Error("Compra con más de 20 entradas"), { status: 409 });
  return result.length ? result : [{ index: 0, number: 1, zone: "Entrada", price: Number(order.amount || 0) }];
}

async function handleLiveFestOrders(request, env, auth) {
  if (auth.role !== "owner") return json({ error: "Solo el propietario puede importar compras" }, 403);
  try {
    const orders = await liveFestOrdersFromSource(env);
    if (request.method === "GET") {
      const existing = await env.DB.prepare("SELECT source, operation_id FROM livefest_imports WHERE owner_id = ?")
        .bind(auth.userId).all();
      const imported = new Set((existing.results || []).map(row => `${row.source}:${row.operation_id}`));
      return json({ orders: orders.map(order => ({ ...order, imported: imported.has(`${order.source}:${order.operation_id}`) })) });
    }
    const body = await readJson(request);
    const selected = Array.isArray(body.operations) ? body.operations : [];
    if (!selected.length || selected.length > 30 || selected.some(item => typeof item !== "string" || item.length > 150))
      return json({ error: "Selecciona entre 1 y 30 compras" }, 400);
    const wanted = new Set(selected);
    const chosen = orders.filter(order => wanted.has(`${order.source}:${order.operation_id}`));
    if (chosen.length !== wanted.size) return json({ error: "Una compra ya no aparece como aprobada. Actualiza la lista." }, 409);
    let imported = 0;
    let skipped = 0;
    for (const order of chosen) {
      const exists = await env.DB.prepare("SELECT 1 FROM livefest_imports WHERE owner_id = ? AND source = ? AND operation_id = ?")
        .bind(auth.userId, order.source, order.operation_id).first();
      if (exists) { skipped++; continue; }
      const title = String(order.event_title || "").trim().slice(0, 200);
      if (!title) throw Object.assign(new Error("Una compra no tiene evento"), { status: 409 });
      let event = await env.DB.prepare("SELECT id FROM events WHERE owner_id = ? AND name = ? AND deleted_at IS NULL LIMIT 1")
        .bind(auth.userId, title).first();
      const eventId = event?.id || `livefest-${await liveFestStableId(String(order.event_id || title))}`;
      const statements = [];
      if (!event) {
        const record = { ...normalizeEvent({
          id: eventId, name: title, date: order.event_date || null, venue: order.location || "",
          image: order.image || "",
        }), owner_id: auth.userId };
        statements.push(insertStatement(env.DB, "events", EVENT_FIELDS, record));
      }
      const items = liveFestTicketItems(order);
      for (const [position, item] of items.entries()) {
        const ticketId = `livefest-${await liveFestStableId(`${order.source}:${order.operation_id}:${position}`)}`;
        const record = { ...normalizeTicket({
          id: ticketId, eventId, internalCode: `${order.operation_id}-${position + 1}`,
          format: "pdf", zone: item.zone, basePrice: item.price, salePrice: item.price,
          status: "sold", paymentStatus: "paid", paymentMethod: order.method || "card",
          buyerName: order.buyer_name || "Cliente Live Fest", buyerPhone: order.buyer_phone || "",
          buyerEmail: order.buyer_email || "", externalOperationId: order.operation_id,
          sourcePlatform: "livefest", notes: `Compra importada de Live Fest · ${order.operation_id}`,
        }), owner_id: auth.userId };
        statements.push(insertStatement(env.DB, "tickets", TICKET_FIELDS, record));
      }
      statements.push(env.DB.prepare("INSERT INTO livefest_imports (owner_id,source,operation_id,event_id,imported_at) VALUES (?,?,?,?,?)")
        .bind(auth.userId, order.source, order.operation_id, eventId, Date.now()));
      await env.DB.batch(statements);
      imported++;
    }
    return json({ ok: true, imported, skipped });
  } catch (error) {
    console.error(JSON.stringify({ event: "livefest_import_failed", errorType: error?.name || "Error" }));
    return json({ error: error?.status ? error.message : "No se pudieron importar las compras" }, error?.status || 500);
  }
}

function liveFestBase64(bytes) {
  let output = "";
  for (let i = 0; i < bytes.length; i += 0x8000) output += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(output);
}

async function liveFestConfirmDelivery(env, auth, ticket) {
  const remaining = await env.DB.prepare(`SELECT COUNT(*) AS total FROM tickets
    WHERE owner_id = ? AND source_platform = 'livefest' AND external_operation_id = ?
      AND deleted_at IS NULL AND status <> 'delivered'`)
    .bind(auth.userId, ticket.external_operation_id).first();
  if (Number(remaining?.total || 0) !== 0) return { synced: false, pendingTickets: Number(remaining.total) };
  const imported = await env.DB.prepare("SELECT source FROM livefest_imports WHERE owner_id = ? AND operation_id = ? LIMIT 1")
    .bind(auth.userId, ticket.external_operation_id).first();
  if (!imported || !env.LIVEFEST_FESTHOLIC_SYNC_TOKEN) return { synced: false, warning: "Falta configurar la sincronización con Live Fest" };
  const endpoint = String(env.LIVEFEST_API_URL || "https://frosty-math-d40e.keenscy10.workers.dev").replace(/\/+$/, "");
  try {
    const response = await fetch(`${endpoint}/api/integrations/festholic/delivery`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Livefest-Sync-Token": env.LIVEFEST_FESTHOLIC_SYNC_TOKEN },
      body: JSON.stringify({ operationId: ticket.external_operation_id, source: imported.source, email: ticket.buyer_email }),
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(`Live Fest respondió ${response.status}`);
    return { synced: true };
  } catch (error) {
    console.error(JSON.stringify({ event: "livefest_delivery_sync_failed", operationId: ticket.external_operation_id, errorType: error?.name || "Error" }));
    return { synced: false, warning: "Correo enviado, pero Live Fest aún no muestra la entrega. Revisa la sincronización." };
  }
}

function outboundEmailSender(env) {
  const configured = String(env.EMAIL_FROM || "").trim();
  const address = configured.match(/<([^<>]+)>$/)?.[1] || configured;
  return isValidEmail(address) ? `Live Fest Perú <${address}>` : "";
}

async function sendFestholicOutboundEmail(env, record, payload) {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
      "Idempotency-Key": record.id,
    },
    signal: AbortSignal.timeout(10000),
    body: JSON.stringify(payload),
  });
  if (!response.ok) return { ok: false, uncertain: response.status >= 500, status: response.status };
  const data = await response.json();
  return { ok: true, providerId: String(data.id || "") };
}

async function handleFestholicOutboundEmail(request, env, auth, purpose) {
  if (auth.role !== "owner") return json({ error: "Solo el propietario puede enviar estos correos" }, 403);
  if (purpose === "review" && liveFestEmailBridgeEnabled(env)) {
    const body = await readJson(request);
    if (body.confirmedCustomer !== true || !isValidEmail(String(body.email || "").trim()) || String(body.email || "").length > 160)
      return json({ error: "Confirma el cliente e ingresa un correo válido" }, 400);
    try {
      const response = await liveFestEmailBridgeFetch(env, "review-invitations", body);
      return json(await response.json(), response.status);
    } catch (error) { return json(liveFestBridgeFailure(error, env), 502); }
  }
  if (!env.RESEND_API_KEY || !outboundEmailSender(env)) return json({ error: "Configura RESEND_API_KEY y EMAIL_FROM en Festholic" }, 503);
  if (purpose === "review" && String(env.LIVEFEST_REVIEWS_ENABLED || "").toLowerCase() !== "true")
    return json({ error: "Publica primero el formulario de reseñas de Live Fest" }, 503);
  const body = await readJson(request);
  const recipient = String(body.email || "").trim().toLowerCase();
  const name = String(body.name || "").trim().slice(0, 100);
  if (!isValidEmail(recipient) || recipient.length > 160) return json({ error: "Ingresa un correo válido" }, 400);
  if (purpose === "review" && body.confirmedCustomer !== true)
    return json({ error: "Confirma que esta persona recibió una compra o cortesía" }, 400);
  let ticket = null;
  let event = null;
  if (purpose === "courtesy") {
    ticket = await getOne(env.DB, "tickets", String(body.ticketId || ""), auth.userId);
    if (!ticket || ticket.deleted_at || ticket.source_platform === "livefest") return json({ error: "Entrada no disponible para cortesía" }, 404);
    if (!["available", "reserved"].includes(ticket.status) || ticket.payment_status === "paid" || Number(ticket.sale_price) > 0)
      return json({ error: "La entrada ya fue vendida o entregada" }, 409);
    if (!ticket.object_key || !["pdf", "image"].includes(ticket.format)) return json({ error: "Sube el archivo de la entrada antes de enviarla" }, 409);
    event = await getOne(env.DB, "events", ticket.event_id, auth.userId);
    if (!event) return json({ error: "Evento no encontrado" }, 404);
  }
  const targetKey = purpose === "courtesy" ? `courtesy:${ticket.id}` : `review:${recipient}`;
  const prior = await env.DB.prepare("SELECT state FROM outbound_livefest_emails WHERE owner_id = ? AND target_key = ? ORDER BY created_at DESC LIMIT 1")
    .bind(auth.userId, targetKey).first();
  if (prior?.state === "sent") return json({ error: purpose === "courtesy" ? "Esta entrada ya se envió como cortesía" : "Ya se envió una invitación a este correo" }, 409);
  if (["sending", "uncertain"].includes(prior?.state)) return json({ error: "Hay un envío sin confirmar. Revisa Resend antes de reintentar." }, 409);
  const record = { id: crypto.randomUUID(), ownerId: auth.userId, purpose, targetKey, ticketId: ticket?.id || null, recipient, sender: outboundEmailSender(env) };
  try {
    await env.DB.prepare(`INSERT INTO outbound_livefest_emails
      (id,owner_id,purpose,target_key,ticket_id,recipient_email,sender_email,state,created_at)
      VALUES (?,?,?,?,?,?,?,?,?)`).bind(record.id, record.ownerId, purpose, targetKey, record.ticketId, recipient, record.sender, "sending", Date.now()).run();
  } catch { return json({ error: "Ya hay un envío en curso" }, 409); }
  const safeName = escapeHtml(name || ticket?.buyer_name || "cliente");
  let payload;
  if (purpose === "courtesy") {
    const object = await env.FILES.get(ticket.object_key);
    if (!object || object.size > 5_000_000) {
      await env.DB.prepare("UPDATE outbound_livefest_emails SET state = 'failed' WHERE id = ?").bind(record.id).run();
      return json({ error: "Archivo no disponible o mayor a 5 MB" }, 409);
    }
    const fileBytes = new Uint8Array(await object.arrayBuffer());
    const fileContent = liveFestBase64(fileBytes);
    const eventName = escapeHtml(event.name);
    const cover = /^https:\/\//.test(event.image_url || "") ? `<img src="${escapeHtml(event.image_url)}" alt="Portada del evento" style="max-width:100%;max-height:170px;border-radius:10px">` : "";
    payload = {
      from: record.sender, to: [recipient], reply_to: "contacto@livefest.pe",
      subject: `Tu cortesía · ${event.name}`,
      html: `<!doctype html><html lang="es"><meta charset="utf-8"><body style="margin:0;background:#f3f2f6;font-family:Arial,sans-serif;color:#20212b"><div style="max-width:540px;margin:20px auto;background:#fff;border-radius:14px;overflow:hidden"><div style="background:#12141e;border-top:5px solid #ff3046;padding:12px 20px"><img src="https://livefest.pe/img/perfil/livefest-logo.png" alt="Live Fest Perú" width="72" height="72"></div><div style="background:#df3048;color:#fff;padding:18px 24px;font-size:22px;font-weight:bold">🎟 Tu cortesía está lista</div><div style="padding:20px 24px"><p>Hola ${safeName}, tu entrada de cortesía para <strong>${eventName}</strong> está adjunta.</p><p style="text-align:center">${cover}</p><p><strong>Zona:</strong> ${escapeHtml(ticket.zone)}<br><strong>Referencia:</strong> ${escapeHtml(ticket.internal_code)}</p><p>Presenta el archivo al ingresar. No compartas el código QR.</p><p>¿Necesitas ayuda? <a href="mailto:contacto@livefest.pe">contacto@livefest.pe</a></p></div></div></body></html>`,
      text: `Hola ${name || ticket.buyer_name || ""}. Tu entrada de cortesía para ${event.name} está adjunta. Zona: ${ticket.zone}. Referencia: ${ticket.internal_code}. No compartas el código QR. Ayuda: contacto@livefest.pe`,
      attachments: [{ filename: safeFileName(ticket.file_name || "entrada.pdf"), content: fileContent, content_type: ticket.file_type || "application/pdf" }],
    };
  } else {
    const reviewUrl = "https://livefest.pe/referencias#resenas";
    payload = {
      from: record.sender, to: [recipient], reply_to: "contacto@livefest.pe",
      subject: "¿Cómo fue tu experiencia con Live Fest Perú? 🎟️",
      html: `<!doctype html><html lang="es"><meta charset="utf-8"><body style="margin:0;background:#f3f2f6;font-family:Arial,sans-serif;color:#20212b"><div style="max-width:540px;margin:20px auto;background:#fff;border-radius:14px;overflow:hidden"><div style="background:#12141e;border-top:5px solid #ff3046;padding:12px 20px"><img src="https://livefest.pe/img/perfil/livefest-logo.png" alt="Live Fest Perú" width="72" height="72"></div><div style="padding:24px"><h1 style="font-size:23px">¿Cómo fue tu experiencia? 💬</h1><p>Hola ${safeName}, gracias por confiar en Live Fest Perú.</p><p>Si recibiste una entrada o compraste con nosotros, cuéntanos sinceramente cómo fue la experiencia. Tu opinión ayuda a otras personas y nos ayuda a mejorar.</p><p style="text-align:center;margin:28px 0"><a href="${reviewUrl}" style="background:#ff3046;color:#fff;text-decoration:none;border-radius:9px;padding:13px 22px;font-weight:bold">Dejar mi reseña →</a></p><p style="font-size:13px;color:#666">Si algo no salió bien, responde a este correo. No incluyas códigos QR ni datos de pago.</p><p style="font-size:12px;color:#777">Si prefieres no recibir más invitaciones, responde «No más invitaciones».</p></div></div></body></html>`,
      text: `Hola ${name || ""}. Si recibiste una entrada o compraste con Live Fest Perú, cuéntanos sinceramente tu experiencia: ${reviewUrl}\n\nSi algo no salió bien, responde a este correo. No incluyas códigos QR ni datos de pago. Para no recibir más invitaciones, responde «No más invitaciones».`,
    };
  }
  try {
    const sent = await sendFestholicOutboundEmail(env, record, payload);
    if (!sent.ok) {
      await env.DB.prepare("UPDATE outbound_livefest_emails SET state = ? WHERE id = ?").bind(sent.uncertain ? "uncertain" : "failed", record.id).run();
      return json({ error: sent.uncertain ? "Resultado incierto. Comprueba Resend antes de reintentar." : "Resend rechazó el correo." }, 502);
    }
    const now = Date.now();
    await env.DB.batch([
      env.DB.prepare("UPDATE outbound_livefest_emails SET state = 'sent', provider_id = ?, sent_at = ? WHERE id = ?").bind(sent.providerId, now, record.id),
      ...(ticket ? [env.DB.prepare(`UPDATE tickets SET status = 'delivered', buyer_email = ?, buyer_name = ?,
        sale_price = 0, payment_method = 'courtesy', notes = ?, updated_at = ? WHERE id = ? AND owner_id = ?`)
        .bind(recipient, name || ticket.buyer_name || "Invitado", [ticket.notes, "Cortesía enviada por correo"].filter(Boolean).join("\n"), now, ticket.id, auth.userId)] : []),
    ]);
    return json({ ok: true, sentTo: recipient, from: record.sender, providerId: sent.providerId, ticketId: ticket?.id || null });
  } catch (error) {
    await env.DB.prepare("UPDATE outbound_livefest_emails SET state = 'uncertain' WHERE id = ? AND state = 'sending'").bind(record.id).run().catch(() => {});
    console.error(JSON.stringify({ event: "festholic_outbound_email_failed", purpose, errorType: error?.name || "Error" }));
    return json({ error: "No se confirmó el envío. Revisa Resend antes de reintentar." }, 502);
  }
}

async function handleLiveFestTicketEmail(request, env, auth, ticketId) {
  if (auth.role !== "owner") return json({ error: "No autorizado" }, 403);
  const ticket = await getOne(env.DB, "tickets", ticketId, auth.userId);
  const isCode = ticket?.format === "code";
  const useBridge = isCode && liveFestEmailBridgeEnabled(env);
  const useZepto = useBridge || Boolean(env.ZEPTO_TOKEN);
  const resendSender = outboundEmailSender(env);
  if (!useZepto && (!env.RESEND_API_KEY || !resendSender))
    return json({ error: "Configura ZEPTO_TOKEN o RESEND_API_KEY y EMAIL_FROM en Festholic" }, 503);
  if (!ticket || ticket.deleted_at || (!isCode && ticket.source_platform !== "livefest")) return json({ error: "Entrada no encontrada" }, 404);
  if (ticket.status === "cancelled" || ticket.payment_status !== "paid") return json({ error: "Comprueba que la entrada esté activa y pagada antes de enviarla" }, 409);
  if (isCode ? !String(ticket.code_value || "").trim() : !ticket.object_key)
    return json({ error: "Guarda el código o sube el archivo antes de enviar" }, 409);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(ticket.buyer_email || "")) return json({ error: "Falta el correo del comprador" }, 400);
  const object = isCode ? null : await env.FILES.get(ticket.object_key);
  if (!isCode && (!object || object.size > 5_000_000)) return json({ error: "Archivo no disponible o demasiado grande" }, 409);
  const event = await getOne(env.DB, "events", ticket.event_id, auth.userId);
  let codeMessage = "";
  if (isCode) {
    const body = await readJson(request);
    codeMessage = typeof body.message === "string" ? body.message.trim() : "";
    if (!codeMessage || codeMessage.length > 20000 || !codeMessage.includes(ticket.code_value))
      return json({ error: "El mensaje debe incluir el código de canje y tener hasta 20000 caracteres" }, 400);
  }
  const unresolved = await env.DB.prepare("SELECT id FROM livefest_ticket_emails WHERE owner_id = ? AND ticket_id = ? AND state IN ('sending','uncertain') LIMIT 1")
    .bind(auth.userId, ticketId).first();
  if (unresolved) return json({ error: `Hay un envío pendiente de confirmar. Revisa ${useZepto ? "Zoho" : "Resend"} antes de repetirlo.` }, 409);
  const id = crypto.randomUUID();
  const at = Date.now();
  try {
    const claim = await env.DB.prepare(`INSERT INTO livefest_ticket_emails (id,owner_id,ticket_id,recipient_email,state,created_at)
      SELECT ?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM livefest_ticket_emails
        WHERE owner_id = ? AND ticket_id = ? AND state IN ('sending','uncertain'))`)
      .bind(id, auth.userId, ticketId, ticket.buyer_email, "sending", at, auth.userId, ticketId).run();
    if (!claim.meta?.changes) return json({ error: "Ya hay un envío en curso. Actualiza el historial." }, 409);
  } catch { return json({ error: "Ya hay un envío en curso. Actualiza el historial." }, 409); }
  const email = escapeHtml(ticket.buyer_email);
  const title = escapeHtml(event?.name || "tu evento");
  const name = escapeHtml(ticket.buyer_name || "");
  const reference = escapeHtml(ticket.external_operation_id || ticket.internal_code);
  const cover = event?.image_url && /^https:\/\//.test(event.image_url)
    ? `<img src="${escapeHtml(event.image_url)}" alt="Portada del evento" height="160" style="max-width:100%;height:160px;width:auto;border-radius:10px">` : "";
  const fileHtml = `<!doctype html><html lang="es"><meta charset="utf-8"><body style="margin:0;background:#f2f2f5;font-family:Arial,sans-serif;color:#222"><div style="max-width:520px;margin:20px auto;background:#fff;border-radius:14px;overflow:hidden"><div style="background:#12141e;padding:16px;color:#fff;border-top:5px solid #ff3046"><img src="https://livefest.pe/img/perfil/livefest-logo.png" alt="Live Fest Perú" width="76" height="76"></div><div style="background:#df3048;color:#fff;padding:18px;font-size:20px;font-weight:bold">🎟 Tu entrada ya está lista</div><div style="padding:22px"><p>Hola ${name}, tu entrada para <strong>${title}</strong> está adjunta.</p><p style="text-align:center">${cover}</p><p><strong>Zona:</strong> ${escapeHtml(ticket.zone)}<br><strong>N.º de operación:</strong> ${reference}</p><p>Presenta el archivo al ingresar y no compartas tu código QR.</p><p>¿Necesitas ayuda? <a href="mailto:contacto@livefest.pe">contacto@livefest.pe</a></p></div></div></body></html>`;
  const html = isCode
    ? `<!doctype html><html lang="es"><meta charset="utf-8"><body style="font-family:Arial,sans-serif;color:#222"><div style="max-width:560px;margin:20px auto;padding:24px;line-height:1.6;overflow-wrap:anywhere">${escapeHtml(codeMessage).replace(/https:\/\/www\.vastiontickets\.com\/canjear-codigo/g, '<a href="https://www.vastiontickets.com/canjear-codigo">https://www.vastiontickets.com/canjear-codigo</a>').replace(/\n/g, "<br>")}</div></body></html>`
    : fileHtml;
  const raw = String(env.ZEPTO_TOKEN || "").trim();
  const authHeader = /^Zoho-enczapikey\s/i.test(raw) ? raw : `Zoho-enczapikey ${raw}`;
  try {
    const attachment = isCode ? null : liveFestBase64(new Uint8Array(await object.arrayBuffer()));
    const textbody = isCode ? codeMessage : `Tu entrada está adjunta.\n${event?.name || ""}\nOperación: ${ticket.external_operation_id || ticket.internal_code}\nAyuda: contacto@livefest.pe`;
    const response = useBridge
      ? await liveFestEmailBridgeFetch(env, "code-email", { requestId: id, email: ticket.buyer_email, name: ticket.buyer_name, eventName: event?.name, message: codeMessage })
      : useZepto
      ? await fetch(env.ZEPTO_API_URL || "https://cpaas.zoho.com/v1.1/email", {
          method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: authHeader },
          signal: AbortSignal.timeout(10000),
          body: JSON.stringify({
            from: { address: "entradas@livefest.pe", name: "Live Fest Perú" },
            to: [{ email_address: { address: ticket.buyer_email, name: ticket.buyer_name || email } }],
            reply_to: [{ address: "contacto@livefest.pe", name: "Live Fest Perú" }],
            subject: `Tu entrada · ${event?.name || "Live Fest Perú"}`, htmlbody: html, textbody,
            ...(isCode ? {} : { attachments: [{ name: ticket.file_name, mime_type: ticket.file_type, content: attachment }] }),
          }),
        })
      : await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json", "Idempotency-Key": id },
          signal: AbortSignal.timeout(10000),
          body: JSON.stringify({
            from: resendSender, to: [ticket.buyer_email], reply_to: "contacto@livefest.pe",
            subject: `Tu entrada · ${event?.name || "Live Fest Perú"}`, html, text: textbody,
            ...(isCode ? {} : { attachments: [{ filename: safeFileName(ticket.file_name || "entrada.pdf"), content: attachment, content_type: ticket.file_type || "application/pdf" }] }),
          }),
        });
    const bridgeResult = useBridge ? await response.json().catch(() => ({})) : null;
    if (!response.ok || (useBridge && !bridgeResult?.ok)) {
      const uncertain = useBridge ? bridgeResult?.state !== "failed" : response.status >= 500;
      await env.DB.prepare("UPDATE livefest_ticket_emails SET state = ? WHERE id = ?").bind(uncertain ? "uncertain" : "failed", id).run();
      return json({ error: uncertain ? `Resultado incierto. Revisa ${useZepto ? "Zoho" : "Resend"} antes de reintentar.` : `${useZepto ? "ZeptoMail" : "Resend"} rechazó el correo.` }, 502);
    }
    const result = bridgeResult || await response.json().catch(() => ({}));
    const actualSender = useBridge ? result.from : useZepto ? "entradas@livefest.pe" : resendSender;
    await env.DB.batch([
      env.DB.prepare("UPDATE livefest_ticket_emails SET state = 'sent', sent_at = ?, provider_id = ?, sender_email = ? WHERE id = ?")
        .bind(Date.now(), String(result.id || result.data?.messageid || ""), actualSender, id),
      env.DB.prepare("UPDATE tickets SET status = 'delivered', updated_at = ? WHERE id = ? AND owner_id = ?").bind(Date.now(), ticketId, auth.userId),
    ]);
    const sync = ticket.source_platform === "livefest" ? await liveFestConfirmDelivery(env, auth, ticket) : {};
    return json({ ok: true, sentTo: ticket.buyer_email, emailId: id, provider: useZepto ? "Zoho" : "Resend", from: actualSender, ...sync });
  } catch (error) {
    await env.DB.prepare("UPDATE livefest_ticket_emails SET state = 'uncertain' WHERE id = ?").bind(id).run().catch(() => {});
    return json({ error: `No se confirmó el envío. Revisa ${useZepto ? "Zoho" : "Resend"} antes de reintentar.` }, 502);
  }
}

async function route(request, env, url, auth) {
  const { method } = request;
  const path = url.pathname;
  const ownerId = auth.userId;

  if (path === "/api/outbound-email/config" && method === "GET") {
    if (auth.role !== "owner") return json({ error: "No autorizado" }, 403);
    if (liveFestEmailBridgeEnabled(env)) {
      try {
        const response = await liveFestEmailBridgeFetch(env, "email-config");
        const data = await response.json();
        if (!response.ok) return json(data, response.status);
        return json({ ...data, reviewsEnabled: data.configured });
      } catch (error) { return json(liveFestBridgeFailure(error, env), 503); }
    }
    return json({ from: outboundEmailSender(env), configured: Boolean(env.RESEND_API_KEY && outboundEmailSender(env)), reviewsEnabled: String(env.LIVEFEST_REVIEWS_ENABLED || "").toLowerCase() === "true" });
  }
  if (path === "/api/outbound-email/history" && method === "GET") {
    if (auth.role !== "owner") return json({ error: "No autorizado" }, 403);
    const result = await env.DB.prepare(`SELECT purpose, ticket_id, recipient_email, sender_email, state, provider_id, created_at, sent_at
      FROM outbound_livefest_emails WHERE owner_id = ? ORDER BY created_at DESC LIMIT 50`).bind(ownerId).all();
    if (liveFestEmailBridgeEnabled(env)) {
      try {
        const response = await liveFestEmailBridgeFetch(env, "review-invitations");
        const data = await response.json();
        if (!response.ok) return json(data, response.status);
        const emails = [
          ...(result.results || []).filter(row => row.purpose !== "review"),
          ...(data.recent || []).map(row => ({ purpose: "review", recipient_email: row.email, state: row.state,
            created_at: Date.parse(row.created_at), sent_at: row.sent_at ? Date.parse(row.sent_at) : null })),
        ].sort((a,b) => (b.sent_at || b.created_at) - (a.sent_at || a.created_at));
        return json({ emails, sharedReviews: true });
      } catch (error) { return json(liveFestBridgeFailure(error, env), 503); }
    }
    return json({ emails: result.results || [] });
  }
  if (path === "/api/outbound-email/courtesy" && method === "POST") return handleFestholicOutboundEmail(request, env, auth, "courtesy");
  if (path === "/api/outbound-email/review" && method === "POST") return handleFestholicOutboundEmail(request, env, auth, "review");

  if (path === "/api/integrations/livefest/orders" && ["GET", "POST"].includes(method)) {
    return handleLiveFestOrders(request, env, auth);
  }
  const liveFestEmailMatch = path.match(/^\/api\/integrations\/livefest\/tickets\/([^/]+)\/email$/);
  if (liveFestEmailMatch && method === "POST") {
    return handleLiveFestTicketEmail(request, env, auth, decodeURIComponent(liveFestEmailMatch[1]));
  }
  if (liveFestEmailMatch && method === "GET") {
    if (auth.role !== "owner") return json({ error: "No autorizado" }, 403);
    const ticketId = decodeURIComponent(liveFestEmailMatch[1]);
    const ticket = await getOne(env.DB, "tickets", ticketId, auth.userId);
    if (!ticket || ticket.deleted_at || (ticket.source_platform !== "livefest" && ticket.format !== "code")) return json({ error: "Entrada no encontrada" }, 404);
    const result = await env.DB.prepare("SELECT id,recipient_email,state,created_at,sent_at FROM livefest_ticket_emails WHERE owner_id = ? AND ticket_id = ? ORDER BY created_at DESC LIMIT 20")
      .bind(auth.userId, ticketId).all();
    const sync = ticket.source_platform === "livefest" && ticket.status === "delivered" ? await liveFestConfirmDelivery(env, auth, ticket) : null;
    return json({ emails: result.results || [], sync });
  }

  if (method === "GET" && path === "/api/digitalizer/token") {
    return issueDigitalizerAccessToken(env, auth);
  }

  if (method === "POST" && path === "/api/auth/change-password") {
    if (!env.SESSION_SECRET) return json({ error: "El sistema de sesiones aun no esta configurado" }, 503);
    const body = await readJson(request);
    const currentPassword = String(body.currentPassword || "");
    const newPassword = String(body.newPassword || "");
    if (newPassword.length < 10 || newPassword.length > 128) {
      return json({ error: "La nueva contraseña debe tener entre 10 y 128 caracteres" }, 400);
    }
    const user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(ownerId).first();
    if (!user || !(await verifyPassword(currentPassword, user.password_salt, user.password_hash))) {
      await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "password_change_failed", detail: "Contraseña actual incorrecta" });
      return json({ error: "La contraseña actual no es correcta" }, 403);
    }
    if (await verifyPassword(newPassword, user.password_salt, user.password_hash)) {
      return json({ error: "La nueva contraseña debe ser diferente" }, 400);
    }
    const credentials = await hashPassword(newPassword);
    const nextVersion = Number(user.session_version || 1) + 1;
    const now = Date.now();
    await env.DB.prepare("UPDATE users SET password_hash = ?, password_salt = ?, session_version = ?, updated_at = ? WHERE id = ?")
      .bind(credentials.hash, credentials.salt, nextVersion, now, ownerId).run();
    const freshAuth = { ...auth, sessionVersion: nextVersion };
    const token = await createSessionToken(freshAuth, env.SESSION_SECRET);
    await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "password_changed", detail: "Contraseña actualizada y sesiones anteriores cerradas" });
    return json({ ok: true, message: "Contraseña actualizada" }, 200, { "Set-Cookie": sessionCookie(token) });
  }

  if (method === "POST" && path === "/api/auth/revoke-sessions") {
    if (!env.SESSION_SECRET) return json({ error: "El sistema de sesiones aun no esta configurado" }, 503);
    const nextVersion = Number(auth.sessionVersion || 1) + 1;
    await env.DB.prepare("UPDATE users SET session_version = ?, updated_at = ? WHERE id = ?")
      .bind(nextVersion, Date.now(), ownerId).run();
    const token = await createSessionToken({ ...auth, sessionVersion: nextVersion }, env.SESSION_SECRET);
    await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "sessions_revoked", detail: "Se cerraron las sesiones de otros dispositivos" });
    return json({ ok: true, message: "Las otras sesiones fueron cerradas" }, 200, { "Set-Cookie": sessionCookie(token) });
  }

  if (method === "GET" && path === "/api/auth/activity") {
    const result = await env.DB.prepare(
      `SELECT action, detail, user_agent, created_at
       FROM security_audit WHERE user_id = ? ORDER BY created_at DESC LIMIT 50`
    ).bind(ownerId).all();
    return json({ activity: result.results });
  }

  if (method === "POST" && path === "/api/auth/resend-email-change") {
    if (!(await consumeAuthAttempt(request, env, "email-change", 5, 60 * 60))) {
      return json({ error: "Demasiados reenvios. Intenta mas tarde." }, 429);
    }
    const user = await env.DB.prepare("SELECT id, name, email, pending_email FROM users WHERE id = ?").bind(ownerId).first();
    if (!user?.pending_email) return json({ error: "No tienes un cambio de correo pendiente" }, 400);
    const delivery = await createAndSendEmailChange(env, user, new URL(request.url).origin);
    return json({ ok: true, message: "Enlace de confirmación enviado", previewUrl: delivery.previewUrl || undefined });
  }

  if (method === "GET" && path === "/api/account/export") {
    const [user, workspaces, events, tickets, clients, activity] = await Promise.all([
      env.DB.prepare("SELECT id, email, name, role, status, experience, created_at, updated_at FROM users WHERE id = ?").bind(ownerId).first(),
      env.DB.prepare("SELECT experience, data_json, updated_at FROM user_workspaces WHERE user_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM events WHERE owner_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM tickets WHERE owner_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM clients WHERE owner_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM activity WHERE owner_id = ? ORDER BY created_at DESC LIMIT 1000").bind(ownerId).all(),
    ]);
    await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "data_exported", detail: "Copia de datos descargada" });
    return json({ exportedAt: new Date().toISOString(), user, workspaces: workspaces.results, events: events.results, tickets: tickets.results, clients: clients.results, activity: activity.results });
  }

  if (method === "POST" && path === "/api/account/deletion-request") {
    const body = await readJson(request);
    const reason = String(body.reason || "").trim().slice(0, 500);
    const now = Date.now();
    await env.DB.prepare(
      `INSERT INTO account_deletion_requests (id, user_id, reason, status, created_at, updated_at)
       VALUES (?, ?, ?, 'pending', ?, ?)
       ON CONFLICT(user_id) DO UPDATE SET reason = excluded.reason, status = 'pending', updated_at = excluded.updated_at`
    ).bind(crypto.randomUUID(), ownerId, reason, now, now).run();
    await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "deletion_requested", detail: "Solicitud de eliminación de cuenta registrada" });
    return json({ ok: true, message: "Solicitud de eliminación registrada" }, 201);
  }

  if (method === "POST" && path === "/api/support/request") {
    const body = await readJson(request);
    const subject = String(body.subject || "").trim().replace(/\s+/g, " ").slice(0, 120);
    const message = String(body.message || "").trim().slice(0, 2000);
    if (subject.length < 3 || message.length < 10) return json({ error: "Completa el asunto y el mensaje" }, 400);
    const now = Date.now();
    await env.DB.prepare(
      "INSERT INTO support_requests (id, user_id, subject, message, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'open', ?, ?)"
    ).bind(crypto.randomUUID(), ownerId, subject, message, now, now).run();
    return json({ ok: true, message: "Solicitud enviada" }, 201);
  }

  if (path.startsWith("/api/admin/")) {
    if (auth.role !== "owner") return json({ error: "Acceso exclusivo para administradores" }, 403);

    if (method === "GET" && path === "/api/admin/overview") {
      const [users, active, support, deletion, promoters, events, tickets, sold, checkins, digitalized] = await Promise.all([
        env.DB.prepare("SELECT COUNT(*) AS total FROM users").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM users WHERE status = 'active'").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM support_requests WHERE status = 'open'").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM account_deletion_requests WHERE status = 'pending'").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM users WHERE experience = 'promoter' AND status = 'active'").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM events WHERE status = 'active' AND deleted_at IS NULL").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM tickets WHERE deleted_at IS NULL").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM tickets WHERE status IN ('sold','delivered') AND deleted_at IS NULL").first(),
        env.DB.prepare("SELECT COUNT(*) AS total FROM tickets WHERE checked_in_at IS NOT NULL AND deleted_at IS NULL").first(),
        env.DB.prepare("SELECT COALESCE(SUM(entry_count), 0) AS total FROM digitalizer_generations").first(),
      ]);
      return json({ users: Number(users?.total || 0), active: Number(active?.total || 0), support: Number(support?.total || 0), deletion: Number(deletion?.total || 0), promoters: Number(promoters?.total || 0), events: Number(events?.total || 0), tickets: Number(tickets?.total || 0), sold: Number(sold?.total || 0), checkins: Number(checkins?.total || 0), digitalized: Number(digitalized?.total || 0) });
    }

    const digitalizerAccessMatch = path.match(/^\/api\/admin\/users\/([^/]+)\/digitalizer-access$/);
    if (digitalizerAccessMatch && method === "PATCH") {
      return updateDigitalizerAccess(request, env, auth, decodeURIComponent(digitalizerAccessMatch[1]));
    }

    if (method === "GET" && path === "/api/admin/users") {
      const query = String(url.searchParams.get("q") || "").trim().slice(0, 100);
      const pattern = `%${query}%`;
      const result = await env.DB.prepare(
        `SELECT u.id, u.email, u.name, u.role, u.status, u.experience, u.created_at, u.updated_at,
                (SELECT a.status FROM digitalizer_access a WHERE a.user_id = u.id) AS digitalizer_access_status,
                (SELECT a.expires_at FROM digitalizer_access a WHERE a.user_id = u.id) AS digitalizer_expires_at,
                (SELECT COUNT(*) FROM events e WHERE e.owner_id = u.id AND e.deleted_at IS NULL) AS event_count,
                (SELECT COUNT(*) FROM tickets t WHERE t.owner_id = u.id AND t.deleted_at IS NULL) AS ticket_count,
                (SELECT COUNT(*) FROM clients c WHERE c.owner_id = u.id) AS client_count,
                (SELECT COALESCE(SUM(g.entry_count), 0) FROM digitalizer_generations g WHERE g.user_id = u.id) AS digitalized_count,
                (SELECT COUNT(*) FROM user_files f WHERE f.user_id = u.id)
                  + (SELECT COUNT(*) FROM tickets t WHERE t.owner_id = u.id AND t.object_key IS NOT NULL AND t.deleted_at IS NULL)
                  + (SELECT COUNT(*) FROM events e WHERE e.owner_id = u.id AND e.flyer_object_key IS NOT NULL AND e.deleted_at IS NULL) AS file_count,
                (SELECT COALESCE(SUM(f.file_size), 0) FROM user_files f WHERE f.user_id = u.id)
                  + (SELECT COALESCE(SUM(t.file_size), 0) FROM tickets t WHERE t.owner_id = u.id AND t.object_key IS NOT NULL AND t.deleted_at IS NULL)
                  + (SELECT COALESCE(SUM(e.flyer_file_size), 0) FROM events e WHERE e.owner_id = u.id AND e.flyer_object_key IS NOT NULL AND e.deleted_at IS NULL) AS storage_bytes
         FROM users u
         WHERE (? = '' OR u.name LIKE ? OR u.email LIKE ?)
         ORDER BY u.created_at DESC LIMIT 200`
      ).bind(query, pattern, pattern).all();
      return json({ users: (result.results || []).map(user => ({ ...user,
        digitalizer_expires_at: digitalizerExpiry(user.digitalizer_expires_at),
        digitalizer_allowed: user.status === "active" && user.digitalizer_access_status === "active"
          && (user.digitalizer_expires_at === null || digitalizerExpiry(user.digitalizer_expires_at) > Date.now()),
      })) });
    }

    if (method === "GET" && path === "/api/admin/audit") {
      const result = await env.DB.prepare(
        `SELECT a.action, a.detail, a.user_agent, a.created_at,
                COALESCE(u.name, 'Cuenta eliminada') AS user_name,
                COALESCE(u.email, '') AS user_email,
                COALESCE(actor.name, 'Sistema') AS actor_name
         FROM security_audit a
         LEFT JOIN users u ON u.id = a.user_id
         LEFT JOIN users actor ON actor.id = a.actor_user_id
         ORDER BY a.created_at DESC LIMIT 200`
      ).all();
      return json({ audit: result.results });
    }

    const adminUserMatch = path.match(/^\/api\/admin\/users\/([^/]+)$/);
    if (method === "PATCH" && adminUserMatch) {
      const targetId = decodeURIComponent(adminUserMatch[1]);
      const body = await readJson(request);
      const status = String(body.status || "");
      const role = String(body.role || "");
      const experience = String(body.experience || "");
      if (!new Set(["active", "disabled"]).has(status) || !new Set(["owner", "promoter"]).has(role) || !EXPERIENCES.has(experience)) {
        return json({ error: "Datos de cuenta no validos" }, 400);
      }
      if (targetId === ownerId && (status !== "active" || role !== "owner")) {
        return json({ error: "No puedes bloquear ni quitar permisos a tu propia cuenta" }, 400);
      }
      await env.DB.prepare("UPDATE users SET status = ?, role = ?, experience = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?")
        .bind(status, role, experience, Date.now(), targetId).run();
      await writeSecurityAudit(request, env, { userId: targetId, actorUserId: ownerId, action: "account_permissions_changed", detail: `Estado: ${status}; rol: ${role}; experiencia: ${experience}` });
      return json({ ok: true });
    }

    if (method === "GET" && path === "/api/admin/requests") {
      const [support, deletion] = await Promise.all([
        env.DB.prepare(`SELECT r.*, u.name, u.email FROM support_requests r JOIN users u ON u.id = r.user_id ORDER BY r.created_at DESC LIMIT 100`).all(),
        env.DB.prepare(`SELECT r.*, u.name, u.email FROM account_deletion_requests r JOIN users u ON u.id = r.user_id ORDER BY r.created_at DESC LIMIT 100`).all(),
      ]);
      return json({ support: support.results, deletion: deletion.results });
    }

    const supportMatch = path.match(/^\/api\/admin\/support\/([^/]+)$/);
    if (method === "PATCH" && supportMatch) {
      const body = await readJson(request);
      const status = String(body.status || "");
      if (!new Set(["open", "resolved"]).has(status)) return json({ error: "Estado no valido" }, 400);
      await env.DB.prepare("UPDATE support_requests SET status = ?, updated_at = ? WHERE id = ?")
        .bind(status, Date.now(), decodeURIComponent(supportMatch[1])).run();
      return json({ ok: true });
    }

    const deletionMatch = path.match(/^\/api\/admin\/deletion-requests\/([^/]+)$/);
    if (method === "PATCH" && deletionMatch) {
      const body = await readJson(request);
      const status = String(body.status || "");
      if (!new Set(["pending", "cancelled"]).has(status)) return json({ error: "Estado no valido" }, 400);
      await env.DB.prepare("UPDATE account_deletion_requests SET status = ?, updated_at = ? WHERE id = ?")
        .bind(status, Date.now(), decodeURIComponent(deletionMatch[1])).run();
      return json({ ok: true });
    }
  }

  if (method === "PATCH" && path === "/api/auth/profile") {
    const body = await readJson(request);
    const hasExperience = body.experience !== undefined;
    const hasIdentity = body.name !== undefined || body.email !== undefined;
    if (!hasExperience && !hasIdentity) return json({ error: "No hay cambios para guardar" }, 400);
    let experience = auth.experience || "promoter";
    if (hasExperience) {
      experience = String(body.experience || "").trim().toLowerCase();
      if (!EXPERIENCES.has(experience)) return json({ error: "Experiencia no valida" }, 400);
    }
    const current = await env.DB.prepare("SELECT email, name, pending_email FROM users WHERE id = ?").bind(ownerId).first();
    if (!current) return json({ error: "Cuenta no encontrada" }, 404);
    const name = hasIdentity ? String(body.name ?? current.name).trim().replace(/\s+/g, " ") : current.name;
    const requestedEmail = hasIdentity ? String(body.email ?? current.email).trim().toLowerCase() : current.email;
    if (name.length < 2 || name.length > 80) return json({ error: "Ingresa un nombre valido" }, 400);
    if (!isValidEmail(requestedEmail) || requestedEmail.length > 160) return json({ error: "Ingresa un correo valido" }, 400);
    let pendingEmail = current.pending_email || "";
    if (requestedEmail === String(current.email).toLowerCase()) {
      pendingEmail = "";
    } else {
      const duplicate = await env.DB.prepare(
        "SELECT id FROM users WHERE id <> ? AND (email = ? COLLATE NOCASE OR pending_email = ? COLLATE NOCASE)"
      ).bind(ownerId, requestedEmail, requestedEmail).first();
      if (duplicate) return json({ error: "Ese correo ya pertenece a otra cuenta" }, 409);
      pendingEmail = requestedEmail;
    }
    if (pendingEmail && !emailVerificationEnabled(env) && String(env.DEV_EMAIL_PREVIEW || "").toLowerCase() !== "true") {
      return json({ error: "El servicio de correo aun no esta configurado" }, 503);
    }
    await env.DB.prepare("UPDATE users SET name = ?, pending_email = ?, experience = ?, updated_at = ? WHERE id = ?")
      .bind(name, pendingEmail || null, experience, Date.now(), ownerId).run();
    let delivery = {};
    if (pendingEmail && pendingEmail !== current.pending_email) {
      delivery = await createAndSendEmailChange(env, { id: ownerId, name, email: current.email, pending_email: pendingEmail }, new URL(request.url).origin);
    } else if (!pendingEmail) {
      await env.DB.prepare("DELETE FROM email_change_tokens WHERE user_id = ?").bind(ownerId).run();
    }
    await writeSecurityAudit(request, env, { userId: ownerId, actorUserId: ownerId, action: "profile_updated", detail: pendingEmail ? "Nombre actualizado; cambio de correo pendiente de confirmación" : "Información de cuenta actualizada" });
    const refreshedAuth = { ...auth, name, pendingEmail, email: current.email, experience };
    const refreshedToken = await createSessionToken(refreshedAuth, env.SESSION_SECRET);
    return json(
      { ok: true, user: publicUser(refreshedAuth), previewUrl: delivery.previewUrl || undefined },
      200,
      { "Set-Cookie": sessionCookie(refreshedToken) },
    );
  }

  const workspaceMatch = path.match(/^\/api\/workspaces\/(promoter|attendee|media)$/);
  if (workspaceMatch && method === "GET") {
    const experience = workspaceMatch[1];
    const record = await env.DB.prepare(
      "SELECT data_json, updated_at FROM user_workspaces WHERE user_id = ? AND experience = ?"
    ).bind(ownerId, experience).first();
    return json({ data: record ? JSON.parse(record.data_json || "{}") : null, updatedAt: record?.updated_at || null });
  }
  if (workspaceMatch && method === "PUT") {
    const experience = workspaceMatch[1];
    const body = await readJson(request);
    const serialized = JSON.stringify(body.data ?? {});
    if (new TextEncoder().encode(serialized).byteLength > WORKSPACE_MAX_BYTES) {
      return json({ error: "El espacio supera el limite permitido" }, 413);
    }
    const now = Date.now();
    await env.DB.prepare(
      `INSERT INTO user_workspaces (user_id, experience, data_json, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(user_id, experience) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at`
    ).bind(ownerId, experience, serialized, now).run();
    return json({ ok: true, updatedAt: now });
  }

  const userFileMatch = path.match(/^\/api\/user-files\/(attendee)\/([^/]+)$/);
  if (userFileMatch) {
    const [, scope, encodedId] = userFileMatch;
    const fileId = decodeURIComponent(encodedId).trim();
    if (!fileId || fileId.length > 160) return json({ error: "Identificador de archivo no valido" }, 400);
    const existing = await env.DB.prepare(
      "SELECT object_key, file_name, file_type, file_size, updated_at FROM user_files WHERE user_id = ? AND scope = ? AND file_id = ?"
    ).bind(ownerId, scope, fileId).first();

    if (method === "GET") {
      if (!existing) return json({ error: "Archivo no encontrado" }, 404);
      const object = await env.FILES.get(existing.object_key);
      if (!object) return json({ error: "Archivo no encontrado" }, 404);
      const headers = new Headers();
      headers.set("Content-Type", existing.file_type || "application/octet-stream");
      headers.set("Content-Disposition", `inline; filename*=UTF-8''${encodeURIComponent(existing.file_name || "entrada")}`);
      headers.set("Cache-Control", "private, no-store");
      headers.set("X-File-Name", encodeURIComponent(existing.file_name || "entrada"));
      return new Response(object.body, { headers });
    }

    if (method === "POST") {
      const length = Number(request.headers.get("Content-Length") || 0);
      const fileType = String(request.headers.get("Content-Type") || "application/octet-stream").toLowerCase();
      const allowedType = fileType === "application/pdf" || fileType.startsWith("image/");
      if (!allowedType) return json({ error: "Solo se permiten PDF o imagenes" }, 415);
      if (length > USER_FILE_MAX_BYTES) return json({ error: "El archivo supera 20 MB" }, 413);
      const fileName = decodeURIComponent(request.headers.get("X-File-Name") || "entrada").slice(0, 180);
      const objectKey = `users/${ownerId}/${scope}/${crypto.randomUUID()}`;
      await env.FILES.put(objectKey, request.body, { httpMetadata: { contentType: fileType } });
      const object = await env.FILES.head(objectKey);
      if (!object || object.size > USER_FILE_MAX_BYTES) {
        if (object) await env.FILES.delete(objectKey);
        return json({ error: "El archivo supera 20 MB" }, 413);
      }
      const now = Date.now();
      await env.DB.prepare(
        `INSERT INTO user_files (user_id, scope, file_id, object_key, file_name, file_type, file_size, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(user_id, scope, file_id) DO UPDATE SET object_key = excluded.object_key,
           file_name = excluded.file_name, file_type = excluded.file_type,
           file_size = excluded.file_size, updated_at = excluded.updated_at`
      ).bind(ownerId, scope, fileId, objectKey, fileName, fileType, object.size, now).run();
      if (existing?.object_key && existing.object_key !== objectKey) await env.FILES.delete(existing.object_key);
      return json({ ok: true, fileName, fileType, fileSize: object.size, updatedAt: now });
    }

    if (method === "DELETE") {
      if (existing?.object_key) await env.FILES.delete(existing.object_key);
      await env.DB.prepare("DELETE FROM user_files WHERE user_id = ? AND scope = ? AND file_id = ?")
        .bind(ownerId, scope, fileId).run();
      return json({ ok: true });
    }
  }

  if (method === "POST" && path === "/api/feedback") {
    const body = await readJson(request);
    const categories = new Set(["general", "events", "tickets", "clients", "mobile", "other"]);
    const category = String(body.category || "general");
    const rating = Number(body.rating || 0);
    const message = String(body.message || "").trim().replace(/\s+/g, " ");
    if (!categories.has(category)) return json({ error: "Categoría no valida" }, 400);
    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      return json({ error: "Selecciona una valoracion del 1 al 5" }, 400);
    }
    if (message.length < 10 || message.length > 1500) {
      return json({ error: "El comentario debe tener entre 10 y 1500 caracteres" }, 400);
    }
    const record = {
      id: crypto.randomUUID(), userId: auth.userId, email: auth.email, name: auth.name,
      category, rating, message, createdAt: Date.now(),
    };
    await env.DB.prepare(
      `INSERT INTO promoter_feedback
       (id, user_id, user_email, user_name, category, rating, message, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      record.id, record.userId, record.email, record.name, record.category,
      record.rating, record.message, record.createdAt,
    ).run();
    return json(record, 201);
  }

  if (method === "GET" && path === "/api/feedback") {
    if (auth.role !== "owner") return json({ error: "No autorizado" }, 403);
    const result = await env.DB.prepare(
      `SELECT id, user_id, user_email, user_name, category, rating, message, created_at
       FROM promoter_feedback ORDER BY created_at DESC LIMIT 200`
    ).all();
    return json(result.results.map((item) => ({
      id: item.id, userId: item.user_id, email: item.user_email, name: item.user_name,
      category: item.category, rating: item.rating, message: item.message, createdAt: item.created_at,
    })));
  }

  if (method === "GET" && path === "/api/bootstrap") {
    const [events, tickets, clients, activity] = await Promise.all([
      env.DB.prepare("SELECT * FROM events WHERE owner_id = ? ORDER BY event_date ASC, created_at DESC").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM tickets WHERE owner_id = ? ORDER BY created_at DESC").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM clients WHERE owner_id = ? ORDER BY updated_at DESC").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM activity WHERE owner_id = ? ORDER BY created_at DESC LIMIT 100").bind(ownerId).all(),
    ]);
    return json({
      events: events.results.map(eventToClient),
      tickets: tickets.results.map(ticketToClient),
      clients: clients.results.map(clientToClient),
      activity: activity.results.map(activityToClient),
    });
  }

  // Guardar una reserva y solo sus entradas en una transacción, sin reescribir todo el inventario.
  if (method === "POST" && path === "/api/reservations/save") {
    if (Number(request.headers.get("Content-Length") || 0) > 512 * 1024) return json({ error: "La reserva es demasiado grande" }, 413);
    const body = await readJson(request);
    if (!body.client || !Array.isArray(body.tickets) || body.tickets.length > 500) {
      return json({ error: "Datos de reserva inválidos" }, 400);
    }
    const clientId = String(body.client.id || "");
    if (!clientId || body.tickets.some((ticket) => !ticket?.id)
      || new Set(body.tickets.map((ticket) => ticket.id)).size !== body.tickets.length) {
      return json({ error: "Identificadores de reserva inválidos" }, 400);
    }
    const storedClient = await getOne(env.DB, "clients", clientId, ownerId);
    const client = { ...mergeStoredClients([normalizeClient(body.client, storedClient || {})], storedClient ? [storedClient] : [])[0], owner_id: ownerId };
    if (client.event_id && !(await getOne(env.DB, "events", client.event_id, ownerId))) {
      return json({ error: "El evento no pertenece a tu cuenta" }, 403);
    }
    const storedTickets = await Promise.all(body.tickets.map((ticket) => getOne(env.DB, "tickets", ticket.id, ownerId)));
    const tickets = body.tickets.map((item, index) => {
      const stored = storedTickets[index];
      const record = normalizeTicket(stored ? { ...item,
        objectKey: stored.object_key, fileName: stored.file_name,
        fileType: stored.file_type, fileSize: stored.file_size,
      } : item, stored || {});
      return { ...record, owner_id: ownerId };
    });
    if (tickets.some((ticket) => ticket.event_id !== client.event_id)) {
      return json({ error: "Todas las entradas deben pertenecer al evento de la reserva" }, 400);
    }
    const activity = body.activity ? { ...normalizeActivity(body.activity), owner_id: ownerId } : null;
    const statements = [
      storedClient
        ? updateStatement(env.DB, "clients", CLIENT_FIELDS, client, ownerId)
        : insertStatement(env.DB, "clients", CLIENT_FIELDS, client),
      ...tickets.map((ticket, index) => storedTickets[index]
        ? updateStatement(env.DB, "tickets", TICKET_FIELDS, ticket, ownerId)
        : insertStatement(env.DB, "tickets", TICKET_FIELDS, ticket)),
    ];
    if (activity) statements.push(env.DB.prepare(
      "INSERT INTO activity (id, type, title, detail, entity_type, entity_id, created_at, owner_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(activity.id, activity.type, activity.title, activity.detail, activity.entity_type, activity.entity_id, activity.created_at, ownerId));
    try {
      await env.DB.batch(statements);
    } catch (error) {
      console.error("POST /api/reservations/save failed", error?.stack || error);
      return json({ error: "No se pudo guardar la reserva" }, 500);
    }
    return json({ ok: true, client: clientToClient(client), tickets: tickets.map(ticketToClient) });
  }

  if (method === "GET" && path === "/api/whatsapp/status") {
    const result = await env.DB.prepare(
      "SELECT COUNT(*) AS total, MAX(sent_at) AS last_message_at FROM whatsapp_messages WHERE owner_id = ?"
    ).bind(ownerId).first();
    return json({
      webhookUrl: `${url.origin}/api/whatsapp/webhook`,
      verifyTokenConfigured: Boolean(env.WHATSAPP_VERIFY_TOKEN),
      appSecretConfigured: Boolean(env.WHATSAPP_APP_SECRET),
      messagesReceived: Number(result?.total || 0),
      lastMessageAt: result?.last_message_at || null,
    });
  }

  if (method === "DELETE" && path === "/api/trash") {
    const deletedTickets = await env.DB.prepare(
      "SELECT id, object_key FROM tickets WHERE owner_id = ? AND deleted_at IS NOT NULL"
    ).bind(ownerId).all();
    const deletedEvents = await env.DB.prepare(
      "SELECT flyer_object_key FROM events WHERE owner_id = ? AND deleted_at IS NOT NULL"
    ).bind(ownerId).all();
    const objectKeys = [
      ...deletedTickets.results.map((ticket) => ticket.object_key),
      ...deletedEvents.results.map((event) => event.flyer_object_key),
    ]
      .filter(Boolean);
    if (objectKeys.length) await env.FILES.delete(objectKeys);

    const [ticketsResult, eventsResult] = await env.DB.batch([
      env.DB.prepare("DELETE FROM tickets WHERE owner_id = ? AND deleted_at IS NOT NULL").bind(ownerId),
      env.DB.prepare("DELETE FROM events WHERE owner_id = ? AND deleted_at IS NOT NULL").bind(ownerId),
    ]);
    return json({
      ok: true,
      tickets: ticketsResult.meta.changes || 0,
      events: eventsResult.meta.changes || 0,
      files: objectKeys.length,
    });
  }

  if (method === "PUT" && path === "/api/state") {
    const body = await readJson(request);
    const [storedEvents, storedTickets, storedClients] = await Promise.all([
      env.DB.prepare("SELECT * FROM events WHERE owner_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM tickets WHERE owner_id = ?").bind(ownerId).all(),
      env.DB.prepare("SELECT * FROM clients WHERE owner_id = ?").bind(ownerId).all(),
    ]);
    const eventFiles = new Map(storedEvents.results.map((record) => [record.id, record]));
    const ticketFiles = new Map(storedTickets.results.map((record) => [record.id, record]));
    const events = Array.isArray(body.events) ? body.events.map((item) => {
      const stored = eventFiles.get(item.id);
      const record = normalizeEvent(item);
      return {
        ...record,
        flyer_object_key: stored?.flyer_object_key || null,
        flyer_file_name: stored?.flyer_file_name || "",
        flyer_file_type: stored?.flyer_file_type || "",
        flyer_file_size: stored?.flyer_file_size || 0,
        owner_id: ownerId,
      };
    }) : [];
    const tickets = Array.isArray(body.tickets) ? body.tickets.map((item) => {
      const stored = ticketFiles.get(item.id);
      const record = normalizeTicket(item);
      return {
        ...record,
        object_key: stored?.object_key || null,
        file_name: stored?.file_name || "",
        file_type: stored?.file_type || "",
        file_size: stored?.file_size || 0,
        owner_id: ownerId,
      };
    }) : [];
    const ownedEventIds = new Set(events.map((event) => event.id));
    if (tickets.some((ticket) => !ownedEventIds.has(ticket.event_id))) {
      return json({ error: "Una entrada referencia un evento que no pertenece a tu cuenta" }, 400);
    }
    const submittedClients = Array.isArray(body.clients) ? body.clients.map((item) => ({ ...normalizeClient(item), owner_id: ownerId })) : [];
    if (submittedClients.some((client) => client.event_id && !ownedEventIds.has(client.event_id))) {
      return json({ error: "Un cliente referencia un evento que no pertenece a tu cuenta" }, 400);
    }
    const clients = mergeStoredClients(submittedClients, storedClients.results)
      .map((client) => ({ ...client, owner_id: ownerId }));
    const activity = Array.isArray(body.activity) ? body.activity.slice(0, 100).map((item) => ({ ...normalizeActivity(item), owner_id: ownerId })) : [];

    // Merge by ID. Replacing all parent rows here can cascade into dependent
    // records and break otherwise valid links to uploaded files in R2.
    const statements = [
      ...events.map((record) => upsertStatement(env.DB, "events", EVENT_FIELDS, record)),
      ...clients.map((record) => upsertStatement(env.DB, "clients", CLIENT_FIELDS, record)),
      ...tickets.map((record) => upsertStatement(env.DB, "tickets", TICKET_FIELDS, record)),
      ...activity.map((record) => upsertStatement(env.DB, "activity", [
        "id", "type", "title", "detail", "entity_type", "entity_id", "created_at", "owner_id",
      ], record)),
    ];
    try {
      await env.DB.batch(statements);
    } catch (error) {
      console.error("PUT /api/state failed", error?.stack || error);
      return json({
        error: "Error interno",
        detail: String(error?.message || error || "No se pudo guardar el estado en la base de datos"),
      }, 500);
    }
    return json({ ok: true, events: events.length, tickets: tickets.length, clients: clients.length });
  }

  if (method === "POST" && path === "/api/events") {
    const body = await readJson(request);
    const record = { ...normalizeEvent(body), owner_id: ownerId };
    await insertRecord(env.DB, "events", EVENT_FIELDS, record);
    await logActivity(env.DB, ownerId, "event", "Evento creado", record.name, "event", record.id);
    return json(eventToClient(record), 201);
  }

  const eventMatch = path.match(/^\/api\/events\/([^/]+)$/);
  if (eventMatch && method === "GET") {
    const id = decodeURIComponent(eventMatch[1]);
    const current = await getOne(env.DB, "events", id, ownerId);
    if (!current || current.deleted_at) return json({ error: "Evento no encontrado" }, 404);
    return json(eventToClient(current));
  }

  if (eventMatch && method === "PATCH") {
    const id = decodeURIComponent(eventMatch[1]);
    const current = await getOne(env.DB, "events", id, ownerId);
    if (!current) return json({ error: "Evento no encontrado" }, 404);
    const record = { ...normalizeEvent({ ...current, ...(await readJson(request)), id }, current), owner_id: ownerId };
    await updateRecord(env.DB, "events", EVENT_FIELDS, record, ownerId);
    await logActivity(env.DB, ownerId, "event", "Evento actualizado", record.name, "event", id);
    return json(eventToClient(record));
  }

  if (eventMatch && method === "DELETE") {
    const id = decodeURIComponent(eventMatch[1]);
    const now = Date.now();
    const result = await env.DB.prepare(
      "UPDATE events SET deleted_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?"
    ).bind(now, now, id, ownerId).run();
    if (!result.meta.changes) return json({ error: "Evento no encontrado" }, 404);
    await env.DB.prepare(
      "UPDATE tickets SET deleted_at = COALESCE(deleted_at, ?), updated_at = ? WHERE event_id = ? AND owner_id = ?"
    ).bind(now, now, id, ownerId).run();
    await logActivity(env.DB, ownerId, "delete", "Evento enviado a papelera", id, "event", id);
    return json({ ok: true });
  }

  if (method === "POST" && path === "/api/event-flyer") {
    const eventId = request.headers.get("X-Event-Id");
    const encodedFileName = request.headers.get("X-File-Name") || "flyer";
    const fileName = decodeURIComponent(encodedFileName);
    const fileType = request.headers.get("Content-Type") || "application/octet-stream";
    const fileSize = Number(request.headers.get("Content-Length") || 0);
    if (!eventId) return json({ error: "Falta X-Event-Id" }, 400);
    if (fileType !== "application/pdf" && !fileType.startsWith("image/")) {
      return json({ error: "El flyer debe ser una imagen o PDF" }, 400);
    }
    if (fileSize > 12 * 1024 * 1024) {
      return json({ error: "El flyer no debe superar 12 MB" }, 413);
    }
    const event = await getOne(env.DB, "events", eventId, ownerId);
    if (!event) return json({ error: "Evento no encontrado" }, 404);
    const previousObjectKey = event.flyer_object_key;

    const objectKey = `users/${ownerId}/event-flyers/${event.id}/${Date.now()}-${safeFileName(fileName)}`;
    await env.FILES.put(objectKey, request.body, {
      httpMetadata: { contentType: fileType },
      customMetadata: { eventId: event.id, ownerId },
    });
    const object = await env.FILES.head(objectKey);
    await env.DB.prepare(
      `UPDATE events
       SET image_url = '', flyer_object_key = ?, flyer_file_name = ?, flyer_file_type = ?,
           flyer_file_size = ?, updated_at = ?
       WHERE id = ? AND owner_id = ?`
    ).bind(objectKey, fileName, fileType, object?.size || 0, Date.now(), event.id, ownerId).run();
    if (previousObjectKey && previousObjectKey !== objectKey) await env.FILES.delete(previousObjectKey);
    return json({
      objectKey,
      fileName,
      fileType,
      fileSize: object?.size || 0,
    }, 201);
  }

  const eventFlyerMatch = path.match(/^\/api\/event-flyer\/([^/]+)$/);
  if (eventFlyerMatch && method === "GET") {
    const eventId = decodeURIComponent(eventFlyerMatch[1]);
    const event = await getOne(env.DB, "events", eventId, ownerId);
    if (!event?.flyer_object_key) return json({ error: "Flyer no encontrado" }, 404);
    const object = await env.FILES.get(event.flyer_object_key);
    if (!object) return json({ error: "Flyer no encontrado" }, 404);
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    const disposition = event.flyer_file_type.startsWith("image/") ? "inline" : "attachment";
    headers.set("Content-Disposition", `${disposition}; filename="${asciiFileName(event.flyer_file_name)}"`);
    headers.set("Cache-Control", "private, no-store");
    return new Response(object.body, { headers });
  }

  if (eventFlyerMatch && method === "DELETE") {
    const eventId = decodeURIComponent(eventFlyerMatch[1]);
    const event = await getOne(env.DB, "events", eventId, ownerId);
    if (!event) return json({ error: "Evento no encontrado" }, 404);
    if (event.flyer_object_key) await env.FILES.delete(event.flyer_object_key);
    await env.DB.prepare(
      `UPDATE events
       SET flyer_object_key = NULL, flyer_file_name = '', flyer_file_type = '',
           flyer_file_size = 0, updated_at = ?
       WHERE id = ? AND owner_id = ?`
    ).bind(Date.now(), eventId, ownerId).run();
    return json({ ok: true });
  }

  if (method === "POST" && path === "/api/promoter/qr/reconstruct") {
    if (!env.QR_RECONSTRUCTOR_URL || !env.QR_RECONSTRUCTOR_TOKEN) {
      return json({ error: "La reconstrucción avanzada aún no está configurada" }, 503);
    }
    if (!allowQrRequest(`reconstruct:${ownerId}`, 12, 60_000)) {
      return json({ error: "Demasiados intentos. Espera un minuto antes de continuar" }, 429);
    }
    const length = Number(request.headers.get("Content-Length") || 0);
    if (length > QR_IMAGE_MAX_BYTES) return json({ error: "La imagen supera el límite de 12 MB" }, 413);
    const contentType = request.headers.get("Content-Type") || "application/octet-stream";
    if (!contentType.startsWith("image/")) return json({ error: "Selecciona una imagen válida" }, 415);
    const serviceUrl = `${String(env.QR_RECONSTRUCTOR_URL).replace(/\/+$/, "")}/reconstruct`;
    const upstream = await fetch(serviceUrl, {
      method: "POST",
      headers: {
        "Content-Type": contentType,
        "X-Service-Token": env.QR_RECONSTRUCTOR_TOKEN,
      },
      body: request.body,
    });
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  }

  if (method === "POST" && path === "/api/promoter/tickets/validate-qr") {
    if (!allowQrRequest(`validate:${ownerId}`, 40, 60_000)) {
      return json({ error: "Demasiados intentos. Espera un minuto antes de continuar" }, 429);
    }
    const body = await readJson(request);
    const qrData = String(body.qr_data || "").trim();
    const eventId = String(body.event_id || "").trim();
    if (!qrData || qrData.length > 4096 || !eventId) return json({ error: "QR y evento son obligatorios" }, 400);
    if (!(await getOne(env.DB, "events", eventId, ownerId))) return json({ error: "El evento no pertenece a tu cuenta" }, 403);
    const ticket = await findTicketByQr(env.DB, ownerId, eventId, qrData);
    if (!ticket) return json({ status: "not_found" }, 404);
    if (ticket.checked_in_at) {
      return json({ status: "already_used", checkedInAt: ticket.checked_in_at, ticket: ticketToClient(ticket) });
    }
    return json({ status: "valid", ticket: ticketToClient(ticket) });
  }

  if (method === "POST" && path === "/api/promoter/tickets/checkin") {
    if (!allowQrRequest(`checkin:${ownerId}`, 40, 60_000)) {
      return json({ error: "Demasiados intentos. Espera un minuto antes de continuar" }, 429);
    }
    const body = await readJson(request);
    const qrData = String(body.qr_data || "").trim();
    const eventId = String(body.event_id || "").trim();
    if (!qrData || !eventId) return json({ error: "QR y evento son obligatorios" }, 400);
    const ticket = await findTicketByQr(env.DB, ownerId, eventId, qrData);
    if (!ticket) return json({ status: "not_found" }, 404);
    if (ticket.checked_in_at) return json({ status: "already_used", checkedInAt: ticket.checked_in_at, ticket: ticketToClient(ticket) });
    const checkedInAt = Date.now();
    const update = await env.DB.prepare(
      "UPDATE tickets SET checked_in_at = ?, updated_at = ? WHERE id = ? AND owner_id = ? AND checked_in_at IS NULL"
    ).bind(checkedInAt, checkedInAt, ticket.id, ownerId).run();
    if (!update.meta.changes) return json({ status: "already_used" }, 409);
    await logActivity(env.DB, ownerId, "checkin", "Check-in registrado", ticket.internal_code, "ticket", ticket.id);
    return json({ status: "checked_in", checkedInAt, ticket: ticketToClient({ ...ticket, checked_in_at: checkedInAt }) });
  }

  if (method === "POST" && path === "/api/tickets") {
    const body = await readJson(request);
    const records = Array.isArray(body) ? body : [body];
    if (!records.length || records.length > 250) {
      return json({ error: "La carga debe contener entre 1 y 250 entradas" }, 400);
    }
    const normalized = records.map((record) => ({ ...normalizeTicket(record), owner_id: ownerId }));
    const eventIds = [...new Set(normalized.map((record) => record.event_id))];
    const ownedEvents = await Promise.all(eventIds.map((id) => getOne(env.DB, "events", id, ownerId)));
    if (ownedEvents.some((event) => !event)) return json({ error: "Uno de los eventos no pertenece a tu cuenta" }, 403);
    await env.DB.batch(normalized.map((record) => insertStatement(env.DB, "tickets", TICKET_FIELDS, record)));
    await logActivity(
      env.DB,
      ownerId,
      "ticket",
      "Entradas agregadas",
      `${normalized.length} entrada(s) registradas`,
      "event",
      normalized[0].event_id,
    );
    return json(normalized.map(ticketToClient), 201);
  }

  if (method === "PATCH" && path === "/api/tickets/bulk") {
    const body = await readJson(request);
    if (!Array.isArray(body) || !body.length || body.length > 250) {
      return json({ error: "La actualización debe incluir entre 1 y 250 entradas" }, 400);
    }
    const ids = body.map((item) => String(item?.id || ""));
    if (ids.some((id) => !id) || new Set(ids).size !== ids.length) {
      return json({ error: "Identificadores de entrada inválidos" }, 400);
    }
    const currentRecords = await Promise.all(ids.map((id) => getOne(env.DB, "tickets", id, ownerId)));
    if (currentRecords.some((record) => !record)) return json({ error: "Una entrada ya no existe" }, 404);
    const normalized = body.map((item, index) => {
      const current = currentRecords[index];
      return { ...normalizeTicket({ ...current, ...item, id: current.id }, current), owner_id: ownerId };
    });
    const eventIds = [...new Set(normalized.map((record) => record.event_id))];
    const ownedEvents = await Promise.all(eventIds.map((id) => getOne(env.DB, "events", id, ownerId)));
    if (ownedEvents.some((record) => !record)) return json({ error: "Una entrada pertenece a otro evento" }, 403);
    const activity = envlessActivityStatement(
      env.DB,
      ownerId,
      "ticket",
      "Entradas actualizadas en lote",
      `${normalized.length} entradas`,
      "event",
      normalized[0].event_id,
    );
    try {
      await env.DB.batch([
        ...normalized.map((record) => updateStatement(env.DB, "tickets", TICKET_FIELDS, record, ownerId)),
        activity,
      ]);
    } catch (error) {
      console.error("PATCH /api/tickets/bulk failed", error?.stack || error);
      return json({ error: "No se pudieron guardar las entradas" }, 500);
    }
    return json(normalized.map(ticketToClient));
  }

  const ticketMatch = path.match(/^\/api\/tickets\/([^/]+)$/);
  if (ticketMatch && method === "PATCH") {
    const id = decodeURIComponent(ticketMatch[1]);
    const current = await getOne(env.DB, "tickets", id, ownerId);
    if (!current) return json({ error: "Entrada no encontrada" }, 404);
    const record = { ...normalizeTicket({ ...current, ...(await readJson(request)), id }, current), owner_id: ownerId };
    if (!(await getOne(env.DB, "events", record.event_id, ownerId))) {
      return json({ error: "El evento no pertenece a tu cuenta" }, 403);
    }
    await updateRecord(env.DB, "tickets", TICKET_FIELDS, record, ownerId);
    await logActivity(env.DB, ownerId, "ticket", "Entrada actualizada", record.internal_code, "ticket", id);
    return json(ticketToClient(record));
  }

  if (ticketMatch && method === "DELETE") {
    const id = decodeURIComponent(ticketMatch[1]);
    const now = Date.now();
    const result = await env.DB.prepare(
      "UPDATE tickets SET deleted_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?"
    ).bind(now, now, id, ownerId).run();
    if (!result.meta.changes) return json({ error: "Entrada no encontrada" }, 404);
    await logActivity(env.DB, ownerId, "delete", "Entrada enviada a papelera", id, "ticket", id);
    return json({ ok: true });
  }

  const restoreMatch = path.match(/^\/api\/(events|tickets)\/([^/]+)\/restore$/);
  if (restoreMatch && method === "POST") {
    const table = restoreMatch[1];
    const id = decodeURIComponent(restoreMatch[2]);
    const now = Date.now();
    const current = await getOne(env.DB, table, id, ownerId);
    if (!current) return json({ error: "Elemento no encontrado" }, 404);
    const result = await env.DB.prepare(
      `UPDATE ${table} SET deleted_at = NULL, updated_at = ? WHERE id = ? AND owner_id = ?`
    ).bind(now, id, ownerId).run();
    if (!result.meta.changes) return json({ error: "Elemento no encontrado" }, 404);
    if (table === "events") {
      await env.DB.prepare(
        "UPDATE tickets SET deleted_at = NULL, updated_at = ? WHERE event_id = ? AND deleted_at = ? AND owner_id = ?"
      ).bind(now, id, current.deleted_at, ownerId).run();
    }
    await logActivity(env.DB, ownerId, "restore", "Elemento restaurado", id, table.slice(0, -1), id);
    return json({ ok: true });
  }

  if (method === "POST" && path === "/api/files") {
    const ticketId = request.headers.get("X-Ticket-Id");
    const encodedFileName = request.headers.get("X-File-Name") || "entrada";
    const fileName = decodeURIComponent(encodedFileName);
    const fileType = request.headers.get("Content-Type") || "application/octet-stream";
    if (!ticketId) return json({ error: "Falta X-Ticket-Id" }, 400);
    const ticket = await getOne(env.DB, "tickets", ticketId, ownerId);
    if (!ticket) return json({ error: "Entrada no encontrada" }, 404);

    const objectKey = `users/${ownerId}/tickets/${ticket.event_id}/${ticket.id}/${safeFileName(fileName)}`;
    await env.FILES.put(objectKey, request.body, {
      httpMetadata: { contentType: fileType },
      customMetadata: { ticketId: ticket.id, ownerId },
    });
    const object = await env.FILES.head(objectKey);
    const now = Date.now();
    await env.DB.prepare(
      `UPDATE tickets
       SET object_key = ?, file_name = ?, file_type = ?, file_size = ?, updated_at = ?
       WHERE id = ? AND owner_id = ?`
    ).bind(objectKey, fileName, fileType, object?.size || 0, now, ticket.id, ownerId).run();
    return json({ objectKey, fileName, fileType, fileSize: object?.size || 0 }, 201);
  }

  const fileMatch = path.match(/^\/api\/files\/([^/]+)$/);
  if (fileMatch && method === "GET") {
    const ticketId = decodeURIComponent(fileMatch[1]);
    const ticket = await getOne(env.DB, "tickets", ticketId, ownerId);
    if (!ticket?.object_key) return json({ error: "Archivo no encontrado" }, 404);
    const object = await env.FILES.get(ticket.object_key);
    if (!object) return json({ error: "Archivo no encontrado" }, 404);
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    headers.set("Content-Disposition", `attachment; filename="${asciiFileName(ticket.file_name)}"`);
    headers.set("Cache-Control", "private, no-store");
    return new Response(object.body, { headers });
  }

  if (fileMatch && method === "DELETE") {
    const ticketId = decodeURIComponent(fileMatch[1]);
    const ticket = await getOne(env.DB, "tickets", ticketId, ownerId);
    if (!ticket?.object_key) return json({ error: "Archivo no encontrado" }, 404);
    await env.FILES.delete(ticket.object_key);
    await env.DB.prepare(
      `UPDATE tickets
       SET object_key = NULL, file_name = '', file_type = '', file_size = 0, updated_at = ?
       WHERE id = ? AND owner_id = ?`
    ).bind(Date.now(), ticketId, ownerId).run();
    return json({ ok: true });
  }

  return json({ error: "Ruta no encontrada" }, 404);
}

async function handleWhatsAppWebhook(request, env, url) {
  if (request.method === "GET") {
    const mode = url.searchParams.get("hub.mode");
    const token = url.searchParams.get("hub.verify_token");
    const challenge = url.searchParams.get("hub.challenge");
    if (
      mode === "subscribe"
      && env.WHATSAPP_VERIFY_TOKEN
      && token === env.WHATSAPP_VERIFY_TOKEN
      && challenge
    ) {
      return new Response(challenge, {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    return json({ error: "Verificacion de webhook rechazada" }, 403);
  }

  if (request.method !== "POST") {
    return json({ error: "Metodo no permitido" }, 405);
  }
  if (!env.WHATSAPP_APP_SECRET) {
    return json({ error: "WHATSAPP_APP_SECRET no configurado" }, 503);
  }

  const rawBody = await request.text();
  const signature = request.headers.get("X-Hub-Signature-256") || "";
  if (!(await verifyMetaSignature(rawBody, signature, env.WHATSAPP_APP_SECRET))) {
    return json({ error: "Firma de Meta invalida" }, 401);
  }

  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return json({ error: "JSON invalido" }, 400);
  }
  if (payload.object !== "whatsapp_business_account") {
    return json({ received: true, processed: 0 });
  }

  let processed = 0;
  for (const entry of payload.entry || []) {
    for (const change of entry.changes || []) {
      if (change.field !== "messages") continue;
      const value = change.value || {};
      const names = new Map(
        (value.contacts || []).map((contact) => [
          normalizeWhatsAppPhone(contact.wa_id),
          String(contact.profile?.name || "").trim(),
        ])
      );
      for (const message of value.messages || []) {
        const phone = normalizeWhatsAppPhone(message.from);
        if (!phone || !message.id) continue;
        const inserted = await storeWhatsAppMessage(
          env.DB,
          message,
          phone,
          names.get(phone) || "",
        );
        if (inserted) processed += 1;
      }
    }
  }
  return json({ received: true, processed });
}

async function storeWhatsAppMessage(db, message, phone, profileName) {
  const sentAt = Number(message.timestamp || 0) * 1000 || Date.now();
  const body = whatsappMessageBody(message);
  const messageType = String(message.type || "unknown");
  const existing = await db.prepare("SELECT id FROM whatsapp_messages WHERE id = ? AND owner_id = ?")
    .bind(message.id, OWNER_USER_ID)
    .first();
  if (existing) return false;

  const current = await db.prepare("SELECT * FROM clients WHERE phone = ? AND owner_id = ? ORDER BY last_contact_at DESC LIMIT 1")
    .bind(phone, OWNER_USER_ID).first();
  const client = current
    ? normalizeClient({
        ...clientToClient(current),
        name: current.name || profileName,
        tags: [...(parseJsonArray(current.tags_json) || []), "WhatsApp"],
        interactions: [
          ...(parseJsonArray(current.interactions_json) || []),
          {
            id: message.id,
            type: "whatsapp",
            text: body || `[${messageType}]`,
            createdAt: sentAt,
          },
        ],
        lastContactAt: sentAt,
      }, current)
    : normalizeClient({
        phone,
        name: profileName,
        stage: "new",
        tags: ["WhatsApp"],
        interactions: [{
          id: message.id,
          type: "whatsapp",
          text: body || `[${messageType}]`,
          createdAt: sentAt,
        }],
        lastContactAt: sentAt,
      });
  client.owner_id = OWNER_USER_ID;

  const media = message[messageType] || {};
  await db.batch([
    current
      ? updateStatement(db, "clients", CLIENT_FIELDS, client, OWNER_USER_ID)
      : insertStatement(db, "clients", CLIENT_FIELDS, client),
    db.prepare(
      `INSERT INTO whatsapp_messages
       (id, client_id, phone, profile_name, direction, message_type, body,
        media_id, reply_to_message_id, sent_at, created_at, owner_id)
       VALUES (?, ?, ?, ?, 'incoming', ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      message.id,
      client.id,
      phone,
      profileName,
      messageType,
      body,
      media.id || null,
      message.context?.id || null,
      sentAt,
      Date.now(),
      OWNER_USER_ID,
    ),
    envlessActivityStatement(
      db,
      OWNER_USER_ID,
      "client",
      "Mensaje de WhatsApp recibido",
      `${profileName || phone}: ${body || `[${messageType}]`}`.slice(0, 500),
      "client",
      client.id,
    ),
  ]);
  return true;
}

function whatsappMessageBody(message) {
  if (message.text?.body) return String(message.text.body).trim();
  if (message.button?.text) return String(message.button.text).trim();
  if (message.interactive?.button_reply) {
    const reply = message.interactive.button_reply;
    return String(reply.title || reply.id || "").trim();
  }
  if (message.interactive?.list_reply) {
    const reply = message.interactive.list_reply;
    return String(reply.title || reply.description || reply.id || "").trim();
  }
  const content = message[message.type] || {};
  return String(content.caption || content.filename || "").trim();
}

async function verifyMetaSignature(body, signature, appSecret) {
  if (!signature.startsWith("sha256=")) return false;
  const expectedHex = signature.slice(7).toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(expectedHex)) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(appSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const actual = new Uint8Array(digest);
  const expected = hexToBytes(expectedHex);
  if (actual.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < actual.length; index += 1) {
    difference |= actual[index] ^ expected[index];
  }
  return difference === 0;
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

function normalizeWhatsAppPhone(value) {
  return String(value || "").replace(/\D/g, "");
}

function mergeStoredClients(submitted, storedRows) {
  const byId = new Map(submitted.map((client) => [client.id, client]));
  for (const row of storedRows) {
    const stored = clientToClient(row);
    const current = byId.get(stored.id);
    // La lista enviada por el cliente es la fuente de verdad. Si un registro
    // almacenado ya no viene en ella, debe poder eliminarse de forma permanente.
    if (!current) continue;
    const interactions = normalizeInteractions([
      ...(parseJsonArray(row.interactions_json) || []),
      ...(parseJsonArray(current.interactions_json) || []),
    ]);
    const uniqueInteractions = [...new Map(interactions.map((item) => [item.id, item])).values()]
      .sort((left, right) => left.createdAt - right.createdAt)
      .slice(-50);
    current.interactions_json = JSON.stringify(uniqueInteractions);
    current.tags_json = JSON.stringify(normalizeStringArray([
      ...(parseJsonArray(row.tags_json) || []),
      ...(parseJsonArray(current.tags_json) || []),
    ]));
    current.name = current.name || row.name || "";
    current.document = current.document || row.document || "";
    current.last_contact_at = Math.max(
      Number(current.last_contact_at || 0),
      Number(row.last_contact_at || 0),
    ) || Date.now();
  }
  return submitted;
}
function normalizeEvent(input, current = {}) {
  const now = Date.now();
  const status = input.status || current.status || "active";
  if (!EVENT_STATUSES.has(status)) throw new Error("Estado de evento invalido");
  const name = String(input.name || current.name || "").trim();
  if (!name) throw new Error("El nombre del evento es obligatorio");
  return {
    id: input.id || current.id || crypto.randomUUID(),
    name,
    event_date: input.date ?? input.eventDate ?? input.event_date ?? current.event_date ?? null,
    venue: String(input.venue ?? current.venue ?? "").trim(),
    status,
    image_url: String(input.image ?? input.imageUrl ?? input.image_url ?? current.image_url ?? ""),
    messages_json: JSON.stringify(
      input.messages
      ?? parseJsonObject(input.messages_json)
      ?? parseJsonObject(current.messages_json)
      ?? {}
    ),
    flyer_object_key: input.flyerObjectKey ?? input.flyer_object_key ?? current.flyer_object_key ?? null,
    flyer_file_name: String(input.flyerFileName ?? input.flyer_file_name ?? current.flyer_file_name ?? ""),
    flyer_file_type: String(input.flyerFileType ?? input.flyer_file_type ?? current.flyer_file_type ?? ""),
    flyer_file_size: number(input.flyerFileSize ?? input.flyer_file_size ?? current.flyer_file_size),
    created_at: Number(input.createdAt ?? input.created_at ?? current.created_at ?? now),
    updated_at: now,
    deleted_at: input.deletedAt ?? input.deleted_at ?? current.deleted_at ?? null,
  };
}

function allowQrRequest(key, limit, windowMs) {
  const now = Date.now();
  const current = qrValidationWindows.get(key);
  if (!current || now - current.startedAt >= windowMs) {
    qrValidationWindows.set(key, { startedAt: now, count: 1 });
    return true;
  }
  current.count += 1;
  return current.count <= limit;
}

function qrTicketId(qrData) {
  const match = String(qrData).match(/^ID:\s*([^\r\n]+)$/im);
  return match ? match[1].trim() : "";
}

async function findTicketByQr(db, ownerId, eventId, qrData) {
  const embeddedId = qrTicketId(qrData);
  return db.prepare(
    `SELECT * FROM tickets
     WHERE owner_id = ? AND event_id = ? AND deleted_at IS NULL
       AND (id = ? OR code_value = ? OR internal_code = ?)
     LIMIT 1`
  ).bind(ownerId, eventId, embeddedId || "__none__", qrData, qrData).first();
}

function normalizeTicket(input, current = {}) {
  const now = Date.now();
  const format = input.format || current.format || "pdf";
  const status = input.status || current.status || "available";
  const payment = input.paymentStatus || input.payment_status || current.payment_status || "pending";
  if (!FORMATS.has(format)) throw new Error("Formato de entrada invalido");
  if (!TICKET_STATUSES.has(status)) throw new Error("Estado de entrada invalido");
  if (!PAYMENT_STATUSES.has(payment)) throw new Error("Estado de pago invalido");
  const eventId = input.eventId || input.event_id || current.event_id;
  const internalCode = String(input.internalCode || input.internal_code || current.internal_code || "").trim();
  if (!eventId || !internalCode) throw new Error("Evento y código interno son obligatorios");
  return {
    id: input.id || current.id || crypto.randomUUID(),
    event_id: eventId,
    internal_code: internalCode,
    format,
    zone: String(input.zone ?? current.zone ?? "General"),
    base_price: number(input.basePrice ?? input.base_price ?? current.base_price),
    sale_price: number(input.salePrice ?? input.sale_price ?? current.sale_price),
    status,
    payment_status: payment,
    payment_method: String(input.paymentMethod ?? input.payment_method ?? current.payment_method ?? ""),
    buyer_name: String(input.buyerName ?? input.buyer_name ?? current.buyer_name ?? ""),
    buyer_phone: String(input.buyerPhone ?? input.buyer_phone ?? current.buyer_phone ?? ""),
    buyer_email: String(input.buyerEmail ?? input.buyer_email ?? current.buyer_email ?? ""),
    buyer_document: String(input.buyerDocument ?? input.buyer_document ?? current.buyer_document ?? ""),
    external_operation_id: String(input.externalOperationId ?? input.external_operation_id ?? current.external_operation_id ?? ""),
    notes: String(input.notes ?? current.notes ?? ""),
    code_value: String(input.codeValue ?? input.code_value ?? current.code_value ?? ""),
    object_key: input.objectKey ?? input.object_key ?? current.object_key ?? null,
    file_name: String(input.fileName ?? input.file_name ?? current.file_name ?? ""),
    file_type: String(input.fileType ?? input.file_type ?? current.file_type ?? ""),
    file_size: number(input.fileSize ?? input.file_size ?? current.file_size),
    created_at: Number(input.createdAt ?? input.created_at ?? current.created_at ?? now),
    updated_at: now,
    deleted_at: input.deletedAt ?? input.deleted_at ?? current.deleted_at ?? null,
    shared_at: input.sharedAt ?? input.shared_at ?? current.shared_at ?? null,
    checked_in_at: input.checkedInAt ?? input.checked_in_at ?? current.checked_in_at ?? null,
    source_platform: String(input.sourcePlatform ?? input.source_platform ?? current.source_platform ?? ""),
  };
}

function normalizeClient(input, current = {}) {
  const now = Date.now();
  const stage = input.stage || current.stage || "new";
  if (!CLIENT_STAGES.has(stage)) throw new Error("Etapa de cliente invalida");
  const phone = String(input.phone ?? current.phone ?? "").replace(/[^\d+]/g, "").trim();
  const name = String(input.name ?? current.name ?? "").trim();
  if (!phone && !name) throw new Error("Ingresa el nombre o el WhatsApp del cliente");
  return {
    id: input.id || current.id || crypto.randomUUID(),
    phone,
    name,
    document: String(input.document ?? input.dni ?? input.buyerDocument ?? current.document ?? "").trim(),
    event_id: input.eventId ?? input.event_id ?? current.event_id ?? null,
    stage,
    tags_json: JSON.stringify(normalizeStringArray(input.tags ?? parseJsonArray(input.tags_json) ?? parseJsonArray(current.tags_json))),
    notes: String(input.notes ?? current.notes ?? ""),
    interactions_json: JSON.stringify(normalizeInteractions(
      input.interactions ?? parseJsonArray(input.interactions_json) ?? parseJsonArray(current.interactions_json)
    )),
    last_contact_at: input.lastContactAt ?? input.last_contact_at ?? current.last_contact_at ?? now,
    created_at: Number(input.createdAt ?? input.created_at ?? current.created_at ?? now),
    updated_at: now,
  };
}

function eventToClient(row) {
  return {
    id: row.id,
    name: row.name,
    date: row.event_date,
    venue: row.venue,
    status: row.status,
    image: row.flyer_object_key
      ? `/api/event-flyer/${encodeURIComponent(row.id)}?v=${row.updated_at}`
      : row.image_url,
    messages: parseJsonObject(row.messages_json) || {},
    flyerObjectKey: row.flyer_object_key,
    flyerFileName: row.flyer_file_name,
    flyerFileType: row.flyer_file_type,
    flyerFileSize: row.flyer_file_size,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    deletedAt: row.deleted_at,
  };
}

function ticketToClient(row) {
  return {
    id: row.id,
    eventId: row.event_id,
    internalCode: row.internal_code,
    format: row.format,
    zone: row.zone,
    basePrice: row.base_price,
    salePrice: row.sale_price,
    status: row.status,
    paymentStatus: row.payment_status,
    paymentMethod: row.payment_method,
    buyerName: row.buyer_name,
    buyerPhone: row.buyer_phone,
    buyerEmail: row.buyer_email || "",
    buyerDocument: row.buyer_document,
    externalOperationId: row.external_operation_id || "",
    notes: row.notes,
    codeValue: row.code_value,
    objectKey: row.object_key,
    fileName: row.file_name,
    fileType: row.file_type,
    fileSize: row.file_size,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    deletedAt: row.deleted_at,
    sharedAt: row.shared_at,
    checkedInAt: row.checked_in_at,
    sourcePlatform: row.source_platform || "",
  };
}

function clientToClient(row) {
  return {
    id: row.id,
    phone: row.phone,
    name: row.name,
    document: row.document || "",
    eventId: row.event_id,
    stage: row.stage,
    tags: parseJsonArray(row.tags_json) || [],
    notes: row.notes,
    interactions: parseJsonArray(row.interactions_json) || [],
    lastContactAt: row.last_contact_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function activityToClient(row) {
  return {
    id: row.id,
    type: row.type,
    title: row.title,
    detail: row.detail,
    entityType: row.entity_type,
    entityId: row.entity_id,
    createdAt: row.created_at,
  };
}

function normalizeActivity(input) {
  return {
    id: input.id || crypto.randomUUID(),
    type: String(input.type || "ticket"),
    title: String(input.title || "Actividad"),
    detail: String(input.detail || ""),
    entity_type: input.entityType || input.entity_type || null,
    entity_id: input.entityId || input.entity_id || null,
    created_at: Number(input.createdAt || input.created_at || Date.now()),
  };
}

async function getOne(db, table, id, ownerId) {
  return db.prepare(`SELECT * FROM ${table} WHERE id = ? AND owner_id = ?`).bind(id, ownerId).first();
}

function insertStatement(db, table, fields, record) {
  const placeholders = fields.map(() => "?").join(", ");
  return db.prepare(
    `INSERT INTO ${table} (${fields.join(", ")}) VALUES (${placeholders})`
  ).bind(...fields.map((field) => record[field]));
}

function upsertStatement(db, table, fields, record) {
  const placeholders = fields.map(() => "?").join(", ");
  const mutableFields = fields.filter((field) => !["id", "owner_id", "created_at"].includes(field));
  return db.prepare(
    `INSERT INTO ${table} (${fields.join(", ")}) VALUES (${placeholders})
     ON CONFLICT(id) DO UPDATE SET ${mutableFields.map((field) => `${field} = excluded.${field}`).join(", ")}`
  ).bind(...fields.map((field) => record[field]));
}

async function insertRecord(db, table, fields, record) {
  return insertStatement(db, table, fields, record).run();
}

async function updateRecord(db, table, fields, record, ownerId) {
  return updateStatement(db, table, fields, record, ownerId).run();
}

function updateStatement(db, table, fields, record, ownerId) {
  const editable = fields.filter((field) => field !== "id" && field !== "created_at" && field !== "owner_id");
  return db.prepare(
    `UPDATE ${table} SET ${editable.map((field) => `${field} = ?`).join(", ")} WHERE id = ? AND owner_id = ?`
  ).bind(...editable.map((field) => record[field]), record.id, ownerId);
}

async function logActivity(db, ownerId, type, title, detail, entityType, entityId) {
  return envlessActivityStatement(db, ownerId, type, title, detail, entityType, entityId).run();
}

function envlessActivityStatement(db, ownerId, type, title, detail, entityType, entityId) {
  return db.prepare(
    `INSERT INTO activity
     (id, type, title, detail, entity_type, entity_id, created_at, owner_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), type, title, detail, entityType, entityId, Date.now(), ownerId);
}

async function readJson(request) {
  const type = request.headers.get("Content-Type") || "";
  if (!type.includes("application/json")) throw new Error("Se esperaba JSON");
  return request.json();
}

async function getAuthContext(request, env) {
  const ownerEmail = String(env.ALLOWED_EMAIL || "").split(",")[0]?.trim().toLowerCase() || "owner@iampromote.local";
  const ownerAuth = { userId: OWNER_USER_ID, email: ownerEmail, name: "Keen Sanchez", role: "owner" };
  if (String(env.DEV_BYPASS_AUTH || "").toLowerCase() === "true") {
    await ensureOwnerAccount(env.DB, ownerEmail);
    return ownerAuth;
  }
  const authorization = request.headers.get("Authorization") || "";
  if (env.ADMIN_TOKEN && authorization === `Bearer ${env.ADMIN_TOKEN}`) {
    await ensureOwnerAccount(env.DB, ownerEmail);
    return ownerAuth;
  }

  const accessEmail = request.headers
    .get("Cf-Access-Authenticated-User-Email")
    ?.trim()
    .toLowerCase();
  const allowedEmails = String(env.ALLOWED_EMAIL || "")
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean);

  if (accessEmail && allowedEmails.includes(accessEmail)) {
    await ensureOwnerAccount(env.DB, ownerEmail);
    return ownerAuth;
  }

  const token = readCookie(request, SESSION_COOKIE);
  const session = token ? await verifySessionToken(token, env.SESSION_SECRET) : null;
  if (!session) return null;
  if (!session.userId && session.email && allowedEmails.includes(session.email)) return ownerAuth;
  const user = await env.DB.prepare(
    "SELECT id, email, pending_email, name, role, status, experience, session_version, avatar_url FROM users WHERE id = ?"
  ).bind(session.userId).first();
  if (!user || user.status !== "active") return null;
  if (Number(session.version || 1) !== Number(user.session_version || 1)) return null;
  return { userId: user.id, email: user.email, pendingEmail: user.pending_email || "", name: user.name, role: user.role, experience: user.experience || "promoter", sessionVersion: user.session_version || 1, avatarUrl: user.avatar_url || "" };
}

async function ensureOwnerAccount(db, email) {
  const existing = await db.prepare("SELECT id FROM users WHERE id = ?").bind(OWNER_USER_ID).first();
  if (existing) return;
  const now = Date.now();
  await db.prepare(
    `INSERT OR IGNORE INTO users
     (id, email, name, password_hash, password_salt, role, status, created_at, updated_at, email_verified_at, experience, session_version)
     VALUES (?, ?, 'Keen Sanchez', 'managed-access', 'managed-access', 'owner', 'active', ?, ?, ?, 'promoter', 1)`
  ).bind(OWNER_USER_ID, `owner-${OWNER_USER_ID}@myfest.internal`, now, now, now).run();
}


function googleOAuthConfigured(env) {
  return Boolean(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET && env.SESSION_SECRET);
}

function safeLocalPath(value, fallback = "") {
  const path = String(value || "");
  return path.startsWith("/") && !path.startsWith("//") ? path : fallback;
}

function googleCallbackUrl(url, env) {
  return String(env.GOOGLE_REDIRECT_URI || new URL("/api/auth/google/callback", url.origin));
}

function oauthCookie(value, maxAge) {
  return `${GOOGLE_OAUTH_COOKIE}=${encodeURIComponent(value)}; Path=/api/auth/google; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
}

function googleErrorRedirect(url, code) {
  const target = new URL("/login.html", url.origin);
  target.searchParams.set("google_error", code);
  return new Response(null, {
    status: 303,
    headers: { Location: target.toString(), "Set-Cookie": oauthCookie("", 0), "Cache-Control": "no-store" },
  });
}

async function handleGoogleStart(request, env, url) {
  if (!googleOAuthConfigured(env)) return googleErrorRedirect(url, "not_configured");
  const nonce = toBase64Url(crypto.getRandomValues(new Uint8Array(24)));
  const experienceValue = String(url.searchParams.get("experience") || "attendee").toLowerCase();
  const stateData = {
    nonce,
    experience: EXPERIENCES.has(experienceValue) ? experienceValue : "attendee",
    next: safeLocalPath(url.searchParams.get("next")),
    exp: Math.floor(Date.now() / 1000) + GOOGLE_OAUTH_MAX_AGE,
  };
  const payload = toBase64Url(new TextEncoder().encode(JSON.stringify(stateData)));
  const state = `${payload}.${await signSessionPayload(payload, env.SESSION_SECRET)}`;
  const authorization = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authorization.searchParams.set("client_id", env.GOOGLE_CLIENT_ID);
  authorization.searchParams.set("redirect_uri", googleCallbackUrl(url, env));
  authorization.searchParams.set("response_type", "code");
  authorization.searchParams.set("scope", "openid profile email");
  authorization.searchParams.set("state", state);
  authorization.searchParams.set("prompt", "select_account");
  return new Response(null, {
    status: 302,
    headers: { Location: authorization.toString(), "Set-Cookie": oauthCookie(nonce, GOOGLE_OAUTH_MAX_AGE), "Cache-Control": "no-store" },
  });
}

async function readGoogleState(request, state, secret) {
  if (!state || !state.includes(".")) return null;
  const separator = state.lastIndexOf(".");
  const payload = state.slice(0, separator);
  const signature = state.slice(separator + 1);
  if (!(await verifySessionSignature(payload, signature, secret))) return null;
  try {
    const data = JSON.parse(new TextDecoder().decode(fromBase64Url(payload)));
    const cookieNonce = readCookie(request, GOOGLE_OAUTH_COOKIE);
    if (!cookieNonce || !constantTimeEqual(cookieNonce, String(data.nonce || ""))) return null;
    if (Number(data.exp || 0) <= Math.floor(Date.now() / 1000)) return null;
    return data;
  } catch {
    return null;
  }
}

async function handleGoogleCallback(request, env, url) {
  if (!googleOAuthConfigured(env)) return googleErrorRedirect(url, "not_configured");
  if (url.searchParams.get("error")) return googleErrorRedirect(url, "cancelled");
  const state = await readGoogleState(request, url.searchParams.get("state"), env.SESSION_SECRET);
  const code = String(url.searchParams.get("code") || "");
  if (!state || !code) return googleErrorRedirect(url, "invalid_state");

  try {
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: env.GOOGLE_CLIENT_ID,
        client_secret: env.GOOGLE_CLIENT_SECRET,
        code,
        grant_type: "authorization_code",
        redirect_uri: googleCallbackUrl(url, env),
      }),
    });
    const tokens = await tokenResponse.json().catch(() => ({}));
    if (!tokenResponse.ok || !tokens.access_token) throw new Error("token_exchange_failed");

    const profileResponse = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    const profile = await profileResponse.json().catch(() => ({}));
    const email = String(profile.email || "").trim().toLowerCase();
    const googleSub = String(profile.sub || "");
    if (!profileResponse.ok || !googleSub || !isValidEmail(email) || profile.email_verified !== true) {
      throw new Error("unverified_google_account");
    }

    let user = await env.DB.prepare("SELECT * FROM users WHERE google_sub = ? OR email = ? COLLATE NOCASE LIMIT 1")
      .bind(googleSub, email).first();
    const now = Date.now();
    if (user && user.status !== "active") return googleErrorRedirect(url, "account_disabled");
    if (user) {
      if (user.google_sub && user.google_sub !== googleSub) return googleErrorRedirect(url, "account_conflict");
      await env.DB.prepare("UPDATE users SET google_sub = ?, avatar_url = COALESCE(NULLIF(avatar_url, ''), ?), email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?")
        .bind(googleSub, String(profile.picture || ""), now, now, user.id).run();
      user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(user.id).first();
    } else {
      const userId = crypto.randomUUID();
      const generatedPassword = await hashPassword(toBase64Url(crypto.getRandomValues(new Uint8Array(32))));
      const experience = EXPERIENCES.has(String(state.experience || "")) ? state.experience : "attendee";
      await env.DB.prepare(
        `INSERT INTO users
         (id, email, name, password_hash, password_salt, role, status, created_at, updated_at, email_verified_at, experience, session_version, google_sub, avatar_url)
         VALUES (?, ?, ?, ?, ?, 'promoter', 'active', ?, ?, ?, ?, 1, ?, ?)`
      ).bind(userId, email, String(profile.name || email.split("@")[0]).slice(0, 80), generatedPassword.hash, generatedPassword.salt, now, now, now, experience, googleSub, String(profile.picture || "")).run();
      user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(userId).first();
      await writeSecurityAudit(request, env, { userId, actorUserId: userId, action: "account_created", detail: "Cuenta creada con Google" });
    }

    const auth = { userId: user.id, email: user.email, name: user.name, role: user.role, experience: user.experience || "attendee", sessionVersion: user.session_version || 1 };
    const sessionToken = await createSessionToken(auth, env.SESSION_SECRET);
    await writeSecurityAudit(request, env, { userId: user.id, actorUserId: user.id, action: "login", detail: "Inicio de sesión con Google" });
    const destination = safeLocalPath(state.next) || ({ attendee: "/fan.html", media: "/media.html", promoter: "/index.html" })[auth.experience] || "/experiencia.html";
    const response = new Response(null, { status: 303, headers: { Location: new URL(destination, url.origin).toString(), "Cache-Control": "no-store" } });
    response.headers.append("Set-Cookie", sessionCookie(sessionToken));
    response.headers.append("Set-Cookie", oauthCookie("", 0));
    return response;
  } catch (error) {
    console.error("Google OAuth failed", error);
    return googleErrorRedirect(url, "failed");
  }
}

async function handleLogin(request, env, cors) {
  if (!env.SESSION_SECRET) {
    return json({ error: "El sistema de sesiones aun no esta configurado" }, 503, cors);
  }
  if (!(await consumeAuthAttempt(request, env, "login", 10, 15 * 60))) {
    return json({ error: "Demasiados intentos. Espera unos minutos." }, 429, cors);
  }
  const body = await request.json().catch(() => ({}));
  const email = String(body.email || "").trim().toLowerCase();
  const password = String(body.password || "");
  if (!isValidEmail(email) || !password) return json({ error: "Correo o contraseña incorrectos" }, 401, cors);

  let user = await env.DB.prepare("SELECT * FROM users WHERE email = ? COLLATE NOCASE").bind(email).first();
  const allowedEmails = String(env.ALLOWED_EMAIL || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  if (!user && env.LOGIN_PASSWORD && allowedEmails.includes(email) && constantTimeEqual(password, String(env.LOGIN_PASSWORD))) {
    const credentials = await hashPassword(password);
    const now = Date.now();
    await env.DB.prepare(
      `INSERT OR IGNORE INTO users
       (id, email, name, password_hash, password_salt, role, status, created_at, updated_at, email_verified_at)
       VALUES (?, ?, ?, ?, ?, 'owner', 'active', ?, ?, ?)`
    ).bind(OWNER_USER_ID, email, "Keen Sanchez", credentials.hash, credentials.salt, now, now, now).run();
    user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(OWNER_USER_ID).first();
  }
  if (!user || user.status !== "active" || !(await verifyPassword(password, user.password_salt, user.password_hash))) {
    await new Promise((resolve) => setTimeout(resolve, 450));
    return json({ error: "Correo o contraseña incorrectos" }, 401, cors);
  }
  if (emailVerificationEnabled(env) && !user.email_verified_at) {
    return json({
      error: "Confirma tu correo antes de ingresar.",
      code: "EMAIL_NOT_VERIFIED",
      email: user.email,
    }, 403, cors);
  }
  const auth = { userId: user.id, email: user.email, name: user.name, role: user.role, experience: user.experience || "promoter", sessionVersion: user.session_version || 1 };
  const token = await createSessionToken(auth, env.SESSION_SECRET);
  await writeSecurityAudit(request, env, { userId: user.id, actorUserId: user.id, action: "login", detail: "Inicio de sesión correcto" });
  return json({ ok: true, user: publicUser(auth) }, 200, { ...cors, "Set-Cookie": sessionCookie(token) });
}

async function handleRegister(request, env, cors) {
  if (!env.SESSION_SECRET) return json({ error: "El sistema de sesiones aun no esta configurado" }, 503, cors);
  if (!(await consumeAuthAttempt(request, env, "register", 5, 60 * 60))) {
    return json({ error: "Demasiados registros desde esta conexion. Intenta mas tarde." }, 429, cors);
  }
  const body = await request.json().catch(() => ({}));
  const name = String(body.name || "").trim().replace(/\s+/g, " ");
  const email = String(body.email || "").trim().toLowerCase();
  const password = String(body.password || "");
  const experience = EXPERIENCES.has(String(body.experience || "").toLowerCase())
    ? String(body.experience).toLowerCase()
    : "promoter";
  if (name.length < 2 || name.length > 80) return json({ error: "Ingresa un nombre valido" }, 400, cors);
  if (!isValidEmail(email) || email.length > 160) return json({ error: "Ingresa un correo valido" }, 400, cors);
  if (password.length < 10 || password.length > 128) {
    return json({ error: "La contraseña debe tener entre 10 y 128 caracteres" }, 400, cors);
  }
  const existing = await env.DB.prepare("SELECT id FROM users WHERE email = ? COLLATE NOCASE").bind(email).first();
  if (existing) return json({ error: "Ya existe una cuenta con ese correo" }, 409, cors);
  const userId = crypto.randomUUID();
  const credentials = await hashPassword(password);
  const now = Date.now();
  const requiresVerification = emailVerificationEnabled(env);
  try {
    await env.DB.prepare(
      `INSERT INTO users
       (id, email, name, password_hash, password_salt, role, status, created_at, updated_at, email_verified_at, experience)
       VALUES (?, ?, ?, ?, ?, 'promoter', 'active', ?, ?, ?, ?)`
    ).bind(
      userId,
      email,
      name,
      credentials.hash,
      credentials.salt,
      now,
      now,
      requiresVerification ? null : now,
      experience,
    ).run();
  } catch (error) {
    if (String(error?.message || "").toLowerCase().includes("unique")) {
      return json({ error: "Ya existe una cuenta con ese correo" }, 409, cors);
    }
    throw error;
  }
  if (requiresVerification) {
    try {
      await createAndSendVerification(env, { id: userId, email, name }, new URL(request.url).origin);
    } catch (error) {
      console.error("Verification email failed", error);
      await env.DB.batch([
        env.DB.prepare("DELETE FROM email_verification_tokens WHERE user_id = ?").bind(userId),
        env.DB.prepare("DELETE FROM users WHERE id = ? AND email_verified_at IS NULL").bind(userId),
      ]);
      return json({ error: "No pudimos enviar el correo de verificacion. Intenta nuevamente." }, 502, cors);
    }
    return json({
      ok: true,
      verificationRequired: true,
      email,
      message: "Revisa tu correo para activar tu cuenta.",
    }, 201, cors);
  }

  const auth = { userId, email, name, role: "promoter", experience, sessionVersion: 1 };
  const token = await createSessionToken(auth, env.SESSION_SECRET);
  await writeSecurityAudit(request, env, { userId, actorUserId: userId, action: "account_created", detail: "Cuenta creada" });
  return json({ ok: true, user: publicUser(auth) }, 201, { ...cors, "Set-Cookie": sessionCookie(token) });
}

async function handleResendVerification(request, env, cors) {
  if (!emailVerificationEnabled(env)) {
    return json({ error: "La verificacion por correo aun no esta configurada." }, 503, cors);
  }
  const body = await request.json().catch(() => ({}));
  const email = String(body.email || "").trim().toLowerCase();
  const generic = {
    ok: true,
    message: "Si existe una cuenta pendiente, enviaremos un nuevo enlace de verificacion.",
  };
  if (!isValidEmail(email)) return json(generic, 200, cors);

  const user = await env.DB.prepare(
    "SELECT id, email, name, email_verified_at FROM users WHERE email = ? COLLATE NOCASE"
  ).bind(email).first();
  if (!user || user.email_verified_at) return json(generic, 200, cors);

  const latest = await env.DB.prepare(
    "SELECT created_at FROM email_verification_tokens WHERE user_id = ? ORDER BY created_at DESC LIMIT 1"
  ).bind(user.id).first();
  if (latest && Date.now() - Number(latest.created_at) < EMAIL_RESEND_COOLDOWN * 1000) {
    return json(generic, 200, cors);
  }

  try {
    await createAndSendVerification(env, user, new URL(request.url).origin);
  } catch (error) {
    console.error("Verification email resend failed", error);
    return json({ error: "No pudimos reenviar el correo. Intenta en unos minutos." }, 502, cors);
  }
  return json(generic, 200, cors);
}

async function handleVerifyEmail(request, env, url) {
  const token = String(url.searchParams.get("token") || "");
  const redirect = new URL("/login", url.origin);
  if (!token || token.length > 256) {
    redirect.searchParams.set("verification", "invalid");
    return Response.redirect(redirect.toString(), 303);
  }

  const tokenHash = await sha256Base64Url(token);
  const record = await env.DB.prepare(
    `SELECT token_hash, user_id, expires_at
     FROM email_verification_tokens
     WHERE token_hash = ?`
  ).bind(tokenHash).first();
  if (!record || Number(record.expires_at) < Date.now()) {
    if (record) {
      await env.DB.prepare("DELETE FROM email_verification_tokens WHERE token_hash = ?").bind(tokenHash).run();
    }
    redirect.searchParams.set("verification", "expired");
    return Response.redirect(redirect.toString(), 303);
  }

  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare(
      "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?"
    ).bind(now, now, record.user_id),
    env.DB.prepare("DELETE FROM email_verification_tokens WHERE user_id = ?").bind(record.user_id),
  ]);
  redirect.searchParams.set("verification", "success");
  return Response.redirect(redirect.toString(), 303);
}

async function createAndSendEmailChange(env, user, origin) {
  const rawToken = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const tokenHash = await sha256Base64Url(rawToken);
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM email_change_tokens WHERE user_id = ? OR expires_at < ?").bind(user.id, now),
    env.DB.prepare("INSERT INTO email_change_tokens (token_hash, user_id, new_email, expires_at, created_at) VALUES (?, ?, ?, ?, ?)")
      .bind(tokenHash, user.id, user.pending_email, now + EMAIL_CHANGE_MAX_AGE * 1000, now),
  ]);
  const verifyUrl = new URL("/api/auth/verify-email-change", origin);
  verifyUrl.searchParams.set("token", rawToken);
  if (String(env.DEV_EMAIL_PREVIEW || "").toLowerCase() === "true") return { previewUrl: verifyUrl.toString() };
  await sendEmailChangeEmail(env, user, verifyUrl.toString());
  return {};
}

async function sendEmailChangeEmail(env, user, verifyUrl) {
  const safeName = escapeHtml(user.name || "usuario");
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [user.pending_email],
      subject: "Confirma tu nuevo correo de MyFest",
      html: `<!doctype html><html><body style="margin:0;background:#0b0b0d;color:#fff;font-family:Arial,sans-serif"><div style="max-width:560px;margin:0 auto;padding:40px 24px"><div style="color:#ff3d9a;font-weight:700">MYFEST</div><h1>Confirma tu nuevo correo</h1><p style="color:#bdb7c4;line-height:1.6">Hola ${safeName}, confirma que esta dirección será el nuevo correo de acceso a tu cuenta.</p><a href="${verifyUrl}" style="display:inline-block;margin:20px 0;padding:14px 22px;border-radius:8px;background:#ff3d9a;color:#17191e;text-decoration:none;font-weight:700">Confirmar correo</a><p style="color:#817a88;font-size:13px">El enlace vence en 1 hora. Si no solicitaste el cambio, ignora este mensaje.</p></div></body></html>`,
      text: `Hola ${user.name || "usuario"}. Confirma tu nuevo correo de MyFest: ${verifyUrl}\n\nEl enlace vence en 1 hora.`,
    }),
  });
  if (!response.ok) throw new Error(`Resend ${response.status}`);
}

async function handleVerifyEmailChange(request, env, url) {
  const rawToken = String(url.searchParams.get("token") || "");
  const failure = new URL("/security.html", url.origin);
  if (!rawToken || rawToken.length > 256) {
    failure.searchParams.set("emailChange", "invalid");
    return Response.redirect(failure.toString(), 303);
  }
  const tokenHash = await sha256Base64Url(rawToken);
  const record = await env.DB.prepare(
    `SELECT t.user_id, t.new_email, t.expires_at, u.name, u.role, u.status, u.experience, u.pending_email, u.session_version
     FROM email_change_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ?`
  ).bind(tokenHash).first();
  if (!record || Number(record.expires_at) < Date.now() || record.status !== "active" || record.pending_email !== record.new_email) {
    if (record) await env.DB.prepare("DELETE FROM email_change_tokens WHERE token_hash = ?").bind(tokenHash).run();
    failure.searchParams.set("emailChange", "expired");
    return Response.redirect(failure.toString(), 303);
  }
  const duplicate = await env.DB.prepare("SELECT id FROM users WHERE id <> ? AND email = ? COLLATE NOCASE").bind(record.user_id, record.new_email).first();
  if (duplicate) {
    failure.searchParams.set("emailChange", "duplicate");
    return Response.redirect(failure.toString(), 303);
  }
  const nextVersion = Number(record.session_version || 1) + 1;
  await env.DB.batch([
    env.DB.prepare("UPDATE users SET email = ?, pending_email = NULL, email_verified_at = ?, session_version = ?, updated_at = ? WHERE id = ?")
      .bind(record.new_email, Date.now(), nextVersion, Date.now(), record.user_id),
    env.DB.prepare("DELETE FROM email_change_tokens WHERE user_id = ?").bind(record.user_id),
  ]);
  await writeSecurityAudit(request, env, { userId: record.user_id, actorUserId: record.user_id, action: "email_changed", detail: "Nuevo correo confirmado" });
  const success = new URL("/security.html", url.origin);
  success.searchParams.set("emailChange", "success");
  if (!env.SESSION_SECRET) return Response.redirect(success.toString(), 303);
  const token = await createSessionToken({ userId: record.user_id, email: record.new_email, name: record.name, role: record.role, experience: record.experience, sessionVersion: nextVersion }, env.SESSION_SECRET);
  return new Response(null, { status: 303, headers: { Location: success.toString(), "Set-Cookie": sessionCookie(token) } });
}

function emailVerificationEnabled(env) {
  return Boolean(env.RESEND_API_KEY && env.EMAIL_FROM);
}

async function handleForgotPassword(request, env, cors) {
  const generic = { ok: true, message: "Si el correo existe, enviaremos instrucciones para recuperar la cuenta." };
  if (!emailVerificationEnabled(env)) return json({ error: "El servicio de correo aun no esta configurado." }, 503, cors);
  if (!(await consumeAuthAttempt(request, env, "forgot", 5, 60 * 60))) return json(generic, 200, cors);
  const body = await request.json().catch(() => ({}));
  const email = String(body.email || "").trim().toLowerCase();
  if (!isValidEmail(email)) return json(generic, 200, cors);
  const user = await env.DB.prepare(
    "SELECT id, email, name FROM users WHERE email = ? COLLATE NOCASE AND status = 'active'"
  ).bind(email).first();
  if (!user) return json(generic, 200, cors);
  const rawToken = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const tokenHash = await sha256Base64Url(rawToken);
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM password_reset_tokens WHERE user_id = ? OR expires_at < ?").bind(user.id, now),
    env.DB.prepare("INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)")
      .bind(tokenHash, user.id, now + PASSWORD_RESET_MAX_AGE * 1000, now),
  ]);
  const resetUrl = new URL("/login.html", new URL(request.url).origin);
  resetUrl.searchParams.set("reset", rawToken);
  await sendPasswordResetEmail(env, user, resetUrl.toString());
  return json(generic, 200, cors);
}

async function handleResetPassword(request, env, cors) {
  if (!(await consumeAuthAttempt(request, env, "reset", 8, 60 * 60))) {
    return json({ error: "Demasiados intentos. Solicita un nuevo enlace." }, 429, cors);
  }
  const body = await request.json().catch(() => ({}));
  const token = String(body.token || "");
  const password = String(body.password || "");
  if (!token || token.length > 256) return json({ error: "Enlace no valido" }, 400, cors);
  if (password.length < 10 || password.length > 128) return json({ error: "La contraseña debe tener entre 10 y 128 caracteres" }, 400, cors);
  const tokenHash = await sha256Base64Url(token);
  const record = await env.DB.prepare(
    "SELECT user_id, expires_at FROM password_reset_tokens WHERE token_hash = ?"
  ).bind(tokenHash).first();
  if (!record || Number(record.expires_at) < Date.now()) {
    if (record) await env.DB.prepare("DELETE FROM password_reset_tokens WHERE token_hash = ?").bind(tokenHash).run();
    return json({ error: "El enlace vencio o ya fue utilizado" }, 400, cors);
  }
  const credentials = await hashPassword(password);
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare("UPDATE users SET password_hash = ?, password_salt = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?")
      .bind(credentials.hash, credentials.salt, now, record.user_id),
    env.DB.prepare("DELETE FROM password_reset_tokens WHERE user_id = ?").bind(record.user_id),
  ]);
  await writeSecurityAudit(request, env, { userId: record.user_id, actorUserId: record.user_id, action: "password_reset", detail: "Contraseña restablecida mediante enlace seguro" });
  return json({ ok: true, message: "Contraseña actualizada. Ya puedes iniciar sesión." }, 200, cors);
}

async function writeSecurityAudit(request, env, entry) {
  if (!env.DB) return;
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "unknown";
  const ipHash = await sha256Base64Url(`audit:${ip}:${env.SESSION_SECRET || "local"}`);
  const userAgent = String(request.headers.get("User-Agent") || "Dispositivo no identificado").slice(0, 220);
  await env.DB.prepare(
    `INSERT INTO security_audit
     (id, user_id, actor_user_id, action, detail, ip_hash, user_agent, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    entry.userId || null,
    entry.actorUserId || null,
    String(entry.action || "unknown").slice(0, 80),
    String(entry.detail || "").slice(0, 500),
    ipHash,
    userAgent,
    Date.now(),
  ).run();
}

async function sendPasswordResetEmail(env, user, resetUrl) {
  const safeName = escapeHtml(user.name || "usuario");
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [user.email],
      subject: "Recupera tu cuenta de MyFest",
      html: `<!doctype html><html><body style="margin:0;background:#0b0b0d;color:#fff;font-family:Arial,sans-serif"><div style="max-width:560px;margin:0 auto;padding:40px 24px"><div style="color:#ff3d9a;font-weight:700">MYFEST</div><h1>Restablece tu contraseña</h1><p style="color:#bdb7c4;line-height:1.6">Hola ${safeName}, usa este enlace para crear una nueva contraseña.</p><a href="${resetUrl}" style="display:inline-block;margin:20px 0;padding:14px 22px;border-radius:8px;background:#b78be7;color:#111;text-decoration:none;font-weight:700">Crear nueva contraseña</a><p style="color:#817a88;font-size:13px">El enlace vence en 30 minutos. Si no lo solicitaste, ignora este mensaje.</p></div></body></html>`,
      text: `Hola ${user.name || "usuario"}. Recupera tu cuenta de MyFest: ${resetUrl}\n\nEl enlace vence en 30 minutos.`,
    }),
  });
  if (!response.ok) throw new Error(`Resend ${response.status}`);
}

async function consumeAuthAttempt(request, env, action, limit, windowSeconds) {
  if (!env.DB) return true;
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const fingerprint = await sha256Base64Url(`${action}:${ip}:${env.SESSION_SECRET || "local"}`);
  const bucket = `${action}:${fingerprint}`;
  const now = Date.now();
  const current = await env.DB.prepare("SELECT attempts, expires_at FROM auth_rate_limits WHERE bucket = ?").bind(bucket).first();
  if (!current || Number(current.expires_at) <= now) {
    await env.DB.prepare(
      "INSERT INTO auth_rate_limits (bucket, attempts, expires_at) VALUES (?, 1, ?) ON CONFLICT(bucket) DO UPDATE SET attempts = 1, expires_at = excluded.expires_at"
    ).bind(bucket, now + windowSeconds * 1000).run();
    return true;
  }
  if (Number(current.attempts) >= limit) return false;
  await env.DB.prepare("UPDATE auth_rate_limits SET attempts = attempts + 1 WHERE bucket = ?").bind(bucket).run();
  return true;
}

async function createAndSendVerification(env, user, origin) {
  const rawToken = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const tokenHash = await sha256Base64Url(rawToken);
  const now = Date.now();
  const expiresAt = now + EMAIL_VERIFICATION_MAX_AGE * 1000;
  await env.DB.batch([
    env.DB.prepare("DELETE FROM email_verification_tokens WHERE user_id = ? OR expires_at < ?").bind(user.id, now),
    env.DB.prepare(
      "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)"
    ).bind(tokenHash, user.id, expiresAt, now),
  ]);

  const verifyUrl = new URL("/api/auth/verify", origin);
  verifyUrl.searchParams.set("token", rawToken);
  try {
    await sendVerificationEmail(env, user, verifyUrl.toString());
  } catch (error) {
    await env.DB.prepare("DELETE FROM email_verification_tokens WHERE token_hash = ?").bind(tokenHash).run();
    throw error;
  }
}

async function sendVerificationEmail(env, user, verifyUrl) {
  const safeName = escapeHtml(user.name || "promotor");
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [user.email],
      subject: "Confirma tu cuenta de MyFest",
      html: `<!doctype html><html><body style="margin:0;background:#0b0712;color:#f8f5ff;font-family:Arial,sans-serif"><div style="max-width:560px;margin:0 auto;padding:40px 24px"><div style="font-size:14px;color:#ff3d9a;font-weight:700">MYFEST</div><h1 style="font-size:28px;margin:18px 0 12px">Confirma tu correo</h1><p style="color:#c5bdcc;line-height:1.65">Hola ${safeName}, activa tu cuenta para comenzar a organizar tus eventos.</p><a href="${verifyUrl}" style="display:inline-block;margin:20px 0;padding:14px 22px;border-radius:8px;background:#b78be7;color:#111;text-decoration:none;font-weight:700">Confirmar mi cuenta</a><p style="color:#8e8598;font-size:13px;line-height:1.6">Este enlace vence en 24 horas. Si no creaste esta cuenta, puedes ignorar el mensaje.</p></div></body></html>`,
      text: `Hola ${user.name || "usuario"}. Confirma tu cuenta de MyFest: ${verifyUrl}\n\nEl enlace vence en 24 horas.`,
    }),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Resend ${response.status}: ${detail.slice(0, 300)}`);
  }
}

async function sha256Base64Url(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return toBase64Url(new Uint8Array(digest));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function publicUser(auth) {
  return { id: auth.userId, email: auth.email, pendingEmail: auth.pendingEmail || "", name: auth.name, role: auth.role, experience: auth.experience || "promoter", avatarUrl: auth.avatarUrl || "" };
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

async function hashPassword(password, saltValue = "") {
  const salt = saltValue ? fromBase64Url(saltValue) : crypto.getRandomValues(new Uint8Array(16));
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: PASSWORD_ITERATIONS },
    key,
    256,
  );
  return { hash: toBase64Url(new Uint8Array(bits)), salt: toBase64Url(salt) };
}

async function verifyPassword(password, salt, expectedHash) {
  const result = await hashPassword(password, salt);
  return constantTimeEqual(result.hash, expectedHash);
}

function readCookie(request, name) {
  const cookies = request.headers.get("Cookie") || "";
  const match = cookies.split(";").map((item) => item.trim()).find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

function sessionCookie(token) {
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; Max-Age=${SESSION_MAX_AGE}; HttpOnly; Secure; SameSite=Strict`;
}

function clearSessionCookie() {
  return `${SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
}

async function createSessionToken(auth, secret) {
  const payload = toBase64Url(new TextEncoder().encode(JSON.stringify({
    userId: auth.userId,
    email: auth.email,
    role: auth.role,
    version: Number(auth.sessionVersion || 1),
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE,
  })));
  return `${payload}.${await signSessionPayload(payload, secret)}`;
}

async function createDigitalizerToken(auth, secret, options = {}) {
  const payload = toBase64Url(new TextEncoder().encode(JSON.stringify({
    userId: auth.userId,
    version: Number(auth.sessionVersion || 1),
    scope: "digitalizer-generation",
    ...(options.id ? { jti: options.id } : {}),
    exp: options.expiresAt ? Math.floor(options.expiresAt / 1000) : Math.floor(Date.now() / 1000) + (60 * 60 * 12),
  })));
  return `${payload}.${await signSessionPayload(payload, secret)}`;
}

async function verifyDigitalizerToken(token, secret) {
  const claim = await verifySessionToken(token, secret);
  return claim?.scope === "digitalizer-generation" && claim.userId ? claim : null;
}

async function verifySessionToken(token, secret) {
  if (!secret || !token.includes(".")) return null;
  const [payload, signature] = token.split(".");
  if (!payload || !signature || !(await verifySessionSignature(payload, signature, secret))) return null;
  try {
    const session = JSON.parse(new TextDecoder().decode(fromBase64Url(payload)));
    return session.exp > Math.floor(Date.now() / 1000) ? session : null;
  } catch {
    return null;
  }
}

async function sessionKey(secret) {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function signSessionPayload(payload, secret) {
  const signature = await crypto.subtle.sign("HMAC", await sessionKey(secret), new TextEncoder().encode(payload));
  return toBase64Url(new Uint8Array(signature));
}

async function verifySessionSignature(payload, signature, secret) {
  try {
    return crypto.subtle.verify("HMAC", await sessionKey(secret), fromBase64Url(signature), new TextEncoder().encode(payload));
  } catch {
    return false;
  }
}

function toBase64Url(bytes) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function constantTimeEqual(left, right) {
  const a = new TextEncoder().encode(left);
  const b = new TextEncoder().encode(right);
  let difference = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) difference |= (a[index] || 0) ^ (b[index] || 0);
  return difference === 0;
}

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = String(env.ALLOWED_ORIGIN || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const approvedOrigin = allowed.includes("*") ? "*" : allowed.includes(origin) ? origin : allowed[0] || "";
  return {
    "Access-Control-Allow-Origin": approvedOrigin,
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-File-Name, X-Ticket-Id, X-Event-Id",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

function safeFileName(value) {
  return String(value)
    .normalize("NFKD")
    .replace(/[^\w.-]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 120) || "entrada";
}

function asciiFileName(value) {
  return safeFileName(value).replace(/"/g, "");
}

function number(value) {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseJsonObject(value) {
  if (!value) return null;
  if (typeof value === "object" && !Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function parseJsonArray(value) {
  if (!value) return null;
  if (Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function normalizeStringArray(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))].slice(0, 20);
}

function normalizeInteractions(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(-50).map((item) => ({
    id: String(item.id || crypto.randomUUID()),
    type: String(item.type || "note"),
    text: String(item.text || "").slice(0, 1000),
    createdAt: Number(item.createdAt || Date.now()),
  }));
}




