#!/usr/bin/env node
/*
 * You tab scroll-owner contract.
 *
 * The profile screen is a flex column inside the page scroller (#mainViewport),
 * and its own profile <main> is the element that must scroll. That only works
 * when #screen-you has a definite height: otherwise the inner element grows to
 * content height, has no scroll range of its own, and - because style.css gives
 * every .overflow-y-auto `overscroll-behavior-y: contain` - the swipe can never
 * chain to #mainViewport.
 *
 * These are structural source checks. They do not simulate touch scrolling.
 */

const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "style.css"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "app_core.js"), "utf8");

let checks = 0;
let failures = 0;

function check(name, condition, detail) {
  checks++;
  if (condition) {
    console.log("  PASS " + name);
  } else {
    console.log("  FAIL " + name + (detail ? "  [" + detail + "]" : ""));
    failures++;
  }
}

function elementAt(id) {
  const marker = 'id="' + id + '"';
  const idIndex = html.indexOf(marker);
  if (idIndex < 0) return null;
  const open = html.lastIndexOf("<", idIndex);
  const nameMatch = html.slice(open).match(/^<([a-zA-Z0-9-]+)/);
  if (!nameMatch) return null;
  const tagEnd = html.indexOf(">", idIndex);
  return {
    id: id,
    name: nameMatch[1].toLowerCase(),
    open: open,
    tag: html.slice(open, tagEnd + 1),
    contentStart: tagEnd + 1
  };
}

function elementEnd(el) {
  const re = new RegExp("<" + el.name + "\\b|</" + el.name + ">", "gi");
  re.lastIndex = el.open;
  let depth = 0;
  let m;
  while ((m = re.exec(html))) {
    if (m[0].charAt(1) === "/") {
      depth--;
      if (depth === 0) return m.index + m[0].length;
    } else {
      depth++;
    }
  }
  return -1;
}

function classOf(tag) {
  const m = tag.match(/\bclass="([^"]*)"/);
  return m ? m[1] : "";
}

function hasClass(tag, name) {
  return classOf(tag).split(/\s+/).indexOf(name) >= 0;
}

function cssBlock(pattern) {
  const m = css.match(pattern);
  return m ? m[1] : "";
}

function countScrollableChildren(block) {
  const re = /class="[^"]*overflow-y-(?:auto|scroll)[^"]*"/g;
  const out = [];
  let m;
  while ((m = re.exec(block))) out.push(m.index);
  return out;
}

console.log("You tab scroll owner");

const viewport = elementAt("mainViewport");
check("#mainViewport exists", !!viewport && viewport.name === "main");
check("#mainViewport owns page scrolling", !!viewport && hasClass(viewport.tag, "overflow-y-auto"));
check("#mainViewport is a flex child with a definite height", !!viewport && hasClass(viewport.tag, "flex-1"));
check("#mainViewport contains the horizontal overflow", !!viewport && hasClass(viewport.tag, "overflow-x-hidden"));

const you = elementAt("screen-you");
const youEnd = you ? elementEnd(you) : -1;
check("#screen-you exists", !!you && you.name === "section");
check("#screen-you is inside #mainViewport", !!you && !!viewport && viewport.open < you.open && you.open < elementEnd(viewport));

const youTag = you ? you.tag : "";
check("#screen-you declares a definite height", /height\s*:\s*100%/.test(youTag), youTag);
check("#screen-you is not itself a scroll container",
  !hasClass(youTag, "overflow-y-auto") && !hasClass(youTag, "overflow-y-scroll"),
  classOf(youTag));

const youBlock = you ? html.slice(you.open, youEnd) : "";
const youScrollers = countScrollableChildren(youBlock);
check("exactly one vertical scroll owner inside #screen-you", youScrollers.length === 1, String(youScrollers.length));

