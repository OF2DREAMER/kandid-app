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
  } else if (tabId === 'users') {
    loadAdminUsers(1);
  }
}

/* ==========================================================================
   PHASE C USER MANAGEMENT CLIENT CONTROLLER
   ========================================================================== */

adminState.users = {
  page: 1,
  pages: 1,
  total: 0,
  items: [],
  currentModalUser: null
};

async function loadAdminUsers(page) {
  page = page || adminState.users.page || 1;
  var q = (document.getElementById('adminUserSearchInput')?.value || '').trim();
  var role = document.getElementById('adminUserRoleFilter')?.value || '';
  var status = document.getElementById('adminUserStatusFilter')?.value || '';

  var url = '/api/admin/users?page=' + page + '&limit=25';
  if (q) url += '&q=' + encodeURIComponent(q);
  if (role) url += '&role=' + encodeURIComponent(role);
  if (status) url += '&status=' + encodeURIComponent(status);

  var tbody = document.getElementById('adminUsersTableBody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-zinc-500">Loading user records...</td></tr>';
  }

  var res = await adminApiRequest(url);
  if (!res || !res.success) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-red-400">Failed to load users: ' + escapeHtml(res ? res.error : 'Unknown error') + '</td></tr>';
    }
    return;
  }

  adminState.users.page = res.page;
  adminState.users.pages = res.pages;
  adminState.users.total = res.total;
  adminState.users.items = res.users || [];

  renderAdminUsersTable();
}

