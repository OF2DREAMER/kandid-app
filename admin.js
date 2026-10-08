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
  } else if (tabId === 'content') {
    loadAdminPosts(1);
  } else if (tabId === 'clusters') {
    loadAdminClusters(1);
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

/* ==========================================================================
   PHASE D CONTENT & MOMENT CLUSTERS CLIENT CONTROLLER
   ========================================================================== */

adminState.posts = {
  page: 1,
  pages: 1,
  total: 0,
  items: [],
  currentModalPost: null
};

adminState.clusters = {
  page: 1,
  pages: 1,
  total: 0,
  items: [],
  currentModalCluster: null
};

async function loadAdminPosts(page) {
  page = page || adminState.posts.page || 1;
  var q = (document.getElementById('adminPostSearchInput')?.value || '').trim();
  var status = document.getElementById('adminPostStatusFilter')?.value || 'all';
  var visibility = document.getElementById('adminPostVisibilityFilter')?.value || 'all';

  var url = '/api/admin/posts?page=' + page + '&limit=25';
  if (q) url += '&q=' + encodeURIComponent(q);
  if (status && status !== 'all') url += '&status=' + encodeURIComponent(status);
  if (visibility && visibility !== 'all') url += '&visibility=' + encodeURIComponent(visibility);

  var tbody = document.getElementById('adminPostsTableBody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-zinc-500">Loading moments...</td></tr>';
  }

  var res = await adminApiRequest(url);
  if (!res || !res.success) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-red-400">Failed to load moments: ' + escapeHtml(res ? res.error : 'Unknown error') + '</td></tr>';
    }
    return;
  }

  adminState.posts.page = res.page;
  adminState.posts.pages = res.pages;
  adminState.posts.total = res.total;
  adminState.posts.items = res.posts || [];

  renderAdminPostsTable();
}

