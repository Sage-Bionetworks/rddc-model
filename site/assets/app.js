(function () {
  "use strict";
  var root = document.documentElement;

  // Copy buttons
  document.querySelectorAll("figure.code .copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var text = btn.parentElement.querySelector("pre").innerText;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = "Copied";
        btn.classList.add("done");
        setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1600);
      });
    });
  });

  // Theme
  var themeBtn = document.querySelector(".theme-toggle");
  themeBtn.addEventListener("click", function () {
    var dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("rddc-theme", root.dataset.theme);
  });

  // Term origin colouring
  var originBtn = document.querySelector(".origins-toggle");
  function syncOrigins() { originBtn.setAttribute("aria-pressed", String(!root.classList.contains("no-origins"))); }
  syncOrigins();
  originBtn.addEventListener("click", function () {
    root.classList.toggle("no-origins");
    localStorage.setItem("rddc-origins", root.classList.contains("no-origins") ? "off" : "on");
    syncOrigins();
  });

  // Legend: hovering or pressing a vocabulary highlights its keys
  document.querySelectorAll(".legend [data-origin]").forEach(function (el) {
    var origin = el.dataset.origin;
    function on() {
      document.body.dataset.focus = origin;
      document.querySelectorAll("pre .k.o-" + origin).forEach(function (k) { k.classList.add("o-focus"); });
    }
    function off() {
      if (el.getAttribute("aria-pressed") === "true") return;
      delete document.body.dataset.focus;
      document.querySelectorAll("pre .k.o-focus").forEach(function (k) { k.classList.remove("o-focus"); });
    }
    el.addEventListener("mouseenter", on);
    el.addEventListener("mouseleave", off);
    el.addEventListener("focus", on);
    el.addEventListener("blur", off);
    el.addEventListener("click", function () {
      var pressed = el.getAttribute("aria-pressed") === "true";
      document.querySelectorAll(".legend [data-origin]").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      document.querySelectorAll("pre .k.o-focus").forEach(function (k) { k.classList.remove("o-focus"); });
      delete document.body.dataset.focus;
      if (!pressed) { el.setAttribute("aria-pressed", "true"); on(); }
    });
  });

  // Mobile navigation
  var menu = document.querySelector(".menu");
  var side = document.getElementById("side");
  menu.addEventListener("click", function () {
    var open = side.classList.toggle("open");
    menu.setAttribute("aria-expanded", String(open));
  });

  // Heading anchors
  document.querySelectorAll(".doc h2[id], .doc h3[id]").forEach(function (h) {
    var a = document.createElement("a");
    a.className = "anchor";
    a.href = "#" + h.id;
    a.setAttribute("aria-label", "Link to this section");
    a.textContent = "#";
    h.appendChild(a);
  });

  // Tabs
  document.querySelectorAll(".tabs").forEach(function (tabs) {
    var buttons = tabs.querySelectorAll('[role="tab"]');
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () { select(i); });
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") select((i + 1) % buttons.length, true);
        if (e.key === "ArrowLeft") select((i - 1 + buttons.length) % buttons.length, true);
      });
    });
    function select(i, focus) {
      buttons.forEach(function (b, j) {
        b.setAttribute("aria-selected", String(i === j));
        b.tabIndex = i === j ? 0 : -1;
        document.getElementById(b.getAttribute("aria-controls")).hidden = i !== j;
      });
      if (focus) buttons[i].focus();
    }
  });

  // Table of contents: mark the section in view
  var tocLinks = document.querySelectorAll(".toc a");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          tocLinks.forEach(function (a) { a.classList.remove("active"); });
          var link = byId[e.target.id];
          if (link) link.classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    Object.keys(byId).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) obs.observe(el);
    });
  }

  // Search
  var input = document.getElementById("q");
  var list = document.getElementById("results");
  var index = null;
  var selected = -1;

  function load() {
    if (index) return Promise.resolve(index);
    return fetch("assets/search-index.json").then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
  }
  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function snippet(text, terms) {
    var lower = text.toLowerCase();
    var at = lower.indexOf(terms[0]);
    var start = Math.max(0, at - 40);
    var s = escapeHtml((start ? "…" : "") + text.slice(start, start + 140));
    terms.forEach(function (t) {
      if (t.length > 1) s = s.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return s;
  }
  function run() {
    var q = input.value.trim().toLowerCase();
    if (!q) { list.hidden = true; return; }
    load().then(function (idx) {
      var terms = q.split(/\s+/);
      var hits = idx.map(function (e) {
        var h = e.heading.toLowerCase(), t = e.text.toLowerCase();
        var score = 0;
        for (var i = 0; i < terms.length; i++) {
          var term = terms[i];
          if (h.indexOf(term) >= 0) score += 5;
          else if (t.indexOf(term) >= 0) score += 1;
          else return null;
        }
        return { e: e, score: score };
      }).filter(Boolean).sort(function (a, b) { return b.score - a.score; }).slice(0, 12);
      selected = -1;
      list.innerHTML = hits.length
        ? hits.map(function (h) {
            return '<li><a href="' + h.e.url + '"><b>' + escapeHtml(h.e.heading) + "</b><small>" +
              escapeHtml(h.e.page) + "</small><br><small>" + snippet(h.e.text, terms) + "</small></a></li>";
          }).join("")
        : '<li class="empty">No matches. Try a property name such as <code>subjectIds</code>.</li>';
      list.hidden = false;
    });
  }
  input.addEventListener("input", run);
  input.addEventListener("focus", function () { load(); if (input.value) run(); });
  input.addEventListener("keydown", function (e) {
    var links = list.querySelectorAll("a");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!links.length) return;
      selected = (selected + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links.forEach(function (a, i) { a.setAttribute("aria-selected", String(i === selected)); });
      links[selected].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && links.length) {
      location.href = links[Math.max(0, selected)].href;
    } else if (e.key === "Escape") {
      input.value = ""; list.hidden = true; input.blur();
    }
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest(".search")) list.hidden = true;
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); input.focus(); }
  });
})();
