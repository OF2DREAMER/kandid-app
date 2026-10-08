/**
 * KINDID ADMIN PANEL — STANDALONE CLIENT CONTROLLER
 * Phase A + B Implementation
 * Strictly isolated from consumer bundle (index.html / app_core.js).
 */

var adminState = {
  me: null,
  activeTab: 'overview',
  overview: null,
  health: null
};

function getAuthToken() {
  try {
    return localStorage.getItem('kandid_token') || localStorage.getItem('token') || '';
  } catch (e) {
    return '';
  }
}

async function adminApiRequest(endpoint, options) {
  options = options || {};
  options.headers = options.headers || {};

  var token = getAuthToken();
  if (token) {
    options.headers['Authorization'] = 'Bearer ' + token;
  }
  options.headers['Content-Type'] = 'application/json';

  try {
    var response = await fetch(endpoint, options);
    var data = await response.json().catch(function() { return {}; });

    if (response.status === 401 || response.status === 403) {
      if (endpoint === '/api/admin/me') {
        renderAccessDenied(data.error || 'Admin authorization required');
      }
    }

    data._httpStatus = response.status;
    return data;
  } catch (err) {
    console.error('Admin API error:', err);
    return { success: false, error: 'Network error communicating with admin backend' };
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function verifyAdminIdentity() {
  var res = await adminApiRequest('/api/admin/me');
  if (res && res.success && res.user) {
    adminState.me = res.user;
    var badge = document.getElementById('adminIdentityBadge');
    if (badge) {
      badge.innerHTML = 'Logged in as <span class="font-bold text-white">@' + escapeHtml(res.user.handle) + '</span> <span class="text-amber-400">(' + escapeHtml(res.user.role) + ')</span>';
    }
    loadAdminOverview();
  } else {
    renderAccessDenied(res ? res.error : 'Unauthorized');
  }
}

function renderAccessDenied(message) {
  document.body.innerHTML = `
    <div class="min-h-screen bg-[#09090b] text-zinc-100 flex items-center justify-center p-6">
      <div class="max-w-md w-full bg-zinc-950 border border-red-500/30 rounded-2xl p-6 space-y-4 shadow-2xl text-center">
        <div class="w-12 h-12 rounded-full bg-red-950/60 border border-red-500/40 text-red-400 flex items-center justify-center text-xl font-mono-tag font-bold mx-auto">⛔</div>
        <h2 class="text-lg font-bold font-mono-tag text-white">Admin Access Denied</h2>
        <p class="text-xs text-zinc-400 font-mono-tag">${escapeHtml(message)}</p>
        <p class="text-[11px] text-zinc-500">You must be logged in as an authorized admin or founder account to view this surface.</p>
        <div class="pt-2 flex justify-center gap-3">
          <a href="/" class="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 font-mono-tag text-xs rounded-xl font-bold transition">← Return to Kandid App</a>
        </div>
      </div>
    </div>
  `;
}

async function loadAdminOverview() {
  var res = await adminApiRequest('/api/admin/overview');
  if (!res || !res.success) return;

  adminState.overview = res;

  var totalUsersEl = document.getElementById('metricTotalUsers');
  var activeUsersEl = document.getElementById('metricActiveUsers');
  var totalMomentsEl = document.getElementById('metricTotalMoments');
  var activeClustersEl = document.getElementById('metricActiveClusters');
  var activeCommunitiesEl = document.getElementById('metricActiveCommunities');
  var pendingReportsEl = document.getElementById('metricPendingReports');
  var pendingBadgeEl = document.getElementById('pendingReportsBadge');

  if (totalUsersEl) totalUsersEl.textContent = Number(res.total_users || 0).toLocaleString();
  if (activeUsersEl) activeUsersEl.textContent = Number(res.active_users || 0).toLocaleString() + ' active nodes';
  if (totalMomentsEl) totalMomentsEl.textContent = Number(res.total_moments || 0).toLocaleString();
  if (activeClustersEl) activeClustersEl.textContent = Number(res.active_clusters || 0).toLocaleString() + ' moment clusters';
  if (activeCommunitiesEl) activeCommunitiesEl.textContent = Number(res.active_communities || 0).toLocaleString();
  if (pendingReportsEl) pendingReportsEl.textContent = Number(res.pending_reports || 0).toLocaleString();
  if (pendingBadgeEl) pendingBadgeEl.textContent = String(res.pending_reports || 0);

  // Health summary update
  var dbStatusEl = document.getElementById('healthDbStatus');
  var dbEngineEl = document.getElementById('healthDbEngine');
  var activeSessionsEl = document.getElementById('healthActiveSessions');
  var envBadgeEl = document.getElementById('envBadge');

  if (res.system_health) {
    if (dbStatusEl) dbStatusEl.textContent = (res.system_health.database || 'HEALTHY').toUpperCase();
    if (dbEngineEl) dbEngineEl.textContent = (res.system_health.engine || 'SQLite / PostgreSQL').toUpperCase();
    if (activeSessionsEl) activeSessionsEl.textContent = Number(res.system_health.active_sessions || 0).toLocaleString() + ' sessions';
    if (envBadgeEl) envBadgeEl.textContent = (res.system_health.environment || 'PRODUCTION').toUpperCase();
  }
}

async function loadAdminHealth() {
  var res = await adminApiRequest('/api/admin/health');
  var container = document.getElementById('healthDetailsContainer');
  if (!container) return;

  if (!res || !res.success) {
    container.innerHTML = '<p class="text-red-400 font-bold">Failed to load health metrics: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  adminState.health = res;

  container.innerHTML = `
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-2">
        <span class="text-zinc-500 font-bold uppercase">Database Status</span>
        <p class="text-sm font-bold text-emerald-400">STATUS: ${escapeHtml(res.status || 'OK').toUpperCase()}</p>
        <p class="text-zinc-400">Engine: <span class="text-white">${escapeHtml(res.db_engine || 'sqlite')}</span></p>
        <p class="text-zinc-400">Latency: <span class="text-white">${res.db_latency_ms || 0} ms</span></p>
      </div>

      <div class="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-2">
        <span class="text-zinc-500 font-bold uppercase">Active Sessions & Telemetry</span>
        <p class="text-zinc-400">Active User Sessions: <span class="text-white font-bold">${res.active_sessions || 0}</span></p>
        <p class="text-zinc-400">Environment: <span class="text-amber-400 font-bold">${escapeHtml(res.environment || 'production')}</span></p>
        <p class="text-zinc-400">Service Version: <span class="text-white">${escapeHtml(res.version || 'v5.2.2')}</span></p>
      </div>
    </div>
  `;
}

function switchAdminTab(tabId) {
  adminState.activeTab = tabId;

  document.querySelectorAll('.admin-nav-item').forEach(function(btn) {
    btn.classList.remove('active');
  });
  var activeBtn = document.getElementById('tab-' + tabId);
  if (activeBtn) activeBtn.classList.add('active');

  document.querySelectorAll('.admin-view').forEach(function(view) {
    view.classList.add('hidden');
  });
  var activeView = document.getElementById('view-' + tabId);
  if (activeView) activeView.classList.remove('hidden');

  if (tabId === 'overview') {
    loadAdminOverview();
  } else if (tabId === 'health') {
    loadAdminHealth();
  }
}

function logoutAdmin() {
  try {
    localStorage.removeItem('kandid_token');
    localStorage.removeItem('token');
    localStorage.removeItem('kandid_user');
  } catch (e) {}
  window.location.href = '/';
}

document.addEventListener('DOMContentLoaded', function() {
  verifyAdminIdentity();
});
