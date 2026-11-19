/**
 * KINDID ADMIN PANEL — STANDALONE CLIENT CONTROLLER
 * Phase A + B Implementation
 * Strictly isolated from consumer bundle (index.html / app_core.js).
 */

var adminState = {
  me: null,
  activeTab: 'overview',
  overview: null,
  health: null,
  pendingSudoRequest: null,
  temp2FaSecret: null
};

function getAuthToken() {
  try {
    return sessionStorage.getItem('kindid_admin_token') ||
           localStorage.getItem('kandid_token') ||
           localStorage.getItem('token') || '';
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

    // Step-Up Sudo Mode Interception
    if (data && data.requires_sudo === true) {
      return await handleSudoElevation(endpoint, options);
    }

    // Mandatory 2FA Interception
    if (data && data.requires_2fa_setup === true) {
      open2FaModal(true);
      return data;
    }

    if (response.status === 401 || response.status === 403) {
      if (endpoint === '/api/admin/me') {
        showAdminLoginGateway(data.error || 'Admin authentication required');
        return data;
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
    hideAdminLoginGateway();
    updateAdminHeaderIdentity(res.user);
    if (!res.user.admin_totp_enabled || res.user.force_2fa_setup) {
      open2FaModal(true);
      return;
    }
    loadAdminOverview();
  } else {
    showAdminLoginGateway(res ? res.error : '');
  }
}

function updateAdminHeaderIdentity(user) {
  var badge = document.getElementById('adminIdentityBadge');
  if (badge) {
    badge.innerHTML = 'Logged in as <span class="font-bold text-white">@' + escapeHtml(user.handle) + '</span> <span class="text-amber-400">(' + escapeHtml(user.role) + ')</span>';
  }

  var btn2FaHeader = document.getElementById('btnAdmin2FaHeader');
  var badge2FaStatus = document.getElementById('badge2FaHeaderStatus');
  if (btn2FaHeader) {
    btn2FaHeader.classList.remove('hidden');
    if (user.admin_totp_enabled) {
      badge2FaStatus.className = 'w-2 h-2 rounded-full bg-emerald-400 ring-2 ring-emerald-500/30';
      btn2FaHeader.title = 'Two-Factor Authentication: Active & Protected';
    } else {
      badge2FaStatus.className = 'w-2 h-2 rounded-full bg-amber-400 ring-2 ring-amber-500/30 animate-pulse';
      btn2FaHeader.title = 'Two-Factor Authentication: Disabled (Click to Setup)';
    }
  }
}

function showAdminLoginGateway(message) {
  var modal = document.getElementById('adminLoginGatewayModal');
  var alertEl = document.getElementById('adminLoginAlert');
  if (modal) {
    modal.classList.remove('hidden');
  }
  if (alertEl) {
    if (message) {
      alertEl.textContent = message;
      alertEl.classList.remove('hidden');
      triggerAppleShake('adminLoginGatewayModal');
    } else {
      alertEl.classList.add('hidden');
    }
  }
}

function hideAdminLoginGateway() {
  var modal = document.getElementById('adminLoginGatewayModal');
  if (modal) {
    modal.classList.add('hidden');
  }
}

function triggerAppleShake(modalId) {
  var modal = document.getElementById(modalId);
  if (!modal) return;
  var card = modal.querySelector('.apple-glass') || modal.firstElementChild;
  if (!card) return;
  card.classList.remove('apple-shake');
  void card.offsetWidth;
  card.classList.add('apple-shake');
  setTimeout(function() {
    card.classList.remove('apple-shake');
  }, 400);
}

function initAppleCodeDigitInputs() {
  document.querySelectorAll('.apple-code-digit').forEach(function(input) {
    input.addEventListener('input', function(e) {
      var val = e.target.value.replace(/\D/g, '');
      e.target.value = val ? val[0] : '';
      var targetId = e.target.getAttribute('data-target');
      var idx = parseInt(e.target.getAttribute('data-idx') || '0', 10);
      var parent = e.target.parentElement;
      if (val && idx < 5 && parent) {
        var next = parent.querySelector('[data-idx="' + (idx + 1) + '"]');
        if (next) next.focus();
      }
      var fullCode = syncAppleCodeDigits(parent, targetId);
      if (fullCode && fullCode.length === 6) {
        if (targetId === 'adminLoginTotpCode') {
          submitAdminLogin();
        } else if (targetId === 'admin2FaConfirmCode') {
          confirm2FaEnable();
        }
      }
    });

    input.addEventListener('keydown', function(e) {
      var targetId = e.target.getAttribute('data-target');
      var idx = parseInt(e.target.getAttribute('data-idx') || '0', 10);
      var parent = e.target.parentElement;
      if (e.key === 'Backspace') {
        if (!e.target.value && idx > 0 && parent) {
          var prev = parent.querySelector('[data-idx="' + (idx - 1) + '"]');
          if (prev) {
            prev.focus();
            prev.value = '';
          }
          syncAppleCodeDigits(parent, targetId);
        } else {
          setTimeout(function() { syncAppleCodeDigits(parent, targetId); }, 0);
        }
      } else if (e.key === 'ArrowLeft' && idx > 0 && parent) {
        var prevLeft = parent.querySelector('[data-idx="' + (idx - 1) + '"]');
        if (prevLeft) prevLeft.focus();
      } else if (e.key === 'ArrowRight' && idx < 5 && parent) {
        var nextRight = parent.querySelector('[data-idx="' + (idx + 1) + '"]');
        if (nextRight) nextRight.focus();
      }
    });

    input.addEventListener('paste', function(e) {
      e.preventDefault();
      var pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
      if (!pasted) return;
      var parent = e.target.parentElement;
      var targetId = e.target.getAttribute('data-target');
      if (!parent) return;
      var inputs = parent.querySelectorAll('.apple-code-digit');
      for (var i = 0; i < inputs.length && i < pasted.length; i++) {
        inputs[i].value = pasted[i];
      }
      var focusIdx = Math.min(pasted.length, 5);
      if (inputs[focusIdx]) inputs[focusIdx].focus();
      var fullCode = syncAppleCodeDigits(parent, targetId);
      if (fullCode && fullCode.length === 6) {
        if (targetId === 'adminLoginTotpCode') {
          submitAdminLogin();
        } else if (targetId === 'admin2FaConfirmCode') {
          confirm2FaEnable();
        }
      }
    });
  });
}

function syncAppleCodeDigits(parent, targetId) {
  if (!parent || !targetId) return '';
  var code = '';
  parent.querySelectorAll('.apple-code-digit').forEach(function(inp) {
    code += inp.value || '';
  });
  var target = document.getElementById(targetId);
  if (target) target.value = code;
  return code;
}

async function submitAdminLogin(event) {
  if (event) event.preventDefault();

  var handleInput = document.getElementById('adminLoginHandle');
  var passInput = document.getElementById('adminLoginPassword');
  var totpInput = document.getElementById('adminLoginTotpCode');
  var alertEl = document.getElementById('adminLoginAlert');
  var totpContainer = document.getElementById('adminLoginTotpContainer');
  var submitBtn = document.getElementById('btnAdminLoginSubmit');

  var handle = handleInput ? handleInput.value.trim() : '';
  var password = passInput ? passInput.value : '';
  var code = totpInput ? totpInput.value.trim() : '';

  if (!handle || !password) {
    if (alertEl) {
      alertEl.textContent = 'Please enter your username/email and password';
      alertEl.classList.remove('hidden');
      triggerAppleShake('adminLoginGatewayModal');
    }
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying...';
  }

  try {
    var response = await fetch('/api/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handle: handle, password: password, code: code })
    });
    var data = await response.json().catch(function() { return {}; });

    if (response.ok && data.success && data.token) {
      sessionStorage.setItem('kindid_admin_token', data.token);
      hideAdminLoginGateway();
      if (passInput) passInput.value = '';
      if (totpInput) totpInput.value = '';
      if (totpContainer) totpContainer.classList.add('hidden');
      document.querySelectorAll('#loginCodeDigitGroup .apple-code-digit').forEach(function(inp) { inp.value = ''; });
      await verifyAdminIdentity();
    } else if (data.totp_required) {
      if (totpContainer) totpContainer.classList.remove('hidden');
      var firstDigit = document.querySelector('#loginCodeDigitGroup [data-idx="0"]');
      if (firstDigit) {
        setTimeout(function() { firstDigit.focus(); }, 100);
      } else if (totpInput) {
        totpInput.focus();
        totpInput.required = true;
      }
      if (alertEl) {
        alertEl.textContent = data.error || 'Please enter your 6-digit authenticator code.';
        alertEl.classList.remove('hidden');
      }
    } else {
      if (alertEl) {
        alertEl.textContent = data.error || 'Login failed. Invalid admin credentials.';
        alertEl.classList.remove('hidden');
        triggerAppleShake('adminLoginGatewayModal');
      }
    }
  } catch (e) {
    if (alertEl) {
      alertEl.textContent = 'Network error connecting to login service.';
      alertEl.classList.remove('hidden');
      triggerAppleShake('adminLoginGatewayModal');
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Sign In';
    }
  }
}

function handleSudoElevation(endpoint, options) {
  return new Promise(function(resolve, reject) {
    adminState.pendingSudoRequest = {
      endpoint: endpoint,
      options: options,
      resolve: resolve,
      reject: reject
    };
    var modal = document.getElementById('adminSudoModal');
    var codeInput = document.getElementById('adminSudoCodeInput');
    var alertEl = document.getElementById('adminSudoAlert');
    if (alertEl) alertEl.classList.add('hidden');
    if (codeInput) {
      codeInput.value = '';
      setTimeout(function() { codeInput.focus(); }, 100);
    }
    if (modal) modal.classList.remove('hidden');
  });
}

async function submitAdminSudo(event) {
  if (event) event.preventDefault();

  var codeInput = document.getElementById('adminSudoCodeInput');
  var alertEl = document.getElementById('adminSudoAlert');
  var confirmBtn = document.getElementById('btnAdminSudoConfirm');
  var inputVal = codeInput ? codeInput.value.trim() : '';

  if (!inputVal) {
    if (alertEl) {
      alertEl.textContent = 'Please enter your 2FA code or password';
      alertEl.classList.remove('hidden');
      triggerAppleShake('adminSudoModal');
    }
    return;
  }

  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Verifying...';
  }

  var body = {};
  if (/^\d{6}$/.test(inputVal)) {
    body.code = inputVal;
  } else {
    body.password = inputVal;
  }

  var token = getAuthToken();
  var headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  try {
    var response = await fetch('/api/admin/auth/sudo-verify', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body)
    });
    var data = await response.json().catch(function() { return {}; });

    if (response.ok && data.success) {
      var modal = document.getElementById('adminSudoModal');
      if (modal) modal.classList.add('hidden');

      if (adminState.pendingSudoRequest) {
        var req = adminState.pendingSudoRequest;
        adminState.pendingSudoRequest = null;
        // Retry the original request with elevated privileges!
        var retryResult = await adminApiRequest(req.endpoint, req.options);
        req.resolve(retryResult);
      }
    } else {
      if (alertEl) {
        alertEl.textContent = data.error || 'Verification failed. Incorrect code or password.';
        alertEl.classList.remove('hidden');
        triggerAppleShake('adminSudoModal');
      }
    }
  } catch (e) {
    if (alertEl) {
      alertEl.textContent = 'Network error during sudo verification';
      alertEl.classList.remove('hidden');
      triggerAppleShake('adminSudoModal');
    }
  } finally {
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Authorize';
    }
  }
}

