const $ = (selector) => document.querySelector(selector);
const menu = $("#adminMenuToggle"), sidebar = $("#adminSidebar"), overlay = $("#adminOverlay");
function toggleAdminMenu(open) { if (!menu || !sidebar || !overlay) return; sidebar.classList.toggle("is-open", open); overlay.classList.toggle("is-open", open); menu.setAttribute("aria-expanded", String(open)); }
menu?.addEventListener("click", () => toggleAdminMenu(!sidebar.classList.contains("is-open")));
overlay?.addEventListener("click", () => toggleAdminMenu(false));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") toggleAdminMenu(false); });
sidebar?.addEventListener("click", (event) => { if (event.target.closest("a")) toggleAdminMenu(false); });
$("#mobileMore")?.addEventListener("click", () => toggleAdminMenu(true));
async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "include", cache: "no-store", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Error de operación");
  return data;
}
function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}
function formatBytes(value = 0) {
  const bytes = Math.max(0, Number(value) || 0);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}
function notify(text, error = false) {
  const notice = $("#adminNotice");
  notice.hidden = false;
  notice.className = "notice";
  notice.style.color = error ? "var(--red)" : "";
  notice.textContent = text;
}
async function loadOverview() {
  const data = await api("/api/admin/overview");
  const values = { activeUsers: data.active, promoters: data.promoters, events: data.events, tickets: data.tickets, soldTickets: data.sold, checkins: data.checkins, digitalizedTickets: data.digitalized, totalUsers: data.users, openSupport: data.support, pendingDeletion: data.deletion };
  Object.entries(values).forEach(([id, value]) => { const node = $("#" + id); if (node) node.textContent = value ?? 0; });
  const ranks = {rankEvents:data.events,rankSold:data.sold,rankCheckins:data.checkins,rankPromoters:data.promoters,rankActive:data.active,rankSupport:data.support,rankDeletion:data.deletion};
  Object.entries(ranks).forEach(([id,value])=>{const node=$("#"+id);if(node)node.textContent=value??0;});
}
function digitalizerDateInput(value) {
  if (!value || !Number.isFinite(Number(value))) return "";
  const date = new Date(Number(value));
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,16);
}
async function loadUsers() {
  const data = await api(`/api/admin/users?q=${encodeURIComponent($("#userSearch").value)}`);
  $("#userList").innerHTML = data.users.map((user) => `
    <article class="user-row" data-user="${esc(user.id)}">
      <div><strong>${esc(user.name)}</strong><small>${esc(user.email)}</small><small class="user-resource-summary">${Number(user.event_count || 0)} eventos · ${Number(user.ticket_count || 0)} entradas · <b>${Number(user.digitalized_count || 0)} digitalizadas</b> · ${Number(user.client_count || 0)} clientes · ${Number(user.file_count || 0)} archivos · ${formatBytes(user.storage_bytes)}</small></div>
      <select data-field="experience"><option value="promoter" ${user.experience === "promoter" ? "selected" : ""}>Promotor</option><option value="attendee" ${user.experience === "attendee" ? "selected" : ""}>Asistente</option><option value="media" ${user.experience === "media" ? "selected" : ""}>Media partner</option></select>
      <select data-field="role"><option value="promoter" ${user.role === "promoter" ? "selected" : ""}>Usuario</option><option value="owner" ${user.role === "owner" ? "selected" : ""}>Administrador</option></select>
      <select data-field="status"><option value="active" ${user.status === "active" ? "selected" : ""}>Activo</option><option value="disabled" ${user.status === "disabled" ? "selected" : ""}>Bloqueado</option></select>
      <button class="btn save-user">Guardar</button>
      <div class="digitalizer-permission" style="grid-column:1 / -1;display:flex;gap:12px;align-items:end;flex-wrap:wrap;padding-top:12px;border-top:1px solid #ffffff20;margin-top:8px">
        <label>Digitalizador<select data-digitalizer-status aria-label="Permiso del digitalizador"><option value="revoked" ${user.digitalizer_access_status !== "active" ? "selected" : ""}>No autorizado</option><option value="active" ${user.digitalizer_access_status === "active" ? "selected" : ""}>Autorizado</option></select></label>
        <label>Vence el (opcional)<input data-digitalizer-expiry type="datetime-local" value="${digitalizerDateInput(user.digitalizer_expires_at)}"></label>
        <button class="btn save-digitalizer" type="button">Guardar acceso</button>
        <small>${user.digitalizer_allowed ? "Acceso vigente" : "Sin acceso vigente"}</small>
      </div>
    </article>`).join("") || "<p>No se encontraron usuarios.</p>";
}
async function loadRequests() {
  const data = await api("/api/admin/requests");
  $("#supportList").innerHTML = data.support.map((request) => `<div class="request-item"><strong>${esc(request.subject)}</strong> <span class="badge">${esc(request.status)}</span><p>${esc(request.message)}</p><small>${esc(request.name)} · ${esc(request.email)}</small>${request.status === "open" ? `<p><button class="btn request-action" data-kind="support" data-id="${esc(request.id)}" data-status="resolved">Marcar resuelto</button></p>` : ""}</div>`).join("") || "<p>Sin solicitudes.</p>";
  $("#deletionList").innerHTML = data.deletion.map((request) => `<div class="request-item"><strong>${esc(request.name)}</strong> <span class="badge">${esc(request.status)}</span><p>${esc(request.reason || "Sin motivo indicado")}</p><small>${esc(request.email)}</small>${request.status === "pending" ? `<p><button class="btn request-action" data-kind="deletion-requests" data-id="${esc(request.id)}" data-status="cancelled">Cancelar solicitud</button></p>` : ""}</div>`).join("") || "<p>Sin solicitudes.</p>";
}
async function loadAudit() {
  const data = await api("/api/admin/audit");
  $("#auditList").innerHTML = data.audit.map((item) => `<div class="request-item"><strong>${esc(item.action)}</strong> <span class="badge">${new Date(item.created_at).toLocaleString("es-PE")}</span><p>${esc(item.detail || "Actividad de cuenta")}</p><small>${esc(item.user_name)}${item.user_email ? ` · ${esc(item.user_email)}` : ""} · actor: ${esc(item.actor_name)}</small></div>`).join("") || "<p>Sin actividad registrada.</p>";
}
document.addEventListener("click", async (event) => {
  const requestButton = event.target.closest(".request-action");
  if (requestButton) {
    requestButton.disabled = true;
    try {
      await api(`/api/admin/${requestButton.dataset.kind}/${encodeURIComponent(requestButton.dataset.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: requestButton.dataset.status }) });
      await Promise.all([loadOverview(), loadRequests(), loadAudit()]);
      notify("Solicitud actualizada.");
    } catch (error) { notify(error.message, true); }
    return;
  }
  const accessButton = event.target.closest(".save-digitalizer");
  if (accessButton) {
    const row = accessButton.closest("[data-user]");
    const expiry = row.querySelector("[data-digitalizer-expiry]").value;
    accessButton.disabled = true;
    try {
      await api(`/api/admin/users/${encodeURIComponent(row.dataset.user)}/digitalizer-access`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allowed: row.querySelector("[data-digitalizer-status]").value === "active",
          expiresAt: expiry ? new Date(expiry).getTime() : null }),
      });
      notify("Permiso guardado. Vuelve a abrir el digitalizador desde Festholic para renovar su acceso.");
      await Promise.all([loadUsers(), loadAudit()]);
    } catch (error) { notify(error.message, true); }
    finally { accessButton.disabled = false; }
    return;
  }
  const button = event.target.closest(".save-user");
  if (!button) return;
  const row = button.closest("[data-user]");
  const value = (name) => row.querySelector(`[data-field='${name}']`).value;
  button.disabled = true;
  try {
    await api(`/api/admin/users/${encodeURIComponent(row.dataset.user)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ experience: value("experience"), role: value("role"), status: value("status") }) });
    notify("Cuenta actualizada. Sus sesiones anteriores fueron cerradas.");
    await Promise.all([loadOverview(), loadUsers()]);
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; }
});
$("#refreshUsers").addEventListener("click", () => Promise.all([loadOverview(), loadUsers(), loadRequests(), loadAudit()]));
$("#userSearch").addEventListener("input", () => { clearTimeout(window.searchTimer); window.searchTimer = setTimeout(loadUsers, 250); });
(async () => {
  try {
    const session = await api("/api/auth/session");
    if (session.user.role !== "owner") return location.replace("/");
    await Promise.all([loadOverview(), loadUsers(), loadRequests(), loadAudit()]);
  } catch (error) { notify(error.message, true); }
})();
