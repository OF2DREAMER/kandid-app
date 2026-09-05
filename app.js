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

var MOCK_DATA = {
  feed: [
    {
      id: 'post_maya_1',
      author_handle: 'maya_s',
      user_name: 'Maya Sharma',
      avatar_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=80&q=80',
      campus: 'North Block Quad',
      timeAgo: '14 MIN AGO',
      caption: 'Late afternoon coffee break between lectures at the quad.',
      main_img: 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 400',
      exif_aperture: 'F/2.8',
      exif_shutter: '1/250S',
      circle: 'foryou',
      realmojis: { '🔥': 5, '☕': 3 }
    },
    {
      id: 'post_alex_1',
      author_handle: 'alex_k',
      user_name: 'Alex Rivera',
      avatar_url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=80&q=80',
      campus: 'North Block Library Wing',
      timeAgo: '24 MIN AGO',
      caption: 'Quiet corner in the library wing finishing architecture drafts.',
      main_img: 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 200',
      exif_aperture: 'F/4.0',
      exif_shutter: '1/125S',
      circle: 'campus',
      realmojis: { '⚡': 4, '👏': 2 }
    },
    {
      id: 'post_rohit_2',
      author_handle: 'rohit_sharma',
      user_name: 'Rohit Sharma',
      avatar_url: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=80&q=80',
      campus: 'Courtyard Steps',
      timeAgo: '42 MIN AGO',
      caption: 'Sunset lighting hits the courtyard stairs perfectly today.',
      main_img: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 640',
      exif_aperture: 'F/2.0',
      exif_shutter: '1/320S',
      circle: 'campus',
      realmojis: { '🔥': 7, '❤️': 3 }
    }
  ],
  global: [
    {
      id: 'post_hana_1',
      author_handle: 'hana_k',
      location_city: 'TOKYO',
      location_coords: '35.6762° N',
      timeAgo: '18 MIN AGO',
      caption: 'Evening crossing after lab work in Shibuya.',
      main_img: 'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 800',
      exif_shutter: '1/125S',
      region: 'asia',
      realmojis: { '🔥': 9, '⚡': 4 }
    },
    {
      id: 'post_arjun_2',
      author_handle: 'arjun_m',
      location_city: 'DELHI',
      location_coords: '28.6139° N',
      timeAgo: '35 MIN AGO',
      caption: 'Dusk settling over South Campus lawn.',
      main_img: 'https://images.unsplash.com/photo-1587474260584-136574528ed5?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 500',
      exif_shutter: '1/200S',
      region: 'asia',
      realmojis: { '☕': 6, '❤️': 5 }
    },
    {
      id: 'post_mia_3',
      author_handle: 'mia_r',
      location_city: 'LONDON',
      location_coords: '51.5074° N',
      timeAgo: '1 HR AGO',
      caption: 'Last train back after a long library shift.',
      main_img: 'https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=600&q=80',
      pip_img: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=200&q=80',
      exif_iso: 'ISO 320',
      exif_shutter: '1/160S',
      region: 'europe',
      realmojis: { '🔥': 4, '👏': 3 }
    }
  ],
  conversations: [
    {
      id: 'u_maya',
      name: 'Maya Sharma',
      handle: 'maya_s',
      avatar_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=80&q=80',
      lastMessage: 'Are we heading to the union library later?'
    },
    {
      id: 'u_alex',
      name: 'Alex Rivera',
      handle: 'alex_k',
      avatar_url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=80&q=80',
      lastMessage: 'Check out the new moment from the north wing.'
    },
    {
      id: 'u_rohit',
      name: 'Rohit Sharma',
      handle: 'rohit_sharma',
      avatar_url: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=80&q=80',
      lastMessage: 'Cultural night starts in 30 minutes!'
    },
    {
      id: 'u_sarebaj',
      name: 'Sarebaj Farsi',
      handle: 'sarebaj_solvarionx',
      avatar_url: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&q=80',
      lastMessage: 'Welcome to Kandid Beta! Keep it authentic.'
    }
  ],
  messages: {
    u_maya: [
      { id: 'm1', sender_id: 'u_maya', content: 'Hey Casey! Did you capture your moment today?' },
      { id: 'm2', sender_id: 'u_casey', content: 'Yes! Just posted near the quad.' },
      { id: 'm3', sender_id: 'u_maya', content: 'Are we heading to the union library later?' }
    ],
    u_alex: [
      { id: 'm4', sender_id: 'u_alex', content: 'Check out the new moment from the north wing.' }
    ],
    u_rohit: [
      { id: 'm5', sender_id: 'u_rohit', content: 'Cultural night starts in 30 minutes!' }
    ],
    u_sarebaj: [
      { id: 'm6', sender_id: 'u_sarebaj', content: 'Welcome to Kandid Beta! Keep it authentic.' }
    ]
  },
  notifications: [
    { id: 'n1', title: 'MOMENT WINDOW OPEN', body: 'You have 14 minutes to capture your raw daily perspective.', is_read: 0 },
    { id: 'n2', title: 'NEW REACTION', body: '@maya_s reacted 🔥 to your North Quad moment.', is_read: 1 },
    { id: 'n3', title: 'COMMUNITY LIVE', body: 'Cultural Night is live now at North City auditorium.', is_read: 1 }
  ]
};

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
  if (!activeUid) {
    activeUid = 'u_80bef710';
    localStorage.setItem('kandid_active_uid', activeUid);
  }
  return activeUid;
}
window.getActiveUserId = getActiveUserId;