function cancelAdminSudo() {
  var modal = document.getElementById('adminSudoModal');
  if (modal) modal.classList.add('hidden');
  if (adminState.pendingSudoRequest) {
    var req = adminState.pendingSudoRequest;
    adminState.pendingSudoRequest = null;
    req.reject({ success: false, error: 'Sudo authentication cancelled by user' });
  }
}

async function open2FaModal(isMandatory) {
  var modal = document.getElementById('admin2FaModal');
  var activeView = document.getElementById('admin2FaActiveView');
  var setupView = document.getElementById('admin2FaSetupView');
  var alertEl = document.getElementById('admin2FaAlert');
  var mandatoryBanner = document.getElementById('admin2FaMandatoryBanner');
  var btnCloseTop = document.getElementById('btn2FaCloseTop');
  var btnCloseBottom = document.getElementById('btn2FaCloseBottom');
  var btnMandatoryLogout = document.getElementById('btn2FaMandatoryLogout');

  if (alertEl) alertEl.classList.add('hidden');

  // Reset 6-box TOTP passcode inputs
  document.querySelectorAll('#setupCodeDigitGroup .apple-code-digit').forEach(function(inp) { inp.value = ''; });
  var confirmHidden = document.getElementById('admin2FaConfirmCode');
  if (confirmHidden) confirmHidden.value = '';

  if (isMandatory) {
    if (mandatoryBanner) mandatoryBanner.classList.remove('hidden');
    if (btnCloseTop) btnCloseTop.classList.add('hidden');
    if (btnCloseBottom) btnCloseBottom.classList.add('hidden');
    if (btnMandatoryLogout) btnMandatoryLogout.classList.remove('hidden');
  } else {
    if (mandatoryBanner) mandatoryBanner.classList.add('hidden');
    if (btnCloseTop) btnCloseTop.classList.remove('hidden');
    if (btnCloseBottom) btnCloseBottom.classList.remove('hidden');
    if (btnMandatoryLogout) btnMandatoryLogout.classList.add('hidden');
  }

  if (adminState.me && adminState.me.admin_totp_enabled && !isMandatory) {
    if (activeView) activeView.classList.remove('hidden');
    if (setupView) setupView.classList.add('hidden');
    if (modal) modal.classList.remove('hidden');
  } else {
    if (activeView) activeView.classList.add('hidden');
    if (setupView) setupView.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');

    var secretEl = document.getElementById('admin2FaSecretDisplay');
    var linkEl = document.getElementById('admin2FaOtpauthLink');
    if (secretEl) secretEl.textContent = 'Generating security secret...';

    var res = await adminApiRequest('/api/admin/auth/2fa-setup');
    if (res && res.success && res.secret) {
      adminState.temp2FaSecret = res.secret;
      if (secretEl) secretEl.textContent = res.secret;
      if (linkEl) {
        linkEl.href = res.otpauth_url;
        linkEl.textContent = res.otpauth_url;
      }
      setTimeout(function() {
        var firstDigit = document.querySelector('#setupCodeDigitGroup [data-idx="0"]');
        if (firstDigit) firstDigit.focus();
      }, 150);
    } else {
      if (alertEl) {
        alertEl.textContent = 'Failed to generate 2FA secret: ' + (res ? res.error : 'Unknown');
        alertEl.classList.remove('hidden');
        triggerAppleShake('admin2FaModal');
      }
    }
  }
}