function renderAdminUsersTable() {
  var tbody = document.getElementById('adminUsersTableBody');
  var pageInfo = document.getElementById('adminUsersPageInfo');
  var prevBtn = document.getElementById('adminUsersPrevBtn');
  var nextBtn = document.getElementById('adminUsersNextBtn');
  if (!tbody) return;

  var items = adminState.users.items;
  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-zinc-500">No user records found matching filters.</td></tr>';
  } else {
    var html = '';
    items.forEach(function(u) {
      var statusBadgeClass = u.account_status === 'suspended'
        ? 'bg-red-500/20 text-red-400 border-red-500/30'
        : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      var roleBadgeClass = u.role === 'founder'
        ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
        : (u.role === 'admin' ? 'bg-purple-500/20 text-purple-300 border-purple-500/30' : 'bg-zinc-800 text-zinc-300 border-zinc-700');

      var createdStr = u.created_at ? String(u.created_at).split('T')[0] : '--';
      var activeStr = u.last_active ? String(u.last_active).split('T')[0] : 'Never';

      html += `
        <tr class="hover:bg-zinc-900/50 transition">
          <td class="px-4 py-3 font-bold text-white">
            ${escapeHtml(u.name || 'User')}
            <div class="text-[10px] text-amber-400 font-normal">@${escapeHtml(u.handle)}</div>
          </td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(u.email || '--')}</td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${roleBadgeClass}">${escapeHtml(u.role)}</span>
          </td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${statusBadgeClass}">${escapeHtml(u.account_status)}</span>
          </td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(u.campus || 'Central Campus')}</td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(createdStr)}</td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(activeStr)}</td>
          <td class="px-4 py-3 text-right">
            <button onclick="openUserActionModal('${escapeHtml(u.id)}')" class="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 rounded-lg text-[11px] transition cursor-pointer font-bold">
              Manage
            </button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  }

  if (pageInfo) {
    pageInfo.textContent = 'Page ' + adminState.users.page + ' of ' + Math.max(1, adminState.users.pages) + ' (' + adminState.users.total + ' total users)';
  }
  if (prevBtn) prevBtn.disabled = (adminState.users.page <= 1);
  if (nextBtn) nextBtn.disabled = (adminState.users.page >= adminState.users.pages);
}

function changeAdminUsersPage(delta) {
  var targetPage = adminState.users.page + delta;
  if (targetPage >= 1 && targetPage <= adminState.users.pages) {
    loadAdminUsers(targetPage);
  }
}

async function openUserActionModal(userId) {
  var modal = document.getElementById('adminUserModal');
  var bodyEl = document.getElementById('modalUserDetailBody');
  var nameEl = document.getElementById('modalUserName');
  var handleEl = document.getElementById('modalUserHandle');
  var btnStatus = document.getElementById('btnModalToggleStatus');
  var roleSelect = document.getElementById('modalRoleSelect');

  if (!modal || !bodyEl) return;

  bodyEl.innerHTML = '<p class="text-zinc-500">Loading user details...</p>';
  modal.classList.remove('hidden');

  var res = await adminApiRequest('/api/admin/users/' + userId);
  if (!res || !res.success || !res.user) {
    bodyEl.innerHTML = '<p class="text-red-400">Failed to load user details: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  var u = res.user;
  adminState.users.currentModalUser = u;

  if (nameEl) nameEl.textContent = u.name || 'User Details';
  if (handleEl) handleEl.textContent = '@' + u.handle;

  bodyEl.innerHTML = `
    <div class="grid grid-cols-2 gap-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl">
      <div><span class="text-zinc-500">User ID:</span> <span class="text-white font-bold">${escapeHtml(u.id)}</span></div>
      <div><span class="text-zinc-500">Email:</span> <span class="text-white font-bold">${escapeHtml(u.email)}</span></div>
      <div><span class="text-zinc-500">Role:</span> <span class="text-amber-400 font-bold">${escapeHtml(u.role)}</span></div>
      <div><span class="text-zinc-500">Account Status:</span> <span class="text-white font-bold">${escapeHtml(u.account_status)}</span></div>
      <div><span class="text-zinc-500">Campus:</span> <span class="text-white">${escapeHtml(u.campus || 'Central Campus')}</span></div>
      <div><span class="text-zinc-500">Active Sessions:</span> <span class="text-white font-bold">${res.active_sessions || 0}</span></div>
      <div><span class="text-zinc-500">Authenticity Score:</span> <span class="text-white">${u.authenticity_score || 100}</span></div>
      <div><span class="text-zinc-500">Streak Count:</span> <span class="text-white">${u.streak_count || 0}</span></div>
    </div>
  `;

  if (btnStatus) {
    if (u.account_status === 'suspended') {
      btnStatus.textContent = 'Restore Account';
      btnStatus.className = 'flex-1 px-3 py-2 bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 hover:bg-emerald-900/60 rounded-xl font-bold transition cursor-pointer';
    } else {
      btnStatus.textContent = 'Suspend Account';
      btnStatus.className = 'flex-1 px-3 py-2 bg-red-950/60 border border-red-500/40 text-red-400 hover:bg-red-900/60 rounded-xl font-bold transition cursor-pointer';
    }
  }

  if (roleSelect) {
    roleSelect.value = u.role || 'student';
  }
}

function closeAdminUserModal() {
  var modal = document.getElementById('adminUserModal');
  if (modal) modal.classList.add('hidden');
  adminState.users.currentModalUser = null;
  var reasonInput = document.getElementById('adminUserActionReason');
  if (reasonInput) reasonInput.value = '';
}

async function executeModalStatusChange() {
  var u = adminState.users.currentModalUser;
  if (!u) return;

  var targetStatus = u.account_status === 'suspended' ? 'active' : 'suspended';
  var actionVerb = targetStatus === 'suspended' ? 'suspend' : 'restore';
  var reason = (document.getElementById('adminUserActionReason')?.value || '').trim();

  if (!confirm('Are you sure you want to ' + actionVerb + ' user @' + u.handle + '?')) return;

  var res = await adminApiRequest('/api/admin/users/' + u.id + '/status', {
    method: 'POST',
    body: JSON.stringify({ status: targetStatus, reason: reason })
  });

  if (res && res.success) {
    alert('Account @' + u.handle + ' is now ' + res.account_status + '.' + (res.sessions_revoked ? ' Revoked ' + res.sessions_revoked + ' sessions.' : ''));
    closeAdminUserModal();
    loadAdminUsers();
  } else {
    alert('Action failed: ' + (res ? res.error : 'Unknown error'));
  }
}

async function executeModalRevokeSessions() {
  var u = adminState.users.currentModalUser;
  if (!u) return;

  if (!confirm('Are you sure you want to revoke all active sessions for @' + u.handle + '?')) return;

  var res = await adminApiRequest('/api/admin/users/' + u.id + '/revoke-sessions', {
    method: 'POST',
    body: JSON.stringify({})
  });

  if (res && res.success) {
    alert('Revoked ' + res.sessions_revoked + ' active sessions for @' + u.handle + '.');
    openUserActionModal(u.id);
  } else {
    alert('Failed to revoke sessions: ' + (res ? res.error : 'Unknown error'));
  }
}

async function executeModalRoleChange() {
  var u = adminState.users.currentModalUser;
  if (!u) return;

  var newRole = document.getElementById('modalRoleSelect')?.value;
  var reason = (document.getElementById('adminUserActionReason')?.value || '').trim();

  if (!newRole) return;
  if (!confirm('Are you sure you want to change @' + u.handle + '\'s role to ' + newRole + '?')) return;

  var res = await adminApiRequest('/api/admin/users/' + u.id + '/role', {
    method: 'POST',
    body: JSON.stringify({ role: newRole, reason: reason })
  });

  if (res && res.success) {
    alert('@' + u.handle + '\'s role is now ' + res.role + '.');
    closeAdminUserModal();
    loadAdminUsers();
  } else {
    alert('Role change failed: ' + (res ? res.error : 'Unknown error'));
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
