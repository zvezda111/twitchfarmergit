/* Theme controller — applied synchronously in <head> to avoid flash-of-wrong-theme.
   Loaded without `defer` so it runs before the body paints. CSP-safe (external file). */
(function () {
  var STORAGE_KEY = "theme";
  var root = document.documentElement;

  function systemPref() {
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function stored() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function current() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function syncButtons(theme) {
    var pressed = theme === "dark";
    var btns = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute("aria-pressed", String(pressed));
      btns[i].setAttribute(
        "title",
        pressed ? "Светлая тема" : "Тёмная тема"
      );
    }
  }

  function apply(theme, persist) {
    root.setAttribute("data-theme", theme);
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch (e) {}
    }
    syncButtons(theme);
  }

  // initial (synchronous, pre-paint)
  apply(stored() || systemPref(), false);

  // follow the OS setting only while the user hasn't chosen explicitly
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function (e) {
      if (!stored()) apply(e.matches ? "dark" : "light", false);
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  window.Theme = {
    toggle: function () {
      apply(current() === "dark" ? "light" : "dark", true);
    },
    set: function (t) {
      apply(t === "dark" ? "dark" : "light", true);
    },
    current: current,
  };

  document.addEventListener("DOMContentLoaded", function () {
    syncButtons(current());
    var btns = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", window.Theme.toggle);
    }
  });
})();