function renderAdminPostsTable() {
  var tbody = document.getElementById('adminPostsTableBody');
  var pageInfo = document.getElementById('adminPostsPageInfo');
  var prevBtn = document.getElementById('adminPostsPrevBtn');
  var nextBtn = document.getElementById('adminPostsNextBtn');
  if (!tbody) return;

  var items = adminState.posts.items;
  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-zinc-500">No moments found matching filters.</td></tr>';
  } else {
    var html = '';
    items.forEach(function(p) {
      var statusBadgeClass = p.moderation_status === 'removed'
        ? 'bg-red-500/20 text-red-400 border-red-500/30'
        : (p.moderation_status === 'hidden' ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30');

      var visBadgeClass = p.is_private
        ? 'bg-purple-500/20 text-purple-300 border-purple-500/30'
        : 'bg-zinc-800 text-zinc-400 border-zinc-700';

      var createdStr = p.created_at ? String(p.created_at).split('T')[0] : '--';
      var clusterBadge = p.cluster_id
        ? `<span class="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">Clustered</span>`
        : `<span class="text-[9px] text-zinc-600">Standalone</span>`;

      var mainThumb = p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-10 h-10 object-cover rounded-lg border border-zinc-800" alt="thumb">` : `<div class="w-10 h-10 bg-zinc-900 rounded-lg flex items-center justify-center text-zinc-600">📷</div>`;

      var captionText = p.caption ? (p.caption.length > 35 ? p.caption.substring(0, 35) + '...' : p.caption) : '<span class="text-zinc-600 italic">No caption</span>';

      html += `
        <tr class="hover:bg-zinc-900/50 transition">
          <td class="px-4 py-3">
            ${mainThumb}
          </td>
          <td class="px-4 py-3 font-bold text-white">
            ${escapeHtml(p.author_name || 'User')}
            <div class="text-[10px] text-amber-400 font-normal">@${escapeHtml(p.author_handle)}</div>
          </td>
          <td class="px-4 py-3 text-zinc-300 max-w-xs truncate" title="${escapeHtml(p.caption || '')}">
            ${escapeHtml(captionText)}
          </td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(p.campus || p.location_city || 'Central Campus')}</td>
          <td class="px-4 py-3">${clusterBadge}</td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${statusBadgeClass}">${escapeHtml(p.moderation_status)}</span>
          </td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${visBadgeClass}">${p.is_private ? 'Private' : 'Public'}</span>
          </td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(createdStr)}</td>
          <td class="px-4 py-3 text-right">
            <button onclick="openPostActionModal('${escapeHtml(p.id)}')" class="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 rounded-lg text-[11px] transition cursor-pointer font-bold">
              Inspect
            </button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  }

  if (pageInfo) {
    pageInfo.textContent = 'Page ' + adminState.posts.page + ' of ' + Math.max(1, adminState.posts.pages) + ' (' + adminState.posts.total + ' total moments)';
  }
  if (prevBtn) prevBtn.disabled = (adminState.posts.page <= 1);
  if (nextBtn) nextBtn.disabled = (adminState.posts.page >= adminState.posts.pages);
}

function changeAdminPostsPage(delta) {
  var targetPage = adminState.posts.page + delta;
  if (targetPage >= 1 && targetPage <= adminState.posts.pages) {
    loadAdminPosts(targetPage);
  }
}

async function openPostActionModal(postId) {
  var modal = document.getElementById('adminPostModal');
  var bodyEl = document.getElementById('modalPostDetailBody');
  var titleEl = document.getElementById('modalPostTitle');
  var subEl = document.getElementById('modalPostSubtitle');

  if (!modal || !bodyEl) return;

  bodyEl.innerHTML = '<p class="text-zinc-500">Loading moment details...</p>';
  modal.classList.remove('hidden');

  var res = await adminApiRequest('/api/admin/posts/' + postId);
  if (!res || !res.success || !res.post) {
    bodyEl.innerHTML = '<p class="text-red-400">Failed to load moment: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  var p = res.post;
  adminState.posts.currentModalPost = p;

  if (titleEl) titleEl.textContent = 'Moment Inspection: ' + (p.id || '');
  if (subEl) subEl.textContent = '@' + p.author_handle + ' (' + (p.author_name || 'User') + ')';

  var mainImg = p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-full h-44 object-cover rounded-xl border border-zinc-800" alt="Main">` : '';
  var pipImg = p.pip_img ? `<img src="${escapeHtml(p.pip_img)}" class="w-24 h-24 object-cover rounded-xl border border-zinc-700 shadow-lg absolute bottom-2 right-2" alt="PiP">` : '';

  bodyEl.innerHTML = `
    <div class="space-y-4">
      <div class="relative rounded-xl overflow-hidden bg-zinc-900 border border-zinc-800">
        ${mainImg}
        ${pipImg}
      </div>

      <div class="grid grid-cols-2 gap-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl">
        <div><span class="text-zinc-500">Moment ID:</span> <span class="text-white font-bold">${escapeHtml(p.id)}</span></div>
        <div><span class="text-zinc-500">Author:</span> <span class="text-amber-400 font-bold">@${escapeHtml(p.author_handle)}</span></div>
        <div><span class="text-zinc-500">Status:</span> <span class="text-white font-bold">${escapeHtml(p.moderation_status)}</span></div>
        <div><span class="text-zinc-500">Visibility:</span> <span class="text-white font-bold">${p.is_private ? 'Private' : 'Public'}</span></div>
        <div><span class="text-zinc-500">Campus:</span> <span class="text-white">${escapeHtml(p.campus || 'Central Campus')}</span></div>
        <div><span class="text-zinc-500">Reactions:</span> <span class="text-white font-bold">${res.reactions_count || 0}</span></div>
        <div><span class="text-zinc-500">Reports:</span> <span class="text-red-400 font-bold">${res.reports_count || 0}</span></div>
        <div><span class="text-zinc-500">Cluster ID:</span> <span class="text-amber-300">${escapeHtml(p.cluster_id || (res.cluster ? res.cluster.id : 'None'))}</span></div>
      </div>

      <div class="p-3 bg-zinc-900/40 border border-zinc-800 rounded-xl space-y-1">
        <span class="text-zinc-500 text-[10px] uppercase font-bold">Caption</span>
        <p class="text-zinc-200">${escapeHtml(p.caption || 'No caption provided.')}</p>
      </div>
    </div>
  `;
}

function closeAdminPostModal() {
  var modal = document.getElementById('adminPostModal');
  if (modal) modal.classList.add('hidden');
  adminState.posts.currentModalPost = null;
  var reasonInput = document.getElementById('adminPostActionReason');
  if (reasonInput) reasonInput.value = '';
}

async function executePostModeration(targetStatus) {
  var p = adminState.posts.currentModalPost;
  if (!p) return;

  var reason = (document.getElementById('adminPostActionReason')?.value || '').trim();
  if (!reason) {
    alert('Please enter a moderation reason for the audit log.');
    return;
  }

  if (!confirm('Are you sure you want to change moment ' + p.id + ' moderation status to ' + targetStatus + '?')) return;

  var res = await adminApiRequest('/api/admin/posts/' + p.id + '/moderation', {
    method: 'POST',
    body: JSON.stringify({ status: targetStatus, reason: reason })
  });

  if (res && res.success) {
    alert('Moment ' + p.id + ' status updated to ' + res.moderation_status + '.');
    closeAdminPostModal();
    loadAdminPosts();
  } else {
    alert('Moderation action failed: ' + (res ? res.error : 'Unknown error'));
  }
}

async function loadAdminClusters(page) {
  page = page || adminState.clusters.page || 1;
  var q = (document.getElementById('adminClusterSearchInput')?.value || '').trim();
  var status = document.getElementById('adminClusterStatusFilter')?.value || 'all';
  var visibility = document.getElementById('adminClusterVisibilityFilter')?.value || 'all';

  var url = '/api/admin/clusters?page=' + page + '&limit=25';
  if (q) url += '&q=' + encodeURIComponent(q);
  if (status && status !== 'all') url += '&status=' + encodeURIComponent(status);
  if (visibility && visibility !== 'all') url += '&visibility=' + encodeURIComponent(visibility);

  var tbody = document.getElementById('adminClustersTableBody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-zinc-500">Loading clusters...</td></tr>';
  }

  var res = await adminApiRequest(url);
  if (!res || !res.success) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-red-400">Failed to load clusters: ' + escapeHtml(res ? res.error : 'Unknown error') + '</td></tr>';
    }
    return;
  }

  adminState.clusters.page = res.page;
  adminState.clusters.pages = res.pages;
  adminState.clusters.total = res.total;
  adminState.clusters.items = res.clusters || [];

  renderAdminClustersTable();
}

function renderAdminClustersTable() {
  var tbody = document.getElementById('adminClustersTableBody');
  var pageInfo = document.getElementById('adminClustersPageInfo');
  var prevBtn = document.getElementById('adminClustersPrevBtn');
  var nextBtn = document.getElementById('adminClustersNextBtn');
  if (!tbody) return;

  var items = adminState.clusters.items;
  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-zinc-500">No clusters found matching filters.</td></tr>';
  } else {
    var html = '';
    items.forEach(function(c) {
      var statusBadgeClass = c.status === 'active'
        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
        : (c.status === 'closed' ? 'bg-zinc-800 text-zinc-300 border-zinc-700' : 'bg-amber-500/20 text-amber-300 border-amber-500/30');

      var createdStr = c.created_at ? String(c.created_at).split('T')[0] : '--';

      html += `
        <tr class="hover:bg-zinc-900/50 transition">
          <td class="px-4 py-3 font-bold text-white">
            ${escapeHtml(c.originating_context || 'Shared Moment')}
            <div class="text-[10px] text-zinc-500 font-mono font-normal">${escapeHtml(c.id)}</div>
          </td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(c.community_id || '--')}</td>
          <td class="px-4 py-3 text-amber-400">@${escapeHtml(c.author_handle || 'originator')}</td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">
              📸 ${c.perspectives_count || 0}
            </span>
          </td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/30">
              📍 ${c.participants_count || 0}
            </span>
          </td>
          <td class="px-4 py-3">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${statusBadgeClass}">${escapeHtml(c.status)}</span>
          </td>
          <td class="px-4 py-3 text-zinc-400 capitalize">${escapeHtml(c.visibility || 'public')}</td>
          <td class="px-4 py-3 text-zinc-400">${escapeHtml(createdStr)}</td>
          <td class="px-4 py-3 text-right">
            <button onclick="openClusterActionModal('${escapeHtml(c.id)}')" class="px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 rounded-lg text-[11px] transition cursor-pointer font-bold">
              Inspect
            </button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  }

  if (pageInfo) {
    pageInfo.textContent = 'Page ' + adminState.clusters.page + ' of ' + Math.max(1, adminState.clusters.pages) + ' (' + adminState.clusters.total + ' total clusters)';
  }
  if (prevBtn) prevBtn.disabled = (adminState.clusters.page <= 1);
  if (nextBtn) nextBtn.disabled = (adminState.clusters.page >= adminState.clusters.pages);
}

function changeAdminClustersPage(delta) {
  var targetPage = adminState.clusters.page + delta;
  if (targetPage >= 1 && targetPage <= adminState.clusters.pages) {
    loadAdminClusters(targetPage);
  }
}

async function openClusterActionModal(clusterId) {
  var modal = document.getElementById('adminClusterModal');
  var bodyEl = document.getElementById('modalClusterDetailBody');
  var titleEl = document.getElementById('modalClusterTitle');
  var subEl = document.getElementById('modalClusterSubtitle');
  var statusSelect = document.getElementById('modalClusterStatusSelect');

  if (!modal || !bodyEl) return;

  bodyEl.innerHTML = '<p class="text-zinc-500">Loading cluster details...</p>';
  modal.classList.remove('hidden');

  var res = await adminApiRequest('/api/admin/clusters/' + clusterId);
  if (!res || !res.success || !res.cluster) {
    bodyEl.innerHTML = '<p class="text-red-400">Failed to load cluster: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  var c = res.cluster;
  adminState.clusters.currentModalCluster = c;

  if (titleEl) titleEl.textContent = 'Cluster: ' + (c.originating_context || c.id);
  if (subEl) subEl.textContent = 'ID: ' + c.id + ' • Status: ' + c.status;
  if (statusSelect) statusSelect.value = c.status || 'active';

  var perspectivesHtml = '';
  if (res.perspectives && res.perspectives.length > 0) {
    perspectivesHtml = res.perspectives.map(function(p) {
      return `
        <div class="p-2 bg-zinc-950 border border-zinc-800 rounded-lg flex items-center gap-3">
          ${p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-10 h-10 object-cover rounded" alt="p">` : ''}
          <div class="flex-1 min-w-0">
            <div class="text-white font-bold text-xs">@${escapeHtml(p.author_handle)}</div>
            <div class="text-[11px] text-zinc-400 truncate">${escapeHtml(p.caption || 'Perspective')}</div>
          </div>
          <span class="text-[9px] px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400">${escapeHtml(p.moderation_status || 'active')}</span>
        </div>
      `;
    }).join('');
  } else {
    perspectivesHtml = '<p class="text-zinc-600 text-[11px] italic">No co-located perspectives recorded.</p>';
  }

  var participantsHtml = '';
  if (res.participants && res.participants.length > 0) {
    participantsHtml = res.participants.map(function(u) {
      return `<span class="px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[10px]">@${escapeHtml(u.handle)}</span>`;
    }).join(' ');
  } else {
    participantsHtml = '<p class="text-zinc-600 text-[11px] italic">No attendance records.</p>';
  }

  bodyEl.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl">
        <div><span class="text-zinc-500">Context:</span> <span class="text-white font-bold">${escapeHtml(c.originating_context || 'Event')}</span></div>
        <div><span class="text-zinc-500">Status:</span> <span class="text-white font-bold uppercase">${escapeHtml(c.status)}</span></div>
        <div><span class="text-zinc-500">Visibility:</span> <span class="text-white capitalize">${escapeHtml(c.visibility || 'public')}</span></div>
        <div><span class="text-zinc-500">Community:</span> <span class="text-amber-400">${escapeHtml(c.community_id || 'Global')}</span></div>
        <div><span class="text-zinc-500">Perspectives:</span> <span class="text-amber-300 font-bold">${res.perspectives_count || 0}</span></div>
        <div><span class="text-zinc-500">Attendees ("I Was There"):</span> <span class="text-blue-300 font-bold">${res.participants_count || 0}</span></div>
      </div>

      <div class="space-y-2">
        <span class="text-zinc-400 text-[10px] uppercase font-bold tracking-wider">Perspectives (${res.perspectives ? res.perspectives.length : 0})</span>
        <div class="max-h-40 overflow-y-auto space-y-2 pr-1">
          ${perspectivesHtml}
        </div>
      </div>

      <div class="space-y-2">
        <span class="text-zinc-400 text-[10px] uppercase font-bold tracking-wider">Verified Attendees (${res.participants ? res.participants.length : 0})</span>
        <div class="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
          ${participantsHtml}
        </div>
      </div>
    </div>
  `;
}

function closeAdminClusterModal() {
  var modal = document.getElementById('adminClusterModal');
  if (modal) modal.classList.add('hidden');
  adminState.clusters.currentModalCluster = null;
  var reasonInput = document.getElementById('adminClusterActionReason');
  if (reasonInput) reasonInput.value = '';
}

async function executeClusterStatusChange() {
  var c = adminState.clusters.currentModalCluster;
  if (!c) return;

  var newStatus = document.getElementById('modalClusterStatusSelect')?.value;
  var reason = (document.getElementById('adminClusterActionReason')?.value || '').trim();

  if (!newStatus) return;
  if (!reason) {
    alert('Please enter a reason for the cluster status change.');
    return;
  }

  if (!confirm('Are you sure you want to change cluster ' + c.id + ' status to ' + newStatus + '?')) return;

  var res = await adminApiRequest('/api/admin/clusters/' + c.id + '/status', {
    method: 'POST',
    body: JSON.stringify({ status: newStatus, reason: reason })
  });

  if (res && res.success) {
    alert('Cluster ' + c.id + ' status updated to ' + res.status + '.');
    closeAdminClusterModal();
    loadAdminClusters();
  } else {
    alert('Cluster status update failed: ' + (res ? res.error : 'Unknown error'));
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