const youScrollerClassIndex = youScrollers.length ? you.open + youScrollers[0] : -1;
const youScrollerStart = youScrollerClassIndex >= 0 ? html.lastIndexOf("<", youScrollerClassIndex) : -1;
const youScrollerTagEnd = youScrollerStart >= 0 ? html.indexOf(">", youScrollerClassIndex) : -1;
const youScrollerTag = youScrollerStart >= 0 ? html.slice(youScrollerStart, youScrollerTagEnd + 1) : "";
check("the You scroll owner is the profile <main>", youScrollerTag.indexOf("<main") === 0, youScrollerTag.slice(0, 40));
check("the You scroll owner can grow to the bounded section height",
  /\bflex-grow\b|\bflex-1\b/.test(youScrollerTag), classOf(youScrollerTag));
check("the You scroll owner has no inline fixed height", !/style="[^"]*height/.test(youScrollerTag), youScrollerTag);

const peer = elementAt("screen-peer-profile");
const peerEnd = peer ? elementEnd(peer) : -1;
const peerTag = peer ? peer.tag : "";
const peerBlock = peer ? html.slice(peer.open, peerEnd) : "";
check("#screen-peer-profile exists", !!peer && peer.name === "section");
check("#screen-peer-profile has the same bounded height contract", /height\s*:\s*100%/.test(peerTag), peerTag);
check("#screen-peer-profile has a scroll owner for each view",
  countScrollableChildren(peerBlock).length === 2,
  String(countScrollableChildren(peerBlock).length));
check("the peer private view stays hidden until selected",
  !!elementAt("peerPrivateView") && /style="[^"]*display\s*:\s*none/.test(elementAt("peerPrivateView").tag));

const peerScroll = elementAt("peerPublicView");
check("#peerPublicView is the peer profile scroll owner",
  !!peerScroll && hasClass(peerScroll.tag, "overflow-y-auto") && hasClass(peerScroll.tag, "flex-1"),
  peerScroll ? classOf(peerScroll.tag) : "missing");

const search = elementAt("screen-search");
check("#screen-search keeps its existing definite height", !!search && /height\s*:\s*100%/.test(search.tag));

const appScreenBody = cssBlock(/(?:^|\n)\.app-screen\s*\{([^}]*)\}/);
check(".app-screen does not impose a competing height", appScreenBody !== "" && !/\bheight\s*:/.test(appScreenBody), appScreenBody.replace(/\s+/g, " ").trim());

const shellRule = cssBlock(/#mainViewport,\s*\n?\.overflow-y-auto,\s*\n?\.overflow-y-scroll\s*\{([^}]*)\}/);
check("mobile-shell containment rule is still present", shellRule !== "");
check("#mainViewport keeps overscroll containment", /overscroll-behavior-y\s*:\s*contain/.test(shellRule));
check("nested scroll containers keep overscroll containment", /\.overflow-y-auto/.test(css.match(/#mainViewport,[\s\S]*?\{[^}]*\}/)[0]));
check("touch momentum scrolling is preserved", /-webkit-overflow-scrolling\s*:\s*touch/.test(shellRule));

const rootBody = cssBlock(/(?:^|\n)html,\s*body\s*\{([^}]*)\}/);
check("root overscroll stays disabled", /overscroll-behavior-y\s*:\s*none/.test(rootBody));

const appContainerRules = html.match(/#appContainer\s*\{[^}]*\}/g) || [];
check("#appContainer keeps a definite height in every chassis rule",
  appContainerRules.length > 0 && appContainerRules.every(function(rule) { return /height\s*:/.test(rule); }),
  String(appContainerRules.length));
check("the mobile shell keeps a viewport-relative app height", /height\s*:\s*100dvh/.test(html));

const switchFn = app.slice(app.indexOf("function switchScreenView"), app.indexOf("window.switchScreenView = switchScreenView;"));
check("switchScreenView does not write height or overflow onto the target",
  switchFn.length > 0 && !/\.style\.height|\.style\.overflow/.test(switchFn));
check("switchScreenView still opens You as a flex column",
  /screenName === 'you'/.test(switchFn) && /target\.style\.display = 'flex'/.test(switchFn));

check("no duplicate #screen-you id", html.split('id="screen-you"').length === 2);
check("no duplicate #screen-peer-profile id", html.split('id="screen-peer-profile"').length === 2);

console.log("\n" + (checks - failures) + "/" + checks + " checks passed");
if (failures) {
  console.log(failures + " check(s) FAILED");
  process.exitCode = 1;
}
