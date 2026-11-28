"""Optional profile fields must be invisible until the user actually adds them.

The rule under test: campus/community, city, bio and any other optional profile
metadata render nothing at all when they hold no genuine user value -- no
"Not added"/"N/A" placeholder, no fabricated campus/community/city/bio defaults,
no empty label, icon, separator or reserved blank space. Mandatory identity
(name, @handle) always renders. A fully populated profile is unchanged.

The rendering harness runs the real `cleanProfileText` + `applyUserToYouScreen`
source from app_core.js inside node against a stub document, so these assertions
exercise the shipped code rather than a copy of it.
"""

import json
import os
import re
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def _slice(source, start, end):
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


HARNESS = r"""
'use strict';

var SOURCE_HELPER = __HELPER__;
var SOURCE_APPLY = __APPLY__;

function makeDocument() {
  var els = {};
  return {
    els: els,
    getElementById: function (id) {
      if (!els[id]) {
        els[id] = {
          id: id, textContent: '', title: '', value: '', src: '',
          style: {}, attrs: {},
          setAttribute: function (k, v) { this.attrs[k] = v; },
          removeAttribute: function (k) { delete this.attrs[k]; }
        };
      }
      return els[id];
    }
  };
}

function render(user) {
  var document = makeDocument();
  var state = { currentUser: {} };
  var factory = new Function(
    'document', 'state',
    SOURCE_HELPER + '\n' + SOURCE_APPLY + '\nreturn applyUserToYouScreen;'
  );
  var apply = factory(document, state);
  apply(user);

  var ids = [
    'youProfileName', 'youProfileUsername', 'youProfileCampus',
    'youProfileLocationRow', 'youProfileCampusRow', 'youProfileCampusCityRow',
    'youProfileCampusName', 'youProfileCampusCity', 'youProfileBio'
  ];
  var out = {};
  ids.forEach(function (id) {
    var node = document.els[id];
    out[id] = node
      ? { text: node.textContent, display: node.style.display || '', title: node.title || '' }
      : null;
  });
  return out;
}

var cases = JSON.parse(process.argv[1]);
var results = {};
Object.keys(cases).forEach(function (name) { results[name] = render(cases[name]); });
process.stdout.write(JSON.stringify(results));
"""


