#!/usr/bin/env node
/*
 * Mobile web shell lockdown checks.
 *
 * These are source-contract checks because this repository has no browser
 * automation dependency. They verify the CSS/metadata that the browser sees;
 * they do not simulate iOS rubber-banding, Android WebView, or real taps.
 */

const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const css = fs.readFileSync(path.join(ROOT, "style.css"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "manifest.json"), "utf8"));

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

function ruleBody(selectorPattern) {
  const match = css.match(selectorPattern);
  return match ? match[1] : "";
}

function hasDeclaration(body, property, value) {
  const escapedProperty = property.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const escapedValue = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(escapedProperty + "\\s*:\\s*" + escapedValue, "i").test(body);
}

function mediaBlock(maxWidth) {
  const start = css.indexOf("@media screen and (max-width: " + maxWidth + "px)");
  if (start < 0) return "";
  const open = css.indexOf("{", start);
  if (open < 0) return "";
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}") {
      depth--;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  return "";
}

console.log("Mobile shell lockdown");

// 1. Root overscroll is disabled and the app viewport contains its own scroll.
const rootBody = ruleBody(/html\s*,\s*body\s*\{([^}]*)\}/);
check("html/body disable overscroll", hasDeclaration(rootBody, "overscroll-behavior", "none"));
check("html/body disable vertical overscroll", hasDeclaration(rootBody, "overscroll-behavior-y", "none"));
check("html/body use touch momentum scrolling", hasDeclaration(rootBody, "-webkit-overflow-scrolling", "touch"));

const viewportBody = ruleBody(/#mainViewport[\s\S]*?\{([^}]*)\}/);
check("#mainViewport contains vertical overscroll", hasDeclaration(viewportBody, "overscroll-behavior-y", "contain"));
check("#mainViewport uses touch momentum scrolling", hasDeclaration(viewportBody, "-webkit-overflow-scrolling", "touch"));

// 2. Interactive controls have instant taps and no browser highlight.
const touchBody = ruleBody(/button\s*,[\s\S]*?\.selectable-chip[\s\S]*?\{([^}]*)\}/);
check("interactive controls use touch-action manipulation", hasDeclaration(touchBody, "touch-action", "manipulation"));
check("interactive controls remove tap highlight", hasDeclaration(touchBody, "-webkit-tap-highlight-color", "transparent"));
check("interactive group includes .action-btn", /\.action-btn/.test(css));
check("interactive group includes .sub-tab-btn", /\.sub-tab-btn/.test(css));
check("interactive group includes .unified-dock", /\.unified-dock/.test(css));
check("interactive group includes .selectable-chip", /\.selectable-chip/.test(css));

// 3. Media viewports suppress native context menus and selection.
const mediaBody = ruleBody(/img\s*,[\s\S]*?\.live-moment-video[\s\S]*?\{([^}]*)\}/);
check("media suppresses iOS touch callout", hasDeclaration(mediaBody, "-webkit-touch-callout", "none"));
check("media suppresses user selection", hasDeclaration(mediaBody, "user-select", "none"));
check("media suppresses webkit user selection", hasDeclaration(mediaBody, "-webkit-user-select", "none"));
check("moment viewport is covered by media rule", /\.moment-viewport-stage/.test(css));
check("selfie PiP is covered by media rule", /\.sub-camera-pip/.test(css));
check("live video is covered by media rule", /\.live-moment-video/.test(css));

// 4. Safe areas protect the top header and bottom dock on phones.
const mobile = mediaBlock(640);
const headerBody = (mobile.match(/#mainGlobalHeader\s*\{([^}]*)\}/) || [])[1] || "";
const dockBody = (mobile.match(/#unifiedDock\s*\{([^}]*)\}/) || [])[1] || "";
check("header uses top safe-area inset", hasDeclaration(headerBody, "padding-top", "max(14px, env(safe-area-inset-top, 14px))"));
check("dock uses bottom safe-area inset", hasDeclaration(dockBody, "bottom", "max(12px, calc(env(safe-area-inset-bottom, 0px) + 8px))"));

// 5. Inputs cannot trigger iOS auto-zoom.
const mobileInputRule = mobile.match(/(input\[type="text"\][\s\S]*?textarea[^{}]*)\{([^}]*)\}/);
const mobileInputSelector = mobileInputRule ? mobileInputRule[1] : "";
const mobileInputBody = mobileInputRule ? mobileInputRule[2] : "";
check("mobile text inputs use 16px font", hasDeclaration(mobileInputBody, "font-size", "16px"));
check("mobile input selector includes textarea", /textarea/.test(mobileInputSelector));
check("mobile input selector includes email search password",
  /input\[type="email"\]/.test(mobileInputSelector) &&
  /input\[type="search"\]/.test(mobileInputSelector) &&
  /input\[type="password"\]/.test(mobileInputSelector));

// 6. Shell metadata and cache versions are correct.
const viewportMeta = (html.match(/<meta\s+name="viewport"\s+content="([^"]+)"/i) || [])[1] || "";
check("viewport includes viewport-fit=cover", /viewport-fit=cover/.test(viewportMeta));
check("viewport disables user scaling", /maximum-scale=1\.0/.test(viewportMeta) && /user-scalable=no/.test(viewportMeta));
check("stylesheet cache bust is 3.3.0", /<link\s+rel="stylesheet"\s+href="\/style\.css\?v=3\.3\.0"/.test(html));
check("app cache bust is 3.3.5", /<script\s+src="\/app_core\.js\?v=3\.3\.5"><\/script>/.test(html));

check("manifest display is standalone", manifest.display === "standalone");
check("manifest orientation is portrait", manifest.orientation === "portrait");
check("manifest background is black", manifest.background_color === "#000000");
check("manifest theme is Kindid dark", manifest.theme_color === "#09090b");
check("manifest start_url is root", manifest.start_url === "/");

console.log("\n" + (checks - failures) + "/" + checks + " checks passed");
if (failures > 0) {
  process.exit(1);
}