function close2FaModal() {
  var modal = document.getElementById('admin2FaModal');
  if (modal) modal.classList.add('hidden');
}

function copy2FaSecret() {
  var secret = adminState.temp2FaSecret || (document.getElementById('admin2FaSecretDisplay') ? document.getElementById('admin2FaSecretDisplay').textContent : '');
  if (secret && navigator.clipboard) {
    navigator.clipboard.writeText(secret).then(function() {
      alert('2FA Secret copied to clipboard!');
    }).catch(function() {
      prompt('Copy secret manually:', secret);
    });
  } else if (secret) {
    prompt('Copy secret manually:', secret);
  }
}

async function confirm2FaEnable() {
  var codeInput = document.getElementById('admin2FaConfirmCode');
  var alertEl = document.getElementById('admin2FaAlert');
  var code = codeInput ? codeInput.value.trim() : '';

  if (!code || code.length !== 6) {
    if (alertEl) {
      alertEl.textContent = 'Please enter a valid 6-digit confirmation code';
      alertEl.className = 'p-3.5 bg-red-500/10 border border-red-500/25 text-[#ff453a] text-xs rounded-2xl';
      alertEl.classList.remove('hidden');
      triggerAppleShake('admin2FaModal');
    }
    return;
  }

  var res = await adminApiRequest('/api/admin/auth/2fa-verify-enable', {
    method: 'POST',
    body: JSON.stringify({ secret: adminState.temp2FaSecret, code: code })
  });

  if (res && res.success) {
    if (adminState.me) adminState.me.admin_totp_enabled = true;
    updateAdminHeaderIdentity(adminState.me);
    var activeView = document.getElementById('admin2FaActiveView');
    var setupView = document.getElementById('admin2FaSetupView');
    var mandatoryBanner = document.getElementById('admin2FaMandatoryBanner');
    var btnCloseTop = document.getElementById('btn2FaCloseTop');
    var btnCloseBottom = document.getElementById('btn2FaCloseBottom');
    var btnMandatoryLogout = document.getElementById('btn2FaMandatoryLogout');

    if (mandatoryBanner) mandatoryBanner.classList.add('hidden');
    if (btnCloseTop) btnCloseTop.classList.remove('hidden');
    if (btnCloseBottom) btnCloseBottom.classList.remove('hidden');
    if (btnMandatoryLogout) btnMandatoryLogout.classList.add('hidden');

    if (setupView) setupView.classList.add('hidden');
    if (activeView) activeView.classList.remove('hidden');
    if (alertEl) {
      alertEl.textContent = 'Two-factor authentication successfully enabled! Unlocking admin control surfaces...';
      alertEl.className = 'p-3.5 bg-[#30d158]/10 border border-[#30d158]/25 text-[#30d158] text-xs rounded-2xl';
      alertEl.classList.remove('hidden');
    }

    setTimeout(function() {
      close2FaModal();
      loadAdminOverview();
    }, 1200);
  } else {
    if (alertEl) {
      alertEl.textContent = res ? res.error : 'Failed to verify code';
      alertEl.className = 'p-3.5 bg-red-500/10 border border-red-500/25 text-[#ff453a] text-xs rounded-2xl';
      alertEl.classList.remove('hidden');
      triggerAppleShake('admin2FaModal');
    }
  }
}