def _render_cases(cases):
    source = _read("app_core.js")
    helper = _slice(source, "function cleanProfileText(value) {", "window.cleanProfileText")
    apply_fn = _slice(source, "function applyUserToYouScreen(u) {", "window.applyUserToYouScreen")
    assert "cleanProfileText" in helper and "cleanProfileText" in apply_fn
    script = HARNESS.replace("__HELPER__", json.dumps(helper)).replace("__APPLY__", json.dumps(apply_fn))
    proc = subprocess.run(
        ["node", "-e", script, "--", json.dumps(cases)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError("node rendering harness failed:\n" + proc.stderr)
    return json.loads(proc.stdout)


def _profile_section(html):
    begin = html.index('id="screen-you"')
    return html[begin:html.index("</section>", begin)]


def _peer_public_section(html):
    begin = html.index('id="peerPublicView"')
    return html[begin:html.index('id="peerPrivateView"', begin)]


def _peer_private_section(html):
    begin = html.index('id="peerPrivateView"')
    return html[begin:begin + 8000]


class TestOptionalProfileFieldsRenderNothing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = _render_cases({
            "all_empty": {"name": "Asha", "handle": "asha"},
            "only_campus": {"name": "Asha", "handle": "asha", "campus": "IIT Patna"},
            "only_city": {"name": "Asha", "handle": "asha", "location_city": "Patna"},
            "only_community": {"name": "Asha", "handle": "asha", "community": "Kindid Builders"},
            "bio_empty": {"name": "Asha", "handle": "asha", "bio": "   "},
            "mixed": {"name": "Asha", "handle": "asha", "campus": "IIT Patna",
                      "location_city": "", "bio": "", "community": "  "},
            "whitespace_all": {"name": "Asha", "handle": "asha", "campus": "   ",
                               "community": "\t\n", "location_city": "  ",
                               "city": "", "bio": " \u00a0 "},
            "populated": {"name": "Asha Rao", "handle": "asha.rao", "campus": "IIT Patna",
                          "location_city": "Patna", "bio": "Chasing light."},
            "sentinel": {"name": "Asha", "handle": "asha",
                         "campus": "Independent Creator / City"},
            "placeholder_literals": {"name": "Asha", "handle": "asha",
                                     "campus": "Not added", "city": "N/A",
                                     "bio": "unknown"},
        })

    def _assert_optional_hidden(self, case, expect_campus=False, expect_city=False, expect_bio=False):
        r = self.results[case]
        if expect_campus:
            self.assertEqual(r["youProfileCampusRow"]["display"], "flex", case)
            self.assertTrue(r["youProfileCampusName"]["text"].strip(), case)
        else:
            self.assertEqual(r["youProfileCampusRow"]["display"], "none", case)
            self.assertEqual(r["youProfileCampusName"]["text"], "", case)
        if expect_city:
            self.assertEqual(r["youProfileCampusCityRow"]["display"], "flex", case)
            self.assertTrue(r["youProfileCampusCity"]["text"].strip(), case)
        else:
            self.assertEqual(r["youProfileCampusCityRow"]["display"], "none", case)
            self.assertEqual(r["youProfileCampusCity"]["text"], "", case)
        if expect_bio:
            self.assertEqual(r["youProfileBio"]["display"], "block", case)
            self.assertTrue(r["youProfileBio"]["text"].strip(), case)
        else:
            self.assertEqual(r["youProfileBio"]["display"], "none", case)
            self.assertEqual(r["youProfileBio"]["text"], "", case)
        expected_container = "flex" if (expect_campus or expect_city) else "none"
        self.assertEqual(r["youProfileLocationRow"]["display"], expected_container, case)

    def test_01_all_optional_fields_empty_render_nothing(self):
        self._assert_optional_hidden("all_empty")
        r = self.results["all_empty"]
        self.assertEqual(r["youProfileName"]["text"], "Asha")
        self.assertEqual(r["youProfileUsername"]["text"], "@asha")
        self.assertEqual(r["youProfileCampus"]["title"], "")

    def test_02_only_campus_populated(self):
        self._assert_optional_hidden("only_campus", expect_campus=True)
        self.assertEqual(self.results["only_campus"]["youProfileCampusName"]["text"], "IIT Patna")

    def test_03_only_city_populated(self):
        self._assert_optional_hidden("only_city", expect_city=True)
        self.assertEqual(self.results["only_city"]["youProfileCampusCity"]["text"], "Patna")

    def test_04_only_community_populated(self):
        self._assert_optional_hidden("only_community", expect_campus=True)
        self.assertEqual(self.results["only_community"]["youProfileCampusName"]["text"], "Kindid Builders")

    def test_05_bio_empty_renders_nothing(self):
        self._assert_optional_hidden("bio_empty")

    def test_06_multiple_populated_some_empty(self):
        self._assert_optional_hidden("mixed", expect_campus=True)
        self.assertEqual(self.results["mixed"]["youProfileCampusCity"]["text"], "")

    def test_07_whitespace_only_values_are_empty(self):
        self._assert_optional_hidden("whitespace_all")

    def test_08_populated_profile_unchanged(self):
        self._assert_optional_hidden("populated", expect_campus=True, expect_city=True, expect_bio=True)
        r = self.results["populated"]
        self.assertEqual(r["youProfileName"]["text"], "Asha Rao")
        self.assertEqual(r["youProfileUsername"]["text"], "@asha.rao")
        self.assertEqual(r["youProfileCampusName"]["text"], "IIT Patna")
        self.assertEqual(r["youProfileCampusCity"]["text"], "Patna")
        self.assertEqual(r["youProfileBio"]["text"], "Chasing light.")
        self.assertEqual(r["youProfileCampus"]["title"], "IIT Patna \u00b7 Patna")

    def test_09_legacy_sentinel_is_not_user_content(self):
        self._assert_optional_hidden("sentinel")

    def test_10_placeholder_literals_are_not_rendered(self):
        self._assert_optional_hidden("placeholder_literals")
        r = self.results["placeholder_literals"]
        for el in ("youProfileCampusName", "youProfileCampusCity", "youProfileBio"):
            self.assertNotIn("Not added", r[el]["text"])
            self.assertNotIn("N/A", r[el]["text"])
            self.assertNotIn("unknown", r[el]["text"])


class TestOptionalProfileFieldsMarkup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        cls.js = _read("app_core.js")

    def test_11_you_profile_ships_empty_hidden_optional_slots(self):
        section = _profile_section(self.html)
        self.assertIn('<span id="youProfileCampusName"></span>', section)
        self.assertIn('<span id="youProfileCampusCity"></span>', section)
        self.assertIn('id="youProfileCampusRow" style="display:none;"', section)
        self.assertIn('id="youProfileCampusCityRow" style="display:none;"', section)
        self.assertIn('id="youProfileLocationRow"', section)
        self.assertIn('id="youProfileBio"', section)
        self.assertNotIn("Not added", section)
        self.assertNotIn("Authentic moments across campus.", section)
        # Mandatory identity stays in the markup, untouched.
        self.assertIn('id="youProfileName"', section)
        self.assertIn('id="youProfileUsername"', section)

    def test_12_peer_profile_ships_empty_hidden_optional_slots(self):
        public = _peer_public_section(self.html)
        self.assertIn('<span id="peerPublicCampus"></span>', public)
        self.assertIn('<span id="peerPublicCity"></span>', public)
        self.assertIn('id="peerPublicBio"', public)
        self.assertNotIn("Authentic moments across campus.", public)
        self.assertNotIn("Not added", public)

        private = _peer_private_section(self.html)
        self.assertIn('id="peerPrivateBio"', private)
        self.assertNotIn("Authentic moments across campus.", private)
        self.assertNotIn("Their world, kept close.", self.html)

    def _fn_block(self, signature, end_marker):
        begin = self.js.index(signature)
        return self.js[begin:self.js.index(end_marker, begin)]

    def test_13_js_has_no_placeholder_or_fabricated_profile_fallbacks(self):
        you = self._fn_block("function applyUserToYouScreen(u) {", "window.applyUserToYouScreen")
        peer = self._fn_block("var pubCampus = document.getElementById", "// 2-column Moments Grid")
        self.assertNotIn("'Not added'", you)
        self.assertNotIn("'Not added'", peer)
        self.assertNotIn("'Authentic moments across campus.'", self.js)
        self.assertNotIn("'Their world, kept close.'", self.js)
        self.assertNotIn("bioInp.value = state.currentUser.bio ||", self.js)
        self.assertNotIn("cityInp.value = state.currentUser.location_city || state.currentUser.city ||", self.js)
        self.assertNotIn("vibeInp.value = state.currentUser.vibe ||", self.js)
        # A deliberately cleared campus must not be resurrected as a fake community.
        self.assertNotIn("newCampus = 'Independent Creator / City'", self.js)
        self.assertIn("function cleanProfileText(value) {", self.js)

    def test_14_js_toggles_visibility_of_every_optional_profile_element(self):
        self.assertIn("campusNameRow.style.display = commName ? 'flex' : 'none';", self.js)
        self.assertIn("campusCityRow.style.display = cityName ? 'flex' : 'none';", self.js)
        self.assertIn("locationRow.style.display = (commName || cityName) ? 'flex' : 'none';", self.js)
        self.assertIn("bioEl.style.display = bioText ? 'block' : 'none';", self.js)
        self.assertIn("pubCampusRow.style.display = 'flex'", self.js)
        self.assertIn("pubCityRow.style.display = 'flex'", self.js)
        self.assertIn("pubLocationRow.style.display = (pubCampusText || pubCityText) ? 'flex' : 'none';", self.js)
        self.assertIn("pubBio.style.display = pubBioText ? 'block' : 'none';", self.js)
        self.assertIn("privBio.style.display = privBioText ? 'block' : 'none';", self.js)
        # The rendered profile title/aria summary never shows a dangling separator.
        self.assertNotIn("campusEl.title = commName + ' \\u00b7 ' + cityName", self.js)

    def test_15_mandatory_identity_is_never_hidden(self):
        self.assertIn("if (nameEl) nameEl.textContent = finalName;", self.js)
        self.assertIn("if (usernameEl) usernameEl.textContent = '@' + finalHandle.toLowerCase();", self.js)
        section = _profile_section(self.html)
        self.assertNotIn('id="youProfileName" style="display:none;"', section)
        self.assertNotIn('id="youProfileUsername" style="display:none;"', section)


if __name__ == "__main__":
    unittest.main(verbosity=2)
