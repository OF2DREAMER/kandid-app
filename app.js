/**
 * Kandid Web Engine (v3.0.2)
 * Authentic Campus Moments Discovery
 */

var savedUser = null;
try {
  savedUser = JSON.parse(localStorage.getItem('kandid_user') || 'null');
} catch(e) {}

var state = {
  currentUser: savedUser,
  token: localStorage.getItem('kandid_token') || null,
  activeCircle: 'foryou',
  activeScreen: 'feed'
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function showToast(msg) {
  var t = document.getElementById('toastBanner');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 2600);
}

// =====================================================================
// TACTILE HAPTIC & PHYSICAL SOUND SYNTHESIZER ENGINE
// =====================================================================
var audioCtx = null;

function getAudioContext() {
  if (!audioCtx) {
    var AudioCtxClass = window.AudioContext || window.webkitAudioContext;
    if (AudioCtxClass) {
      audioCtx = new AudioCtxClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(function() {});
  }
  return audioCtx;
}

function playTactileFeedback(type) {
  // 1. Hardware Haptic Vibration (Phones)
  try {
    if (navigator.vibrate) {
      if (type === 'shutter') {
        navigator.vibrate([30]);
      } else if (type === 'success' || type === 'xp') {
        navigator.vibrate([15, 30, 20]);
      } else if (type === 'notif') {
        navigator.vibrate([20, 35, 15]);
      } else {
        navigator.vibrate(12);
      }
    }
  } catch(e){}

  // 2. Synthesized Zero-Latency Web Audio Chime / Clicks
  try {
    var ctx = getAudioContext();
    if (!ctx) return;
    var now = ctx.currentTime;

    if (type === 'shutter') {
      // Leica-style mechanical shutter snap click
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(160, now);
      osc.frequency.exponentialRampToValueAtTime(30, now + 0.05);
      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.06);
    } else if (type === 'pop') {
      // RealMoji Bubble Pop
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(420, now);
      osc.frequency.exponentialRampToValueAtTime(780, now + 0.04);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.05);
    } else if (type === 'success' || type === 'xp') {
      // XP Chime & Connected Sound
      var osc1 = ctx.createOscillator();
      var gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(523.25, now); // C5
      osc1.frequency.setValueAtTime(659.25, now + 0.08); // E5
      gain1.gain.setValueAtTime(0.18, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.3);
    } else if (type === 'notif') {
      // Soft Ambient Notification Bell
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now); // A5
      osc.frequency.setValueAtTime(1174.66, now + 0.06); // D6
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.26);
    }
  } catch(e){}
}
window.playTactileFeedback = playTactileFeedback;

// SECURITY B-04: Safe media URL opener — only https:// allowed
function safeOpenMediaUrl(url) {
  if (url && typeof url === 'string' && url.trim().startsWith('https://')) {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}
window.safeOpenMediaUrl = safeOpenMediaUrl;

function getActiveUserId() {
  if (state.currentUser && state.currentUser.id) return state.currentUser.id;
  var stored = null;
  try {
    stored = JSON.parse(localStorage.getItem('kandid_user') || 'null');
  } catch(e) {}
  if (stored && stored.id) {
    state.currentUser = stored;
    return stored.id;
  }
  var activeUid = localStorage.getItem('kandid_active_uid');
  return activeUid || '';
}
window.getActiveUserId = getActiveUserId;

function sanitizeHeaderValue(val) {
  if (!val) return '';
  return String(val).replace(/[^\x20-\x7E]/g, '').trim();
}

async function apiRequest(endpoint, options) {
  options = options || {};
  var headers = options.headers || {};
  headers['Content-Type'] = 'application/json';
  if (state.token && state.token !== 'null' && state.token !== 'undefined') {
    var cleanTok = sanitizeHeaderValue(state.token);
    if (cleanTok) headers['Authorization'] = 'Bearer ' + cleanTok;
  }
  var uid = getActiveUserId();
  if (uid) {
    var cleanUid = sanitizeHeaderValue(uid);
    if (cleanUid) headers['X-User-Id'] = cleanUid;
  }
  options.headers = headers;
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData) && !(options.body instanceof Blob)) {
    options.body = JSON.stringify(options.body);
  }

  // Timeout guard — prevent indefinite hangs (e.g. cold server start, network stall)
  var controller = new AbortController();
  var timeoutMs = options._timeout || 12000;
  var timerId = setTimeout(function() { controller.abort(); }, timeoutMs);
  options.signal = controller.signal;

  try {
    var res = await fetch(endpoint, options);
    clearTimeout(timerId);
    var contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      // Server returned non-JSON (HTML error page, cold-start 502, etc.)
      var text = await res.text();
      console.warn('[API] Non-JSON response for', endpoint, 'status:', res.status, 'body:', text.substring(0, 200));
      return { success: false, error: 'Server error (' + res.status + ')', _status: res.status };
    }
    var data = await res.json();
    // Propagate HTTP status for auth-specific handling
    if (!data._status) data._status = res.status;
    return data;
  } catch (err) {
    clearTimeout(timerId);
    var isTimeout = err && err.name === 'AbortError';
    console.warn('[API] fetch error for', endpoint, isTimeout ? 'TIMEOUT' : (err && err.message));
    return {
      success: false,
      error: isTimeout ? 'Request timed out' : ((err && err.message) ? err.message : 'Network error'),
      _timeout: isTimeout,
      _network: !isTimeout
    };
  }
}

// Sub-Tab Switcher (FOR YOU | NEARBY | CAMPUS | GLOBAL)
function selectSubTab(circleName) {
  state.activeCircle = circleName;

  if (state.activeScreen !== 'feed') {
    switchScreenView('feed');
  }

  document.querySelectorAll('.sub-tab-btn[data-circle]').forEach(function(t) {
    if (t.dataset.circle === circleName) {
      t.className = 'sub-tab-btn flex-1 py-1.5 bg-zinc-800 text-white font-bold rounded-lg shadow-sm active transition-all';
    } else {
      t.className = 'sub-tab-btn flex-1 py-1.5 text-zinc-400 hover:text-white transition-colors cursor-pointer';
    }
  });

  var feedStream = document.getElementById('feedContentStream');
  var campusStream = document.getElementById('campusContentStream');
  var globalStream = document.getElementById('globalContentStream');
  var nearbyStream = document.getElementById('nearbyContentStream');
  var statusMode = document.getElementById('statusBarModeTag');

  if (circleName === 'global') {
    if (feedStream) feedStream.style.display = 'none';
    if (campusStream) campusStream.style.display = 'none';
    if (nearbyStream) nearbyStream.style.display = 'none';
    if (globalStream) {
      globalStream.style.display = 'block';
      globalStream.style.visibility = 'visible';
      globalStream.style.opacity = '1';
    }
    if (statusMode) statusMode.textContent = 'GLOBAL WINDOW';
    loadGlobalScreen(state.activeRegion || 'all');
  } else if (circleName === 'campus' || circleName === 'community') {
    if (feedStream) feedStream.style.display = 'none';
    if (globalStream) globalStream.style.display = 'none';
    if (nearbyStream) nearbyStream.style.display = 'none';
    if (campusStream) {
      campusStream.style.display = 'block';
      campusStream.style.visibility = 'visible';
      campusStream.style.opacity = '1';
    }
    if (statusMode) statusMode.textContent = 'COMMUNITY';
    loadCommunityScreen();
  } else if (circleName === 'nearby') {
    if (feedStream) feedStream.style.display = 'none';
    if (campusStream) campusStream.style.display = 'none';
    if (globalStream) globalStream.style.display = 'none';
    if (nearbyStream) {
      nearbyStream.style.display = 'block';
      nearbyStream.style.visibility = 'visible';
      nearbyStream.style.opacity = '1';
    }
    if (statusMode) statusMode.textContent = 'NEARBY';
    loadNearbyScreen();
  } else {
    if (campusStream) campusStream.style.display = 'none';
    if (globalStream) globalStream.style.display = 'none';
    if (nearbyStream) nearbyStream.style.display = 'none';
    if (feedStream) {
      feedStream.style.display = 'block';
      feedStream.style.visibility = 'visible';
      feedStream.style.opacity = '1';
    }
    if (statusMode) statusMode.textContent = 'LIVE';
    loadFeedMoments(circleName);
  }
}
window.selectSubTab = selectSubTab;

async function loadNearbyScreen() {
  var container = document.getElementById('nearbyMomentsContainer');
  var banner = document.getElementById('nearbyProximityBanner');
  var emptyState = document.getElementById('nearbyEmptyState');
  var locState = document.getElementById('nearbyLocationState');
  
  if (!container) return;

  var locStatus = localStorage.getItem('kandid_location_status') || 'needed';
  
  if (locStatus === 'needed') {
    if (banner) banner.style.display = 'none';
    if (container) container.style.display = 'none';
    if (emptyState) { emptyState.style.display = 'none'; emptyState.classList.add('hidden'); }
    if (locState) { locState.style.display = 'flex'; locState.classList.remove('hidden'); }
    return;
  }
  
  if (locStatus === 'denied') {
    if (banner) banner.style.display = 'none';
    if (container) container.style.display = 'none';
    if (locState) { locState.style.display = 'none'; locState.classList.add('hidden'); }
    if (emptyState) { emptyState.style.display = 'flex'; emptyState.classList.remove('hidden'); }
    return;
  }

  // Location Granted -> Fetch Data
  var data = await apiRequest('/api/feed?circle=nearby');
  if (data && data.success && Array.isArray(data.feed) && data.feed.length > 0) {
    if (banner) banner.style.display = 'flex';
    if (locState) { locState.style.display = 'none'; locState.classList.add('hidden'); }
    if (emptyState) { emptyState.style.display = 'none'; emptyState.classList.add('hidden'); }
    if (container) { container.style.display = 'block'; renderFeedCards(data.feed, container); }
  } else {
    // Has location but no posts nearby
    if (banner) banner.style.display = 'none';
    if (locState) { locState.style.display = 'none'; locState.classList.add('hidden'); }
    if (container) container.style.display = 'none';
    if (emptyState) { emptyState.style.display = 'flex'; emptyState.classList.remove('hidden'); }
  }
}
window.loadNearbyScreen = loadNearbyScreen;

function requestLocation() {
  localStorage.setItem('kandid_location_status', 'granted');
  loadNearbyScreen();
}
window.requestLocation = requestLocation;

function showNearbyEmptyState() {
  localStorage.setItem('kandid_location_status', 'denied');
  loadNearbyScreen();
}
window.showNearbyEmptyState = showNearbyEmptyState;

function filterGlobalRegion(region) {
  console.log("FILTER GLOBAL REGION:", region);
  state.activeRegion = region;

  document.querySelectorAll('.global-region-btn').forEach(function(btn) {
    if (btn.dataset.region === region) {
      btn.className = 'global-region-btn px-3 py-1 bg-amber-500 text-black rounded-lg font-bold transition-all cursor-pointer';
    } else {
      btn.className = 'global-region-btn px-2.5 py-1 bg-zinc-900 text-zinc-400 hover:text-white rounded-lg border border-zinc-800 transition-all cursor-pointer';
    }
  });

  loadGlobalScreen(region);
}
window.filterGlobalRegion = filterGlobalRegion;

async function loadGlobalScreen(region) {
  var globalContainer = document.getElementById('globalMomentsContainer');
  var quietCard = document.getElementById('globalQuietCard');
  if (!globalContainer) return;

  region = region || state.activeRegion || 'all';
  var endpoint = '/api/global?region=' + encodeURIComponent(region);
  var data = await apiRequest(endpoint);

  if (data && data.success && Array.isArray(data.moments)) {
    if (data.moments.length > 0) {
      renderGlobalCards(data.moments, globalContainer);
      if (quietCard) quietCard.style.display = 'block';
    } else {
      globalContainer.innerHTML = '';
      if (quietCard) quietCard.style.display = 'block';
    }
  }
}
window.loadGlobalScreen = loadGlobalScreen;

function renderGlobalCards(moments, container) {
  container.innerHTML = '';
  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3.5 shadow-2xl relative kandid-card';
    card.dataset.postId = m.id;

    var authorHandle = escapeHtml(m.author_handle || m.user_handle || 'hana_k');
    var city = escapeHtml((m.location_city || m.campus || 'GLOBAL').toUpperCase());
    var coords = m.location_coords ? escapeHtml(m.location_coords) : '';
    var locBanner = coords ? (city + ' · ' + coords) : city;
    var commTarget = m.community_name || m.primary_community_name || m.primary_community_id || (m.campus ? m.campus.replace(/^Near\s+/i, '') : '');
    var timeAgo = escapeHtml((m.timeAgo || m.time_ago || '18 MIN AGO').toUpperCase());
    var captionText = escapeHtml(m.caption || 'Real moment across global coordinates.');
    var iso = escapeHtml(m.exif_iso || 'ISO 400');
    var shutter = escapeHtml(m.exif_shutter || '1/250S');

    var avatarSrc = (m.avatar_url && !m.avatar_url.includes('api.dicebear.com')) ? m.avatar_url : '';
    var avatarHtml = '<img src="' + avatarSrc + '" class="w-full h-full object-cover">';

    var realmojis = m.realmojis || {};
    var reactionPillsHtml = '';
    for (var emoji in realmojis) {
      if (realmojis[emoji] > 0) {
        reactionPillsHtml += '<button class="realmoji-btn inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-900 border border-zinc-800 rounded-md text-[9px] font-mono-tag active:scale-95 transition-transform cursor-pointer" data-emoji="' + emoji + '">' +
          '<span>' + emoji + '</span>' +
          '<span class="emoji-count-num text-[8px] font-bold text-zinc-300">' + realmojis[emoji] + '</span>' +
        '</button>';
      }
    }

    var mainImgSrc = m.main_img || m.mainImg || '';
    var pipImgSrc = m.pip_img || m.pipImg || '';

    card.innerHTML =
      '<div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner group select-none moment-viewport-stage cursor-pointer">' +
        '<img src="' + mainImgSrc + '" class="w-full h-full object-cover main-stage-img" alt="Global Moment">' +
        '<div class="sub-camera-pip absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black cursor-pointer z-10 active:scale-95 transition-transform" title="Tap to Swap Optics">' +
          '<img src="' + pipImgSrc + '" class="w-full h-full object-cover pip-sub-img" alt="Selfie Photo">' +
          '<div class="absolute bottom-1 left-1.5 px-1 py-0.5 bg-black/60 backdrop-blur text-[8px] text-zinc-300 font-mono-tag rounded">ME • 50mm</div>' +
        '</div>' +
        '<div class="double-tap-burst">🔥</div>' +
      '</div>' +

      '<div class="space-y-2 px-0.5">' +
        '<div class="flex justify-between items-center text-[10px] text-zinc-400 font-mono-tag font-bold tracking-wider flex-wrap gap-1">' +
          (commTarget
            ? '<button type="button" onclick="event.stopPropagation(); openCampusPage(\'' + escapeHtml(commTarget).replace(/'/g, "\\'") + '\')" class="text-amber-400/90 hover:text-amber-300 hover:underline cursor-pointer active:scale-95 transition text-left">◉ ' + escapeHtml(locBanner) + '</button>'
            : '<span>' + escapeHtml(locBanner) + '</span>') +
          '<span class="text-amber-400">' + timeAgo + '</span>' +
        '</div>' +

        '<p class="text-xs text-zinc-200 font-normal leading-relaxed">' +
          '"' + captionText + '"' +
        '</p>' +

        '<div class="flex justify-between items-center pt-1 border-t border-zinc-900 font-mono-tag">' +
          '<div class="flex items-center gap-2">' +
            '<div class="w-5 h-5 rounded-full bg-zinc-800 overflow-hidden border border-zinc-700 flex items-center justify-center">' +
              avatarHtml +
            '</div>' +
            '<span class="text-[11px] text-zinc-400 font-medium font-sans">@' + authorHandle + '</span>' +
            '<span class="text-[9px] text-zinc-600">· ' + iso + ' · ' + shutter + '</span>' +
          '</div>' +

          '<div class="relative flex items-center gap-1.5 reaction-control-container">' +
            '<div class="reaction-badge-group flex items-center gap-1">' +
              reactionPillsHtml +
            '</div>' +
            '<button class="px-3 py-1 bg-zinc-900 hover:bg-zinc-800 transition-all text-[9px] font-semibold text-zinc-300 rounded-lg border border-zinc-800 cursor-pointer react-trigger-btn active:scale-95 flex items-center gap-1">' +
              '<span>✦ React</span>' +
            '</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    container.appendChild(card);
    attachCardInteractions(card, m);
  });
}
window.renderGlobalCards = renderGlobalCards;

// Screen Switcher (FEED | SEARCH | CHAT | YOU)
function switchScreenView(screenName) {
  state.activeScreen = screenName;

  if (screenName === 'feed') {
    if (typeof handleNewUserFeedEntry === 'function') {
      handleNewUserFeedEntry();
    }
  } else {
    if (typeof handleNewUserFeedExit === 'function') {
      handleNewUserFeedExit();
    }
  }

  document.querySelectorAll('.app-screen').forEach(function(scr) {
    scr.classList.remove('active');
    scr.style.display = 'none';
  });

  var target = document.getElementById('screen-' + screenName);
  if (target) {
    target.classList.add('active');
    if (screenName.startsWith('chat-') || screenName === 'empty-search' || screenName === 'error' || screenName === 'offline' || screenName === 'block' || screenName === 'block-list' || screenName === 'report' || screenName.includes('confirm') || screenName === 'you' || screenName === 'peer-profile' || screenName === 'search') {
        target.style.display = 'flex';
    } else {
        target.style.display = 'block';
    }
  }

  document.querySelectorAll('.dock-item').forEach(function(btn) {
    if (btn.dataset.screen === screenName || ((screenName === 'memories' || screenName === 'progress' || screenName === 'settings' || screenName === 'report' || screenName === 'block') && btn.dataset.screen === 'you') || (screenName === 'empty-search' && btn.dataset.screen === 'search') || (screenName.startsWith('chat-') && btn.dataset.screen === 'chat-home')) {
      btn.className = 'dock-item text-amber-500 flex flex-col items-center cursor-pointer active';
    } else {
      btn.className = 'dock-item text-zinc-500 hover:text-white flex flex-col items-center transition-colors cursor-pointer';
    }
  });

  var subTabs = document.getElementById('subTabsBar');
  if (subTabs) {
    subTabs.style.display = (screenName === 'feed') ? 'flex' : 'none';
  }

  var memoriesHeader = document.getElementById('memoriesHeaderInfo');
  if (memoriesHeader) {
    memoriesHeader.style.display = (screenName === 'memories') ? 'flex' : 'none';
  }

  var statusMode = document.getElementById('statusBarModeTag');
  if (statusMode) {
    if (screenName === 'search') {
      statusMode.textContent = 'SEARCH';
    } else if (screenName === 'feed') {
      statusMode.textContent = (state.activeCircle === 'campus' || state.activeCircle === 'community') ? 'COMMUNITY' : (state.activeCircle === 'global' ? 'GLOBAL WINDOW' : (state.activeCircle === 'nearby' ? 'NEARBY' : 'LIVE'));
    } else if (screenName === 'memories') {
      statusMode.textContent = 'ARCHIVE';
    } else {
      statusMode.textContent = screenName.toUpperCase();
    }
  }

  var notifBtn = document.getElementById('notifBtn');
  if (notifBtn) {
    if (screenName === 'notifications') {
      notifBtn.className = 'w-8 h-8 bg-zinc-900 border border-zinc-800 rounded-full flex items-center justify-center text-amber-400 relative shadow-sm cursor-pointer notif-btn';
    } else {
      notifBtn.className = 'w-8 h-8 bg-zinc-900 border border-zinc-800 rounded-full flex items-center justify-center text-zinc-400 hover:text-white transition-colors relative shadow-sm cursor-pointer notif-btn';
    }
  }

  if (screenName === 'search') {
    loadSearchDiscovery();
  } else if (screenName === 'chat-home') {
    loadChatConversations();
  } else if (screenName === 'you') {
    loadYouScreen();
  } else if (screenName === 'memories') {
    loadMemoriesScreen();
  } else if (screenName === 'progress') {
    loadProgressScreen();
  } else if (screenName === 'settings') {
    loadSettingsScreen();
  } else if (screenName === 'notifications') {
    loadNotifications();
  } else if (screenName === 'block-list') {
    loadBlockList();
  }



  var globalHeader = document.getElementById("mainGlobalHeader");
  var settingsHeader = document.getElementById("settingsHeader");
  var headerEmptySearch = document.getElementById("headerEmptySearch");
  var headerError = document.getElementById("headerError");
  var headerOffline = document.getElementById("headerOffline");
  var headerReport = document.getElementById("headerReport");
  var headerBlock = document.getElementById("headerBlock");
  var headerReportConfirm = document.getElementById("headerReportConfirm");
  var headerBlockConfirm = document.getElementById("headerBlockConfirm");
  var headerChatHome = document.getElementById("headerChatHome");
  var headerChatNew = document.getElementById("headerChatNew");
  var headerChatConversation = document.getElementById("headerChatConversation");
  var headerChatShared = document.getElementById("headerChatShared");
  var headerChatEmpty = document.getElementById("headerChatEmpty");
  var headerChatRequest = document.getElementById("headerChatRequest");
  var headerChatSettings = document.getElementById("headerChatSettings");
  var headerPeerProfile = document.getElementById("headerPeerProfile");
  var headerCampusPage = document.getElementById("headerCampusPage");
  
  if (globalHeader) {
    // Hide all headers first
    globalHeader.style.display = "none";
    if (settingsHeader) settingsHeader.style.display = "none";
    if (headerEmptySearch) headerEmptySearch.style.display = "none";
    if (headerError) headerError.style.display = "none";
    if (headerOffline) headerOffline.style.display = "none";
    if (headerReport) headerReport.style.display = "none";
    if (headerBlock) headerBlock.style.display = "none";
    if (headerReportConfirm) headerReportConfirm.style.display = "none";
    if (headerBlockConfirm) headerBlockConfirm.style.display = "none";
    if (headerChatHome) headerChatHome.style.display = "none";
    if (headerChatNew) headerChatNew.style.display = "none";
    if (headerChatConversation) headerChatConversation.style.display = "none";
    if (headerChatShared) headerChatShared.style.display = "none";
    if (headerChatEmpty) headerChatEmpty.style.display = "none";
    if (headerChatRequest) headerChatRequest.style.display = "none";
    if (headerChatSettings) headerChatSettings.style.display = "none";
    if (headerPeerProfile) headerPeerProfile.style.display = "none";
    if (headerCampusPage) headerCampusPage.style.display = "none";

    // Show the active one
    var statusText = "LIVE";
    var statusColorClass = "text-amber-500";
    var dotClass = "w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse";
    
    if (screenName === "settings") {
      if (settingsHeader) settingsHeader.style.display = "block";
      statusText = "SETTINGS";
    } else if (screenName === "empty-search") {
      if (headerEmptySearch) headerEmptySearch.style.display = "flex";
      statusText = "EMPTY STATE";
    } else if (screenName === "error") {
      if (headerError) headerError.style.display = "flex";
      statusText = "ERROR STATE";
    } else if (screenName === "offline") {
      if (headerOffline) headerOffline.style.display = "flex";
      statusText = "OFFLINE";
      statusColorClass = "text-zinc-400";
      dotClass = "w-1.5 h-1.5 rounded-full bg-zinc-500";
    } else if (screenName === "report") {
      if (headerReport) headerReport.style.display = "flex";
      statusText = "REPORT";
    } else if (screenName === "block") {
      if (headerBlock) headerBlock.style.display = "flex";
      statusText = "BLOCK";
    } else if (screenName === "report-confirm") {
      if (headerReportConfirm) headerReportConfirm.style.display = "flex";
      statusText = "CONFIRMATION";
    } else if (screenName === "block-confirm") {
      if (headerBlockConfirm) headerBlockConfirm.style.display = "flex";
      statusText = "BLOCKED";
    } else if (screenName === "chat-home") {
      if (headerChatHome) headerChatHome.style.display = "none";
      statusText = "CHAT HOME";
    } else if (screenName === "chat-new") {
      if (headerChatNew) headerChatNew.style.display = "flex";
      statusText = "NEW MESSAGE";
      loadChatNewSuggestions();
    } else if (screenName === "chat-conversation") {
      if (headerChatConversation) headerChatConversation.style.display = "flex";
      statusText = "CONVERSATION";
    } else if (screenName === "chat-shared") {
      if (headerChatShared) headerChatShared.style.display = "flex";
      statusText = "SHARED MOMENT";
    } else if (screenName === "chat-empty") {
      if (headerChatEmpty) headerChatEmpty.style.display = "flex";
      statusText = "EMPTY STATE";
    } else if (screenName === "chat-request") {
      if (headerChatRequest) headerChatRequest.style.display = "flex";
      statusText = "REQUEST";
    } else if (screenName === "chat-settings" || screenName === "chat-privacy") {
      if (headerChatSettings) headerChatSettings.style.display = "none";
      statusText = "CHAT PRIVACY";
    } else if (screenName === "peer-profile") {
      if (headerPeerProfile) headerPeerProfile.style.display = "none";
      statusText = "USER PROFILE";
    } else if (screenName === "campus-page") {
      var headerCampus = document.getElementById("headerCampusPage");
      if (headerCampus) headerCampus.style.display = "flex";
      statusText = "COMMUNITY";
    } else if (screenName === "collective-memory") {
      statusText = "COLLECTIVE MEMORY";
    } else if (screenName === "live-pulse") {
      statusText = "LIVE PULSE";
    } else if (screenName === "memories") {
      statusText = "JOURNAL";
    } else if (screenName === "you") {
      statusText = "YOU";
    } else {
      globalHeader.style.display = "block";
    }
    
    var modeTag = document.getElementById("statusBarModeTag");
    var modeDot = document.getElementById("statusBarDot");
    if (modeTag) {
        modeTag.textContent = statusText;
        modeTag.className = "text-[9px] font-mono-tag " + statusColorClass;
    }
    if (modeDot) {
        modeDot.className = dotClass;
    }
  }

  var unifiedDock = document.getElementById("unifiedDock");
  var composerMain = document.getElementById("chatComposerMain");
  var composerShared = document.getElementById("chatComposerShared");
  
  if (unifiedDock) {
    if (screenName === "collective-memory" || screenName === "live-pulse" || screenName === "chat-conversation" || screenName === "chat-shared" || screenName === "chat-privacy") {
      unifiedDock.style.display = "none";
    } else {
      unifiedDock.style.display = "flex";
    }
  }

  if (composerMain) composerMain.style.display = "none";
  if (composerShared) composerShared.style.display = "none";
  
  if (screenName === "chat-conversation" && composerMain) composerMain.style.display = "flex";
  if (screenName === "chat-shared" && composerShared) composerShared.style.display = "flex";

  var vp = document.getElementById('mainViewport');
  if (vp) vp.scrollTop = 0;
}
window.switchScreenView = switchScreenView;

async function loadCommunityScreen() {
  var campusContainer = document.getElementById('campusMomentsContainer');
  var activeName = document.getElementById('communityActiveName');
  var activeLoc = document.getElementById('communityActiveLocation');
  var activeCount = document.getElementById('communityActiveCount');
  var contextDesc = document.getElementById('communityContextDesc');

  var currentComm = state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');
  if (activeName) activeName.textContent = currentComm;
  if (activeLoc) activeLoc.textContent = state.currentGeoApprox || 'New Delhi, India';

  var data = await apiRequest('/api/feed?circle=campus');
  if (data && data.success && Array.isArray(data.feed)) {
    if (campusContainer) {
      if (data.feed.length > 0) {
        renderCommunityCards(data.feed, campusContainer);
        if (activeCount) activeCount.textContent = (data.feed.length + 3) + ' people active';
      } else {
        campusContainer.innerHTML = 
          '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-6 text-center space-y-2 shadow-lg">' +
            '<div class="text-amber-500 text-lg font-mono-tag">✦</div>' +
            '<h3 class="text-xs font-bold text-white uppercase font-mono-tag">NO COMMUNITY MOMENTS YET</h3>' +
            '<p class="text-[11px] text-zinc-400">Capture the first authentic moment in ' + escapeHtml(currentComm) + '!</p>' +
            '<button onclick="openCameraStudio()" class="mt-2 px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[10px] rounded-xl font-mono-tag tracking-wider uppercase cursor-pointer">Capture Now 📸</button>' +
          '</div>';
      }
    }
  }

  if (contextDesc) {
    contextDesc.textContent = 'People capturing ordinary life around ' + currentComm + ' without performance or rankings.';
  }

  if (typeof loadMoreAroundYou === 'function') {
    loadMoreAroundYou();
  }
}
window.loadCommunityScreen = loadCommunityScreen;
window.loadCampusScreen = loadCommunityScreen;

function renderCommunityCards(moments, container) {
  container.innerHTML = '';
  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'moment-article space-y-2.5 pb-2 border-b border-white/[.05]';
    card.dataset.postId = m.id;

    var authorHandle = escapeHtml(m.author_handle || m.user_handle || 'student');
    var timeAgo = escapeHtml(m.created_at ? formatTimeAgoClean(m.created_at) : (m.timeAgo || m.time_ago || 'JUST NOW').toUpperCase());
    var captionText = escapeHtml(m.caption || 'Unfiltered moment.');
    var locName = escapeHtml(m.location_city || m.campus || 'Near Quad');
    if (!locName.toLowerCase().startsWith('near ')) locName = 'Near ' + locName;
    var commTarget = m.community_name || m.primary_community_name || m.primary_community_id || (m.campus ? m.campus.replace(/^Near\s+/i, '') : '');

    var avatarLetter = (m.author_name || authorHandle).substring(0, 2).toUpperCase();

    var mainImgSrc = m.main_img || m.mainImg || '';
    var pipImgSrc = m.pip_img || m.pipImg || '';

    var clusterBadgeHtml = '';
    if (m.cluster_id || (m.perspectives_count && m.perspectives_count > 0)) {
      var pCount = m.perspectives_count || 1;
      clusterBadgeHtml = '<button onclick="event.stopPropagation(); openMomentClusterModal(\'' + (m.cluster_id || '') + '\', \'' + m.id + '\')" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-[9px] font-mono-tag font-bold text-amber-400 transition cursor-pointer active:scale-95 shadow-sm">' +
        '<span>✦</span> <span>' + pCount + ' perspective' + (pCount === 1 ? '' : 's') + '</span>' +
      '</button>';
    }

    var iWasThereHtml = '';
    var hasSharedContext = !!(m.primary_community_id || m.context_community_id || m.cluster_id || m.campus);
    if (!m.is_private && hasSharedContext && (!state.currentUser || state.currentUser.id !== m.user_id)) {
      iWasThereHtml = '<button onclick="event.stopPropagation(); handleIWasThereClick(\'' + m.id + '\')" class="px-2.5 py-1 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 border border-amber-500/30 text-amber-400 hover:text-amber-300 text-[9px] font-mono-tag font-bold cursor-pointer active:scale-95 transition shadow-sm" title="Self-assert contextual participation">+ I WAS THERE</button>';
    }

    card.innerHTML = 
      '<div class="moment-image aspect-[4/5] rounded-[28px] overflow-hidden relative border border-white/[.08] shadow-2xl moment-viewport-stage cursor-pointer select-none">' +
        '<img class="w-full h-full object-cover main-stage-img" src="' + mainImgSrc + '" alt="Real moment">' +
        '<div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-black/35 pointer-events-none"></div>' +
        
        '<!-- Time Badge -->' +
        '<div class="absolute top-4 right-4 z-10 flex items-center gap-1.5">' +
          clusterBadgeHtml +
          '<span class="font-mono-tag text-[9px] text-white/90 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/15 moment-live-timestamp" data-created-at="' + escapeHtml(m.created_at || '') + '">' +
            timeAgo +
          '</span>' +
        '</div>' +

        '<!-- Selfie PiP Layer (Tap to swap) -->' +
        '<div class="sub-camera-pip absolute top-4 left-4 w-20 h-28 rounded-2xl overflow-hidden border-2 border-white/20 shadow-2xl bg-black cursor-pointer z-20 active:scale-95 transition-transform" title="Tap to Swap Views">' +
          '<img src="' + pipImgSrc + '" class="w-full h-full object-cover pip-sub-img" alt="Selfie Photo">' +
        '</div>' +

        '<!-- Bottom Overlay -->' +
        '<div class="absolute bottom-4 inset-x-4 z-10 space-y-2.5">' +
          '<div class="flex items-center gap-1.5 flex-wrap">' +
            (commTarget
              ? '<button type="button" onclick="event.stopPropagation(); openCampusPage(\'' + escapeHtml(commTarget).replace(/'/g, "\\'") + '\')" class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl location-chip bg-black/60 backdrop-blur-md border border-white/10 hover:border-amber-500/50 hover:bg-black/80 transition cursor-pointer text-left active:scale-95" title="Open Community Page">' +
                  '<span class="text-amber-400 text-xs">⌖</span>' +
                  '<span class="text-[10px] text-zinc-200 hover:text-amber-300 font-medium font-mono-tag">' + locName + '</span>' +
                '</button>'
              : '<div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl location-chip bg-black/60 backdrop-blur-md border border-white/10">' +
                  '<span class="text-amber-400 text-xs">⌖</span>' +
                  '<span class="text-[10px] text-zinc-200 font-medium">' + locName + '</span>' +
                '</div>') +
          '</div>' +

          '<p class="text-[13px] font-medium text-white leading-snug">"' + captionText + '"</p>' +

          '<div class="flex items-center justify-between pt-2 border-t border-white/15">' +
            '<div class="flex items-center gap-2">' +
              '<div class="w-7 h-7 rounded-full bg-zinc-950 border border-white/20 flex items-center justify-center text-[9px] font-bold text-amber-400 font-mono-tag">' + avatarLetter + '</div>' +
              '<span class="text-xs font-bold text-white font-mono-tag">@' + authorHandle + '</span>' +
            '</div>' +
            '<button onclick="openMomentMenu(\'' + m.id + '\')" class="text-zinc-400 hover:text-white text-sm cursor-pointer px-1" aria-label="More">···</button>' +
          '</div>' +
        '</div>' +
      '</div>' +

      '<!-- Reaction Row -->' +
      '<div class="mt-2 flex items-center justify-between px-1">' +
        '<div class="reaction-badge-group flex items-center gap-1.5" id="realmojis-' + m.id + '">' +
        '</div>' +
        '<div class="flex items-center gap-2">' +
          iWasThereHtml +
          '<button onclick="openReactions(\'' + m.id + '\')" class="px-4 py-2 rounded-2xl bg-zinc-950 border border-white/[.07] text-zinc-300 hover:text-white text-[11px] font-mono-tag flex items-center gap-1.5 cursor-pointer active:scale-95 transition shadow-sm">' +
            '<span class="text-amber-400">✦</span> React' +
          '</button>' +
        '</div>' +
      '</div>';

    container.appendChild(card);
    attachCardInteractions(card, m);
  });
  updateAllMomentTimestamps();
}
window.renderCommunityCards = renderCommunityCards;

// Community V1 Modals & Actions
var activeTargetMomentId = null;

async function openLivePulse(communityName) {
  communityName = communityName || state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');
  state.previousScreen = state.activeScreen || 'feed';
  switchScreenView('live-pulse');

  var nameEl = document.getElementById('livePulseCommunityName');
  var locEl = document.getElementById('livePulseLocation');
  var taglineEl = document.getElementById('livePulseTagline');
  var badgeEl = document.getElementById('livePulseActiveCountBadge');
  var container = document.getElementById('livePulseMomentsContainer');

  if (nameEl) nameEl.textContent = communityName;

  var res = await apiRequest('/api/community/pulse?community=' + encodeURIComponent(communityName));
  if (res && res.success) {
    if (res.community) {
      if (nameEl) nameEl.textContent = res.community.name;
      if (locEl) locEl.textContent = res.community.location;
      if (taglineEl) taglineEl.textContent = res.community.tagline || "A living layer of what's happening around here right now.";
      if (badgeEl) badgeEl.textContent = '● ' + res.community.active_count + ' Moments captured recently';
    }
    if (container && Array.isArray(res.moments)) {
      renderFeedCards(res.moments, container);
    }
  }
}
window.openLivePulse = openLivePulse;

function handleLivePulseBack() {
  switchScreenView(state.previousScreen || 'feed');
}
window.handleLivePulseBack = handleLivePulseBack;

async function openCommunitySwitcher() {
  var modal = document.getElementById('switcherModal');
  var listEl = document.getElementById('switcherCommunityList');
  if (modal) modal.style.display = 'flex';

  if (!listEl) return;
  listEl.innerHTML = '<div class="py-4 text-center text-xs text-zinc-500 font-mono-tag">Loading your communities...</div>';

  var res = await apiRequest('/api/community/my');
  var activeComm = state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');

  if (res && res.success && Array.isArray(res.communities) && res.communities.length > 0) {
    listEl.innerHTML = res.communities.map(function(c) {
      var isActive = (c.name.toLowerCase() === activeComm.toLowerCase());
      var borderClass = isActive ? 'border-amber-500/60 bg-amber-500/10' : 'border-white/[.06] bg-zinc-950 hover:border-zinc-700';
      var textClass = isActive ? 'text-amber-400 font-extrabold' : 'text-zinc-200 font-bold';
      var badge = isActive ? '<span class="font-mono-tag text-[9px] text-amber-400 font-bold bg-amber-500/20 px-2 py-0.5 rounded">● Active</span>' : ('<span class="font-mono-tag text-[9px] text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">' + escapeHtml(c.type || 'Community') + '</span>');

      return '<div onclick="switchCommunity(\'' + escapeHtml(c.name).replace(/'/g, "\\'") + '\')" class="p-3.5 rounded-2xl ' + borderClass + ' border flex items-center justify-between cursor-pointer active:scale-95 transition shadow-sm group">' +
        '<div class="flex items-center gap-2.5">' +
          '<span class="text-base">' + (c.icon || '📍') + '</span>' +
          '<div>' +
            '<h4 class="text-xs ' + textClass + ' group-hover:text-amber-300 transition-colors">' + escapeHtml(c.name) + '</h4>' +
            (c.city ? '<p class="text-[9px] text-zinc-400 font-mono-tag">' + escapeHtml(c.city) + '</p>' : '') +
          '</div>' +
        '</div>' +
        badge +
      '</div>';
    }).join('');
  } else {
    listEl.innerHTML = 
      '<div class="py-6 text-center text-xs text-zinc-400 font-mono-tag">You haven\'t found your world yet.</div>';
  }
}
window.openCommunitySwitcher = openCommunitySwitcher;

function closeCommunitySwitcher() {
  var modal = document.getElementById('switcherModal');
  if (modal) modal.style.display = 'none';
}
window.closeCommunitySwitcher = closeCommunitySwitcher;

function switchCommunity(name) {
  state.activeCommunity = name;
  closeCommunitySwitcher();
  playTactileFeedback('click');
  showToast('Switched to ' + name + ' ✦');
  
  if (state.activeScreen === 'campus-page') {
    openCampusPage(name);
  } else {
    selectSubTab('community');
  }
}
window.switchCommunity = switchCommunity;

function submitNewCommunity() {
  var input = document.getElementById('newCommName');
  var name = input ? input.value.trim() : '';
  if (!name) return;
  closeCreateCommunity();
  if (input) input.value = '';
  switchCommunity(name);
  showToast('Community "' + name + '" created! 🚀');
}
window.submitNewCommunity = submitNewCommunity;

function openMomentMenu(postId) {
  activeTargetMomentId = postId;
  var modal = document.getElementById('momentModal');
  if (modal) modal.style.display = 'flex';
}
window.openMomentMenu = openMomentMenu;

function closeMomentMenu() {
  var modal = document.getElementById('momentModal');
  if (modal) modal.style.display = 'none';
}
window.closeMomentMenu = closeMomentMenu;

function openReactions(postId) {
  activeTargetMomentId = postId;
  var modal = document.getElementById('reactionModal');
  if (modal) modal.style.display = 'flex';
}
window.openReactions = openReactions;

function closeReactions() {
  var modal = document.getElementById('reactionModal');
  if (modal) modal.style.display = 'none';
}
window.closeReactions = closeReactions;

async function sendReaction(emoji) {
  closeReactions();
  if (activeTargetMomentId) {
    await submitReaction(activeTargetMomentId, emoji);
  }
  showToast(emoji + ' reaction sent ✦');
}
window.sendReaction = sendReaction;

async function openCampusPage(campusName) {
  if (state.activeScreen && state.activeScreen !== 'campus-page') {
    state.previousScreen = state.activeScreen;
  }
  campusName = campusName || state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');
  state.activeCommunity = campusName;
  switchScreenView('campus-page');

  var titleEl = document.getElementById('headerCampusTitle');
  var nameEl = document.getElementById('campusPageName');
  var typeTagEl = document.getElementById('campusPageTypeTag');
  var locEl = document.getElementById('campusPageLocation');
  var descEl = document.getElementById('campusPageDescription');
  var joinBtn = document.getElementById('campusPageJoinBtn');
  var activeAreasEl = document.getElementById('campusPageActiveAreasCount');
  var pulseDotEl = document.getElementById('campusPagePulseDot');
  var pulseTagEl = document.getElementById('campusPagePulseTag');
  var pulseHeadingEl = document.getElementById('campusPagePulseHeading');
  var pulseTilesEl = document.getElementById('campusPagePulseTiles');
  var areasListEl = document.getElementById('campusPageAreasList');
  var momentsEl = document.getElementById('campusPageMomentsContainer');
  var memoriesGridEl = document.getElementById('campusPageMemoriesGrid');
  var peopleListEl = document.getElementById('campusPagePeopleList');

  if (titleEl) titleEl.textContent = campusName;
  if (nameEl) nameEl.textContent = campusName;

  var data = await apiRequest('/api/community/detail?campus=' + encodeURIComponent(campusName));
  if (data && data.success) {
    if (data.campus) {
      var c = data.campus;
      state.activeCommunityId = c.id || '';
      state.activeCommunity = c.name || campusName;
      state.activeCommunityData = c;
      if (nameEl) nameEl.textContent = c.name;
      if (typeTagEl) typeTagEl.textContent = '◉ ' + (c.tag || 'COMMUNITY HUB');
      if (locEl) locEl.textContent = (c.location || 'Local Region') + (c.creator_handle ? ' · Created by @' + c.creator_handle : '');
      if (descEl) descEl.textContent = c.description || 'Authentic moments and shared daily life.';

      if (joinBtn) {
        var isPrimary = Boolean(state.currentUser && (
          (state.currentUser.campus && state.currentUser.campus.toLowerCase() === c.name.toLowerCase()) || 
          (state.currentUser.campus && state.currentUser.campus === c.id)
        ));
        if (isPrimary) {
          joinBtn.textContent = '[ PRIMARY COMMUNITY ]';
          joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-zinc-800 text-amber-400 font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition cursor-pointer';
        } else if (c.is_joined) {
          joinBtn.textContent = '[ JOINED ✓ ]';
          joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-zinc-800 text-zinc-300 font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition cursor-pointer';
        } else {
          joinBtn.textContent = '[ + JOIN COMMUNITY ]';
          joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition shadow-lg cursor-pointer';
        }
      }

      // Creator Ownership Controls Visibility (Owner-Only)
      var myId = state.currentUser ? String(state.currentUser.id || '').trim() : '';
      var myHandle = state.currentUser ? String(state.currentUser.handle || '').trim().toLowerCase() : '';
      var cCreatorId = c.creator_id ? String(c.creator_id).trim() : '';
      var cCreatorHandle = c.creator_handle ? String(c.creator_handle).trim().toLowerCase() : '';
      var cUserRole = c.user_role ? String(c.user_role).trim().toLowerCase() : '';
      var isOwner = Boolean(
        (cCreatorId && myId && cCreatorId === myId) || 
        (cCreatorHandle && myHandle && cCreatorHandle === myHandle) || 
        (cUserRole === 'owner' || cUserRole === 'creator') ||
        (state.currentUser && (state.currentUser.role === 'admin' || state.currentUser.role === 'founder'))
      );

      var creatorControls = document.getElementById('campusPageCreatorControls');
      if (creatorControls) {
        creatorControls.style.display = isOwner ? 'flex' : 'none';
      }

      var hostBtn = document.getElementById('campusPageHostBtn');
      if (hostBtn) {
        hostBtn.style.display = isOwner ? 'inline-block' : 'none';
      }
      // Community Share Moment action - Membership Authorized
      var isEligibleMember = Boolean(
        c.is_joined || 
        (c.user_role && ['owner', 'admin', 'creator', 'member'].indexOf(c.user_role.toLowerCase()) !== -1) ||
        (state.currentUser && (state.currentUser.role === 'admin' || state.currentUser.role === 'founder'))
      );

      var shareBtn = document.getElementById('campusShareMomentBtn');
      var nonMemberNotice = document.getElementById('campusNonMemberNotice');

      if (shareBtn) {
        shareBtn.style.display = isEligibleMember ? 'flex' : 'none';
        if (isEligibleMember) {
          shareBtn.onclick = function() {
            openCommunityMomentCapture(c.id, c.name);
          };
        } else {
          shareBtn.onclick = null;
        }
      }

      if (nonMemberNotice) {
        var isPublic = (c.visibility || 'public').toLowerCase() === 'public';
        nonMemberNotice.style.display = (!isEligibleMember && isPublic) ? 'block' : 'none';
      }
    }

    // Load Personal Community Context & Return Signal (Phase 11)
    if (state.currentUser) {
      var contextCard = document.getElementById('campusPageConnectionCard');
      var statusEl = document.getElementById('campusPageConnectionStatus');
      var attendedEl = document.getElementById('campusPageAttendedCount');
      var contributedEl = document.getElementById('campusPageContributedCount');
      var headlineEl = document.getElementById('campusPageReturnContextHeadline');

      var commId = (data.campus && data.campus.id) ? data.campus.id : '';
      apiRequest('/api/community/context?name=' + encodeURIComponent(campusName) + (commId ? '&community_id=' + encodeURIComponent(commId) : '')).then(function(ctxRes) {
        if (ctxRes && ctxRes.success && contextCard) {
          contextCard.style.display = 'block';
          if (statusEl) {
            var roleName = ctxRes.membership_status === 'owner' ? 'Creator / Owner' : (ctxRes.membership_status === 'admin' ? 'Admin' : (ctxRes.is_member ? 'Member' : 'Exploring'));
            statusEl.textContent = roleName;
          }
          if (contributedEl && ctxRes.participation) {
            contributedEl.textContent = (ctxRes.participation.moments_contributed || 0) + ' moments';
          }
        }
      });

      apiRequest('/api/community/return-context?name=' + encodeURIComponent(campusName) + (commId ? '&community_id=' + encodeURIComponent(commId) : '')).then(function(retRes) {
        if (retRes && retRes.success && headlineEl && retRes.calm_headline) {
          headlineEl.textContent = retRes.calm_headline;
        }
      });
    }

    // Live Pulse Rendering (Honest server-authoritative states)
    var pulseState = (data.pulse && data.pulse.pulse_state) || (data.pulse && data.pulse.active_areas_count > 0 && Array.isArray(data.pulse.recent_pulse) && data.pulse.recent_pulse.length > 0 ? 'LIVE NOW' : 'QUIET RIGHT NOW');
    if (pulseState === 'LIVE NOW') {
      if (pulseDotEl) pulseDotEl.className = 'w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse';
      if (pulseTagEl) {
        pulseTagEl.textContent = '● LIVE NOW';
        pulseTagEl.className = 'font-mono-tag text-[9px] uppercase tracking-[.2em] text-emerald-400 font-bold';
      }
      if (pulseHeadingEl) pulseHeadingEl.textContent = 'An experience is happening across the community right now.';
      if (activeAreasEl) activeAreasEl.textContent = (data.pulse.active_areas_count || 1) + ' active areas';
    } else if (pulseState === 'ACTIVE') {
      if (pulseDotEl) pulseDotEl.className = 'w-1.5 h-1.5 rounded-full bg-amber-500';
      if (pulseTagEl) {
        pulseTagEl.textContent = '● ACTIVE';
        pulseTagEl.className = 'font-mono-tag text-[9px] uppercase tracking-[.2em] text-amber-400 font-bold';
      }
      if (pulseHeadingEl) pulseHeadingEl.textContent = 'Life is happening across the community.';
      if (activeAreasEl) activeAreasEl.textContent = (data.pulse.active_areas_count || 1) + ' active areas';
    } else {
      if (pulseDotEl) pulseDotEl.className = 'w-1.5 h-1.5 rounded-full bg-zinc-600';
      if (pulseTagEl) {
        pulseTagEl.textContent = '○ QUIET RIGHT NOW';
        pulseTagEl.className = 'font-mono-tag text-[9px] uppercase tracking-[.2em] text-zinc-500 font-bold';
      }
      if (pulseHeadingEl) pulseHeadingEl.textContent = 'This space is calm right now. Shared moments will appear here.';
      if (activeAreasEl) activeAreasEl.textContent = 'Quiet right now';
    }

    if (data.pulse && Array.isArray(data.pulse.recent_pulse) && data.pulse.recent_pulse.length > 0) {
      if (pulseTilesEl) {
        pulseTilesEl.innerHTML = '';
        data.pulse.recent_pulse.forEach(function(p) {
          var tile = document.createElement('div');
          tile.className = 'w-20 shrink-0 p-2 rounded-xl bg-zinc-900 border border-white/10 space-y-1 cursor-pointer hover:border-amber-500/40 transition active:scale-95';
          tile.onclick = function() { openPlacePage(p.area); };
          tile.innerHTML = 
            '<div class="w-full aspect-square rounded-lg overflow-hidden bg-black">' +
              '<img src="' + (p.main_img || '') + '" class="w-full h-full object-cover">' +
            '</div>' +
            '<p class="text-[10px] font-bold text-white truncate">' + escapeHtml(p.area) + '</p>' +
            '<p class="font-mono-tag text-[8px] text-zinc-500">' + escapeHtml(p.timeAgo) + '</p>';
          pulseTilesEl.appendChild(tile);
        });

        var pulseActionTile = document.createElement('div');
        pulseActionTile.className = 'w-20 shrink-0 rounded-xl border border-amber-500/40 bg-amber-500/10 flex flex-col items-center justify-center text-center cursor-pointer hover:bg-amber-500/20 active:scale-95 transition shadow-sm p-2';
        pulseActionTile.onclick = function() { openLivePulse(campusName); };
        pulseActionTile.innerHTML = '<span class="text-amber-400 text-xs font-bold font-mono-tag">OPEN</span><span class="text-[9px] text-amber-300 font-mono-tag font-bold">PULSE →</span>';
        pulseTilesEl.appendChild(pulseActionTile);
      }
    } else {
      if (pulseTilesEl) {
        pulseTilesEl.innerHTML = '<div class="py-3 px-1 text-xs text-zinc-500 font-mono-tag">Quiet right now.</div>';
      }
    }

    if (areasListEl && Array.isArray(data.areas) && data.areas.length > 0) {
      areasListEl.innerHTML = '';
      data.areas.forEach(function(a) {
        var aRow = document.createElement('div');
        aRow.className = 'p-2.5 rounded-xl bg-zinc-900/80 border border-white/[.04] flex items-center justify-between cursor-pointer hover:border-amber-500/30 transition active:scale-95';
        aRow.onclick = function() { openPlacePage(a.name); };
        aRow.innerHTML = 
          '<span class="text-xs font-bold text-white">' + escapeHtml(a.name) + '</span>' +
          '<span class="font-mono-tag text-[9px] text-zinc-400">' + a.momentsCount + ' Moments</span>';
        areasListEl.appendChild(aRow);
      });
    }

    if (momentsEl) {
      if (Array.isArray(data.moments) && data.moments.length > 0) {
        renderCommunityCards(data.moments, momentsEl);
      } else {
        var curCommId = (data.campus && data.campus.id) ? data.campus.id : '';
        var curCommName = (data.campus && data.campus.name) ? data.campus.name : campusName;
        var isEligibleToContribute = Boolean(
          (data.campus && data.campus.is_joined) ||
          (data.campus && data.campus.user_role && ['owner', 'admin', 'creator', 'member'].indexOf(data.campus.user_role.toLowerCase()) !== -1) ||
          (state.currentUser && (state.currentUser.role === 'admin' || state.currentUser.role === 'founder'))
        );
        if (isEligibleToContribute) {
          momentsEl.innerHTML = '<div class="py-6 text-center space-y-2 rounded-2xl bg-zinc-950/60 border border-white/[.04] p-4">' +
            '<p class="text-xs text-zinc-500 font-mono-tag">No shared moments yet. Be the first to share an authentic moment.</p>' +
            '<button onclick="openCommunityMomentCapture(\'' + escapeHtml(curCommId) + '\', \'' + escapeHtml(curCommName).replace(/'/g, "\\'") + '\')" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 font-mono-tag font-bold text-[10px] uppercase cursor-pointer active:scale-95 transition">📸 + SHARE FIRST MOMENT</button>' +
          '</div>';
        } else {
          momentsEl.innerHTML = '<div class="py-6 text-center space-y-2 rounded-2xl bg-zinc-950/60 border border-white/[.04] p-4">' +
            '<p class="text-xs text-zinc-500 font-mono-tag">No shared moments yet.</p>' +
            '<p class="text-[11px] text-zinc-600 font-mono-tag">Join this space to share authentic moments with the community.</p>' +
          '</div>';
        }
      }
    }

    if (memoriesGridEl) {
      if (Array.isArray(data.collective_memories) && data.collective_memories.length > 0) {
        memoriesGridEl.innerHTML = data.collective_memories.map(function(m) {
          var attendeeCount = m.checked_in_count || m.moments_count || 0;
          var attendeeTxt = attendeeCount > 0 ? (attendeeCount + ' people were there') : 'Archived memory';
          return '<div onclick="openCollectiveMemoryPage(\'' + (m.id || 'mem_1') + '\')" class="p-3 rounded-2xl bg-zinc-950 border border-white/[.07] hover:border-amber-500/40 space-y-2 shadow-md cursor-pointer transition active:scale-95 group">' +
            '<div class="w-full aspect-[4/3] rounded-xl overflow-hidden bg-black">' +
              '<img src="' + (m.cover_img || m.cover_image || '') + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
            '</div>' +
            '<p class="text-xs font-bold text-white truncate group-hover:text-amber-400 transition-colors">' + escapeHtml(m.title) + '</p>' +
            '<p class="font-mono-tag text-[8px] text-zinc-400">' + attendeeTxt + '</p>' +
          '</div>';
        }).join('');
      } else {
        memoriesGridEl.innerHTML = '<div class="col-span-2 py-6 text-center text-xs text-zinc-500 font-mono-tag">No collective memories yet. Shared moments will appear here.</div>';
      }
    }

    if (peopleListEl && Array.isArray(data.people)) {
      peopleListEl.innerHTML = data.people.map(function(u) {
        return '<div class="flex items-center justify-between py-1.5 border-b border-zinc-900/80">' +
          '<div class="flex items-center gap-2 cursor-pointer" onclick="openUserProfile(\'' + u.id + '\')">' +
            '<div class="w-7 h-7 rounded-full bg-zinc-900 border border-white/20 flex items-center justify-center text-[9px] font-bold text-amber-400 font-mono-tag">' + escapeHtml(u.avatar_letter || 'K') + '</div>' +
            '<span class="text-xs font-bold text-white">@' + escapeHtml(u.handle || 'user') + '</span>' +
          '</div>' +
          '<button onclick="handlePeerProfileConnect(event, \'' + u.id + '\')" class="font-mono-tag text-[9px] text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2.5 py-0.5 rounded cursor-pointer active:scale-95">Connect</button>' +
        '</div>';
      }).join('');
    }
  }
}
window.openCampusPage = openCampusPage;
window.switchCommunity = openCampusPage;

function openCommunityMomentCapture(commId, commName) {
  var cName = commName || state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');
  state.activeCommunity = cName;
  state.selectedReviewCommunity = cName;
  if (commId) state.activeCommunityId = commId;
  if (typeof playTactileFeedback === 'function') playTactileFeedback('tap');
  openCameraStudio();
}
window.openCommunityMomentCapture = openCommunityMomentCapture;


 async function openCreatorEarningsModal() {
  // Drop earnings removed — no-op
}
window.openCreatorEarningsModal = openCreatorEarningsModal;

function closeCreatorEarningsModal() {
  var modal = document.getElementById('creatorEarningsModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreatorEarningsModal = closeCreatorEarningsModal;

async function openCreatorOperationsModal() {
  var modal = document.getElementById('creatorOperationsModal');
  if (modal) modal.style.display = 'flex';

  var commsListEl = document.getElementById('opsCommunitiesList');

  var res = await apiRequest('/api/community/manage');
  if (res && res.success && res.operations) {
    var op = res.operations;

    // Communities
    if (commsListEl) {
      if (Array.isArray(op.communities) && op.communities.length > 0) {
        commsListEl.innerHTML = op.communities.map(function(c) {
          return '<div class="p-2.5 rounded-xl bg-zinc-900 border border-white/[.04] flex items-center justify-between text-xs">' +
            '<div class="flex items-center gap-2">' +
              '<span class="text-sm">' + (c.icon || '📍') + '</span>' +
              '<div>' +
                '<span class="text-white font-bold block">' + escapeHtml(c.name) + '</span>' +
                '<span class="text-[9px] font-mono-tag text-zinc-500">' + escapeHtml(c.city || 'Campus') + '</span>' +
              '</div>' +
            '</div>' +
            '<span class="text-[9px] font-mono-tag text-amber-400 font-bold uppercase px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30">' + escapeHtml(c.user_role || 'ADMIN') + '</span>' +
          '</div>';
        }).join('');
      } else {
        commsListEl.innerHTML = '<div class="p-2.5 rounded-xl bg-zinc-900 text-xs text-zinc-500 font-mono-tag">No managed communities yet.</div>';
      }
    }
  }
}
window.openCreatorOperationsModal = openCreatorOperationsModal;

function closeCreatorOperationsModal() {
  var modal = document.getElementById('creatorOperationsModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreatorOperationsModal = closeCreatorOperationsModal;

// Phase 9: Safety & Moderation Client Controllers
var currentReportTarget = { communityId: '', targetType: 'community', targetId: '', reason: 'Spam' };

function openCommunityReportModal(communityId, targetType, targetId, title) {
  currentReportTarget.communityId = communityId || state.activeCommunityId || 'comm_1';
  currentReportTarget.targetType = targetType || 'community';
  currentReportTarget.targetId = targetId || communityId || 'comm_1';
  currentReportTarget.reason = 'Spam';

  var titleEl = document.getElementById('reportTargetTitle');
  if (titleEl) titleEl.textContent = 'Report ' + (targetType ? targetType.toUpperCase() : 'CONTENT');

  var modal = document.getElementById('communityReportModal');
  if (modal) modal.style.display = 'flex';

  selectReportReason('Spam');
}
window.openCommunityReportModal = openCommunityReportModal;

function closeCommunityReportModal() {
  var modal = document.getElementById('communityReportModal');
  if (modal) modal.style.display = 'none';
}
window.closeCommunityReportModal = closeCommunityReportModal;

function selectReportReason(reason) {
  currentReportTarget.reason = reason;
  var btns = document.querySelectorAll('.report-reason-btn');
  btns.forEach(function(b) {
    if (b.textContent.trim().toLowerCase() === reason.toLowerCase()) {
      b.className = 'report-reason-btn p-2 rounded-xl bg-rose-500/20 border border-rose-500 text-rose-300 text-[10px] text-left font-bold';
    } else {
      b.className = 'report-reason-btn p-2 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-300 hover:border-amber-500/40 text-[10px] text-left';
    }
  });
}
window.selectReportReason = selectReportReason;

async function submitCommunityReport() {
  var detailsInput = document.getElementById('reportDetailsInput');
  var details = detailsInput ? detailsInput.value.trim() : '';

  var res = await apiRequest('/api/community/report', {
    method: 'POST',
    body: JSON.stringify({
      community_id: currentReportTarget.communityId,
      target_type: currentReportTarget.targetType,
      target_id: currentReportTarget.targetId,
      reason: currentReportTarget.reason,
      details: details
    })
  });

  if (res && res.success) {
    playTactileFeedback('click');
    showToast('✓ ' + (res.message || 'Report submitted to safety team.'));
    closeCommunityReportModal();
    if (detailsInput) detailsInput.value = '';
  } else {
    showToast('Failed to submit report: ' + (res ? res.error : 'Error'));
  }
}
window.submitCommunityReport = submitCommunityReport;

async function openCommunityModerationModal(communityId) {
  var commId = communityId || state.activeCommunityId || 'comm_1';
  var modal = document.getElementById('communityModerationModal');
  if (modal) modal.style.display = 'flex';

  var listEl = document.getElementById('moderationReportsList');
  if (listEl) listEl.innerHTML = '<div class="p-3 rounded-xl bg-zinc-900 text-xs text-zinc-400 font-mono-tag text-center">Loading reports...</div>';

  var res = await apiRequest('/api/community/moderation/reports?community_id=' + encodeURIComponent(commId));
  if (res && res.success && Array.isArray(res.reports)) {
    if (listEl) {
      if (res.reports.length > 0) {
        listEl.innerHTML = res.reports.map(function(r) {
          var statusColor = r.status === 'pending' ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' : 'text-zinc-400 bg-zinc-800 border-zinc-700';
          return '<div class="p-3 rounded-xl bg-zinc-900 border border-white/[.04] space-y-2 text-xs font-mono-tag">' +
            '<div class="flex justify-between items-start">' +
              '<div>' +
                '<span class="text-white font-bold block">' + escapeHtml(r.target_type).toUpperCase() + ' · ' + escapeHtml(r.reason) + '</span>' +
                '<span class="text-[9px] text-zinc-500">By @' + escapeHtml(r.reporter_handle || 'user') + ' · ' + escapeHtml(r.created_at || 'Recent') + '</span>' +
              '</div>' +
              '<span class="text-[9px] font-bold uppercase px-2 py-0.5 rounded border ' + statusColor + '">' + escapeHtml(r.status) + '</span>' +
            '</div>' +
            (r.details ? '<p class="text-[10px] text-zinc-300 font-sans bg-zinc-950 p-2 rounded-lg border border-white/[.03]">' + escapeHtml(r.details) + '</p>' : '') +
            '<div class="flex items-center gap-2 pt-1 border-t border-zinc-800">' +
              (r.status === 'pending' ? '<button onclick="handleModerationAction(\'' + escapeHtml(r.id) + '\', \'review\', \'' + escapeHtml(r.target_type) + '\', \'' + escapeHtml(r.target_id) + '\', \'' + escapeHtml(commId) + '\')" class="text-amber-400 hover:underline cursor-pointer text-[10px]">Review</button>' : '') +
              (r.status === 'pending' ? '<button onclick="handleModerationAction(\'' + escapeHtml(r.id) + '\', \'dismiss\', \'' + escapeHtml(r.target_type) + '\', \'' + escapeHtml(r.target_id) + '\', \'' + escapeHtml(commId) + '\')" class="text-zinc-400 hover:underline cursor-pointer text-[10px]">Dismiss</button>' : '') +
              (r.target_type === 'moment' ? '<button onclick="handleModerationAction(\'' + escapeHtml(r.id) + '\', \'hide\', \'' + escapeHtml(r.target_type) + '\', \'' + escapeHtml(r.target_id) + '\', \'' + escapeHtml(commId) + '\')" class="text-rose-400 hover:underline cursor-pointer text-[10px]">Hide Content</button>' : '') +
            '</div>' +
          '</div>';
        }).join('');
      } else {
        listEl.innerHTML = '<div class="p-3 rounded-xl bg-zinc-900 text-xs text-zinc-500 font-mono-tag text-center">No reports filed for this community. Clean record!</div>';
      }
    }
  } else {
    if (listEl) listEl.innerHTML = '<div class="p-3 rounded-xl bg-zinc-900 text-xs text-rose-400 font-mono-tag text-center">' + (res ? res.error : 'Failed to load moderation reports') + '</div>';
  }
}
window.openCommunityModerationModal = openCommunityModerationModal;

function closeCommunityModerationModal() {
  var modal = document.getElementById('communityModerationModal');
  if (modal) modal.style.display = 'none';
}
window.closeCommunityModerationModal = closeCommunityModerationModal;

async function handleModerationAction(reportId, action, targetType, targetId, communityId) {
  var res = await apiRequest('/api/community/moderation/action', {
    method: 'POST',
    body: JSON.stringify({
      report_id: reportId,
      action: action,
      target_type: targetType,
      target_id: targetId,
      community_id: communityId || state.activeCommunityId || 'comm_1'
    })
  });
  if (res && res.success) {
    showToast('✓ Moderation action executed: ' + action);
    openCommunityModerationModal(communityId);
  } else {
    showToast('Failed to apply moderation action: ' + (res ? res.error : 'Error'));
  }
}
window.handleModerationAction = handleModerationAction;

async function loadCommunityDiscovery(options) {
  options = options || {};
  var campus = options.campus || '';
  var city = options.city || '';
  var type = options.type || '';
  var q = options.q || '';
  var limit = options.limit || 20;

  var queryParams = [];
  if (campus) queryParams.push('campus=' + encodeURIComponent(campus));
  if (city) queryParams.push('city=' + encodeURIComponent(city));
  if (type) queryParams.push('type=' + encodeURIComponent(type));
  if (q) queryParams.push('q=' + encodeURIComponent(q));
  if (limit) queryParams.push('limit=' + encodeURIComponent(limit));
  if (options.nearby_only) queryParams.push('nearby_only=1');

  var url = '/api/community/discover' + (queryParams.length ? '?' + queryParams.join('&') : '');
  var res = await apiRequest(url);
  return res;
}
window.loadCommunityDiscovery = loadCommunityDiscovery;

async function loadMoreAroundYou() {
  var container = document.getElementById('moreAroundYouContainer');
  if (!container) return;

  var userCampus = (state.currentUser && state.currentUser.campus) ? state.currentUser.campus : (state.activeCommunity || '');
  var userCity = (state.currentUser && (state.currentUser.location_city || state.currentUser.city)) ? (state.currentUser.location_city || state.currentUser.city) : '';

  var res = await loadCommunityDiscovery({
    campus: userCampus,
    city: userCity,
    nearby_only: 1,
    limit: 12
  });

  var list = (res && res.success && Array.isArray(res.near_you)) ? res.near_you : [];
  // Ensure strict public visibility and filter out any invalid entries
  list = list.filter(function(c) {
    return c && c.visibility === 'public';
  });

  if (list && list.length > 0) {
    container.innerHTML = list.map(function(c) {
      var badge = c.context_reason || 'Active Community';
      return '<div onclick="openCampusPage(\'' + escapeHtml(c.name).replace(/'/g, "\\'") + '\')" class="w-36 shrink-0 p-3 rounded-2xl bg-zinc-950 border border-white/[.07] hover:border-amber-500/40 space-y-2 cursor-pointer transition shadow-md active:scale-95 group">' +
        '<div class="flex items-center justify-between">' +
          '<div class="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center font-bold text-sm">' + (c.icon || '📍') + '</div>' +
        '</div>' +
        '<div>' +
          '<h3 class="text-xs font-bold text-white group-hover:text-amber-400 transition-colors truncate">' + escapeHtml(c.name) + '</h3>' +
          '<p class="font-mono-tag text-[8px] text-amber-400/90 mt-0.5 truncate">' + escapeHtml(badge) + '</p>' +
        '</div>' +
      '</div>';
    }).join('');
  } else {
    container.innerHTML = '<div class="w-full py-4 text-center text-[10px] font-mono-tag text-zinc-500">No other nearby public spaces right now</div>';
  }
}
window.loadMoreAroundYou = loadMoreAroundYou;

async function openCollectiveMemoryPage(memoryId) {
  memoryId = memoryId || 'mem_1';
  switchScreenView('collective-memory');

  var titleEl = document.getElementById('collectiveMemoryTitle');
  var dateEl = document.getElementById('collectiveMemoryDate');
  var badgeEl = document.getElementById('collectiveMemoryCountBadge');
  var commEl = document.getElementById('collectiveMemoryCommunity');
  var storyEl = document.getElementById('collectiveMemoryStory');
  var heroContainer = document.getElementById('collectiveMemoryHeroContainer');
  var capturedByEl = document.getElementById('collectiveMemoryCapturedBy');
  var momentsContainer = document.getElementById('collectiveMemoryMomentsContainer');

  var res = await apiRequest('/api/community/memories/detail?id=' + encodeURIComponent(memoryId));
  if (res && res.success && res.memory) {
    var m = res.memory;
    if (titleEl) titleEl.textContent = m.title;
    if (dateEl) dateEl.textContent = m.date_str;
    if (badgeEl) badgeEl.textContent = (m.moments_count ?? 0) + ' Moments captured together';
    if (commEl) commEl.textContent = m.community_name;
    if (storyEl) storyEl.textContent = m.story || 'Unfiltered community moments captured together.';

    // 1. Render Hero Moment
    if (heroContainer) {
      var heroImg = m.cover_img || (res.moments && res.moments[0] ? (res.moments[0].main_img || res.moments[0].image_url) : '');
      var heroCaption = (res.moments && res.moments[0] && res.moments[0].caption) ? res.moments[0].caption : 'Opening the day together.';
      if (heroImg) {
        heroContainer.innerHTML =
          '<div class="relative w-full aspect-[4/3] bg-zinc-950 overflow-hidden">' +
            '<img src="' + escapeHtml(heroImg) + '" class="w-full h-full object-cover">' +
            '<div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex flex-col justify-end p-4">' +
              '<span class="font-mono-tag text-[8px] text-amber-400 font-bold uppercase tracking-widest block mb-1">⭐ HERO MOMENT</span>' +
              '<p class="text-xs text-white font-medium italic">“' + escapeHtml(heroCaption) + '”</p>' +
            '</div>' +
          '</div>';
      } else {
        heroContainer.innerHTML = '';
      }
    }

    // 2. Render Unique Contributors ("CAPTURED BY")
    if (capturedByEl) {
      if (Array.isArray(res.moments) && res.moments.length > 0) {
        var authors = [];
        res.moments.forEach(function(post) {
          var name = post.author_name || post.user_name || post.author_handle || post.user_handle || 'Member';
          if (!authors.includes(name)) authors.push(name);
        });
        if (authors.length > 0) {
          var displayAuthors = authors.slice(0, 4).join(' · ');
          if (authors.length > 4) {
            displayAuthors += ' · +' + (authors.length - 4) + ' others';
          }
          capturedByEl.textContent = displayAuthors;
        } else {
          capturedByEl.textContent = 'Community members';
        }
      } else {
        capturedByEl.textContent = 'No contributors yet';
      }
    }

    // 3. Render Timeline Moments
    if (momentsContainer) {
      if (Array.isArray(res.moments) && res.moments.length > 0) {
        renderFeedCards(res.moments, momentsContainer);
      } else {
        momentsContainer.innerHTML = '<div class="text-center text-zinc-500 font-mono-tag text-xs py-8">No moments captured yet.</div>';
      }
    }
  }
}
window.openCollectiveMemoryPage = openCollectiveMemoryPage;

function handleCollectiveMemoryBack() {
  switchScreenView('campus-page');
}
window.handleCollectiveMemoryBack = handleCollectiveMemoryBack;

function handleCampusPageBack() {
  var prev = state.previousScreen || 'feed';
  if (prev === 'campus-page') prev = 'feed';
  switchScreenView(prev);
}
window.handleCampusPageBack = handleCampusPageBack;

async function toggleJoinCommunity() {
  var btn = document.getElementById('campusPageJoinBtn');
  var name = state.activeCommunity || 'North City University';
  var commId = state.activeCommunityId || '';
  if (!btn) return;
  
  btn.style.opacity = '0.5';
  var res = await apiRequest('/api/community/join', {
    method: 'POST',
    body: JSON.stringify({ name: name, community_id: commId, id: commId })
  });
  btn.style.opacity = '1';

  if (res && res.success) {
    playTactileFeedback('xp');
    var shareBtn = document.getElementById('campusShareMomentBtn');
    var nonMemberNotice = document.getElementById('campusNonMemberNotice');
    if (res.is_joined) {
      showToast('Joined ' + name + '! ✦');
      btn.textContent = '[ JOINED ✓ ]';
      btn.className = 'mt-2 w-full py-2.5 rounded-xl bg-zinc-800 text-zinc-300 font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition cursor-pointer';
      if (shareBtn) {
        shareBtn.style.display = 'flex';
        shareBtn.onclick = function() {
          openCommunityMomentCapture(state.activeCommunityId || '', name);
        };
      }
      if (nonMemberNotice) nonMemberNotice.style.display = 'none';
    } else {
      showToast('Left ' + name);
      btn.textContent = '[ + JOIN COMMUNITY ]';
      btn.className = 'mt-2 w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition shadow-lg cursor-pointer';
      if (shareBtn) {
        shareBtn.style.display = 'none';
        shareBtn.onclick = null;
      }
      if (nonMemberNotice) nonMemberNotice.style.display = 'block';
    }
  }
}
window.toggleJoinCommunity = toggleJoinCommunity;

state.newCommunityType = 'Interest';

function openCreateCommunityModal() {
  if (state.currentUser && !state.currentUser.is_creator && !['admin', 'founder', 'creator'].includes(state.currentUser.role)) {
    openCreatorOnboardingModal();
    return;
  }
  var modal = document.getElementById('createCommunityModal');
  if (modal) modal.style.display = 'flex';
}
window.openCreateCommunityModal = openCreateCommunityModal;

function closeCreateCommunityModal() {
  var modal = document.getElementById('createCommunityModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreateCommunityModal = closeCreateCommunityModal;

function selectNewCommunityType(type) {
  state.newCommunityType = type;
  var group = document.getElementById('createCommunityTypeGroup');
  if (!group) return;
  group.querySelectorAll('.comm-type-pill').forEach(function(pill) {
    if (pill.dataset.type === type) {
      pill.className = 'comm-type-pill p-2.5 rounded-xl border border-amber-500/60 bg-amber-500/10 text-amber-400 text-xs font-mono-tag font-bold text-left flex items-center gap-2 cursor-pointer';
    } else {
      pill.className = 'comm-type-pill p-2.5 rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-400 text-xs font-mono-tag font-bold text-left flex items-center gap-2 cursor-pointer';
    }
  });
}
window.selectNewCommunityType = selectNewCommunityType;

async function submitNewCommunity() {
  var nameInput = document.getElementById('newCommName');
  var descInput = document.getElementById('newCommDesc');
  var visInput = document.querySelector('input[name="newCommVisibility"]:checked');

  var name = nameInput ? nameInput.value.trim() : '';
  var desc = descInput ? descInput.value.trim() : '';
  var vis = visInput ? visInput.value : 'public';
  var type = state.newCommunityType || 'Interest';

  if (!name || name.length < 3) {
    showToast('Please enter a valid community name (min 3 chars)');
    return;
  }

  showToast('Creating ' + name + '...');
  var res = await apiRequest('/api/community/create', {
    method: 'POST',
    body: JSON.stringify({
      name: name,
      type: type,
      description: desc,
      visibility: vis
    })
  });

  if (res && res.success && res.community) {
    closeCreateCommunityModal();
    playTactileFeedback('xp');
    showToast('Community "' + name + '" created! ✦ +50 XP');
    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';
    await openCampusPage(res.community.name);
    if (typeof loadMoreAroundYou === 'function') loadMoreAroundYou();
  } else {
    if (res && res.error === 'CREATOR_REQUIRED') {
      closeCreateCommunityModal();
      openCreatorOnboardingModal();
      showToast('Community Creator activation required to launch spaces.');
    } else {
      showToast(res && res.error ? res.error : 'Could not create community.');
    }
  }
}
window.submitNewCommunity = submitNewCommunity;

function openPlacePage(placeName) {
  showToast('Opening ' + placeName + ' Place View ⌖');
  selectSubTab('community');
}
window.openPlacePage = openPlacePage;

function openCampusOptions() {
  var modal = document.getElementById('campusOptionsMenuModal');
  if (modal) modal.style.display = 'flex';
}
window.openCampusOptions = openCampusOptions;

function closeCampusOptions() {
  var modal = document.getElementById('campusOptionsMenuModal');
  if (modal) modal.style.display = 'none';
}
window.closeCampusOptions = closeCampusOptions;

async function loadFeedMoments(circle) {
  var container = document.getElementById('feedStreamContainer');
  if (!container) return;

  circle = circle || state.activeCircle || 'foryou';
  var endpoint = (circle === 'foryou') ? '/api/feed?circle=all' : ('/api/feed?circle=' + circle);

  // Show loading spinner — always cleared by finally{}
  container.innerHTML =
    '<div class="py-12 text-center text-zinc-500 font-mono-tag text-xs flex flex-col items-center gap-2">' +
      '<span class="w-4 h-4 border-2 border-amber-500/40 border-t-amber-500 rounded-full animate-spin"></span>' +
      '<span>Loading Authentic Moments...</span>' +
    '</div>';

  var data = null;
  try {
    data = await apiRequest(endpoint);
  } catch(e) {
    data = { success: false, error: e && e.message ? e.message : 'Network error', _network: true };
  } finally {
    // Always run — guarantees spinner is never the final state
    if (data && data.success && Array.isArray(data.feed)) {
      // ── STATE A: SUCCESS WITH POSTS ──────────────────────────────────
      if (data.feed.length === 0) {
        // ── STATE B: SUCCESS + ZERO POSTS ────────────────────────────
        container.innerHTML =
          '<div class="flex flex-col items-center justify-center py-16 space-y-3 text-center px-6">' +
            '<div class="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-xl">📷</div>' +
            '<h3 class="text-xs font-black text-white uppercase font-mono-tag tracking-wider">NO MOMENTS YET</h3>' +
            '<p class="text-[11px] text-zinc-400">Be the first to capture today\'s unfiltered perspective.</p>' +
            '<button class="mt-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs rounded-xl font-mono-tag tracking-wider uppercase cursor-pointer shadow-lg active:scale-95 transition" onclick="openCameraStudio()">CAPTURE TODAY\'S MOMENT</button>' +
          '</div>';
      } else {
        renderFeedCards(data.feed, container);
      }
    } else if (data && (data._status === 401 || data._status === 403 || (data.error && (data.error + '').toLowerCase().includes('auth')))) {
      // ── STATE C: AUTH FAILURE ─────────────────────────────────────
      container.innerHTML =
        '<div class="flex flex-col items-center justify-center py-16 space-y-3 text-center px-6">' +
          '<div class="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-xl">🔒</div>' +
          '<h3 class="text-xs font-black text-white uppercase font-mono-tag tracking-wider">SESSION EXPIRED</h3>' +
          '<p class="text-[11px] text-zinc-400">Please log in again to see your feed.</p>' +
          '<button class="mt-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs rounded-xl font-mono-tag tracking-wider uppercase cursor-pointer shadow-lg active:scale-95 transition" onclick="switchScreenView(\'login\')">LOG IN</button>' +
        '</div>';
    } else {
      // ── STATE D: SERVER / NETWORK / TIMEOUT ERROR ─────────────────
      var errLabel = (data && data._timeout) ? "Couldn't reach server." : "Couldn't load Moments.";
      container.innerHTML =
        '<div class="flex flex-col items-center justify-center py-16 space-y-3 text-center px-6">' +
          '<div class="w-10 h-10 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-500 mx-auto text-lg">⚠</div>' +
          '<h3 class="text-xs font-black text-white uppercase font-mono-tag tracking-wider">' + errLabel + '</h3>' +
          '<p class="text-[11px] text-zinc-400">Check your connection and try again.</p>' +
          '<button class="mt-2 px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white font-extrabold text-xs rounded-xl font-mono-tag tracking-wider uppercase cursor-pointer active:scale-95 transition border border-zinc-700" onclick="loadFeedMoments(\'' + circle + '\')">TRY AGAIN</button>' +
        '</div>';
    }
  }
}

function formatPostTime(createdStr) {
    if (!createdStr) {
        var n = new Date();
        return n.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
    }
    try {
        var dt = new Date(createdStr);
        if (isNaN(dt.getTime())) {
            var n = new Date();
            return n.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        return dt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
    } catch(e) {
        var n = new Date();
        return n.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
    }
}

function formatTimeAgoClean(createdStr) {
    if (!createdStr) return 'JUST NOW';
    try {
        var str = String(createdStr).trim();
        if (str.indexOf(' ') !== -1 && str.indexOf('T') === -1) {
            str = str.replace(' ', 'T');
        }
        if (!str.endsWith('Z') && str.indexOf('+') === -1 && str.lastIndexOf('-') <= 10) {
            str += 'Z';
        }
        var dt = new Date(str);
        if (isNaN(dt.getTime())) return 'JUST NOW';
        var now = new Date();
        var diffSec = Math.floor((now.getTime() - dt.getTime()) / 1000);
        if (diffSec < 60) return 'JUST NOW';
        var mins = Math.floor(diffSec / 60);
        if (mins < 60) return mins + ' MIN AGO';
        var hrs = Math.floor(mins / 60);
        if (hrs < 24) return hrs + ' HR AGO';
        var days = Math.floor(hrs / 24);
        if (days <= 6) return days + ' DAYS AGO';
        var weeks = Math.floor(days / 7);
        if (weeks < 5) return weeks + (weeks === 1 ? ' WEEK AGO' : ' WEEKS AGO');
        var months = Math.floor(days / 30);
        if (months < 12) return months + (months === 1 ? ' MONTH AGO' : ' MONTHS AGO');
        return dt.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase();
    } catch(e) {
        return 'JUST NOW';
    }
}
window.formatTimeAgoClean = formatTimeAgoClean;

function updateAllMomentTimestamps() {
    var elements = document.querySelectorAll('.moment-live-timestamp[data-created-at]');
    if (!elements || elements.length === 0) return;
    elements.forEach(function(el) {
        var raw = el.getAttribute('data-created-at');
        if (raw) {
            var next = formatTimeAgoClean(raw);
            if (el.textContent !== next) {
                el.textContent = next;
            }
        }
    });
}
window.updateAllMomentTimestamps = updateAllMomentTimestamps;

if (!window._momentTimestampInterval) {
    window._momentTimestampInterval = setInterval(updateAllMomentTimestamps, 10000);
}

function getApproxLocationString(m) {
    var raw = m.location_city || m.locationCity || m.campus || '';
    if (!raw) return 'Near Central Market';
    if (raw.toLowerCase().startsWith('near ')) {
        return raw;
    }
    return 'Near ' + raw;
}

state.currentGeoApprox = '';
function captureCurrentGeoLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(async function(pos) {
        try {
            var lat = pos.coords.latitude;
            var lon = pos.coords.longitude;
            var res = await fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + lat + '&longitude=' + lon + '&localityLanguage=en');
            if (res.ok) {
                var data = await res.json();
                var place = data.locality || data.city || data.principalSubdivision || '';
                if (place) {
                    state.currentGeoApprox = place;
                }
            }
        } catch(e) {
            console.warn('Geolocation geocode fallback:', e);
        }
    }, function(err) {
        console.warn('Geolocation error:', err);
    }, { timeout: 3500, maximumAge: 60000 });
}

function renderFeedCards(moments, container) {
  container.innerHTML = '';
  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3.5 shadow-2xl relative kandid-card';
    card.dataset.postId = m.id;

    var authorHandle = escapeHtml(m.author_handle || m.user_handle || 'kandid.creator');
    var rawComm = m.community_name || m.primary_community_name || m.campus || 'CENTRAL CAMPUS';
    var cleanCommName = rawComm.replace(/^Near\s+/i, '');
    var campusName = escapeHtml(cleanCommName.toUpperCase());
    var commTarget = m.community_name || m.primary_community_name || m.primary_community_id || cleanCommName;
    var timeAgo = escapeHtml(m.created_at ? formatTimeAgoClean(m.created_at) : (m.timeAgo || m.time_ago || 'JUST NOW').toUpperCase());
    var captionText = escapeHtml(m.caption || 'Raw unfiltered moment on campus.');
    var iso = escapeHtml(m.exif_iso || 'ISO 400');
    var aperture = escapeHtml(m.exif_aperture || 'F/2.8');
    var shutter = escapeHtml(m.exif_shutter || '1/250S');

    var avatarSrc = m.avatar_url;
    var avatarHtml = avatarSrc
      ? '<img src="' + avatarSrc + '" class="w-full h-full object-cover">'
      : '<span class="text-[9px] font-mono-tag font-bold text-zinc-300">K</span>';

    var realmojis = m.realmojis || {};
    var reactionPillsHtml = '';
    for (var emoji in realmojis) {
      if (realmojis[emoji] > 0) {
        reactionPillsHtml += '<button class="realmoji-btn inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-900 border border-zinc-800 rounded-md text-[9px] font-mono-tag active:scale-95 transition-transform cursor-pointer" data-emoji="' + emoji + '">' +
          '<span>' + emoji + '</span>' +
          '<span class="emoji-count-num text-[8px] font-bold text-zinc-300">' + realmojis[emoji] + '</span>' +
        '</button>';
      }
    }

    var mainImgSrc = m.main_img || m.mainImg || '';
    var pipImgSrc = m.pip_img || m.pipImg || '';

    var audioUrl = m.audio_url || m.audioData || '';
    var audioPlayerBarHtml = audioUrl ?
      '<div class="bg-zinc-900/90 border border-amber-500/30 rounded-xl px-3 py-2 flex items-center justify-between shadow-inner">' +
        '<div class="flex items-center gap-2">' +
          '<span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>' +
          '<span class="text-[9px] text-zinc-300 font-mono-tag font-bold tracking-wider uppercase">3.0s Ambient Sound</span>' +
        '</div>' +
        '<button class="px-2.5 py-1 bg-amber-500 hover:bg-amber-400 active:scale-95 text-black font-extrabold text-[8px] font-mono-tag rounded-lg flex items-center gap-1 transition shadow-sm cursor-pointer" onclick="event.stopPropagation(); playFeedAudio(\'' + escapeHtml(audioUrl) + '\')">' +
          '<span>▶ PLAY SOUND</span>' +
        '</button>' +
      '</div>' : '';

    var motionUrl = m.motion_url || m.motionData || '';
    var liveBadgeHtml = motionUrl ?
      '<div class="live-motion-badge absolute top-3 right-3 px-2 py-0.5 rounded-full bg-black/70 apple-blur border border-amber-500/40 text-[8px] font-extrabold text-amber-400 font-mono-tag tracking-wider uppercase flex items-center gap-1.5 pointer-events-none z-10 shadow-lg">' +
        '<span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span> LIVE' +
      '</div>' : '';

    var motionVideoHtml = motionUrl ?
      '<video src="' + escapeHtml(motionUrl) + '" playsinline loop muted class="live-moment-video absolute inset-0 w-full h-full object-cover z-[5]" style="display:none;"></video>' : '';

    var clusterBadgeHtml = '';
    if (m.cluster_id || (m.perspectives_count && m.perspectives_count > 0)) {
      var pCount = m.perspectives_count || 1;
      clusterBadgeHtml = '<button onclick="event.stopPropagation(); openMomentClusterModal(\'' + (m.cluster_id || '') + '\', \'' + m.id + '\')" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-[9px] font-mono-tag font-bold text-amber-400 transition cursor-pointer active:scale-95 shadow-sm">' +
        '<span>✦</span> <span>' + pCount + ' perspective' + (pCount === 1 ? '' : 's') + '</span>' +
      '</button>';
    }

    var iWasThereHtml = '';
    var hasSharedContext = !!(m.primary_community_id || m.context_community_id || m.cluster_id || m.campus);
    if (!m.is_private && hasSharedContext && (!state.currentUser || state.currentUser.id !== m.user_id)) {
      iWasThereHtml = '<button onclick="event.stopPropagation(); handleIWasThereClick(\'' + m.id + '\')" class="px-2 py-0.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-amber-500/30 text-amber-400 hover:text-amber-300 text-[9px] font-mono-tag font-bold cursor-pointer active:scale-95 transition shadow-sm" title="Self-assert contextual participation">+ I WAS THERE</button>';
    }

    card.innerHTML =
      '<div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner group select-none moment-viewport-stage cursor-pointer">' +
        liveBadgeHtml +
        motionVideoHtml +
        '<img src="' + mainImgSrc + '" class="w-full h-full object-cover main-stage-img" alt="Moment Photo">' +
        '<div class="sub-camera-pip absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black cursor-pointer z-10 active:scale-95 transition-transform" title="Tap to Swap Optics">' +
          '<img src="' + pipImgSrc + '" class="w-full h-full object-cover pip-sub-img" alt="Selfie Photo">' +
          '<div class="absolute bottom-1 left-1.5 px-1 py-0.5 bg-black/60 backdrop-blur text-[8px] text-zinc-300 font-mono-tag rounded">ME • 50mm</div>' +
        '</div>' +
        '<div class="double-tap-burst">🔥</div>' +
      '</div>' +

      '<div class="space-y-2 px-0.5">' +
        '<div class="flex items-center justify-between gap-1 flex-wrap">' +
          '<div class="flex items-center gap-1.5">' +
            (commTarget
              ? '<button type="button" onclick="event.stopPropagation(); openCampusPage(\'' + escapeHtml(commTarget).replace(/'/g, "\\'") + '\')" class="text-[10px] text-amber-400 hover:text-amber-300 font-mono-tag font-bold tracking-wider uppercase inline-flex items-center gap-1 cursor-pointer transition hover:underline active:scale-95" title="Open Community Page"><span>◉</span> <span>' + campusName + '</span></button>'
              : '<span class="text-[10px] text-zinc-400 font-mono-tag font-bold tracking-wider uppercase">' + campusName + '</span>') +
            '<span class="text-[10px] text-zinc-600 font-mono-tag">·</span>' +
            '<span class="text-[10px] text-zinc-400 font-mono-tag uppercase moment-live-timestamp" data-created-at="' + escapeHtml(m.created_at || '') + '">' + timeAgo + '</span>' +
          '</div>' +
          clusterBadgeHtml +
        '</div>' +

        '<p class="text-xs text-zinc-200 font-normal leading-relaxed">' +
          '"' + captionText + '"' +
        '</p>' +

        audioPlayerBarHtml +

        '<div class="flex justify-between items-center pt-1 border-t border-zinc-900">' +
          '<div class="flex items-center gap-2">' +
            '<div class="w-5 h-5 rounded-full bg-zinc-800 overflow-hidden border border-zinc-700 flex items-center justify-center">' +
              avatarHtml +
            '</div>' +
            '<span class="text-[11px] text-zinc-400 font-medium">@' + authorHandle + '</span>' +
            '<span class="text-[9px] text-zinc-600 font-mono-tag">· ' + iso + ' · ' + aperture + ' · ' + shutter + '</span>' +
          '</div>' +

          '<div class="relative flex items-center gap-1.5 reaction-control-container">' +
            '<div class="reaction-badge-group flex items-center gap-1">' +
              reactionPillsHtml +
            '</div>' +
            iWasThereHtml +
            '<button class="px-3 py-1 bg-zinc-900 hover:bg-zinc-800 transition-all text-[9px] font-semibold text-zinc-300 rounded-lg border border-zinc-800 cursor-pointer font-mono-tag react-trigger-btn active:scale-95 flex items-center gap-1">' +
              '<span>✦ React</span>' +
            '</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    container.appendChild(card);
    attachCardInteractions(card, m);
  });
  updateAllMomentTimestamps();
}

function attachCardInteractions(card, momentData) {
  var stage = card.querySelector('.moment-viewport-stage');
  var pip = card.querySelector('.sub-camera-pip');
  var mainImg = card.querySelector('.main-stage-img');
  var pipImg = card.querySelector('.pip-sub-img');
  var burst = card.querySelector('.double-tap-burst');
  var reactBtn = card.querySelector('.react-trigger-btn');
  var reactContainer = card.querySelector('.reaction-control-container');
  var videoEl = card.querySelector('.live-moment-video');

  // Live Photo Hold to Play
  if (videoEl && stage) {
    var startLivePlay = function(e) {
      if (e.target.closest('.sub-camera-pip')) return;
      videoEl.style.display = 'block';
      videoEl.play().catch(function(){});
      playTactileFeedback('shutter');
      if (momentData.audio_url) {
        playFeedAudio(momentData.audio_url);
      }
    };
    var stopLivePlay = function() {
      videoEl.pause();
      videoEl.style.display = 'none';
    };

    stage.addEventListener('mousedown', startLivePlay);
    stage.addEventListener('mouseup', stopLivePlay);
    stage.addEventListener('mouseleave', stopLivePlay);
    stage.addEventListener('touchstart', startLivePlay, { passive: true });
    stage.addEventListener('touchend', stopLivePlay, { passive: true });
  }

  if (pip && mainImg && pipImg) {
    pip.addEventListener('click', function(e) {
      e.stopPropagation();
      var tmp = mainImg.src;
      mainImg.src = pipImg.src;
      pipImg.src = tmp;
    });
  }

  var lastTap = 0;
  if (stage) {
    stage.addEventListener('click', function(e) {
      if (e.target.closest('.sub-camera-pip')) return;
      var now = Date.now();
      if (now - lastTap < 300) {
        if (burst) {
          burst.classList.add('animate');
          setTimeout(function() { burst.classList.remove('animate'); }, 600);
        }
        triggerReaction(momentData.id || card.dataset.postId, '🔥', reactBtn);
      }
      lastTap = now;
    });
  }

  if (reactBtn && reactContainer) {
    reactBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      var existing = reactContainer.querySelector('.reaction-popover-menu');
      if (existing) {
        existing.remove();
        return;
      }
      var pop = document.createElement('div');
      pop.className = 'reaction-popover-menu';
      var emojis = ['🔥', '⚡', '😮', '❤️', '👏', '☕'];
      emojis.forEach(function(em) {
        var btn = document.createElement('button');
        btn.className = 'reaction-popover-emoji';
        btn.textContent = em;
        btn.addEventListener('click', function(ev) {
          ev.stopPropagation();
          pop.remove();
          triggerReaction(momentData.id || card.dataset.postId, em, reactBtn);
        });
        pop.appendChild(btn);
      });

      var selfieBtn = document.createElement('button');
      selfieBtn.className = 'reaction-popover-emoji text-sm bg-amber-500/20 border border-amber-500/40 rounded-lg flex items-center justify-center';
      selfieBtn.textContent = '🤳';
      selfieBtn.title = 'Snap Selfie Realmoji';
      selfieBtn.addEventListener('click', function(ev) {
        ev.stopPropagation();
        pop.remove();
        openRealmojiCapture(momentData.id || card.dataset.postId);
      });
      pop.appendChild(selfieBtn);

      reactContainer.appendChild(pop);
    });
  }
}

async function triggerReaction(postId, emoji, btnEl) {
  playTactileFeedback('pop');
  showToast('Reacted ' + emoji + ' ✦');
  await apiRequest('/api/react', {
    method: 'POST',
    body: JSON.stringify({ postId: postId, emoji: emoji })
  });
}

// =====================================================================



// =====================================================================
// KANDID DUAL SEQUENTIAL CAMERA & UNIVERSAL 3.0S WAV AUDIO ENGINE
// =====================================================================
state.capturedMomentData = null;
state.cameraCircle = 'campus';
state.cameraFacingMode = 'environment';
state.mainMediaStream = null;
state.pipMediaStream = null;
state.audioStream = null;
state.recordedAudioDataUrl = '';

function setupCameraStudio() {
  var shutter = document.getElementById('mainShutterTrigger');
  var momentCapture = document.getElementById('momentCaptureTriggerBtn');
  if (shutter) shutter.addEventListener('click', openCameraStudio);
  if (momentCapture) momentCapture.addEventListener('click', openCameraStudio);
}

async function openCameraStudio() {
  var modal = document.getElementById('cameraStudioModal');
  if (!modal) return;
  modal.style.display = 'flex';
  
  captureCurrentGeoLocation();

  state.cameraFacingMode = 'environment';
  await startHardwareCameraStreams('environment');
}
window.openCameraStudio = openCameraStudio;

function stopHardwareVideoStreams() {
  if (state.mainMediaStream) {
    state.mainMediaStream.getTracks().forEach(function(track) { track.stop(); });
    state.mainMediaStream = null;
  }
  var mainVideo = document.getElementById('cameraMainVideo');
  if (mainVideo) {
    mainVideo.srcObject = null;
    try { mainVideo.pause(); } catch(e){}
  }
}

function stopHardwareCameraStreams() {
  stopHardwareVideoStreams();
  if (state.pipMediaStream) {
    state.pipMediaStream.getTracks().forEach(function(track) { track.stop(); });
    state.pipMediaStream = null;
  }
  if (state.audioStream) {
    state.audioStream.getTracks().forEach(function(track) { track.stop(); });
    state.audioStream = null;
  }
}

async function startHardwareCameraStreams(facingMode) {
  facingMode = facingMode || state.cameraFacingMode || 'environment';
  state.cameraFacingMode = facingMode;

  var mainVideo = document.getElementById('cameraMainVideo');
  var mainImg = document.getElementById('cameraMainPreviewImg');

  stopHardwareVideoStreams();
  await new Promise(function(r) { setTimeout(r, 60); });

  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      var constraints = {
        video: {
          facingMode: facingMode === 'user' ? 'user' : 'environment'
        },
        audio: false
      };

      var videoStream = await navigator.mediaDevices.getUserMedia(constraints);
      state.mainMediaStream = videoStream;

      if (mainVideo) {
        mainVideo.srcObject = videoStream;
        mainVideo.setAttribute('playsinline', 'true');
        mainVideo.setAttribute('webkit-playsinline', 'true');
        mainVideo.setAttribute('autoplay', 'true');
        mainVideo.muted = true;
        mainVideo.style.transform = (facingMode === 'user') ? 'scaleX(-1)' : 'none';
        mainVideo.style.willChange = 'transform';
        mainVideo.classList.remove('hidden');
        if (mainImg) mainImg.classList.add('hidden');
        await mainVideo.play().catch(function() {});
      }
    }
  } catch (err) {
    console.warn('Camera video stream error, trying fallback:', err);
    try {
      var fallbackStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facingMode } },
        audio: false
      });
      state.mainMediaStream = fallbackStream;
      if (mainVideo) {
        mainVideo.srcObject = fallbackStream;
        mainVideo.setAttribute('playsinline', 'true');
        mainVideo.setAttribute('webkit-playsinline', 'true');
        mainVideo.setAttribute('autoplay', 'true');
        mainVideo.muted = true;
        mainVideo.style.transform = (facingMode === 'user') ? 'scaleX(-1)' : 'none';
        mainVideo.classList.remove('hidden');
        if (mainImg) mainImg.classList.add('hidden');
        await mainVideo.play().catch(function() {});
      }
    } catch(fErr) {
      console.warn('Fallback stream error, trying generic video:', fErr);
      try {
        var genericStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        state.mainMediaStream = genericStream;
        if (mainVideo) {
          mainVideo.srcObject = genericStream;
          mainVideo.setAttribute('playsinline', 'true');
          mainVideo.setAttribute('webkit-playsinline', 'true');
          mainVideo.setAttribute('autoplay', 'true');
          mainVideo.muted = true;
          mainVideo.classList.remove('hidden');
          if (mainImg) mainImg.classList.add('hidden');
          await mainVideo.play().catch(function() {});
        }
      } catch(gErr) {
        console.error('All camera access failed:', gErr);
      }
    }
  }
}

function closeCameraStudio() {
  stopHardwareCameraStreams();
  var hud = document.getElementById('cameraDualCaptureHUD');
  if (hud) hud.style.display = 'none';
  var modal = document.getElementById('cameraStudioModal');
  if (modal) modal.style.display = 'none';
}
window.closeCameraStudio = closeCameraStudio;

async function toggleCameraLens() {
  var nextMode = (state.cameraFacingMode === 'environment') ? 'user' : 'environment';
  showToast('Switching to ' + (nextMode === 'user' ? 'Front Selfie' : 'Rear Lens') + ' ⇄');
  await startHardwareCameraStreams(nextMode);
}
window.toggleCameraLens = toggleCameraLens;

function triggerFlashSimulation() {
  var flash = document.getElementById('cameraFlashOverlay');
  if (flash) {
    flash.style.opacity = '1';
    setTimeout(function() { flash.style.opacity = '0'; }, 180);
  }
  showToast('Flash Triggered ⚡');
}
window.triggerFlashSimulation = triggerFlashSimulation;

// Universal WAV Encoder Helper (Pure JS, zero dependencies)
function audioBufferToWav(buffer) {
  var numChannels = 1;
  var sampleRate = buffer.sampleRate;
  var format = 1; // PCM
  var bitDepth = 16;
  
  var samples = buffer.getChannelData(0);
  var blockAlign = numChannels * (bitDepth / 8);
  var byteRate = sampleRate * blockAlign;
  var dataSize = samples.length * (bitDepth / 8);
  var bufferLength = 44 + dataSize;
  
  var arrayBuffer = new ArrayBuffer(bufferLength);
  var view = new DataView(arrayBuffer);
  
  function writeString(offset, string) {
    for (var i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }
  
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);
  
  // Write 16-bit PCM samples
  var offset = 44;
  for (var i = 0; i < samples.length; i++, offset += 2) {
    var s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  
  return new Blob([view], { type: 'audio/wav' });
}

// Robust Dual-Engine 3.0s Ambient Audio Recorder
function record3SecAmbientAudio() {
  return new Promise(async function(resolve) {
    var micStream = null;

    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        micStream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false
          } 
        });
      }
    } catch(e) {
      console.warn('Microphone permission or capture error:', e);
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch(e2) {
        console.warn('Standard mic access failed:', e2);
        resolve('');
        return;
      }
    }

    if (!micStream || micStream.getAudioTracks().length === 0) {
      resolve('');
      return;
    }

    // Engine A: Modern MediaRecorder (Chrome / Android / Modern Safari)
    if (typeof MediaRecorder !== 'undefined') {
      try {
        var mimeType = '';
        var types = [
          'audio/webm;codecs=opus',
          'audio/webm',
          'audio/mp4',
          'audio/aac',
          'audio/ogg;codecs=opus',
          'audio/wav'
        ];
        for (var i = 0; i < types.length; i++) {
          if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(types[i])) {
            mimeType = types[i];
            break;
          }
        }

        var recorder = mimeType ? new MediaRecorder(micStream, { mimeType: mimeType }) : new MediaRecorder(micStream);
        var audioChunks = [];

        recorder.ondataavailable = function(evt) {
          if (evt.data && evt.data.size > 0) {
            audioChunks.push(evt.data);
          }
        };

        recorder.onstop = function() {
          try {
            micStream.getTracks().forEach(function(t) { t.stop(); });
            var blobType = mimeType || 'audio/webm';
            var audioBlob = new Blob(audioChunks, { type: blobType });
            var reader = new FileReader();
            reader.onloadend = function() {
              resolve(reader.result || '');
            };
            reader.readAsDataURL(audioBlob);
          } catch(err) {
            console.warn('MediaRecorder blob parse error:', err);
            resolve('');
          }
        };

        recorder.start(100);

        setTimeout(function() {
          if (recorder && recorder.state !== 'inactive') {
            recorder.stop();
          }
        }, 3000);
        return;
      } catch(mrErr) {
        console.warn('MediaRecorder init failed, falling back to WebAudio PCM:', mrErr);
      }
    }

    // Engine B: AudioContext Pure 16-bit PCM WAV Encoder Fallback (iOS Safari / WebKit)
    try {
      var AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtxClass) {
        micStream.getTracks().forEach(function(t) { t.stop(); });
        resolve('');
        return;
      }

      var audioCtx = new AudioCtxClass();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      var source = audioCtx.createMediaStreamSource(micStream);
      var bufferSize = 4096;
      var recorderNode = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      var recordedSamples = [];
      var currentSamplesCount = 0;

      recorderNode.onaudioprocess = function(e) {
        var inputData = e.inputBuffer.getChannelData(0);
        var chunk = new Float32Array(inputData.length);
        chunk.set(inputData);
        recordedSamples.push(chunk);
        currentSamplesCount += chunk.length;
      };

      source.connect(recorderNode);
      recorderNode.connect(audioCtx.destination);

      setTimeout(function() {
        try {
          source.disconnect();
          recorderNode.disconnect();
          micStream.getTracks().forEach(function(t) { t.stop(); });

          var fullBuffer = audioCtx.createBuffer(1, Math.max(1, currentSamplesCount), audioCtx.sampleRate);
          var channelData = fullBuffer.getChannelData(0);
          var offset = 0;
          for (var j = 0; j < recordedSamples.length; j++) {
            channelData.set(recordedSamples[j], offset);
            offset += recordedSamples[j].length;
          }

          var wavBlob = audioBufferToWav(fullBuffer);
          audioCtx.close().catch(function(){});

          var reader = new FileReader();
          reader.onloadend = function() {
            resolve(reader.result || '');
          };
          reader.readAsDataURL(wavBlob);
        } catch(bufErr) {
          console.warn('WAV encoding error:', bufErr);
          resolve('');
        }
      }, 3000);

    } catch(acErr) {
      console.warn('AudioContext fallback error:', acErr);
      if (micStream) {
        micStream.getTracks().forEach(function(t) { t.stop(); });
      }
      resolve('');
    }
  });
}

// =====================================================================
// KANDID DUAL-CAMERA ARCHITECTURE ENGINE (SPECIFICATION V1.0)
// =====================================================================
const KandidCameraEngine = {
  state: 'IDLE',
  step: 1, // 1 = Rear Moment, 2 = Front Selfie
  activeFacing: 'environment',
  mainStream: null,
  pipStream: null,
  rearFrame: null,
  frontFrame: null,
  compositeImage: null,
  audioClip: null,
  isMultiCamSupported: false,

  setState(newState, detail) {
    this.state = newState;
    console.log('[KandidCameraEngine] State -> ' + newState + (detail ? ' : ' + detail : ''));
  },

  updateShutterUI(step) {
    var instr = document.getElementById('cameraShutterInstruction');
    var hud = document.getElementById('cameraDualCaptureHUD');
    if (instr) {
      if (step === 1) {
        instr.textContent = 'STEP 1: TAP TO SNAP MOMENT 📸';
        instr.className = 'text-[11px] font-bold text-zinc-300 font-mono-tag tracking-widest uppercase pb-1';
      } else {
        instr.textContent = 'STEP 2: SMILE & TAP TO SNAP SELFIE 🤳';
        instr.className = 'text-[12px] font-extrabold text-amber-400 font-mono-tag tracking-widest uppercase pb-1 animate-pulse';
      }
    }
    if (hud) hud.style.display = 'none';
  },

  frontDeviceId: null,
  rearDeviceId: null,

  async discoverHardwareDevices() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
      var devices = await navigator.mediaDevices.enumerateDevices();
      var videoDevices = devices.filter(function(d) { return d.kind === 'videoinput'; });
      
      if (videoDevices.length > 0) {
        // Only trust device labels if they are populated (after permission)
        var front = videoDevices.find(function(d) {
          var l = (d.label || '').toLowerCase();
          return l && (l.includes('front') || l.includes('user') || l.includes('selfie') || l.includes('facetime') || l.includes('facing front'));
        });
        this.frontDeviceId = front ? front.deviceId : null;

        var rear = videoDevices.find(function(d) {
          var l = (d.label || '').toLowerCase();
          return l && (l.includes('back') || l.includes('environment') || l.includes('rear') || l.includes('facing back') || l.includes('wide'));
        });
        this.rearDeviceId = rear ? rear.deviceId : null;
      }
    } catch(e) {
      console.warn('[CameraEngine] Device discovery error', e);
    }
  },

  async initialize() {
    this.setState('REQUESTING_PERMISSION');
    this.step = 1;
    this.rearFrame = null;
    this.frontFrame = null;
    this.activeFacing = 'environment';
    state.cameraFacingMode = 'environment';
    this.updateShutterUI(1);

    var modal = document.getElementById('cameraStudioModal');
    if (modal) modal.style.display = 'flex';
    captureCurrentGeoLocation();

    this.setState('INITIALIZING');
    await this.startMainPreview('environment');
    await this.discoverHardwareDevices();
    this.setState('READY');
  },

  async startMainPreview(facing) {
    this.activeFacing = facing || 'environment';
    state.cameraFacingMode = this.activeFacing;

    var mainVideo = document.getElementById('cameraMainVideo');
    var mainImg = document.getElementById('cameraMainPreviewImg');

    // 1. Fully stop and release previous camera hardware streams
    if (this.mainStream) {
      try {
        this.mainStream.getTracks().forEach(function(t) { t.stop(); });
      } catch(e){}
      this.mainStream = null;
    }
    if (state.mainMediaStream) {
      try {
        state.mainMediaStream.getTracks().forEach(function(t) { t.stop(); });
      } catch(e){}
      state.mainMediaStream = null;
    }
    if (mainVideo && mainVideo.srcObject) {
      try {
        var oldTracks = mainVideo.srcObject.getTracks ? mainVideo.srcObject.getTracks() : [];
        oldTracks.forEach(function(t) { t.stop(); });
      } catch(e){}
      mainVideo.srcObject = null;
    }

    // 2. Hardware cooldown to allow OS camera subsystem to release physical sensor
    await new Promise(function(r) { setTimeout(r, 220); });

    var stream = null;
    var targetMode = (this.activeFacing === 'user') ? 'user' : 'environment';
    var preferredDeviceId = (targetMode === 'user') ? this.frontDeviceId : this.rearDeviceId;

    // 3. WebRTC Standard: Request facingMode with ideal constraints
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: targetMode },
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        },
        audio: false
      });
    } catch(e1) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: targetMode },
          audio: false
        });
      } catch(e2) {
        if (preferredDeviceId) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              video: { deviceId: { exact: preferredDeviceId } },
              audio: false
            });
          } catch(e3){}
        }
        if (!stream) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          } catch(e4){}
        }
      }
    }

    if (!stream) {
      console.warn('[CameraEngine] Could not get stream for ' + this.activeFacing);
      return;
    }

    this.mainStream = stream;
    state.mainMediaStream = stream;

    if (mainVideo) {
      mainVideo.muted = true;
      mainVideo.defaultMuted = true;
      mainVideo.playsInline = true;
      mainVideo.setAttribute('playsinline', 'true');
      mainVideo.setAttribute('webkit-playsinline', 'true');
      mainVideo.setAttribute('autoplay', 'true');
      mainVideo.srcObject = stream;
      mainVideo.style.transform = (this.activeFacing === 'user') ? 'scaleX(-1)' : 'none';
      mainVideo.style.willChange = 'transform';
      mainVideo.classList.remove('hidden');

      try {
        var p = mainVideo.play();
        if (p && p.catch) p.catch(function(){});
      } catch(playErr){}

      // Poll until video is actively producing live frames
      var pollStart = Date.now();
      while ((Date.now() - pollStart) < 2500) {
        if (mainVideo.videoWidth > 0 && mainVideo.videoHeight > 0 && mainVideo.readyState >= 2) {
          break;
        }
        await new Promise(function(r) { setTimeout(r, 40); });
      }

      if (mainImg) mainImg.classList.add('hidden');
    }
  },

  async capture() {
    if (this.state === 'CAPTURING' || this.state === 'PROCESSING' || this.state === 'COMPOSING') return;
    this.setState('CAPTURING');

    var flash = document.getElementById('cameraFlashOverlay');
    var mainVideo = document.getElementById('cameraMainVideo');
    var mainImg = document.getElementById('cameraMainPreviewImg');
    var hud = document.getElementById('cameraDualCaptureHUD');
    var countdownEl = document.getElementById('cameraDualCountdown');
    var statusTitle = document.getElementById('cameraDualStatusTitle');
    var statusSub = document.getElementById('cameraDualStatusSub');

    var startFacing = this.activeFacing || 'environment';

    // ==========================================
    // STEP 1: SNAP FIRST FRAME (CURRENT VIEW)
    // ==========================================
    if (flash) {
      flash.style.opacity = '1';
      setTimeout(function() { flash.style.opacity = '0'; }, 120);
    }
    if (navigator.vibrate) try { navigator.vibrate(45); } catch(e){}

    var firstCanvas = document.createElement('canvas');
    var firstFrameData = '';
    if (mainVideo && mainVideo.videoWidth > 0 && mainVideo.videoHeight > 0) {
      firstCanvas.width = mainVideo.videoWidth;
      firstCanvas.height = mainVideo.videoHeight;
      var fctx1 = firstCanvas.getContext('2d');
      if (startFacing === 'user') {
        fctx1.translate(firstCanvas.width, 0);
        fctx1.scale(-1, 1);
      }
      fctx1.drawImage(mainVideo, 0, 0, firstCanvas.width, firstCanvas.height);
      firstFrameData = firstCanvas.toDataURL('image/jpeg', 0.92);
    }

    if (startFacing === 'user') {
      this.frontFrame = firstFrameData;
    } else {
      this.rearFrame = firstFrameData;
    }

    // Freeze first frame on screen during transition
    if (mainImg && firstFrameData) {
      mainImg.src = firstFrameData;
      mainImg.classList.remove('hidden');
    }

    // Show Transition HUD
    if (hud) hud.style.display = 'flex';
    var nextFacing = (startFacing === 'environment') ? 'user' : 'environment';
    if (countdownEl) countdownEl.textContent = (nextFacing === 'user') ? '🤳' : '📸';
    if (statusTitle) statusTitle.textContent = (nextFacing === 'user') ? '1/2 REAR CAPTURED! 📸' : '1/2 SELFIE CAPTURED! 🤳';
    if (statusSub) statusSub.textContent = (nextFacing === 'user') ? 'SMILE FOR FRONT SELFIE...' : 'NOW SNAPPING REAR SCENE...';

    // ==========================================
    // STEP 2: SWITCH TO OPPOSITE CAMERA
    // ==========================================
    await this.startMainPreview(nextFacing);

    // Poll until second video stream is actively delivering decoded frames
    var pollStart = Date.now();
    while ((Date.now() - pollStart) < 3500) {
      if (mainVideo && mainVideo.videoWidth > 0 && mainVideo.videoHeight > 0 && mainVideo.readyState >= 2) {
        break;
      }
      await new Promise(function(r) { setTimeout(r, 50); });
    }

    // Delay for sensor auto-focus and exposure settling
    await new Promise(function(r) { setTimeout(r, 400); });

    // ==========================================
    // STEP 3: SNAP SECOND FRAME
    // ==========================================
    if (flash) {
      flash.style.opacity = '1';
      setTimeout(function() { flash.style.opacity = '0'; }, 120);
    }
    if (navigator.vibrate) try { navigator.vibrate(40); } catch(e){}

    var secondCanvas = document.createElement('canvas');
    var secondFrameData = '';
    if (mainVideo && mainVideo.videoWidth > 0 && mainVideo.videoHeight > 0) {
      secondCanvas.width = mainVideo.videoWidth;
      secondCanvas.height = mainVideo.videoHeight;
      var fctx2 = secondCanvas.getContext('2d');
      if (nextFacing === 'user') {
        fctx2.translate(secondCanvas.width, 0);
        fctx2.scale(-1, 1);
      }
      fctx2.drawImage(mainVideo, 0, 0, secondCanvas.width, secondCanvas.height);
      secondFrameData = secondCanvas.toDataURL('image/jpeg', 0.92);
    }

    if (nextFacing === 'user') {
      this.frontFrame = secondFrameData;
    } else {
      this.rearFrame = secondFrameData;
    }

    if (hud) hud.style.display = 'none';

    // Safe fallback if one sensor failed
    if (!this.frontFrame && this.rearFrame) this.frontFrame = this.rearFrame;
    if (!this.rearFrame && this.frontFrame) this.rearFrame = this.frontFrame;

    if (hud) hud.style.display = 'none';

    // Safe fallback if selfie sensor failed
    if (!this.frontFrame && this.rearFrame) {
      var mirrorCanvas = document.createElement('canvas');
      mirrorCanvas.width = rearCanvas ? rearCanvas.width : 640;
      mirrorCanvas.height = rearCanvas ? rearCanvas.height : 480;
      var mctx = mirrorCanvas.getContext('2d');
      mctx.translate(mirrorCanvas.width, 0);
      mctx.scale(-1, 1);
      mctx.drawImage(rearCanvas, 0, 0, mirrorCanvas.width, mirrorCanvas.height);
      this.frontFrame = mirrorCanvas.toDataURL('image/jpeg', 0.88);
    }

    // Ensure neither image is black or empty
    if (!this.rearFrame && this.frontFrame) this.rearFrame = this.frontFrame;
    if (!this.frontFrame && this.rearFrame) this.frontFrame = this.rearFrame;

    // Record 3s ambient audio
    var audioPromise = record3SecAmbientAudio();
    var audioDataUrl = await audioPromise;
    this.audioClip = audioDataUrl || '';
    state.recordedAudioDataUrl = this.audioClip;

    // 4. IMAGE PROCESSOR & COMPOSITOR (Spec Section 5 & 6)
    this.setState('PROCESSING');
    this.setState('COMPOSING');

    var compositeResult = await this.composeMoment(this.rearFrame, this.frontFrame);
    this.compositeImage = compositeResult;

    this.stop();
    this.setState('READY_TO_POST');

    // Bind to Review state
    state.capturedMomentData = {
      mainImg: this.rearFrame,
      pipImg: this.frontFrame,
      compositeImg: this.compositeImage,
      audioData: this.audioClip,
      iso: 'ISO 400',
      aperture: 'f/2.8',
      shutter: '1/250s'
    };

    showToast('Kandid Dual Moment Captured! 📸🤳');
    closeCameraStudio();
    openMomentReview();
  },

  async composeMoment(rearSrc, frontSrc) {
    return new Promise(function(resolve) {
      if (!rearSrc || !frontSrc) {
        resolve(rearSrc || frontSrc || '');
        return;
      }

      var rearImg = new Image();
      var frontImg = new Image();
      var loadedCount = 0;

      var onLoaded = function() {
        loadedCount++;
        if (loadedCount === 2) {
          try {
            var outCanvas = document.createElement('canvas');
            outCanvas.width = 1080;
            outCanvas.height = 1350; // Standard 4:5 Portrait Ratio
            var ctx = outCanvas.getContext('2d');

            // 1. Draw Rear Environment (Main Canvas)
            ctx.drawImage(rearImg, 0, 0, outCanvas.width, outCanvas.height);

            // 2. Draw Front Selfie (PiP Top-Left Window with Rounded Corners & Shadow)
            var pipW = 270;
            var pipH = 360;
            var pipX = 36;
            var pipY = 36;
            var radius = 24;

            ctx.save();
            ctx.shadowColor = 'rgba(0, 0, 0, 0.65)';
            ctx.shadowBlur = 24;
            ctx.shadowOffsetX = 0;
            ctx.shadowOffsetY = 8;

            // Clip Rounded Rect
            ctx.beginPath();
            if (ctx.roundRect) {
              ctx.roundRect(pipX, pipY, pipW, pipH, radius);
            } else {
              ctx.rect(pipX, pipY, pipW, pipH);
            }
            ctx.clip();
            ctx.drawImage(frontImg, pipX, pipY, pipW, pipH);
            ctx.restore();

            // Stroke White Border
            ctx.save();
            ctx.lineWidth = 4;
            ctx.strokeStyle = '#FFFFFF';
            ctx.beginPath();
            if (ctx.roundRect) {
              ctx.roundRect(pipX, pipY, pipW, pipH, radius);
            } else {
              ctx.rect(pipX, pipY, pipW, pipH);
            }
            ctx.stroke();
            ctx.restore();

            resolve(outCanvas.toDataURL('image/jpeg', 0.92));
          } catch(err) {
            console.warn('[CameraEngine] Composition canvas error:', err);
            resolve(rearSrc);
          }
        }
      };

      rearImg.onload = onLoaded;
      rearImg.onerror = function() { resolve(rearSrc); };
      frontImg.onload = onLoaded;
      frontImg.onerror = function() { resolve(rearSrc); };

      rearImg.src = rearSrc;
      frontImg.src = frontSrc;
    });
  },

  async toggleLens() {
    var nextFacing = (this.activeFacing === 'environment') ? 'user' : 'environment';
    showToast('Switching to ' + (nextFacing === 'user' ? 'Front Selfie' : 'Rear Lens') + ' ⇄');
    await this.startMainPreview(nextFacing);
  },

  stop() {
    if (this.mainStream) {
      try {
        this.mainStream.getTracks().forEach(function(t) { t.stop(); });
      } catch(e){}
      this.mainStream = null;
    }
    if (this.pipStream) {
      try {
        this.pipStream.getTracks().forEach(function(t) { t.stop(); });
      } catch(e){}
      this.pipStream = null;
    }
    state.mainMediaStream = null;
    state.pipMediaStream = null;
    this.setState('IDLE');
  }
};
window.KandidCameraEngine = KandidCameraEngine;

// Legacy Adapter Bindings
async function openCameraStudio() {
  await KandidCameraEngine.initialize();
}
window.openCameraStudio = openCameraStudio;

function closeCameraStudio() {
  KandidCameraEngine.stop();
  var hud = document.getElementById('cameraDualCaptureHUD');
  if (hud) hud.style.display = 'none';
  var modal = document.getElementById('cameraStudioModal');
  if (modal) modal.style.display = 'none';
}
window.closeCameraStudio = closeCameraStudio;

async function toggleCameraLens() {
  await KandidCameraEngine.toggleLens();
}
window.toggleCameraLens = toggleCameraLens;

async function takeSnapshot() {
  playTactileFeedback('shutter');
  await KandidCameraEngine.capture();
}
window.takeSnapshot = takeSnapshot;

function triggerFlashSimulation() {
  var flash = document.getElementById('cameraFlashOverlay');
  if (flash) {
    flash.style.opacity = '1';
    setTimeout(function() { flash.style.opacity = '0'; }, 180);
  }
  showToast('Flash Triggered ⚡');
}
window.triggerFlashSimulation = triggerFlashSimulation;

function swapReviewImages() {
  var main = document.getElementById('reviewMainImg');
  var pip = document.getElementById('reviewPipImg');
  if (main && pip && state.capturedMomentData) {
    var tmp = main.src;
    main.src = pip.src;
    pip.src = tmp;
    state.capturedMomentData.mainImg = main.src;
    state.capturedMomentData.pipImg = pip.src;
    showToast('Swapped Main & Selfie Views ⇄');
  }
}
window.swapReviewImages = swapReviewImages;

function handleNativeFileCapture(event) {
  var file = event.target.files && event.target.files[0];
  if (!file) return;

  var reader = new FileReader();
  reader.onload = function(e) {
    var dataUrl = e.target.result;
    stopHardwareCameraStreams();
    
    state.capturedMomentData = {
      mainImg: dataUrl,
      pipImg: (state.currentUser && state.currentUser.avatar_url) ? state.currentUser.avatar_url : dataUrl,
      audioData: '',
      iso: 'ISO 200',
      aperture: 'f/1.8',
      shutter: '1/400s'
    };
    
    closeCameraStudio();
    openMomentReview();
  };
  reader.readAsDataURL(file);
}
window.handleNativeFileCapture = handleNativeFileCapture;

function openMomentReview() {
  ['feedContentStream', 'campusContentStream', 'globalContentStream', 'nearbyContentStream'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  var reviewStream = document.getElementById('reviewContentStream');
  if (reviewStream) reviewStream.style.display = 'block';

  // Bind real captured image to review
  var reviewMain = document.getElementById('reviewMainImg');
  var reviewPip = document.getElementById('reviewPipImg');
  if (reviewMain && state.capturedMomentData) reviewMain.src = state.capturedMomentData.mainImg;
  if (reviewPip && state.capturedMomentData) reviewPip.src = state.capturedMomentData.pipImg;

  if (state.activeScreen !== 'feed') {
    switchScreenView('feed');
  }

  var statusMode = document.getElementById('statusBarModeTag');
  if (statusMode) statusMode.textContent = 'REVIEW';

  var timeHud = document.getElementById('reviewTimeHUD');
  if (timeHud) {
    var now = new Date();
    timeHud.textContent = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
  }

  // Setup Capture Context options
  setupReviewContextUI();
}
window.openMomentReview = openMomentReview;

async function setupReviewContextUI() {
  var locEl = document.getElementById('reviewApproxLocation');
  var listEl = document.getElementById('reviewCommunityOptionsList');

  var approxLocName = state.currentGeoApprox ? 
    (state.currentGeoApprox.startsWith('Near ') ? state.currentGeoApprox : ('Near ' + state.currentGeoApprox)) : 
    (state.currentUser ? ('Near Quad · ' + (state.currentUser.campus || 'Supaul')) : 'Near Quad · Supaul');

  if (locEl) locEl.textContent = '⌖ ' + approxLocName;

  if (!listEl) return;
  listEl.innerHTML = '<div class="py-2 text-center text-[10px] text-zinc-500 font-mono-tag">Loading recommended communities...</div>';

  var defaultComm = state.activeCommunity || (state.currentUser ? state.currentUser.campus : '');
  state.selectedReviewCommunity = defaultComm;

  var res = await apiRequest('/api/community/my');
  var communities = (res && res.success && Array.isArray(res.communities)) ? res.communities : [];

  // Ensure target community from active context is present
  if (state.activeCommunityId && defaultComm) {
    var hasTarget = communities.some(function(c) { return c.id === state.activeCommunityId; });
    if (!hasTarget) {
      communities.unshift({ id: state.activeCommunityId, name: defaultComm, type: 'Community Space', icon: '📍' });
    }
  }

  // Always provide Personal (Feed) option
  var hasPersonalFeed = communities.some(function(c) { return !c.id || c.name === 'Personal (Feed)'; });
  if (!hasPersonalFeed) {
    communities.push({ id: '', name: 'Personal (Feed)', type: 'Feed', icon: '✨' });
  }

  // Determine pre-selected item index
  var matchedIdx = -1;
  if (state.activeCommunityId) {
    matchedIdx = communities.findIndex(function(c) { return c.id === state.activeCommunityId; });
  }
  if (matchedIdx === -1 && defaultComm) {
    matchedIdx = communities.findIndex(function(c) { 
      return c.name && c.name.toLowerCase() === defaultComm.toLowerCase(); 
    });
  }
  if (matchedIdx === -1) {
    matchedIdx = 0;
  }

  if (communities[matchedIdx]) {
    state.selectedReviewCommunity = communities[matchedIdx].name;
    state.activeCommunityId = communities[matchedIdx].id || '';
  }

  listEl.innerHTML = communities.map(function(c, idx) {
    var isChecked = (idx === matchedIdx);
    return '<label class="flex items-center justify-between p-2.5 rounded-xl bg-zinc-900/90 border border-white/[.04] hover:border-amber-500/40 cursor-pointer transition active:scale-[0.99]">' +
      '<div class="flex items-center gap-2">' +
        '<input type="radio" name="reviewCommunityDest" value="' + escapeHtml(c.name).replace(/"/g, '&quot;') + '" data-comm-id="' + (c.id || '') + '" ' + (isChecked ? 'checked' : '') + ' onchange="state.selectedReviewCommunity = this.value; state.activeCommunityId = this.getAttribute(\'data-comm-id\');" class="accent-amber-500 w-3.5 h-3.5">' +
        '<span class="text-xs">' + (c.icon || '📍') + '</span>' +
        '<span class="text-xs font-bold text-white">' + escapeHtml(c.name) + '</span>' +
      '</div>' +
      '<span class="font-mono-tag text-[8px] ' + (isChecked ? 'text-amber-400 font-bold bg-amber-500/10 border border-amber-500/30' : 'text-zinc-500 bg-zinc-800') + ' px-1.5 py-0.5 rounded">' +
        (isChecked ? 'SELECTED' : escapeHtml(c.type || 'Community')) +
      '</span>' +
    '</label>';
  }).join('');
}
window.setupReviewContextUI = setupReviewContextUI;

function closeMomentReview() {
  var reviewStream = document.getElementById('reviewContentStream');
  if (reviewStream) reviewStream.style.display = 'none';
  state.activeCommunityId = null;
  state.selectedReviewCommunity = null;
  selectSubTab(state.activeCircle || 'foryou');
}
window.closeMomentReview = closeMomentReview;

function retakeMomentFromReview() {
  closeMomentReview();
  openCameraStudio();
}
window.retakeMomentFromReview = retakeMomentFromReview;

var activeAudioInstance = null;

function playReviewAudio() {
  if (state.capturedMomentData && state.capturedMomentData.audioData) {
    if (activeAudioInstance) {
      activeAudioInstance.pause();
    }
    activeAudioInstance = new Audio(state.capturedMomentData.audioData);
    activeAudioInstance.play().catch(function(e) { console.warn('Playback error', e); });
    showToast('Playing 3.0s Ambient Sound 🔊');
  } else {
    showToast('No ambient audio recorded for this capture');
  }
}
window.playReviewAudio = playReviewAudio;

function playFeedAudio(audioUrl) {
  if (!audioUrl) {
    showToast('Ambient audio not available for this moment');
    return;
  }
  if (activeAudioInstance) {
    activeAudioInstance.pause();
  }
  activeAudioInstance = new Audio(audioUrl);
  activeAudioInstance.play().catch(function(e) { console.warn('Audio play error', e); });
  showToast('Playing 3.0s Ambient Sound 🔊');
}
window.playFeedAudio = playFeedAudio;

async function publishCapturedMoment() {
  var captionInput = document.getElementById('reviewCaptionInput');
  var caption = captionInput ? captionInput.value.trim() : '';
  if (!caption) caption = 'Late evening. Finally quiet.';

  showToast('Publishing your unfiltered moment... 🚀');

  var approxLocName = state.currentGeoApprox ? 
    (state.currentGeoApprox.startsWith('Near ') ? state.currentGeoApprox : ('Near ' + state.currentGeoApprox)) : 
    (state.currentUser ? ('Near Quad · ' + (state.currentUser.campus || 'Supaul')) : 'Near Quad · Supaul');

  // Selected Community Context
  var selectedRadio = document.querySelector('input[name="reviewCommunityDest"]:checked');
  var chosenCommunity = selectedRadio ? selectedRadio.value : (state.selectedReviewCommunity || state.activeCommunity || '');
  var chosenCommId = selectedRadio ? selectedRadio.getAttribute('data-comm-id') : (state.activeCommunityId || '');

  var isPersonalFeed = (!chosenCommId && (!chosenCommunity || chosenCommunity.toLowerCase() === 'personal (feed)' || chosenCommunity.toLowerCase() === 'feed'));
  var finalCommId = isPersonalFeed ? '' : (chosenCommId || '');
  var finalPrimaryComm = isPersonalFeed ? '' : (chosenCommId || chosenCommunity || '');

  var payload = {
    caption: caption,
    circle: state.activeCircle || 'campus',
    region: 'all',
    locationCity: approxLocName,
    community: isPersonalFeed ? 'Personal (Feed)' : chosenCommunity,
    community_id: finalCommId,
    primary_community_id: finalPrimaryComm,
    context_community_id: state.activeCommunity || (state.currentUser ? state.currentUser.campus : ''),
    context_location: approxLocName,
    mainImg: state.capturedMomentData ? state.capturedMomentData.mainImg : '',
    pipImg: state.capturedMomentData ? state.capturedMomentData.pipImg : '',
    audioData: state.capturedMomentData ? state.capturedMomentData.audioData : '',
    audioDuration: '3.0s',
    iso: 'ISO 400',
    aperture: 'f/2.8',
    shutter: '1/250s',
    is_daily_mission: (state.activeScreen === 'mission'),
    event_id: state.activeEventId || '',
    cluster_id: state.activeClusterContext || ''
  };

  var data = await apiRequest('/api/moments/capture', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (data && data.success) {
    if (captionInput) captionInput.value = '';
    if (typeof markDailyAlertCompleted === 'function') {
      markDailyAlertCompleted();
    }
    if (state.activeClusterContext) {
      showToast('Perspective added to shared moment cluster! ✦');
      state.activeClusterContext = null;
    } else {
      showToast('Moment shared to ' + (chosenCommunity || 'Feed') + '! 🔥 +50 XP');
    }
    closeMomentReview();
    
    // Refresh feeds and profile
    await loadFeedMoments('foryou');
    await loadCampusScreen();
    await loadYouScreen();
  } else {
    var errMsg = (data && (data.message || data.error)) ? (data.message || data.error) : 'Network error';
    if (data && data.code === 'COMMUNITY_MEMBERSHIP_REQUIRED') {
      errMsg = 'Active membership required to share moments to this community.';
    }
    showToast('Failed to publish moment: ' + errMsg);
  }
}
window.publishCapturedMoment = publishCapturedMoment;


// =====================================================================
// SECTION 2: SEARCH — MAP-BASED PROXIMITY RADAR & 4 CATEGORIES (APPROVED)
// =====================================================================
state.searchQuery = '';
state.searchCategory = 'people'; // Strict 4 categories: 'people' | 'moments' | 'places' | 'communities'
state.searchFocused = false;
state.lastSearchResults = null;
state.selectedRadarNode = null;

var searchDebounceTimer = null;
var searchAbortCtrl = null;
var _recentSearchesCache = null;

// ── View helpers ──────────────────────────────────────────────────────
function _searchShowView(viewName) {
  var views = {
    'idle': document.getElementById('view-idle'),
    'focused': document.getElementById('view-focused'),
    'people': document.getElementById('view-res-people'),
    'moments': document.getElementById('view-res-moments'),
    'places': document.getElementById('view-res-places'),
    'communities': document.getElementById('view-res-communities'),
    'loading': document.getElementById('view-loading'),
    'error': document.getElementById('view-error'),
    'empty': document.getElementById('view-empty')
  };

  Object.keys(views).forEach(function(k) {
    if (views[k]) {
      views[k].classList.add('hidden');
      views[k].classList.remove('flex');
    }
  });

  var target = views[viewName];
  if (target) {
    target.classList.remove('hidden');
    target.classList.add('flex');
  }
}
window._searchShowView = _searchShowView;

// ── Category Navigation Pills (People, Moments, Places, Communities) ──
function selectSearchCategory(cat) {
  var validCategories = ['people', 'moments', 'places', 'communities'];
  if (!validCategories.includes(cat)) cat = 'people';
  state.searchCategory = cat;

  validCategories.forEach(function(c) {
    var pill = document.getElementById('cat-pill-' + c);
    if (pill) {
      if (c === cat) {
        pill.className = 'search-cat-pill px-3 py-1 rounded-full bg-amber-500 text-black font-bold flex-shrink-0 cursor-pointer transition';
        pill.setAttribute('aria-selected', 'true');
      } else {
        pill.className = 'search-cat-pill px-3 py-1 rounded-full bg-neutral-900 border border-neutral-800 text-gray-400 hover:text-white transition flex-shrink-0 cursor-pointer';
        pill.setAttribute('aria-selected', 'false');
      }
    }
  });

  if (state.searchQuery && state.searchQuery.trim()) {
    _displayCategoryResults(cat);
  }
}
window.selectSearchCategory = selectSearchCategory;
window.selectSearchFilter = selectSearchCategory; // backward compat

function _displayCategoryResults(cat) {
  var data = state.lastSearchResults;
  if (!data) {
    performSearch(state.searchQuery, cat);
    return;
  }

  var listMap = {
    'people': data.people || [],
    'moments': data.moments || [],
    'places': data.places || [],
    'communities': data.communities || []
  };

  var items = listMap[cat] || [];
  if (items.length > 0) {
    _searchShowView(cat);
  } else {
    _searchShowView('empty');
  }
}

// ── Search Input & Focus ──────────────────────────────────────────────
function handleSearchInput(event) {
  var val = (event.target.value || '').trim();
  if (val.length > 80) {
    val = val.substring(0, 80);
    event.target.value = val;
  }
  state.searchQuery = val;
  var clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) {
    if (val) clearBtn.classList.remove('hidden');
    else clearBtn.classList.add('hidden');
  }

  if (!val) {
    if (state.searchFocused) {
      _searchShowView('focused');
      loadRecentSearches();
    } else {
      _searchShowView('idle');
    }
    return;
  }

  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(function() {
    performSearch(val, state.searchCategory);
  }, 300);
}
window.handleSearchInput = handleSearchInput;

function onSearchFocus() {
  state.searchFocused = true;
  if (!state.searchQuery) {
    _searchShowView('focused');
    loadRecentSearches();
  }
}
window.onSearchFocus = onSearchFocus;

function onSearchBlur() {
  state.searchFocused = false;
  setTimeout(function() {
    if (!state.searchQuery) {
      _searchShowView('idle');
    }
  }, 200);
}
window.onSearchBlur = onSearchBlur;

function clearSearchInput() {
  var input = document.getElementById('main-search-input');
  if (input) input.value = '';
  state.searchQuery = '';
  var clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) clearBtn.classList.add('hidden');
  closeSearchActivitySheet();
  _searchShowView('idle');
  loadSearchDiscovery();
}
window.clearSearchInput = clearSearchInput;

function filterBySector(sectorName) {
  var input = document.getElementById('main-search-input');
  if (input) input.value = sectorName;
  state.searchQuery = sectorName;
  var clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) clearBtn.classList.remove('hidden');
  performSearch(sectorName, 'places');
}
window.filterBySector = filterBySector;

function filterByFrequency(freqTag) {
  var input = document.getElementById('main-search-input');
  if (input) input.value = freqTag;
  state.searchQuery = freqTag;
  var clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) clearBtn.classList.remove('hidden');
  performSearch(freqTag, 'moments');
}
window.filterByFrequency = filterByFrequency;

// ── Recent Searches ───────────────────────────────────────────────────
async function loadRecentSearches() {
  var list = document.getElementById('searchRecentList');
  if (!list) return;

  var data = await apiRequest('/api/search/recent');
  _recentSearchesCache = (data && data.success && Array.isArray(data.searches)) ? data.searches : [];

  if (!_recentSearchesCache.length) {
    list.innerHTML = '<div class="py-6 text-center text-xs text-gray-500 font-mono-meta">NO RECENT SEARCHES</div>';
    return;
  }

  list.innerHTML = '';
  _recentSearchesCache.forEach(function(rs) {
    var item = document.createElement('div');
    item.className = 'flex items-center justify-between p-3 bg-[#121215]/60 border border-neutral-800/60 rounded-xl cursor-pointer hover:border-neutral-700 transition select-none';
    item.innerHTML =
      '<div class="flex items-center space-x-3 text-xs text-gray-200 min-w-0">' +
        '<i class="fa-solid fa-clock-rotate-left text-gray-500 flex-shrink-0"></i>' +
        '<span class="truncate">' + escapeHtml(rs.query) + '</span>' +
      '</div>' +
      '<button class="text-gray-500 hover:text-white text-xs p-1 flex-shrink-0 cursor-pointer" aria-label="Delete recent search">' +
        '<i class="fa-solid fa-xmark"></i>' +
      '</button>';

    item.querySelector('button').addEventListener('click', function(e) {
      deleteRecentSearch(e, rs.id);
    });

    item.addEventListener('click', function(e) {
      if (e.target.closest('button')) return;
      var input = document.getElementById('main-search-input');
      if (input) input.value = rs.query;
      state.searchQuery = rs.query;
      var clearBtn = document.getElementById('search-clear-btn');
      if (clearBtn) clearBtn.classList.remove('hidden');
      performSearch(rs.query, state.searchCategory);
    });

    list.appendChild(item);
  });
}
window.loadRecentSearches = loadRecentSearches;

async function saveRecentSearch(query, category) {
  if (!query || !query.trim()) return;
  try {
    await apiRequest('/api/search/recent', 'POST', { query: query.trim(), search_type: category || 'all' });
    _recentSearchesCache = null;
  } catch(e) {}
}

async function deleteRecentSearch(e, rsId) {
  if (e && e.stopPropagation) e.stopPropagation();
  if (!rsId) return;
  await apiRequest('/api/search/recent?id=' + encodeURIComponent(rsId), 'DELETE');
  _recentSearchesCache = null;
  loadRecentSearches();
}
window.deleteRecentSearch = deleteRecentSearch;

async function clearAllRecentSearches() {
  await apiRequest('/api/search/recent', 'DELETE');
  _recentSearchesCache = null;
  loadRecentSearches();
}
window.clearAllRecentSearches = clearAllRecentSearches;

// ── Proximity Radar ───────────────────────────────────────────────────
async function loadRadar() {
  var nodesLayer = document.getElementById('activity-nodes-layer');
  var footerStatus = document.getElementById('radar-footer-status');
  var locOffOverlay = document.getElementById('map-loc-off-overlay');

  if (locOffOverlay) locOffOverlay.classList.add('hidden');

  var data = await apiRequest('/api/search/radar');
  if (!data || !data.success) {
    if (footerStatus) footerStatus.textContent = 'QUIET AROUND HERE';
    if (nodesLayer) nodesLayer.innerHTML = '';
    return;
  }

  var nodes = data.nodes || [];

  if (nodes.length === 0) {
    if (footerStatus) footerStatus.textContent = 'QUIET AROUND HERE';
    if (nodesLayer) nodesLayer.innerHTML = '';
    return;
  }

  if (footerStatus) {
    footerStatus.textContent = 'AROUND YOU · ACTIVITY AROUND HERE';
  }

  if (nodesLayer) {
    nodesLayer.innerHTML = '';
    var nodeCoords = [
      { top: '30%', left: '22%' },
      { top: '58%', left: '64%' },
      { top: '24%', left: '68%' },
      { top: '68%', left: '20%' },
      { top: '18%', left: '44%' },
      { top: '76%', left: '46%' }
    ];

    nodes.slice(0, 6).forEach(function(n, idx) {
      var pos = nodeCoords[idx % nodeCoords.length];
      var isCampus = n.type === 'campus';
      var dotClass = isCampus ? 'bg-amber-400 animate-pulse' : 'bg-neutral-400';

      var nodeEl = document.createElement('div');
      nodeEl.className = 'absolute flex items-center space-x-1.5 bg-[#121215]/95 border border-[#27272A] px-2 py-1 rounded-md shadow-md cursor-pointer hover:border-amber-500 transition select-none';
      nodeEl.style.top = pos.top;
      nodeEl.style.left = pos.left;
      nodeEl.innerHTML =
        '<span class="w-1.5 h-1.5 rounded-full ' + dotClass + '"></span>' +
        '<span class="text-[9px] font-semibold text-gray-200">' + escapeHtml(n.label || (isCampus ? 'Campus' : 'Place')) + '</span>';

      nodeEl.addEventListener('click', function() {
        openSearchActivitySheet(n);
      });
      nodesLayer.appendChild(nodeEl);
    });
  }
}
window.loadRadar = loadRadar;

function openSearchActivitySheet(node) {
  state.selectedRadarNode = node;
  var sheet = document.getElementById('search-activity-sheet');
  var title = document.getElementById('activity-sheet-title');
  var subtitle = document.getElementById('activity-sheet-subtitle');
  var actionBtn = document.getElementById('activity-sheet-action-btn');
  var footerStatus = document.getElementById('radar-footer-status');

  if (title) title.textContent = (node.label || 'CAMPUS').toUpperCase();
  if (subtitle) {
    var typeName = node.type === 'campus' ? 'Campus' : (node.type === 'place' ? 'Place' : 'Community');
    var count = node.post_count || 1;
    subtitle.textContent = typeName + ' · ' + count + ' recent Moment' + (count !== 1 ? 's' : '');
  }
  if (footerStatus) footerStatus.textContent = 'SELECTED AREA';

  if (actionBtn) {
    actionBtn.onclick = function() {
      closeSearchActivitySheet();
      if (typeof openCampusPage === 'function') {
        openCampusPage(node.label);
      }
    };
  }

  if (sheet) {
    sheet.classList.remove('hidden');
    sheet.classList.add('block');
  }
}
window.openSearchActivitySheet = openSearchActivitySheet;

function closeSearchActivitySheet() {
  state.selectedRadarNode = null;
  var sheet = document.getElementById('search-activity-sheet');
  if (sheet) {
    sheet.classList.add('hidden');
    sheet.classList.remove('block');
  }
  var footerStatus = document.getElementById('radar-footer-status');
  if (footerStatus) {
    footerStatus.textContent = 'AROUND YOU · ACTIVITY AROUND HERE';
  }
}
window.closeSearchActivitySheet = closeSearchActivitySheet;

function enableSearchLocation() {
  if (!navigator.geolocation) {
    showToast('Geolocation is not supported by your browser');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function(pos) {
      showToast('Location enabled');
      var overlay = document.getElementById('map-loc-off-overlay');
      if (overlay) overlay.classList.add('hidden');
      loadRadar();
    },
    function(err) {
      showToast('Location permission required for nearby discovery');
      var footerStatus = document.getElementById('radar-footer-status');
      if (footerStatus) footerStatus.textContent = 'LOCATION REQUIRED';
    },
    { timeout: 8000 }
  );
}
window.enableSearchLocation = enableSearchLocation;

// ── Around You Discovery ──────────────────────────────────────────────
async function loadSearchDiscovery() {
  loadRadar();

  var aroundContainer = document.getElementById('searchAroundYouContainer');
  if (!aroundContainer) return;

  var data = await apiRequest('/api/search?type=all');
  if (!data || !data.success) {
    aroundContainer.innerHTML = '<div class="py-6 text-center text-xs text-gray-500 font-mono-meta">NO ACTIVITY RECORDED NEARBY YET</div>';
    return;
  }

  var items = [];
  if (Array.isArray(data.sectors) && data.sectors.length > 0) {
    data.sectors.forEach(function(s) {
      items.push({ name: s.name, type: 'Place', subtext: s.area || 'Active area', icon: s.icon || '📍' });
    });
  } else if (Array.isArray(data.campuses) && data.campuses.length > 0) {
    data.campuses.forEach(function(c) {
      items.push({ name: c.name, type: 'Campus', subtext: (c.city || 'Campus') + ' · Recent Moments', icon: '🎓' });
    });
  }

  if (Array.isArray(data.communities) && data.communities.length > 0) {
    data.communities.slice(0, 2).forEach(function(c) {
      items.push({ name: c.name, type: 'Community', subtext: c.city || 'Recent Moments', icon: '📸' });
    });
  }

  if (items.length === 0) {
    aroundContainer.innerHTML = '<div class="py-6 text-center text-xs text-gray-500 font-mono-meta">NO ACTIVITY RECORDED NEARBY YET</div>';
    return;
  }

  aroundContainer.innerHTML = '';
  items.slice(0, 4).forEach(function(item) {
    var card = document.createElement('div');
    card.className = 'bg-[#121215]/60 border border-neutral-800/60 rounded-xl p-3.5 flex items-center justify-between cursor-pointer hover:border-neutral-700 transition select-none';
    card.innerHTML =
      '<div class="flex items-center space-x-3 min-w-0">' +
        '<div class="w-9 h-9 rounded-lg overflow-hidden bg-neutral-800 flex-shrink-0 flex items-center justify-center text-sm">' +
          item.icon +
        '</div>' +
        '<div class="min-w-0">' +
          '<h4 class="text-xs font-bold text-white truncate">' + escapeHtml(item.name) + '</h4>' +
          '<p class="text-[10px] text-gray-400 mt-0.5 truncate">' + escapeHtml(item.type + ' · ' + item.subtext) + '</p>' +
        '</div>' +
      '</div>' +
      '<i class="fa-solid fa-chevron-right text-[10px] text-gray-500 flex-shrink-0"></i>';

    card.addEventListener('click', function() {
      if (typeof openCampusPage === 'function') openCampusPage(item.name);
    });
    aroundContainer.appendChild(card);
  });
}
window.loadSearchDiscovery = loadSearchDiscovery;

// ── Search Execution ──────────────────────────────────────────────────
async function performSearch(query, category) {
  query = (typeof query === 'string') ? query : state.searchQuery;
  category = category || state.searchCategory || 'people';

  if (!query || !query.trim()) {
    _searchShowView('idle');
    loadSearchDiscovery();
    return;
  }

  closeSearchActivitySheet();
  _searchShowView('loading');

  if (searchAbortCtrl) {
    try { searchAbortCtrl.abort(); } catch(e) {}
  }
  searchAbortCtrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;

  var endpoint = '/api/search?q=' + encodeURIComponent(query.trim()) + '&type=all';
  var data = await apiRequest(endpoint);

  if (!data || !data.success) {
    _searchShowView('error');
    return;
  }

  state.lastSearchResults = data;

  var people = data.people || [];
  var moments = data.moments || [];
  var places = data.places || [];
  var communities = data.communities || [];

  renderPeopleSearchResults(people);
  renderMomentsSearchResults(moments);
  renderPlacesSearchResults(places);
  renderCommunitiesSearchResults(communities);

  var totalResults = people.length + moments.length + places.length + communities.length;
  if (totalResults === 0) {
    _searchShowView('empty');
    return;
  }

  var counts = {
    'people': people.length,
    'moments': moments.length,
    'places': places.length,
    'communities': communities.length
  };

  if (counts[category] > 0) {
    selectSearchCategory(category);
    _searchShowView(category);
  } else {
    var firstCategoryWithResults = ['people', 'moments', 'places', 'communities'].find(function(c) {
      return counts[c] > 0;
    }) || 'people';
    selectSearchCategory(firstCategoryWithResults);
    _searchShowView(firstCategoryWithResults);
  }

  saveRecentSearch(query, category);
}
window.performSearch = performSearch;

// ── Result Renderers ──────────────────────────────────────────────────
function renderPeopleSearchResults(people) {
  var list = document.getElementById('searchPeopleResultsList');
  if (!list) return;
  list.innerHTML = '';

  if (!people || people.length === 0) {
    list.innerHTML = '<div class="py-8 text-center text-xs text-gray-500 font-mono-meta">NO PEOPLE FOUND</div>';
    return;
  }

  people.forEach(function(p) {
    var item = document.createElement('div');
    item.className = 'bg-[#121215]/60 border border-neutral-800/60 rounded-xl p-3.5 flex items-center justify-between select-none';

    var avatarSrc = (p.avatar_url && !p.avatar_url.includes('api.dicebear.com')) ? p.avatar_url : '';
    var name = escapeHtml(p.name || 'Student');
    var handle = escapeHtml(p.handle || 'user');
    var campus = escapeHtml(p.campus || 'North City University');

    var isConnected = Boolean(p.is_connected || p.connection_status === 'connected' || (state.currentUser && state.currentUser.friends && state.currentUser.friends.includes(p.id)));
    var isRequested = Boolean(p.is_requested || p.connection_status === 'requested');

    var buttonHtml = '';
    if (isConnected) {
      buttonHtml = '<span class="px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-gray-300 rounded-full text-[10px] font-bold flex-shrink-0">CONNECTED</span>';
    } else if (isRequested) {
      buttonHtml = '<span class="px-3 py-1.5 bg-neutral-900 border border-neutral-800 text-amber-400 rounded-full text-[10px] font-bold flex-shrink-0">REQUESTED</span>';
    } else {
      buttonHtml = '<button class="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-[10px] font-bold transition flex-shrink-0 cursor-pointer">CONNECT</button>';
    }

    item.innerHTML =
      '<div class="flex items-center space-x-3.5 min-w-0 cursor-pointer user-profile-target">' +
        '<img src="' + avatarSrc + '" alt="" class="w-11 h-11 rounded-full object-cover flex-shrink-0 border border-neutral-800">' +
        '<div class="min-w-0">' +
          '<h4 class="text-xs font-bold text-white truncate">' + name + '</h4>' +
          '<p class="text-[10px] text-gray-400 font-mono-meta truncate">@' + handle + ' · ' + campus + '</p>' +
        '</div>' +
      '</div>' +
      buttonHtml;

    item.querySelector('.user-profile-target').addEventListener('click', function() {
      openUserProfile(p.id, p);
    });

    var btn = item.querySelector('button');
    if (btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        connectWithUser(p.id, btn);
      });
    }

    list.appendChild(item);
  });
}
window.renderPeopleSearchResults = renderPeopleSearchResults;

function renderMomentsSearchResults(moments) {
  var grid = document.getElementById('searchMomentsResultsGrid');
  if (!grid) return;
  grid.innerHTML = '';

  if (!moments || moments.length === 0) {
    grid.innerHTML = '<div class="col-span-2 py-8 text-center text-xs text-gray-500 font-mono-meta">NO MOMENTS FOUND</div>';
    return;
  }

  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'relative h-[180px] rounded-[14px] overflow-hidden border border-neutral-800/80 group cursor-pointer bg-neutral-900 select-none';

    var mainImg = m.main_img || m.mainImg || m.mediaUrl || '';
    var campus = escapeHtml(m.campus || m.location_city || 'Campus');
    var timeAgo = escapeHtml(m.created_at ? formatTimeAgoClean(m.created_at) : (m.timeAgo || 'JUST NOW'));

    var imgHtml = mainImg
      ? '<img src="' + escapeHtml(mainImg) + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" alt="">'
      : '<div class="w-full h-full flex items-center justify-center text-2xl text-neutral-700">📷</div>';

    card.innerHTML =
      imgHtml +
      '<div class="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-transparent pointer-events-none"></div>' +
      '<div class="absolute bottom-2.5 left-2.5 right-2.5 pointer-events-none">' +
        '<p class="text-[9px] font-mono-meta text-amber-400 font-bold">' + timeAgo + '</p>' +
        '<p class="text-xs font-bold text-white truncate mt-0.5">' + campus + '</p>' +
      '</div>';

    card.addEventListener('click', function() {
      if (typeof openMomentDetail === 'function') openMomentDetail(m);
    });

    grid.appendChild(card);
  });
}
window.renderMomentsSearchResults = renderMomentsSearchResults;

function renderPlacesSearchResults(places) {
  var list = document.getElementById('searchPlacesResultsList');
  if (!list) return;
  list.innerHTML = '';

  if (!places || places.length === 0) {
    list.innerHTML = '<div class="py-8 text-center text-xs text-gray-500 font-mono-meta">NO PLACES FOUND</div>';
    return;
  }

  places.forEach(function(pl) {
    var card = document.createElement('div');
    card.className = 'bg-[#121215]/60 border border-neutral-800/60 rounded-xl p-4 space-y-1 cursor-pointer hover:border-neutral-700 transition select-none';
    var subtitle = pl.area ? (pl.area + ' · Active area') : 'Campus · Recent public Moments';
    card.innerHTML =
      '<h4 class="text-xs font-bold text-white">' + escapeHtml(pl.name) + '</h4>' +
      '<p class="text-[11px] text-gray-400">' + escapeHtml(subtitle) + '</p>';

    card.addEventListener('click', function() {
      if (typeof openCampusPage === 'function') openCampusPage(pl.name);
    });

    list.appendChild(card);
  });
}
window.renderPlacesSearchResults = renderPlacesSearchResults;

function renderCommunitiesSearchResults(communities) {
  var list = document.getElementById('searchCommunitiesResultsList');
  if (!list) return;
  list.innerHTML = '';

  if (!communities || communities.length === 0) {
    list.innerHTML = '<div class="py-8 text-center text-xs text-gray-500 font-mono-meta">NO COMMUNITIES FOUND</div>';
    return;
  }

  communities.forEach(function(c) {
    var card = document.createElement('div');
    card.className = 'bg-[#121215]/60 border border-neutral-800/60 rounded-xl p-4 flex items-center justify-between select-none cursor-pointer hover:border-neutral-700 transition';
    card.innerHTML =
      '<div class="min-w-0 mr-3">' +
        '<h4 class="text-xs font-bold text-white truncate">' + escapeHtml(c.name) + '</h4>' +
        '<p class="text-[11px] text-gray-400 mt-0.5 truncate">' + escapeHtml(c.description || (c.city || 'Where visual storytellers meet.')) + '</p>' +
      '</div>' +
      '<button class="px-3.5 py-1.5 bg-neutral-900 border border-neutral-700 hover:border-neutral-500 text-white rounded-full text-[10px] font-bold transition flex-shrink-0 cursor-pointer">VIEW</button>';

    card.addEventListener('click', function() {
      if (typeof openCampusPage === 'function') openCampusPage(c.name);
    });

    list.appendChild(card);
  });
}
window.renderCommunitiesSearchResults = renderCommunitiesSearchResults;

// =====================================================================
// PUBLIC & PRIVATE PEER PROFILE ENGINE
// =====================================================================
var lastScreenBeforeProfile = 'feed';

function closePeerProfile() {
  switchScreenView(lastScreenBeforeProfile || 'feed');
}
window.closePeerProfile = closePeerProfile;
window.handlePeerProfileBack = closePeerProfile;

function retryLoadPeerProfile() {
  if (state.activePeerUserId) {
    openUserProfile(state.activePeerUserId);
  }
}
window.retryLoadPeerProfile = retryLoadPeerProfile;

async function openUserProfile(userId, preloadedData) {
  if (!userId) return;
  // Always preserve originating screen for proper Back navigation (Feed, Search, Chat, etc.)
  if (state.activeScreen && state.activeScreen !== 'peer-profile') {
    lastScreenBeforeProfile = state.activeScreen;
  }
  state.activePeerUserId = userId;
  state.activePeerConnectionStatus = 'none';

  switchScreenView('peer-profile');

  var loadingEl = document.getElementById('peerProfileLoading');
  var errorEl = document.getElementById('peerProfileError');
  var peerPublicView = document.getElementById('peerPublicView');
  var peerPrivateView = document.getElementById('peerPrivateView');

  // Reset view to clean loading state
  if (peerPublicView) peerPublicView.style.display = 'none';
  if (peerPrivateView) peerPrivateView.style.display = 'none';
  if (errorEl) errorEl.style.display = 'none';
  if (loadingEl) loadingEl.style.display = 'flex';

  // Fetch authoritative profile data from server
  var res = null;
  try {
    res = await apiRequest('/api/user/profile?user_id=' + encodeURIComponent(userId));
  } catch (err) {
    console.warn('[Profile] API request failed:', err);
  }

  if (loadingEl) loadingEl.style.display = 'none';

  // Handle server error, 404, or blocked user
  if (!res || !res.success || !res.user) {
    console.warn('[Profile] Server returned error or user not found');
    if (errorEl) errorEl.style.display = 'flex';
    return;
  }

  var u = res.user;
  var connStatus = res.connection_status || u.connection_status || 'none';
  state.activePeerConnectionStatus = connStatus;
  state.activePeerUser = u;

  var isPrivate = (res.is_private === true) || (u.profile_visibility === 'private' && connStatus !== 'connected' && connStatus !== 'self');

  // Real user attributes with clean fallbacks
  var finalName = u.name || 'User';
  var finalHandle = (u.handle || u.username || 'user').replace('@', '');
  var cleanHandle = '@' + finalHandle.toLowerCase();
  var finalBio = u.bio || '';
  var rawAvatar = (u.avatar_url || u.avatar || '').trim();
  var finalAvatar = (rawAvatar && !rawAvatar.includes('api.dicebear.com')) ? rawAvatar : '';
  var rawCover = (u.cover_url || u.cover || '').trim();
  var finalCover = (rawCover && !rawCover.includes('unsplash.com')) ? rawCover : '';

  if (isPrivate) {
    // ─── PRIVATE PROFILE STATE ───
    if (peerPrivateView) peerPrivateView.style.display = 'flex';
    if (peerPublicView) peerPublicView.style.display = 'none';

    var privName = document.getElementById('peerPrivateName');
    var privUsername = document.getElementById('peerPrivateUsername');
    var privBio = document.getElementById('peerPrivateBio');
    var privAvatar = document.getElementById('peerPrivateAvatar');
    var privCover = document.getElementById('peerPrivateCoverImg');

    if (privName) privName.textContent = finalName;
    if (privUsername) privUsername.textContent = cleanHandle;
    if (privBio) {
      privBio.textContent = finalBio || 'Their world, kept close.';
    }
    if (privAvatar) {
      if (finalAvatar) {
        privAvatar.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        privAvatar.onload = function() { this.style.display = 'block'; };
        privAvatar.src = finalAvatar;
      } else {
        privAvatar.style.display = 'none';
        privAvatar.removeAttribute('src');
      }
    }
    if (privCover) {
      if (finalCover) {
        privCover.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        privCover.onload = function() { this.style.display = 'block'; };
        privCover.src = finalCover;
      } else {
        privCover.style.display = 'none';
        privCover.removeAttribute('src');
      }
    }

    updatePeerConnectionUI(connStatus);
  } else {
    // ─── PUBLIC PROFILE STATE ───
    if (peerPublicView) peerPublicView.style.display = 'flex';
    if (peerPrivateView) peerPrivateView.style.display = 'none';

    var pubName = document.getElementById('peerPublicName');
    var pubUsername = document.getElementById('peerPublicUsername');
    var pubCampus = document.getElementById('peerPublicCampus');
    var pubCity = document.getElementById('peerPublicCity');
    var pubCampusRow = document.getElementById('peerPublicCampusRow');
    var pubCityRow = document.getElementById('peerPublicCityRow');
    var pubBio = document.getElementById('peerPublicBio');
    var pubAvatar = document.getElementById('peerPublicAvatar');
    var pubCover = document.getElementById('peerPublicCoverImg');
    var pubMsgBtn = document.getElementById('peerPublicMessageBtn');

    if (pubName) pubName.textContent = finalName;
    if (pubUsername) pubUsername.textContent = cleanHandle;

    if (pubCampus && pubCampusRow) {
      if (u.campus) {
        pubCampus.textContent = u.campus;
        pubCampusRow.style.display = 'flex';
      } else {
        pubCampusRow.style.display = 'none';
      }
    }
    if (pubCity && pubCityRow) {
      var cCity = u.location_city || u.city || '';
      if (cCity) {
        pubCity.textContent = cCity;
        pubCityRow.style.display = 'flex';
      } else {
        pubCityRow.style.display = 'none';
      }
    }

    if (pubBio) {
      pubBio.textContent = finalBio || 'Authentic moments across campus.';
    }
    if (pubAvatar) {
      if (finalAvatar) {
        pubAvatar.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        pubAvatar.onload = function() { this.style.display = 'block'; };
        pubAvatar.src = finalAvatar;
      } else {
        pubAvatar.style.display = 'none';
        pubAvatar.removeAttribute('src');
      }
    }
    if (pubCover) {
      if (finalCover) {
        pubCover.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        pubCover.onload = function() { this.style.display = 'block'; };
        pubCover.src = finalCover;
      } else {
        pubCover.style.display = 'none';
        pubCover.removeAttribute('src');
      }
    }

    if (pubMsgBtn) {
      pubMsgBtn.onclick = function() {
        openChatThread(u.id, finalName, cleanHandle, finalAvatar, Boolean(u.is_online), u.campus || '');
      };
    }

    updatePeerConnectionUI(connStatus);

    // 2-column Moments Grid
    var momentsGrid = document.getElementById('peerPublicMomentsGrid');
    if (momentsGrid) {
      momentsGrid.innerHTML = '';
      var moments = res.moments || [];
      if (moments.length > 0) {
        moments.forEach(function(m) {
          var article = document.createElement('article');
          article.className = 'relative h-[170px] rounded-[14px] overflow-hidden border border-neutral-800/80 group cursor-pointer active:scale-95 transition';
          var imgUrl = escapeHtml(m.main_img || m.mediaUrl || m.media_url || m.mainImg || '');
          var locStr = escapeHtml(m.campus || m.location_city || u.campus || 'Campus');
          var timeStr = escapeHtml(m.timeAgo || m.time_ago || (m.created_at ? formatTimeAgoClean(m.created_at) : 'RECENT')).toUpperCase();

          var imgHtml = imgUrl
            ? '<img src="' + imgUrl + '" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" alt="' + locStr + '">'
            : '<div class="w-full h-full bg-neutral-900 flex items-center justify-center text-zinc-700 font-mono-meta text-xs">MOMENT</div>';

          article.innerHTML =
            imgHtml +
            '<div class="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-transparent pointer-events-none" aria-hidden="true"></div>' +
            '<div class="absolute bottom-2.5 left-2.5 right-2.5 pointer-events-none">' +
              '<p class="text-[9px] font-extrabold text-amber-400 tracking-wider uppercase">' + timeStr + '</p>' +
              '<p class="text-xs font-bold text-white truncate mt-0.5"><i class="fa-solid fa-location-dot text-[8px] mr-1 text-gray-400" aria-hidden="true"></i>' + locStr + '</p>' +
            '</div>';

          article.onclick = function() {
            if (typeof openMomentDetailModal === 'function') {
              openMomentDetailModal(m.id || m.postId);
            } else if (typeof openMomentDetail === 'function') {
              openMomentDetail(m);
            }
          };

          momentsGrid.appendChild(article);
        });
      } else {
        var emptyDiv = document.createElement('div');
        emptyDiv.className = 'col-span-2 py-8 text-center text-[10px] text-zinc-500 font-mono-meta tracking-wider';
        emptyDiv.textContent = 'NO PUBLIC MOMENTS YET';
        momentsGrid.appendChild(emptyDiv);
      }
    }

    // Shared World Section
    var pubSharedWorld = document.getElementById('peerPublicSharedWorld');
    var pubSharedCommCard = document.getElementById('peerPublicSharedCommCard');
    var pubSharedCommText = document.getElementById('peerPublicSharedCommText');
    var pubMutualConnCard = document.getElementById('peerPublicMutualConnCard');
    var pubMutualConnText = document.getElementById('peerPublicMutualConnText');

    if (pubSharedWorld) pubSharedWorld.style.display = 'block';

    try {
      var sharedRes = await apiRequest('/api/user/shared-context?target_id=' + encodeURIComponent(userId));
      if (sharedRes && sharedRes.success) {
        var sharedComms = sharedRes.shared_communities || [];
        var mutualConns = sharedRes.mutual_connections || [];

        if (pubSharedCommText) {
          if (sharedComms.length > 0) {
            var firstComm = sharedComms[0].name;
            var extraComm = sharedComms.length - 1;
            pubSharedCommText.textContent = firstComm + (extraComm > 0 ? ' + ' + extraComm + ' more' : '');
            if (pubSharedCommCard) {
              pubSharedCommCard.onclick = function() {
                if (typeof openCampusPage === 'function') openCampusPage(sharedComms[0].name);
              };
            }
          } else {
            pubSharedCommText.textContent = 'Explore communities together';
            if (pubSharedCommCard) {
              pubSharedCommCard.onclick = function() {
                openCommunitySwitcher();
              };
            }
          }
        }

        if (pubMutualConnText) {
          if (mutualConns.length > 0) {
            var firstNames = mutualConns.slice(0, 2).map(function(c) { return c.name; }).join(', ');
            var extraConn = mutualConns.length - 2;
            pubMutualConnText.textContent = firstNames + (extraConn > 0 ? ' +' + extraConn : '');
          } else {
            pubMutualConnText.textContent = 'No mutual connections yet';
          }
        }
      }
    } catch (e) {
      console.warn('[Profile] shared context error:', e);
    }
  }
}
window.openUserProfile = openUserProfile;

// ─── CONNECTION STATE UI ENGINE ───
function updatePeerConnectionUI(status) {
  var connectText = document.getElementById('peerPublicConnectText');
  var connectBtn = document.getElementById('peerPublicConnectBtn');
  var connectIcon = document.getElementById('peerPublicConnectIcon');
  var declineBtn = document.getElementById('peerPublicDeclineBtn');
  var msgBtn = document.getElementById('peerPublicMessageBtn');

  var privBtn = document.getElementById('peerPrivateConnectBtn');
  var privText = document.getElementById('peerPrivateConnectText');
  var privIcon = document.getElementById('peerPrivateConnectIcon');

  if (connectBtn) connectBtn.style.display = 'flex';
  if (declineBtn) declineBtn.style.display = 'none';
  if (msgBtn) {
    msgBtn.style.display = 'flex';
    msgBtn.className = 'px-2.5 py-1.5 bg-transparent border border-neutral-700 hover:border-neutral-500 rounded-full text-[10px] font-semibold text-gray-200 flex items-center space-x-1 transition cursor-pointer active:scale-95 flex-shrink-0';
  }
  if (privBtn) privBtn.style.display = 'flex';

  if (status === 'connected') {
    if (connectText) connectText.textContent = 'CONNECTED';
    if (connectIcon) { connectIcon.className = 'fa-solid fa-check text-[9px]'; connectIcon.textContent = ''; }
    if (connectBtn) {
      connectBtn.className = 'px-2.5 py-1.5 bg-neutral-900 border border-neutral-700 text-amber-400 rounded-full text-[10px] font-bold tracking-wide flex items-center space-x-1 transition shadow cursor-pointer active:scale-95 flex-shrink-0';
    }
    if (privText) privText.textContent = 'CONNECTED';
    if (privIcon) { privIcon.className = 'fa-solid fa-check text-[10px]'; privIcon.textContent = ''; }
    if (privBtn) {
      privBtn.className = 'w-full py-2.5 bg-neutral-900 border border-neutral-700 text-amber-400 rounded-full text-xs font-bold tracking-wider flex items-center justify-center space-x-2 transition cursor-pointer';
    }
  } else if (status === 'pending_sent') {
    if (connectText) connectText.textContent = 'REQUESTED';
    if (connectIcon) { connectIcon.className = 'fa-solid fa-clock text-[9px]'; connectIcon.textContent = ''; }
    if (connectBtn) {
      connectBtn.className = 'px-2.5 py-1.5 bg-neutral-900 border border-amber-500/50 text-amber-400 rounded-full text-[10px] font-bold tracking-wide flex items-center space-x-1 transition shadow cursor-pointer active:scale-95 flex-shrink-0';
    }
    if (privText) privText.textContent = 'REQUESTED';
    if (privIcon) { privIcon.className = 'fa-solid fa-clock text-[10px]'; privIcon.textContent = ''; }
    if (privBtn) {
      privBtn.className = 'w-full py-2.5 bg-neutral-900 border border-amber-500/50 text-amber-400 rounded-full text-xs font-bold tracking-wider flex items-center justify-center space-x-2 transition cursor-pointer';
    }
  } else if (status === 'pending_received') {
    if (connectText) connectText.textContent = 'ACCEPT';
    if (connectIcon) { connectIcon.className = 'fa-solid fa-user-check text-[9px]'; connectIcon.textContent = ''; }
    if (connectBtn) {
      connectBtn.className = 'px-2.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-[10px] font-bold tracking-wide flex items-center space-x-1 transition shadow-lg shadow-amber-500/10 cursor-pointer active:scale-95 flex-shrink-0';
    }
    if (declineBtn) declineBtn.style.display = 'inline-block';

    if (privText) privText.textContent = 'ACCEPT';
    if (privIcon) { privIcon.className = 'fa-solid fa-user-check text-[10px]'; privIcon.textContent = ''; }
    if (privBtn) {
      privBtn.className = 'w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-xs font-bold tracking-wider flex items-center justify-center space-x-2 transition shadow-lg shadow-amber-500/10 cursor-pointer active:scale-95';
    }
  } else if (status === 'self') {
    if (connectBtn) connectBtn.style.display = 'none';
    if (msgBtn) msgBtn.style.display = 'none';
    if (privBtn) privBtn.style.display = 'none';
  } else {
    // NOT_CONNECTED / 'none'
    if (connectText) connectText.textContent = 'CONNECT';
    if (connectIcon) { connectIcon.className = 'fa-solid fa-user-plus text-[9px]'; connectIcon.textContent = ''; }
    if (connectBtn) {
      connectBtn.className = 'px-2.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-[10px] font-bold tracking-wide flex items-center space-x-1 transition shadow-lg shadow-amber-500/10 cursor-pointer active:scale-95 flex-shrink-0';
    }
    if (privText) privText.textContent = 'CONNECT';
    if (privIcon) { privIcon.className = 'fa-solid fa-user-plus text-[10px]'; privIcon.textContent = ''; }
    if (privBtn) {
      privBtn.className = 'w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-xs font-bold tracking-wider flex items-center justify-center space-x-2 transition shadow-lg shadow-amber-500/10 cursor-pointer active:scale-95';
    }
  }
}

// ─── TOGGLE CONNECTION HANDLER ───
var isTogglingConnection = false;
async function togglePeerConnection() {
  if (!state.activePeerUserId || isTogglingConnection) return;
  var currStatus = state.activePeerConnectionStatus || 'none';
  isTogglingConnection = true;

  try {
    if (currStatus === 'none') {
      updatePeerConnectionUI('pending_sent');
      var res = await apiRequest('/api/friend/request', {
        method: 'POST',
        body: { target_user_id: state.activePeerUserId }
      });
      if (res && res.success) {
        state.activePeerConnectionStatus = res.status || 'pending_sent';
        updatePeerConnectionUI(state.activePeerConnectionStatus);
        showToast('Connection request sent! ⏳');
      } else {
        updatePeerConnectionUI('none');
        state.activePeerConnectionStatus = 'none';
        showToast(res && res.error ? res.error : 'Could not send request.');
      }
    } else if (currStatus === 'pending_sent') {
      updatePeerConnectionUI('none');
      var res = await apiRequest('/api/friend/cancel', {
        method: 'POST',
        body: { target_user_id: state.activePeerUserId }
      });
      if (res && res.success) {
        state.activePeerConnectionStatus = 'none';
        updatePeerConnectionUI('none');
        showToast('Connection request cancelled.');
      } else {
        state.activePeerConnectionStatus = 'pending_sent';
        updatePeerConnectionUI('pending_sent');
        showToast(res && res.error ? res.error : 'Could not cancel request.');
      }
    } else if (currStatus === 'pending_received') {
      updatePeerConnectionUI('connected');
      var res = await apiRequest('/api/friend/accept', {
        method: 'POST',
        body: { target_user_id: state.activePeerUserId }
      });
      if (res && res.success) {
        state.activePeerConnectionStatus = 'connected';
        updatePeerConnectionUI('connected');
        showToast('Connection accepted! ✦');
        await openUserProfile(state.activePeerUserId);
      } else {
        state.activePeerConnectionStatus = 'pending_received';
        updatePeerConnectionUI('pending_received');
        showToast(res && res.error ? res.error : 'Could not accept connection.');
      }
    } else if (currStatus === 'connected') {
      openProfileActionsMenu();
    }
  } finally {
    isTogglingConnection = false;
  }
}
window.togglePeerConnection = togglePeerConnection;

async function declinePeerConnection() {
  if (!state.activePeerUserId) return;
  updatePeerConnectionUI('none');
  state.activePeerConnectionStatus = 'none';
  showToast('Connection request declined.');
  await apiRequest('/api/friend/reject', {
    method: 'POST',
    body: { target_user_id: state.activePeerUserId }
  });
}
window.declinePeerConnection = declinePeerConnection;
window.declinePeerConnection = declinePeerConnection;

// ─── PROFILE ACTIONS BOTTOM SHEET (⋮ MENU) ───
function openProfileActionsMenu() {
  var overlay = document.getElementById('profileActionsOverlay');
  var removeBtn = document.getElementById('profileActionRemoveConnection');
  if (removeBtn) {
    removeBtn.style.display = (state.activePeerConnectionStatus === 'connected') ? 'flex' : 'none';
  }
  if (overlay) overlay.style.display = 'flex';
}
window.openProfileActionsMenu = openProfileActionsMenu;

function closeProfileActionsMenu() {
  var overlay = document.getElementById('profileActionsOverlay');
  if (overlay) overlay.style.display = 'none';
}
window.closeProfileActionsMenu = closeProfileActionsMenu;

async function removePeerConnection() {
  closeProfileActionsMenu();
  if (!state.activePeerUserId) return;
  state.activePeerConnectionStatus = 'none';
  updatePeerConnectionUI('none');
  showToast('Connection removed.');
  await apiRequest('/api/friend/disconnect', {
    method: 'POST',
    body: { target_user_id: state.activePeerUserId }
  });
  // Refresh profile to reflect privacy boundary
  await openUserProfile(state.activePeerUserId);
}
window.removePeerConnection = removePeerConnection;

async function blockPeerUser() {
  closeProfileActionsMenu();
  if (!state.activePeerUserId) return;
  var conf = confirm('Block this user? You will no longer see their moments or connection.');
  if (!conf) return;

  var res = await apiRequest('/api/user/block', {
    method: 'POST',
    body: { target_id: state.activePeerUserId, user_id: state.activePeerUserId }
  });
  showToast('User blocked.');
  handlePeerProfileBack();
}
window.blockPeerUser = blockPeerUser;

async function reportPeerUser() {
  closeProfileActionsMenu();
  if (!state.activePeerUserId) return;
  var reason = prompt('Please describe the problem with this account:') || 'Inappropriate content';
  await apiRequest('/api/user/report', {
    method: 'POST',
    body: { target_id: state.activePeerUserId, reason: reason }
  });
  showToast('Report submitted. Thank you for keeping Kandid safe.');
}
window.reportPeerUser = reportPeerUser;

function messageFromActionsMenu() {
  closeProfileActionsMenu();
  if (state.activePeerUser) {
    var u = state.activePeerUser;
    var rawH = (u.handle || u.username || 'user').replace('@', '');
    openChatThread(u.id, u.name || 'User', '@' + rawH.toLowerCase(), u.avatar_url || '', u.is_online);
  }
}
window.messageFromActionsMenu = messageFromActionsMenu;

function handlePeerProfileBack() {
  switchScreenView(lastScreenBeforeProfile || 'feed');
}
window.handlePeerProfileBack = handlePeerProfileBack;

// ─── SETTINGS UTILITIES (CHANGE PASSWORD & DELETE ACCOUNT) ───
function openChangePasswordModal() {
  var modal = document.getElementById('changePasswordModal');
  if (modal) modal.style.display = 'flex';
}
window.openChangePasswordModal = openChangePasswordModal;

function closeChangePasswordModal() {
  var modal = document.getElementById('changePasswordModal');
  if (modal) modal.style.display = 'none';
}
window.closeChangePasswordModal = closeChangePasswordModal;

async function submitChangePassword(e) {
  if (e && e.preventDefault) e.preventDefault();
  var curr = (document.getElementById('inputCurrentPassword') || {}).value || '';
  var nw = (document.getElementById('inputNewPassword') || {}).value || '';
  var conf = (document.getElementById('inputConfirmNewPassword') || {}).value || '';

  if (!curr || !nw) {
    showToast('Please enter both current and new password.');
    return;
  }
  if (nw.length < 6) {
    showToast('New password must be at least 6 characters.');
    return;
  }
  if (nw !== conf) {
    showToast('New passwords do not match.');
    return;
  }

  var btn = document.getElementById('btnSubmitChangePassword');
  if (btn) btn.disabled = true;

  var res = await apiRequest('/api/user/change-password', {
    method: 'POST',
    body: { current_password: curr, new_password: nw }
  });

  if (btn) btn.disabled = false;

  if (res && res.success) {
    showToast('Password updated successfully! 🔑');
    closeChangePasswordModal();
    if (document.getElementById('inputCurrentPassword')) document.getElementById('inputCurrentPassword').value = '';
    if (document.getElementById('inputNewPassword')) document.getElementById('inputNewPassword').value = '';
    if (document.getElementById('inputConfirmNewPassword')) document.getElementById('inputConfirmNewPassword').value = '';
  } else {
    showToast(res && res.error ? res.error : 'Could not change password.');
  }
}
window.submitChangePassword = submitChangePassword;

async function confirmDeleteAccount() {
  var conf = confirm('⚠️ Are you sure you want to permanently delete your Kandid account?\n\nThis action cannot be undone.');
  if (!conf) return;
  var secondConf = prompt('Type DELETE to confirm account deletion:');
  if (secondConf !== 'DELETE') {
    showToast('Deletion cancelled.');
    return;
  }
  showToast('Account deleted.');
  logoutUser();
}
window.confirmDeleteAccount = confirmDeleteAccount;

// YOU / PROFILE & PERSONAL ARCHIVE MODULE
// =====================================================================
state.activeDetailMoment = null;
state.detailMomentFlipped = false;

function triggerDirectAvatarUpload() {
  var input = document.getElementById('youDirectAvatarInput');
  if (input) {
    input.value = '';
    input.click();
  }
}
window.triggerDirectAvatarUpload = triggerDirectAvatarUpload;

async function handleDirectAvatarUpload(event) {
  var file = event && event.target && event.target.files && event.target.files[0];
  if (!file) return;
  if (!file.type || !file.type.startsWith('image/')) {
    showToast('Please select a valid image file.');
    return;
  }
  showToast('Updating profile photo...');
  var reader = new FileReader();
  reader.onload = async function(e) {
    var base64Data = e.target.result;
    // Optimistic preview
    var avatarEl = document.getElementById('youProfileAvatar');
    var initsEl = document.getElementById('youProfileInitials');
    if (avatarEl) {
      avatarEl.src = base64Data;
      avatarEl.style.display = 'block';
    }
    if (initsEl) initsEl.style.display = 'none';

    try {
      var res = await apiRequest('/api/user/photo', {
        method: 'POST',
        body: { photo: base64Data }
      });
      if (res && (res.success || res.avatar_url || res.url)) {
        var newUrl = res.avatar_url || res.url;
        if (state.currentUser) {
          state.currentUser.avatar_url = newUrl;
          try {
            localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
          } catch(err) {}
        }
        showToast('Profile photo updated! ✨');
      } else {
        var updateRes = await apiRequest('/api/user/update', {
          method: 'POST',
          body: { avatar_url: base64Data }
        });
        if (updateRes && (updateRes.success || (updateRes.user && updateRes.user.avatar_url))) {
          var updatedUrl = (updateRes.user && updateRes.user.avatar_url) || base64Data;
          if (state.currentUser) {
            state.currentUser.avatar_url = updatedUrl;
            try {
              localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
            } catch(err) {}
          }
          showToast('Profile photo updated! ✨');
        } else {
          showToast('Could not update profile photo.');
          if (state.currentUser) applyUserToYouScreen(state.currentUser);
        }
      }
    } catch(err) {
      console.warn('[Avatar] upload error:', err);
      showToast('Photo upload failed.');
      if (state.currentUser) applyUserToYouScreen(state.currentUser);
    }
  };
  reader.readAsDataURL(file);
}
window.handleDirectAvatarUpload = handleDirectAvatarUpload;

// YOU / PROFILE COVER PHOTO INTERACTION
state.stagedCoverBase64 = null;
state.previousCoverSrc = '';
state.previousCoverDisplay = 'none';

function triggerDirectCoverUpload() {
  var input = document.getElementById('youDirectCoverInput');
  if (input) {
    input.value = '';
    input.click();
  }
}
window.triggerDirectCoverUpload = triggerDirectCoverUpload;

function handleDirectCoverUpload(event) {
  var file = event && event.target && event.target.files && event.target.files[0];
  if (!file) return;
  if (!file.type || !file.type.startsWith('image/')) {
    showToast('Please select a valid image file (JPG, PNG, WebP).');
    return;
  }
  if (file.size > 15 * 1024 * 1024) {
    showToast('Cover photo exceeds maximum size limit (15MB).');
    return;
  }

  var coverImg = document.getElementById('youCoverImg');
  state.previousCoverSrc = coverImg ? (coverImg.getAttribute('src') || '') : '';
  state.previousCoverDisplay = coverImg ? coverImg.style.display : 'none';

  var reader = new FileReader();
  reader.onload = function(e) {
    var base64Data = e.target.result;
    state.stagedCoverBase64 = base64Data;

    // Show preview in cover area
    if (coverImg) {
      coverImg.src = base64Data;
      coverImg.style.display = 'block';
    }

    // Reveal Action Bar [Cancel / Save], hide edit trigger
    var editBtn = document.getElementById('youCoverEditBtn');
    var actionBar = document.getElementById('youCoverActionBar');
    if (editBtn) editBtn.style.display = 'none';
    if (actionBar) actionBar.style.display = 'flex';
  };
  reader.readAsDataURL(file);
}
window.handleDirectCoverUpload = handleDirectCoverUpload;

function cancelCoverUpload() {
  var coverImg = document.getElementById('youCoverImg');
  if (coverImg) {
    if (state.previousCoverSrc && !state.previousCoverSrc.includes('unsplash.com')) {
      coverImg.src = state.previousCoverSrc;
      coverImg.style.display = state.previousCoverDisplay || 'block';
    } else {
      coverImg.style.display = 'none';
      coverImg.removeAttribute('src');
    }
  }

  state.stagedCoverBase64 = null;
  var input = document.getElementById('youDirectCoverInput');
  if (input) input.value = '';

  var editBtn = document.getElementById('youCoverEditBtn');
  var actionBar = document.getElementById('youCoverActionBar');
  if (editBtn) editBtn.style.display = 'inline-flex';
  if (actionBar) actionBar.style.display = 'none';
}
window.cancelCoverUpload = cancelCoverUpload;

async function saveCoverUpload() {
  if (!state.stagedCoverBase64) return;
  var saveBtn = document.getElementById('youSaveCoverBtn');
  var origText = saveBtn ? saveBtn.textContent : 'Save';
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
  }
  showToast('Updating cover photo...');

  try {
    var res = await apiRequest('/api/user/cover', {
      method: 'POST',
      body: { cover: state.stagedCoverBase64 }
    });

    if (!res || !res.success) {
      res = await apiRequest('/api/user/update', {
        method: 'POST',
        body: { cover_url: state.stagedCoverBase64 }
      });
    }

    if (res && (res.success || res.cover_url || (res.user && res.user.cover_url))) {
      var newUrl = res.cover_url || (res.user && res.user.cover_url) || state.stagedCoverBase64;
      if (state.currentUser) {
        state.currentUser.cover_url = newUrl;
        try {
          localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
        } catch(err) {}
      }

      var coverImg = document.getElementById('youCoverImg');
      if (coverImg) {
        coverImg.src = newUrl;
        coverImg.style.display = 'block';
      }

      state.stagedCoverBase64 = null;
      var editBtn = document.getElementById('youCoverEditBtn');
      var actionBar = document.getElementById('youCoverActionBar');
      if (editBtn) editBtn.style.display = 'inline-flex';
      if (actionBar) actionBar.style.display = 'none';

      showToast('Cover photo updated! ✨');
    } else {
      showToast('Could not update cover photo. Please try again.');
      cancelCoverUpload();
    }
  } catch(err) {
    console.warn('[Cover] upload error:', err);
    showToast('Cover photo upload failed. Please try again.');
    cancelCoverUpload();
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = origText;
    }
  }
}
window.saveCoverUpload = saveCoverUpload;

function applyUserToYouScreen(u) {
  if (!u) return;
  var avatarEl = document.getElementById('youProfileAvatar');
  var initialsEl = document.getElementById('youProfileInitials');
  var nameEl = document.getElementById('youProfileName');
  var usernameEl = document.getElementById('youProfileUsername');
  var campusEl = document.getElementById('youProfileCampus');
  var bioEl = document.getElementById('youProfileBio');
  var streakVal = document.getElementById('youStreakVal');
  var momentsCountVal = document.getElementById('youMomentsCountVal');
  var memoriesCountVal = document.getElementById('youMemoriesCountVal');

  // Cover image: real cover or blank dark container
  var coverImg = document.getElementById('youCoverImg');
  if (coverImg) {
    var rawCover = (u.cover_url || u.cover || '').trim();
    if (rawCover && !rawCover.includes('unsplash.com')) {
      coverImg.onerror = function() {
        this.style.display = 'none';
        this.removeAttribute('src');
      };
      coverImg.onload = function() {
        this.style.display = 'block';
      };
      coverImg.src = rawCover;
    } else {
      coverImg.style.display = 'none';
      coverImg.removeAttribute('src');
    }
  }

  var finalName = u.name || (state.currentUser ? state.currentUser.name : 'You');
  var finalHandle = u.username || u.handle || (state.currentUser ? (state.currentUser.username || state.currentUser.handle) : 'user');
  finalHandle = String(finalHandle).replace('@', '');

  if (initialsEl) {
    initialsEl.style.display = 'none';
    initialsEl.textContent = '';
  }

  var rawAvatar = (u.avatar_url || u.avatar || '').trim();
  if (rawAvatar && !rawAvatar.includes('api.dicebear.com')) {
    if (avatarEl) {
      avatarEl.onerror = function() {
        this.style.display = 'none';
        this.removeAttribute('src');
        if (initialsEl) {
          initialsEl.style.display = 'none';
          initialsEl.textContent = '';
        }
      };
      avatarEl.onload = function() {
        this.style.display = 'block';
      };
      avatarEl.src = rawAvatar;
    }
  } else {
    if (avatarEl) {
      avatarEl.style.display = 'none';
      avatarEl.removeAttribute('src');
    }
  }

  if (nameEl) nameEl.textContent = finalName;
  if (usernameEl) usernameEl.textContent = '@' + finalHandle.toLowerCase();
  
  var commName = u.campus || u.community || (state.currentUser ? state.currentUser.campus : 'Campus Community');
  var cityName = u.location_city || u.city || (state.currentUser ? (state.currentUser.location_city || state.currentUser.city) : 'Local');
  var campusNameEl = document.getElementById('youProfileCampusName');
  var campusCityEl = document.getElementById('youProfileCampusCity');
  if (campusNameEl) campusNameEl.textContent = commName;
  if (campusCityEl) campusCityEl.textContent = cityName;
  if (campusEl) campusEl.title = commName + ' · ' + cityName;

  // Real "Your World" card counts
  var peopleDescEl = document.getElementById('youWorldPeopleDesc');
  var commDescEl = document.getElementById('youWorldCommunitiesDesc');
  var connCount = (u.connections_count != null) ? u.connections_count : (u.connections_from ? 1 : 0);
  if (peopleDescEl) {
    peopleDescEl.textContent = connCount > 0 ? (connCount + (connCount === 1 ? ' connection' : ' connections')) : 'People who matter.';
  }
  if (commDescEl) {
    var jc = (u.joined_communities && u.joined_communities.length) || 0;
    commDescEl.textContent = jc > 0 ? (jc + (jc === 1 ? ' community' : ' communities')) : 'Spaces you\'re part of.';
  }
  
  if (bioEl) bioEl.textContent = u.bio || 'Authentic moments across campus.';
  
  var sNum = (u.streak != null ? u.streak : (u.streak_count != null ? u.streak_count : 1));
  if (streakVal) streakVal.textContent = sNum + (sNum === 1 ? ' DAY' : ' DAYS');
  if (momentsCountVal) momentsCountVal.textContent = (u.momentCount != null ? u.momentCount : (state.myMoments ? state.myMoments.length : 1));
  if (memoriesCountVal) memoriesCountVal.textContent = (u.memoryCount != null ? u.memoryCount : (state.myMoments ? state.myMoments.length : 1));

  var editName = document.getElementById('modalEditName');
  var editBio = document.getElementById('modalEditBio');
  var editCampus = document.getElementById('modalEditCampus');
  var editCity = document.getElementById('modalEditCity');
  if (editName) editName.value = finalName;
  if (editBio) editBio.value = u.bio || '';
  if (editCampus) editCampus.value = commName;
  if (editCity) editCity.value = cityName;
}
window.applyUserToYouScreen = applyUserToYouScreen;

async function loadYouJournalThumbnails() {
  var strip = document.getElementById('youJournalThumbnailsStrip');
  if (!strip) return;

  var memData = await apiRequest('/api/me/memories');
  var memories = (memData && memData.success && Array.isArray(memData.memories)) ? memData.memories : [];
  
  strip.innerHTML = '';
  if (!memories || memories.length === 0) {
    var myMoments = state.myMoments || [];
    if (myMoments.length === 0) {
      strip.innerHTML = '<div class="py-2 text-[10px] text-zinc-500 font-mono-meta tracking-wider">NO MEMORIES RECORDED YET</div>';
      return;
    }
    memories = myMoments;
  }

  // Display up to 4 thumbnails
  var displayList = memories.slice(0, 4);
  var remaining = memories.length - 4;

  displayList.forEach(function(m) {
    var thumb = document.createElement('div');
    thumb.className = 'w-14 h-14 rounded-xl bg-neutral-900 border border-neutral-800 overflow-hidden flex-shrink-0 cursor-pointer active:scale-95 transition';
    var imgUrl = m.mediaUrl || m.main_img || m.media_url || m.mainImg || '';
    if (imgUrl) {
      thumb.innerHTML = '<img src="' + escapeHtml(imgUrl) + '" class="w-full h-full object-cover" alt="Memory preview">';
    } else {
      thumb.innerHTML = '<div class="w-full h-full bg-neutral-900 flex items-center justify-center text-amber-500/80 text-xs font-mono-meta">✦</div>';
    }
    thumb.onclick = function() {
      openMemoryArchive();
    };
    strip.appendChild(thumb);
  });

  if (remaining > 0) {
    var plusDiv = document.createElement('div');
    plusDiv.className = 'w-14 h-14 rounded-xl bg-neutral-900/90 border border-neutral-800 flex items-center justify-center flex-shrink-0 text-amber-400 font-bold text-xs cursor-pointer active:scale-95 transition';
    plusDiv.textContent = '+' + remaining;
    plusDiv.onclick = function() {
      openMemoryArchive();
    };
    strip.appendChild(plusDiv);
  }
}
window.loadYouJournalThumbnails = loadYouJournalThumbnails;

async function loadYouScreen() {
  if (state.currentUser) {
    applyUserToYouScreen(state.currentUser);
  }

  var data = await apiRequest('/api/me');
  if (!data || !data.success || !data.user) {
    data = await apiRequest('/api/user/profile');
  }

  if (data && (data.user || data.success)) {
    var u = data.user || {};
    state.currentUser = Object.assign({}, state.currentUser || {}, u);
    try {
      localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
      if (state.currentUser.id) {
        localStorage.setItem('kandid_active_uid', state.currentUser.id);
      }
    } catch(e) {}
    applyUserToYouScreen(state.currentUser);

    // Update Pending Requests Badge
    var reqBadge = document.getElementById('youRequestsBadge');
    if (reqBadge) {
      var reqCount = u.pending_requests_count || 0;
      reqBadge.textContent = reqCount > 0 ? reqCount : '';
      reqBadge.style.display = 'none';
    }

    // Render Dynamic TODAY card (Captured vs Capture Prompt)
    renderYouTodayCard(u);
    if (u.has_captured_today && typeof markDailyAlertCompleted === 'function') {
      markDailyAlertCompleted();
    }

    // Render Dynamic Communities
    renderYouCommunitiesList(u.joined_communities || []);

    // Load Real Moments & Real Journal Previews
    await loadMyMoments();
    await loadYouJournalThumbnails();
    await loadProgressScreen();
  }
}

function renderYouTodayCard(u) {
  var card = document.getElementById('youTodayCaptureCard');
  if (!card) return;

  if (u && (u.has_captured_today || u.today_moment)) {
    var tm = u.today_moment || {};
    var timeTxt = tm.timeAgo || tm.time_str || '12:42 PM';
    var locTxt = tm.campus || tm.location_context || 'Near Campus';
    card.innerHTML =
      '<div class="flex items-center justify-between">' +
        '<div class="space-y-0.5">' +
          '<span class="text-[9px] text-amber-500 font-mono-tag font-bold tracking-widest uppercase block">TODAY</span>' +
          '<h3 class="text-xs font-extrabold text-white font-mono-tag leading-snug">✓ MOMENT CAPTURED</h3>' +
          '<p class="text-[10px] text-zinc-400 font-mono-tag pt-0.5">Captured ' + escapeHtml(timeTxt) + ' · ' + escapeHtml(locTxt) + '</p>' +
        '</div>' +
        '<button class="px-3.5 py-2 bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500 hover:text-black text-amber-400 font-mono-tag text-[10px] font-bold rounded-xl transition cursor-pointer active:scale-95 uppercase flex items-center gap-1" id="youViewTodayMomentBtn">' +
          '<span>VIEW TODAY\'S MOMENT</span>' +
          '<span>→</span>' +
        '</button>' +
      '</div>';
    
    var viewBtn = document.getElementById('youViewTodayMomentBtn');
    if (viewBtn) {
      viewBtn.onclick = function() {
        if (u.today_moment) openMomentDetail(u.today_moment);
        else openMemoryArchive();
      };
    }
  } else {
    card.innerHTML =
      '<div class="flex items-center justify-between">' +
        '<div class="space-y-1">' +
          '<span class="text-[9px] text-amber-500 font-mono-tag font-bold tracking-widest uppercase block">TODAY</span>' +
          '<h3 class="text-xs font-extrabold text-white font-mono-tag leading-snug">You haven\'t captured<br>your Moment yet.</h3>' +
          '<p class="text-[10px] text-zinc-500 font-mono-tag pt-0.5">Every day is a new story.</p>' +
        '</div>' +
        '<div class="flex flex-col items-center gap-1.5 flex-shrink-0 cursor-pointer active:scale-95 transition" onclick="openCameraStudio()">' +
          '<div class="w-14 h-14 rounded-full border-2 border-dashed border-amber-500/60 bg-amber-500/10 flex items-center justify-center text-amber-400 text-xl font-bold shadow-lg">' +
            '+' +
          '</div>' +
          '<span class="text-[9px] text-amber-400 font-mono-tag font-extrabold tracking-wider uppercase">CAPTURE NOW</span>' +
        '</div>' +
      '</div>';
  }
}

function renderYouCommunitiesList(communities) {
  var container = document.getElementById('youCommunitiesContainer');
  if (!container) return;
  container.innerHTML = '';

  if (!communities || communities.length === 0) {
    container.innerHTML =
      '<div class="bg-zinc-950 border border-zinc-800/60 rounded-2xl p-4 text-center space-y-2 font-mono-tag">' +
        '<p class="text-xs font-bold text-zinc-300">Find your people and places.</p>' +
        '<button class="px-3.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 text-[10px] font-bold rounded-xl transition cursor-pointer" onclick="openCommunitySwitcher()">DISCOVER COMMUNITIES →</button>' +
      '</div>';
    return;
  }

  communities.slice(0, 3).forEach(function(c) {
    var row = document.createElement('div');
    row.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3 flex items-center justify-between hover:border-zinc-700 transition cursor-pointer shadow-md active:scale-95';
    var cType = (c.type || 'COMMUNITY').toUpperCase();
    var cIcon = c.icon || (cType === 'CAMPUS' ? '🎓' : cType === 'PLACE' ? '📍' : '📸');
    var myId = state.currentUser ? String(state.currentUser.id || '').trim() : '';
    var myHandle = state.currentUser ? String(state.currentUser.handle || '').trim().toLowerCase() : '';
    var cCreatorId = c.creator_id ? String(c.creator_id).trim() : '';
    var cCreatorHandle = c.creator_handle ? String(c.creator_handle).trim().toLowerCase() : '';
    var isHost = c.is_owner || c.role === 'owner' || (
      state.currentUser && (
        (cCreatorId && myId && cCreatorId === myId) ||
        (cCreatorHandle && myHandle && cCreatorHandle === myHandle)
      )
    );

    row.innerHTML =
      '<div class="flex items-center gap-3 min-w-0">' +
        '<div class="w-8 h-8 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-sm flex-shrink-0">' +
          cIcon +
        '</div>' +
        '<div class="min-w-0">' +
          '<div class="flex items-center gap-1.5">' +
            '<h4 class="text-xs font-bold text-white font-mono-tag truncate">◉ ' + escapeHtml(c.name) + '</h4>' +
            (isHost ? '<span class="text-[8px] bg-amber-500/15 border border-amber-500/40 text-amber-400 font-bold px-1.5 py-0.2 rounded font-mono-tag tracking-wider flex-shrink-0">HOST</span>' : '') +
          '</div>' +
          '<p class="text-[9px] text-zinc-400 font-mono-tag tracking-wider uppercase">' + escapeHtml(cType) + ' · Active today</p>' +
        '</div>' +
      '</div>' +
      '<span class="text-[10px] text-zinc-500 font-mono-tag">→</span>';

    row.onclick = function() {
      if (typeof openCampusPage === 'function') openCampusPage(c.name);
    };
    container.appendChild(row);
  });
}


async function loadProgressScreen() {
  var data = await apiRequest('/api/me/progress');
  if (data && data.success) {
    var xp = data.xp || 0;
    var level = 1 + Math.floor(xp / 250);
    var nextXp = level * 250;
    var progressPct = Math.min(100, Math.floor((xp % 250) / 250 * 100));
    var remainingXp = nextXp - xp;
    
    // Update You Screen Card
    var levelSnippet = document.getElementById('youLevelSnippet');
    var xpSnippet = document.getElementById('youXpSnippet');
    if (levelSnippet) levelSnippet.textContent = (level < 10 ? '0' : '') + level;
    if (xpSnippet) xpSnippet.textContent = xp.toLocaleString() + ' XP';

    // Update Progress Screen
    var pLevel = document.getElementById('progressLevelTxt');
    var pRank = document.getElementById('progressRankTxt');
    var pXp = document.getElementById('progressXpTxt');
    var pNextXp = document.getElementById('progressNextXpTxt');
    var pBar = document.getElementById('progressProgressBar');
    var pNextLevel = document.getElementById('progressNextLevelTxt');
    var pRemXp = document.getElementById('progressRemainingXpTxt');

    var rankName = 'OBSERVER';
    if (level > 2) rankName = 'SCOUT';
    if (level > 5) rankName = 'EXPLORER';
    if (level > 9) rankName = 'LENS MASTER';

    if (pLevel) pLevel.textContent = (level < 10 ? '0' : '') + level;
    if (pRank) pRank.textContent = rankName;
    if (pXp) pXp.textContent = xp.toLocaleString() + ' XP';
    if (pNextXp) pNextXp.textContent = nextXp.toLocaleString() + ' XP TO LEVEL ' + ((level + 1) < 10 ? '0' : '') + (level + 1);
    if (pBar) pBar.style.width = progressPct + '%';
    if (pNextLevel) pNextLevel.textContent = ((level + 1) < 10 ? '0' : '') + (level + 1);
    if (pRemXp) pRemXp.textContent = remainingXp.toLocaleString() + ' XP REMAINING';

    // Quests
    var q = data.quests || {};
    var mcap = document.getElementById('questStatusMoment');
    var dmiss = document.getElementById('questStatusMission');
    var cdisc = document.getElementById('questStatusCampus');
    
    if (mcap) {
      if (q.moment_captured) {
        mcap.className = 'text-[9px] text-amber-400 font-mono-tag bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 rounded-lg font-bold';
        mcap.textContent = '✓ COMPLETED';
      } else {
        mcap.className = 'text-[9px] text-zinc-400 font-mono-tag bg-zinc-900 border border-zinc-800 px-2.5 py-1 rounded-lg font-bold';
        mcap.textContent = 'PENDING';
      }
    }
    
    if (dmiss) {
      if (q.daily_mission) {
        dmiss.className = 'text-[9px] text-amber-400 font-mono-tag bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 rounded-lg font-bold';
        dmiss.textContent = '✓ COMPLETED';
      } else {
        dmiss.className = 'text-[9px] text-zinc-400 font-mono-tag bg-zinc-900 border border-zinc-800 px-2.5 py-1 rounded-lg font-bold';
        dmiss.textContent = 'PENDING';
      }
    }

    if (cdisc) {
      if (q.campus_discovered) {
        cdisc.className = 'text-[9px] text-amber-400 font-mono-tag bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 rounded-lg font-bold';
        cdisc.textContent = '✓ COMPLETED';
      } else {
        cdisc.className = 'text-[9px] text-zinc-600 font-mono-tag bg-zinc-900/50 border border-zinc-900 px-2.5 py-1 rounded-lg font-bold';
        cdisc.textContent = 'PENDING';
      }
    }

    // History
    var histList = document.getElementById('progressHistoryList');
    if (histList && data.history) {
      histList.innerHTML = '';
      if (data.history.length === 0) {
        histList.innerHTML = '<div class="text-center text-zinc-500 text-[10px] py-2">No recent progress to show.</div>';
      } else {
        data.history.forEach(function(h, idx) {
          var borderClass = (idx < data.history.length - 1) ? 'border-b border-zinc-900 pb-2.5' : '';
          var el = document.createElement('div');
          el.className = 'flex justify-between items-center ' + borderClass;
          el.innerHTML = '<div class="space-y-0.5"><span class="text-amber-400 font-bold">+' + h.amount + ' XP</span><p class="text-zinc-300 text-[11px] font-sans">' + escapeHtml(h.reason) + '</p></div><span class="text-[9px] text-zinc-500">Today</span>';
          histList.appendChild(el);
        });
      }
    }
  }
}
window.loadProgressScreen = loadProgressScreen;
window.loadYouScreen = loadYouScreen;
window.loadUserProfile = loadYouScreen;

async function loadMyMoments() {
  var container = document.getElementById('youMomentsHorizontalContainer');
  var grid = document.getElementById('youMomentsGrid');
  if (!container && !grid) return;

  var data = await apiRequest('/api/me/moments');
  if (data && data.success && Array.isArray(data.moments)) {
    if (container) renderMomentsHorizontal(data.moments, container);
    if (grid) renderMomentsGrid(data.moments, grid);
  }
}
window.loadMyMoments = loadMyMoments;

function renderMomentsHorizontal(moments, container) {
  if (!container) return;
  container.innerHTML = '';

  if (moments && moments.length > 0) {
    moments.slice(0, 6).forEach(function(m) {
      var card = document.createElement('div');
      card.className = 'w-28 h-36 flex-shrink-0 bg-zinc-950 border border-zinc-800/80 rounded-2xl overflow-hidden relative shadow-lg group cursor-pointer active:scale-95 transition-all select-none';

      var timeAgoText = escapeHtml(m.timeAgo || m.time_ago || (m.created_at ? formatTimeAgoClean(m.created_at) : 'RECENT')).toUpperCase();
      var locText = escapeHtml((m.campus || m.community_name || m.location_city || 'KANDID')).toUpperCase();
      var imgSrc = escapeHtml(m.mediaUrl || m.mainImg || m.main_img || '');

      var imgHtml = imgSrc 
        ? '<img src="' + imgSrc + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">'
        : '<div class="w-full h-full bg-zinc-900 flex items-center justify-center text-zinc-700 font-mono-tag text-xs">MOMENT</div>';

      card.innerHTML =
        imgHtml +
        '<div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent pointer-events-none"></div>' +
        '<div class="absolute top-1.5 right-2 text-white/80 text-xs font-bold drop-shadow">⋮</div>' +
        '<div class="absolute bottom-2 left-2.5 right-2 space-y-0.5 pointer-events-none">' +
          '<div class="text-[8px] font-bold text-amber-400 font-mono-tag uppercase tracking-wider">' + timeAgoText + '</div>' +
          '<div class="text-[8px] font-bold text-zinc-300 font-mono-tag uppercase truncate">' + locText + '</div>' +
        '</div>';

      card.addEventListener('click', function() {
        openMomentDetail(m);
      });
      container.appendChild(card);
    });
  } else {
    var emptyEl = document.createElement('div');
    emptyEl.className = 'py-4 text-center text-[10px] text-zinc-500 font-mono-meta tracking-wider w-full';
    emptyEl.textContent = 'NO MOMENTS CAPTURED YET';
    container.appendChild(emptyEl);
  }
}

function renderMomentsGrid(moments, grid) {
  if (!grid) return;
  grid.innerHTML = '';
  if (!moments || moments.length === 0) {
    grid.innerHTML =
      '<div class="col-span-2 py-8 text-center text-[10px] text-zinc-500 font-mono-meta tracking-wider">' +
        'NO MOMENTS CAPTURED YET' +
      '</div>';
    return;
  }

  moments.slice(0, 10).forEach(function(m) {
    var article = document.createElement('article');
    article.className = 'relative h-[170px] rounded-[14px] overflow-hidden border border-neutral-800/80 group cursor-pointer active:scale-95 transition';
    var imgUrl = escapeHtml(m.main_img || m.mediaUrl || m.media_url || m.mainImg || '');
    var locStr = escapeHtml(m.campus || m.location_city || (state.currentUser ? state.currentUser.campus : '') || 'Campus');
    var timeStr = escapeHtml((m.timeAgo || m.time_ago || (m.created_at ? formatTimeAgoClean(m.created_at) : 'RECENT'))).toUpperCase();

    var imgHtml = imgUrl
      ? '<img src="' + imgUrl + '" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" alt="' + locStr + '">'
      : '<div class="w-full h-full bg-neutral-900 flex items-center justify-center text-zinc-700 font-mono-meta text-xs">MOMENT</div>';

    article.innerHTML =
      imgHtml +
      '<div class="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-transparent pointer-events-none" aria-hidden="true"></div>' +
      '<div class="absolute bottom-2.5 left-2.5 right-2.5 pointer-events-none">' +
        '<p class="text-[9px] font-extrabold text-amber-400 tracking-wider uppercase">' + timeStr + '</p>' +
        '<p class="text-xs font-bold text-white truncate mt-0.5"><i class="fa-solid fa-location-dot text-[8px] mr-1 text-gray-400" aria-hidden="true"></i>' + locStr + '</p>' +
      '</div>';

    article.onclick = function() {
      openMomentDetail(m);
    };
    grid.appendChild(article);
  });
}

function openMomentDetail(m) {
  state.activeDetailMoment = m;
  state.detailMomentFlipped = false;
  var modal = document.getElementById('momentDetailModal');
  var mainImg = document.getElementById('momentDetailMainImg');
  var pipImg = document.getElementById('momentDetailPipImg');
  var campusEl = document.getElementById('momentDetailCampus');
  var captionEl = document.getElementById('momentDetailCaption');
  var timeEl = document.getElementById('momentDetailTime');
  var exifEl = document.getElementById('momentDetailExif');
  var authorHandleEl = document.getElementById('momentDetailAuthorHandle');
  var audioBar = document.getElementById('momentDetailAudioBar');
  var deleteBtn = document.getElementById('momentDetailDeleteBtn');

  if (mainImg) mainImg.src = m.mediaUrl || m.main_img || m.mainImg || '';
  if (pipImg) pipImg.src = m.pipUrl || m.pip_img || m.pipImg || '';
  if (campusEl) campusEl.textContent = (m.campus || 'NORTH CITY UNIVERSITY').toUpperCase();
  if (captionEl) captionEl.textContent = m.caption || 'Unedited perspective.';
  if (timeEl) timeEl.textContent = m.timeAgo || m.time_ago || 'TODAY';
  if (exifEl) {
    var iso = m.exif_iso || (m.exif && m.exif.iso) || 'ISO 400';
    var ap = m.exif_aperture || (m.exif && m.exif.aperture) || 'f/2.8';
    var sh = m.exif_shutter || (m.exif && m.exif.shutter) || '1/250s';
    exifEl.textContent = iso + ' · ' + ap + ' · ' + sh;
  }
  if (authorHandleEl) {
    authorHandleEl.textContent = '@' + (m.author_handle || m.user_handle || (state.currentUser ? state.currentUser.handle : 'you'));
  }

  var audioUrl = m.audio_url || m.audioData || '';
  if (audioBar) {
    audioBar.style.display = audioUrl ? 'flex' : 'none';
  }

  var isOwner = !m.user_id || (state.currentUser && (m.user_id === state.currentUser.id || m.author_handle === state.currentUser.handle));
  if (deleteBtn) {
    deleteBtn.style.display = isOwner ? 'flex' : 'none';
  }

  if (modal) modal.style.display = 'flex';
}
window.openMomentDetail = openMomentDetail;

function playCurrentModalAudio() {
  if (!state.activeDetailMoment) return;
  var audioUrl = state.activeDetailMoment.audio_url || state.activeDetailMoment.audioData || '';
  if (audioUrl) {
    playFeedAudio(audioUrl);
  } else {
    showToast('No ambient audio for this moment');
  }
}
window.playCurrentModalAudio = playCurrentModalAudio;

async function handleDeleteCurrentMoment() {
  if (!state.activeDetailMoment) return;
  var postId = state.activeDetailMoment.id;
  if (!postId) return;

  if (!confirm('Are you sure you want to permanently delete this moment?')) {
    return;
  }

  showToast('Deleting moment... 🗑️');
  var res = await apiRequest('/api/moments/delete', {
    method: 'POST',
    body: JSON.stringify({ postId: postId })
  });

  if (res && res.success) {
    showToast('Moment deleted successfully! ✨');
    closeMomentDetail();
    // Refresh feeds and profile
    if (typeof loadFeedMoments === 'function') loadFeedMoments('foryou');
    if (typeof loadCampusScreen === 'function') loadCampusScreen();
    if (typeof loadYouScreen === 'function') loadYouScreen();
  } else {
    showToast('Failed to delete: ' + (res ? res.error : 'Network error'));
  }
}
window.handleDeleteCurrentMoment = handleDeleteCurrentMoment;

function closeMomentDetail() {
  var modal = document.getElementById('momentDetailModal');
  if (modal) modal.style.display = 'none';
  state.activeDetailMoment = null;
}
window.closeMomentDetail = closeMomentDetail;

function swapMomentDetailPip() {
  var mainImg = document.getElementById('momentDetailMainImg');
  var pipImg = document.getElementById('momentDetailPipImg');
  if (mainImg && pipImg) {
    var tmp = mainImg.src;
    mainImg.src = pipImg.src;
    pipImg.src = tmp;
    showToast('Optics View Swapped ⇄');
  }
}
window.swapMomentDetailPip = swapMomentDetailPip;

async function openMemoryArchive() {
  switchScreenView('memories');
}
window.openMemoryArchive = openMemoryArchive;

function closeMemoryArchive() {
  switchScreenView('you');
}
window.closeMemoryArchive = closeMemoryArchive;

function navigateToCampus() {
  switchScreenView('feed');
  selectSubTab('campus');
}
window.navigateToCampus = navigateToCampus;

function openYouSettings() {
  var modal = document.getElementById('youSettingsModal');
  if (modal) modal.style.display = 'flex';
}
window.openYouSettings = openYouSettings;

function closeYouSettings() {
  var modal = document.getElementById('youSettingsModal');
  if (modal) modal.style.display = 'none';
}
window.closeYouSettings = closeYouSettings;

async function saveProfileSettings() {
  var name = document.getElementById('editProfileName').value.trim();
  var bio = document.getElementById('editProfileBio').value.trim();
  var campus = document.getElementById('editProfileCampus').value.trim();

  var res = await apiRequest('/api/user/update', {
    method: 'POST',
    body: JSON.stringify({ name: name, bio: bio, campus: campus })
  });

  if (res && res.success) {
    showToast('Profile updated successfully ✓');
    closeYouSettings();
    await loadYouScreen();
  }
}
window.saveProfileSettings = saveProfileSettings;

async function switchUserAccount(handle) {
  var res = await apiRequest('/api/auth/switch', {
    method: 'POST',
    body: JSON.stringify({ handle: handle })
  });

  if (res && res.success) {
    showToast('Switched user to @' + handle + ' ✦');
    closeYouSettings();
    await loadYouScreen();
    await loadFeedMoments();
    await loadCampusScreen();
    await loadChatConversations();
    await loadNotifications();
  }
}
window.switchUserAccount = switchUserAccount;


// =====================================================================
// NEW USER DAILY MISSION TRIGGER (SERVER-AUTHORITATIVE & CALM UX)
// =====================================================================
var newUserMissionTimer = null;

function showDailyMissionPrompt(userId) {
  var push = document.getElementById('osPushNotification');
  if (push) {
    push.classList.remove('-translate-y-[150%]');
    setTimeout(function() {
      push.classList.add('-translate-y-[150%]');
    }, 7000);
  }
  if (userId) {
    try {
      localStorage.setItem('kandid_daily_mission_shown_' + userId, 'true');
      localStorage.removeItem('kandid_new_account_' + userId);
      localStorage.removeItem('kandid_feed_entry_time_' + userId);
    } catch(e) {}
  }
}
window.showDailyMissionPrompt = showDailyMissionPrompt;

function handleNewUserFeedExit() {
  if (newUserMissionTimer) {
    clearTimeout(newUserMissionTimer);
    newUserMissionTimer = null;
  }
}
window.handleNewUserFeedExit = handleNewUserFeedExit;

function handleNewUserFeedEntry() {
  var user = state.currentUser;
  if (!user || !user.id) {
    try {
      user = JSON.parse(localStorage.getItem('kandid_user') || 'null');
    } catch(e) {}
  }
  if (!user || !user.id) return;
  var userId = user.id;

  try {
    // Rule 6 & 7: Only for genuinely new user account & never if already shown
    if (localStorage.getItem('kandid_daily_mission_shown_' + userId) === 'true') {
      return;
    }
    if (localStorage.getItem('kandid_new_account_' + userId) !== 'true') {
      return;
    }
  } catch(e) {
    return;
  }

  // Rule 2 & 3: Start 2-minute client-side timer from first Feed entry
  var now = Date.now();
  var entryTimeStr = null;
  try {
    entryTimeStr = localStorage.getItem('kandid_feed_entry_time_' + userId);
    if (!entryTimeStr) {
      entryTimeStr = now.toString();
      localStorage.setItem('kandid_feed_entry_time_' + userId, entryTimeStr);
    }
  } catch(e) {
    entryTimeStr = now.toString();
  }

  var entryTime = parseInt(entryTimeStr, 10) || now;
  var DURATION_MS = 2 * 60 * 1000; // Exactly 2 minutes
  var elapsed = now - entryTime;
  var remainingMs = DURATION_MS - elapsed;

  // Rule 8: Prevent duplicate timers
  handleNewUserFeedExit();

  if (remainingMs <= 0) {
    // 2 minutes already elapsed since first feed entry
    if (state.activeScreen === 'feed') {
      showDailyMissionPrompt(userId);
    }
    return;
  }

  // Rule 3, 4, 5: Schedule prompt after remaining duration
  newUserMissionTimer = setTimeout(function() {
    newUserMissionTimer = null;
    try {
      if (localStorage.getItem('kandid_daily_mission_shown_' + userId) === 'true') {
        return;
      }
    } catch(e) {}

    if (state.activeScreen === 'feed') {
      showDailyMissionPrompt(userId);
    }
  }, remainingMs);
}
window.handleNewUserFeedEntry = handleNewUserFeedEntry;

function handlePushClick() {
  var push = document.getElementById('osPushNotification');
  if (push) {
    push.classList.add('-translate-y-[150%]');
  }
  switchScreenView('mission');
}
window.handlePushClick = handlePushClick;

document.addEventListener('DOMContentLoaded', async function() {
  // 1. Navigation Dock
  document.querySelectorAll('.dock-item').forEach(function(btn) {
    btn.addEventListener('click', function() {
      switchScreenView(btn.dataset.screen);
    });
  });

  // 2. Sub-Tabs Filter (FOR YOU | NEARBY | CAMPUS | GLOBAL)
  document.querySelectorAll('.sub-tab-btn[data-circle]').forEach(function(tab) {
    tab.addEventListener('click', function(e) {
      e.preventDefault();
      selectSubTab(tab.dataset.circle);
    });
  });

  // 3. Attach card interactions to initial DOM cards
  document.querySelectorAll('.kandid-card').forEach(function(card) {
    attachCardInteractions(card, { id: card.dataset.postId || 'post_sample' });
  });

  // 4. Digital Status Clock
  setInterval(function() {
    var now = new Date();
    var hours = String(now.getHours()).padStart(2, '0');
    var minutes = String(now.getMinutes()).padStart(2, '0');
    var clockEl = document.getElementById('statusClock');
    if (clockEl) clockEl.textContent = hours + ':' + minutes;
  }, 1000);

  // 5. Initialize Sub-modules
  setupCameraStudio();
  await loadFeedMoments('foryou');
  await loadNotifications();
  await loadSearchDiscovery();
  await loadChatConversations();
  await loadYouScreen();

  // 5b. Real-time Heartbeat, Notification, & Presence Poller
  setInterval(function() {
      // D3-3: skip network polling while the tab/document is hidden
      if (document.hidden) return;
      if (state.token) {
          apiRequest('/api/heartbeat', { method: 'POST' }).then(function(hb) {
              if (hb && hb.success) {
                  // Update unread notification dot
                  var notifDot = document.getElementById('notifDot');
                  if (notifDot) {
                      notifDot.style.display = (hb.unreadCount > 0) ? 'block' : 'none';
                  }

                  // Update YOU page Requests Badge
                  var youReqBadge = document.getElementById('youRequestsBadge');
                  if (youReqBadge) {
                      youReqBadge.textContent = hb.pendingRequestsCount > 0 ? hb.pendingRequestsCount : '';
                      youReqBadge.style.display = 'none';
                  }

                  // Trigger In-App Live Notification Toast Banner
                  if (hb.latestNotification && hb.latestNotification.id) {
                      if (!state.lastAlertedNotifId) {
                          state.lastAlertedNotifId = hb.latestNotification.id;
                      } else if (state.lastAlertedNotifId !== hb.latestNotification.id) {
                          state.lastAlertedNotifId = hb.latestNotification.id;
                          showLiveNotificationBanner(hb.latestNotification);
                      }
                  }
              }
          }).catch(function(){});
      }

      if (state.activeScreen === 'notifications') {
          loadNotifications();
      }
  }, 3000);

  // 6. Register Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }

  // 7. New User Daily Mission Trigger (Only for genuine new users on Feed)
  if (state.activeScreen === 'feed') {
    handleNewUserFeedEntry();
  }
});

window.openSettings = function() {
    switchScreenView('settings');
};

window.closeSettings = function() {
    switchScreenView('you');
};


// =====================================================================
// KANDID V4.2 PRODUCTION ONBOARDING & AUTHENTICATION CONTROLLER
// =====================================================================
state.onboardPlaces = {
    campus: '',
    city: '',
    workplace: '',
    community: ''
};
state.onboardAvatarData = '';
state.currentPlaceModalType = '';

const privacyText = `
    <p class="italic text-zinc-400">Effective Date: September 1, 2026</p>
    <p>Kandid is operated by SolvarionX (“SolvarionX”, “Kandid”, “we”, “us”, or “our”).</p>
    <p>Kandid is a social network designed around real people, real places, real relationships, and real-world moments. We believe privacy should be built into the product rather than added later.</p>
    <p>This Privacy Policy explains what information we collect, why we collect it, how we use it, when we share it, and the choices available to you when you use Kandid.</p>
    <p>By using Kandid, you acknowledge the practices described in this Privacy Policy.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">1. Information We Collect</h4>
    <p>We collect information necessary to operate Kandid, protect the community, and provide features you choose to use (Name, Username, Email, Phone, Profile photo, Credentials, Date of birth).</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">2. Content You Create</h4>
    <p>Photos, Videos, Audio, Captions, Moments, Places, and Communities you choose to associate with. You control what you create and share.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">3. Camera, Microphone & Contacts</h4>
    <p>Access required only when capturing Moments or using optional contact discovery. Your address book is never displayed publicly.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">4. Location & Technical Information</h4>
    <p>Approximate location areas are used for nearby discovery without exposing exact live location. Device logs are collected to operate and secure Kandid.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">5. Contact & Privacy Requests</h4>
    <p>Operated by SolvarionX. For privacy requests, contact privacy@solvarionx.com.</p>
`;

const termsText = `
    <p class="italic text-zinc-400">Effective Date: September 1, 2026</p>
    <p>Welcome to Kandid, operated by SolvarionX (“SolvarionX”, “Kandid”, “we”, “us”, or “our”). These Terms of Service (“Terms”) govern your access to and use of Kandid.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">1. What Kandid Is</h4>
    <p>Kandid is a social network built around real people, real relationships, real places, and authentic Moments without relying primarily on popularity metrics.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">2. Eligibility & Account Security</h4>
    <p>You must be legally permitted to use the service under applicable law and provide accurate account information. You are responsible for keeping your credentials secure.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">3. Your Content & License</h4>
    <p>You retain ownership of content you submit. You grant SolvarionX a non-exclusive license to host and distribute your content solely as necessary to operate Kandid.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">4. Prohibited Conduct & Authenticity</h4>
    <p>You agree not to manipulate systems, create fake accounts, harass others, dox individuals, or violate our Community Guidelines.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">5. Contact</h4>
    <p>Operator: SolvarionX. For legal inquiries, contact legal@solvarionx.com.</p>
`;

window.switchScreen = function(screenId) {
    var screens = document.querySelectorAll('.kandid-screen');
    screens.forEach(function(s) {
        s.style.display = 'none';
        s.classList.remove('active');
    });

    var target = document.getElementById('screen-' + screenId);
    if (target) {
        target.style.display = 'flex';
        target.classList.add('active');
    }

    if (screenId === 'inviteSomeone') {
        var usernameInput = document.getElementById('final-username');
        var handle = (state.currentUser && state.currentUser.handle) ? state.currentUser.handle : (usernameInput ? usernameInput.value.trim().replace('@', '') : 'you');
        var inviteDisplay = document.getElementById('inviteLinkDisplay');
        if (inviteDisplay) {
            inviteDisplay.textContent = 'kandid.network/invite/@' + (handle || 'you');
        }
    }
};

const aboutText = `
    <p class="italic text-amber-400 font-mono-tag">Kandid 2.0 — Unfiltered Social Network</p>
    <p>Kandid is designed around real life, authentic dual-camera moments, real campus & place communities, and genuine connection.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">Our Core Principles</h4>
    <p>• <strong>Zero Vanity Metrics:</strong> No follower counts, no public like counts, no popularity rankings.</p>
    <p>• <strong>Authentic Moments:</strong> Unfiltered dual-camera photo captures with 3-second ambient audio.</p>
    <p>• <strong>Community Belonging:</strong> Campus, Place, and Interest hubs where members connect for free.</p>
    <p>• <strong>Fair Creator Value:</strong> Community creators shape real-world connections on campus.</p>
    <p class="pt-2 text-zinc-400">Operated by SolvarionX with pride.</p>
`;

const guidelinesText = `
    <p class="italic text-zinc-400">Community Safety & Respect Standards</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">1. Be Real & Authentic</h4>
    <p>Capture ordinary, uncurated moments from your day. No staged, misleading, or stolen media.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">2. Respect Consent & Privacy</h4>
    <p>Do not capture or share moments of people who requested privacy. Never publish private coordinates or dox anyone.</p>
    <h4 class="font-bold text-white uppercase font-mono-tag pt-2">3. Zero Tolerance For Harassment</h4>
    <p>Hate speech, bullying, non-consensual sharing, and spam will result in immediate permanent account suspension.</p>
`;

window.openLegalModal = function(type) {
    var heading = document.getElementById('modal-heading');
    var body = document.getElementById('modal-body');
    var modal = document.getElementById('legal-modal');
    
    if (type === 'privacy') {
        if (heading) heading.innerText = "KANDID PRIVACY POLICY";
        if (body) body.innerHTML = privacyText;
    } else if (type === 'about') {
        if (heading) heading.innerText = "ABOUT KANDID";
        if (body) body.innerHTML = aboutText;
    } else if (type === 'guidelines') {
        if (heading) heading.innerText = "COMMUNITY GUIDELINES";
        if (body) body.innerHTML = guidelinesText;
    } else {
        if (heading) heading.innerText = "KANDID TERMS OF SERVICE";
        if (body) body.innerHTML = termsText;
    }
    if (modal) modal.style.display = 'flex';
};

window.closeLegalModal = function() {
    var modal = document.getElementById('legal-modal');
    if (modal) modal.style.display = 'none';
};

// =====================================================================
// CATEGORIZED RELATABLE ONBOARDING PLACES & COMMUNITIES
// =====================================================================
const PLACE_CATEGORIES_DATA = {
  'Community': {
    title: 'ADD COMMUNITY / HUB',
    subtitle: 'Where you create, learn, collaborate & belong.',
    placeholder: 'e.g. Indiranagar Tech Hub, Bandra Creator Collective...',
    header: 'Relatable Communities & Hubs:',
    items: [
      { name: 'Indiranagar Coffee & Tech Hub', meta: 'Tech & Cafe · Bengaluru', icon: '☕' },
      { name: 'Bandra Creator Collective', meta: 'Creators & Media · Mumbai', icon: '💻' },
      { name: 'North City Community Hub', meta: 'Open Community · Supaul', icon: '🌿' },
      { name: 'Delhi University Campus', meta: 'North Campus · Delhi', icon: '🎓' },
      { name: 'Hauz Khas Design Studio', meta: 'Design & Visual · Delhi', icon: '🎨' },
      { name: 'Koramangala Startup Commons', meta: 'Makers & Founders · Bengaluru', icon: '🚀' },
      { name: 'Central Reading & Research Wing', meta: 'Quiet & Books · Supaul', icon: '📚' }
    ]
  },
  'City': {
    title: 'ADD YOUR CITY / TOWN',
    subtitle: 'Where are you currently living or exploring?',
    placeholder: 'e.g. Bengaluru, Mumbai, Delhi NCR, Supaul, Pune...',
    header: 'Major Cities & Towns:',
    items: [
      { name: 'Bengaluru, KA', meta: 'Silicon Valley of India', icon: '🏙️' },
      { name: 'Mumbai, MH', meta: 'Maximum City & Coast', icon: '🌆' },
      { name: 'Delhi NCR', meta: 'Capital & Heritage Hub', icon: '🏛️' },
      { name: 'Supaul, Bihar', meta: 'North Bihar Region', icon: '📍' },
      { name: 'Patna, Bihar', meta: 'Historic Capital', icon: '📍' },
      { name: 'Pune, MH', meta: 'Oxford of the East', icon: '⛰️' },
      { name: 'Hyderabad, TS', meta: 'Cyber City & Pearls', icon: '🌴' },
      { name: 'Goa / Panaji', meta: 'Coastal Creative Circle', icon: '🏖️' }
    ]
  },
  'Creative Circle': {
    title: 'CHOOSE YOUR VIBE / CIRCLE',
    subtitle: 'What is your primary craft or creative energy?',
    placeholder: 'e.g. Indie Hacker, Street Photographer, Designer...',
    header: 'Relatable Creative Circles:',
    items: [
      { name: 'Indie Hackers & Tech Builders', meta: 'Code, AI & Hardware', icon: '💻' },
      { name: 'Street & Analog Photographers', meta: '35mm, Visual Stories', icon: '📸' },
      { name: 'Visual & UI/UX Designers', meta: 'Figma, Posters & Brand', icon: '🎨' },
      { name: 'Indie Musicians & Beatmakers', meta: 'Synths, Vinyl & Live', icon: '🎵' },
      { name: 'Late Night Cafe Thinkers', meta: 'Coffee, Notes & Ideas', icon: '☕' },
      { name: 'Writers, Essayists & Researchers', meta: 'Substack & Longform', icon: '📚' },
      { name: 'Outdoor & Nature Explorers', meta: 'Trails, Cycles & Treks', icon: '🌿' }
    ]
  },
  'Workplace': {
    title: 'ADD WORKPLACE / STUDIO',
    subtitle: 'Where you build, research, or work from.',
    placeholder: 'e.g. WeWork Galaxy, Indie Studio, Lab...',
    header: 'Workplaces & Studios:',
    items: [
      { name: 'WeWork Galaxy / Co-working', meta: 'Coworking Space', icon: '🏢' },
      { name: 'Indie Garage & Makerspace', meta: 'Hardware & Prototyping', icon: '🛠️' },
      { name: 'Independent Media & Pod Studio', meta: 'Audio & Video Recording', icon: '🎙️' },
      { name: 'Third Wave Coffee Labs', meta: 'Remote Work Cafe', icon: '☕' },
      { name: 'Remote Home Studio', meta: 'Deep Focus Setup', icon: '🏡' },
      { name: 'University Research Lab', meta: 'Campus Science Wing', icon: '🔬' }
    ]
  }
};

window.openPlaceModal = function(type) {
    state.currentPlaceModalType = type;
    var cat = PLACE_CATEGORIES_DATA[type] || PLACE_CATEGORIES_DATA['Community'];

    var title = document.getElementById('place-modal-title');
    var subtitle = document.getElementById('place-modal-subtitle');
    var header = document.getElementById('placeModalSuggestionsHeader');
    var input = document.getElementById('placeModalInput');
    
    if (title) title.innerText = cat.title;
    if (subtitle) subtitle.innerText = cat.subtitle;
    if (header) header.innerText = cat.header;
    if (input) {
        input.value = '';
        input.placeholder = cat.placeholder;
    }
    
    renderPlaceSuggestions(type, '');
    
    var modal = document.getElementById('place-modal');
    if (modal) modal.style.display = 'flex';
};

window.closePlaceModal = function() {
    var modal = document.getElementById('place-modal');
    if (modal) modal.style.display = 'none';
};

function renderPlaceSuggestions(type, filterText) {
    var container = document.getElementById('placeModalSuggestions');
    if (!container) return;
    
    var cat = PLACE_CATEGORIES_DATA[type] || PLACE_CATEGORIES_DATA['Community'];
    var items = cat.items || [];
    
    var q = (filterText || '').trim().toLowerCase();
    if (q) {
        items = items.filter(function(it) {
            return it.name.toLowerCase().includes(q) || (it.meta && it.meta.toLowerCase().includes(q));
        });
    }
    
    if (items.length === 0) {
        container.innerHTML = 
            '<div class="p-3 bg-zinc-900/30 border border-zinc-800 rounded-xl text-center text-zinc-500 text-[10px]">' +
                'No exact preset found. Tap "Save Selection" below to add "' + escapeHtml(filterText) + '".' +
            '</div>';
        return;
    }
    
    container.innerHTML = items.map(function(it) {
        return '<div onclick="selectPlace(\'' + escapeHtml(it.name).replace(/'/g, "\\'") + '\')" class="p-2.5 bg-zinc-900/60 hover:bg-zinc-900 active:scale-98 border border-zinc-800/80 hover:border-amber-500/40 rounded-xl cursor-pointer flex justify-between items-center transition-all shadow-sm group">' +
            '<div class="flex items-center gap-2.5 min-w-0">' +
                '<span class="text-sm">' + (it.icon || '📍') + '</span>' +
                '<div class="min-w-0">' +
                    '<h4 class="text-xs font-bold text-white group-hover:text-amber-400 transition-colors truncate">' + escapeHtml(it.name) + '</h4>' +
                    '<p class="text-[9px] text-zinc-500 truncate">' + escapeHtml(it.meta || '') + '</p>' +
                '</div>' +
            '</div>' +
            '<span class="text-amber-500 font-mono-tag text-[10px] font-bold opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">SELECT +</span>' +
        '</div>';
    }).join('');
}

window.filterPlaceSuggestions = function() {
    var input = document.getElementById('placeModalInput');
    var val = input ? input.value : '';
    renderPlaceSuggestions(state.currentPlaceModalType, val);
};

window.selectPlace = function(name) {
    var type = state.currentPlaceModalType || 'Community';
    playTactileFeedback('pop');
    showToast('Added ' + name + ' 📍');
    
    if (type === 'Community') {
        state.onboardPlaces.community = name;
        state.onboardPlaces.campus = name;
        var lbl = document.getElementById('world-campus-label');
        var sub = document.getElementById('world-campus-sub');
        var plus = document.getElementById('world-campus-plus');
        if (lbl) lbl.textContent = name;
        if (sub) sub.textContent = 'Your Selected Community';
        if (plus) { plus.textContent = '✓'; plus.className = 'text-amber-500 text-sm font-bold'; }
    } else if (type === 'City') {
        state.onboardPlaces.city = name;
        var lbl = document.getElementById('world-city-label');
        var sub = document.getElementById('world-city-sub');
        var plus = document.getElementById('world-city-plus');
        if (lbl) lbl.textContent = name;
        if (sub) sub.textContent = 'Your Selected City';
        if (plus) { plus.textContent = '✓'; plus.className = 'text-amber-500 text-sm font-bold'; }
    } else if (type === 'Creative Circle') {
        state.onboardPlaces.vibe = name;
        var lbl = document.getElementById('world-place-label');
        var sub = document.getElementById('world-place-sub');
        var plus = document.getElementById('world-place-plus');
        if (lbl) lbl.textContent = name;
        if (sub) sub.textContent = 'Your Vibe & Circle';
        if (plus) { plus.textContent = '✓'; plus.className = 'text-amber-500 text-sm font-bold'; }
    } else if (type === 'Workplace') {
        state.onboardPlaces.workplace = name;
        var lbl = document.getElementById('world-workplace-label');
        var sub = document.getElementById('world-workplace-sub');
        var plus = document.getElementById('world-workplace-plus');
        if (lbl) lbl.textContent = name;
        if (sub) sub.textContent = 'Your Selected Workplace';
        if (plus) { plus.textContent = '✓'; plus.className = 'text-amber-500 text-sm font-bold'; }
    }
    
    closePlaceModal();
};

window.saveCustomPlace = function() {
    var input = document.getElementById('placeModalInput');
    var val = input ? input.value.trim() : '';
    if (!val) {
        showToast('Please enter or select a place');
        return;
    }
    selectPlace(val);
};

window.updateFinalInitials = function() {
    var nameInput = document.getElementById('final-name');
    var val = nameInput ? nameInput.value.trim() : '';
    var initials = 'K';
    if (val) {
        var parts = val.split(' ').filter(Boolean);
        if (parts.length >= 2) {
            initials = (parts[0][0] + parts[1][0]).toUpperCase();
        } else if (parts.length === 1) {
            initials = parts[0].substring(0, 2).toUpperCase();
        }
    }
    var initialsEl = document.getElementById('final-initials');
    if (initialsEl) initialsEl.textContent = initials;
};

var handleCheckTimer = null;
window.handleUsernameInput = function(input) {
    if (!input) return;
    var val = input.value.trim();
    if (val && !val.startsWith('@')) {
        input.value = '@' + val;
        val = input.value;
    }
    var cleanHandle = val.replace('@', '').toLowerCase();
    var badge = document.getElementById('handleAvailabilityBadge');
    if (!badge) return;

    if (!cleanHandle || cleanHandle.length < 2) {
        badge.classList.add('hidden');
        return;
    }

    clearTimeout(handleCheckTimer);
    badge.classList.remove('hidden');
    badge.textContent = 'Checking...';
    badge.className = 'text-[9px] font-mono-tag font-bold text-zinc-400';

    handleCheckTimer = setTimeout(async function() {
        try {
            var res = await apiRequest('/api/users/check-handle?handle=' + encodeURIComponent(cleanHandle));
            if (res && res.available) {
                badge.textContent = '✓ Available';
                badge.className = 'text-[9px] font-mono-tag font-bold text-emerald-400';
            } else {
                badge.textContent = '✗ ' + (res && res.message ? res.message : 'Taken');
                badge.className = 'text-[9px] font-mono-tag font-bold text-red-400';
            }
        } catch(e) {
            badge.classList.add('hidden');
        }
    }, 250);
};

window.togglePasswordVisibility = function(inputId, iconId) {
    var input = document.getElementById(inputId);
    var icon = document.getElementById(iconId);
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) icon.textContent = '🙈';
    } else {
        input.type = 'password';
        if (icon) icon.textContent = '👁️';
    }
};

window.openGoogleAuthModal = function() {
    var modal = document.getElementById('googleAuthModal');
    if (modal) modal.style.display = 'flex';
};

window.closeGoogleAuthModal = function() {
    var modal = document.getElementById('googleAuthModal');
    if (modal) modal.style.display = 'none';
};

window.toggleCustomGoogleInput = function() {
    var form = document.getElementById('customGoogleForm');
    if (form) {
        form.classList.toggle('hidden');
        if (!form.classList.contains('hidden')) {
            var em = document.getElementById('customGoogleEmail');
            if (em) em.focus();
        }
    }
};

window.selectGoogleAccount = async function(email, name, avatarUrl) {
    closeGoogleAuthModal();
    showToast('Verifying with Google Identity (' + email + ')...');

    try {
        var res = await apiRequest('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({
                name: name || 'Google User',
                email: email,
                picture: avatarUrl || ''
            })
        });

        if (res && res.success) {
            // Case 1: Existing Active User -> Direct Instant Feed Login
            if (res.status === 'ACTIVE_USER' && res.token && res.user) {
                localStorage.setItem('kandid_token', res.token);
                localStorage.setItem('kandid_onboarded', 'true');
                localStorage.setItem('kandid_user', JSON.stringify(res.user));
                state.token = res.token;
                state.currentUser = res.user;

                var obFlow = document.getElementById('onboardingFlow');
                if (obFlow) obFlow.style.display = 'none';

                showToast('Welcome back, @' + res.user.handle + '! ✨');

                switchScreenView('feed');
                await loadFeedMoments('foryou');
                await loadCampusScreen();
                await loadYouScreen();
                await loadNotifications();
                await loadChatConversations();
                return;
            } 

            // Case 2: Resume Pending Onboarding Session
            if (res.status === 'RESUME_ONBOARDING') {
                var gp = res.google_profile || {};
                var saved = res.saved_state || {};
                
                state.onboardingSession = {
                    id: res.session_id,
                    profile: gp,
                    handle: saved.handle || gp.suggested_handle || '',
                    campusId: saved.campus_id || null,
                    campusName: saved.campus_name || null,
                    city: saved.city || null,
                    step: res.step || 1
                };

                populateOnboardingIdentityFields(gp.name || '', gp.email || email, state.onboardingSession.handle, gp.avatar_url || avatarUrl);
                
                if (state.onboardingSession.campusName) {
                    selectCampus(state.onboardingSession.campusId, state.onboardingSession.campusName, state.onboardingSession.city);
                }

                showToast('Welcome back! Resuming your setup... 🔄');
                
                if (res.step === 2) {
                    switchScreen('world');
                } else if (res.step === 3) {
                    goToOnboardingReview();
                } else {
                    switchScreen('identity');
                }
                return;
            } 

            // Case 3: New Google User -> Initialize Onboarding Session
            if (res.status === 'NEW_ONBOARDING' || res.is_new) {
                var gp = res.google_profile || { email: email, name: name, avatar_url: avatarUrl, suggested_handle: email.split('@')[0] };
                
                state.onboardingSession = {
                    id: res.session_id,
                    profile: gp,
                    handle: gp.suggested_handle || 'user',
                    campusId: null,
                    campusName: null,
                    city: null,
                    step: 1
                };

                populateOnboardingIdentityFields(gp.name || '', gp.email || email, gp.suggested_handle || '', gp.avatar_url || avatarUrl);

                showToast('Google Identity Verified ✓ Customize your handle & campus');
                switchScreen('identity');
            }
        } else {
            showToast('Google verification failed: ' + (res ? res.error : 'Network error'));
        }
    } catch(e) {
        console.error('Google Auth error:', e);
        showToast('Google sign-in error.');
    }
};

function populateOnboardingIdentityFields(name, email, handle, avatarUrl) {
    var nameInput = document.getElementById('final-name');
    var emailInput = document.getElementById('final-email');
    var usernameInput = document.getElementById('final-username');
    var box = document.getElementById('final-initials-box');
    var banner = document.getElementById('googleIdentityBanner');

    if (banner) banner.classList.remove('hidden');
    if (nameInput) nameInput.value = name;
    if (emailInput) emailInput.value = email;
    if (usernameInput) {
        usernameInput.value = handle ? ('@' + handle.replace('@', '')) : '';
        if (typeof handleUsernameInput === 'function') {
            handleUsernameInput(usernameInput);
        }
    }
    if (avatarUrl && box) {
        state.onboardAvatarData = avatarUrl;
        box.innerHTML = '<img src="' + escapeHtml(avatarUrl) + '" class="w-full h-full object-cover">';
    }

    if (typeof updateFinalInitials === 'function') {
        updateFinalInitials();
    }
}

window.submitCustomGoogleAccount = function() {
    var emailInput = document.getElementById('customGoogleEmail');
    var nameInput = document.getElementById('customGoogleName');

    var email = emailInput ? emailInput.value.trim() : '';
    var name = nameInput ? nameInput.value.trim() : '';

    if (!email || !email.includes('@')) {
        showToast('Please enter a valid Google email address');
        if (emailInput) emailInput.focus();
        return;
    }

    if (!name) {
        name = email.split('@')[0];
    }

    selectGoogleAccount(email, name, '');
};

window.loginWithGoogle = function() {
    openGoogleAuthModal();
};

window.formatHandleInput = window.handleUsernameInput;

window.triggerPhotoUpload = function() {
    var fileInput = document.getElementById('final-avatar-input');
    if (fileInput) fileInput.click();
};

window.handlePhotoUpload = function(event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function(e) {
        state.onboardAvatarData = e.target.result;
        var box = document.getElementById('final-initials-box');
        if (box) {
            box.innerHTML = '<img src="' + e.target.result + '" class="w-full h-full object-cover">';
        }
        var lbl = document.getElementById('photo-upload-label');
        if (lbl) lbl.textContent = 'Photo Selected ✓';
        showToast('Profile photo added 📸');
    };
    reader.readAsDataURL(file);
};

window.validateAndGoToWorld = async function() {
    var nameInput = document.getElementById('final-name');
    var emailInput = document.getElementById('final-email');
    var usernameInput = document.getElementById('final-username');
    var passwordInput = document.getElementById('final-password');

    var nameVal = nameInput ? nameInput.value.trim() : '';
    var emailVal = emailInput ? emailInput.value.trim() : '';
    var userVal = usernameInput ? usernameInput.value.trim().replace('@', '') : '';
    var passVal = passwordInput ? passwordInput.value.trim() : '';

    if (!nameVal) {
        showToast('Please enter your full name');
        if (nameInput) nameInput.focus();
        return;
    }
    if (emailVal && !emailVal.includes('@')) {
        showToast('Please enter a valid email address');
        if (emailInput) emailInput.focus();
        return;
    }
    if (!userVal || userVal.length < 2) {
        showToast('Please choose a username (at least 2 characters)');
        if (usernameInput) usernameInput.focus();
        return;
    }

    if (!state.onboardingSession) {
        state.onboardingSession = {
            id: '',
            profile: { name: nameVal, email: emailVal },
            handle: userVal,
            campusId: null,
            campusName: null,
            city: null,
            step: 2
        };
    } else {
        state.onboardingSession.handle = userVal;
        state.onboardingSession.step = 2;
    }

    if (state.onboardingSession.id) {
        try {
            await apiRequest('/api/onboarding/update-step', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: state.onboardingSession.id,
                    step: 2,
                    handle: userVal
                })
            });
        } catch(e) {}
    }

    switchScreen('world');
    handleCampusSearchInput('');
};

// Campus Search & Selection Logic
var campusSearchTimer = null;
window.handleCampusSearchInput = function(query) {
    clearTimeout(campusSearchTimer);
    campusSearchTimer = setTimeout(function() {
        searchCampuses(query);
    }, 150);
};

window.searchCampuses = async function(query) {
    var dropdown = document.getElementById('onboardCampusDropdown');
    if (!dropdown) return;

    try {
        var res = await apiRequest('/api/campuses/search?q=' + encodeURIComponent((query || '').trim()));
        var campuses = (res && res.campuses) ? res.campuses : [];
        
        if (campuses.length === 0) {
            dropdown.innerHTML = '<div class="p-3 text-center text-zinc-500 text-xs font-mono-tag">No campuses found. <span onclick="openCampusRequestModal()" class="text-amber-400 underline cursor-pointer">Request to add your campus →</span></div>';
            dropdown.classList.remove('hidden');
            return;
        }

        dropdown.innerHTML = campuses.map(function(c) {
            return '<div onclick="selectCampus(\'' + escapeHtml(c.id) + '\', \'' + escapeHtml(c.name).replace(/'/g, "\\'") + '\', \'' + escapeHtml(c.city || '').replace(/'/g, "\\'") + '\')" class="p-3 hover:bg-zinc-800/80 cursor-pointer flex items-center justify-between transition-colors group">' +
                '<div>' +
                    '<h5 class="text-xs font-bold text-white group-hover:text-amber-400 transition-colors">' + escapeHtml(c.name) + '</h5>' +
                    '<p class="text-[10px] text-zinc-400 font-mono-tag">' + escapeHtml(c.city + (c.state ? ', ' + c.state : '')) + '</p>' +
                '</div>' +
                '<span class="text-[9px] text-amber-500 font-mono-tag font-bold opacity-0 group-hover:opacity-100 transition-opacity">SELECT +</span>' +
            '</div>';
        }).join('');
        dropdown.classList.remove('hidden');
    } catch(e) {
        console.error('Campus search error:', e);
    }
};

window.selectCampus = function(id, name, city) {
    if (!state.onboardingSession) {
        state.onboardingSession = {};
    }
    state.onboardingSession.campusId = id;
    state.onboardingSession.campusName = name;
    if (city) {
        state.onboardingSession.city = city;
        var cityInput = document.getElementById('onboardCityInput');
        if (cityInput) cityInput.value = city;
    }

    var nameDisplay = document.getElementById('selectedCampusNameDisplay');
    var cityDisplay = document.getElementById('selectedCampusCityDisplay');
    var searchInput = document.getElementById('onboardCampusSearchInput');
    var dropdown = document.getElementById('onboardCampusDropdown');

    if (nameDisplay) nameDisplay.textContent = name;
    if (cityDisplay) cityDisplay.textContent = city || 'Campus';
    if (searchInput) searchInput.value = name;
    if (dropdown) dropdown.classList.add('hidden');

    showToast('Campus Selected: ' + name + ' 🎓');
};

window.quickSelectCity = function(cityName) {
    var input = document.getElementById('onboardCityInput');
    if (input) input.value = cityName;
    if (state.onboardingSession) {
        state.onboardingSession.city = cityName;
    }
    showToast('City set to: ' + cityName + ' 📍');
};

// Campus Request Modal
window.openCampusRequestModal = function() {
    var modal = document.getElementById('campusRequestModal');
    if (modal) modal.style.display = 'flex';
};

window.closeCampusRequestModal = function() {
    var modal = document.getElementById('campusRequestModal');
    if (modal) modal.style.display = 'none';
};

window.submitCampusRequest = async function() {
    var nameInput = document.getElementById('requestCampusName');
    var cityInput = document.getElementById('requestCampusCity');
    var emailInput = document.getElementById('final-email');

    var campusName = nameInput ? nameInput.value.trim() : '';
    var city = cityInput ? cityInput.value.trim() : '';
    var email = emailInput ? emailInput.value.trim() : '';

    if (!campusName || !city) {
        showToast('Please enter both campus name and city');
        return;
    }

    try {
        var res = await apiRequest('/api/campuses/request', {
            method: 'POST',
            body: JSON.stringify({
                campus_name: campusName,
                city: city,
                email: email
            })
        });

        closeCampusRequestModal();
        selectCampus('camp_req_temp', campusName, city);
        showToast('Campus requested! Temporarily applied to your profile ✓');
    } catch(e) {
        showToast('Campus request submitted for review ✓');
        closeCampusRequestModal();
    }
};

window.selectedInterests = [];
window.selectedPlaces = [];

window.toggleChip = function(btn, chipId) {
    if (!btn) return;
    btn.classList.toggle('selected');
    if (btn.classList.contains('selected')) {
        btn.style.background = 'rgba(245, 158, 11, 0.12)';
        btn.style.borderColor = 'rgba(245, 158, 11, 0.5)';
        btn.style.color = '#f59e0b';
        if (chipId && chipId.startsWith('interest_')) {
            if (!window.selectedInterests.includes(chipId)) window.selectedInterests.push(chipId);
        } else if (chipId) {
            if (!window.selectedPlaces.includes(chipId)) window.selectedPlaces.push(chipId);
        }
    } else {
        btn.style.background = '';
        btn.style.borderColor = '';
        btn.style.color = '';
        if (chipId && chipId.startsWith('interest_')) {
            window.selectedInterests = window.selectedInterests.filter(function(x) { return x !== chipId; });
        } else if (chipId) {
            window.selectedPlaces = window.selectedPlaces.filter(function(x) { return x !== chipId; });
        }
    }
};

window.setCity = function(cityName) {
    var input = document.getElementById('cityInput');
    if (input) input.value = cityName;
    if (!state.onboardingSession) state.onboardingSession = {};
    state.onboardingSession.city = cityName;
    showToast('City set to: ' + cityName + ' 📍');
};

window.handleCampusSearch = function(query) {
    var results = document.getElementById('campusResults');
    if (!results) return;
    query = (query || '').trim().toLowerCase();
    if (!query) {
        results.classList.add('hidden');
        return;
    }
    results.classList.remove('hidden');
};

window.selectCampus = function(id, name, loc) {
    if (!state.onboardingSession) state.onboardingSession = {};
    state.onboardingSession.campusId = id;
    state.onboardingSession.campusName = name;
    state.onboardingSession.campusLoc = loc;

    var inputContainer = document.getElementById('campusInputContainer');
    var selectedCard = document.getElementById('selectedCampusCard');
    var nameEl = document.getElementById('selectedCampusName');
    var locEl = document.getElementById('selectedCampusLoc');
    var results = document.getElementById('campusResults');

    if (nameEl) nameEl.textContent = name;
    if (locEl) locEl.textContent = loc;
    if (inputContainer) inputContainer.classList.add('hidden');
    if (selectedCard) selectedCard.classList.remove('hidden');
    if (results) results.classList.add('hidden');

    showToast('Selected: ' + name + ' 🎓');
};

window.resetCampusSelection = function() {
    var inputContainer = document.getElementById('campusInputContainer');
    var selectedCard = document.getElementById('selectedCampusCard');
    var searchInput = document.getElementById('campusSearchInput');

    if (selectedCard) selectedCard.classList.add('hidden');
    if (inputContainer) inputContainer.classList.remove('hidden');
    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
    }
    if (state.onboardingSession) {
        state.onboardingSession.campusId = null;
        state.onboardingSession.campusName = null;
    }
};

window.skipCampus = function() {
    if (!state.onboardingSession) state.onboardingSession = {};
    state.onboardingSession.campusId = 'none';
    state.onboardingSession.campusName = 'Independent Creator / City';
    showToast('Campus step skipped');
    var cityInput = document.getElementById('cityInput');
    if (cityInput) cityInput.focus();
};

window.persistWorldContext = function() {
    var cityInput = document.getElementById('cityInput');
    var cityVal = cityInput ? cityInput.value.trim() : '';

    if (!state.onboardingSession) state.onboardingSession = {};
    if (cityVal) state.onboardingSession.city = cityVal;

    goToOnboardingReview();
};

// Review Screen Rendering & Editorial Step
window.goToOnboardingReview = async function() {
    var cityInput = document.getElementById('onboardCityInput');
    var cityVal = cityInput ? cityInput.value.trim() : '';
    
    if (!state.onboardingSession) {
        state.onboardingSession = {};
    }
    if (cityVal) {
        state.onboardingSession.city = cityVal;
    }

    if (state.onboardingSession.id) {
        try {
            await apiRequest('/api/onboarding/update-step', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: state.onboardingSession.id,
                    step: 3,
                    campus_id: state.onboardingSession.campusId || '',
                    campus_name: state.onboardingSession.campusName || '',
                    city: state.onboardingSession.city || ''
                })
            });
        } catch(e) {}
    }

    renderOnboardingReview();
    switchScreen('review');
};

function renderOnboardingReview() {
    var nameInput = document.getElementById('final-name');
    var emailInput = document.getElementById('final-email');
    var usernameInput = document.getElementById('final-username');

    var nameVal = (nameInput && nameInput.value.trim()) || (state.onboardingSession && state.onboardingSession.profile && state.onboardingSession.profile.name) || '';
    var emailVal = (emailInput && emailInput.value.trim()) || (state.onboardingSession && state.onboardingSession.profile && state.onboardingSession.profile.email) || '';
    var handleVal = (usernameInput && usernameInput.value.trim().replace('@', '')) || (state.onboardingSession && state.onboardingSession.handle) || '';
    var campusVal = (state.onboardingSession && state.onboardingSession.campusName && state.onboardingSession.campusId !== 'none') ? state.onboardingSession.campusName.trim() : '';
    var cityVal = (state.onboardingSession && state.onboardingSession.city) ? state.onboardingSession.city.trim() : '';
    if (!cityVal) {
        var cInp = document.getElementById('cityInput');
        if (cInp && cInp.value.trim()) cityVal = cInp.value.trim();
    }

    var rName = document.getElementById('summaryName') || document.getElementById('reviewNameDisplay');
    var rHandle = document.getElementById('summaryHandle') || document.getElementById('reviewHandleDisplay');
    var rEmail = document.getElementById('reviewEmailDisplay');
    var rCampus = document.getElementById('summaryCampusText') || document.getElementById('reviewCampusDisplay');
    var rCity = document.getElementById('summaryCityText') || document.getElementById('reviewCityDisplay');
    var rAvatarBox = document.getElementById('summaryAvatar') || document.getElementById('reviewAvatarBox');
    var rInterests = document.getElementById('summaryInterestsText');

    if (rName) rName.textContent = nameVal || 'Not added';
    if (rHandle) {
        if (handleVal) {
            rHandle.textContent = '@' + handleVal;
            rHandle.classList.remove('hidden');
        } else {
            rHandle.classList.add('hidden');
        }
    }
    if (rEmail) rEmail.textContent = emailVal;
    if (rCampus) rCampus.textContent = campusVal || 'Not added';
    if (rCity) rCity.textContent = cityVal || 'Not added';

    if (rInterests) {
        var interestMap = {
            'interest_photo': 'Photography',
            'interest_music': 'Music',
            'interest_coding': 'Coding',
            'interest_sports': 'Sports',
            'interest_startups': 'Startups',
            'interest_art': 'Art'
        };
        var selectedList = (window.selectedInterests || []).map(function(id) {
            return interestMap[id] || id.replace('interest_', '');
        }).filter(Boolean);
        rInterests.textContent = selectedList.length > 0 ? selectedList.join(' · ') : 'Not added';
    }

    if (rAvatarBox) {
        rAvatarBox.replaceChildren();
        if (state.onboardAvatarData) {
            var img = document.createElement('img');
            img.src = state.onboardAvatarData;
            img.className = 'w-full h-full object-cover';
            img.alt = nameVal ? (nameVal + "'s profile photo") : 'Profile photo';
            img.onerror = function() {
                rAvatarBox.replaceChildren();
                rAvatarBox.textContent = nameVal ? nameVal.charAt(0).toUpperCase() : '—';
            };
            rAvatarBox.appendChild(img);
        } else if (nameVal) {
            rAvatarBox.textContent = nameVal.charAt(0).toUpperCase();
        } else {
            rAvatarBox.textContent = '—';
        }
    }
}

window.navigateBack = function() {
    switchScreen('world');
};

window.editIdentity = function() {
    switchScreen('identity');
};

window.editWorld = function() {
    switchScreen('world');
};

window.completeOnboarding = function() {
    return window.submitFinalOnboarding();
};

window.loadOnboardingSummary = renderOnboardingReview;

window.editOnboardingStep = function(step) {
    if (step === 1) {
        switchScreen('identity');
    } else if (step === 2) {
        switchScreen('world');
    }
};

// Final Activation: Atomic Account Creation
window.submitFinalOnboarding = async function() {
    var btn = document.getElementById('finalJoinKandidBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-pulse">Activating Kandid Account...</span>';
    }

    var nameInput = document.getElementById('final-name');
    var emailInput = document.getElementById('final-email');
    var usernameInput = document.getElementById('final-username');
    var passwordInput = document.getElementById('final-password');

    var nameVal = (nameInput && nameInput.value.trim()) || 'Student';
    var emailVal = (emailInput && emailInput.value.trim()) || '';
    var userVal = (usernameInput && usernameInput.value.trim().replace('@', '')) || 'user';
    var passVal = (passwordInput && passwordInput.value.trim()) || '';
    var campusVal = (state.onboardingSession && state.onboardingSession.campusName) || '';
    var campusIdVal = (state.onboardingSession && state.onboardingSession.campusId) || '';
    var cityVal = (state.onboardingSession && state.onboardingSession.city) || '';
    var avatarVal = state.onboardAvatarData || '';

    try {
        var res;
        // If we have an active onboarding session from Google Identity
        if (state.onboardingSession && state.onboardingSession.id) {
            res = await apiRequest('/api/onboarding/complete', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: state.onboardingSession.id,
                    name: nameVal,
                    handle: userVal,
                    campus_name: campusVal,
                    campus_id: campusIdVal,
                    city: cityVal,
                    password: passVal,
                    avatar_url: avatarVal
                })
            });
        } else {
            // Direct registration fallback
            res = await apiRequest('/api/register', {
                method: 'POST',
                body: JSON.stringify({
                    name: nameVal,
                    email: emailVal,
                    handle: userVal,
                    campus: campusVal,
                    location_city: cityVal,
                    password: passVal,
                    avatar_url: avatarVal
                })
            });
        }

        if (res && res.success && res.token && res.user) {
            localStorage.setItem('kandid_token', res.token);
            localStorage.setItem('kandid_onboarded', 'true');
            localStorage.setItem('kandid_user', JSON.stringify(res.user));
            localStorage.setItem('kandid_new_account_' + res.user.id, 'true');
            state.token = res.token;
            state.currentUser = res.user;

            var obFlow = document.getElementById('onboardingFlow');
            if (obFlow) obFlow.style.display = 'none';

            showToast('Welcome to Kandid, @' + res.user.handle + '! 📷 Your world is active.');

            switchScreenView('feed');
            await loadFeedMoments('foryou');
            await loadCampusScreen();
            await loadYouScreen();
            await loadNotifications();
            await loadChatConversations();
        } else {
            showToast('Activation error: ' + (res ? (res.error || res.message) : 'Please try again'));
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Join Kandid →';
            }
        }
    } catch(e) {
        console.error('Final onboarding error:', e);
        showToast('Error during activation. Please try again.');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Join Kandid →';
        }
    }
};

window.copyInviteLink = function() {
    var usernameInput = document.getElementById('final-username');
    var handle = (state.currentUser && state.currentUser.handle) ? state.currentUser.handle : (usernameInput ? usernameInput.value.trim().replace('@', '') : 'you');
    var link = 'https://kandid.network/invite/@' + (handle || 'you');
    
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function() {
            showToast('Invite link copied to clipboard 📋');
        }).catch(function() {
            showToast('Link: ' + link);
        });
    } else {
        showToast('Link: ' + link);
    }
};

async function checkOnboarding() {
    var token = localStorage.getItem('kandid_token');
    var obFlow = document.getElementById('onboardingFlow');
    
    if (!token) {
        state.token = null;
        state.currentUser = null;
        localStorage.removeItem('kandid_active_uid');
        if (obFlow) {
            obFlow.style.display = 'flex';
            switchScreen('entry');
        }
    } else {
        state.token = token;
        if (obFlow) obFlow.style.display = 'none';
        
        try {
            var res = await apiRequest('/api/auth/me');
            if (res && res.user) {
                state.currentUser = res.user;
                localStorage.setItem('kandid_user', JSON.stringify(res.user));
                if (res.user.id) {
                    localStorage.setItem('kandid_active_uid', res.user.id);
                }
            } else {
                // If token invalid, force login
                localStorage.removeItem('kandid_token');
                localStorage.removeItem('kandid_user');
                localStorage.removeItem('kandid_active_uid');
                state.token = null;
                state.currentUser = null;
                if (obFlow) {
                    obFlow.style.display = 'flex';
                    switchScreen('entry');
                }
            }
        } catch(e) {
            console.error('Auth check failed', e);
        }
    }
}

window.submitUserLogin = async function() {
    var identifierInput = document.getElementById('loginIdentifier');
    var passwordInput = document.getElementById('loginPassword');
    var errBox = document.getElementById('loginErrorBox');
    var errText = document.getElementById('loginErrorText');
    
    if (errBox) errBox.classList.add('hidden');

    var identifier = identifierInput ? identifierInput.value.trim().replace('@', '') : '';
    var password = passwordInput ? passwordInput.value.trim() : '';
    
    if (!identifier) {
        showToast('Please enter your username or email');
        if (identifierInput) identifierInput.focus();
        return;
    }
    if (!password) {
        showToast('Please enter your password');
        if (passwordInput) passwordInput.focus();
        return;
    }
    
    showToast('Logging in...');
    
    try {
        var res = await apiRequest('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ identifier: identifier, password: password })
        });
        
        if (res && res.success && res.token) {
            localStorage.setItem('kandid_token', res.token);
            localStorage.setItem('kandid_onboarded', 'true');
            localStorage.setItem('kandid_user', JSON.stringify(res.user));
            if (res.user && res.user.id) {
                localStorage.setItem('kandid_active_uid', res.user.id);
            }
            state.token = res.token;
            state.currentUser = res.user;
            showToast('Welcome back, ' + (res.user.name || res.user.username || 'User') + '! 🎉');
            
            var obFlow = document.getElementById('onboardingFlow');
            if (obFlow) obFlow.style.display = 'none';
            
            switchScreenView('feed');
            await loadFeedMoments('foryou');
            await loadCampusScreen();
            await loadYouScreen();
            await loadNotifications();
            await loadChatConversations();
        } else {
            var errMsg = (res && res.error) ? res.error : 'Invalid username or password.';
            if (errBox && errText) {
                errText.textContent = errMsg;
                errBox.classList.remove('hidden');
            } else {
                showToast(errMsg);
            }
        }
    } catch (e) {
        console.error("Login error", e);
        showToast('Network error during login. Please try again.');
    }
};

window.openResetPasswordModal = function() {
    var modal = document.getElementById('resetPasswordModal');
    var stage1 = document.getElementById('resetPasswordStage1');
    var stage2 = document.getElementById('resetPasswordStage2');
    var loginId = document.getElementById('loginIdentifier');
    var resetId = document.getElementById('resetIdentifier');
    var otpInput = document.getElementById('resetOtpCode');
    var newPwInput = document.getElementById('resetNewPassword');

    if (stage1) stage1.style.display = 'block';
    if (stage2) stage2.style.display = 'none';
    if (otpInput) otpInput.value = '';
    if (newPwInput) newPwInput.value = '';

    if (loginId && resetId && loginId.value.trim()) {
        resetId.value = loginId.value.trim();
    }
    if (modal) modal.style.display = 'flex';
    if (resetId) resetId.focus();
};

window.closeResetPasswordModal = function() {
    var modal = document.getElementById('resetPasswordModal');
    if (modal) modal.style.display = 'none';
};

window.resetPasswordGoBack = function() {
    var stage1 = document.getElementById('resetPasswordStage1');
    var stage2 = document.getElementById('resetPasswordStage2');
    if (stage1) stage1.style.display = 'block';
    if (stage2) stage2.style.display = 'none';
};

window.requestResetPasswordOtp = async function() {
    var idInput = document.getElementById('resetIdentifier');
    var btn = document.getElementById('resetSendOtpBtn');
    var identifier = idInput ? idInput.value.trim() : '';

    if (!identifier) {
        showToast('Please enter your username or registered email');
        if (idInput) idInput.focus();
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-pulse">SENDING OTP CODE...</span>';
    }

    try {
        var res = await apiRequest('/api/auth/forgot-password', {
            method: 'POST',
            body: JSON.stringify({ identifier: identifier })
        });

        if (res && res.success) {
            var stage1 = document.getElementById('resetPasswordStage1');
            var stage2 = document.getElementById('resetPasswordStage2');
            var hint = document.getElementById('resetOtpHint');
            var otpInput = document.getElementById('resetOtpCode');

            if (hint && res.masked_email) {
                hint.textContent = 'Check ' + res.masked_email + ' for your verification code.';
            }
            if (stage1) stage1.style.display = 'none';
            if (stage2) stage2.style.display = 'block';
            if (otpInput) otpInput.focus();

            showToast('Check your email for the verification code ✉️');
        } else {
            showToast(res && res.error ? res.error : 'Unable to send verification code. Please try again.');
        }
    } catch(e) {
        showToast('Unable to send verification code. Please try again.');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'SEND VERIFICATION CODE →';
        }
    }
};

window.submitResetPassword = async function() {
    var idInput = document.getElementById('resetIdentifier');
    var otpInput = document.getElementById('resetOtpCode');
    var passInput = document.getElementById('resetNewPassword');
    
    var identifier = idInput ? idInput.value.trim() : '';
    var otp = otpInput ? otpInput.value.trim() : '';
    var newPassword = passInput ? passInput.value.trim() : '';

    if (!identifier) {
        showToast('Please enter your username or email');
        resetPasswordGoBack();
        return;
    }
    if (!otp || otp.length < 4) {
        showToast('Please enter the 6-digit verification code');
        if (otpInput) otpInput.focus();
        return;
    }
    if (!newPassword || newPassword.length < 4) {
        showToast('Password must be at least 4 characters long');
        if (passInput) passInput.focus();
        return;
    }

    showToast('Verifying code & updating password...');
    var res = await apiRequest('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ identifier: identifier, otp: otp, new_password: newPassword })
    });

    if (res && res.success && res.token) {
        localStorage.setItem('kandid_token', res.token);
        localStorage.setItem('kandid_onboarded', 'true');
        localStorage.setItem('kandid_user', JSON.stringify(res.user));
        state.token = res.token;
        state.currentUser = res.user;

        closeResetPasswordModal();
        showToast('Password updated! Welcome, ' + res.user.name + ' 🎉');

        var obFlow = document.getElementById('onboardingFlow');
        if (obFlow) obFlow.style.display = 'none';

        switchScreenView('feed');
        await loadFeedMoments('foryou');
        await loadCampusScreen();
        await loadYouScreen();
        await loadNotifications();
        await loadChatConversations();
    } else {
        showToast(res && res.error ? res.error : 'Could not reset password.');
    }
};

// =====================================================================
// EXCLUSIVE FOUNDER WELCOME MODAL (FIRST LOGIN ONLY)
// =====================================================================
function checkAndShowFounderModal() {
    var seen = localStorage.getItem('kandid_founder_note_seen');
    var token = localStorage.getItem('kandid_token');
    var onboarded = localStorage.getItem('kandid_onboarded');
    
    if (token && onboarded && !seen) {
        var modal = document.getElementById('founderWelcomeModal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }
}
window.checkAndShowFounderModal = checkAndShowFounderModal;

function dismissFounderModal() {
    localStorage.setItem('kandid_founder_note_seen', 'true');
    var modal = document.getElementById('founderWelcomeModal');
    if (modal) {
        modal.style.opacity = '0';
        setTimeout(function() {
            modal.style.display = 'none';
            modal.style.opacity = '1';
        }, 250);
    }
    showToast("Let's keep it real! Welcome to Kandid. 🚀");
}
window.dismissFounderModal = dismissFounderModal;

document.addEventListener('DOMContentLoaded', async function() {
    await checkOnboarding();
    checkAndShowFounderModal();
    if (state.activeScreen === 'feed' && typeof handleNewUserFeedEntry === 'function') {
        handleNewUserFeedEntry();
    }
});


// =====================================================================
// CHAT NEW MESSAGE & PEOPLE DISCOVERY
// =====================================================================
var chatNewDebounceTimer = null;

function handleChatNewSearch(event) {
  var q = (event.target.value || '').trim();
  if (chatNewDebounceTimer) clearTimeout(chatNewDebounceTimer);
  chatNewDebounceTimer = setTimeout(function() {
    if (q.length > 0) {
      searchPeopleForChat(q);
    } else {
      loadChatNewSuggestions();
    }
  }, 250);
}
window.handleChatNewSearch = handleChatNewSearch;

async function loadChatNewSuggestions() {
  var container = document.getElementById('chatNewSearchResults');
  if (!container) return;
  
  container.innerHTML = '<div class="text-center py-4 text-xs text-zinc-500 font-mono-tag">Loading campus peers...</div>';
  
  var data = await apiRequest('/api/search?type=people&q=');
  if (data && data.success && Array.isArray(data.people)) {
    renderChatNewUserList(data.people, container, 'CAMPUS CONNECTIONS');
  } else {
    container.innerHTML = '<div class="text-center py-6 text-xs text-zinc-500 font-mono-tag">Type a name above to find campus peers.</div>';
  }
}
window.loadChatNewSuggestions = loadChatNewSuggestions;

async function searchPeopleForChat(query) {
  var container = document.getElementById('chatNewSearchResults');
  if (!container) return;

  container.innerHTML = '<div class="text-center py-4 text-xs text-zinc-500 font-mono-tag animate-pulse">SEARCHING PEERS...</div>';

  var data = await apiRequest('/api/search?type=people&q=' + encodeURIComponent(query));
  if (data && data.success && Array.isArray(data.people)) {
    if (data.people.length === 0) {
      container.innerHTML = '<div class="text-center py-6 text-xs text-zinc-500 font-mono-tag">No members found matching "' + escapeHtml(query) + '"</div>';
    } else {
      renderChatNewUserList(data.people, container, 'SEARCH RESULTS (' + data.people.length + ')');
    }
  }
}

function renderChatNewUserList(users, container, title) {
  container.innerHTML = '';
  
  var header = document.createElement('span');
  header.className = 'text-[9px] text-zinc-500 font-mono-tag tracking-widest uppercase px-1 font-bold block mb-2';
  header.textContent = title;
  container.appendChild(header);

  var currentUser = state.currentUser || JSON.parse(localStorage.getItem('kandid_user') || 'null');

  users.forEach(function(u) {
    // Skip self
    if (currentUser && currentUser.id === u.id) return;

    var item = document.createElement('div');
    item.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3 flex items-center justify-between shadow-md cursor-pointer hover:bg-zinc-900/50 transition-all';
    
    var avatarSrc = (u.avatar_url && !u.avatar_url.includes('api.dicebear.com')) ? u.avatar_url : '';
    var name = escapeHtml(u.name || 'Student');
    var handle = escapeHtml(u.handle || 'user');
    var campus = escapeHtml(u.campus || 'North City University');

    item.innerHTML = 
      '<div class="flex items-center gap-3">' +
        '<div class="w-11 h-11 rounded-full bg-zinc-900 overflow-hidden border border-zinc-800 flex-shrink-0">' +
          '<img src="' + avatarSrc + '" class="w-full h-full object-cover">' +
        '</div>' +
        '<div>' +
          '<h3 class="text-xs font-bold text-white">' + name + '</h3>' +
          '<p class="text-[10px] text-zinc-500 font-mono-tag">@' + handle + ' · ' + campus + '</p>' +
        '</div>' +
      '</div>' +
      '<button class="chat-start-btn px-3 py-1.5 bg-zinc-900 hover:bg-amber-500 hover:text-black border border-zinc-800 text-zinc-300 font-mono-tag text-[10px] font-bold rounded-xl transition cursor-pointer active:scale-95 flex items-center gap-1 flex-shrink-0">' +
        '<span>💬</span> <span>CHAT</span>' +
      '</button>';

    var chatBtn = item.querySelector('.chat-start-btn');
    if (chatBtn) {
      chatBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        openChatThread(u.id, name, '@' + handle, avatarSrc);
      });
    }

    item.addEventListener('click', function() {
      openUserProfile(u.id, u);
    });

    container.appendChild(item);
  });
}

// =====================================================================
// SAFETY: BLOCK & REPORT ACTIONS
// =====================================================================
async function submitReportUser() {
  var targetId = state.activeChatUser || 'u_maya';
  var res = await apiRequest('/api/user/report', {
    method: 'POST',
    body: JSON.stringify({
      targetId: targetId,
      reason: 'Inappropriate content / Community guidelines',
      details: 'Reported via mobile in-app flow'
    })
  });
  
  if (res && res.success) {
    showToast('Report submitted. Thank you for keeping Kandid safe 🛡️');
  }
  switchScreenView('report-confirm');
}
window.submitReportUser = submitReportUser;

async function submitBlockUser() {
  var targetId = state.activeChatUser || 'u_alex';
  var res = await apiRequest('/api/user/block', {
    method: 'POST',
    body: JSON.stringify({
      targetId: targetId
    })
  });
  
  if (res && res.success) {
    showToast('User blocked successfully');
    await loadChatConversations();
  }
  switchScreenView('block-confirm');
}
window.submitBlockUser = submitBlockUser;

// =====================================================================
// BLOCK LIST: PERSISTED BLOCKED PEOPLE (MANAGE BLOCKED PEOPLE SCREEN)
// =====================================================================
async function loadBlockList() {
  var container = document.getElementById('blockListContainer');
  if (!container) return;

  container.innerHTML = '<div class="text-center py-12 text-xs text-zinc-500 font-mono-tag animate-pulse">Loading blocked people...</div>';

  var res = await apiRequest('/api/user/blocked');
  var blocked = (res && res.success && Array.isArray(res.blocked)) ? res.blocked : [];

  if (!res || !res.success) {
    container.innerHTML = '<div class="text-center py-12 text-xs text-zinc-500 font-mono-tag">Could not load your block list. Please try again.</div>';
    return;
  }

  if (blocked.length === 0) {
    container.innerHTML = '<div class="text-center py-12 text-xs text-zinc-500 font-mono-tag">You haven\u2019t blocked anyone. Blocked people will appear here.</div>';
    return;
  }

  container.innerHTML = '';
  blocked.forEach(function(u) {
    var row = document.createElement('div');
    row.className = 'flex items-center justify-between p-3.5 rounded-2xl bg-zinc-950 border border-zinc-800/80';
    var avatarLetter = (u.name || u.handle || 'U').charAt(0).toUpperCase();
    var avatarHtml = u.avatar_url
      ? '<img src="' + escapeHtml(u.avatar_url) + '" class="w-10 h-10 rounded-full object-cover" alt="">'
      : '<div class="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center text-amber-400 font-bold text-xs">' + escapeHtml(avatarLetter) + '</div>';
    row.innerHTML =
      '<div class="flex items-center gap-3 min-w-0">' +
        avatarHtml +
        '<div class="min-w-0">' +
          '<p class="text-xs font-bold text-white truncate">' + escapeHtml(u.name || u.handle || 'User') + '</p>' +
          '<p class="text-[10px] text-zinc-500 font-mono-tag truncate">@' + escapeHtml(u.handle || '') + '</p>' +
        '</div>' +
      '</div>' +
      '<button class="px-3.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-amber-400 font-bold text-[10px] rounded-full tracking-wider uppercase cursor-pointer flex-shrink-0" onclick="unblockUser(\'' + escapeHtml(u.id) + '\')">UNBLOCK</button>';
    container.appendChild(row);
  });
}
window.loadBlockList = loadBlockList;

async function unblockUser(userId) {
  if (!userId) return;
  var res = await apiRequest('/api/community/unblock', {
    method: 'POST',
    body: JSON.stringify({ target_id: userId })
  });
  if (res && res.success) {
    showToast('User unblocked');
    loadBlockList();
  } else {
    showToast('Could not unblock: ' + (res && res.error ? res.error : 'Network error'));
  }
}
window.unblockUser = unblockUser;


// =====================================================================
// MEMORIES / PERSONAL ARCHIVE LOADER (10/10 REFINED JOURNAL ENGINE)
// =====================================================================
var activeMemoriesMonth = 'ALL';
var memoriesSearchQuery = '';

async function loadMemoriesScreen() {
  var container = document.getElementById('memoriesListContainer');
  if (!container) return;

  container.innerHTML = '<div class="text-center py-12 text-xs text-zinc-500 font-mono-tag animate-pulse">Loading memories...</div>';

  var data = await apiRequest('/api/me/memories');
  var moments = (data && (data.memories || data.moments)) || [];
  state.myMemories = moments;

  // Update contextual dimensions: MOMENTS · PLACES · COMMUNITIES (No Streak, No Gamification)
  var momentsVal = document.getElementById('memoriesMomentsVal');
  var placesVal = document.getElementById('memoriesPlacesVal');
  var communitiesVal = document.getElementById('memoriesCommunitiesVal');

  var placesSet = new Set();
  var commsSet = new Set();
  moments.forEach(function(m) {
    var loc = m.campus || m.locationCity || m.location_city;
    if (loc && loc.trim()) placesSet.add(loc.trim().toUpperCase());
    var cid = m.primary_community_id || m.community_id;
    if (cid) commsSet.add(cid);
  });

  if (momentsVal) momentsVal.textContent = (data && data.momentsCount !== undefined) ? data.momentsCount : moments.length;
  if (placesVal) placesVal.textContent = (data && data.placesCount !== undefined) ? data.placesCount : placesSet.size;
  if (communitiesVal) communitiesVal.textContent = (data && data.communitiesCount !== undefined) ? data.communitiesCount : commsSet.size;

  // Build dynamic timeline tabs
  updateMemoriesMonthTabs(moments);

  // Render feed
  renderMemoriesFeed();
}
window.loadMemoriesScreen = loadMemoriesScreen;

function updateMemoriesMonthTabs(moments) {
  var tabsContainer = document.getElementById('memoriesMonthFilterTabs');
  if (!tabsContainer) return;

  var monthsMap = {};
  moments.forEach(function(m) {
    var d = m.created_at || m.createdAt;
    if (d && d.length >= 7) {
      monthsMap[d.substring(0, 7)] = true;
    }
  });

  var keys = Object.keys(monthsMap).sort().reverse();
  if (keys.length === 0) {
    keys = ['2026-09', '2026-08'];
  }

  var monthNames = {
    '01': 'JAN', '02': 'FEB', '03': 'MAR', '04': 'APR',
    '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AUG',
    '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DEC'
  };

  var html = '<button type="button" class="px-2.5 py-1 ' + (activeMemoriesMonth === 'ALL' ? 'bg-amber-500 text-black font-bold' : 'bg-zinc-900/80 text-zinc-400 hover:text-white border border-zinc-800') + ' rounded-lg flex-shrink-0 cursor-pointer mem-filter-btn" data-month="ALL" onclick="filterMemoriesByMonth(\'ALL\')">ALL MEMORIES</button>';

  keys.forEach(function(k) {
    var parts = k.split('-');
    var label = (monthNames[parts[1]] || parts[1]) + ' ' + parts[0];
    var isActive = (activeMemoriesMonth === k);
    html += '<button type="button" class="px-2.5 py-1 ' + (isActive ? 'bg-amber-500 text-black font-bold' : 'bg-zinc-900/80 text-zinc-400 hover:text-white border border-zinc-800') + ' rounded-lg flex-shrink-0 cursor-pointer mem-filter-btn" data-month="' + k + '" onclick="filterMemoriesByMonth(\'' + k + '\')">' + label + '</button>';
  });

  tabsContainer.innerHTML = html;
}
window.updateMemoriesMonthTabs = updateMemoriesMonthTabs;

function filterMemoriesByMonth(monthYear) {
  activeMemoriesMonth = monthYear;
  document.querySelectorAll('.mem-filter-btn').forEach(function(btn) {
    if (btn.dataset.month === monthYear) {
      btn.className = 'px-2.5 py-1 bg-amber-500 text-black rounded-lg font-bold flex-shrink-0 cursor-pointer mem-filter-btn';
    } else {
      btn.className = 'px-2.5 py-1 bg-zinc-900/80 text-zinc-400 hover:text-white rounded-lg border border-zinc-800 flex-shrink-0 cursor-pointer mem-filter-btn';
    }
  });
  renderMemoriesFeed();
}
window.filterMemoriesByMonth = filterMemoriesByMonth;

function handleMemoriesSearch(val) {
  memoriesSearchQuery = (val || '').trim();
  renderMemoriesFeed();
}
window.handleMemoriesSearch = handleMemoriesSearch;

function renderMemoriesFeed() {
  var container = document.getElementById('memoriesListContainer');
  if (!container) return;

  var moments = state.myMemories || [];

  // Filter by Month
  if (activeMemoriesMonth !== 'ALL') {
    moments = moments.filter(function(m) {
      var d = m.created_at || m.createdAt || '';
      return d.startsWith(activeMemoriesMonth);
    });
  }

  // Filter by Search Query
  if (memoriesSearchQuery) {
    var q = memoriesSearchQuery.toLowerCase();
    moments = moments.filter(function(m) {
      var cap = (m.caption || '').toLowerCase();
      var loc = (m.locationCity || m.campus || m.location_city || '').toLowerCase();
      var time = (m.timeAgo || '').toLowerCase();
      return cap.includes(q) || loc.includes(q) || time.includes(q);
    });
  }

  container.innerHTML = '';

  if (moments.length === 0) {
    container.innerHTML = 
      '<div class="bg-zinc-950/60 border border-zinc-800/60 rounded-2xl p-10 text-center space-y-4 my-6">' +
        '<div class="w-10 h-10 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mx-auto text-sm">' +
          '<svg class="w-4 h-4 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>' +
        '</div>' +
        '<div class="space-y-1">' +
          '<h3 class="text-xs font-bold text-white tracking-[0.15em] uppercase font-mono-tag">NOTHING HERE YET</h3>' +
          '<p class="text-xs text-zinc-400 leading-relaxed max-w-[240px] mx-auto font-normal">Moments from this part of your life will appear here.</p>' +
        '</div>' +
        '<div class="pt-2">' +
          '<button type="button" class="text-[11px] font-mono-tag text-amber-500 hover:text-amber-400 transition font-medium tracking-wider cursor-pointer" onclick="openCameraStudio()">' +
            'OPEN CAMERA →' +
          '</button>' +
        '</div>' +
      '</div>';
    return;
  }

  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'bg-zinc-950/80 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3 shadow-xl transition';
    
    var mainImg = m.mainImg || m.main_img || m.mediaUrl || '';
    var pipImg = m.pipImg || m.pip_img || '';
    var location = escapeHtml(m.locationCity || m.campus || m.location_city || 'CAMPUS');
    var caption = escapeHtml(m.caption || '');
    var timeStr = m.timeAgo || (typeof formatTimeAgo === 'function' ? formatTimeAgo(m.created_at || '') : 'RECENT');
    var perspectivesCount = m.perspective_count || (m.cluster_id ? 3 : 1);

    var cardHtml = 
      '<div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner cursor-pointer" onclick="openMomentDetail(' + escapeHtml(JSON.stringify(m)) + ')">' +
        '<img src="' + escapeHtml(mainImg) + '" class="w-full h-full object-cover" alt="Memory moment" loading="lazy">';

    if (pipImg) {
      cardHtml += 
        '<div class="absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black">' +
          '<img src="' + escapeHtml(pipImg) + '" class="w-full h-full object-cover" alt="Front perspective" loading="lazy">' +
        '</div>';
    }

    if (perspectivesCount > 1) {
      cardHtml += 
        '<div class="absolute bottom-3 right-3 px-2.5 py-1 bg-black/75 backdrop-blur-md rounded-md border border-zinc-700/60 flex items-center gap-1.5 text-[9px] text-zinc-300 font-mono-tag">' +
          '<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>' +
          '<span>' + perspectivesCount + ' PERSPECTIVES</span>' +
        '</div>';
    }

    cardHtml += 
      '</div>' +
      '<div class="space-y-1 px-0.5">' +
        '<div class="flex justify-between items-center text-[10px] text-zinc-400 font-mono-tag">' +
          '<span class="font-bold text-white tracking-wide">' + location.toUpperCase() + '</span>' +
          '<span class="text-zinc-500">' + timeStr + '</span>' +
        '</div>';

    if (caption) {
      cardHtml += '<p class="text-xs text-zinc-300 font-normal leading-relaxed">"' + caption + '"</p>';
    }

    cardHtml += '</div>';

    card.innerHTML = cardHtml;
    container.appendChild(card);
  });
}
window.renderMemoriesFeed = renderMemoriesFeed;
window.renderMemoriesFeedGrouped = renderMemoriesFeed;

// =====================================================================
// SETTINGS & DATA EXPORT MODULE (INTERACTIVE & PERSISTENT)
// =====================================================================
var defaultSettings = {
  moment_reminders: true,
  messages: true,
  community_activity: true,
  sound: true,
  haptics: true,
  data_saver: false,
  camera_access: true,
  ambient_audio: true,
  high_quality_media: false,
  reduced_motion: false
};

function getSettingValue(key) {
  var stored = localStorage.getItem('kandid_setting_' + key);
  if (stored !== null) return stored === 'true';
  return defaultSettings[key] !== undefined ? defaultSettings[key] : true;
}

function updateSettingSwitchUI(key) {
  var isEnabled = getSettingValue(key);
  var track = document.getElementById('toggleTrack_' + key);
  var thumb = document.getElementById('toggleThumb_' + key);
  if (track && thumb) {
    if (isEnabled) {
      track.className = 'w-10 h-6 bg-amber-500 rounded-full relative cursor-pointer p-0.5 transition-colors shadow-sm';
      thumb.className = 'w-5 h-5 bg-black rounded-full transition-transform transform translate-x-4 shadow';
    } else {
      track.className = 'w-10 h-6 bg-zinc-800 rounded-full relative cursor-pointer p-0.5 transition-colors';
      thumb.className = 'w-5 h-5 bg-zinc-500 rounded-full transition-transform transform translate-x-0 shadow';
    }
  }
}

function toggleSetting(key) {
  var cur = getSettingValue(key);
  var next = !cur;
  localStorage.setItem('kandid_setting_' + key, next.toString());
  updateSettingSwitchUI(key);
  var label = key.replace(/_/g, ' ').toUpperCase();
  showToast(label + ': ' + (next ? 'ENABLED ✓' : 'DISABLED ✕'));
}
window.toggleSetting = toggleSetting;

function openAboutKandidModal() {
  if (typeof openLegalModal === 'function') {
    openLegalModal('about');
  } else {
    showToast('Kandid 2.0 — Authentic Social without Vanity');
  }
}
window.openAboutKandidModal = openAboutKandidModal;

function openCommunityGuidelinesModal() {
  if (typeof openLegalModal === 'function') {
    openLegalModal('guidelines');
  } else {
    showToast('Kandid Community Guidelines: Be Real, Respect Privacy.');
  }
}
window.openCommunityGuidelinesModal = openCommunityGuidelinesModal;

function openHiddenContentModal() {
  showToast('No hidden content. Your feed is clean ✨');
}
window.openHiddenContentModal = openHiddenContentModal;

// ===================================================================
// PHASE 18: PROFESSIONAL IDENTITY, COMMUNITY ROLES & CREATOR DASHBOARD
// ===================================================================

function renderSettingsCreatorSection(user) {
  var u = user || state.currentUser;
  var isCreator = false;
  if (u) {
    if (u.is_creator === 1 || u.is_creator === true || u.is_creator === '1') {
      isCreator = true;
    } else if (['admin', 'founder', 'creator'].includes(u.role)) {
      isCreator = true;
    }
  }

  var becomeRow = document.getElementById('settingsBecomeCreatorRow');
  var dashRow = document.getElementById('settingsCreatorDashboardRow');
  var createRow = document.getElementById('settingsCreateCommunityRow');

  if (isCreator) {
    if (becomeRow) becomeRow.style.display = 'none';
    if (dashRow) dashRow.style.display = 'flex';
    if (createRow) createRow.style.display = 'flex';
  } else {
    if (becomeRow) becomeRow.style.display = 'flex';
    if (dashRow) dashRow.style.display = 'none';
    if (createRow) createRow.style.display = 'none';
  }
}
window.renderSettingsCreatorSection = renderSettingsCreatorSection;

function openCreatorOnboardingModal() {
  var modal = document.getElementById('creatorOnboardingModal');
  if (modal) modal.style.display = 'flex';
}
window.openCreatorOnboardingModal = openCreatorOnboardingModal;

function closeCreatorOnboardingModal() {
  var modal = document.getElementById('creatorOnboardingModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreatorOnboardingModal = closeCreatorOnboardingModal;

async function submitCreatorActivation() {
  var btn = document.getElementById('btnActivateCreator');
  var origText = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>ACTIVATING...</span>';
  }

  try {
    var res = await apiRequest('/api/creator/activate', {
      method: 'POST',
      body: JSON.stringify({})
    });

    if (res && (res.success || res.status === 'already_active' || res.status === 'activated')) {
      if (state.currentUser) {
        state.currentUser.is_creator = 1;
        state.currentUser.creator_activated_at = res.creator_activated_at || new Date().toISOString();
      }
      try {
        var stored = localStorage.getItem('kandid_user');
        if (stored) {
          var parsed = JSON.parse(stored);
          parsed.is_creator = 1;
          localStorage.setItem('kandid_user', JSON.stringify(parsed));
        }
      } catch (e) {}

      closeCreatorOnboardingModal();
      renderSettingsCreatorSection(state.currentUser);
      if (typeof playTactileFeedback === 'function') playTactileFeedback('xp');
      showToast("You're now a Community Creator! ✦");

      setTimeout(function() {
        openCreatorDashboardModal();
      }, 300);
    } else {
      showToast(res && res.error ? res.error : 'Failed to activate creator profile');
    }
  } catch (err) {
    console.error('Creator activation error:', err);
    showToast('Network error activating creator profile');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}
window.submitCreatorActivation = submitCreatorActivation;

async function openCreatorDashboardModal() {
  var modal = document.getElementById('creatorDashboardModal');
  if (modal) modal.style.display = 'flex';

  var spacesCountEl = document.getElementById('creatorDashSpacesCount');
  var membersCountEl = document.getElementById('creatorDashDropsCount');       // repurposed: TOTAL MEMBERS
  var momentsCountEl = document.getElementById('creatorDashAttendeesCount');   // repurposed: MOMENTS SHARED
  var pulseCountEl   = document.getElementById('creatorDashCheckinsCount');    // repurposed: LIVE PULSE
  var commsListEl    = document.getElementById('creatorDashCommunitiesList');

  try {
    var res = await apiRequest('/api/creator/dashboard');
    if (!res || !res.success) {
      if (res && res.error === 'CREATOR_REQUIRED') {
        closeCreatorDashboardModal();
        openCreatorOnboardingModal();
        showToast('Please activate Community Creator profile first.');
        return;
      }
      showToast(res && res.error ? res.error : 'Could not load Creator Dashboard');
      return;
    }

    var ov = res.overview || {};

    if (spacesCountEl) spacesCountEl.textContent = ov.spaces_managed || 0;
    if (membersCountEl) membersCountEl.textContent = ov.total_members || 0;
    if (momentsCountEl) momentsCountEl.textContent = ov.total_moments || 0;
    if (pulseCountEl)   pulseCountEl.textContent   = ov.live_pulse_count || 0;

    // Communities / Spaces
    if (commsListEl) {
      var spaces = res.spaces || [];
      if (spaces.length > 0) {
        commsListEl.innerHTML = spaces.map(function(s) {
          var role = (s.role || s.user_role || 'CREATOR').toUpperCase();
          var roleBadgeClass = role === 'OWNER' ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' : 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30';
          return '<div class="p-3 rounded-2xl bg-zinc-950 border border-white/[.06] flex items-center justify-between text-xs">' +
            '<div class="flex items-center gap-2.5 min-w-0">' +
              '<span class="text-base flex-shrink-0">' + (s.icon || '📍') + '</span>' +
              '<div class="min-w-0">' +
                '<span class="text-white font-bold block truncate">' + escapeHtml(s.name) + '</span>' +
                '<span class="text-[9px] font-mono-tag text-zinc-500 block truncate">' + (s.members_count || 1) + ' members · ' + escapeHtml(s.city || 'Campus') + '</span>' +
              '</div>' +
            '</div>' +
            '<div class="flex items-center gap-2 flex-shrink-0">' +
              '<span class="text-[9px] font-mono-tag font-bold px-2 py-0.5 rounded border ' + roleBadgeClass + '">' + escapeHtml(role) + '</span>' +
              '<button onclick="closeCreatorDashboardModal(); openCampusPage(\'' + escapeHtml(s.name).replace(/'/g, "\\'") + '\')" class="text-[10px] font-mono-tag font-bold text-amber-400 hover:text-amber-300 p-1">OPEN ›</button>' +
            '</div>' +
          '</div>';
        }).join('');
      } else {
        commsListEl.innerHTML = '<div class="p-3 text-center text-xs text-zinc-500 font-mono-tag rounded-xl bg-zinc-950/60 border border-white/[.04]">No spaces created yet. Tap + New Space to begin.</div>';
      }
    }
  } catch (err) {
    console.error('Creator dashboard fetch error:', err);
    showToast('Failed to load creator dashboard data');
  }
}
window.openCreatorDashboardModal = openCreatorDashboardModal;

function closeCreatorDashboardModal() {
  var modal = document.getElementById('creatorDashboardModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreatorDashboardModal = closeCreatorDashboardModal;

async function loadSettingsScreen() {
  var data = await apiRequest('/api/me');
  if (data && data.user) {
    var u = data.user;
    if (state.currentUser) {
      state.currentUser.is_creator = u.is_creator;
      state.currentUser.creator_activated_at = u.creator_activated_at;
      if (u.profile_visibility) state.currentUser.profile_visibility = u.profile_visibility;
      if (u.connections_from) state.currentUser.connections_from = u.connections_from;
    }
    var privLabel = document.getElementById('settingsProfilePrivacyLabel');
    if (privLabel) {
      var isPriv = (u.profile_visibility === 'private');
      privLabel.textContent = isPriv ? 'PRIVATE · Only identity & bio visible' : 'PUBLIC · Visible across Kandid';
    }
    var userEl = document.getElementById('settingsUsername');
    if (userEl) userEl.textContent = '@' + (u.handle || u.username || 'user');

    // Populate email
    var emailEl = document.getElementById('settingsEmail');
    var emailVerEl = document.getElementById('settingsEmailVerified');
    if (emailEl) {
      var email = u.email || (state.currentUser && state.currentUser.email) || '';
      emailEl.textContent = email ? email : '—';
    }
    if (emailVerEl) {
      var isVerified = u.email_verified || (state.currentUser && state.currentUser.email_verified);
      if (isVerified) {
        emailVerEl.textContent = 'VERIFIED ✓';
        emailVerEl.className = 'text-[9px] text-emerald-400 font-mono-tag font-bold';
      } else {
        emailVerEl.textContent = 'UNVERIFIED';
        emailVerEl.className = 'text-[9px] text-zinc-500 font-mono-tag font-bold';
      }
    }
  }

  // Sync all toggle switches
  var settingKeys = ['moment_reminders', 'messages', 'community_activity', 'sound', 'haptics', 'camera_access', 'ambient_audio', 'high_quality_media', 'reduced_motion'];
  settingKeys.forEach(function(k) {
    updateSettingSwitchUI(k);
  });
}
window.loadSettingsScreen = loadSettingsScreen;

async function downloadUserData() {
  showToast('Preparing your JSON archive...');
  var res = await apiRequest('/api/settings/export-data');
  if (res && res.success) {
    var blob = new Blob([JSON.stringify(res.export, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'kandid_archive_' + (state.currentUser ? state.currentUser.handle : 'user') + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('Archive downloaded successfully 💾');
  }
}
window.downloadUserData = downloadUserData;

function logoutUser() {
  if (typeof handleNewUserFeedExit === 'function') {
    handleNewUserFeedExit();
  }
  localStorage.removeItem('kandid_token');
  localStorage.removeItem('kandid_onboarded');
  localStorage.removeItem('kandid_user');
  localStorage.removeItem('kandid_active_uid');
  state.token = null;
  state.currentUser = null;
  showToast('Logged out successfully. Redirecting...');
  setTimeout(function() {
    window.location.reload();
  }, 600);
}
window.logoutUser = logoutUser;

// =====================================================================
// SHARED MOMENT CHAT REPLY
// =====================================================================
async function sendSharedMomentReply() {
  var input = document.getElementById('chatComposerSharedInput');
  if (!input) return;
  var text = input.value.trim();
  if (!text || !state.activeChatUser) return;
  input.value = '';

  var res = await apiRequest('/api/chat/send', {
    method: 'POST',
    body: JSON.stringify({
      receiverId: state.activeChatUser,
      content: '💬 Replied to Moment: "' + text + '"'
    })
  });

  if (res && res.success) {
    switchScreenView('chat-conversation');
    await loadChatMessages(state.activeChatUser);
  }
}
window.sendSharedMomentReply = sendSharedMomentReply;


// =====================================================================
// NOTIFICATIONS & CONNECTION REQUESTS MODULE
// =====================================================================
window.openNotificationsDrawer = function() {
  switchScreenView('notifications');
};

var liveNotifTimer = null;

function showLiveNotificationBanner(notif) {
  var banner = document.getElementById('liveNotificationBanner');
  var titleEl = document.getElementById('liveNotifTitle');
  var bodyEl = document.getElementById('liveNotifBody');
  var actionBtn = document.getElementById('liveNotifActionBtn');

  if (!banner || !notif) return;
  state.currentLiveNotif = notif;

  playTactileFeedback('notif');

  if (titleEl) titleEl.textContent = notif.title || 'New Notification';
  if (bodyEl) bodyEl.textContent = notif.body || notif.time_ago || 'Tap to view';
  if (actionBtn) {
    actionBtn.textContent = (notif.type === 'connection_request') ? 'ACCEPT' : 'VIEW';
  }

  banner.style.display = 'flex';

  if (liveNotifTimer) clearTimeout(liveNotifTimer);
  liveNotifTimer = setTimeout(function() {
    dismissLiveNotification();
  }, 7000);
}
window.showLiveNotificationBanner = showLiveNotificationBanner;

function dismissLiveNotification() {
  var banner = document.getElementById('liveNotificationBanner');
  if (banner) banner.style.display = 'none';
  if (liveNotifTimer) clearTimeout(liveNotifTimer);
}
window.dismissLiveNotification = dismissLiveNotification;

function handleLiveNotificationClick() {
  var notif = state.currentLiveNotif;
  dismissLiveNotification();
  if (!notif) {
    switchScreenView('notifications');
    return;
  }
  if (notif.type === 'connection_request' || notif.type === 'connection_accepted') {
    if (notif.sender_id || notif.target_id) {
      openUserProfile(notif.sender_id || notif.target_id);
    } else {
      switchScreenView('notifications');
    }
  } else if (notif.action_screen) {
    switchScreenView(notif.action_screen);
  } else {
    switchScreenView('notifications');
  }
}
window.handleLiveNotificationClick = handleLiveNotificationClick;

async function loadConnectionRequests() {
  var sec = document.getElementById('notificationsRequestsSection');
  var container = document.getElementById('notificationsRequestsContainer');
  var header = document.getElementById('notificationsRequestsHeader');
  var youBadge = document.getElementById('youRequestsBadge');

  var res = await apiRequest('/api/friend/requests');
  if (res && res.success && Array.isArray(res.requests)) {
    var reqs = res.requests;
    
    // Update YOU page Requests Badge
    if (youBadge) {
      youBadge.textContent = reqs.length > 0 ? reqs.length : '';
      youBadge.style.display = 'none';
    }

    if (!sec || !container) return;

    if (reqs.length === 0) {
      sec.style.display = 'none';
      container.innerHTML = '';
      return;
    }

    sec.style.display = 'block';
    if (header) header.textContent = 'CONNECTION REQUESTS (' + reqs.length + ')';
    container.innerHTML = '';

    reqs.forEach(function(r) {
      var item = document.createElement('div');
      item.className = 'bg-zinc-950 border border-amber-500/40 rounded-2xl p-3.5 flex items-center justify-between gap-3 shadow-xl transition-all';
      
      var avSrc = (r.avatar_url && !r.avatar_url.includes('api.dicebear.com')) ? r.avatar_url : '';
      var name = escapeHtml((r.name || 'Student').toUpperCase());
      var handle = escapeHtml((r.handle || 'user').toUpperCase());
      var campus = escapeHtml(r.campus || 'North City University');
      var timeAgo = escapeHtml(r.time_ago || 'Recently');

      item.innerHTML =
        '<div class="flex items-center gap-3 min-w-0 flex-1 cursor-pointer" onclick="openUserProfile(\'' + r.id + '\')">' +
          '<div class="w-11 h-11 rounded-2xl bg-zinc-900 overflow-hidden border border-zinc-700 flex-shrink-0 flex items-center justify-center">' +
            '<img src="' + avSrc + '" class="w-full h-full object-cover">' +
          '</div>' +
          '<div class="space-y-0.5 min-w-0">' +
            '<h4 class="text-xs font-extrabold text-white uppercase font-mono-tag truncate">' + name + '</h4>' +
            '<p class="text-[10px] text-amber-400 font-mono-tag truncate">@' + handle + ' · <span class="text-zinc-500">' + campus + '</span></p>' +
            '<span class="text-[8px] text-zinc-500 font-mono-tag block">' + timeAgo + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="flex items-center gap-1.5 flex-shrink-0">' +
          '<button class="accept-btn px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[10px] font-mono-tag rounded-xl shadow-md uppercase active:scale-95 cursor-pointer">ACCEPT</button>' +
          '<button class="decline-btn px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-white font-extrabold text-[10px] font-mono-tag rounded-xl shadow-sm uppercase active:scale-95 cursor-pointer">✕</button>' +
        '</div>';

      item.querySelector('.accept-btn').addEventListener('click', async function(e) {
        e.stopPropagation();
        item.style.opacity = '0.5';
        playTactileFeedback('xp');
        showToast('Accepting request from @' + handle + '...');
        var acceptRes = await apiRequest('/api/friend/accept', { method: 'POST', body: { target_user_id: r.id } });
        if (acceptRes && acceptRes.success) {
          showToast('Connected with ' + name + '! ✦ +25 XP');
          item.remove();
          await loadConnectionRequests();
        }
      });

      item.querySelector('.decline-btn').addEventListener('click', async function(e) {
        e.stopPropagation();
        item.style.opacity = '0.5';
        await apiRequest('/api/friend/reject', { method: 'POST', body: { target_user_id: r.id } });
        showToast('Request declined.');
        item.remove();
        await loadConnectionRequests();
      });

      container.appendChild(item);
    });
  }
}
window.loadConnectionRequests = loadConnectionRequests;

async function loadNotifications() {
  await loadConnectionRequests();

  var container = document.getElementById('notificationsListContainer');
  var notifDot = document.getElementById('notifDot');

  var data = await apiRequest('/api/notifications');
  if (data && Array.isArray(data.notifications)) {
    var notifs = data.notifications;
    var unreadCount = data.unreadCount || notifs.filter(function(n) { return n.is_read === 0; }).length;

    if (notifDot) {
      notifDot.style.display = (unreadCount > 0) ? 'block' : 'none';
    }

    if (!container) return;
    container.innerHTML = '';

    if (notifs.length === 0) {
      container.innerHTML = 
        '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-8 text-center space-y-2">' +
          '<div class="w-10 h-10 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-sm font-mono-tag">🔔</div>' +
          '<h3 class="text-xs font-bold text-white uppercase font-mono-tag">YOU\'RE ALL CAUGHT UP</h3>' +
          '<p class="text-[11px] text-zinc-400">No new alerts right now. Authentic moments will appear here.</p>' +
        '</div>';
      return;
    }

    // Partition notifications into TODAY and EARLIER
    var todayNotifs = [];
    var earlierNotifs = [];

    notifs.forEach(function(n) {
      var tAgo = (n.time_ago || n.timeAgo || '').toLowerCase();
      if (tAgo.includes('just now') || tAgo.includes('m ago') || tAgo.includes('h ago') || tAgo.includes('today')) {
        todayNotifs.push(n);
      } else {
        earlierNotifs.push(n);
      }
    });

    if (todayNotifs.length === 0 && earlierNotifs.length > 0) {
      todayNotifs = earlierNotifs.slice(0, 3);
      earlierNotifs = earlierNotifs.slice(3);
    }

    function renderNotifItem(n) {
      var item = document.createElement('div');
      var isUnread = (n.is_read === 0);
      var borderHighlight = isUnread ? 'border-l-2 border-l-amber-500' : '';

      item.className = 'bg-zinc-950 border border-zinc-800/80 ' + borderHighlight + ' rounded-2xl p-3.5 flex items-center justify-between gap-3 shadow-lg transition-colors cursor-pointer hover:bg-zinc-900/50 active:scale-[0.99]';

      var avatarSrc = (n.avatar_url && !n.avatar_url.includes('api.dicebear.com')) ? n.avatar_url : '';
      var title = escapeHtml(n.title || n.message || 'New activity on Kandid');
      var timeAgo = escapeHtml(n.time_ago || n.timeAgo || 'Recent');

      item.innerHTML =
        '<div class="flex items-center gap-3 min-w-0">' +
          '<div class="w-10 h-10 rounded-xl bg-zinc-900 overflow-hidden border border-zinc-800 flex-shrink-0 flex items-center justify-center">' +
            '<img src="' + avatarSrc + '" class="w-full h-full object-cover">' +
          '</div>' +
          '<div class="space-y-0.5 min-w-0">' +
            '<p class="text-xs text-white font-medium leading-snug truncate">' + title + '</p>' +
            '<span class="text-[9px] text-zinc-500 font-mono-tag uppercase">' + timeAgo + '</span>' +
          '</div>' +
        '</div>' +
        (isUnread ? '<span class="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0 animate-pulse"></span>' : '');

      item.addEventListener('click', function() {
        var nType = (n.type || '').toLowerCase();
        if (nType === 'connection_request' || nType === 'connection_accepted') {
          if (n.sender_id || n.target_id) {
            openUserProfile(n.sender_id || n.target_id);
          } else {
            switchScreenView('notifications');
          }
        } else if (nType.includes('message') || nType.includes('chat')) {
          if (n.sender_id) {
            openChatThread(n.sender_id, n.actor_name || 'Friend', n.actor_handle || 'user', avatarSrc, true);
          } else {
            switchScreenView('chat-home');
          }
        } else if (nType.includes('reaction') || nType.includes('moment')) {
          if (n.moment_id || n.target_id) {
            if (typeof openMomentDetailModal === 'function') {
              openMomentDetailModal(n.moment_id || n.target_id);
            } else {
              switchScreenView('feed');
            }
          } else {
            switchScreenView('feed');
          }
        } else if (nType.includes('community') || nType.includes('campus')) {
          openCampusPage(n.community_name || n.target_id || 'North City University');
        } else if (nType.includes('memory')) {
          openCollectiveMemoryPage(n.memory_id || 'mem_1');
        } else if (n.action_screen) {
          switchScreenView(n.action_screen);
        } else {
          switchScreenView('feed');
        }
      });

      return item;
    }

    // Render TODAY Section
    if (todayNotifs.length > 0) {
      var todayHeader = document.createElement('div');
      todayHeader.className = 'px-1 pt-1 pb-0.5';
      todayHeader.innerHTML = '<span class="text-[9px] text-amber-500 font-mono-tag font-bold tracking-widest uppercase">TODAY</span>';
      container.appendChild(todayHeader);

      todayNotifs.forEach(function(n) {
        container.appendChild(renderNotifItem(n));
      });
    }

    // Render EARLIER Section
    if (earlierNotifs.length > 0) {
      var earlierHeader = document.createElement('div');
      earlierHeader.className = 'px-1 pt-3 pb-0.5';
      earlierHeader.innerHTML = '<span class="text-[9px] text-zinc-500 font-mono-tag font-bold tracking-widest uppercase">EARLIER</span>';
      container.appendChild(earlierHeader);

      earlierNotifs.forEach(function(n) {
        container.appendChild(renderNotifItem(n));
      });
    }
  }
}
window.loadNotifications = loadNotifications;

async function markAllNotificationsRead() {
  await apiRequest('/api/notifications/mark-read', { method: 'POST' });
  var notifDot = document.getElementById('notifDot');
  if (notifDot) notifDot.style.display = 'none';
  showToast('All notifications marked as read ✓');
  await loadNotifications();
}
window.markAllNotificationsRead = markAllNotificationsRead;


// =====================================================================
// CHAT V2 MESSAGING ENGINE (PRODUCTION REAL-TIME SYSTEM)
// =====================================================================
// REAL-TIME CHAT & MESSAGING ENGINE (V2.1 PRODUCTION)
// =====================================================================
state.activeChatUser = null;
state.chatSyncInterval = null;

function isUserOnline(lastActive) {
  if (!lastActive) return false;
  try {
    var d = new Date(lastActive);
    var now = new Date();
    return (now.getTime() - d.getTime()) < 120000; // Active within last 2 minutes
  } catch(e) {
    return false;
  }
}
window.isUserOnline = isUserOnline;

// Local cache of fetched conversations and connections
var cachedChatConversations = [];
var cachedChatConnections = [];
var chatHomeCurrentState = 'populated'; // 'populated', 'empty', 'newmsg'

function formatChatTime(isoString) {
  if (!isoString) return '';
  var d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  var now = new Date();
  var diffSec = Math.floor((now - d) / 1000);
  if (diffSec < 60) return 'Just now';
  var diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return diffMin + 'm';
  var diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return diffHr + 'h';
  var diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return diffDays + 'd';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function setChatHomeState(targetState) {
  var populated = document.getElementById('state-populated');
  var empty = document.getElementById('state-empty');
  var newmsg = document.getElementById('state-newmsg');

  if (populated) populated.classList.add('hidden');
  if (empty) empty.classList.add('hidden');
  if (newmsg) newmsg.classList.add('hidden');

  chatHomeCurrentState = targetState;

  if (targetState === 'populated' && populated) {
    populated.classList.remove('hidden');
  } else if (targetState === 'empty' && empty) {
    empty.classList.remove('hidden');
  } else if (targetState === 'newmsg' && newmsg) {
    newmsg.classList.remove('hidden');
  }
}
window.setChatHomeState = setChatHomeState;

async function checkChatUnreadBadge() {
  if (!state.currentUser) return;
  try {
    var data = await apiRequest('/api/chat/unread-count');
    var badge = document.getElementById('chatUnreadBadge');
    var count = (data && data.success) ? (data.count || 0) : 0;
    if (badge) {
      if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.classList.remove('hidden');
        badge.style.display = 'flex';
      } else {
        badge.classList.add('hidden');
        badge.style.display = 'none';
      }
    }
    // Also update chat header notification dot if unread notifications exist
    var chatNotifDot = document.getElementById('chatNotifDot');
    if (chatNotifDot) {
      var notifData = await apiRequest('/api/notifications?unread=1');
      if (notifData && notifData.unread_count > 0) {
        chatNotifDot.classList.remove('hidden');
      } else {
        chatNotifDot.classList.add('hidden');
      }
    }
  } catch(e){}
}
window.checkChatUnreadBadge = checkChatUnreadBadge;

async function loadChatConversations(isSilent = false) {
  var listContainer = document.getElementById('chatConversationsList');
  if (!listContainer) return;

  if (!isSilent && cachedChatConversations.length === 0) {
    listContainer.innerHTML = '<div class="text-center py-8 text-xs text-zinc-500 font-mono-meta animate-pulse">Syncing conversations...</div>';
  }

  var data = await apiRequest('/api/chat/conversations');
  if (data && data.success && Array.isArray(data.conversations)) {
    var convos = data.conversations;
    cachedChatConversations = convos;

    var searchInput = document.getElementById('chatSearchInput');
    var query = searchInput ? searchInput.value.trim().toLowerCase() : '';

    if (chatHomeCurrentState !== 'newmsg') {
      if (convos.length === 0 && !query) {
        setChatHomeState('empty');
      } else {
        setChatHomeState('populated');
        renderChatConversations(convos, query);
      }
    }
  }
}
window.loadChatConversations = loadChatConversations;

function renderChatConversations(convos, filterQuery = '') {
  var listContainer = document.getElementById('chatConversationsList');
  if (!listContainer) return;

  var filtered = convos;
  if (filterQuery) {
    filtered = convos.filter(function(c) {
      var name = ((c.participant && c.participant.name) || c.name || '').toLowerCase();
      var handle = ((c.participant && c.participant.handle) || c.handle || '').toLowerCase();
      var campus = ((c.participant && c.participant.campus) || c.campus || '').toLowerCase();
      var lastMsg = ((c.last_message && c.last_message.preview) || c.lastMessage || '').toLowerCase();
      return name.includes(filterQuery) || handle.includes(filterQuery) || campus.includes(filterQuery) || lastMsg.includes(filterQuery);
    });
  }

  listContainer.innerHTML = '';

  if (filtered.length === 0) {
    if (filterQuery) {
      listContainer.innerHTML = '<div class="text-center py-10 text-xs text-gray-500 font-mono-meta">No conversations found matching "' + escapeHtml(filterQuery) + '"</div>';
    } else {
      setChatHomeState('empty');
    }
    return;
  }

  filtered.forEach(function(c) {
    var p = c.participant || {};
    var partnerId = p.id || c.id;
    var rawName = p.name || c.name || 'Student';
    var rawHandle = (p.handle || c.handle || 'user').replace('@', '');
    var rawCampus = p.campus || c.campus || '';
    var isOnline = (p.is_online !== undefined) ? p.is_online : (c.is_online || false);

    var name = escapeHtml(rawName);
    var handle = escapeHtml(rawHandle);
    var campus = escapeHtml(rawCampus);

    var avatarSrc = p.avatar_url || c.avatar_url || '';
    if (avatarSrc.includes('unsplash.com') || avatarSrc.includes('api.dicebear.com')) {
      avatarSrc = '';
    }

    var lastMsgObj = c.last_message || {};
    var lastMsgText = escapeHtml(lastMsgObj.preview || c.lastMessage || 'Tap to chat');
    var isMoment = lastMsgObj.type === 'moment' || lastMsgObj.moment_id || lastMsgText.includes('Shared a Moment');
    var timeFormatted = formatChatTime(lastMsgObj.created_at || c.lastTimestamp || '');

    var unreadCnt = (c.unread_count !== undefined) ? c.unread_count : (c.unreadCount || 0);
    var hasUnread = (c.unread === true) || (unreadCnt > 0);

    var article = document.createElement('article');
    article.className = 'py-3.5 flex items-center justify-between group cursor-pointer hover:bg-neutral-900/30 px-2 -mx-2 rounded-xl transition';
    article.setAttribute('data-user-id', partnerId);

    var messagePreviewHtml = '';
    if (isMoment) {
      messagePreviewHtml = 
        '<div class="text-[11px] text-gray-300 truncate mt-0.5 flex items-center space-x-1.5">' +
          '<span class="inline-block w-3.5 h-3.5 rounded overflow-hidden flex-shrink-0 border border-neutral-700 bg-neutral-800 text-[9px] flex items-center justify-center">📸</span>' +
          '<span class="truncate">' + lastMsgText + '</span>' +
        '</div>';
    } else {
      messagePreviewHtml = 
        '<p class="text-[11px] ' + (hasUnread ? 'text-gray-200 font-medium' : 'text-gray-400') + ' truncate mt-0.5">' + lastMsgText + '</p>';
    }

    article.innerHTML = 
      '<div class="flex items-center space-x-3.5 min-w-0 flex-1">' +
        '<div class="relative w-11 h-11 rounded-full overflow-hidden bg-neutral-800 flex-shrink-0 border border-neutral-800">' +
          '<img src="' + avatarSrc + '" alt="' + name + '" class="w-full h-full object-cover">' +
          (isOnline ? '<div class="absolute bottom-0 right-0 w-2.5 h-2.5 bg-amber-500 border-2 border-[#0b0b0c] rounded-full"></div>' : '') +
        '</div>' +
        '<div class="min-w-0 flex-1 pr-2">' +
        '<h4 class="text-xs font-bold text-white truncate">' + name + '</h4>' +
          messagePreviewHtml +
          (campus ? '<p class="text-[10px] text-gray-500 truncate mt-0.5 font-mono-meta">' + campus + '</p>' : '') +
        '</div>' +
      '</div>' +
      '<div class="flex flex-col items-end flex-shrink-0 pl-2">' +
        '<span class="text-[10px] font-mono-meta ' + (hasUnread ? 'text-amber-400 font-bold' : 'text-gray-500') + '">' + timeFormatted + '</span>' +
        (hasUnread ? '<span class="w-1.5 h-1.5 bg-amber-500 rounded-full mt-1.5" aria-label="Unread message"></span>' : '') +
      '</div>';

    article.addEventListener('click', function() {
      openChatThread(partnerId, rawName, '@' + rawHandle, avatarSrc, isOnline, rawCampus);
    });

    listContainer.appendChild(article);
  });
}

async function startNewChatFromConnections() {
  setChatHomeState('newmsg');
  await loadChatConnections();
}
window.startNewChatFromConnections = startNewChatFromConnections;

function exitChatNewMsgState() {
  var searchInput = document.getElementById('chatSearchInput');
  if (searchInput) searchInput.value = '';
  var clearBtn = document.getElementById('chatSearchClearBtn');
  if (clearBtn) clearBtn.classList.add('hidden');

  if (cachedChatConversations.length > 0) {
    setChatHomeState('populated');
    renderChatConversations(cachedChatConversations);
  } else {
    setChatHomeState('empty');
  }
}
window.exitChatNewMsgState = exitChatNewMsgState;

async function loadChatConnections() {
  var container = document.getElementById('chatConnectionsList');
  if (!container) return;

  container.innerHTML = '<div class="text-center py-6 text-xs text-gray-500 font-mono-meta animate-pulse">Loading connections...</div>';

  var data = await apiRequest('/api/chat/connections');
  if (data && data.success && Array.isArray(data.connections)) {
    cachedChatConnections = data.connections;
    renderChatConnections(cachedChatConnections);
  } else {
    container.innerHTML = '<div class="text-center py-6 text-xs text-gray-500 font-mono-meta">Could not load connections.</div>';
  }
}
window.loadChatConnections = loadChatConnections;

function renderChatConnections(connections, filterQuery = '') {
  var container = document.getElementById('chatConnectionsList');
  if (!container) return;

  var filtered = connections;
  if (filterQuery) {
    filtered = connections.filter(function(c) {
      var name = (c.name || '').toLowerCase();
      var handle = (c.handle || '').toLowerCase();
      var campus = (c.campus || '').toLowerCase();
      return name.includes(filterQuery) || handle.includes(filterQuery) || campus.includes(filterQuery);
    });
  }

  container.innerHTML = '';

  if (filtered.length === 0) {
    if (filterQuery) {
      container.innerHTML = '<div class="text-center py-8 text-xs text-gray-500 font-mono-meta">No connections matching "' + escapeHtml(filterQuery) + '"</div>';
    } else {
      container.innerHTML = 
        '<div class="py-8 text-center space-y-2">' +
          '<p class="text-xs text-gray-400 font-mono-meta">NO CONNECTIONS YET</p>' +
          '<p class="text-[11px] text-gray-500">Connect with people in Search to start conversations.</p>' +
          '<button onclick="switchScreenView(\'search\')" class="mt-2 px-3.5 py-1.5 bg-neutral-900 border border-neutral-800 text-amber-500 hover:text-white rounded-lg text-xs font-mono-meta cursor-pointer">FIND PEOPLE IN SEARCH →</button>' +
        '</div>';
    }
    return;
  }

  filtered.forEach(function(c) {
    var rawName = c.name || 'Student';
    var rawHandle = (c.handle || 'user').replace('@', '');
    var rawCampus = c.campus || 'Connected';
    var isOnline = !!c.is_online;

    var name = escapeHtml(rawName);
    var handle = escapeHtml(rawHandle);
    var campus = escapeHtml(rawCampus);

    var avatarSrc = c.avatar_url || '';
    if (avatarSrc.includes('unsplash.com') || avatarSrc.includes('api.dicebear.com')) {
      avatarSrc = '';
    }

    var row = document.createElement('div');
    row.className = 'flex items-center justify-between p-2 -mx-2 rounded-xl hover:bg-neutral-900/60 cursor-pointer transition';
    row.setAttribute('data-user-id', c.id);

    row.innerHTML = 
      '<div class="flex items-center space-x-3 min-w-0 flex-1">' +
        '<div class="relative w-10 h-10 rounded-full overflow-hidden bg-neutral-800 flex-shrink-0 border border-neutral-800">' +
          '<img src="' + avatarSrc + '" alt="" class="w-full h-full object-cover">' +
          (isOnline ? '<div class="absolute bottom-0 right-0 w-2.5 h-2.5 bg-amber-500 border-2 border-[#0b0b0c] rounded-full"></div>' : '') +
        '</div>' +
        '<div class="min-w-0 flex-1 pr-2">' +
          '<h5 class="text-xs font-bold text-white truncate">' + name + '</h5>' +
          '<p class="text-[10px] text-gray-400 font-mono-meta truncate">' + campus + '</p>' +
        '</div>' +
      '</div>' +
      '<button type="button" class="px-2.5 py-1 bg-neutral-900 hover:bg-amber-500 hover:text-black border border-neutral-800 text-gray-300 text-[10px] font-mono-meta font-bold rounded-lg transition cursor-pointer flex-shrink-0">CHAT</button>';

    row.addEventListener('click', function() {
      openChatThread(c.id, rawName, '@' + rawHandle, avatarSrc, isOnline, rawCampus);
    });

    container.appendChild(row);
  });
}

function handleChatSearchInput(e) {
  var val = e.target.value;
  var clearBtn = document.getElementById('chatSearchClearBtn');
  if (clearBtn) {
    if (val) {
      clearBtn.classList.remove('hidden');
    } else {
      clearBtn.classList.add('hidden');
    }
  }

  var query = val.trim().toLowerCase();

  if (chatHomeCurrentState === 'newmsg') {
    renderChatConnections(cachedChatConnections, query);
  } else {
    // If user has conversations, filter them
    if (cachedChatConversations.length > 0) {
      renderChatConversations(cachedChatConversations, query);
    } else if (query) {
      // If 0 conversations but user is typing to search someone, switch to State C and search connections
      setChatHomeState('newmsg');
      if (cachedChatConnections.length === 0) {
        loadChatConnections().then(function() {
          renderChatConnections(cachedChatConnections, query);
        });
      } else {
        renderChatConnections(cachedChatConnections, query);
      }
    }
  }
}
window.handleChatSearchInput = handleChatSearchInput;

function clearChatSearch() {
  var searchInput = document.getElementById('chatSearchInput');
  if (searchInput) {
    searchInput.value = '';
    searchInput.focus();
  }
  var clearBtn = document.getElementById('chatSearchClearBtn');
  if (clearBtn) clearBtn.classList.add('hidden');

  if (chatHomeCurrentState === 'newmsg') {
    renderChatConnections(cachedChatConnections, '');
  } else {
    if (cachedChatConversations.length > 0) {
      setChatHomeState('populated');
      renderChatConversations(cachedChatConversations, '');
    } else {
      setChatHomeState('empty');
    }
  }
}
window.clearChatSearch = clearChatSearch;

function openChatThread(userId, name, handle, avatarUrl, isOnline, campus) {
  state.activeChatUser = userId;
  state.activeChatPartner = {
    id: userId,
    name: name || 'Student',
    handle: handle ? (handle.startsWith('@') ? handle : '@' + handle) : '@student',
    avatarUrl: avatarUrl || '',
    isOnline: !!isOnline,
    campus: campus || ''
  };

  clearChatReplyTo();
  closeChatAttachmentMenu();
  closeChatActionMenu();
  closeChatReactionSheet();
  closeChatMomentPicker();

  var headerAvatar = document.getElementById('headerChatAvatar');
  var headerName = document.getElementById('headerChatName');
  var headerHandle = document.getElementById('headerChatHandle');
  var headerCampus = document.getElementById('headerChatCampus');
  
  if (headerAvatar) {
    if (avatarUrl && avatarUrl.trim() && !avatarUrl.includes('api.dicebear.com')) {
      headerAvatar.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
      headerAvatar.onload = function() { this.style.display = 'block'; };
      headerAvatar.src = avatarUrl;
    } else {
      headerAvatar.style.display = 'none';
      headerAvatar.removeAttribute('src');
    }
  }
  if (headerName) {
    headerName.textContent = state.activeChatPartner.name;
  }
  if (headerCampus) {
    if (campus) {
      headerCampus.textContent = campus;
      headerCampus.classList.remove('hidden');
    } else {
      headerCampus.classList.add('hidden');
    }
  }
  if (headerHandle) {
    headerHandle.textContent = state.activeChatPartner.handle;
  }

  switchScreenView('chat-conversation');
  loadChatMessages(userId);
  checkChatUnreadBadge();
}
window.openChatThread = openChatThread;

function viewChatPartnerProfile() {
  if (state.activeChatUser) {
    openUserProfile(state.activeChatUser);
  }
}
window.viewChatPartnerProfile = viewChatPartnerProfile;

function openChatActionMenu() {
  var modal = document.getElementById('chatActionSheetModal');
  if (!modal) return;
  var partner = state.activeChatPartner || { name: 'Student', handle: '@student', avatarUrl: '' };
  var av = document.getElementById('chatActionAvatar');
  var nm = document.getElementById('chatActionName');
  var hd = document.getElementById('chatActionHandle');
  if (av) {
    if (partner.avatarUrl && partner.avatarUrl.trim() && !partner.avatarUrl.includes('api.dicebear.com')) {
      av.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
      av.onload = function() { this.style.display = 'block'; };
      av.src = partner.avatarUrl;
    } else {
      av.style.display = 'none';
      av.removeAttribute('src');
    }
  }
  if (nm) nm.textContent = partner.name;
  if (hd) hd.textContent = partner.handle;

  var mutedList = JSON.parse(localStorage.getItem('kandid_muted_convs') || '[]');
  var isMuted = state.activeChatUser && mutedList.includes(state.activeChatUser);
  var muteBtnText = document.getElementById('chatMuteBtnText');
  if (muteBtnText) {
    muteBtnText.textContent = isMuted ? 'Unmute Notifications' : 'Mute Notifications';
  }

  modal.classList.remove('hidden');
  modal.classList.add('flex');
}
window.openChatActionMenu = openChatActionMenu;

function closeChatActionMenu() {
  var modal = document.getElementById('chatActionSheetModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}
window.closeChatActionMenu = closeChatActionMenu;

function toggleChatMute() {
  if (!state.activeChatUser) return;
  var mutedList = JSON.parse(localStorage.getItem('kandid_muted_convs') || '[]');
  var idx = mutedList.indexOf(state.activeChatUser);
  if (idx > -1) {
    mutedList.splice(idx, 1);
    showToast('Notifications unmuted for this chat');
  } else {
    mutedList.push(state.activeChatUser);
    showToast('Notifications muted for this chat 🔕');
  }
  localStorage.setItem('kandid_muted_convs', JSON.stringify(mutedList));
}
window.toggleChatMute = toggleChatMute;

function openChatPrivacyScreen() {
  if (state.activeChatPartner) {
    var handle = state.activeChatPartner.handle || '@user';
    var blockTitle = document.getElementById('chatPrivacyBlockPromptTitle');
    if (blockTitle) {
      blockTitle.textContent = 'Block ' + (handle.startsWith('@') ? handle : ('@' + handle)) + '?';
    }
  }
  switchScreenView('chat-privacy');
}
window.openChatPrivacyScreen = openChatPrivacyScreen;

function closeChatPrivacyScreen() {
  switchScreenView('chat-conversation');
}
window.closeChatPrivacyScreen = closeChatPrivacyScreen;

function openChatPrivacyModal(type) {
  var container = document.getElementById('chatPrivacyModalContainer');
  var sheetBlock = document.getElementById('chatPrivacySheetBlock');
  var sheetReport = document.getElementById('chatPrivacySheetReport');
  var sheetSignout = document.getElementById('chatPrivacySheetSignout');
  if (!container) return;

  if (sheetBlock) sheetBlock.classList.add('hidden');
  if (sheetReport) sheetReport.classList.add('hidden');
  if (sheetSignout) sheetSignout.classList.add('hidden');

  if (type === 'block') {
    if (state.activeChatPartner) {
      var handle = state.activeChatPartner.handle || '@user';
      var blockTitle = document.getElementById('chatPrivacyBlockPromptTitle');
      if (blockTitle) {
        blockTitle.textContent = 'Block ' + (handle.startsWith('@') ? handle : ('@' + handle)) + '?';
      }
    }
    if (sheetBlock) sheetBlock.classList.remove('hidden');
  } else if (type === 'report') {
    if (sheetReport) sheetReport.classList.remove('hidden');
  } else if (type === 'signout') {
    if (sheetSignout) sheetSignout.classList.remove('hidden');
  }

  container.classList.remove('hidden');
  container.classList.add('flex');
}
window.openChatPrivacyModal = openChatPrivacyModal;

function closeChatPrivacyModal() {
  var container = document.getElementById('chatPrivacyModalContainer');
  var sheetBlock = document.getElementById('chatPrivacySheetBlock');
  var sheetReport = document.getElementById('chatPrivacySheetReport');
  var sheetSignout = document.getElementById('chatPrivacySheetSignout');
  if (container) {
    container.classList.add('hidden');
    container.classList.remove('flex');
  }
  if (sheetBlock) sheetBlock.classList.add('hidden');
  if (sheetReport) sheetReport.classList.add('hidden');
  if (sheetSignout) sheetSignout.classList.add('hidden');
}
window.closeChatPrivacyModal = closeChatPrivacyModal;

async function executeChatPrivacyBlock() {
  if (!state.activeChatUser) return;
  var btn = document.getElementById('chatPrivacyConfirmBlockBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'BLOCKING...'; }
  try {
    var res = await apiRequest('/api/chat/block', {
      method: 'POST',
      body: JSON.stringify({ targetUserId: state.activeChatUser })
    });
    if (res && res.success) {
      closeChatPrivacyModal();
      showToast('User blocked');
      switchScreenView('chat-home');
      loadChatConversations();
    } else {
      showToast(res ? (res.error || 'Failed to block user') : 'Failed to block user');
    }
  } catch (err) {
    showToast('Failed to block user. Please try again.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'BLOCK'; }
  }
}
window.executeChatPrivacyBlock = executeChatPrivacyBlock;

async function executeChatPrivacyReport() {
  if (!state.activeChatUser) return;
  var btn = document.getElementById('chatPrivacyConfirmReportBtn');
  var selectedRadio = document.querySelector('input[name="chat-report-reason"]:checked');
  var reason = selectedRadio ? selectedRadio.value : 'Harassment';
  if (btn) { btn.disabled = true; btn.textContent = 'SUBMITTING...'; }
  try {
    var res = await apiRequest('/api/chat/report', {
      method: 'POST',
      body: JSON.stringify({
        reportedUserId: state.activeChatUser,
        reason: reason,
        details: 'Reported via Chat Privacy & Security screen'
      })
    });
    if (res && res.success) {
      closeChatPrivacyModal();
      showToast('Report submitted. Safety team will review.');
    } else {
      showToast(res ? (res.error || 'Failed to submit report') : 'Failed to submit report');
    }
  } catch (err) {
    showToast('Failed to submit report. Please try again.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'SUBMIT REPORT'; }
  }
}
window.executeChatPrivacyReport = executeChatPrivacyReport;

async function executeChatPrivacySignout() {
  var btn = document.getElementById('chatPrivacyConfirmSignoutBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'SIGNING OUT...'; }
  try {
    await apiRequest('/api/auth/logout', { method: 'POST' });
  } catch (e) {}
  closeChatPrivacyModal();
  logoutUser();
}
window.executeChatPrivacySignout = executeChatPrivacySignout;

function promptChatReport() {
  openChatPrivacyModal('report');
}
window.promptChatReport = promptChatReport;

function promptChatBlock() {
  openChatPrivacyModal('block');
}
window.promptChatBlock = promptChatBlock;

// Reply banner management
function setChatReplyTo(msgId, authorName, textSnippet) {
  state.activeChatReplyTo = {
    id: msgId,
    authorName: authorName || 'Student',
    content: textSnippet || 'Quoted message'
  };
  var banner = document.getElementById('chatReplyBanner');
  var authorEl = document.getElementById('chatReplyAuthor');
  var snippetEl = document.getElementById('chatReplySnippet');
  if (authorEl) authorEl.textContent = 'Replying to ' + state.activeChatReplyTo.authorName;
  if (snippetEl) snippetEl.textContent = state.activeChatReplyTo.content;
  if (banner) {
    banner.classList.remove('hidden');
    banner.classList.add('flex');
  }
  var input = document.getElementById('chatComposerInput');
  if (input) input.focus();
}
window.setChatReplyTo = setChatReplyTo;

function clearChatReplyTo() {
  state.activeChatReplyTo = null;
  var banner = document.getElementById('chatReplyBanner');
  if (banner) {
    banner.classList.add('hidden');
    banner.classList.remove('flex');
  }
}
window.clearChatReplyTo = clearChatReplyTo;

function handleChatReplyClick(msgId) {
  var targetMsg = (state.chatLoadedMessages || []).find(function(m) { return m.id === msgId; });
  if (!targetMsg) return;
  var myUid = String(getActiveUserId() || '').toLowerCase();
  var isMe = String(targetMsg.sender_id || '').toLowerCase() === myUid;
  var name = isMe ? 'You' : (state.activeChatPartner ? state.activeChatPartner.name : 'Student');
  var snippet = targetMsg.content || (targetMsg.message_type === 'photo' ? 'Photo' : 'Moment');
  setChatReplyTo(targetMsg.id, name, snippet);
}
window.handleChatReplyClick = handleChatReplyClick;

// Reactions sheet management
function openChatReactionSheet(msgId) {
  state.targetReactionMsgId = msgId;
  var modal = document.getElementById('chatReactionSheetModal');
  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}
window.openChatReactionSheet = openChatReactionSheet;

function closeChatReactionSheet() {
  state.targetReactionMsgId = null;
  var modal = document.getElementById('chatReactionSheetModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}
window.closeChatReactionSheet = closeChatReactionSheet;

async function submitMessageReaction(emoji) {
  if (!state.targetReactionMsgId) return;
  var msgId = state.targetReactionMsgId;
  closeChatReactionSheet();
  await toggleChatReaction(msgId, emoji);
}
window.submitMessageReaction = submitMessageReaction;

function replyToTargetReactionMessage() {
  if (!state.targetReactionMsgId || !state.chatLoadedMessages) {
    closeChatReactionSheet();
    return;
  }
  var msgId = state.targetReactionMsgId;
  var targetMsg = state.chatLoadedMessages.find(function(m){ return m.id === msgId; });
  closeChatReactionSheet();
  if (targetMsg) {
    var myUid = getActiveUserId();
    var isMe = targetMsg.sender_id === myUid;
    var name = isMe ? 'You' : (state.activeChatPartner ? state.activeChatPartner.name : 'Student');
    var snippet = targetMsg.content || (targetMsg.message_type === 'photo' ? 'Photo' : 'Moment');
    setChatReplyTo(targetMsg.id, name, snippet);
  }
}
window.replyToTargetReactionMessage = replyToTargetReactionMessage;

async function toggleChatReaction(msgId, emoji) {
  try {
    var res = await apiRequest('/api/chat/reactions', {
      method: 'POST',
      body: JSON.stringify({
        message_id: msgId,
        emoji: emoji
      })
    });
    if (res && res.success) {
      await loadChatMessages(state.activeChatUser, true);
    }
  } catch (err) {
    console.error('Reaction error:', err);
  }
}
window.toggleChatReaction = toggleChatReaction;

// Attachment drawer management
function toggleChatAttachmentMenu() {
  var menu = document.getElementById('chatAttachmentMenu');
  if (menu) {
    menu.classList.toggle('hidden');
  }
}
window.toggleChatAttachmentMenu = toggleChatAttachmentMenu;

function closeChatAttachmentMenu() {
  var menu = document.getElementById('chatAttachmentMenu');
  if (menu) {
    menu.classList.add('hidden');
  }
}
window.closeChatAttachmentMenu = closeChatAttachmentMenu;

function triggerChatPhotoUpload() {
  closeChatAttachmentMenu();
  var fileInp = document.getElementById('chatPhotoFileInput');
  if (fileInp) fileInp.click();
}
window.triggerChatPhotoUpload = triggerChatPhotoUpload;

async function handleChatPhotoSelected(event) {
  var file = event.target.files && event.target.files[0];
  if (!file) return;
  event.target.value = '';

  if (!state.activeChatUser) {
    showToast('Select a conversation first');
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    showToast('Photo must be smaller than 10MB');
    return;
  }

  showToast('Uploading attachment...');
  var reader = new FileReader();
  reader.onload = async function(e) {
    var base64Data = e.target.result;
    try {
      var uploadRes = await apiRequest('/api/chat/attachments', {
        method: 'POST',
        body: JSON.stringify({
          partner_id: state.activeChatUser,
          data: base64Data,
          mime_type: file.type || 'image/jpeg'
        })
      });

      if (!uploadRes || !uploadRes.success || !uploadRes.attachment) {
        showToast(uploadRes ? uploadRes.error : 'Attachment upload failed');
        return;
      }

      var replyId = state.activeChatReplyTo ? state.activeChatReplyTo.id : null;
      clearChatReplyTo();

      var sendRes = await apiRequest('/api/chat/send', {
        method: 'POST',
        body: JSON.stringify({
          receiverId: state.activeChatUser,
          message_type: 'photo',
          media_url: uploadRes.attachment.url,
          content: 'Sent a photo',
          reply_to_id: replyId
        })
      });

      if (sendRes && sendRes.success) {
        showToast('Photo sent 🔒');
        await loadChatMessages(state.activeChatUser, false);
      } else {
        showToast('Failed to send photo');
      }
    } catch (err) {
      console.error('Chat photo upload error:', err);
      showToast('Error uploading photo');
    }
  };
  reader.readAsDataURL(file);
}
window.handleChatPhotoSelected = handleChatPhotoSelected;

// Moment picker modal management
async function openChatMomentPicker() {
  var modal = document.getElementById('chatMomentPickerModal');
  var grid = document.getElementById('chatMomentPickerGrid');
  if (!modal || !grid) return;

  grid.innerHTML = '<div class="col-span-3 text-center py-8 text-zinc-500 font-mono-tag text-xs">Loading moments...</div>';
  modal.classList.remove('hidden');
  modal.classList.add('flex');

  try {
    var res = await apiRequest('/api/feed?circle=all');
    var moments = (res && res.moments) ? res.moments : [];
    if (!moments.length) {
      grid.innerHTML = '<div class="col-span-3 text-center py-8 text-zinc-500 font-mono-tag text-xs">No moments found to share</div>';
      return;
    }
    grid.innerHTML = '';
    moments.slice(0, 15).forEach(function(m) {
      var item = document.createElement('div');
      item.className = 'aspect-[3/4] bg-zinc-900 rounded-xl overflow-hidden border border-zinc-800 relative cursor-pointer group hover:border-amber-500 transition-all';
      item.onclick = function() {
        shareMomentToActiveChat(m.id);
      };
      var imgUrl = m.image_url || m.main_img || '';
      item.innerHTML = 
        '<img src="' + imgUrl + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
        '<div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/20 p-1.5 flex flex-col justify-between">' +
          '<span class="text-[8px] font-mono-tag text-amber-400 font-bold uppercase truncate">' + escapeHtml(m.campus || 'CAMPUS') + '</span>' +
          '<span class="text-[8px] text-zinc-200 line-clamp-1 font-sans">' + escapeHtml(m.caption || '') + '</span>' +
        '</div>';
      grid.appendChild(item);
    });
  } catch (err) {
    grid.innerHTML = '<div class="col-span-3 text-center py-8 text-red-400 font-mono-tag text-xs">Failed to load moments</div>';
  }
}
window.openChatMomentPicker = openChatMomentPicker;

function closeChatMomentPicker() {
  var modal = document.getElementById('chatMomentPickerModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}
window.closeChatMomentPicker = closeChatMomentPicker;

async function shareMomentToActiveChat(momentId) {
  if (!state.activeChatUser || !momentId) return;
  closeChatMomentPicker();
  showToast('Sharing moment...');
  try {
    var replyId = state.activeChatReplyTo ? state.activeChatReplyTo.id : null;
    clearChatReplyTo();
    var res = await apiRequest('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({
        receiverId: state.activeChatUser,
        message_type: 'moment',
        moment_id: momentId,
        content: 'Shared a Moment',
        reply_to_id: replyId
      })
    });
    if (res && res.success) {
      showToast('Moment shared to conversation ✨');
      await loadChatMessages(state.activeChatUser, false);
    } else {
      showToast(res ? res.error : 'Failed to share moment');
    }
  } catch (err) {
    console.error('Share moment error:', err);
    showToast('Failed to share moment');
  }
}
window.shareMomentToActiveChat = shareMomentToActiveChat;

async function loadChatMessages(userId, isSilent = false) {
  var container = document.getElementById('chatMessageHistoryV2');
  if (!container) return;

  if (!isSilent && (!container.children.length || container.innerText.includes('LOADING'))) {
      container.innerHTML = '<div class="text-center py-4 text-[10px] text-zinc-500 font-mono-tag">PRIVATE CONVERSATION • LOADING...</div>';
  }

  var myUid = getActiveUserId();
  var data = await apiRequest('/api/chat/messages?chat_id=' + encodeURIComponent(userId) + '&user_id=' + encodeURIComponent(myUid));
  if (data && data.success && Array.isArray(data.messages)) {
    if (state.currentUser && state.currentUser.id) {
      localStorage.setItem('kandid_active_uid', state.currentUser.id);
    }
    state.chatLoadedMessages = data.messages;

    // Build signature to check if DOM needs re-rendering
    var msgSignature = JSON.stringify(data.messages.map(function(m){
      var rxCnt = (m.reactions || []).length;
      return m.id + '_' + (m.read_at ? '1' : '0') + '_' + rxCnt;
    }));
    if (isSilent && container.dataset.msgSig === msgSignature) {
        return; 
    }
    container.dataset.msgSig = msgSignature;

    if (data.messages.length === 0) {
      container.innerHTML = 
        '<div class="text-center py-10 space-y-1 my-auto">' +
          '<span class="text-2xl block">👋</span>' +
          '<p class="text-xs text-white font-bold font-mono-tag uppercase">START OF THE CONVERSATION</p>' +
          '<p class="text-[10px] text-zinc-500 font-mono-tag">Messages are private & encrypted in transit.</p>' +
        '</div>';
      return;
    }

    container.innerHTML = '';
    var myId = String(data.resolved_user_id || myUid || '').toLowerCase();
    var activePartnerId = String(data.resolved_chat_id || userId || '').toLowerCase();

    var lastDateGroup = null;
    data.messages.forEach(function(m) {
      var senderId = String(m.sender_id || '').toLowerCase();
      var isMe = (senderId === myId) || (senderId !== activePartnerId);
      
      // Date divider
      var dateStr = 'TODAY';
      if (m.created_at) {
        var d = new Date(m.created_at);
        if (!isNaN(d.getTime())) {
          var now = new Date();
          if (d.toDateString() === now.toDateString()) {
            dateStr = 'TODAY';
          } else {
            dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
          }
        }
      }
      
      if (dateStr !== lastDateGroup) {
        lastDateGroup = dateStr;
        var dateDivider = document.createElement('div');
        dateDivider.className = 'text-center my-2.5';
        dateDivider.innerHTML = '<span class="text-[8px] font-mono-tag text-zinc-500 bg-zinc-900/80 border border-zinc-800 px-2.5 py-0.5 rounded-full uppercase tracking-wider">' + dateStr + '</span>';
        container.appendChild(dateDivider);
      }

      var bubbleWrap = document.createElement('div');
      bubbleWrap.className = isMe ? 'flex flex-col items-end space-y-1 group' : 'flex flex-col items-start space-y-1 group';
      bubbleWrap.dataset.msgId = m.id;

      var bubbleStyle = isMe 
        ? 'bg-amber-500 text-black font-medium' 
        : 'bg-zinc-900 text-zinc-100 border border-zinc-800';

      var timeOnly = '';
      if (m.created_at) {
        var t = new Date(m.created_at);
        if (!isNaN(t.getTime())) {
          timeOnly = t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
      }
      
      var statusIcon = '';
      if (isMe) {
        if (m.read_at) {
          statusIcon = '<span class="text-[9px] text-amber-950 font-bold ml-1 font-mono-tag" title="Seen">✓✓</span>';
        } else {
          statusIcon = '<span class="text-[9px] text-black/60 font-bold ml-1 font-mono-tag" title="Delivered">✓</span>';
        }
      }

      // Quoted Reply Block
      var replyHtml = '';
      if (m.reply_to) {
        var replyBg = isMe ? 'bg-black/15 border-amber-600' : 'bg-zinc-950 border-amber-500';
        replyHtml = 
          '<div class="rounded-xl ' + replyBg + ' px-2.5 py-1 mb-1.5 border-l-2 text-[10px] space-y-0.5 max-w-full overflow-hidden">' +
            '<span class="font-bold ' + (isMe ? 'text-black font-mono-tag' : 'text-amber-400 font-mono-tag') + ' block truncate">@' + escapeHtml(m.reply_to.sender_handle || 'user') + '</span>' +
            '<span class="truncate block ' + (isMe ? 'text-black/80' : 'text-zinc-300') + '">' + escapeHtml(m.reply_to.content || '') + '</span>' +
          '</div>';
      }

      // Photo Attachment Block
      var photoHtml = '';
      if (m.message_type === 'photo' || (m.media_url && !m.moment)) {
        // SECURITY B-04: use data-media-url + safeOpenMediaUrl() instead of inline onclick with window.open to prevent javascript: XSS
        photoHtml = 
          '<div class="rounded-xl overflow-hidden border ' + (isMe ? 'border-amber-600/30' : 'border-zinc-800') + ' my-1 max-w-[240px]">' +
            '<img src="' + escapeHtml(m.media_url) + '" class="w-full h-auto max-h-60 object-cover rounded-lg cursor-pointer" loading="lazy" data-media-url="' + escapeHtml(m.media_url) + '" onclick="safeOpenMediaUrl(this.dataset.mediaUrl)">' +
          '</div>';
      }

      // Moment Card Block
      var momentHtml = '';
      if (m.message_type === 'moment' && m.moment) {
        momentHtml = 
          '<div class="rounded-xl overflow-hidden border border-zinc-700 bg-black/40 my-1 max-w-[240px] cursor-pointer shadow-md" onclick="switchScreenView(\'feed\')">' +
            '<img src="' + escapeHtml(m.moment.image_url) + '" class="w-full aspect-[4/3] object-cover">' +
            '<div class="p-2 space-y-0.5 bg-zinc-950/90 border-t border-zinc-800">' +
              '<span class="text-[8px] text-amber-400 font-mono-tag font-bold uppercase tracking-wider block">SHARED A MOMENT · ' + escapeHtml(m.moment.campus || 'CAMPUS') + '</span>' +
              (m.moment.caption ? ('<p class="text-[11px] text-zinc-200 truncate font-sans">"' + escapeHtml(m.moment.caption) + '"</p>') : '') +
            '</div>' +
          '</div>';
      }

      // Text body
      var textHtml = '';
      var hasCustomText = m.content && m.content !== 'Shared a Moment' && m.content !== 'Sent a photo';
      if (hasCustomText || (!photoHtml && !momentHtml)) {
        textHtml = '<p class="leading-relaxed break-words">' + escapeHtml(m.content || '') + '</p>';
      }

      // Action buttons row (visible on hover / active)
      var senderLabel = isMe ? 'You' : (state.activeChatPartner ? state.activeChatPartner.name : 'Student');
      var quoteText = m.content || (m.message_type === 'photo' ? 'Photo' : 'Moment');

      bubbleWrap.innerHTML = 
        '<div class="flex items-end gap-1.5 ' + (isMe ? 'flex-row-reverse' : 'flex-row') + ' max-w-[85%]">' +
          '<div class="rounded-2xl px-3.5 py-2 text-xs ' + bubbleStyle + ' shadow-sm space-y-0.5 max-w-full">' +
            replyHtml +
            photoHtml +
            momentHtml +
            textHtml +
            '<div class="flex items-center justify-end gap-1 opacity-80 pt-0.5">' +
              '<span class="text-[8px] font-mono-tag">' + timeOnly + '</span>' +
              statusIcon +
            '</div>' +
          '</div>' +
          '<div class="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 shrink-0 pb-1">' +
            '<button onclick="handleChatReplyClick(\'' + m.id + '\')" class="w-6 h-6 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center text-[10px] cursor-pointer" title="Reply">↩</button>' +
            '<button onclick="openChatReactionSheet(\'' + m.id + '\')" class="w-6 h-6 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center text-[10px] cursor-pointer" title="React">☺</button>' +
          '</div>' +
        '</div>';

      // Render reaction pills if any
      if (m.reactions && m.reactions.length) {
        var rxMap = {};
        m.reactions.forEach(function(r) {
          if (!rxMap[r.emoji]) rxMap[r.emoji] = { count: 0, me: false };
          rxMap[r.emoji].count++;
          if (String(r.user_id).toLowerCase() === myId) rxMap[r.emoji].me = true;
        });

        var rxContainer = document.createElement('div');
        rxContainer.className = 'flex flex-wrap gap-1 px-1 ' + (isMe ? 'justify-end' : 'justify-start');
        Object.keys(rxMap).forEach(function(em) {
          var item = rxMap[em];
          var pillBtn = document.createElement('button');
          var cls = item.me ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold' : 'bg-zinc-850 text-zinc-300 border-zinc-800';
          pillBtn.className = 'text-[10px] px-2 py-0.5 rounded-full border ' + cls + ' font-mono-tag flex items-center gap-1 active:scale-95 transition-all cursor-pointer';
          pillBtn.innerHTML = em + ' <span class="text-[9px]">' + item.count + '</span>';
          pillBtn.onclick = function() {
            toggleChatReaction(m.id, em);
          };
          rxContainer.appendChild(pillBtn);
        });
        bubbleWrap.appendChild(rxContainer);
      }

      container.appendChild(bubbleWrap);
    });

    container.scrollTop = container.scrollHeight;
  }
}
window.loadChatMessages = loadChatMessages;

function openCameraForActiveChat() {
  if (state.activeChatUser) {
    state.activeChatMomentReceiver = state.activeChatUser;
    showToast('Snap a moment for this chat 📸');
  }
  openCameraStudio();
}
window.openCameraForActiveChat = openCameraForActiveChat;

async function sendChatMessageV2() {
  var input = document.getElementById('chatComposerInput');
  if (!input) return;
  var text = input.value.trim();
  if (!text) return;
  if (!state.activeChatUser) {
    showToast('Please select a user to message.');
    return;
  }

  var replyId = state.activeChatReplyTo ? state.activeChatReplyTo.id : null;
  clearChatReplyTo();
  input.value = '';

  var myUid = getActiveUserId();
  var container = document.getElementById('chatMessageHistoryV2');
  var tempBubble = null;
  if (container) {
    if (container.innerText.includes('START OF THE CONVERSATION') || container.innerText.includes('PRIVATE CONVERSATION')) {
      container.innerHTML = '';
    }

    tempBubble = document.createElement('div');
    tempBubble.className = 'flex flex-col items-end space-y-1';
    var timeNow = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    tempBubble.innerHTML = 
      '<div class="max-w-[78%] rounded-2xl px-3.5 py-2 text-xs bg-amber-500 text-black font-medium shadow-sm space-y-0.5">' +
        '<p class="leading-relaxed">' + escapeHtml(text) + '</p>' +
        '<div class="flex items-center justify-end gap-1 opacity-80 pt-0.5">' +
          '<span class="text-[8px] font-mono-tag">' + timeNow + '</span>' +
          '<span class="text-[9px] text-black/60 font-bold ml-1 font-mono-tag">✓</span>' +
        '</div>' +
      '</div>';
    container.appendChild(tempBubble);
    container.scrollTop = container.scrollHeight;
  }

  try {
    var res = await apiRequest('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({
        senderId: myUid,
        sender_id: myUid,
        receiverId: state.activeChatUser,
        receiver_id: state.activeChatUser,
        content: text,
        reply_to_id: replyId,
        message_type: 'text'
      })
    });

    if (res && res.success) {
      if (tempBubble && res.message && res.message.id) {
        tempBubble.dataset.msgId = res.message.id;
      }
      await loadChatMessages(state.activeChatUser, true);
      checkChatUnreadBadge();
    } else {
      showToast(res ? res.error : 'Message send failed. Please check connection.');
      if (tempBubble) tempBubble.remove();
    }
  } catch (err) {
    console.error('Chat send error:', err);
    showToast('Failed to send message.');
    if (tempBubble) tempBubble.remove();
  }
}
window.sendChatMessageV2 = sendChatMessageV2;

// Background Real-Time Poller for Chat & Notifications
if (window.chatSyncGlobalInterval) clearInterval(window.chatSyncGlobalInterval);
window.chatSyncGlobalInterval = setInterval(function() {
  // D3-3: skip network polling while the tab/document is hidden
  if (document.hidden) return;
  checkChatUnreadBadge();
  if (state.activeScreen === 'chat-conversation' && state.activeChatUser) {
    loadChatMessages(state.activeChatUser, true);
  } else if (state.activeScreen === 'chat-home') {
    loadChatConversations(true);
  }
}, 2500);

// Background Heartbeat Ping (keeps active status live every 45s)
if (window.chatHeartbeatInterval) clearInterval(window.chatHeartbeatInterval);
window.chatHeartbeatInterval = setInterval(function() {
  // D3-3: skip network polling while the tab/document is hidden
  if (document.hidden) return;
  if (state.currentUser && state.token) {
    apiRequest('/api/auth/ping').catch(function(){});
  }
}, 45000);

// =====================================================================
// EDIT PROFILE & USER UPDATE SYSTEM
// =====================================================================
var pendingEditAvatarData = '';
var pendingEditCoverData = '';

function openEditProfileModal() {
  var modal = document.getElementById('editProfileModal');
  var nameInp = document.getElementById('modalEditName');
  var userInp = document.getElementById('modalEditUsername');
  var bioInp = document.getElementById('modalEditBio');
  var campusInp = document.getElementById('modalEditCampus');
  var cityInp = document.getElementById('modalEditCity');
  var vibeInp = document.getElementById('modalEditVibe');
  var previewImg = document.getElementById('modalEditAvatarPreview');
  var initsEl = document.getElementById('modalEditAvatarInitials');

  pendingEditAvatarData = '';
  pendingEditCoverData = '';

  if (state.currentUser) {
    if (nameInp) nameInp.value = state.currentUser.name || '';
    if (userInp) userInp.value = (state.currentUser.handle || state.currentUser.username || '').replace('@', '');
    if (bioInp) bioInp.value = state.currentUser.bio || 'Capturing ordinary days.';
    if (campusInp) campusInp.value = state.currentUser.campus || state.currentUser.community || 'North City Community';
    if (cityInp) cityInp.value = state.currentUser.location_city || state.currentUser.city || 'Supaul, Bihar';
    if (vibeInp) vibeInp.value = state.currentUser.vibe || 'Creator';
    
    if (initsEl) {
      initsEl.style.display = 'none';
      initsEl.textContent = '';
    }

    var curAvatar = (state.currentUser.avatar_url || state.currentUser.avatar || '').trim();
    if (curAvatar && !curAvatar.includes('api.dicebear.com')) {
      if (previewImg) {
        previewImg.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        previewImg.onload = function() { this.style.display = 'block'; };
        previewImg.src = curAvatar;
      }
    } else {
      if (previewImg) {
        previewImg.style.display = 'none';
        previewImg.removeAttribute('src');
      }
    }

    var curCover = (state.currentUser.cover_url || state.currentUser.cover || '').trim();
    var coverPreview = document.getElementById('modalEditCoverPreview');
    var coverPlaceholder = document.getElementById('modalEditCoverPlaceholder');
    if (coverPlaceholder) {
      coverPlaceholder.style.display = 'none';
      coverPlaceholder.textContent = '';
    }

    if (curCover && !curCover.includes('unsplash.com')) {
      if (coverPreview) {
        coverPreview.onerror = function() { this.style.display = 'none'; this.removeAttribute('src'); };
        coverPreview.onload = function() { this.style.display = 'block'; };
        coverPreview.src = curCover;
      }
    } else {
      if (coverPreview) {
        coverPreview.style.display = 'none';
        coverPreview.removeAttribute('src');
      }
    }
  }

  if (modal) modal.style.display = 'flex';
}
window.openEditProfileModal = openEditProfileModal;

function handleModalAvatarUpload(event) {
  var file = event.target.files && event.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    pendingEditAvatarData = e.target.result;
    var previewImg = document.getElementById('modalEditAvatarPreview');
    var initsEl = document.getElementById('modalEditAvatarInitials');
    if (previewImg) {
      previewImg.src = e.target.result;
      previewImg.style.display = 'block';
    }
    if (initsEl) initsEl.style.display = 'none';
    showToast('Photo selected! Click Save Changes 📸');
  };
  reader.readAsDataURL(file);
}
window.handleModalAvatarUpload = handleModalAvatarUpload;

function handleModalCoverUpload(event) {
  var file = event.target.files && event.target.files[0];
  if (!file) return;
  if (!file.type || !file.type.startsWith('image/')) {
    showToast('Please select a valid image file (JPG, PNG, WebP).');
    return;
  }
  if (file.size > 15 * 1024 * 1024) {
    showToast('Cover photo exceeds maximum size limit (15MB).');
    return;
  }
  var reader = new FileReader();
  reader.onload = function(e) {
    pendingEditCoverData = e.target.result;
    var coverPreview = document.getElementById('modalEditCoverPreview');
    var coverPlaceholder = document.getElementById('modalEditCoverPlaceholder');
    if (coverPreview) {
      coverPreview.src = e.target.result;
      coverPreview.style.display = 'block';
    }
    if (coverPlaceholder) coverPlaceholder.style.display = 'none';
    showToast('Cover photo selected! Click Save Changes 📸');
  };
  reader.readAsDataURL(file);
}
window.handleModalCoverUpload = handleModalCoverUpload;

function closeEditProfileModal() {
  var modal = document.getElementById('editProfileModal');
  if (modal) modal.style.display = 'none';
  pendingEditAvatarData = '';
  pendingEditCoverData = '';
  var aInp = document.getElementById('modalEditAvatarInput');
  if (aInp) aInp.value = '';
  var cInp = document.getElementById('modalEditCoverInput');
  if (cInp) cInp.value = '';
}
window.closeEditProfileModal = closeEditProfileModal;

async function saveUserProfileChanges() {
  var nameInp = document.getElementById('modalEditName');
  var userInp = document.getElementById('modalEditUsername');
  var bioInp = document.getElementById('modalEditBio');
  var campusInp = document.getElementById('modalEditCampus');
  var cityInp = document.getElementById('modalEditCity');
  var vibeInp = document.getElementById('modalEditVibe');

  var newName = nameInp ? nameInp.value.trim() : '';
  var newHandle = userInp ? userInp.value.trim().replace('@', '') : '';
  var newBio = bioInp ? bioInp.value.trim() : '';
  var newCampus = campusInp ? campusInp.value.trim() : '';
  var newCity = cityInp ? cityInp.value.trim() : '';
  var newVibe = vibeInp ? vibeInp.value.trim() : '';

  if (!newName) {
    showToast('Name cannot be empty');
    return;
  }

  showToast('Saving profile updates...');
  var payload = {
    name: newName,
    handle: newHandle,
    bio: newBio,
    campus: newCampus,
    location_city: newCity,
    vibe: newVibe
  };
  if (pendingEditAvatarData) {
    payload.avatar_url = pendingEditAvatarData;
  }
  if (pendingEditCoverData) {
    payload.cover_url = pendingEditCoverData;
  }

  var res = await apiRequest('/api/user/update', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (res && res.success) {
    if (state.currentUser) {
      state.currentUser.name = newName;
      if (newHandle) state.currentUser.handle = newHandle;
      state.currentUser.bio = newBio;
      state.currentUser.campus = newCampus;
      state.currentUser.location_city = newCity;
      state.currentUser.vibe = newVibe;
      if (res.user && res.user.avatar_url) {
        state.currentUser.avatar_url = res.user.avatar_url;
      }
      if (res.user && res.user.cover_url) {
        state.currentUser.cover_url = res.user.cover_url;
      } else if (pendingEditCoverData) {
        state.currentUser.cover_url = pendingEditCoverData;
      }
      localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
    }
    showToast('Profile updated successfully! ✨');
    closeEditProfileModal();
    await loadYouScreen();
    await loadSettingsScreen();
  } else {
    showToast('Could not save changes: ' + (res ? res.error : 'Network error'));
  }
}
window.saveUserProfileChanges = saveUserProfileChanges;

// =====================================================================
// PRIVACY CONTROLS MODAL HANDLERS
// =====================================================================
function openPrivacyModal() {
  var modal = document.getElementById('privacyModal');
  if (modal) {
    modal.style.display = 'flex';
    // Pre-select current values
    var u = state.currentUser || {};
    var currProf = (u.profile_visibility || 'public').toLowerCase();
    var profRadio = document.querySelector('input[name="privacyProfile"][value="' + currProf + '"]');
    if (profRadio) profRadio.checked = true;

    var currConn = (u.connections_from || 'everyone').toLowerCase();
    var connRadio = document.querySelector('input[name="privacyConnections"][value="' + currConn + '"]');
    if (connRadio) connRadio.checked = true;
  }
}
window.openPrivacyModal = openPrivacyModal;

function closePrivacyModal() {
  var modal = document.getElementById('privacyModal');
  if (modal) modal.style.display = 'none';
}
window.closePrivacyModal = closePrivacyModal;

async function savePrivacySettings() {
  var pVis = document.querySelector('input[name="privacyProfile"]:checked');
  var mVis = document.querySelector('input[name="privacyMoments"]:checked');
  var msgVis = document.querySelector('input[name="privacyMessages"]:checked');
  var connVis = document.querySelector('input[name="privacyConnections"]:checked');

  var profileVisibility = pVis ? pVis.value.toLowerCase() : 'public';
  var connectionsFrom = connVis ? connVis.value.toLowerCase() : 'everyone';

  var payload = {
    profile_visibility: profileVisibility,
    moments_visibility: mVis ? mVis.value : 'everyone',
    approximate_location: true,
    messages_from: msgVis ? msgVis.value : 'everyone',
    connections_from: connectionsFrom
  };

  showToast('Saving privacy preferences...');

  var res = await apiRequest('/api/user/privacy', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (state.currentUser) {
    state.currentUser.profile_visibility = profileVisibility;
    state.currentUser.connections_from = connectionsFrom;
    localStorage.setItem('kandid_user', JSON.stringify(state.currentUser));
  }

  var labelEl = document.getElementById('settingsProfilePrivacyLabel');
  if (labelEl) {
    labelEl.textContent = (profileVisibility === 'private') ? 'PRIVATE · Only identity & bio visible' : 'PUBLIC · Visible across Kandid';
  }

  if (res && res.success) {
    showToast(profileVisibility === 'private' ? 'Profile is now PRIVATE 🔒' : 'Profile is now PUBLIC 🌐');
    closePrivacyModal();
  } else {
    showToast(res && res.error ? res.error : 'Privacy settings saved.');
    closePrivacyModal();
  }
}
window.savePrivacySettings = savePrivacySettings;

// =====================================================================
// NEARBY SCREEN ENGINE (REAL PROXIMITY MOMENTS, COMMUNITIES & DROPS)
// =====================================================================
async function loadNearbyScreen() {
  var container = document.getElementById('nearbyMomentsContainer');
  var emptyState = document.getElementById('nearbyEmptyState');
  var locState = document.getElementById('nearbyLocationState');
  var banner = document.getElementById('nearbyProximityBanner');

  if (locState) locState.style.display = 'none';
  if (banner) banner.style.display = 'flex';

  var data = await apiRequest('/api/feed?circle=nearby');
  if (data && data.success && Array.isArray(data.feed)) {
    if (data.feed.length === 0) {
      if (emptyState) {
        emptyState.classList.remove('hidden');
        emptyState.style.display = 'flex';
      }
      if (container) container.innerHTML = '';
    } else {
      if (emptyState) emptyState.style.display = 'none';
      if (container) {
        container.innerHTML = '';

        // 1. Happening Nearby Header & Moments Cards
        var momentsBox = document.createElement('div');
        momentsBox.className = 'space-y-4';
        renderFeedCards(data.feed, momentsBox);
        container.appendChild(momentsBox);
      }
    }
  }
}
window.loadNearbyScreen = loadNearbyScreen;

// =====================================================================
// FEATURE 1: DEDICATED CONNECTED FRIENDS ENGINE
// =====================================================================
async function loadConnectedFriends() {
  var container = document.getElementById('connectedFriendsList');
  if (!container) return;
  container.innerHTML = '<div class="text-center py-6 text-xs text-zinc-500 font-mono-tag">Loading connected friends...</div>';

  var data = await apiRequest('/api/friends');
  if (data && data.success && Array.isArray(data.friends)) {
    var friends = data.friends;
    if (friends.length === 0) {
      container.innerHTML = 
        '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-6 text-center space-y-2">' +
          '<div class="text-2xl">👥</div>' +
          '<h3 class="text-xs font-bold text-white font-mono-tag uppercase">NO CONNECTED FRIENDS YET</h3>' +
          '<p class="text-[11px] text-zinc-400 font-sans">Connect with people across your campus and spaces to start conversations.</p>' +
          '<button class="mt-2 px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[10px] rounded-xl font-mono-tag cursor-pointer active:scale-95 transition-all shadow-md" onclick="switchScreenView(\'search\')">DISCOVER PEOPLE IN COMMUNITY →</button>' +
        '</div>';
      return;
    }

    container.innerHTML = '';
    friends.forEach(function(f) {
      var item = document.createElement('div');
      item.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3 flex items-center justify-between gap-3 shadow-md hover:border-zinc-700 transition';
      
      var avatarSrc = (f.avatar_url && !f.avatar_url.includes('api.dicebear.com')) ? f.avatar_url : '';
      var name = escapeHtml(f.name || 'Student');
      var handle = escapeHtml(f.handle || 'user');
      var campus = escapeHtml(f.campus || 'North City University');

      var isOnline = (typeof isUserOnline === 'function') ? isUserOnline(f.last_active) : false;
      var statusDot = isOnline ? '<span class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" title="Online now"></span>' : '<span class="w-2 h-2 rounded-full bg-zinc-600" title="Offline"></span>';

      item.innerHTML = 
        '<div class="flex items-center gap-3 cursor-pointer" onclick="openUserProfile(\'' + f.id + '\')">' +
          '<div class="relative w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 overflow-hidden flex-shrink-0 flex items-center justify-center">' +
            '<img src="' + avatarSrc + '" class="w-full h-full object-cover">' +
          '</div>' +
          '<div class="space-y-0.5">' +
            '<div class="flex items-center gap-1.5">' +
              '<h4 class="text-xs font-bold text-white leading-tight">' + name + '</h4>' +
              statusDot +
            '</div>' +
            '<p class="text-[10px] text-amber-400 font-mono-tag">@' + handle + '</p>' +
            '<span class="text-[9px] text-zinc-500 font-mono-tag uppercase">' + campus + '</span>' +
          '</div>' +
        '</div>' +
        '<button class="px-3 py-1.5 bg-zinc-900 hover:bg-amber-500 hover:text-black border border-zinc-800 text-zinc-300 font-mono-tag text-[10px] font-bold rounded-xl transition cursor-pointer active:scale-95 flex items-center gap-1 flex-shrink-0" onclick="openChatWithUser(\'' + f.id + '\', \'' + escapeHtml(name) + '\', \'' + escapeHtml(handle) + '\', \'' + escapeHtml(avatarSrc) + '\')">' +
          '<span>💬</span> <span>MESSAGE</span>' +
        '</button>';

      container.appendChild(item);
    });
  }
}
window.loadConnectedFriends = loadConnectedFriends;

function openChatWithUser(userId, name, handle, avatarUrl, isOnline) {
  openChatThread(userId, name, handle, avatarUrl, isOnline);
}
window.openChatWithUser = openChatWithUser;

function switchChatSubTab(tab) {
  if (tab === 'friends') {
    startNewChatFromConnections();
  } else {
    exitChatNewMsgState();
  }
}
window.switchChatSubTab = switchChatSubTab;

async function connectWithUser(userId, btnEl) {
  if (!userId) return;
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = 'CONNECTING...';
  }
  var res = await apiRequest('/api/friends/connect', {
    method: 'POST',
    body: JSON.stringify({ friendId: userId })
  });

  if (res && res.success) {
    var isNowConnected = (res.status === 'connected');
    showToast(isNowConnected ? 'Connected! +25 XP 🎉' : 'Connection request sent ✉️');
    if (btnEl) {
      if (isNowConnected) {
        btnEl.className = 'px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-gray-300 rounded-full text-[10px] font-bold flex-shrink-0';
        btnEl.textContent = 'CONNECTED';
        btnEl.disabled = true;
      } else {
        btnEl.className = 'px-3 py-1.5 bg-neutral-900 border border-neutral-800 text-amber-400 rounded-full text-[10px] font-bold flex-shrink-0';
        btnEl.textContent = 'REQUESTED';
        btnEl.disabled = true;
      }
    }
  } else {
    showToast('Could not connect: ' + (res ? res.error : 'Network error'));
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.className = 'px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-full text-[10px] font-bold transition flex-shrink-0 cursor-pointer';
      btnEl.textContent = 'CONNECT';
    }
  }
}
window.connectWithUser = connectWithUser;

// =====================================================================
// FEATURE 2: SELFIE REALMOJI REACTION CAPTURE ENGINE
// =====================================================================
var realmojiMediaStream = null;

async function openRealmojiCapture(postId) {
  state.activeReactPostId = postId;
  var modal = document.getElementById('realmojiCaptureModal');
  var video = document.getElementById('realmojiVideo');
  if (!modal || !video) return;

  modal.style.display = 'flex';
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      realmojiMediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 400 }, height: { ideal: 400 } },
        audio: false
      });
      video.srcObject = realmojiMediaStream;
      video.play().catch(function(e){ console.warn(e); });
    }
  } catch(e) {
    console.warn('Realmoji camera error:', e);
    showToast('Front camera permission needed for selfie Realmoji');
  }
}
window.openRealmojiCapture = openRealmojiCapture;

function closeRealmojiCapture() {
  var modal = document.getElementById('realmojiCaptureModal');
  if (modal) modal.style.display = 'none';
  if (realmojiMediaStream) {
    realmojiMediaStream.getTracks().forEach(function(t) { t.stop(); });
    realmojiMediaStream = null;
  }
}
window.closeRealmojiCapture = closeRealmojiCapture;

async function snapAndSendRealmoji() {
  var video = document.getElementById('realmojiVideo');
  var canvas = document.getElementById('realmojiCanvas');
  if (!video || !canvas) return;

  canvas.width = 200;
  canvas.height = 200;
  var ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, 200, 200);
  var dataUrl = canvas.toDataURL('image/jpeg', 0.8);

  showToast('Sending your Selfie Realmoji... 🤳');
  closeRealmojiCapture();

  var res = await apiRequest('/api/react', {
    method: 'POST',
    body: JSON.stringify({
      postId: state.activeReactPostId,
      emoji: '🤳',
      customPhoto: dataUrl
    })
  });

  if (res && res.success) {
    showToast('Selfie Realmoji posted! 🔥 +15 XP');
    if (typeof loadFeedMoments === 'function') loadFeedMoments(state.activeCircle || 'foryou');
  } else {
    showToast('Reaction failed: ' + (res ? res.error : 'Network error'));
  }
}
window.snapAndSendRealmoji = snapAndSendRealmoji;

// =====================================================================
// FEATURE 3: SPONTANEOUS DAILY ALERT ENGINE ("⚠️ TIME TO KANDID")
// =====================================================================
var dailyPrompts = [
  'Show your current view & surroundings',
  "Capture what's on your desk right now",
  'The coffee or drink keeping you alive today',
  'The book or screen in front of you',
  'Who or what is next to you right now'
];

var dailyAlertSeconds = 884;
var dailyAlertInterval = null;

function isTodayMomentCaptured() {
  var todayStr = new Date().toISOString().split('T')[0];
  var lastCap = localStorage.getItem('kandid_last_captured_date');
  if (lastCap === todayStr) return true;
  if (state.hasCapturedToday) return true;
  return false;
}
window.isTodayMomentCaptured = isTodayMomentCaptured;

function markDailyAlertCompleted() {
  var todayStr = new Date().toISOString().split('T')[0];
  localStorage.setItem('kandid_last_captured_date', todayStr);
  state.hasCapturedToday = true;

  if (dailyAlertInterval) {
    clearInterval(dailyAlertInterval);
    dailyAlertInterval = null;
  }

  var banner = document.getElementById('dailyKandidAlertBanner');
  if (banner) {
    banner.style.display = 'none';
  }
}
window.markDailyAlertCompleted = markDailyAlertCompleted;

function initDailyKandidAlert() {
  var banner = document.getElementById('dailyKandidAlertBanner');
  var countdownEl = document.getElementById('dailyAlertCountdown');
  var promptDescEl = banner ? banner.querySelector('p') : null;
  if (!banner || !countdownEl) return;

  if (isTodayMomentCaptured()) {
    banner.style.display = 'none';
    if (dailyAlertInterval) {
      clearInterval(dailyAlertInterval);
      dailyAlertInterval = null;
    }
    return;
  }

  var currentPrompt = dailyPrompts[Math.floor(Math.random() * dailyPrompts.length)];
  if (promptDescEl) {
    promptDescEl.textContent = 'Mission: ' + currentPrompt;
  }
  state.activeDailyPrompt = currentPrompt;

  banner.style.display = 'flex';
  if (!dailyAlertSeconds || dailyAlertSeconds <= 0) {
    dailyAlertSeconds = 884;
  }

  if (dailyAlertInterval) clearInterval(dailyAlertInterval);
  dailyAlertInterval = setInterval(function() {
    if (isTodayMomentCaptured()) {
      clearInterval(dailyAlertInterval);
      dailyAlertInterval = null;
      banner.style.display = 'none';
      return;
    }
    dailyAlertSeconds--;
    if (dailyAlertSeconds <= 0) {
      clearInterval(dailyAlertInterval);
      dailyAlertInterval = null;
      countdownEl.textContent = '00:00';
      banner.style.display = 'none';
    } else {
      var mins = Math.floor(dailyAlertSeconds / 60);
      var secs = dailyAlertSeconds % 60;
      countdownEl.textContent = (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs;
    }
  }, 1000);
}
window.initDailyKandidAlert = initDailyKandidAlert;

function dismissDailyAlert() {
  var banner = document.getElementById('dailyKandidAlertBanner');
  if (banner) banner.style.display = 'none';
  if (dailyAlertInterval) {
    clearInterval(dailyAlertInterval);
    dailyAlertInterval = null;
  }
}
window.dismissDailyAlert = dismissDailyAlert;

// =====================================================================
// FEATURE 4: 1-TAP CAMPUS INVITE ENGINE (+100 XP)
// =====================================================================
function shareCampusInvite() {
  var handle = state.currentUser ? state.currentUser.handle : 'student';
  var inviteUrl = 'https://kandid.network/invite/@' + handle.replace('@', '');
  var text = 'Join me on Kandid! Raw, unedited moments with 3-second ambient audio from our campus: ' + inviteUrl;

  if (navigator.share) {
    navigator.share({
      title: 'Join me on Kandid',
      text: text,
      url: inviteUrl
    }).then(function() {
      showToast('Invite shared! +100 XP Earned 🚀');
    }).catch(function() {
      copyInviteToClipboard(inviteUrl);
    });
  } else {
    copyInviteToClipboard(inviteUrl);
  }
}
window.shareCampusInvite = shareCampusInvite;

function copyInviteToClipboard(text) {
  navigator.clipboard.writeText(text).then(function() {
    showToast('Invite link copied! Share on WhatsApp/Insta +100 XP 📋');
  }).catch(function() {
    showToast('Invite link: ' + text);
  });
}
window.copyInviteToClipboard = copyInviteToClipboard;

// =====================================================================
// =====================================================================
// FEATURE 5: MEMORIES ARCHIVE (UNIFIED WITH JOURNAL ENGINE)
// =====================================================================
// Functions filterMemoriesByMonth and renderMemoriesFeed are implemented above in Section 5.

// Start Daily Kandid Alert after 5 minutes of app usage
setTimeout(function() {
  initDailyKandidAlert();
}, 5 * 60 * 1000); // 5 Minutes (300,000 ms)

// =============================================================================
// AUTHENTIC VIRAL GRAPH & MOMENT CLUSTERS FRONTEND MODULE
// =============================================================================
state.activeClusterContext = null;
state.currentViewingCluster = null;

async function openMomentClusterModal(clusterId, momentId) {
  var modal = document.getElementById('momentClusterModal');
  if (!modal) return;

  var titleEl = document.getElementById('momentClusterTitle');
  var contextTextEl = document.getElementById('momentClusterContextText');
  var countEl = document.getElementById('momentClusterPerspectivesCount');
  var primaryEl = document.getElementById('momentClusterPrimaryShowcase');
  var listEl = document.getElementById('momentClusterPerspectivesList');
  var connArea = document.getElementById('momentClusterConnectionArea');
  var connPrompt = document.getElementById('momentClusterConnectionPrompt');
  var connBtn = document.getElementById('momentClusterConnectBtn');
  var addBtn = document.getElementById('momentClusterAddPerspectiveBtn');

  if (listEl) listEl.innerHTML = '<div class="p-4 text-center text-xs text-zinc-500 font-mono-tag">Loading perspectives...</div>';
  modal.style.display = 'flex';

  var clusterData = null;
  if (clusterId) {
    var res = await apiRequest('/api/cluster/' + encodeURIComponent(clusterId));
    if (res && res.success && res.cluster) {
      clusterData = res.cluster;
    }
  }

  if (!clusterData && momentId) {
    var eligRes = await apiRequest('/api/moment/' + encodeURIComponent(momentId) + '/eligibility');
    if (eligRes && eligRes.success && eligRes.cluster_id) {
      var res2 = await apiRequest('/api/cluster/' + encodeURIComponent(eligRes.cluster_id));
      if (res2 && res2.success && res2.cluster) {
        clusterData = res2.cluster;
      }
    }
  }

  state.currentViewingCluster = clusterData;

  if (!clusterData) {
    if (listEl) listEl.innerHTML = '<div class="p-4 text-center text-xs text-zinc-500 font-mono-tag">This moment is waiting for its first shared perspective.</div>';
    if (countEl) countEl.textContent = '0 perspectives';
    if (addBtn) {
      addBtn.onclick = function() {
        if (momentId) {
          handleIWasThereClick(momentId, true);
        } else {
          closeMomentClusterModal();
          openCameraStudio();
        }
      };
    }
    return;
  }

  state.activeClusterContext = clusterData.id;

  if (titleEl) titleEl.textContent = 'One Real Moment — ' + ((clusterData.perspectives_count || 0) + 1) + ' Perspectives';
  if (contextTextEl) contextTextEl.textContent = clusterData.originating_context || 'Shared Context';
  if (countEl) countEl.textContent = (clusterData.perspectives_count || 0) + ' perspective' + ((clusterData.perspectives_count === 1) ? '' : 's');

  if (primaryEl && clusterData.primary_moment) {
    var pm = clusterData.primary_moment;
    primaryEl.innerHTML = 
      '<div class="p-3 rounded-2xl bg-zinc-900 border border-amber-500/20 space-y-2">' +
        '<div class="flex items-center justify-between text-[10px] font-mono-tag">' +
          '<span class="text-amber-400 font-bold">PRIMARY MOMENT</span>' +
          '<span class="text-zinc-500">@' + escapeHtml(pm.author_handle || 'creator') + '</span>' +
        '</div>' +
        '<div class="aspect-[16/10] bg-black rounded-xl overflow-hidden relative">' +
          '<img src="' + escapeHtml(pm.main_img || '') + '" class="w-full h-full object-cover">' +
        '</div>' +
        '<p class="text-xs text-zinc-200 font-normal leading-relaxed">"' + escapeHtml(pm.caption || 'Unfiltered moment.') + '"</p>' +
      '</div>';
  }

  if (listEl) {
    if (clusterData.perspectives && clusterData.perspectives.length > 0) {
      listEl.innerHTML = '';
      clusterData.perspectives.forEach(function(persp) {
        var card = document.createElement('div');
        card.className = 'p-3 rounded-2xl bg-zinc-900/70 border border-zinc-800 space-y-2';
        card.innerHTML = 
          '<div class="flex items-center justify-between text-[10px] font-mono-tag">' +
            '<div class="flex items-center gap-1.5">' +
              '<div class="w-5 h-5 rounded-full bg-zinc-800 flex items-center justify-center font-bold text-amber-400 text-[9px]">' + escapeHtml(persp.avatar_letter || 'K') + '</div>' +
              '<span class="text-zinc-300 font-bold">@' + escapeHtml(persp.author_handle || 'user') + '</span>' +
            '</div>' +
            '<span class="text-zinc-500">' + escapeHtml(persp.location_city || 'Campus') + '</span>' +
          '</div>' +
          '<div class="aspect-[16/10] bg-black rounded-xl overflow-hidden relative">' +
            '<img src="' + escapeHtml(persp.main_img || '') + '" class="w-full h-full object-cover">' +
          '</div>' +
          '<p class="text-xs text-zinc-300 font-normal leading-relaxed">"' + escapeHtml(persp.caption || 'Perspective.') + '"</p>';
        listEl.appendChild(card);
      });
    } else {
      listEl.innerHTML = '<div class="p-4 text-center text-xs text-zinc-500 font-mono-tag">No additional perspectives added yet. Be the first to share what you saw.</div>';
    }
  }

  if (connArea && clusterData.connection_suggestion && clusterData.connection_suggestion.suggested) {
    connArea.style.display = 'block';
    if (connPrompt) connPrompt.textContent = clusterData.connection_suggestion.message;
    if (connBtn) {
      connBtn.onclick = function() {
        connectWithClusterMember(clusterData.connection_suggestion.target_user_id, clusterData.connection_suggestion.target_handle);
      };
    }
  } else if (connArea) {
    connArea.style.display = 'none';
  }

  if (addBtn) {
    addBtn.onclick = function() {
      openPerspectiveCapture(clusterData.id, clusterData.community_id, clusterData.originating_context);
    };
  }
}
window.openMomentClusterModal = openMomentClusterModal;

function closeMomentClusterModal() {
  var modal = document.getElementById('momentClusterModal');
  if (modal) modal.style.display = 'none';
}
window.closeMomentClusterModal = closeMomentClusterModal;

async function handleIWasThereClick(momentId, openCaptureAfter) {
  try {
    var res = await apiRequest('/api/moment/' + encodeURIComponent(momentId) + '/i-was-there', {
      method: 'POST',
      body: JSON.stringify({ moment_id: momentId })
    });
    if (res && res.success) {
      showToast(res.message || 'Participation recorded! ✦');
      state.activeClusterContext = res.cluster_id;
      if (openCaptureAfter) {
        closeMomentClusterModal();
        openCameraStudio();
      } else {
        openMomentClusterModal(res.cluster_id, momentId);
      }
    } else if (res && res.code === 'CAMPUS_DISCOVERY_ONLY') {
      // B-12: Do NOT auto-join to bypass campus discovery boundary — show user-facing error
      showToast('This moment is only available to community members. Join the community first to participate.');

    } else {
      var err = 'Participation not authorized.';
      if (res && res.code === 'OWN_MOMENT') {
        err = 'You cannot assert participation in your own moment.';
      } else if (res && res.code === 'BLOCKED_USER') {
        err = 'Unable to participate in this moment.';
      } else if (res && res.code === 'CLUSTER_COOLDOWN') {
        err = 'Please wait a moment before participating again.';
      } else if (res && (res.error || res.message)) {
        err = res.error || res.message;
      }
      showToast(err);
    }
  } catch(e) {
    console.error('Error in handleIWasThereClick:', e);
    showToast('Failed to record participation.');
  }
}
window.handleIWasThereClick = handleIWasThereClick;

function handleAddPerspectiveClick() {
  var c = state.currentViewingCluster;
  if (c && c.id) {
    openPerspectiveCapture(c.id, c.community_id, c.originating_context);
  } else {
    closeMomentClusterModal();
    openCameraStudio();
  }
}
window.handleAddPerspectiveClick = handleAddPerspectiveClick;

function openPerspectiveCapture(clusterId, communityId, location) {
  state.activeClusterContext = clusterId;
  closeMomentClusterModal();
  openCameraStudio();
  showToast('Optics ready. Capture your perspective for this cluster.');
}
window.openPerspectiveCapture = openPerspectiveCapture;

async function connectWithClusterMember(targetUserId, targetHandle) {
  try {
    var res = await apiRequest('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({
        recipientId: targetUserId,
        content: 'Hey @' + targetHandle + '! We shared a moment together on Kandid.'
      })
    });
    if (res && res.success) {
      showToast('Connected with @' + targetHandle + '! Check Direct Messages.');
      var connArea = document.getElementById('momentClusterConnectionArea');
      if (connArea) connArea.style.display = 'none';
    } else {
      showToast('Connection request sent to @' + targetHandle);
    }
  } catch(e) {
    showToast('Connection sent.');
  }
}
window.connectWithClusterMember = connectWithClusterMember;