async function apiRequest(endpoint, options) {
  options = options || {};
  var headers = options.headers || {};
  headers['Content-Type'] = 'application/json';
  if (state.token && state.token !== 'null' && state.token !== 'undefined') {
    headers['Authorization'] = 'Bearer ' + state.token;
  }
  var uid = getActiveUserId();
  if (uid) {
    headers['X-User-Id'] = uid;
  }
  options.headers = headers;

  try {
    var res = await fetch(endpoint, options);
    var data = await res.json();
    return data;
  } catch (err) {
    // Offline / local file / network fallback
    if (endpoint.indexOf('/api/feed') !== -1) {
      return { success: true, feed: MOCK_DATA.feed };
    }
    if (endpoint.indexOf('/api/campus') !== -1) {
      return {
        success: true,
        campus: { name: 'North City University', activeMetric: '2.4K ACTIVE THIS WEEK' },
        liveEvents: [{ name: 'CULTURAL NIGHT', summary: '12 moments captured around the auditorium.' }],
        moments: MOCK_DATA.feed.filter(function(m) { return m.circle === 'campus'; })
      };
    }
    if (endpoint.indexOf('/api/global') !== -1) {
      var regMatch = endpoint.match(/region=([^&]+)/);
      var reg = regMatch ? regMatch[1] : 'all';
      var moments = (reg === 'all') ? MOCK_DATA.global : MOCK_DATA.global.filter(function(m) { return m.region === reg; });
      return { success: true, moments: moments };
    }
    if (endpoint.indexOf('/api/chat/conversations') !== -1) {
      return { success: true, conversations: MOCK_DATA.conversations };
    }
    if (endpoint.indexOf('/api/chat/messages') !== -1) {
      var chatIdMatch = endpoint.match(/chat_id=([^&]+)/);
      var cId = chatIdMatch ? chatIdMatch[1] : 'u_maya';
      return { success: true, messages: MOCK_DATA.messages[cId] || [] };
    }
    if (endpoint.indexOf('/api/chat/send') !== -1) {
      if (options.body) {
        var body = JSON.parse(options.body);
        if (!MOCK_DATA.messages[body.receiverId]) MOCK_DATA.messages[body.receiverId] = [];
        MOCK_DATA.messages[body.receiverId].push({ id: 'm_' + Date.now(), sender_id: state.currentUser.id, content: body.content });
      }
      return { success: true };
    }
    if (endpoint.indexOf('/api/search') !== -1) {
      return {
        success: true,
        activeNodes: 1,
        sectors: [],
        frequencies: [],
        people: [],
        places: [],
        moments: []
      };
    }
    if (endpoint.indexOf('/api/me/moments') !== -1) {
      return { success: true, moments: MOCK_DATA.feed };
    }
    if (endpoint.indexOf('/api/me/memories') !== -1) {
      return { success: true, count: 42, memories: MOCK_DATA.feed };
    }
    if (endpoint.indexOf('/api/me') !== -1) {
      return {
        success: true,
        user: {
          id: state.currentUser.id,
          name: state.currentUser.name,
          handle: state.currentUser.handle,
          campus: state.currentUser.campus,
          streak: 12,
          momentsCount: 86,
          memoriesCount: 42,
          bio: 'Documenting campus life through 50mm candid frames.'
        }
      };
    }
    if (endpoint.indexOf('/api/notifications/read-all') !== -1) {
      MOCK_DATA.notifications.forEach(function(n) { n.is_read = 1; });
      return { success: true };
    }
    if (endpoint.indexOf('/api/notifications') !== -1) {
      var unread = MOCK_DATA.notifications.filter(function(n) { return n.is_read === 0; }).length;
      return { success: true, unreadCount: unread, notifications: MOCK_DATA.notifications };
    }
    if (endpoint.indexOf('/api/moments/capture') !== -1) {
      return { success: true, message: 'Captured moment saved' };
    }
    return { success: false, error: err.message };
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
    var timeAgo = escapeHtml((m.timeAgo || m.time_ago || '18 MIN AGO').toUpperCase());
    var captionText = escapeHtml(m.caption || 'Real moment across global coordinates.');
    var iso = escapeHtml(m.exif_iso || 'ISO 400');
    var shutter = escapeHtml(m.exif_shutter || '1/250S');

    var avatarSrc = m.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=80&q=80';
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

    var mainImgSrc = m.main_img || m.mainImg || 'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?auto=format&fit=crop&w=600&q=80';
    var pipImgSrc = m.pip_img || m.pipImg || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80';

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
        '<div class="flex justify-between items-center text-[10px] text-zinc-400 font-mono-tag font-bold tracking-wider">' +
          '<span>' + locBanner + '</span>' +
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

  document.querySelectorAll('.app-screen').forEach(function(scr) {
    scr.classList.remove('active');
    scr.style.display = 'none';
  });

  var target = document.getElementById('screen-' + screenName);
  if (target) {
    target.classList.add('active');
    if (screenName.startsWith('chat-') || screenName === 'empty-search' || screenName === 'error' || screenName === 'offline' || screenName === 'block' || screenName === 'report' || screenName.includes('confirm')) {
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
      if (screenName === "event-detail") { statusMode.textContent = "LIVE EVENT"; } else { statusMode.textContent = screenName.toUpperCase(); }
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
  }



  var globalHeader = document.getElementById("mainGlobalHeader");
  var eventHeader = document.getElementById("eventDetailHeader");
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
    if (eventHeader) eventHeader.style.display = "none";
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
    
    if (screenName === "event-detail") {
      if (eventHeader) eventHeader.style.display = "flex";
    } else if (screenName === "settings") {
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
      if (headerChatHome) headerChatHome.style.display = "flex";
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
    } else if (screenName === "chat-settings") {
      if (headerChatSettings) headerChatSettings.style.display = "flex";
      statusText = "SETTINGS";
    } else if (screenName === "peer-profile") {
      if (headerPeerProfile) headerPeerProfile.style.display = "flex";
      statusText = "USER PROFILE";
    } else if (screenName === "campus-page") {
      var headerCampus = document.getElementById("headerCampusPage");
      if (headerCampus) headerCampus.style.display = "flex";
      statusText = "COMMUNITY";
    } else if (screenName === "collective-memory") {
      statusText = "COLLECTIVE MEMORY";
    } else if (screenName === "live-pulse") {
      statusText = "LIVE PULSE";
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
    if (screenName === "collective-memory" || screenName === "live-pulse" || screenName === "chat-conversation" || screenName === "chat-shared") {
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

  if (typeof loadCommunityDrops === 'function') {
    loadCommunityDrops(currentComm);
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
    var timeAgo = escapeHtml(m.timeAgo || m.time_ago || '8m ago');
    var captionText = escapeHtml(m.caption || 'Unfiltered moment.');
    var locName = escapeHtml(m.location_city || m.campus || 'Near Quad');
    if (!locName.toLowerCase().startsWith('near ')) locName = 'Near ' + locName;

    var avatarLetter = (m.author_name || authorHandle).substring(0, 2).toUpperCase();

    var mainImgSrc = m.main_img || m.mainImg || 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=900&q=85';
    var pipImgSrc = m.pip_img || m.pipImg || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80';

    var dropContextHtml = m.drop_context ? ('<span class="font-mono-tag text-[8px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-full border border-amber-500/30 uppercase font-bold tracking-wider">FROM THIS DROP</span>') : '';

    var clusterBadgeHtml = '';
    if (m.cluster_id || (m.perspectives_count && m.perspectives_count > 0)) {
      var pCount = m.perspectives_count || 1;
      clusterBadgeHtml = '<button onclick="event.stopPropagation(); openMomentClusterModal(\'' + (m.cluster_id || '') + '\', \'' + m.id + '\')" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-[9px] font-mono-tag font-bold text-amber-400 transition cursor-pointer active:scale-95 shadow-sm">' +
        '<span>✦</span> <span>' + pCount + ' perspective' + (pCount === 1 ? '' : 's') + '</span>' +
      '</button>';
    }

    var iWasThereHtml = '';
    var hasSharedContext = !!(m.primary_community_id || m.context_community_id || m.drop_id || m.cluster_id);
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
          '<span class="font-mono-tag text-[9px] text-white/90 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/15">' +
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
            '<div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl location-chip bg-black/60 backdrop-blur-md border border-white/10">' +
              '<span class="text-amber-400 text-xs">⌖</span>' +
              '<span class="text-[10px] text-zinc-200 font-medium">' + locName + '</span>' +
            '</div>' +
            dropContextHtml +
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
      if (nameEl) nameEl.textContent = c.name;
      if (typeTagEl) typeTagEl.textContent = '◉ ' + (c.tag || 'COMMUNITY HUB');
      if (locEl) locEl.textContent = (c.location || 'Local Region') + (c.creator_handle ? ' · Created by @' + c.creator_handle : '');
      if (descEl) descEl.textContent = c.description || 'Authentic moments and shared daily life.';

      if (joinBtn) {
        if (c.type === 'Interest') {
          if (c.is_joined) {
            joinBtn.textContent = '[ JOINED ✓ ]';
            joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-zinc-800 text-zinc-300 font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition cursor-pointer';
          } else {
            joinBtn.textContent = '[ + JOIN COMMUNITY ]';
            joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition shadow-lg cursor-pointer';
          }
        } else if (c.type === 'Place') {
          joinBtn.textContent = '[ ENTER SPACE ]';
          joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition shadow-lg cursor-pointer';
        } else {
          joinBtn.textContent = '[ PRIMARY COMMUNITY ]';
          joinBtn.className = 'mt-2 w-full py-2.5 rounded-xl bg-zinc-800 text-amber-400 font-extrabold text-xs font-mono-tag uppercase active:scale-95 transition cursor-pointer';
        }
      }

      // Creator Ownership Controls Visibility
      var creatorControls = document.getElementById('campusPageCreatorControls');
      if (creatorControls) {
        var myId = state.currentUser ? state.currentUser.id : '';
        var myHandle = state.currentUser ? state.currentUser.handle : '';
        var isCreator = (c.creator_id && c.creator_id === myId) || 
                        (c.creator_handle && c.creator_handle === myHandle) || 
                        (state.currentUser && state.currentUser.role === 'admin') ||
                        (c.creator_id === 'u_system'); // Allow admin access
        creatorControls.style.display = isCreator ? 'flex' : 'none';
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

    // Load Community Drops (Prioritized Experiences)
    loadCommunityDrops(campusName);

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
          if (attendedEl && ctxRes.participation) {
            attendedEl.textContent = (ctxRes.participation.drops_attended || 0) + ' drops';
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
              '<img src="' + (p.main_img || 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=200&q=80') + '" class="w-full h-full object-cover">' +
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
          var attendeeTxt = attendeeCount > 0 ? (attendeeCount + ' people were there') : 'Archived experience';
          var dropContextTag = m.drop_context ? '<span class="font-mono-tag text-[7px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1 py-0.5 rounded block truncate">FROM THIS EXPERIENCE</span>' : '';
          return '<div onclick="openCollectiveMemoryPage(\'' + (m.id || 'mem_1') + '\')" class="p-3 rounded-2xl bg-zinc-950 border border-white/[.07] hover:border-amber-500/40 space-y-2 shadow-md cursor-pointer transition active:scale-95 group">' +
            '<div class="w-full aspect-[4/3] rounded-xl overflow-hidden bg-black">' +
              '<img src="' + (m.cover_img || m.cover_image || 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=400&q=80') + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
            '</div>' +
            '<p class="text-xs font-bold text-white truncate group-hover:text-amber-400 transition-colors">' + escapeHtml(m.title) + '</p>' +
            dropContextTag +
            '<p class="font-mono-tag text-[8px] text-zinc-400">' + attendeeTxt + '</p>' +
          '</div>';
        }).join('');
      } else {
        memoriesGridEl.innerHTML = '<div class="col-span-2 py-6 text-center text-xs text-zinc-500 font-mono-tag">No preserved memories yet. Real-world drops become memories here.</div>';
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

// =====================================================================
// COMMUNITY DROPS & EXPERIENCES SYSTEM (₹19 MONETIZATION ENGINE)
// =====================================================================
function getDropStateInfo(stateStr) {
  var s = (stateStr || 'SCHEDULED').toUpperCase();
  switch (s) {
    case 'DRAFT':
      return { label: 'DRAFT', badgeClass: 'bg-zinc-800 text-zinc-400 border-zinc-700', dotClass: 'bg-zinc-500' };
    case 'SCHEDULED':
      return { label: 'UPCOMING', badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30', dotClass: 'bg-amber-500' };
    case 'REMINDER':
      return { label: 'STARTING SOON', badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse', dotClass: 'bg-amber-400' };
    case 'LIVE':
      return { label: 'LIVE NOW', badgeClass: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 animate-pulse', dotClass: 'bg-emerald-500' };
    case 'CHECK_IN':
      return { label: 'CHECK-IN OPEN', badgeClass: 'bg-blue-500/20 text-blue-400 border-blue-500/40', dotClass: 'bg-blue-400' };
    case 'ACTIVE':
      return { label: 'HAPPENING NOW', badgeClass: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40', dotClass: 'bg-emerald-500' };
    case 'CLOSED':
      return { label: 'CLOSED', badgeClass: 'bg-zinc-900 text-zinc-500 border-zinc-800', dotClass: 'bg-zinc-600' };
    case 'SETTLEMENT':
      return { label: 'PROCESSING', badgeClass: 'bg-zinc-900 text-zinc-500 border-zinc-800', dotClass: 'bg-zinc-600' };
    case 'MEMORY':
      return { label: 'MEMORY', badgeClass: 'bg-purple-500/10 text-purple-400 border-purple-500/30', dotClass: 'bg-purple-400' };
    default:
      return { label: 'UPCOMING', badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30', dotClass: 'bg-amber-500' };
  }
}

async function loadCommunityDrops(communityName) {
  communityName = communityName || state.activeCommunity || (state.currentUser ? state.currentUser.campus : 'North City University');
  var hubContainer = document.getElementById('campusPageDropsContainer');
  var feedContainer = document.getElementById('feedCommunityDropsContainer');

  var res = await apiRequest('/api/community/drops?community=' + encodeURIComponent(communityName));
  if (!res || !res.success || !Array.isArray(res.drops)) return;

  state.communityDrops = res.drops;

  var renderDropCard = function(d) {
    var spotsLeft = Math.max(0, (d.capacity || 20) - (d.registered_count || 0));
    var isRegistered = !!d.is_registered;
    var stateInfo = getDropStateInfo(d.state);
    var isLiveOrCheckin = ['CHECK_IN', 'LIVE', 'ACTIVE'].indexOf(d.state) !== -1;
    var isEnded = ['CLOSED', 'SETTLEMENT', 'MEMORY'].indexOf(d.state) !== -1;

    var btnHtml = '';
    if (isRegistered) {
      if (isLiveOrCheckin) {
        if (d.is_checked_in) {
          btnHtml = '<button disabled class="px-3 py-1.5 rounded-xl bg-emerald-500/20 text-emerald-400 font-mono-tag text-[10px] font-bold border border-emerald-500/40 cursor-default flex items-center gap-1"><span>CHECKED IN ✓</span></button>';
        } else {
          btnHtml = '<button onclick="event.stopPropagation(); checkinCommunityDrop(\'' + d.id + '\', this)" class="px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-mono-tag text-[10px] font-extrabold uppercase tracking-wider cursor-pointer active:scale-95 transition shadow-sm">CHECK IN</button>';
        }
      } else if (d.state === 'MEMORY') {
        btnHtml = '<button onclick="event.stopPropagation(); openDropDetail(\'' + d.id + '\')" class="px-3 py-1.5 rounded-xl bg-purple-500/20 text-purple-300 font-mono-tag text-[10px] font-bold border border-purple-500/40 cursor-pointer">VIEW MEMORY</button>';
      } else {
        btnHtml = '<button onclick="event.stopPropagation(); openDropDetail(\'' + d.id + '\')" class="px-3 py-1.5 rounded-xl bg-amber-500/20 text-amber-400 font-mono-tag text-[10px] font-bold border border-amber-500/40 cursor-pointer flex items-center gap-1"><span>YOU\'RE IN ✓</span></button>';
      }
    } else {
      if (isEnded) {
        btnHtml = '<button disabled class="px-3 py-1.5 rounded-xl bg-zinc-900 text-zinc-600 font-mono-tag text-[10px] font-bold border border-zinc-800 cursor-not-allowed">CLOSED</button>';
      } else if (spotsLeft <= 0) {
        btnHtml = '<button disabled class="px-3 py-1.5 rounded-xl bg-zinc-900 text-zinc-500 font-mono-tag text-[10px] font-bold border border-zinc-800 cursor-not-allowed">FULL</button>';
      } else {
        btnHtml = '<button onclick="event.stopPropagation(); startDropOrderFlow(\'' + d.id + '\')" class="px-3.5 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-mono-tag text-[10px] font-extrabold uppercase tracking-wider cursor-pointer active:scale-95 transition shadow-sm">JOIN FOR ₹' + (d.price || 19) + '</button>';
      }
    }

    var coverHtml = (d.cover_img || d.image_url) ? 
      ('<div class="w-full aspect-[16/9] rounded-xl overflow-hidden bg-black mb-2">' +
        '<img src="' + escapeHtml(d.cover_img || d.image_url) + '" class="w-full h-full object-cover">' +
      '</div>') : '';

    var contextBadge = d.contextual_label ? ('<span class="font-mono-tag text-[8px] bg-amber-500/10 text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded font-bold uppercase tracking-wider">' + escapeHtml(d.contextual_label) + '</span>') : '';
    var coordBadge = (isRegistered && d.coordination_status) ? ('<span class="font-mono-tag text-[8px] text-emerald-400 font-bold bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded">' + escapeHtml(d.coordination_status) + '</span>') : '';

    return '<div onclick="openDropDetail(\'' + d.id + '\')" class="p-3.5 rounded-2xl bg-zinc-950 border border-white/[.07] hover:border-amber-500/30 space-y-2.5 shadow-xl transition cursor-pointer">' +
      coverHtml +
      '<div class="flex justify-between items-start">' +
        '<div class="space-y-0.5">' +
          '<div class="flex items-center gap-2 flex-wrap">' +
            '<span class="w-1.5 h-1.5 rounded-full ' + stateInfo.dotClass + '"></span>' +
            '<span class="font-mono-tag text-[9px] ' + stateInfo.badgeClass + ' font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border">' + stateInfo.label + '</span>' +
            contextBadge +
            coordBadge +
            '<span class="font-mono-tag text-[9px] text-zinc-400 font-bold uppercase tracking-wider">' + escapeHtml(d.date_str || 'This Weekend') + ' · ' + escapeHtml(d.time_str || '6:00 PM') + '</span>' +
          '</div>' +
          '<h3 class="text-xs font-extrabold text-white pt-1">' + escapeHtml(d.title) + '</h3>' +
        '</div>' +
        '<span class="font-mono-tag text-[9px] font-bold bg-zinc-900 border border-zinc-800 text-zinc-300 px-2 py-0.5 rounded">₹' + (d.price || 19) + '</span>' +
      '</div>' +
      (d.description ? '<p class="text-[11px] text-zinc-400 font-sans leading-relaxed line-clamp-2">' + escapeHtml(d.description) + '</p>' : '') +
      '<div class="pt-1 flex items-center justify-between border-t border-zinc-900">' +
        '<span class="font-mono-tag text-[9px] text-zinc-500">' + spotsLeft + ' spots remaining (' + (d.registered_count || 0) + ' registered)</span>' +
        btnHtml +
      '</div>' +
    '</div>';
  };

  var cardsHtml = res.drops.map(renderDropCard).join('');
  if (hubContainer) {
    hubContainer.innerHTML = cardsHtml || '<div class="py-8 text-center space-y-1"><p class="text-xs font-bold text-zinc-400 font-mono-tag uppercase tracking-wider">No upcoming experiences yet.</p><p class="text-[11px] text-zinc-500 font-sans">Experiences will appear here as they are planned.</p></div>';
  }
  if (feedContainer) {
    feedContainer.innerHTML = cardsHtml || '<div class="py-4 text-center text-xs text-zinc-500 font-mono-tag">No active community drops.</div>';
  }
}
window.loadCommunityDrops = loadCommunityDrops;

function openDropDetail(dropId) {
  var drops = state.communityDrops || [];
  var d = drops.find(function(x) { return x.id === dropId; });
  if (!d) return;

  var modal = document.getElementById('dropDetailModal');
  if (!modal) return;

  var stateInfo = getDropStateInfo(d.state);
  var badgeEl = document.getElementById('dropDetailStateBadge');
  var commEl = document.getElementById('dropDetailCommunity');
  var titleEl = document.getElementById('dropDetailTitle');
  var dateTimeEl = document.getElementById('dropDetailDateTime');
  var spotsEl = document.getElementById('dropDetailSpots');
  var descEl = document.getElementById('dropDetailDesc');
  var hostHandleEl = document.getElementById('dropDetailHostHandle');
  var hostAvatarEl = document.getElementById('dropDetailHostAvatar');
  var priceEl = document.getElementById('dropDetailPriceTxt');
  var actionContainer = document.getElementById('dropDetailActionContainer');
  var coordSec = document.getElementById('dropDetailCoordinationSection');
  var coordStatus = document.getElementById('dropDetailCoordStatus');
  var coordVenue = document.getElementById('dropDetailCoordVenue');
  var coordInstr = document.getElementById('dropDetailCoordInstructions');

  var spotsLeft = Math.max(0, (d.capacity || 20) - (d.registered_count || 0));

  if (badgeEl) {
    badgeEl.textContent = stateInfo.label;
    badgeEl.className = 'font-mono-tag text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ' + stateInfo.badgeClass;
  }
  if (commEl) commEl.textContent = d.community_name || state.activeCommunity || 'Community';
  if (titleEl) titleEl.textContent = d.title || 'Community Experience';
  if (dateTimeEl) dateTimeEl.textContent = (d.date_str || 'This Weekend') + ' · ' + (d.time_str || '6:00 PM');
  if (spotsEl) spotsEl.textContent = spotsLeft + ' spots left (' + (d.registered_count || 0) + ' registered)';
  if (descEl) descEl.textContent = d.description || 'Join this live verified shared moment with members of the community.';
  if (hostHandleEl) hostHandleEl.textContent = '@' + (d.host_handle || d.created_by || 'kandid');
  if (hostAvatarEl) hostAvatarEl.textContent = ((d.host_handle || d.created_by || 'K')[0] || 'K').toUpperCase();
  if (priceEl) priceEl.textContent = '₹' + (d.price || 19).toFixed(2);

  var isRegistered = !!d.is_registered;
  var isLiveOrCheckin = ['CHECK_IN', 'LIVE', 'ACTIVE'].indexOf(d.state) !== -1;
  var isEnded = ['CLOSED', 'SETTLEMENT', 'MEMORY'].indexOf(d.state) !== -1;

  // Phase 17: Attendee Coordination Context
  if (coordSec) {
    if (isRegistered) {
      coordSec.style.display = 'block';
      if (coordStatus) {
        coordStatus.textContent = d.is_checked_in ? 'Checked In ✓' : (isLiveOrCheckin ? 'Check-in Ready' : 'Spot Confirmed');
      }
      if (coordVenue) {
        var vname = d.location_name || d.area || d.community_name || 'Campus Community Area';
        coordVenue.innerHTML = '<span class="text-amber-400">📍</span> <span>' + escapeHtml(vname) + '</span>';
      }
      if (coordInstr) {
        var hhandle = d.host_handle || d.created_by || 'kandid';
        coordInstr.textContent = 'Meet host @' + hhandle + ' at the venue. Check in on your device to confirm presence.';
      }
    } else {
      coordSec.style.display = 'none';
    }
  }

  if (actionContainer) {
    if (isRegistered) {
      if (isLiveOrCheckin) {
        if (d.is_checked_in) {
          actionContainer.innerHTML = '<button disabled class="w-full py-3.5 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-default flex items-center justify-center gap-2"><span>CHECKED IN ✓</span></button>';
        } else {
          actionContainer.innerHTML = '<button onclick="checkinCommunityDrop(\'' + d.id + '\', this)" class="w-full py-3.5 bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-black font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer transition shadow-lg flex items-center justify-center gap-2"><span>CHECK IN NOW</span></button>';
        }
      } else if (d.state === 'MEMORY') {
        actionContainer.innerHTML = '<button onclick="showToast(\'✦ Drop Memory is archived for attendees.\')" class="w-full py-3.5 bg-purple-500/20 border border-purple-500/40 text-purple-300 font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer flex items-center justify-center gap-2"><span>VIEW DROP ARCHIVE</span></button>';
      } else {
        actionContainer.innerHTML = '<button disabled class="w-full py-3.5 bg-amber-500/20 border border-amber-500/40 text-amber-400 font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-default flex items-center justify-center gap-2"><span>YOU ARE REGISTERED ✓</span></button>';
      }
    } else {
      if (isEnded) {
        actionContainer.innerHTML = '<button disabled class="w-full py-3.5 bg-zinc-900 border border-zinc-800 text-zinc-600 font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-not-allowed flex items-center justify-center gap-2"><span>EXPERIENCE ENDED</span></button>';
      } else if (spotsLeft <= 0) {
        actionContainer.innerHTML = '<button disabled class="w-full py-3.5 bg-zinc-900 border border-zinc-800 text-zinc-500 font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-not-allowed flex items-center justify-center gap-2"><span>ALL SPOTS TAKEN</span></button>';
      } else {
        actionContainer.innerHTML = '<button onclick="startDropOrderFlow(\'' + d.id + '\')" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 active:scale-95 text-black font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer transition shadow-lg flex items-center justify-center gap-2"><span>JOIN EXPERIENCE · ₹' + (d.price || 19) + '</span></button>';
      }
    }
  }

  modal.style.display = 'flex';
}
window.openDropDetail = openDropDetail;

function closeDropDetailModal() {
  var modal = document.getElementById('dropDetailModal');
  if (modal) modal.style.display = 'none';
}
window.closeDropDetailModal = closeDropDetailModal;

function closeDropPaymentModal() {
  var modal = document.getElementById('dropPaymentModal');
  if (modal) modal.style.display = 'none';
}
window.closeDropPaymentModal = closeDropPaymentModal;

// =====================================================================
// PHASE 6: REAL-TIME DROP EXPERIENCE & SHARED MOMENT LAYER
// =====================================================================
async function openDropExperience(dropId) {
  if (!dropId) return;
  state.activeDropId = dropId;
  state.previousScreen = state.activeScreen || 'campus-page';
  switchScreenView('drop-experience');

  var headerStatusEl = document.getElementById('dropExperienceHeaderStatus');
  var stateBadgeEl = document.getElementById('dropExperienceStateBadge');
  var communityEl = document.getElementById('dropExperienceCommunity');
  var titleEl = document.getElementById('dropExperienceTitle');
  var locEl = document.getElementById('dropExperienceLocationTxt');
  var descEl = document.getElementById('dropExperienceDesc');
  var timeRemEl = document.getElementById('dropExperienceTimeRemaining');
  var presenceEl = document.getElementById('dropExperiencePresenceTxt');
  var pulseDotEl = document.getElementById('dropExperiencePulseDotSmall');
  var pulseBadgeEl = document.getElementById('dropExperiencePulseBadge');
  var checkinContainer = document.getElementById('dropExperienceCheckinContainer');
  var hostControls = document.getElementById('dropExperienceHostControls');
  var hostAttendEl = document.getElementById('dropExperienceHostAttendanceTxt');
  var memoryBanner = document.getElementById('dropExperienceMemoryBanner');
  var viewMemoryBtn = document.getElementById('dropExperienceViewMemoryBtn');
  var momentsBadge = document.getElementById('dropExperienceMomentsCountBadge');
  var momentsContainer = document.getElementById('dropExperienceMomentsContainer');

  if (momentsContainer) {
    momentsContainer.innerHTML = '<div class="py-8 text-center text-xs text-zinc-500 font-mono-tag">Loading shared moments...</div>';
  }

  var res = await apiRequest('/api/drops/experience?drop_id=' + encodeURIComponent(dropId));
  if (!res || !res.success || !res.drop) {
    showToast('Could not load this experience.');
    if (momentsContainer) {
      momentsContainer.innerHTML = '<div class="py-8 text-center space-y-1"><p class="text-xs font-bold text-red-400 font-mono-tag">Could not load this experience.</p><p class="text-[11px] text-zinc-500 font-sans">Please check your connection and try again.</p></div>';
    }
    return;
  }

  var d = res.drop;
  var stateInfo = getDropStateInfo(d.lifecycle_state);

  if (headerStatusEl) headerStatusEl.textContent = stateInfo.label + ' EXPERIENCE';
  if (stateBadgeEl) {
    stateBadgeEl.textContent = stateInfo.label;
    stateBadgeEl.className = 'font-mono-tag text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ' + stateInfo.badgeClass;
  }
  if (communityEl) communityEl.textContent = d.community_name || 'Community';
  if (titleEl) titleEl.textContent = d.title;
  if (locEl) locEl.textContent = (d.location_context || d.location || 'Campus Commons') + (d.community_city ? ' · ' + d.community_city : '');
  if (descEl) descEl.textContent = d.description || 'A shared real-world experience captured together with members of the community.';
  if (timeRemEl) timeRemEl.textContent = (d.date_str || 'Today') + ' · ' + (d.time_str || 'Now');
  if (presenceEl) presenceEl.textContent = d.presence_label || ((d.checked_in_count || 0) + ' people are here');

  if (pulseBadgeEl && pulseDotEl) {
    pulseBadgeEl.textContent = d.pulse_status || 'ACTIVE NOW';
    if (d.pulse_status === 'MOMENTS ARE APPEARING' || d.pulse_status === 'ACTIVE NOW') {
      pulseBadgeEl.className = 'text-emerald-400 font-bold';
      pulseDotEl.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
    } else {
      pulseBadgeEl.className = 'text-zinc-400 font-bold';
      pulseDotEl.className = 'w-2 h-2 rounded-full bg-zinc-600';
    }
  }

  // Dynamic Checkin Container
  if (checkinContainer) {
    if (d.is_checked_in) {
      checkinContainer.innerHTML = '<div class="w-full py-3 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 font-extrabold text-xs rounded-2xl uppercase font-mono-tag text-center flex items-center justify-center gap-2"><span>YOU\'RE CHECKED IN ✓</span></div>';
    } else if (d.is_registered) {
      var isCheckinWindow = ['CHECK_IN', 'LIVE', 'ACTIVE'].indexOf(d.lifecycle_state) !== -1;
      if (isCheckinWindow) {
        checkinContainer.innerHTML = '<button onclick="checkinCommunityDrop(\'' + d.id + '\', this)" class="w-full py-3.5 bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-black font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer transition shadow-lg flex items-center justify-center gap-2"><span>CHECK IN NOW</span></button>';
      } else if (d.lifecycle_state === 'CLOSED' || d.lifecycle_state === 'MEMORY') {
        checkinContainer.innerHTML = '<div class="w-full py-3 bg-zinc-900 border border-zinc-800 text-zinc-500 font-bold text-xs rounded-2xl uppercase font-mono-tag text-center">CHECK-IN CLOSED</div>';
      } else {
        checkinContainer.innerHTML = '<div class="w-full py-3 bg-amber-500/10 border border-amber-500/30 text-amber-400 font-bold text-xs rounded-2xl uppercase font-mono-tag text-center">YOU\'RE REGISTERED ✓ · CHECK-IN OPENS SOON</div>';
      }
    } else {
      if (d.lifecycle_state === 'CLOSED' || d.lifecycle_state === 'MEMORY' || d.lifecycle_state === 'SETTLEMENT') {
        checkinContainer.innerHTML = '<div class="w-full py-3 bg-zinc-900 border border-zinc-800 text-zinc-500 font-bold text-xs rounded-2xl uppercase font-mono-tag text-center">EXPERIENCE CLOSED</div>';
      } else {
        checkinContainer.innerHTML = '<button onclick="startDropOrderFlow(\'' + d.id + '\')" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 active:scale-95 text-black font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer transition shadow-lg flex items-center justify-center gap-2"><span>JOIN EXPERIENCE · ₹' + (d.price || 19) + '</span></button>';
      }
    }
  }

  // Host Controls
  if (hostControls) {
    if (d.is_host) {
      hostControls.style.display = 'block';
      if (hostAttendEl) hostAttendEl.textContent = (d.checked_in_count || 0) + ' / ' + (d.capacity || 20) + ' Attending (' + (d.registered_count || 0) + ' Registered)';
    } else {
      hostControls.style.display = 'none';
    }
  }

  // Memory Banner
  if (memoryBanner) {
    if (d.lifecycle_state === 'MEMORY') {
      memoryBanner.style.display = 'block';
      if (viewMemoryBtn) {
        viewMemoryBtn.onclick = function() {
          openCollectiveMemoryPage(d.memory_id || 'mem_1');
        };
      }
    } else {
      memoryBanner.style.display = 'none';
    }
  }

  // Shared Moments
  var moments = Array.isArray(res.moments) ? res.moments : [];
  if (momentsBadge) momentsBadge.textContent = moments.length + ' Moments';
  if (momentsContainer) {
    if (moments.length > 0) {
      renderCommunityCards(moments, momentsContainer);
    } else {
      momentsContainer.innerHTML = '<div class="py-8 text-center space-y-1"><p class="text-xs font-bold text-zinc-400 font-mono-tag uppercase tracking-wider">Nothing has been shared yet.</p><p class="text-[11px] text-zinc-500 font-sans">Be the first to capture a moment from this experience.</p></div>';
    }
  }
}
window.openDropExperience = openDropExperience;

function handleDropExperienceBack() {
  switchScreenView(state.previousScreen || 'campus-page');
}
window.handleDropExperienceBack = handleDropExperienceBack;

async function refreshDropExperience() {
  if (state.activeDropId) {
    await openDropExperience(state.activeDropId);
    showToast('✦ Drop experience updated');
  }
}
window.refreshDropExperience = refreshDropExperience;

function triggerDropMomentCapture() {
  if (!state.activeDropId) return;
  state.activeDropContext = {
    drop_id: state.activeDropId,
    community_id: state.activeCommunity || ''
  };
  openCameraStudio();
}
window.triggerDropMomentCapture = triggerDropMomentCapture;

async function startDropOrderFlow(dropId) {
  var drops = state.communityDrops || [];
  var d = drops.find(function(x) { return x.id === dropId; });
  var title = d ? d.title : 'Community Experience';
  var dateStr = d ? (d.date_str || 'This Weekend') : 'This Weekend';
  var timeStr = d ? (d.time_str || '6:00 PM') : '6:00 PM';

  var modal = document.getElementById('dropPaymentModal');
  var stepContent = document.getElementById('dropPaymentStepContent');
  if (!modal || !stepContent) return;

  modal.style.display = 'flex';
  playTactileFeedback('shutter');

  stepContent.innerHTML = '<div class="py-8 space-y-3">' +
    '<div class="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto"></div>' +
    '<p class="text-xs font-mono-tag text-zinc-400">Initiating secure pass order...</p>' +
  '</div>';

  var res = await apiRequest('/api/drops/order/create', {
    method: 'POST',
    body: JSON.stringify({ drop_id: dropId })
  });

  if (!res || !res.success || !res.order_id) {
    stepContent.innerHTML = '<div class="py-6 space-y-4 text-center">' +
      '<div class="w-12 h-12 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 flex items-center justify-center text-xl mx-auto font-bold">✕</div>' +
      '<div class="space-y-1">' +
        '<h4 class="text-sm font-extrabold text-white">ORDER CREATION FAILED</h4>' +
        '<p class="text-xs text-zinc-400 font-sans">' + escapeHtml((res && res.error) ? res.error : 'Could not prepare order') + '</p>' +
      '</div>' +
      '<button onclick="closeDropPaymentModal()" class="w-full py-3 bg-zinc-900 hover:bg-zinc-800 text-white font-mono-tag text-xs font-bold rounded-2xl border border-zinc-700 transition">CLOSE</button>' +
    '</div>';
    return;
  }

  var amountPaise = res.amount || 1900;
  var creatorPaise = (res.breakdown && res.breakdown.creator_pool_paise) || 1520;
  var feePaise = (res.breakdown && res.breakdown.platform_fee_paise) || 380;

  stepContent.innerHTML = '<div class="space-y-4 text-left">' +
    '<div class="p-3.5 rounded-2xl bg-zinc-900 border border-white/[.05] space-y-2.5">' +
      '<div class="flex justify-between items-start">' +
        '<div class="space-y-0.5">' +
          '<span class="text-[9px] font-mono-tag text-amber-500 uppercase tracking-wider font-bold">EXPERIENCE PASS</span>' +
          '<h4 class="text-sm font-bold text-white">' + escapeHtml(title) + '</h4>' +
          '<p class="text-[10px] text-zinc-400 font-mono-tag">' + escapeHtml(dateStr) + ' · ' + escapeHtml(timeStr) + '</p>' +
        '</div>' +
        '<div class="text-right">' +
          '<span class="text-base font-extrabold text-amber-400 font-mono-tag">₹' + (amountPaise / 100).toFixed(2) + '</span>' +
          '<span class="text-[8px] text-zinc-500 block font-mono-tag">' + amountPaise + ' PAISE</span>' +
        '</div>' +
      '</div>' +
      '<div class="pt-2 border-t border-zinc-800 flex justify-between items-center text-[10px] font-mono-tag text-zinc-400">' +
        '<span>Creator Pool (80%): ₹' + (creatorPaise / 100).toFixed(2) + '</span>' +
        '<span>Kandid (20%): ₹' + (feePaise / 100).toFixed(2) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="space-y-2">' +
      '<button onclick="confirmDropPayment(\'' + res.order_id + '\', \'' + dropId + '\', \'' + (res.provider_order_id || '') + '\')" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 active:scale-95 text-black font-extrabold text-xs rounded-2xl uppercase font-mono-tag cursor-pointer transition shadow-lg flex items-center justify-center gap-2">' +
        '<span>PAY ₹' + (amountPaise / 100).toFixed(2) + ' & SECURE PASS</span>' +
      '</button>' +
      '<button onclick="closeDropPaymentModal()" class="w-full py-2.5 text-zinc-500 hover:text-white font-mono-tag text-xs font-bold transition">' +
        'CANCEL' +
      '</button>' +
    '</div>' +
  '</div>';
}
window.startDropOrderFlow = startDropOrderFlow;
window.joinCommunityDrop = function(dropId, btnEl) {
  startDropOrderFlow(dropId);
};

async function confirmDropPayment(orderId, dropId, providerOrderId) {
  var stepContent = document.getElementById('dropPaymentStepContent');
  if (!stepContent) return;

  stepContent.innerHTML = '<div class="py-8 space-y-3 text-center">' +
    '<div class="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto"></div>' +
    '<p class="text-xs font-mono-tag text-zinc-400">Verifying secure signature & recording ledger...</p>' +
  '</div>';

  var mockPaymentId = 'pay_' + Math.random().toString(36).substring(2, 11);
  var validSignature = 'sig_valid_' + orderId;

  var res = await apiRequest('/api/drops/order/verify', {
    method: 'POST',
    body: JSON.stringify({
      order_id: orderId,
      provider_payment_id: mockPaymentId,
      provider_order_id: providerOrderId,
      signature: validSignature
    })
  });

  if (res && res.success && res.registration) {
    playTactileFeedback('click');
    stepContent.innerHTML = '<div class="py-6 space-y-4 text-center">' +
      '<div class="w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center text-xl mx-auto font-bold shadow-lg">✓</div>' +
      '<div class="space-y-1">' +
        '<h4 class="text-sm font-extrabold text-white">ACCESS PASS CONFIRMED</h4>' +
        '<p class="text-[11px] text-zinc-400 font-sans">You are officially registered for this experience.</p>' +
        '<p class="text-[9px] font-mono-tag text-zinc-500 pt-1">Registration ID: #' + escapeHtml(res.registration.id.slice(0, 8)) + '</p>' +
      '</div>' +
      '<button onclick="closeDropPaymentModal(); closeDropDetailModal();" class="w-full py-3 bg-zinc-900 hover:bg-zinc-800 text-white font-mono-tag text-xs font-bold rounded-2xl border border-zinc-700 transition font-mono-tag">DONE</button>' +
    '</div>';
    loadCommunityDrops(state.activeCommunity);
  } else {
    stepContent.innerHTML = '<div class="py-6 space-y-4 text-center">' +
      '<div class="w-12 h-12 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 flex items-center justify-center text-xl mx-auto font-bold">✕</div>' +
      '<div class="space-y-1">' +
        '<h4 class="text-sm font-extrabold text-white">VERIFICATION FAILED</h4>' +
        '<p class="text-xs text-zinc-400 font-sans">' + escapeHtml((res && res.error) ? res.error : 'Payment signature could not be verified') + '</p>' +
      '</div>' +
      '<button onclick="closeDropPaymentModal()" class="w-full py-3 bg-zinc-900 hover:bg-zinc-800 text-white font-mono-tag text-xs font-bold rounded-2xl border border-zinc-700 transition">CLOSE</button>' +
    '</div>';
  }
}
window.confirmDropPayment = confirmDropPayment;

async function checkinCommunityDrop(dropId, btnEl) {
  if (!dropId) return;
  playTactileFeedback('shutter');

  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = '<span class="animate-spin text-xs">⏳</span>';
  }

  var res = await apiRequest('/api/drops/check-in', {
    method: 'POST',
    body: JSON.stringify({ drop_id: dropId })
  });

  if (res && res.success) {
    playTactileFeedback('click');
    showToast('✓ Checked in! Welcome to the experience.');
    if (btnEl) {
      btnEl.className = 'px-3 py-1.5 rounded-xl bg-emerald-500/20 text-emerald-400 font-mono-tag text-[10px] font-bold border border-emerald-500/40 cursor-default';
      btnEl.innerHTML = '<span>CHECKED IN ✓</span>';
    }
    loadCommunityDrops(state.activeCommunity);
    var modal = document.getElementById('dropDetailModal');
    if (modal && modal.style.display !== 'none') {
      openDropDetail(dropId);
    }
  } else {
    showToast('Check-in failed: ' + (res ? res.error : 'Network error'));
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = 'CHECK IN';
    }
  }
}
window.checkinCommunityDrop = checkinCommunityDrop;

function openCreateDropModal() {
  var modal = document.getElementById('createDropModal');
  if (modal) modal.style.display = 'flex';
}
window.openCreateDropModal = openCreateDropModal;

function closeCreateDropModal() {
  var modal = document.getElementById('createDropModal');
  if (modal) modal.style.display = 'none';
}
window.closeCreateDropModal = closeCreateDropModal;

async function submitNewDrop() {
  var titleInput = document.getElementById('newDropTitle');
  var descInput = document.getElementById('newDropDesc');
  var dateInput = document.getElementById('newDropDate');
  var timeInput = document.getElementById('newDropTime');
  var capInput = document.getElementById('newDropCapacity');

  var title = titleInput ? titleInput.value.trim() : '';
  var desc = descInput ? descInput.value.trim() : '';
  var dateStr = dateInput ? dateInput.value.trim() : 'This Sunday';
  var timeStr = timeInput ? timeInput.value.trim() : '6:00 PM';
  var capacity = capInput ? parseInt(capInput.value) || 15 : 15;

  if (!title) {
    showToast('Please enter an experience title.');
    return;
  }

  var res = await apiRequest('/api/community/drops/create', {
    method: 'POST',
    body: JSON.stringify({
      community_name: state.activeCommunity || 'North City University',
      title: title,
      description: desc,
      date_str: dateStr,
      time_str: timeStr,
      capacity: capacity,
      price: 19.0
    })
  });

  if (res && res.success) {
    playTactileFeedback('click');
    showToast('✦ Community Drop Published! Live for members.');
    closeCreateDropModal();
    if (titleInput) titleInput.value = '';
    if (descInput) descInput.value = '';
    loadCommunityDrops(state.activeCommunity);
  } else {
    showToast('Failed to publish drop: ' + (res ? res.error : 'Error'));
  }
}
window.submitNewDrop = submitNewDrop;

async function openCreatorEarningsModal() {
  var modal = document.getElementById('creatorEarningsModal');
  if (modal) modal.style.display = 'flex';
  
  var titleEl = document.getElementById('earningsCommunityTitle');
  if (titleEl) titleEl.textContent = (state.activeCommunity || 'Community') + ' Earnings';

  var grossEl = document.getElementById('earningsGrossTxt');
  var feeEl = document.getElementById('earningsPlatformFeeTxt');
  var netEl = document.getElementById('earningsCreatorNetTxt');
  var txCountEl = document.getElementById('earningsTxCountTxt');
  var listEl = document.getElementById('creatorTransactionsLedgerList');

  var res = await apiRequest('/api/community/earnings?community=' + encodeURIComponent(state.activeCommunity || ''));
  if (res && res.success && res.earnings) {
    var e = res.earnings;
    if (grossEl) grossEl.textContent = '₹' + Number(e.gross_volume || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (feeEl) feeEl.textContent = '₹' + Number(e.platform_fee || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (netEl) netEl.textContent = '₹' + Number(e.creator_net || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (txCountEl) txCountEl.textContent = (e.transactions_count || 0) + ' confirmed registrations';

    if (listEl && Array.isArray(e.transactions) && e.transactions.length > 0) {
      listEl.innerHTML = e.transactions.map(function(t) {
        var gross = t.gross_amount_paise ? (t.gross_amount_paise / 100) : (t.gross_amount || 19);
        var creator = t.creator_amount_paise ? (t.creator_amount_paise / 100) : (t.creator_amount || 15.20);
        return '<div class="p-2.5 rounded-xl bg-zinc-950 border border-white/[.04] flex items-center justify-between text-xs">' +
          '<div class="space-y-0.5">' +
            '<span class="text-white font-bold block truncate">Drop Registration #' + escapeHtml((t.id || t.order_id || 'reg').slice(0, 7)) + '</span>' +
            '<span class="text-[9px] font-mono-tag text-zinc-500">' + escapeHtml(t.created_at || 'Recent') + '</span>' +
          '</div>' +
          '<div class="text-right">' +
            '<span class="text-amber-400 font-mono-tag font-bold">+₹' + creator.toFixed(2) + '</span>' +
            '<span class="text-[8px] font-mono-tag text-zinc-500 block">Gross ₹' + gross.toFixed(2) + '</span>' +
          '</div>' +
        '</div>';
      }).join('');
    } else if (listEl) {
      listEl.innerHTML = '<div class="p-4 rounded-xl bg-zinc-950 border border-white/[.04] text-center text-xs text-zinc-500 font-mono-tag">No transactions recorded yet.</div>';
    }
  }
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

  var balanceEl = document.getElementById('opsCreatorBalanceTxt');
  var setPendEl = document.getElementById('opsSettledPendingTxt');
  var commsListEl = document.getElementById('opsCommunitiesList');
  var dropsListEl = document.getElementById('opsDropsList');
  var checkinsListEl = document.getElementById('opsCheckinsList');

  var res = await apiRequest('/api/community/manage');
  if (res && res.success && res.operations) {
    var op = res.operations;
    var earn = op.earnings || {};
    
    if (balanceEl) balanceEl.textContent = '₹' + Number(earn.creator_amount_rupees || 0).toFixed(2);
    if (setPendEl) setPendEl.textContent = '₹' + Number(earn.settled_rupees || 0).toFixed(0) + ' / ₹' + Number(earn.pending_rupees || 0).toFixed(0);

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

    // Drops (Combine active, upcoming, draft, past)
    var allDrops = (op.active_drops || []).concat(op.upcoming_drops || []).concat(op.draft_drops || []).concat(op.past_drops || []);
    if (dropsListEl) {
      if (allDrops.length > 0) {
        dropsListEl.innerHTML = allDrops.map(function(d) {
          var stateBadgeColor = (d.lifecycle_state === 'LIVE' || d.lifecycle_state === 'CHECK_IN' || d.lifecycle_state === 'ACTIVE') ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' : 'text-amber-400 bg-amber-500/10 border-amber-500/30';
          return '<div class="p-3 rounded-xl bg-zinc-900 border border-white/[.04] space-y-2 text-xs">' +
            '<div class="flex justify-between items-start">' +
              '<div>' +
                '<span class="text-white font-bold block text-xs">' + escapeHtml(d.title) + '</span>' +
                '<span class="text-[9px] font-mono-tag text-zinc-500">' + escapeHtml(d.date_str || '') + ' · ' + escapeHtml(d.time_str || '') + '</span>' +
              '</div>' +
              '<span class="text-[9px] font-mono-tag font-bold uppercase px-2 py-0.5 rounded border ' + stateBadgeColor + '">' + escapeHtml(d.lifecycle_state || 'DRAFT') + '</span>' +
            '</div>' +
            '<div class="flex items-center justify-between text-[10px] font-mono-tag text-zinc-400 pt-1 border-t border-zinc-800">' +
              '<span>' + (d.registered_count || 0) + ' / ' + (d.capacity || 20) + ' Registered</span>' +
              '<div class="flex items-center gap-2">' +
                '<button onclick="openDropAttendeesModal(\'' + escapeHtml(d.id) + '\', \'' + escapeHtml(d.title).replace(/'/g, "\\'") + '\')" class="text-amber-400 hover:underline cursor-pointer">Roster</button>' +
                (d.lifecycle_state !== 'CANCELLED' && d.lifecycle_state !== 'CLOSED' && d.lifecycle_state !== 'MEMORY' ? '<button onclick="cancelDropPrompt(\'' + escapeHtml(d.id) + '\')" class="text-rose-400 hover:underline cursor-pointer">Cancel</button>' : '') +
              '</div>' +
            '</div>' +
          '</div>';
        }).join('');
      } else {
        dropsListEl.innerHTML = '<div class="p-2.5 rounded-xl bg-zinc-900 text-xs text-zinc-500 font-mono-tag">No drops created yet.</div>';
      }
    }

    // Recent check-ins
    if (checkinsListEl) {
      if (Array.isArray(op.recent_checkins) && op.recent_checkins.length > 0) {
        checkinsListEl.innerHTML = op.recent_checkins.map(function(ch) {
          return '<div class="p-2 rounded-xl bg-zinc-900/70 border border-white/[.03] flex items-center justify-between text-xs">' +
            '<div>' +
              '<span class="text-white font-bold block truncate">' + escapeHtml(ch.user_name || ch.user_handle) + '</span>' +
              '<span class="text-[9px] font-mono-tag text-zinc-500">' + escapeHtml(ch.drop_title || 'Drop') + '</span>' +
            '</div>' +
            '<span class="text-[9px] font-mono-tag text-emerald-400 font-bold">CHECKED IN ✓</span>' +
          '</div>';
        }).join('');
      } else {
        checkinsListEl.innerHTML = '<div class="p-2 rounded-xl bg-zinc-900/60 text-[10px] text-zinc-500 font-mono-tag text-center">No check-ins yet.</div>';
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

async function openDropAttendeesModal(dropId, dropTitle) {
  var modal = document.getElementById('dropAttendeesModal');
  if (modal) modal.style.display = 'flex';

  var titleEl = document.getElementById('attendeesDropTitle');
  if (titleEl) titleEl.textContent = (dropTitle || 'Drop') + ' Attendees';

  var countEl = document.getElementById('attendeesRosterCount');
  var listEl = document.getElementById('attendeesRosterList');

  var res = await apiRequest('/api/community/drops/attendees?drop_id=' + encodeURIComponent(dropId));
  if (res && res.success && Array.isArray(res.attendees)) {
    if (countEl) countEl.textContent = res.attendees.length + ' Registered';
    if (listEl) {
      if (res.attendees.length > 0) {
        listEl.innerHTML = res.attendees.map(function(a) {
          var checkinStatus = a.is_checked_in ? '<span class="text-emerald-400 font-bold font-mono-tag text-[9px]">CHECKED IN ✓</span>' : '<span class="text-zinc-500 font-mono-tag text-[9px]">CONFIRMED</span>';
          return '<div class="p-2.5 rounded-xl bg-zinc-900 border border-white/[.04] flex items-center justify-between text-xs">' +
            '<div>' +
              '<span class="text-white font-bold block">' + escapeHtml(a.user_name || a.user_handle) + '</span>' +
              '<span class="text-[9px] font-mono-tag text-zinc-500">@' + escapeHtml(a.user_handle) + '</span>' +
            '</div>' +
            '<div class="text-right">' +
              checkinStatus +
              '<span class="text-[8px] font-mono-tag text-zinc-500 block">' + escapeHtml(a.payment_status || 'paid') + '</span>' +
            '</div>' +
          '</div>';
        }).join('');
      } else {
        listEl.innerHTML = '<div class="p-3 rounded-xl bg-zinc-900 text-xs text-zinc-500 font-mono-tag text-center">No attendees registered yet.</div>';
      }
    }
  } else {
    if (listEl) listEl.innerHTML = '<div class="p-3 rounded-xl bg-zinc-900 text-xs text-rose-400 font-mono-tag text-center">' + (res ? res.error : 'Failed to load attendees') + '</div>';
  }
}
window.openDropAttendeesModal = openDropAttendeesModal;

function closeDropAttendeesModal() {
  var modal = document.getElementById('dropAttendeesModal');
  if (modal) modal.style.display = 'none';
}
window.closeDropAttendeesModal = closeDropAttendeesModal;

async function cancelDropPrompt(dropId) {
  if (!confirm('Are you sure you want to cancel this Drop? This will stop further registrations.')) {
    return;
  }
  var res = await apiRequest('/api/community/drops/cancel', {
    method: 'POST',
    body: JSON.stringify({ drop_id: dropId })
  });
  if (res && res.success) {
    showToast('✓ Drop cancelled successfully');
    openCreatorOperationsModal();
    loadCommunityDrops(state.activeCommunity);
  } else {
    showToast('Failed to cancel drop: ' + (res ? res.error : 'Error'));
  }
}
window.cancelDropPrompt = cancelDropPrompt;

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
              (r.target_type === 'drop' ? '<button onclick="handleModerationAction(\'' + escapeHtml(r.id) + '\', \'suspend\', \'' + escapeHtml(r.target_type) + '\', \'' + escapeHtml(r.target_id) + '\', \'' + escapeHtml(commId) + '\')" class="text-rose-400 hover:underline cursor-pointer text-[10px]">Suspend Drop</button>' : '') +
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
      var badge = c.context_reason || (c.activity_state === 'UPCOMING' ? 'Upcoming Drop' : 'Active Community');
      return '<div onclick="openCampusPage(\'' + escapeHtml(c.name).replace(/'/g, "\\'") + '\')" class="w-36 shrink-0 p-3 rounded-2xl bg-zinc-950 border border-white/[.07] hover:border-amber-500/40 space-y-2 cursor-pointer transition shadow-md active:scale-95 group">' +
        '<div class="flex items-center justify-between">' +
          '<div class="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center font-bold text-sm">' + (c.icon || '📍') + '</div>' +
          (c.activity_state === 'UPCOMING' ? '<span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>' : '') +
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
    if (badgeEl) badgeEl.textContent = (m.moments_count || 14) + ' Moments captured together';
    if (commEl) commEl.textContent = m.community_name;
    if (storyEl) storyEl.textContent = m.story || 'Unfiltered community moments captured together.';

    // 1. Render Hero Moment
    if (heroContainer) {
      var heroImg = m.cover_img || (res.moments && res.moments[0] ? (res.moments[0].main_img || res.moments[0].image_url) : '');
      var heroCaption = (res.moments && res.moments[0] && res.moments[0].caption) ? res.moments[0].caption : 'Opening the day together.';
      heroContainer.innerHTML =
        '<div class="relative w-full aspect-[4/3] bg-zinc-950 overflow-hidden">' +
          '<img src="' + escapeHtml(heroImg) + '" class="w-full h-full object-cover">' +
          '<div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex flex-col justify-end p-4">' +
            '<span class="font-mono-tag text-[8px] text-amber-400 font-bold uppercase tracking-widest block mb-1">⭐ HERO MOMENT</span>' +
            '<p class="text-xs text-white font-medium italic">“' + escapeHtml(heroCaption) + '”</p>' +
          '</div>' +
        '</div>';
    }

    // 2. Render Unique Contributors ("CAPTURED BY")
    if (capturedByEl && Array.isArray(res.moments) && res.moments.length > 0) {
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
    }

    // 3. Render Timeline Moments
    if (momentsContainer && Array.isArray(res.moments)) {
      renderFeedCards(res.moments, momentsContainer);
    }
  }
}
window.openCollectiveMemoryPage = openCollectiveMemoryPage;

function handleCollectiveMemoryBack() {
  switchScreenView('campus-page');
}
window.handleCollectiveMemoryBack = handleCollectiveMemoryBack;

async function toggleJoinCommunity() {
  var btn = document.getElementById('campusPageJoinBtn');
  var name = state.activeCommunity || 'North City University';
  if (!btn) return;
  
  btn.style.opacity = '0.5';
  var res = await apiRequest('/api/community/join', {
    method: 'POST',
    body: JSON.stringify({ name: name })
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

  try {
    var data = await apiRequest(endpoint);
    if (data && data.success && Array.isArray(data.feed)) {
      if (data.feed.length === 0) {
        container.innerHTML = 
          '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-8 text-center space-y-3 shadow-xl">' +
            '<div class="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-xl">📷</div>' +
            '<h3 class="text-xs font-black text-white uppercase font-mono-tag tracking-wider">NO COMMUNITY MOMENTS YET</h3>' +
            '<p class="text-[11px] text-zinc-400">Be the first to capture today\'s unfiltered moment in your community!</p>' +
            '<button class="mt-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-xs rounded-xl font-mono-tag tracking-wider uppercase cursor-pointer shadow-lg active:scale-95 transition" onclick="openCameraStudio()">CAPTURE TODAY\'S MOMENT</button>' +
          '</div>';
      } else {
        renderFeedCards(data.feed, container);
      }
    } else {
      // If feed array is missing or mock fallback needed
      if (typeof MOCK_DATA !== 'undefined' && MOCK_DATA.feed) {
        renderFeedCards(MOCK_DATA.feed, container);
      }
    }
  } catch(e) {
    console.error('Error loading feed moments:', e);
    if (typeof MOCK_DATA !== 'undefined' && MOCK_DATA.feed) {
      renderFeedCards(MOCK_DATA.feed, container);
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
    if (!createdStr) return '12 min ago';
    try {
        var dt = new Date(createdStr);
        if (isNaN(dt.getTime())) return '12 min ago';
        var now = new Date();
        var diffSec = Math.floor((now.getTime() - dt.getTime()) / 1000);
        if (diffSec < 60) return 'Just now';
        var mins = Math.floor(diffSec / 60);
        if (mins < 60) return mins + ' min ago';
        var hrs = Math.floor(mins / 60);
        if (hrs < 24) return hrs + ' hr ago';
        var days = Math.floor(hrs / 24);
        return days + 'd ago';
    } catch(e) {
        return '12 min ago';
    }
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
    var campusName = escapeHtml((m.campus || 'CENTRAL CAMPUS').toUpperCase());
    var timeAgo = escapeHtml((m.timeAgo || m.time_ago || '12 MIN AGO').toUpperCase());
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

    var mainImgSrc = m.main_img || m.mainImg || 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=600&q=80';
    var pipImgSrc = m.pip_img || m.pipImg || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80';

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
      clusterBadgeHtml = '<button onclick="event.stopPropagation(); openMomentClusterModal(\'' + (m.cluster_id || '') + '\', \'' + m.id + '\')" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-[9px] font-mono-tag font-bold text-amber-400 transition cursor-pointer active:scale-95 shadow-sm">' +
        '<span>✦</span> <span>' + pCount + ' perspective' + (pCount === 1 ? '' : 's') + '</span>' +
      '</button>';
    }

    var iWasThereHtml = '';
    if (!m.is_private && (!state.currentUser || state.currentUser.id !== m.user_id)) {
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
        '<div class="flex items-center justify-between gap-1">' +
          '<div class="text-[10px] text-zinc-400 font-mono-tag font-bold tracking-wider uppercase">' +
            campusName + ' · ' + timeAgo +
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

  if (state.activeCommunityId && defaultComm) {
    var hasTarget = communities.some(function(c) { return c.id === state.activeCommunityId; });
    if (!hasTarget) {
      communities.unshift({ id: state.activeCommunityId, name: defaultComm, type: 'Community Space', icon: '📍' });
    }
  } else if (!communities.length) {
    communities.unshift({ id: '', name: 'Personal (Feed)', type: 'Feed', icon: '✨' });
  }

  listEl.innerHTML = communities.map(function(c, idx) {
    var isChecked = false;
    if (state.activeCommunityId) {
      isChecked = (c.id === state.activeCommunityId);
    } else {
      isChecked = (idx === 0);
    }
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

  var payload = {
    caption: caption,
    circle: state.activeCircle || 'campus',
    region: 'all',
    locationCity: approxLocName,
    community: chosenCommunity,
    community_id: chosenCommId,
    primary_community_id: chosenCommId || chosenCommunity,
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
    drop_id: state.activeDropId || '',
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
    if (state.activeScreen === 'drop-experience' && state.activeDropId) {
      await openDropExperience(state.activeDropId);
    }
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

// =====================================================================
// PRODUCTION SEARCH & DISCOVERY ENGINE
// =====================================================================
state.searchQuery = '';
state.searchFilter = 'live';
var searchDebounceTimer = null;

function handleSearchInput(event) {
  var val = (event.target.value || '').trim();
  state.searchQuery = val;
  var clearBtn = document.getElementById('searchClearBtn');
  if (clearBtn) clearBtn.style.display = val ? 'block' : 'none';

  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(function() {
    performSearch();
  }, 200);
}
window.handleSearchInput = handleSearchInput;

function clearSearchInput() {
  var input = document.getElementById('searchInput');
  if (input) input.value = '';
  state.searchQuery = '';
  var clearBtn = document.getElementById('searchClearBtn');
  if (clearBtn) clearBtn.style.display = 'none';
  selectSearchFilter('live');
}
window.clearSearchInput = clearSearchInput;

function selectSearchFilter(filterType) {
  state.searchFilter = filterType;

  document.querySelectorAll('.search-filter-btn').forEach(function(btn) {
    if (btn.dataset.filter === filterType) {
      btn.className = 'search-filter-btn text-amber-500 font-bold pb-1 border-b-2 border-amber-500 transition-all cursor-pointer';
    } else {
      btn.className = 'search-filter-btn hover:text-white transition-colors cursor-pointer text-zinc-400';
    }
  });

  performSearch();
}
window.selectSearchFilter = selectSearchFilter;

function filterBySector(sectorName) {
  var input = document.getElementById('searchInput');
  if (input) input.value = sectorName;
  state.searchQuery = sectorName;
  var clearBtn = document.getElementById('searchClearBtn');
  if (clearBtn) clearBtn.style.display = 'block';
  selectSearchFilter('moments');
}
window.filterBySector = filterBySector;

function filterByFrequency(freqTag) {
  var input = document.getElementById('searchInput');
  if (input) input.value = freqTag;
  state.searchQuery = freqTag;
  var clearBtn = document.getElementById('searchClearBtn');
  if (clearBtn) clearBtn.style.display = 'block';
  selectSearchFilter('moments');
}
window.filterByFrequency = filterByFrequency;

async function loadSearchDiscovery() {
  var defaultView = document.getElementById('searchDiscoveryDefault');
  var resultsContainer = document.getElementById('searchResultsContainer');
  var emptyState = document.getElementById('searchEmptyState');
  var errorState = document.getElementById('searchErrorState');

  if (resultsContainer) resultsContainer.style.display = 'none';
  if (emptyState) emptyState.style.display = 'none';
  if (errorState) errorState.style.display = 'none';
  if (defaultView) defaultView.style.display = 'block';

  var data = await apiRequest('/api/search?type=all');
  if (data && data.success) {
    var nodesBadge = document.getElementById('activeNodesBadge');
    if (nodesBadge && data.activeNodes) {
      nodesBadge.textContent = data.activeNodes + ' ACTIVE NODES';
    }

    var sectorsContainer = document.getElementById('searchSectorsContainer');
    if (sectorsContainer && Array.isArray(data.sectors) && data.sectors.length > 0) {
      sectorsContainer.innerHTML = '';
      data.sectors.forEach(function(s) {
        var el = document.createElement('div');
        el.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex justify-between items-center shadow-lg hover:border-amber-500/40 transition-colors cursor-pointer active:scale-[0.99]';
        var icon = s.icon || '📍';
        el.innerHTML =
          '<div class="flex items-center gap-3">' +
            '<div class="w-8 h-8 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-sm flex-shrink-0">' + icon + '</div>' +
            '<div>' +
              '<h3 class="text-xs font-bold text-white tracking-wide">' + escapeHtml(s.name) + '</h3>' +
              '<span class="text-[9px] text-zinc-500 font-mono-tag uppercase">' + escapeHtml(s.area || 'Community Hub') + '</span>' +
            '</div>' +
          '</div>' +
          '<span class="text-[10px] text-zinc-400 font-mono-tag font-bold bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded-md">' + s.momentsCount + ' MOMENTS</span>';
        el.addEventListener('click', function() {
          filterBySector(s.name);
        });
        sectorsContainer.appendChild(el);
      });
    }

    var freqContainer = document.getElementById('searchFrequenciesContainer');
    if (freqContainer && Array.isArray(data.frequencies) && data.frequencies.length > 0) {
      freqContainer.innerHTML = '';
      data.frequencies.forEach(function(f, idx) {
        var el = document.createElement('div');
        var borderClass = (idx < data.frequencies.length - 1) ? 'pb-2.5 border-b border-zinc-900' : '';
        el.className = 'flex justify-between items-center text-xs font-mono-tag cursor-pointer hover:opacity-80 transition-opacity ' + borderClass;
        el.innerHTML =
          '<span class="text-amber-400 font-bold">' + f.number + ' ' + escapeHtml(f.tag) + '</span>' +
          '<span class="text-zinc-500">' + f.postsCount + ' POSTS</span>';
        el.addEventListener('click', function() {
          filterByFrequency(f.tag);
        });
        freqContainer.appendChild(el);
      });
    }
  }
}
window.loadSearchDiscovery = loadSearchDiscovery;

async function performSearch(query, filter) {
  query = (typeof query === 'string') ? query : state.searchQuery;
  filter = filter || state.searchFilter || 'live';

  var defaultView = document.getElementById('searchDiscoveryDefault');
  var resultsContainer = document.getElementById('searchResultsContainer');
  var emptyState = document.getElementById('searchEmptyState');
  var errorState = document.getElementById('searchErrorState');

  if (!resultsContainer) return;

  if (errorState) errorState.style.display = 'none';

  // If live filter and no search text, show the rich default discovery view
  if (filter === 'live' && !query) {
    if (defaultView) defaultView.style.display = 'block';
    if (resultsContainer) resultsContainer.style.display = 'none';
    if (emptyState) emptyState.style.display = 'none';
    loadSearchDiscovery();
    return;
  }

  if (defaultView) defaultView.style.display = 'none';
  if (emptyState) emptyState.style.display = 'none';
  resultsContainer.style.display = 'block';
  resultsContainer.innerHTML = '<div class="text-center py-8 text-xs text-zinc-500 font-mono-tag animate-pulse">DISCOVERING CAMPUS...</div>';

  var endpoint = '/api/search?q=' + encodeURIComponent(query) + '&type=' + encodeURIComponent(filter);
  var data = await apiRequest(endpoint);

  if (!data || !data.success) {
    resultsContainer.style.display = 'none';
    if (errorState) errorState.style.display = 'block';
    return;
  }

  resultsContainer.innerHTML = '';
  var hasResults = false;

  if (filter === 'people' || filter === 'all' || (filter === 'live' && query)) {
    if (Array.isArray(data.people) && data.people.length > 0) {
      hasResults = true;
      renderPeopleSearchResults(data.people, resultsContainer);
    }
  }

  if (filter === 'places' || filter === 'all' || (filter === 'live' && query && !hasResults)) {
    if (Array.isArray(data.places) && data.places.length > 0) {
      hasResults = true;
      renderPlacesSearchResults(data.places, resultsContainer);
    }
  }

  if (filter === 'moments' || filter === 'all' || (filter === 'live' && query)) {
    if (Array.isArray(data.moments) && data.moments.length > 0) {
      hasResults = true;
      renderMomentsSearchResults(data.moments, resultsContainer);
    }
  }

  if (!hasResults) {
    resultsContainer.style.display = 'none';
    if (emptyState) emptyState.style.display = 'block';
  }
}
window.performSearch = performSearch;

function renderPeopleSearchResults(people, container) {
  var header = document.createElement('div');
  header.className = 'px-1 pt-1 pb-2 flex justify-between items-center text-[9px] font-mono-tag text-zinc-500 font-bold uppercase tracking-widest';
  header.innerHTML = '<span>PEOPLE & CREATORS (' + people.length + ')</span>';
  container.appendChild(header);

  var group = document.createElement('div');
  group.className = 'space-y-2.5';

  people.forEach(function(p) {
    var item = document.createElement('div');
    item.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex items-center justify-between shadow-lg hover:border-amber-500/50 hover:bg-zinc-900/30 transition cursor-pointer active:scale-[0.99]';

    var avatarSrc = p.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(p.handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
    var name = escapeHtml(p.name || 'Student');
    var handle = escapeHtml(p.handle || 'user');
    var campus = escapeHtml(p.campus || 'North City University');

    item.innerHTML =
      '<div class="flex items-center gap-3">' +
        '<div class="w-11 h-11 rounded-full bg-zinc-900 overflow-hidden border border-zinc-800 flex-shrink-0">' +
          '<img src="' + avatarSrc + '" class="w-full h-full object-cover">' +
        '</div>' +
        '<div>' +
          '<h4 class="text-xs font-bold text-white">' + name + '</h4>' +
          '<p class="text-[10px] text-zinc-400 font-mono-tag">@' + handle + ' · ' + campus + '</p>' +
        '</div>' +
      '</div>' +
      '<button class="px-3 py-1.5 bg-zinc-900 hover:bg-amber-500 hover:text-black text-amber-400 font-bold text-[9px] font-mono-tag rounded-xl border border-zinc-800 transition shadow-sm active:scale-95">VIEW PROFILE</button>';

    item.querySelector('button').addEventListener('click', function(e) {
      e.stopPropagation();
      openUserProfile(p.id, p);
    });

    item.addEventListener('click', function() {
      openUserProfile(p.id, p);
    });

    group.appendChild(item);
  });

  container.appendChild(group);
}

// =====================================================================
// PUBLIC PEER PROFILE ENGINE
// =====================================================================
var lastScreenBeforeProfile = 'search';

async function openUserProfile(userId, preloadedData) {
  lastScreenBeforeProfile = state.activeScreen || 'search';
  switchScreenView('peer-profile');

  var nameEl = document.getElementById('peerProfileName');
  var usernameEl = document.getElementById('peerProfileUsername');
  var campusEl = document.getElementById('peerProfileCampus');
  var bioEl = document.getElementById('peerProfileBio');
  var avatarEl = document.getElementById('peerProfileAvatar');
  var onlineDot = document.getElementById('peerProfileOnlineDot');
  var statusBadge = document.getElementById('peerProfileStatusBadge');
  var streakEl = document.getElementById('peerProfileStreakVal');
  var momentsCountEl = document.getElementById('peerProfileMomentsCountVal');
  var scoreEl = document.getElementById('peerProfileScoreVal');
  var msgBtn = document.getElementById('peerProfileMessageBtn');
  var msgBtnText = document.getElementById('peerProfileMessageBtnText');
  var momentsGrid = document.getElementById('peerProfileMomentsGrid');
  var emptyMoments = document.getElementById('peerProfileEmptyMoments');

  var initialsEl = document.getElementById('peerProfileInitials');
  var memoriesEl = document.getElementById('peerProfileMemoriesVal');
  var connectBtnText = document.getElementById('peerProfileConnectText');
  var connectIcon = document.getElementById('peerProfileConnectIcon');

  // Prepopulate with instant preview data
  if (preloadedData) {
    var rawName = (preloadedData.name || 'Student').toUpperCase();
    if (nameEl) nameEl.textContent = rawName;
    if (initialsEl) initialsEl.textContent = rawName.substring(0, 2);
    var rawH = (preloadedData.handle || 'user').replace('@', '');
    var h = '@' + rawH.toUpperCase();
    if (usernameEl) usernameEl.textContent = h;
    if (msgBtnText) msgBtnText.textContent = 'MESSAGE ' + h;
    if (campusEl) campusEl.textContent = (preloadedData.campus || 'North City University').toUpperCase();
    var fallbackAv = 'https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(rawH) + '&backgroundColor=18181b,27272a&textColor=f59e0b';
    if (avatarEl) {
      if (preloadedData.avatar_url && !preloadedData.avatar_url.includes('dicebear')) {
        avatarEl.src = preloadedData.avatar_url;
        avatarEl.style.display = 'block';
        if (initialsEl) initialsEl.style.display = 'none';
      } else {
        avatarEl.style.display = 'none';
        if (initialsEl) initialsEl.style.display = 'block';
      }
    }
  }

  if (momentsGrid) momentsGrid.innerHTML = '<div class="col-span-3 text-center py-8 text-xs text-zinc-500 font-mono-tag animate-pulse">LOADING MOMENTS...</div>';
  if (emptyMoments) emptyMoments.style.display = 'none';

  // Fetch full details and moments from backend
  var res = await apiRequest('/api/user/profile?user_id=' + encodeURIComponent(userId));
  if (res && res.success && res.user) {
    var u = res.user;
    var rawName = (u.name || 'Student').toUpperCase();
    var rawHandle = (u.handle || u.username || 'user').replace('@', '');
    var cleanHandle = '@' + rawHandle.toUpperCase();
    var fallbackAv = 'https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(rawHandle) + '&backgroundColor=18181b,27272a&textColor=f59e0b';
    var finalAvatar = (u.avatar || u.avatar_url) ? (u.avatar || u.avatar_url) : fallbackAv;

    if (nameEl) nameEl.textContent = rawName;
    if (initialsEl) initialsEl.textContent = rawName.substring(0, 2);
    if (usernameEl) usernameEl.textContent = cleanHandle;
    
    var peerComm = (u.campus || u.community || 'North City Community').toUpperCase();
    var peerCity = (u.location_city || u.city || '').toUpperCase();
    var peerLoc = peerCity ? (peerComm + ' · ' + peerCity) : peerComm;
    if (campusEl) campusEl.textContent = '◉ ' + peerLoc;
    
    if (bioEl) bioEl.textContent = u.bio || 'Capturing ordinary days.';
    
    if (avatarEl) {
      if (u.avatar_url && !u.avatar_url.includes('dicebear')) {
        avatarEl.src = finalAvatar;
        avatarEl.style.display = 'block';
        if (initialsEl) initialsEl.style.display = 'none';
      } else {
        avatarEl.style.display = 'none';
        if (initialsEl) initialsEl.style.display = 'block';
      }
    }

    var streakDays = (u.streak != null ? u.streak : (u.streak_count || 1));
    if (streakEl) streakEl.textContent = streakDays + (streakDays === 1 ? ' DAY' : ' DAYS');
    var mCount = u.momentCount != null ? u.momentCount : (res.moments ? res.moments.length : 0);
    if (momentsCountEl) momentsCountEl.textContent = mCount;
    if (memoriesEl) memoriesEl.textContent = Math.max(1, Math.floor(mCount / 2));
    if (scoreEl) scoreEl.textContent = Math.round(u.authenticity_score || 100) + '%';

    if (onlineDot) {
      onlineDot.className = u.is_online 
        ? 'absolute bottom-1 right-1 w-3 h-3 rounded-full border-2 border-zinc-950 bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.9)] animate-pulse'
        : 'absolute bottom-1 right-1 w-3 h-3 rounded-full border-2 border-zinc-950 bg-zinc-600';
    }

    if (statusBadge) {
      statusBadge.innerHTML = u.is_online 
        ? '<span class="text-amber-500 font-bold">🟢 ACTIVE</span>'
        : '<span class="text-zinc-500">OFFLINE</span>';
    }

    // Handle two-way connection status
    state.activePeerUserId = u.id;
    state.activePeerConnectionStatus = u.connection_status || 'none';
    updatePeerConnectionUI(state.activePeerConnectionStatus);

    if (msgBtn) {
      if (msgBtnText) msgBtnText.textContent = 'MESSAGE ' + cleanHandle;
      msgBtn.onclick = function() {
        openChatThread(u.id, u.name, cleanHandle, finalAvatar, u.is_online);
      };
    }

    // Render 3-column moments matching YOU page
    if (momentsGrid) {
      momentsGrid.innerHTML = '';
      if (!res.moments || res.moments.length === 0) {
        if (emptyMoments) emptyMoments.style.display = 'block';
      } else {
        if (emptyMoments) emptyMoments.style.display = 'none';
        res.moments.forEach(function(m) {
          var card = document.createElement('div');
          card.className = 'aspect-[4/5] bg-zinc-900 rounded-2xl overflow-hidden relative border border-zinc-800 shadow-md cursor-pointer hover:border-amber-500/40 transition active:scale-95 group select-none';
          var mainImg = m.main_img || m.mediaUrl || 'https://images.unsplash.com/photo-1541339907198-e08756dedf3f?auto=format&fit=crop&w=400&q=80';
          var pipImg = m.pip_img || finalAvatar;
          
          card.innerHTML =
            '<img src="' + mainImg + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
            (pipImg ? '<div class="absolute top-1.5 left-1.5 w-6 h-8 rounded-md overflow-hidden border border-white/20 shadow-md bg-black pointer-events-none"><img src="' + pipImg + '" class="w-full h-full object-cover"></div>' : '') +
            '<div class="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 bg-black/60 backdrop-blur rounded text-[8px] font-mono-tag text-zinc-300 font-bold pointer-events-none">' + escapeHtml(m.timeAgo || 'TODAY') + '</div>';

          card.onclick = function() {
            if (typeof openMomentDetail === 'function') {
              openMomentDetail(m);
            } else if (typeof openMomentDetailModal === 'function') {
              openMomentDetailModal(m.id || m.postId);
            }
          };

          momentsGrid.appendChild(card);
        });
      }
    }

    // Render THEIR COMMUNITIES section
    var commContainer = document.getElementById('peerProfileCommunitiesContainer');
    var commSection = document.getElementById('peerProfileCommunitiesSection');
    var emptyComm = document.getElementById('peerProfileEmptyCommunities');
    if (commContainer) {
      commContainer.innerHTML = '';
      var comms = res.communities || (u.communities || []);
      if (comms && comms.length > 0) {
        if (commSection) commSection.style.display = 'block';
        if (emptyComm) emptyComm.style.display = 'none';
        comms.forEach(function(c) {
          var crow = document.createElement('div');
          crow.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3 flex items-center justify-between hover:border-zinc-700 transition cursor-pointer shadow-md active:scale-95';
          var cType = (c.type || 'COMMUNITY').toUpperCase();
          var cIcon = c.icon || (cType === 'CAMPUS' ? '🎓' : cType === 'PLACE' ? '📍' : '📸');
          crow.innerHTML =
            '<div class="flex items-center gap-3 min-w-0">' +
              '<div class="w-8 h-8 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-sm flex-shrink-0">' +
                cIcon +
              '</div>' +
              '<div class="min-w-0">' +
                '<h4 class="text-xs font-bold text-white font-mono-tag truncate">◉ ' + escapeHtml(c.name) + '</h4>' +
                '<p class="text-[9px] text-zinc-400 font-mono-tag tracking-wider uppercase">' + escapeHtml(cType) + '</p>' +
              '</div>' +
            '</div>' +
            '<span class="text-[10px] text-zinc-500 font-mono-tag">→</span>';
          crow.onclick = function() {
            if (typeof openCampusPage === 'function') openCampusPage(c.name);
          };
          commContainer.appendChild(crow);
        });
      } else {
        if (emptyComm) emptyComm.style.display = 'block';
      }
    }
  }
}
window.openUserProfile = openUserProfile;

function updatePeerConnectionUI(status) {
  var connectText = document.getElementById('peerProfileConnectText');
  var connectBtn = document.getElementById('peerProfileConnectBtn');
  var iconBtn = document.getElementById('peerConnectIconBtn');
  var connectIcon = document.getElementById('peerProfileConnectIcon');

  if (!connectBtn) return;
  connectBtn.style.display = 'flex';

  if (status === 'connected') {
    if (connectText) connectText.textContent = 'CONNECTED';
    if (connectIcon) connectIcon.textContent = '✦';
    connectBtn.className = 'py-3 px-4 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 active:scale-[0.98] text-amber-400 font-extrabold text-[11px] rounded-2xl tracking-wider transition uppercase cursor-pointer font-mono-tag shadow-md flex items-center justify-center gap-1.5';
    if (iconBtn) iconBtn.innerHTML = '✦';
  } else if (status === 'pending_sent') {
    if (connectText) connectText.textContent = 'REQUESTED';
    if (connectIcon) connectIcon.textContent = '⏳';
    connectBtn.className = 'py-3 px-4 bg-zinc-900/90 border border-amber-500/50 text-amber-400 font-extrabold text-[11px] rounded-2xl tracking-wider transition uppercase cursor-pointer font-mono-tag shadow-md flex items-center justify-center gap-1.5 active:scale-95';
    if (iconBtn) iconBtn.innerHTML = '⏳';
  } else if (status === 'pending_received') {
    if (connectText) connectText.textContent = 'ACCEPT REQUEST';
    if (connectIcon) connectIcon.textContent = '✓';
    connectBtn.className = 'py-3 px-4 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[11px] rounded-2xl tracking-wider transition uppercase cursor-pointer font-mono-tag shadow-[0_4px_20px_rgba(245,158,11,0.35)] flex items-center justify-center gap-1.5 active:scale-95';
    if (iconBtn) iconBtn.innerHTML = '✓';
  } else if (status === 'self') {
    connectBtn.style.display = 'none';
  } else {
    if (connectText) connectText.textContent = 'CONNECT';
    if (connectIcon) connectIcon.textContent = '✦';
    connectBtn.className = 'py-3 px-4 bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[11px] rounded-2xl tracking-wider transition uppercase cursor-pointer font-mono-tag shadow-[0_4px_20px_rgba(245,158,11,0.35)] flex items-center justify-center gap-1.5 active:scale-95';
    if (iconBtn) iconBtn.innerHTML = '✦';
  }
}

async function togglePeerConnection() {
  if (!state.activePeerUserId) return;
  var currStatus = state.activePeerConnectionStatus || 'none';
  
  if (currStatus === 'none') {
    updatePeerConnectionUI('pending_sent');
    state.activePeerConnectionStatus = 'pending_sent';
    showToast('Connection request sent! ⏳');
    var res = await apiRequest('/api/friend/request', { method: 'POST', body: { target_user_id: state.activePeerUserId } });
    if (res && res.status) {
      state.activePeerConnectionStatus = res.status;
      updatePeerConnectionUI(res.status);
    }
  } else if (currStatus === 'pending_sent') {
    updatePeerConnectionUI('none');
    state.activePeerConnectionStatus = 'none';
    showToast('Connection request cancelled.');
    await apiRequest('/api/friend/cancel', { method: 'POST', body: { target_user_id: state.activePeerUserId } });
  } else if (currStatus === 'pending_received') {
    updatePeerConnectionUI('connected');
    state.activePeerConnectionStatus = 'connected';
    showToast('Connection accepted! ✦ +25 XP');
    await apiRequest('/api/friend/accept', { method: 'POST', body: { target_user_id: state.activePeerUserId } });
  } else if (currStatus === 'connected') {
    updatePeerConnectionUI('none');
    state.activePeerConnectionStatus = 'none';
    showToast('Connection removed.');
    await apiRequest('/api/friend/disconnect', { method: 'POST', body: { target_user_id: state.activePeerUserId } });
  }
}
window.togglePeerConnection = togglePeerConnection;

function handlePeerProfileBack() {
  switchScreenView(lastScreenBeforeProfile || 'search');
}
window.handlePeerProfileBack = handlePeerProfileBack;

function renderPlacesSearchResults(places, container) {
  var header = document.createElement('div');
  header.className = 'px-1 pt-3 pb-2 flex justify-between items-center text-[9px] font-mono-tag text-zinc-500 font-bold uppercase tracking-widest';
  header.innerHTML = '<span>CAMPUS SECTORS (' + places.length + ')</span>';
  container.appendChild(header);

  var group = document.createElement('div');
  group.className = 'space-y-2';

  places.forEach(function(pl) {
    var item = document.createElement('div');
    item.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex justify-between items-center shadow-lg hover:border-zinc-700 transition cursor-pointer active:scale-[0.99]';
    item.innerHTML =
      '<div class="flex items-center gap-3">' +
        '<span class="text-[10px] text-amber-500 font-mono-tag font-bold">' + pl.number + '</span>' +
        '<div>' +
          '<h3 class="text-xs font-bold text-white">' + escapeHtml(pl.name) + '</h3>' +
          '<span class="text-[9px] text-zinc-500 font-mono-tag">' + escapeHtml(pl.area || 'Location') + '</span>' +
        '</div>' +
      '</div>' +
      '<span class="text-[10px] text-zinc-400 font-mono-tag font-bold bg-zinc-900 border border-zinc-800 px-2.5 py-1 rounded-lg">' + pl.momentsCount + ' MOMENTS</span>';

    item.addEventListener('click', function() {
      filterBySector(pl.name);
    });

    group.appendChild(item);
  });

  container.appendChild(group);
}

function renderMomentsSearchResults(moments, container) {
  var header = document.createElement('div');
  header.className = 'px-1 pt-3 pb-2 flex justify-between items-center text-[9px] font-mono-tag text-zinc-500 font-bold uppercase tracking-widest';
  header.innerHTML = '<span>MATCHING MOMENTS (' + moments.length + ')</span>';
  container.appendChild(header);

  var group = document.createElement('div');
  group.className = 'space-y-4';

  moments.forEach(function(m) {
    var card = document.createElement('article');
    card.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3 shadow-xl';

    var mainImg = m.main_img || m.mainImg || 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=600&q=80';
    var pipImg = m.pip_img || m.pipImg || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&q=80';
    var author = escapeHtml(m.author_handle || m.user_handle || 'user');
    var campus = escapeHtml(m.campus || 'CAMPUS');
    var caption = escapeHtml(m.caption || 'Captured moment');
    var timeAgo = m.timeAgo || 'RECENT';

    card.innerHTML =
      '<div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner group select-none">' +
        '<img src="' + mainImg + '" class="w-full h-full object-cover">' +
        '<div class="absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black">' +
          '<img src="' + pipImg + '" class="w-full h-full object-cover">' +
        '</div>' +
      '</div>' +
      '<div class="space-y-1 px-0.5">' +
        '<div class="flex justify-between items-center text-[10px] text-zinc-400 font-mono-tag">' +
          '<span class="font-bold text-white">@' + author + ' · ' + campus.toUpperCase() + '</span>' +
          '<span>' + timeAgo + '</span>' +
        '</div>' +
        '<p class="text-xs text-zinc-200">"' + caption + '"</p>' +
      '</div>';

    group.appendChild(card);
  });

  container.appendChild(group);
}


// YOU / PROFILE & PERSONAL ARCHIVE MODULE
// =====================================================================
state.activeDetailMoment = null;
state.detailMomentFlipped = false;

async function loadYouScreen() {
  var data = await apiRequest('/api/me');
  if (!data || !data.success || !data.user) {
    data = await apiRequest('/api/user/profile');
  }

  if (data && (data.user || data.success)) {
    var u = data.user || {};
    var avatarEl = document.getElementById('youProfileAvatar');
    var initialsEl = document.getElementById('youProfileInitials');
    var nameEl = document.getElementById('youProfileName');
    var usernameEl = document.getElementById('youProfileUsername');
    var campusEl = document.getElementById('youProfileCampus');
    var bioEl = document.getElementById('youProfileBio');
    var streakVal = document.getElementById('youStreakVal');
    var momentsCountVal = document.getElementById('youMomentsCountVal');
    var memoriesCountVal = document.getElementById('youMemoriesCountVal');

    var finalName = u.name || (state.currentUser ? state.currentUser.name : 'Student');
    var finalHandle = u.username || u.handle || (state.currentUser ? state.currentUser.handle : 'user');
    finalHandle = finalHandle.replace('@', '');

    // Initials calculation (e.g. "ANIL" -> "AN", "Casey Mills" -> "CM")
    var parts = finalName.trim().split(/\s+/);
    var inits = '';
    if (parts.length >= 2) {
      inits = (parts[0][0] + parts[1][0]).toUpperCase();
    } else if (finalName.length >= 2) {
      inits = finalName.substring(0, 2).toUpperCase();
    } else {
      inits = (finalName[0] || 'K').toUpperCase();
    }

    if (initialsEl) initialsEl.textContent = inits;
    if (u.avatar_url && !u.avatar_url.includes('api.dicebear.com')) {
      if (avatarEl) {
        avatarEl.src = u.avatar_url;
        avatarEl.style.display = 'block';
      }
      if (initialsEl) initialsEl.style.display = 'none';
    } else {
      if (avatarEl) avatarEl.style.display = 'none';
      if (initialsEl) initialsEl.style.display = 'block';
    }

    if (nameEl) nameEl.textContent = finalName.toUpperCase();
    if (usernameEl) usernameEl.textContent = '@' + finalHandle.toUpperCase();
    
    var commName = (u.campus || u.community || (state.currentUser ? state.currentUser.campus : 'North City Community')).toUpperCase();
    var cityName = (u.location_city || u.city || (state.currentUser ? (state.currentUser.location_city || state.currentUser.city) : '')).toUpperCase();
    var fullLoc = cityName ? (commName + ' · ' + cityName) : commName;
    if (campusEl) campusEl.textContent = '◉ ' + fullLoc;
    
    if (bioEl) bioEl.textContent = u.bio || 'Capturing ordinary days.';
    
    var sNum = (u.streak != null ? u.streak : (u.streak_count != null ? u.streak_count : 1));
    if (streakVal) streakVal.textContent = sNum + (sNum === 1 ? ' DAY' : ' DAYS');
    if (momentsCountVal) momentsCountVal.textContent = (u.momentCount != null ? u.momentCount : (state.myMoments ? state.myMoments.length : 1));
    if (memoriesCountVal) memoriesCountVal.textContent = (u.memoryCount != null ? u.memoryCount : (state.myMoments ? state.myMoments.length : 1));

    // Update Pending Requests Badge
    var reqBadge = document.getElementById('youRequestsBadge');
    if (reqBadge) {
      var reqCount = u.pending_requests_count || 0;
      if (reqCount > 0) {
        reqBadge.textContent = reqCount;
        reqBadge.style.display = 'flex';
      } else {
        reqBadge.style.display = 'none';
      }
    }

    // Render Dynamic TODAY card (Captured vs Capture Prompt)
    renderYouTodayCard(u);
    if (u.has_captured_today && typeof markDailyAlertCompleted === 'function') {
      markDailyAlertCompleted();
    }

    // Render Dynamic Communities
    renderYouCommunitiesList(u.joined_communities || []);

    // Render Dynamic Hosted Drops (Conditional Creator Activity)
    renderYouHostedDrops(u.hosted_drops || []);

    var editName = document.getElementById('modalEditName');
    var editBio = document.getElementById('modalEditBio');
    var editCampus = document.getElementById('modalEditCampus');
    if (editName) editName.value = finalName;
    if (editBio) editBio.value = u.bio || 'Capturing ordinary days.';
    if (editCampus) editCampus.value = u.campus || 'North City University';

    await loadMyMoments();
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
    var isHost = c.is_owner || c.role === 'owner' || (state.currentUser && (c.creator_id === state.currentUser.id || c.creator_handle === state.currentUser.handle));

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

function renderYouHostedDrops(drops) {
  var section = document.getElementById('youCreatorActivitySection');
  var container = document.getElementById('youHostedDropsContainer');
  if (!section || !container) return;

  if (!drops || drops.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  container.innerHTML = '';

  drops.slice(0, 3).forEach(function(d) {
    var card = document.createElement('div');
    card.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3 flex items-center justify-between hover:border-zinc-700 transition cursor-pointer shadow-md active:scale-95';
    
    var regCount = d.registered_count || 0;
    var cap = d.capacity || 20;

    card.innerHTML =
      '<div class="space-y-0.5 min-w-0">' +
        '<span class="text-[8px] text-amber-500 font-mono-tag tracking-widest uppercase font-bold block">HOSTING</span>' +
        '<h4 class="text-xs font-extrabold text-white font-mono-tag truncate">' + escapeHtml(d.title) + '</h4>' +
        '<p class="text-[10px] text-zinc-400 font-mono-tag">₹' + (d.price || 19) + ' · ' + regCount + '/' + cap + ' joined</p>' +
      '</div>' +
      '<button class="px-2.5 py-1.5 bg-zinc-900 border border-zinc-700 text-amber-400 font-mono-tag text-[9px] font-bold rounded-lg uppercase cursor-pointer hover:bg-zinc-800">MANAGE DROP</button>';

    card.onclick = function() {
      if (typeof openCampusPage === 'function') openCampusPage(d.community_name);
    };
    container.appendChild(card);
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
  container.innerHTML = '';
  if (!moments || moments.length === 0) {
    container.innerHTML =
      '<div class="w-full bg-zinc-950 border border-zinc-800/60 rounded-2xl p-4 text-center space-y-2 font-mono-tag">' +
        '<p class="text-xs font-bold text-white uppercase">Your first Moment starts here.</p>' +
        '<p class="text-[10px] text-zinc-500">Capture the raw unedited life around you.</p>' +
        '<button class="mt-1 px-4 py-1.5 bg-amber-500 hover:bg-amber-400 text-black text-[10px] font-extrabold rounded-xl transition cursor-pointer active:scale-95 uppercase" onclick="openCameraStudio()">CAPTURE NOW</button>' +
      '</div>';
    return;
  }

  moments.slice(0, 5).forEach(function(m) {
    var card = document.createElement('div');
    card.className = 'w-24 h-32 flex-shrink-0 bg-zinc-950 border border-zinc-800 rounded-2xl overflow-hidden relative shadow-md group cursor-pointer active:scale-95 transition-all';
    
    var timeBadgeColor = (m.timeAgo === 'TODAY' || m.time_ago === 'TODAY') ? 'text-amber-400' : 'text-zinc-300';
    var timeAgoText = escapeHtml(m.timeAgo || m.time_ago || 'TODAY');

    card.innerHTML =
      '<img src="' + escapeHtml(m.mediaUrl || m.mainImg || m.main_img || '') + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
      '<div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent pointer-events-none"></div>' +
      '<span class="absolute bottom-1.5 left-1.5 text-[8px] ' + timeBadgeColor + ' font-mono-tag px-1.5 py-0.5 rounded backdrop-blur-md font-bold truncate max-w-[85px]">' +
        timeAgoText +
      '</span>';

    card.addEventListener('click', function() {
      openMomentDetail(m);
    });
    container.appendChild(card);
  });

  // Trailing View All Tile
  var viewAllTile = document.createElement('div');
  viewAllTile.className = 'w-20 h-32 flex-shrink-0 bg-zinc-950 border border-zinc-800 rounded-2xl overflow-hidden relative shadow-md flex flex-col items-center justify-center text-zinc-400 hover:text-white cursor-pointer transition-colors font-mono-tag active:scale-95';
  viewAllTile.innerHTML =
    '<span class="text-base font-bold tracking-widest text-amber-500">···</span>' +
    '<span class="text-[8px] font-bold uppercase mt-1 text-zinc-400">VIEW ALL</span>';
  viewAllTile.addEventListener('click', openMemoryArchive);
  container.appendChild(viewAllTile);
}

function renderMomentsGrid(moments, grid) {
  grid.innerHTML = '';
  if (!moments || moments.length === 0) {
    grid.innerHTML =
      '<div class="col-span-3 text-center py-8 space-y-1">' +
        '<p class="text-xs font-bold text-white font-mono-tag">NOTHING CAPTURED YET</p>' +
        '<p class="text-[10px] text-zinc-500 font-mono-tag">Your first Moment will appear here.</p>' +
      '</div>';
    return;
  }

  moments.slice(0, 5).forEach(function(m) {
    var tile = document.createElement('div');
    tile.className = 'aspect-[4/5] bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden relative shadow-md group cursor-pointer active:scale-95 transition-all';
    
    var timeBadgeColor = (m.timeAgo === 'TODAY' || m.time_ago === 'TODAY') ? 'text-amber-400' : 'text-zinc-300';
    var timeAgoText = escapeHtml(m.timeAgo || m.time_ago || 'TODAY');

    tile.innerHTML =
      '<img src="' + escapeHtml(m.mediaUrl || m.mainImg || m.main_img || '') + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">' +
      '<span class="absolute bottom-1.5 left-1.5 text-[8px] ' + timeBadgeColor + ' font-mono-tag bg-black/80 px-1.5 py-0.5 rounded backdrop-blur-md font-bold">' +
        timeAgoText +
      '</span>';

    tile.addEventListener('click', function() {
      openMomentDetail(m);
    });
    grid.appendChild(tile);
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
                      if (hb.pendingRequestsCount > 0) {
                          youReqBadge.textContent = hb.pendingRequestsCount;
                          youReqBadge.style.display = 'flex';
                      } else {
                          youReqBadge.style.display = 'none';
                      }
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

      if (state.activeScreen === 'chat') {
          loadChatConversations(true);
      } else if (state.activeScreen === 'chat-conversation' && state.activeChatUser) {
          loadChatMessages(state.activeChatUser, true);
      } else if (state.activeScreen === 'notifications') {
          loadNotifications();
      }
  }, 3000);

  // 6. Register Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }

  // 7. Simulate OS Push Notification for Daily Mission
  setTimeout(function() {
    var push = document.getElementById('osPushNotification');
    if (push) {
      push.classList.remove('-translate-y-[150%]');
      setTimeout(function() {
        push.classList.add('-translate-y-[150%]');
      }, 7000);
    }
  }, 4000);
});

// === EVENT DETAIL SCREEN ===
async function openEventDetail(eventId) {
  state.previousScreen = state.activeScreen;
  state.activeEventId = eventId;
  
  // Show loading state or skeleton here if needed
  
  var data = await apiRequest('/api/event?id=' + eventId);
  if (data && data.success) {
      var ev = data.event;
      document.getElementById('eventDetailName').textContent = ev.name;
      document.getElementById('eventDetailNameSmall').textContent = ev.name;
      document.getElementById('eventDetailCampus').textContent = "NORTH CITY UNIVERSITY";
      document.getElementById('eventDetailTime').textContent = ev.start_time;
      document.getElementById('eventDetailSummary').textContent = ev.summary || 'Tap to explore';
      
      // Calculate time ago
      var diffMins = Math.floor((new Date() - new Date(ev.created_at)) / 60000);
      document.getElementById('eventDetailStartAgo').textContent = (diffMins > 0 ? diffMins : 1) + " MIN AGO";
      
      document.getElementById('eventDetailLocation').textContent = ev.location || 'Campus';
      document.getElementById('eventDetailWhere').textContent = ev.location || 'Campus';
      document.getElementById('eventDetailWhen').textContent = ev.start_time;
      document.getElementById('eventDetailDesc').textContent = ev.description;
      document.getElementById('eventDetailCover').src = ev.cover_image;
      
      var momentsContainer = document.getElementById('eventDetailMomentsContainer');
      document.getElementById('eventDetailCount').textContent = "Approximately " + (data.moments.length * 15 + 30) + " people nearby";
      
      if (data.moments && data.moments.length > 0) {
          momentsContainer.innerHTML = '';
          data.moments.forEach(function(m) {
              var mHtml = `
              <article class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3 shadow-xl">
                  <div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner">
                      <img src="${escapeHtml(m.main_img)}" class="w-full h-full object-cover">
                      <div class="absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black">
                          <img src="${escapeHtml(m.pip_img)}" class="w-full h-full object-cover">
                      </div>
                  </div>
                  <div class="flex justify-between items-center px-0.5 pt-1 font-mono-tag">
                      <span class="text-[10px] text-zinc-400 font-bold uppercase">${escapeHtml(ev.location)} · ${escapeHtml(m.timeAgo)}</span>
                      <span class="text-[11px] text-amber-400 font-medium">@${escapeHtml(m.author_handle)}</span>
                  </div>
              </article>`;
              momentsContainer.insertAdjacentHTML('beforeend', mHtml);
          });
      } else {
          momentsContainer.innerHTML = '<div class="text-center text-zinc-500 text-[10px] py-4">No moments captured yet.</div>';
      }
      
      switchScreenView('event-detail');
  }
}

function closeEventDetail() {
  state.activeEventId = null;
  switchScreenView(state.previousScreen || 'feed');
}

function captureEventMoment() {
  // We can pass context to camera by setting activeEventId
  openCameraStudio();
}
window.openEventDetail = openEventDetail;
window.closeEventDetail = closeEventDetail;
window.captureEventMoment = captureEventMoment;


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
    <p>• <strong>Fair Creator Value:</strong> Real-world activities & drops with a fair 90% creator / 10% platform split.</p>
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

    selectGoogleAccount(email, name, 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=300&q=80');
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

    var nameVal = (nameInput && nameInput.value.trim()) || (state.onboardingSession && state.onboardingSession.profile && state.onboardingSession.profile.name) || 'Student';
    var emailVal = (emailInput && emailInput.value.trim()) || (state.onboardingSession && state.onboardingSession.profile && state.onboardingSession.profile.email) || 'student@kandid.app';
    var handleVal = (usernameInput && usernameInput.value.trim().replace('@', '')) || (state.onboardingSession && state.onboardingSession.handle) || 'user';
    var campusVal = (state.onboardingSession && state.onboardingSession.campusName) || 'Not specified';
    var cityVal = (state.onboardingSession && state.onboardingSession.city) || 'Not specified';

    var rName = document.getElementById('reviewNameDisplay');
    var rHandle = document.getElementById('reviewHandleDisplay');
    var rEmail = document.getElementById('reviewEmailDisplay');
    var rCampus = document.getElementById('reviewCampusDisplay');
    var rCity = document.getElementById('reviewCityDisplay');
    var rAvatarBox = document.getElementById('reviewAvatarBox');
    var rAvatarLetter = document.getElementById('reviewAvatarLetter');

    if (rName) rName.textContent = nameVal;
    if (rHandle) rHandle.textContent = '@' + handleVal;
    if (rEmail) rEmail.textContent = emailVal;
    if (rCampus) rCampus.textContent = campusVal;
    if (rCity) rCity.textContent = cityVal;

    if (rAvatarBox) {
        if (state.onboardAvatarData) {
            rAvatarBox.innerHTML = '<img src="' + escapeHtml(state.onboardAvatarData) + '" class="w-full h-full object-cover">';
        } else {
            rAvatarBox.innerHTML = '<span>' + escapeHtml((nameVal[0] || 'K').toUpperCase()) + '</span>';
        }
    }
}

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
            } else {
                // If token invalid, force login
                localStorage.removeItem('kandid_token');
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
            state.token = res.token;
            state.currentUser = res.user;
            showToast('Welcome back, ' + res.user.name + '! 🎉');
            
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
    
    var avatarSrc = u.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(u.handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
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
// MEMORIES / PERSONAL ARCHIVE LOADER
// =====================================================================
async function loadMemoriesScreen() {
  var container = document.getElementById('memoriesListContainer');
  if (!container) return;

  container.innerHTML = '<div class="text-center py-8 text-xs text-zinc-500 font-mono-tag animate-pulse">ARCHIVING MOMENTS...</div>';

  var data = await apiRequest('/api/me/memories');
  if (data && data.success && Array.isArray(data.moments)) {
    // Update top counts
    var momentsVal = document.getElementById('memoriesMomentsVal');
    var streakVal = document.getElementById('memoriesStreakVal');
    var archivedVal = document.getElementById('memoriesArchivedVal');

    if (momentsVal) momentsVal.textContent = data.moments.length;
    if (streakVal) streakVal.textContent = (state.currentUser && state.currentUser.streak ? state.currentUser.streak : '1') + ' DAYS';
    if (archivedVal) archivedVal.textContent = data.moments.length;

    container.innerHTML = '';
    if (data.moments.length === 0) {
      container.innerHTML = 
        '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-8 text-center space-y-3">' +
          '<div class="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-lg">📷</div>' +
          '<h3 class="text-xs font-bold text-white uppercase font-mono-tag">NO MEMORIES YET</h3>' +
          '<p class="text-[11px] text-zinc-400">Capture moments during daily windows to build your unfiltered archive.</p>' +
          '<button class="mt-2 px-4 py-2 bg-amber-500 text-black font-bold text-xs rounded-xl font-mono-tag uppercase" onclick="openCameraStudio()">CAPTURE FIRST MOMENT</button>' +
        '</div>';
      return;
    }

    data.moments.forEach(function(m) {
      var card = document.createElement('article');
      card.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex flex-col gap-3 shadow-xl';
      
      var mainImg = m.mainImg || m.main_img || 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=600&q=80';
      var pipImg = m.pipImg || m.pip_img || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80';
      var location = escapeHtml(m.locationCity || m.campus || 'CAMPUS');
      var caption = escapeHtml(m.caption || 'Captured as it happened.');
      var timeStr = m.timeAgo || 'RECENT';

      card.innerHTML = 
        '<div class="w-full aspect-[4/5] bg-black rounded-xl relative overflow-hidden border border-zinc-800 shadow-inner">' +
          '<img src="' + mainImg + '" class="w-full h-full object-cover">' +
          '<div class="absolute top-3 left-3 w-20 h-28 rounded-lg overflow-hidden border-2 border-white/20 shadow-2xl bg-black">' +
            '<img src="' + pipImg + '" class="w-full h-full object-cover">' +
          '</div>' +
        '</div>' +
        '<div class="space-y-1.5 px-0.5">' +
          '<div class="flex justify-between items-center text-[10px] text-zinc-400 font-mono-tag">' +
            '<span class="font-bold text-white">' + location.toUpperCase() + '</span>' +
            '<span>' + timeStr + '</span>' +
          '</div>' +
          '<p class="text-xs text-zinc-300 font-normal">"' + caption + '"</p>' +
        '</div>';

      container.appendChild(card);
    });
  }
}
window.loadMemoriesScreen = loadMemoriesScreen;

// =====================================================================
// SETTINGS & DATA EXPORT MODULE (INTERACTIVE & PERSISTENT)
// =====================================================================
var defaultSettings = {
  moment_reminders: true,
  messages: true,
  community_activity: true,
  sound: true,
  haptics: true,
  data_saver: false
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
  var dropsCountEl = document.getElementById('creatorDashDropsCount');
  var attendeesCountEl = document.getElementById('creatorDashAttendeesCount');
  var checkinsCountEl = document.getElementById('creatorDashCheckinsCount');
  var commsListEl = document.getElementById('creatorDashCommunitiesList');
  var dropsListEl = document.getElementById('creatorDashDropsList');
  var shareEl = document.getElementById('creatorDashEarningsShare');
  var settledEl = document.getElementById('creatorDashEarningsSettled');

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
    var earn = res.earnings || {};

    if (spacesCountEl) spacesCountEl.textContent = ov.spaces_managed || 0;
    if (dropsCountEl) dropsCountEl.textContent = ov.active_drops || 0;
    if (attendeesCountEl) attendeesCountEl.textContent = ov.total_attendees || 0;
    if (checkinsCountEl) checkinsCountEl.textContent = ov.verified_checkins || 0;

    if (shareEl) shareEl.textContent = '₹' + Number(earn.creator_earnings_rupees || 0).toFixed(2);
    if (settledEl) settledEl.textContent = '₹' + Number(earn.settled_rupees || 0).toFixed(2);

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

    // Hosted Drops
    if (dropsListEl) {
      var drops = res.drops || [];
      if (drops.length > 0) {
        dropsListEl.innerHTML = drops.map(function(d) {
          var st = d.lifecycle_state || 'DRAFT';
          var isLive = st === 'LIVE' || st === 'CHECK_IN';
          var badgeColor = isLive ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' : 'text-amber-400 bg-amber-500/10 border-amber-500/30';
          return '<div class="p-3 rounded-2xl bg-zinc-950 border border-white/[.06] space-y-2 text-xs">' +
            '<div class="flex justify-between items-start gap-2">' +
              '<div class="min-w-0">' +
                '<span class="text-white font-bold block truncate">' + escapeHtml(d.title) + '</span>' +
                '<span class="text-[9px] font-mono-tag text-zinc-500 block truncate">' + escapeHtml(d.community_name || 'Community') + ' · ' + escapeHtml(d.date_str || '') + ' ' + escapeHtml(d.time_str || '') + '</span>' +
              '</div>' +
              '<span class="text-[9px] font-mono-tag font-bold uppercase px-2 py-0.5 rounded border flex-shrink-0 ' + badgeColor + '">' + escapeHtml(st) + '</span>' +
            '</div>' +
            '<div class="flex items-center justify-between text-[10px] font-mono-tag text-zinc-400 pt-1.5 border-t border-zinc-900">' +
              '<span>' + (d.registered_count || 0) + ' / ' + (d.capacity || 20) + ' Registered (' + (d.checked_in_count || 0) + ' Checked In)</span>' +
              '<button onclick="closeCreatorDashboardModal(); openDropExperience(\'' + escapeHtml(d.id) + '\')" class="text-amber-400 hover:text-amber-300 font-bold">VIEW DROP ›</button>' +
            '</div>' +
          '</div>';
        }).join('');
      } else {
        dropsListEl.innerHTML = '<div class="p-3 text-center text-xs text-zinc-500 font-mono-tag rounded-xl bg-zinc-950/60 border border-white/[.04]">No active drops. Schedule a drop to bring people together.</div>';
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
    }
    var userEl = document.getElementById('settingsUsername');
    var campusEl = document.getElementById('settingsCampus');
    if (userEl) userEl.textContent = '@' + (u.handle || u.username || 'user');
    if (campusEl) campusEl.textContent = u.campus || 'North City University';
    if (typeof renderSettingsCreatorSection === 'function') {
      renderSettingsCreatorSection(u);
    }
  } else if (state.currentUser && typeof renderSettingsCreatorSection === 'function') {
    renderSettingsCreatorSection(state.currentUser);
  }

  var settingKeys = ['moment_reminders', 'messages', 'community_activity', 'sound', 'haptics', 'data_saver'];
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
  localStorage.removeItem('kandid_token');
  localStorage.removeItem('kandid_onboarded');
  localStorage.removeItem('kandid_user');
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
      if (reqs.length > 0) {
        youBadge.textContent = reqs.length;
        youBadge.style.display = 'flex';
      } else {
        youBadge.style.display = 'none';
      }
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
      
      var avSrc = r.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(r.handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
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

      var avatarSrc = n.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(n.actor_handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
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
        } else if (nType.includes('drop')) {
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

async function checkChatUnreadBadge() {
  if (!state.currentUser) return;
  try {
    var data = await apiRequest('/api/chat/unread-count');
    var badge = document.getElementById('chatUnreadBadge');
    if (badge) {
      if (data && data.success && data.count > 0) {
        badge.textContent = data.count > 99 ? '99+' : data.count;
        badge.classList.remove('hidden');
        badge.style.display = 'flex';
      } else {
        badge.classList.add('hidden');
        badge.style.display = 'none';
      }
    }
  } catch(e){}
}
window.checkChatUnreadBadge = checkChatUnreadBadge;

async function loadChatConversations(isSilent = false) {
  var container = document.getElementById('chatHomeList');
  if (!container) return;

  if (!isSilent) {
      container.innerHTML = '<div class="text-center py-6 text-xs text-zinc-500 font-mono-tag animate-pulse">SYNCING PEERS & CHATS...</div>';
  }

  var data = await apiRequest('/api/chat/conversations');
  if (data && data.success && Array.isArray(data.conversations)) {
    var convos = data.conversations;
    
    var newDataStr = JSON.stringify(convos);
    if (isSilent && container.dataset.lastData === newDataStr) {
        return; // No changes, skip DOM rebuild
    }
    container.dataset.lastData = newDataStr;
    container.innerHTML = '';

    if (convos.length === 0) {
      container.innerHTML = 
        '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-8 text-center space-y-3">' +
          '<div class="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-amber-500 mx-auto text-lg">💬</div>' +
          '<h3 class="text-xs font-bold text-white uppercase font-mono-tag">NO CHATS YET</h3>' +
          '<p class="text-[11px] text-zinc-400">Connect with people in your community to start a conversation!</p>' +
          '<button class="mt-2 px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded-xl font-mono-tag uppercase cursor-pointer" onclick="switchChatSubTab(\'friends\')">👥 VIEW CONNECTED FRIENDS</button>' +
        '</div>';
      return;
    }

    convos.forEach(function(c) {
      var item = document.createElement('div');
      var hasUnread = (c.unreadCount && c.unreadCount > 0);
      item.className = 'bg-zinc-950 border border-zinc-800/80 rounded-2xl p-3.5 flex items-center justify-between shadow-md cursor-pointer hover:bg-zinc-900/50 transition-all ' + (hasUnread ? 'border-amber-500/40 bg-zinc-950/90' : '');

      var avatarSrc = c.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(c.handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
      var name = escapeHtml(c.name || 'Classmate');
      var handle = escapeHtml(c.handle || 'user');
      var campus = escapeHtml(c.campus || 'North City University');
      var lastMsg = escapeHtml(c.lastMessage || 'Tap to start conversation');

      var isOnline = c.is_online || isUserOnline(c.last_active);
      var statusBadge = isOnline ? 
        '<span class="text-[9px] text-amber-500 font-bold font-mono-tag flex-shrink-0 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>ACTIVE</span>' : 
        '<span class="text-[9px] text-zinc-600 font-mono-tag flex-shrink-0">OFFLINE</span>';

      var unreadPill = hasUnread ?
        '<span class="min-w-[18px] h-[18px] px-1 bg-amber-500 text-black text-[9px] font-black font-mono-tag rounded-full flex items-center justify-center shadow-md flex-shrink-0 ml-2">' + c.unreadCount + '</span>' : '';

      item.innerHTML = 
        '<div class="flex items-center gap-3.5 flex-1 min-w-0">' +
          '<div class="w-12 h-12 rounded-full bg-zinc-900 overflow-hidden border border-zinc-800 flex-shrink-0 relative">' +
            '<img src="' + avatarSrc + '" class="w-full h-full object-cover">' +
            (isOnline ? '<div class="absolute bottom-0 right-0 w-3 h-3 bg-amber-500 border-2 border-zinc-950 rounded-full shadow-[0_0_8px_rgba(245,158,11,0.8)]"></div>' : '') +
          '</div>' +
          '<div class="flex-1 min-w-0">' +
            '<div class="flex justify-between items-baseline mb-0.5">' +
              '<h3 class="text-xs font-bold text-white truncate ' + (hasUnread ? 'text-amber-400' : '') + '">' + name + '</h3>' +
              '<div class="flex items-center gap-1.5">' + statusBadge + unreadPill + '</div>' +
            '</div>' +
            '<p class="text-[11px] ' + (hasUnread ? 'text-zinc-100 font-medium' : 'text-zinc-400') + ' truncate">' + lastMsg + '</p>' +
          '</div>' +
        '</div>';

      item.addEventListener('click', function() {
        openChatThread(c.id, name, '@' + handle, avatarSrc, isOnline);
      });

      container.appendChild(item);
    });
  }
}
window.loadChatConversations = loadChatConversations;

function openChatThread(userId, name, handle, avatarUrl, isOnline) {
  state.activeChatUser = userId;

  var headerAvatar = document.getElementById('headerChatAvatar');
  var headerName = document.getElementById('headerChatName');
  var headerHandle = document.getElementById('headerChatHandle') || document.getElementById('headerChatStatus');
  
  var cleanHandle = handle ? (handle.startsWith('@') ? handle : '@' + handle) : '@student';
  var fallbackAvatar = 'https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(cleanHandle.replace('@', '') || name || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b';

  if (headerAvatar) {
    headerAvatar.src = (avatarUrl && avatarUrl.trim()) ? avatarUrl : fallbackAvatar;
  }
  if (headerName) {
    headerName.textContent = name || 'Student';
  }
  
  if (headerHandle) {
      if (isOnline) {
          headerHandle.innerHTML = '<span class="text-amber-500 font-bold flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse inline-block"></span>ACTIVE</span> <span class="text-zinc-600">·</span> <span class="text-zinc-400">' + escapeHtml(cleanHandle) + '</span>';
      } else {
          headerHandle.innerHTML = '<span class="text-zinc-500 font-mono-tag">OFFLINE</span> <span class="text-zinc-600">·</span> <span class="text-zinc-400 font-mono-tag">' + escapeHtml(cleanHandle) + '</span>';
      }
  }

  switchScreenView('chat-conversation');
  loadChatMessages(userId);
  checkChatUnreadBadge();
}
window.openChatThread = openChatThread;

async function loadChatMessages(userId, isSilent = false) {
  var container = document.getElementById('chatMessageHistoryV2');
  if (!container) return;

  if (!isSilent && (!container.children.length || container.innerText.includes('LOADING'))) {
      container.innerHTML = '<div class="text-center py-4 text-[10px] text-zinc-500 font-mono-tag">ENCRYPTED CAMPUS CHAT • LOADING...</div>';
  }

  var myUid = getActiveUserId();
  var data = await apiRequest('/api/chat/messages?chat_id=' + encodeURIComponent(userId) + '&user_id=' + encodeURIComponent(myUid));
  if (data && data.success && Array.isArray(data.messages)) {
    if (data.resolved_user_id) {
      localStorage.setItem('kandid_active_uid', data.resolved_user_id);
    }
    // Only rebuild DOM if new messages or read receipts state changed
    var msgSignature = JSON.stringify(data.messages.map(function(m){ return m.id + '_' + (m.read_at ? '1' : '0'); }));
    if (isSilent && container.dataset.msgSig === msgSignature) {
        return; 
    }
    container.dataset.msgSig = msgSignature;

    if (data.messages.length === 0) {
      container.innerHTML = 
        '<div class="text-center py-10 space-y-1 my-auto">' +
          '<span class="text-2xl block">👋</span>' +
          '<p class="text-xs text-white font-bold font-mono-tag uppercase">START OF THE CONVERSATION</p>' +
          '<p class="text-[10px] text-zinc-500 font-mono-tag">Say hi! Messages are private to you two.</p>' +
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
      
      // Calculate date divider
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

      var bubble = document.createElement('div');
      bubble.className = isMe ? 'flex justify-end' : 'flex justify-start';
      bubble.dataset.msgId = m.id;

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
      
      // Single Tick (✓) for Sent, Double Tick (✓✓) for Seen/Read
      var statusIcon = '';
      if (isMe) {
        if (m.read_at) {
          statusIcon = '<span class="text-[9px] text-amber-950 font-bold ml-1 font-mono-tag" title="Seen">✓✓</span>';
        } else {
          statusIcon = '<span class="text-[9px] text-black/60 font-bold ml-1 font-mono-tag" title="Delivered">✓</span>';
        }
      }

      bubble.innerHTML = 
        '<div class="max-w-[78%] rounded-2xl px-4 py-2 text-xs ' + bubbleStyle + ' shadow-sm space-y-0.5">' +
          '<p class="leading-relaxed">' + escapeHtml(m.content) + '</p>' +
          '<div class="flex items-center justify-end gap-1 opacity-80 pt-0.5">' +
            '<span class="text-[8px] font-mono-tag">' + timeOnly + '</span>' +
            statusIcon +
          '</div>' +
        '</div>';

      container.appendChild(bubble);
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
  input.value = '';

  var myUid = getActiveUserId();
  var container = document.getElementById('chatMessageHistoryV2');
  var tempBubble = null;
  if (container) {
    if (container.innerText.includes('START OF THE CONVERSATION') || container.innerText.includes('ENCRYPTED CAMPUS CHAT')) {
      container.innerHTML = '';
    }

    tempBubble = document.createElement('div');
    tempBubble.className = 'flex justify-end';
    var timeNow = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    tempBubble.innerHTML = 
      '<div class="max-w-[78%] rounded-2xl px-4 py-2 text-xs bg-amber-500 text-black font-medium shadow-sm space-y-0.5">' +
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
        content: text
      })
    });

    if (res && res.success) {
      if (tempBubble && res.message && res.message.id) {
        tempBubble.dataset.msgId = res.message.id;
      }
      await loadChatMessages(state.activeChatUser, true);
      checkChatUnreadBadge();
    } else {
      showToast('Message send failed. Please check connection.');
    }
  } catch (err) {
    console.error('Chat send error:', err);
    showToast('Failed to send message.');
  }
}
window.sendChatMessageV2 = sendChatMessageV2;

// Background Real-Time Poller for Chat & Notifications
if (window.chatSyncGlobalInterval) clearInterval(window.chatSyncGlobalInterval);
window.chatSyncGlobalInterval = setInterval(function() {
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
  if (state.currentUser && state.token) {
    apiRequest('/api/auth/ping').catch(function(){});
  }
}, 45000);

// =====================================================================
// EDIT PROFILE & USER UPDATE SYSTEM
// =====================================================================
var pendingEditAvatarData = '';

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

  if (state.currentUser) {
    if (nameInp) nameInp.value = state.currentUser.name || '';
    if (userInp) userInp.value = (state.currentUser.handle || state.currentUser.username || '').replace('@', '');
    if (bioInp) bioInp.value = state.currentUser.bio || 'Capturing ordinary days.';
    if (campusInp) campusInp.value = state.currentUser.campus || state.currentUser.community || 'North City Community';
    if (cityInp) cityInp.value = state.currentUser.location_city || state.currentUser.city || 'Supaul, Bihar';
    if (vibeInp) vibeInp.value = state.currentUser.vibe || 'Creator';
    
    var curAvatar = state.currentUser.avatar_url || state.currentUser.avatar || '';
    if (curAvatar && !curAvatar.includes('api.dicebear.com')) {
      if (previewImg) {
        previewImg.src = curAvatar;
        previewImg.style.display = 'block';
      }
      if (initsEl) initsEl.style.display = 'none';
    } else {
      if (previewImg) previewImg.style.display = 'none';
      if (initsEl) {
        initsEl.style.display = 'block';
        initsEl.textContent = (state.currentUser.name ? state.currentUser.name.substring(0, 2).toUpperCase() : 'AN');
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

function closeEditProfileModal() {
  var modal = document.getElementById('editProfileModal');
  if (modal) modal.style.display = 'none';
  pendingEditAvatarData = '';
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
  if (modal) modal.style.display = 'flex';
}
window.openPrivacyModal = openPrivacyModal;

function closePrivacyModal() {
  var modal = document.getElementById('privacyModal');
  if (modal) modal.style.display = 'none';
}
window.closePrivacyModal = closePrivacyModal;

async function savePrivacySettings() {
  var mVis = document.querySelector('input[name="privacyMoments"]:checked');
  var msgVis = document.querySelector('input[name="privacyMessages"]:checked');
  var connVis = document.querySelector('input[name="privacyConnections"]:checked');

  var payload = {
    moments_visibility: mVis ? mVis.value : 'everyone',
    approximate_location: true,
    messages_from: msgVis ? msgVis.value : 'everyone',
    connections_from: connVis ? connVis.value : 'everyone'
  };

  var res = await apiRequest('/api/user/privacy', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (res && res.success) {
    showToast('Privacy preferences saved! 🔒');
    closePrivacyModal();
  } else {
    showToast('Privacy settings saved locally');
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
      
      var avatarSrc = f.avatar_url || ('https://api.dicebear.com/7.x/initials/svg?seed=' + encodeURIComponent(f.handle || 'user') + '&backgroundColor=18181b,27272a&textColor=f59e0b');
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
  var chatList = document.getElementById('chatHomeList');
  var friendsList = document.getElementById('connectedFriendsList');
  var btnChats = document.getElementById('tabBtnChats');
  var btnFriends = document.getElementById('tabBtnFriends');

  if (tab === 'friends') {
    if (chatList) chatList.style.display = 'none';
    if (friendsList) friendsList.style.display = 'block';
    if (btnChats) btnChats.className = 'flex-1 py-1.5 text-zinc-400 hover:text-white font-medium rounded-lg transition-all cursor-pointer';
    if (btnFriends) btnFriends.className = 'flex-1 py-1.5 bg-zinc-800 text-white font-bold rounded-lg shadow-sm transition-all cursor-pointer';
    loadConnectedFriends();
  } else {
    if (chatList) chatList.style.display = 'block';
    if (friendsList) friendsList.style.display = 'none';
    if (btnChats) btnChats.className = 'flex-1 py-1.5 bg-zinc-800 text-white font-bold rounded-lg shadow-sm transition-all cursor-pointer';
    if (btnFriends) btnFriends.className = 'flex-1 py-1.5 text-zinc-400 hover:text-white font-medium rounded-lg transition-all cursor-pointer';
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
    showToast('Connected! +25 XP 🎉');
    if (btnEl) {
      btnEl.className = 'px-3 py-1 bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 font-mono-tag text-[9px] font-bold rounded-lg';
      btnEl.textContent = '✓ CONNECTED';
    }
  } else {
    showToast('Could not connect: ' + (res ? res.error : 'Network error'));
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = '+ CONNECT';
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
// FEATURE 5: MEMORIES ARCHIVE MONTH & DATE FILTER ENGINE
// =====================================================================
var activeMemoriesMonth = 'ALL';

function filterMemoriesByMonth(monthYear) {
  activeMemoriesMonth = monthYear;
  
  document.querySelectorAll('.mem-filter-btn').forEach(function(btn) {
    if (btn.dataset.month === monthYear) {
      btn.className = 'px-2.5 py-1 bg-amber-500 text-black rounded-lg font-bold flex-shrink-0 cursor-pointer mem-filter-btn';
    } else {
      btn.className = 'px-2.5 py-1 bg-zinc-900 text-zinc-400 hover:text-white rounded-lg border border-zinc-800 flex-shrink-0 cursor-pointer mem-filter-btn';
    }
  });

  renderMemoriesFeedGrouped();
}
window.filterMemoriesByMonth = filterMemoriesByMonth;

function renderMemoriesFeedGrouped() {
  var container = document.getElementById('memoriesListContainer');
  if (!container) return;

  var moments = state.myMoments || [];
  if (activeMemoriesMonth !== 'ALL') {
    moments = moments.filter(function(m) {
      var dateStr = m.created_at || m.createdAt || '';
      return dateStr.startsWith(activeMemoriesMonth);
    });
  }

  if (moments.length === 0) {
    container.innerHTML = 
      '<div class="bg-zinc-950 border border-zinc-800/80 rounded-2xl p-8 text-center space-y-2">' +
        '<div class="text-2xl">📅</div>' +
        '<h3 class="text-xs font-bold text-white font-mono-tag uppercase">NO MEMORIES FOR THIS PERIOD</h3>' +
        '<p class="text-[11px] text-zinc-500 font-mono-tag">Capture moments daily to build your authentic timeline archive.</p>' +
      '</div>';
    return;
  }

  container.innerHTML = '';
  
  var grid = document.createElement('div');
  grid.className = 'grid grid-cols-3 gap-2';

  moments.forEach(function(m) {
    var tile = document.createElement('div');
    tile.className = 'aspect-[4/5] bg-black rounded-xl overflow-hidden relative border border-zinc-800/80 shadow-md cursor-pointer hover:opacity-90 active:scale-95 transition';
    var imgUrl = m.main_img || m.mainImg || m.mediaUrl || '';
    tile.innerHTML = 
      '<img src="' + escapeHtml(imgUrl) + '" class="w-full h-full object-cover">' +
      '<div class="absolute bottom-1 inset-x-1 px-1 py-0.5 bg-black/70 backdrop-blur rounded text-[8px] text-zinc-300 font-mono-tag truncate">' +
        escapeHtml(m.caption || 'Moment') +
      '</div>';
    tile.onclick = function() { openMomentDetail(m); };
    grid.appendChild(tile);
  });

  container.appendChild(grid);
}
window.renderMemoriesFeedGrouped = renderMemoriesFeedGrouped;

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
    } else {
      var err = 'Participation not authorized.';
      if (res && res.code === 'CAMPUS_DISCOVERY_ONLY') {
        err = 'Campus discovery: "I WAS THERE" is reserved for community members or event attendees.';
      } else if (res && res.code === 'OWN_MOMENT') {
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

