// Runs BEFORE the stylesheet (blocking, not a module, no defer) so the right
// theme is on <html> before first paint -- no flash of the wrong theme. It has
// to be an external file: the page's CSP forbids inline scripts.
// A saved choice (set only when the user clicks the toggle) wins; otherwise the
// system preference decides, and chrome.js keeps following system changes until
// the user makes an explicit choice.
(function () {
  var saved = null;
  try { saved = localStorage.getItem("graha-theme"); } catch (e) { /* storage blocked */ }
  var theme = saved === "light" || saved === "dark"
    ? saved
    : (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.setAttribute("data-theme", theme);
})();
