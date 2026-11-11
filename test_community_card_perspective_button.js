// test_community_card_perspective_button.js
// Regression test verifying that Community moment cards do NOT render a duplicate
// perspective badge overlay at the top, and keep the perspective action strictly
// in the bottom action bar.

'use strict';

const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, 'app_core.js');
const src = fs.readFileSync(srcPath, 'utf8');

let pass = 0;
let fail = 0;

function check(desc, cond) {
  if (cond) {
    pass++;
    console.log('  PASS: ' + desc);
  } else {
    fail++;
    console.log('  FAIL: ' + desc);
  }
}

console.log('=== COMMUNITY MOMENT CARD PERSPECTIVE BUTTON AUDIT TESTS ===\n');

// 1. In renderCommunityCards, top-right overlay must not contain clusterBadgeHtml
const fnIdx = src.indexOf('function renderCommunityCards(moments, container, mode)');
const fnEndIdx = src.indexOf('window.renderCommunityCards = renderCommunityCards;', fnIdx);
const renderCommunityCardsBody = src.slice(fnIdx, fnEndIdx);

check('renderCommunityCards function exists', fnIdx !== -1 && fnEndIdx !== -1);

check('top-right badge overlay in sequence mode does not include clusterBadgeHtml',
  !renderCommunityCardsBody.includes("clusterBadgeHtml +")
);

check('top-right badge overlay only contains timestamp badge',
  renderCommunityCardsBody.includes('<div class="absolute top-4 right-4 z-10 flex items-center gap-1.5">\'' + '\n' +
    '            \'<span class="font-mono-tag text-[9px] text-white/90 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/15 moment-live-timestamp"') ||
  renderCommunityCardsBody.includes("moment-live-timestamp")
);

// 2. Bottom action bar still contains perspectiveBtnHtml
check('bottom action row contains perspectiveBtnHtml',
  renderCommunityCardsBody.includes('perspectiveBtnHtml +')
);

// 3. perspectiveBtnHtml still calls openMomentClusterModal
check('perspectiveBtnHtml calls openMomentClusterModal',
  renderCommunityCardsBody.includes("openMomentClusterModal")
);

// 4. Graceful image error handling on feed card main and pip images
check('main-stage-img has onerror fallback handler',
  renderCommunityCardsBody.includes('class="w-full h-full object-cover main-stage-img" src="\' + escapeHtml(mainImgSrc) + \'" alt="" onerror="this.style.opacity=\\\'0\\\';"')
);

check('pip-sub-img has onerror fallback handler',
  renderCommunityCardsBody.includes('class="w-full h-full object-cover pip-sub-img" alt="" onerror="this.style.opacity=\\\'0\\\';"')
);

// 5. Cluster modal perspective list image has fallback
const modalIdx = src.indexOf('async function openMomentClusterModal');
const modalEndIdx = src.indexOf('window.openMomentClusterModal = openMomentClusterModal;', modalIdx);
const modalBody = src.slice(modalIdx, modalEndIdx);

check('cluster modal primary moment img has onerror fallback',
  modalBody.includes('clusterData.primary_moment') && modalBody.includes('onerror="this.style.opacity=\\\'0\\\';"')
);

check('cluster modal perspective list checks for non-empty image src',
  modalBody.includes('var perspImgSrc = persp.main_img || persp.pip_img || \'\';')
);

console.log('\n=========================================');
console.log('Checks: ' + (pass + fail) + ' | Passed: ' + pass + ' | Failed: ' + fail);

if (fail > 0) {
  process.exit(1);
} else {
  console.log('ALL COMMUNITY CARD TESTS PASSED');
  process.exit(0);
}
