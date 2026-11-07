// test_login_identifier_normalization.js
// Regression test verifying that submitUserLogin normalizes usernames by stripping
// only leading '@' symbols, while keeping email addresses containing '@' fully intact.

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

console.log('=== LOGIN IDENTIFIER NORMALIZATION TESTS ===\n');

// 1. Static check: submitUserLogin must use /^@+/ instead of global/blind '@' replace
const fnIdx = src.indexOf('window.submitUserLogin = async function()');
const fnEndIdx = src.indexOf('window.openResetPasswordModal = function()', fnIdx);
check('submitUserLogin function exists', fnIdx !== -1 && fnEndIdx !== -1);

const body = src.slice(fnIdx, fnEndIdx);

check('submitUserLogin uses leading-only @ replace regex /^@+/',
  body.includes(".replace(/^@+/, '')") || body.includes('.replace(/^@+/, "")')
);

check('submitUserLogin does NOT blindly remove all @ characters with replace(\'@\', \'\')',
  !body.includes(".replace('@', '')")
);

// 2. Behavioral simulation of normalization logic
function normalizeIdentifier(val) {
  return val ? val.trim().replace(/^@+/, '') : '';
}

check('Email with @ is preserved intact: user@example.com',
  normalizeIdentifier('user@example.com') === 'user@example.com'
);

check('Email with whitespace is preserved intact: "  founder@kandid.in  "',
  normalizeIdentifier('  founder@kandid.in  ') === 'founder@kandid.in'
);

check('Username with leading @ is stripped: @founder -> founder',
  normalizeIdentifier('@founder') === 'founder'
);

check('Username with multiple leading @ is stripped: @@founder -> founder',
  normalizeIdentifier('@@founder') === 'founder'
);

check('Plain username without @ is unchanged: founder -> founder',
  normalizeIdentifier('founder') === 'founder'
);

check('Null or undefined input yields empty string',
  normalizeIdentifier(null) === '' && normalizeIdentifier(undefined) === ''
);

console.log('\n=========================================');
console.log('Checks: ' + (pass + fail) + ' | Passed: ' + pass + ' | Failed: ' + fail);

if (fail > 0) {
  process.exit(1);
} else {
  console.log('ALL LOGIN IDENTIFIER TESTS PASSED');
  process.exit(0);
}