function renderAccessDenied(message) {
  showAdminLoginGateway(message);
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
      <div class="p-5 apple-card rounded-2xl border border-white/10 space-y-2.5">
        <span class="text-[#86868b] text-[11px] font-semibold uppercase tracking-wider">Database Status</span>
        <p class="text-sm font-semibold text-[#30d158] flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-[#30d158] animate-pulse"></span>STATUS: ${escapeHtml(res.status || 'OK').toUpperCase()}
        </p>
        <p class="text-xs text-[#86868b]">Engine: <span class="text-white font-medium">${escapeHtml(res.db_engine || 'sqlite')}</span></p>
        <p class="text-xs text-[#86868b]">Latency: <span class="text-white font-medium">${res.db_latency_ms || 0} ms</span></p>
      </div>

      <div class="p-5 apple-card rounded-2xl border border-white/10 space-y-2.5">
        <span class="text-[#86868b] text-[11px] font-semibold uppercase tracking-wider">Active Sessions & Telemetry</span>
        <p class="text-xs text-[#86868b]">Active User Sessions: <span class="text-white font-semibold">${res.active_sessions || 0}</span></p>
        <p class="text-xs text-[#86868b]">Environment: <span class="text-[#30d158] font-semibold uppercase">${escapeHtml(res.environment || 'production')}</span></p>
        <p class="text-xs text-[#86868b]">Service Version: <span class="text-white font-medium">${escapeHtml(res.version || 'v5.2.2')}</span></p>
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
        ? 'bg-red-500/15 text-[#ff453a] border border-red-500/25'
        : 'bg-[#30d158]/15 text-[#30d158] border border-[#30d158]/25';
      var roleBadgeClass = u.role === 'founder'
        ? 'bg-[#ff9f0a]/15 text-[#ffd60a] border border-[#ff9f0a]/25'
        : (u.role === 'admin' ? 'bg-[#bf5af2]/15 text-[#bf5af2] border border-[#bf5af2]/25' : 'bg-white/10 text-white/80 border border-white/15');

      var createdStr = u.created_at ? String(u.created_at).split('T')[0] : '--';
      var activeStr = u.last_active ? String(u.last_active).split('T')[0] : 'Never';

      html += `
        <tr class="hover:bg-white/[0.04] transition">
          <td class="px-5 py-3.5 font-medium text-white">
            ${escapeHtml(u.name || 'User')}
            <div class="text-[11px] text-[#2997ff] font-normal">@${escapeHtml(u.handle)}</div>
          </td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(u.email || '--')}</td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${roleBadgeClass}">${escapeHtml(u.role)}</span>
          </td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${statusBadgeClass}">${escapeHtml(u.account_status)}</span>
          </td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(u.campus || 'Central Campus')}</td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(createdStr)}</td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(activeStr)}</td>
          <td class="px-5 py-3.5 text-right">
            <button onclick="openUserActionModal('${escapeHtml(u.id)}')" class="px-3.5 py-1.5 apple-btn-secondary rounded-full text-xs font-medium transition cursor-pointer">
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

  bodyEl.innerHTML = '<p class="text-[#86868b]">Loading user details...</p>';
  modal.classList.remove('hidden');

  var res = await adminApiRequest('/api/admin/users/' + userId);
  if (!res || !res.success || !res.user) {
    bodyEl.innerHTML = '<p class="text-[#ff453a]">Failed to load user details: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  var u = res.user;
  adminState.users.currentModalUser = u;

  if (nameEl) nameEl.textContent = u.name || 'User Details';
  if (handleEl) handleEl.textContent = '@' + u.handle;

  bodyEl.innerHTML = `
    <div class="grid grid-cols-2 gap-3 p-4 apple-card rounded-2xl border border-white/10 text-xs">
      <div><span class="text-[#86868b]">User ID:</span> <span class="text-white font-medium">${escapeHtml(u.id)}</span></div>
      <div><span class="text-[#86868b]">Email:</span> <span class="text-white font-medium">${escapeHtml(u.email)}</span></div>
      <div><span class="text-[#86868b]">Role:</span> <span class="text-[#ffd60a] font-semibold">${escapeHtml(u.role)}</span></div>
      <div><span class="text-[#86868b]">Account Status:</span> <span class="text-white font-semibold">${escapeHtml(u.account_status)}</span></div>
      <div><span class="text-[#86868b]">Campus:</span> <span class="text-white">${escapeHtml(u.campus || 'Central Campus')}</span></div>
      <div><span class="text-[#86868b]">Active Sessions:</span> <span class="text-[#30d158] font-semibold">${res.active_sessions || 0}</span></div>
      <div><span class="text-[#86868b]">Authenticity Score:</span> <span class="text-white">${u.authenticity_score || 100}</span></div>
      <div><span class="text-[#86868b]">Streak Count:</span> <span class="text-white">${u.streak_count || 0}</span></div>
    </div>
  `;

  if (btnStatus) {
    if (u.account_status === 'suspended') {
      btnStatus.textContent = 'Restore Account';
      btnStatus.className = 'flex-1 py-2.5 apple-btn-success rounded-full text-xs font-medium transition cursor-pointer';
    } else {
      btnStatus.textContent = 'Suspend Account';
      btnStatus.className = 'flex-1 py-2.5 apple-btn-danger rounded-full text-xs font-medium transition cursor-pointer';
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
        ? 'bg-red-500/15 text-[#ff453a] border border-red-500/25'
        : (p.moderation_status === 'hidden' ? 'bg-[#ff9f0a]/15 text-[#ffd60a] border border-[#ff9f0a]/25' : 'bg-[#30d158]/15 text-[#30d158] border border-[#30d158]/25');

      var visBadgeClass = p.is_private
        ? 'bg-[#bf5af2]/15 text-[#bf5af2] border border-[#bf5af2]/25'
        : 'bg-white/10 text-white/70 border border-white/15';

      var createdStr = p.created_at ? String(p.created_at).split('T')[0] : '--';
      var clusterBadge = p.cluster_id
        ? `<span class="text-[10px] px-2 py-0.5 rounded-full bg-[#ff9f0a]/15 text-[#ffd60a] border border-[#ff9f0a]/30 font-medium">Clustered</span>`
        : `<span class="text-[11px] text-[#86868b]">Standalone</span>`;

      var mainThumb = p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-10 h-10 object-cover rounded-xl border border-white/10 shadow-sm" alt="thumb">` : `<div class="w-10 h-10 bg-white/5 rounded-xl border border-white/10 flex items-center justify-center text-xs text-[#86868b]">📷</div>`;

      var captionText = p.caption ? (p.caption.length > 35 ? p.caption.substring(0, 35) + '...' : p.caption) : '<span class="text-[#86868b] italic">No caption</span>';

      html += `
        <tr class="hover:bg-white/[0.04] transition">
          <td class="px-5 py-3.5">
            ${mainThumb}
          </td>
          <td class="px-5 py-3.5 font-medium text-white">
            ${escapeHtml(p.author_name || 'User')}
            <div class="text-[11px] text-[#2997ff] font-normal">@${escapeHtml(p.author_handle)}</div>
          </td>
          <td class="px-5 py-3.5 text-[#e5e5ea] max-w-xs truncate" title="${escapeHtml(p.caption || '')}">
            ${escapeHtml(captionText)}
          </td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(p.campus || p.location_city || 'Central Campus')}</td>
          <td class="px-5 py-3.5">${clusterBadge}</td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${statusBadgeClass}">${escapeHtml(p.moderation_status)}</span>
          </td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${visBadgeClass}">${p.is_private ? 'Private' : 'Public'}</span>
          </td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(createdStr)}</td>
          <td class="px-5 py-3.5 text-right">
            <button onclick="openPostActionModal('${escapeHtml(p.id)}')" class="px-3.5 py-1.5 apple-btn-secondary rounded-full text-xs font-medium transition cursor-pointer">
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

  bodyEl.innerHTML = '<p class="text-[#86868b]">Loading moment details...</p>';
  modal.classList.remove('hidden');

  var res = await adminApiRequest('/api/admin/posts/' + postId);
  if (!res || !res.success || !res.post) {
    bodyEl.innerHTML = '<p class="text-[#ff453a]">Failed to load moment: ' + escapeHtml(res ? res.error : 'Unknown error') + '</p>';
    return;
  }

  var p = res.post;
  adminState.posts.currentModalPost = p;

  if (titleEl) titleEl.textContent = 'Moment Inspection: ' + (p.id || '');
  if (subEl) subEl.textContent = '@' + p.author_handle + ' (' + (p.author_name || 'User') + ')';

  var mainImg = p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-full h-44 object-cover rounded-2xl border border-white/10 shadow-inner" alt="Main">` : '';
  var pipImg = p.pip_img ? `<img src="${escapeHtml(p.pip_img)}" class="w-24 h-24 object-cover rounded-2xl border-2 border-white/20 shadow-2xl absolute bottom-3 right-3" alt="PiP">` : '';

  bodyEl.innerHTML = `
    <div class="space-y-4">
      <div class="relative rounded-2xl overflow-hidden bg-black/60 border border-white/10">
        ${mainImg}
        ${pipImg}
      </div>

      <div class="grid grid-cols-2 gap-3 p-4 apple-card rounded-2xl border border-white/10 text-xs">
        <div><span class="text-[#86868b]">Moment ID:</span> <span class="text-white font-medium">${escapeHtml(p.id)}</span></div>
        <div><span class="text-[#86868b]">Author:</span> <span class="text-[#2997ff] font-medium">@${escapeHtml(p.author_handle)}</span></div>
        <div><span class="text-[#86868b]">Status:</span> <span class="text-white font-semibold">${escapeHtml(p.moderation_status)}</span></div>
        <div><span class="text-[#86868b]">Visibility:</span> <span class="text-white font-semibold">${p.is_private ? 'Private' : 'Public'}</span></div>
        <div><span class="text-[#86868b]">Campus:</span> <span class="text-white">${escapeHtml(p.campus || 'Central Campus')}</span></div>
        <div><span class="text-[#86868b]">Reactions:</span> <span class="text-white font-medium">${res.reactions_count || 0}</span></div>
        <div><span class="text-[#86868b]">Reports:</span> <span class="text-[#ff453a] font-semibold">${res.reports_count || 0}</span></div>
        <div><span class="text-[#86868b]">Cluster ID:</span> <span class="text-[#ffd60a]">${escapeHtml(p.cluster_id || (res.cluster ? res.cluster.id : 'None'))}</span></div>
      </div>

      <div class="p-3.5 apple-card rounded-2xl border border-white/10 space-y-1">
        <span class="text-[#86868b] text-[10px] uppercase font-semibold">Caption</span>
        <p class="text-[#e5e5ea] text-xs">${escapeHtml(p.caption || 'No caption provided.')}</p>
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
        ? 'bg-[#30d158]/15 text-[#30d158] border border-[#30d158]/25'
        : (c.status === 'closed' ? 'bg-white/10 text-white/70 border border-white/15' : 'bg-[#ff9f0a]/15 text-[#ffd60a] border border-[#ff9f0a]/25');

      var createdStr = c.created_at ? String(c.created_at).split('T')[0] : '--';

      html += `
        <tr class="hover:bg-white/[0.04] transition">
          <td class="px-5 py-3.5 font-medium text-white">
            ${escapeHtml(c.originating_context || 'Shared Moment')}
            <div class="text-[11px] text-[#86868b] font-mono font-normal">${escapeHtml(c.id)}</div>
          </td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(c.community_id || '--')}</td>
          <td class="px-5 py-3.5 text-[#2997ff] font-medium">@${escapeHtml(c.author_handle || 'originator')}</td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-[#ff9f0a]/15 text-[#ffd60a] border border-[#ff9f0a]/30">
              📸 ${c.perspectives_count || 0}
            </span>
          </td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-[#0071e3]/15 text-[#2997ff] border border-[#0071e3]/30">
              📍 ${c.participants_count || 0}
            </span>
          </td>
          <td class="px-5 py-3.5">
            <span class="text-[10px] font-semibold px-2.5 py-0.5 rounded-full ${statusBadgeClass}">${escapeHtml(c.status)}</span>
          </td>
          <td class="px-5 py-3.5 text-[#86868b] capitalize">${escapeHtml(c.visibility || 'public')}</td>
          <td class="px-5 py-3.5 text-[#86868b]">${escapeHtml(createdStr)}</td>
          <td class="px-5 py-3.5 text-right">
            <button onclick="openClusterActionModal('${escapeHtml(c.id)}')" class="px-3.5 py-1.5 apple-btn-secondary rounded-full text-xs font-medium transition cursor-pointer">
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
        <div class="p-3 apple-card rounded-xl border border-white/10 flex items-center gap-3">
          ${p.main_img ? `<img src="${escapeHtml(p.main_img)}" class="w-10 h-10 object-cover rounded-xl border border-white/10" alt="p">` : ''}
          <div class="flex-1 min-w-0">
            <div class="text-white font-medium text-xs">@${escapeHtml(p.author_handle)}</div>
            <div class="text-[11px] text-[#86868b] truncate">${escapeHtml(p.caption || 'Perspective')}</div>
          </div>
          <span class="text-[10px] px-2 py-0.5 rounded-full border border-white/10 text-[#86868b] font-medium">${escapeHtml(p.moderation_status || 'active')}</span>
        </div>
      `;
    }).join('');
  } else {
    perspectivesHtml = '<p class="text-[#86868b] text-xs italic">No co-located perspectives recorded.</p>';
  }

  var participantsHtml = '';
  if (res.participants && res.participants.length > 0) {
    participantsHtml = res.participants.map(function(u) {
      return `<span class="px-2.5 py-1 rounded-full bg-white/10 border border-white/10 text-[#e5e5ea] text-[10px] font-medium">@${escapeHtml(u.handle)}</span>`;
    }).join(' ');
  } else {
    participantsHtml = '<p class="text-[#86868b] text-xs italic">No attendance records.</p>';
  }

  bodyEl.innerHTML = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-3 p-4 apple-card rounded-2xl border border-white/10 text-xs">
        <div><span class="text-[#86868b]">Context:</span> <span class="text-white font-medium">${escapeHtml(c.originating_context || 'Event')}</span></div>
        <div><span class="text-[#86868b]">Status:</span> <span class="text-white font-semibold uppercase">${escapeHtml(c.status)}</span></div>
        <div><span class="text-[#86868b]">Visibility:</span> <span class="text-white capitalize">${escapeHtml(c.visibility || 'public')}</span></div>
        <div><span class="text-[#86868b]">Community:</span> <span class="text-[#2997ff] font-medium">${escapeHtml(c.community_id || 'Global')}</span></div>
        <div><span class="text-[#86868b]">Perspectives:</span> <span class="text-[#ffd60a] font-semibold">${res.perspectives_count || 0}</span></div>
        <div><span class="text-[#86868b]">Attendees:</span> <span class="text-[#2997ff] font-semibold">${res.participants_count || 0}</span></div>
      </div>

      <div class="space-y-2">
        <span class="text-[#86868b] text-[11px] uppercase font-semibold tracking-wider">Perspectives (${res.perspectives ? res.perspectives.length : 0})</span>
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

async function logoutAdmin() {
  try {
    var token = getAuthToken();
    var headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    await fetch('/api/admin/auth/logout', { method: 'POST', headers: headers }).catch(function() {});
  } catch (e) {}

  try {
    sessionStorage.removeItem('kindid_admin_token');
    localStorage.removeItem('kandid_token');
    localStorage.removeItem('token');
    localStorage.removeItem('kandid_user');
  } catch (e) {}

  window.location.href = '/admin';
}

document.addEventListener('DOMContentLoaded', function() {
  initAppleCodeDigitInputs();
  verifyAdminIdentity();
});
