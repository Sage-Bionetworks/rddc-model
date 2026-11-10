/* "Data trajectory" page.
   Reads assets/data-trajectory.json (written by scripts/rules_site.py), lets the
   reader describe a file and its source, and shows the route the rules choose on a
   map of every zone. Deposits are numbered as rules_site.explorer_data numbers them,
   and states after each step are replayed from the workflows' effects as
   rules_site.lookup does. */
(function () {
  "use strict";
  var root = document.getElementById("pr-explorer");
  if (!root) return;
  var SVGNS = "http://www.w3.org/2000/svg";

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }
  function svg(tag, attrs, parent, text) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function code(text, title) {
    var c = el("code", { text: text });
    if (title) c.title = title;
    return c;
  }
  function txt(s) { return document.createTextNode(s); }
  function firstSentence(s) {
    var m = /^(.+?\.)(\s|$)/.exec(s || "");
    return m ? m[1] : (s || "");
  }
  function runnerLabel(wf) {
    var r = { cirro: "Cirro", container: "Container", service: "Service" }[wf.runner] || wf.runner;
    if (wf.cirroExecutor) r += " · " + wf.cirroExecutor;
    return wf.pipelineVersion ? r + " · v" + wf.pipelineVersion : r;
  }

  fetch(root.getAttribute("data-src")).then(function (r) { return r.json(); }).then(start, function () {
    root.textContent = "Could not load the rules data.";
  });

  // --- the zone map ----------------------------------------------------------------
  // Zones are placed in columns by their longest distance from the deposit zone along
  // the catalog's moves, and in rule-file order within a column. Moves a workflow can
  // make between zones are drawn faintly; the file's route is drawn on top.
  var COL = 170, ROW = 108, NODE_W = 120, NODE_H = 44, LEFT = 80, TOP = 74;

  function buildMap(data) {
    var zones = data.zoneList, edges = {};
    Object.keys(data.workflows).forEach(function (w) {
      var wf = data.workflows[w];
      if (!wf.writesTo || !wf.readsFrom) return;
      wf.readsFrom.forEach(function (a) {
        var k = a + ">" + wf.writesTo;
        (edges[k] = edges[k] || []).push(w);
      });
    });
    var rank = {};
    zones.forEach(function (z) { rank[z.id] = z.initial ? 0 : -1; });
    for (var it = 0; it < zones.length; it++) {
      Object.keys(edges).forEach(function (k) {
        var ab = k.split(">");
        if (ab[0] !== ab[1] && rank[ab[0]] >= 0 && rank[ab[1]] < rank[ab[0]] + 1) rank[ab[1]] = rank[ab[0]] + 1;
      });
    }
    var maxRank = Math.max.apply(null, zones.map(function (z) { return rank[z.id]; }));
    zones.forEach(function (z) { if (rank[z.id] < 0) rank[z.id] = maxRank + 1; });
    maxRank = Math.max.apply(null, zones.map(function (z) { return rank[z.id]; }));
    var pos = {}, rows = {};
    zones.forEach(function (z) {
      var c = rank[z.id], r = rows[c] = (rows[c] || 0) + 1;
      pos[z.id] = { x: LEFT + c * COL, y: TOP + (r - 1) * ROW };
    });
    var maxRows = Math.max.apply(null, Object.keys(rows).map(function (c) { return rows[c]; }));
    var gov = data.governance;
    var BAND_GAP = 30, BAND_H = 36;
    var bandY = TOP + (maxRows - 1) * ROW + NODE_H / 2 + 24 + BAND_GAP;
    var W = LEFT * 2 + maxRank * COL, H = gov ? bandY + BAND_H + 6 : TOP + (maxRows - 1) * ROW + NODE_H / 2 + 30;

    var title = svg("title", { id: "pr-map-title" }, null, "Zones and the file's route");
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, "class": "pr-map-svg", role: "img",
                         "aria-labelledby": "pr-map-title" });
    s.appendChild(title);
    var defs = svg("defs", {}, s);
    [["pr-arrow-faint", "pr-ah-faint"], ["pr-arrow-on", "pr-ah-on"], ["pr-arrow-alt", "pr-ah-alt"]].forEach(function (m) {
      var mk = svg("marker", { id: m[0], viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7",
                              markerHeight: "7", orient: "auto-start-reverse" }, defs);
      svg("path", { d: "M0 0 L10 5 L0 10 z", "class": m[1] }, mk);
    });

    // Platform modules (INTAKE, NORMALIZE, DISCOVER, GOVERN): a dashed frame around each
    // module's zones, with room above for loops. Zones with no module are outside them.
    var modules = [], frames = [];
    zones.forEach(function (z) { if (z.module && modules.indexOf(z.module) < 0) modules.push(z.module); });
    modules.forEach(function (m) {
      var mz = zones.filter(function (z) { return z.module === m; });
      var xs = mz.map(function (z) { return pos[z.id].x; }), ys = mz.map(function (z) { return pos[z.id].y; });
      var loops = mz.some(function (z) { return edges[z.id + ">" + z.id]; });
      var x0 = Math.min.apply(null, xs) - NODE_W / 2 - 12, x1 = Math.max.apply(null, xs) + NODE_W / 2 + 12;
      var y0 = Math.min.apply(null, ys) - NODE_H / 2 - (loops ? 52 : 28), y1 = Math.max.apply(null, ys) + NODE_H / 2 + 24;
      svg("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 12, "class": "pr-module" }, s);
      svg("text", { x: x0 + 10, y: y0 + 15, "class": "pr-module-label" }, s, m);
      frames.push({ module: m, x: (x0 + x1) / 2, bottom: y1 });
    });

    // GOVERN holds registers, not data: a band under every module, tied to each by the
    // registers it reads. Record steps on the route write register entries to it.
    if (gov) {
      var bx0 = LEFT - NODE_W / 2 - 12, bx1 = LEFT + maxRank * COL + NODE_W / 2 + 12;
      frames.forEach(function (f) {
        var tie = svg("line", { x1: f.x, y1: f.bottom, x2: f.x, y2: bandY, "class": "pr-tie" }, s);
        svg("title", {}, tie, f.module + " reads GOVERN's registers");
      });
      var band = svg("g", { "class": "pr-band" }, s);
      svg("title", {}, band, gov.label + ": " + gov.description);
      svg("rect", { x: bx0, y: bandY, width: bx1 - bx0, height: BAND_H, rx: 10 }, band);
      svg("text", { x: bx0 + 12, y: bandY + 22, "class": "pr-band-label" }, band,
          gov.label + " · registers and approvals · no patient-level data");
    }

    function edgePath(a, b) {
      var p = pos[a], q = pos[b];
      if (a === b) {
        return { d: "M" + (p.x - 26) + " " + (p.y - NODE_H / 2) + " C" + (p.x - 30) + " " + (p.y - 64) + " " +
                    (p.x + 30) + " " + (p.y - 64) + " " + (p.x + 26) + " " + (p.y - NODE_H / 2),
                 mid: { x: p.x, y: p.y - 56 } };
      }
      var x1 = p.x + NODE_W / 2, y1 = p.y, x2 = q.x - NODE_W / 2, y2 = q.y;
      var c1 = { x: x1 + 50, y: y1 }, c2 = { x: x2 - 50, y: y2 };
      return { d: "M" + x1 + " " + y1 + " C" + c1.x + " " + c1.y + " " + c2.x + " " + c2.y + " " + x2 + " " + y2,
               mid: { x: (x1 + 3 * c1.x + 3 * c2.x + x2) / 8, y: (y1 + 3 * c1.y + 3 * c2.y + y2) / 8 } };
    }

    var faint = svg("g", { "class": "pr-faint" }, s);
    Object.keys(edges).forEach(function (k) {
      var ab = k.split(">"), e = edgePath(ab[0], ab[1]);
      var path = svg("path", { d: e.d, "class": "pr-e", "marker-end": "url(#pr-arrow-faint)" }, faint);
      svg("title", {}, path, ab[0] + " → " + ab[1] + ": " + edges[k].join(", "));
    });
    var nodes = {};
    zones.forEach(function (z) {
      var p = pos[z.id], g = svg("g", { "class": "pr-node", transform: "translate(" + p.x + "," + p.y + ")" }, s);
      svg("title", {}, g, z.id + ": " + (z.description || ""));
      svg("rect", { x: -NODE_W / 2, y: -NODE_H / 2, width: NODE_W, height: NODE_H, rx: 8 }, g);
      svg("text", { y: z.cirroEnvironment ? -3 : 5, "class": "pr-node-name" }, g, z.id);
      if (z.cirroEnvironment) svg("text", { y: 13, "class": "pr-node-sub" }, g, "Cirro environment");
      var tag = svg("text", { y: NODE_H / 2 + 14, "class": "pr-node-tag" }, g, "");
      nodes[z.id] = { g: g, tag: tag };
    });
    var active = svg("g", { "class": "pr-active" }, s);
    return { svg: s, title: title, nodes: nodes, active: active, edgePath: edgePath, pos: pos, bandY: gov ? bandY : null };
  }

  function zoneSeq(data, workflows) {
    var z = data.initialZone, seq = [];
    workflows.forEach(function (w) {
      var to = data.workflows[w].writesTo;
      seq.push({ from: z, to: to, workflow: w });
      z = to;
    });
    return seq;
  }

  function drawRoute(map, data, r) {
    var a = map.active;
    while (a.firstChild) a.removeChild(a.firstChild);
    var main = zoneSeq(data, r.steps.map(function (s) { return s.workflow; }));
    var onPath = {}, used = {};
    onPath[data.initialZone] = true;
    main.forEach(function (m) { onPath[m.to] = true; used[m.from + ">" + m.to] = true; });
    var target = data.targets[r.target].zone;
    Object.keys(map.nodes).forEach(function (z) {
      var n = map.nodes[z], cls = "pr-node";
      if (onPath[z]) cls += " pr-on";
      if (z === target) cls += " pr-target";
      if (z === data.initialZone) cls += " pr-start";
      n.g.setAttribute("class", cls);
      n.tag.textContent = z === target ? "target" : (z === data.initialZone ? "deposited" : "");
    });
    // Further route to release, where it leaves the route to the target.
    if (r.release) {
      zoneSeq(data, r.release).forEach(function (m) {
        var k = m.from + ">" + m.to;
        if (used[k]) return;
        var e = map.edgePath(m.from, m.to);
        var p = svg("path", { d: e.d, "class": "pr-e-alt", "marker-end": "url(#pr-arrow-alt)" }, a);
        svg("title", {}, p, "Route to release: " + m.workflow);
      });
    }
    // The route to the target, with numbered steps. Steps on the same move stack.
    var stacks = {};
    main.forEach(function (m, i) {
      var k = m.from + ">" + m.to, e = map.edgePath(m.from, m.to);
      if (!stacks[k]) {
        stacks[k] = 0;
        var p = svg("path", { d: e.d, "class": "pr-e-on", pathLength: "1", "marker-end": "url(#pr-arrow-on)" }, a);
        svg("title", {}, p, m.from + " → " + m.to);
      }
      var n = stacks[k]++;
      var wfm = data.workflows[m.workflow];
      if (wfm.recordsTo && map.bandY !== null) {
        // A record step writes register entries to GOVERN, not data.
        // It leaves the zone's right side and runs down the gap beside the column, so it
        // crosses no zone box.
        var p0 = map.pos[m.to], gx = p0.x + NODE_W / 2 + 6 + 4 * n;
        var rec = svg("path", { d: "M" + (p0.x + NODE_W / 2) + " " + (p0.y + 10) + " H" + gx + " V" + map.bandY,
                                "class": "pr-e-rec", "marker-end": "url(#pr-arrow-on)" }, a);
        svg("title", {}, rec, (i + 1) + ". " + m.workflow + " writes register entries to GOVERN: " + wfm.recordsTo);
      }
      var dx = m.from === m.to ? (n - 0.5) * 22 : 0, dy = m.from === m.to ? -6 : n * 22;
      var g = svg("g", { "class": "pr-badge", transform: "translate(" + (e.mid.x + dx) + "," + (e.mid.y + dy) + ")" }, a);
      svg("title", {}, g, (i + 1) + ". " + m.workflow + " (" + runnerLabel(data.workflows[m.workflow]) + ")");
      svg("circle", { r: 10 }, g);
      svg("text", { y: 4 }, g, String(i + 1));
    });
    map.title.textContent = "Route: " + [data.initialZone].concat(main.map(function (m, i) {
      return (i + 1) + " " + m.workflow + " to " + m.to;
    })).join(", ") + ". Target zone: " + target + ".";
  }

  function start(data) {
    var props = data.properties;                       // [[id, description], ...]
    var propDesc = {};
    props.forEach(function (p) { propDesc[p[0]] = p[1]; });
    var state = readHash(data);

    var map = buildMap(data);
    function key(cls, label) {
      return el("span", { "class": "pr-legend-item" }, [el("span", { "class": "pr-key " + cls }), txt(label)]);
    }
    var mapWrap = el("div", { "class": "pr-map-wrap" }, [map.svg, el("div", { "class": "pr-legend" }, [
      key("pr-key-on", "Route to the target (numbered steps)"),
      key("pr-key-alt", "Further route to release"),
      key("pr-key-faint", "Other moves the workflows allow (hover for names)"),
      key("pr-key-module", "Platform module"),
      key("pr-key-rec", "Register entries written to GOVERN")
    ])]);
    var form = el("form", { "class": "pr-form", "aria-label": "Describe the file" });
    var result = el("div", { "class": "pr-result", "aria-live": "polite" });
    root.textContent = "";
    root.appendChild(mapWrap);
    root.appendChild(el("div", { "class": "pr-body" }, [form, result]));

    // --- controls -------------------------------------------------------------
    function field(label, control) {
      return el("div", { "class": "pr-field" }, [el("label", { "for": control.id, text: label }), control]);
    }
    var clsSel = el("select", { id: "pr-class" });
    var byModality = {};
    data.classes.forEach(function (c) { (byModality[c.modality] = byModality[c.modality] || []).push(c.name); });
    Object.keys(byModality).sort().forEach(function (m) {
      var g = el("optgroup", { label: m });
      byModality[m].forEach(function (n) { g.appendChild(el("option", { value: n, text: n })); });
      clsSel.appendChild(g);
    });
    var stdSel = el("select", { id: "pr-std" });
    var regBox = el("input", { type: "checkbox", id: "pr-registered" });
    var regLabel = el("label", { "for": "pr-registered" });

    var fileFs = el("fieldset", { "class": "pr-group-box" }, [el("legend", { text: "The file" })]);
    fileFs.appendChild(field("Data class (additionalType)", clsSel));
    fileFs.appendChild(field("Standard (from its file set's conformsTo)", stdSel));
    var dimSelects = [];
    data.dims.forEach(function (d, i) {
      var s = el("select", { id: "pr-dim-" + i });
      d.options.forEach(function (o, j) { s.appendChild(el("option", { value: String(j), text: o.label })); });
      dimSelects.push(s);
      if (d.options.length > 1 && d.name === "fileSetClass") fileFs.appendChild(field("File set class", s));
    });
    form.appendChild(fileFs);

    var flagFs = el("fieldset", { "class": "pr-group-box" }, [el("legend", { text: "Sensitivity flags in the sidecar" })]);
    var flagBoxes = data.flags.map(function (f, j) {
      var box = el("input", { type: "checkbox", id: "pr-flag-" + j });
      flagFs.appendChild(el("div", { "class": "pr-check" }, [box,
        el("label", { "for": "pr-flag-" + j, title: f.description }, [code(f.key)]),
        el("p", { "class": "pr-hint", title: f.description, text: firstSentence(f.description) })]));
      return box;
    });
    form.appendChild(flagFs);

    var srcFs = el("fieldset", { "class": "pr-group-box" }, [el("legend", { text: "The source (source register)" })]);
    srcFs.appendChild(el("div", { "class": "pr-check" }, [regBox, regLabel]));
    data.dims.forEach(function (d, i) {
      if (d.options.length > 1 && d.name.indexOf("register:") === 0) srcFs.appendChild(field(d.name.slice(9), dimSelects[i]));
    });
    form.appendChild(srcFs);

    // --- state <-> controls ----------------------------------------------------
    function fillStd(cls, want) {
      stdSel.textContent = "";
      data.combos.forEach(function (c) {
        if (c[0] !== cls) return;
        stdSel.appendChild(el("option", { value: c[1] === null ? "" : c[1], text: c[1] === null ? "none" : data.standards[c[1]] }));
      });
      var opts = Array.prototype.map.call(stdSel.options, function (o) { return o.value; });
      // Default to the class's standard, if it has one.
      stdSel.value = want !== undefined && opts.indexOf(want) >= 0 ? want : (opts[1] || "");
    }
    function toControls() {
      clsSel.value = state.cls;
      fillStd(state.cls, state.std);
      data.flags.forEach(function (f, j) { flagBoxes[j].checked = !!state.flags[f.key]; });
      regBox.checked = state.registered;
      var mod = data.classes.filter(function (c) { return c.name === state.cls; })[0].modality;
      regLabel.textContent = "";
      [txt("The source is registered for this file's modality ("), code("modalities"), txt(" includes "),
       code(mod), txt(")")].forEach(function (n) { regLabel.appendChild(n); });
      dimSelects.forEach(function (s, i) { s.value = String(state.dims[i]); });
    }
    function fromControls() {
      state.cls = clsSel.value;
      state.std = stdSel.value;
      data.flags.forEach(function (f, j) { state.flags[f.key] = flagBoxes[j].checked; });
      state.registered = regBox.checked;
      state.dims = dimSelects.map(function (s) { return Number(s.value); });
    }
    form.addEventListener("change", function (e) {
      if (e.target === clsSel) { state.cls = clsSel.value; fillStd(state.cls); }
      fromControls();
      toControls();
      writeHash(data, state);
      render();
    });

    // --- lookup (as rules_site.lookup) ----------------------------------------------
    function lookup() {
      var p = 0;
      data.dims.forEach(function (d, i) { p = p * d.options.length + state.dims[i]; });
      var std = state.std === "" ? null : state.std;
      var combo = -1;
      data.combos.forEach(function (c, k) { if (c[0] === state.cls && c[1] === std) combo = k; });
      var bits = 0;
      data.flags.forEach(function (f, j) { if (state.flags[f.key]) bits += 1 << j; });
      var i = ((p * data.combos.length + combo) * (1 << data.flags.length) + bits) * 2 + (state.registered ? 1 : 0);
      var r = data.routes[data.table[i]];
      var startProps = props.filter(function (_, j) { return (r[1] >> j) & 1; }).map(function (q) { return q[0]; });
      var cur = { cls: state.cls, std: std || "none", zone: data.initialZone, props: startProps };
      var start = cur;
      var steps = r[2].map(function (w) {
        var wf = data.workflows[w], clears = wf.clears || [], sets = wf.sets || [];
        cur = {
          cls: wf.produces || cur.cls, std: wf.producesStandard || cur.std, zone: wf.writesTo,
          props: cur.props.filter(function (x) { return clears.indexOf(x) < 0; })
            .concat(sets.filter(function (x) { return cur.props.indexOf(x) < 0; }))
        };
        return { workflow: w, state: cur };
      });
      return { target: r[0], start: start, steps: steps, duties: r[3], release: r[4], pub: r[5],
               ambiguous: r[6] & 1, noRoute: r[6] & 2 };
    }

    // --- rendering ----------------------------------------------------------------
    function propChips(list) {
      if (!list.length) return el("span", { "class": "muted", text: "no tracked properties" });
      var span = el("span", { "class": "pr-props" });
      list.forEach(function (p) { span.appendChild(el("span", { "class": "pr-prop", title: propDesc[p] || "", text: p })); });
      return span;
    }
    function stateLine(s) {
      var std = s.std !== "none" ? " (" + (data.standards[s.std] || s.std) + ")" : "";
      return el("div", { "class": "pr-state" }, [
        el("span", { "class": "pr-zone", text: s.zone }), code(s.cls), txt(std + " "), propChips(s.props)]);
    }
    function workflowChip(w) {
      var wf = data.workflows[w];
      return el("span", { "class": "pr-step", title: wf.description || "" }, [
        el("a", { href: "processing-rules.html#wf-" + w, text: w }), el("small", { text: runnerLabel(wf) })]);
    }
    function routeLine(label, list) {
      var p = el("p", {}, [el("strong", { text: label + ": " })]);
      if (list === null) { p.appendChild(txt("no route under these rules")); return p; }
      list.forEach(function (w, k) {
        if (k) p.appendChild(el("span", { "class": "pr-arrow", "aria-hidden": "true", text: "→" }));
        p.appendChild(workflowChip(w));
      });
      return p;
    }
    function render() {
      var r = lookup(), t = data.targets[r.target];
      drawRoute(map, data, r);
      result.textContent = "";
      result.appendChild(el("div", { "class": "pr-card" }, [
        el("div", { "class": "pr-card-head" }, [el("strong", {}, [txt("Target "), code(r.target)]),
          el("span", { "class": "badge", text: "ends in zone " + t.zone })]),
        el("p", { text: t.sentence }),
        t.note ? el("p", { "class": "muted", text: t.note }) : null]));
      if (r.noRoute) result.appendChild(el("div", { "class": "note pr-fail", text: "No route reaches this target." }));
      if (r.ambiguous) result.appendChild(el("div", { "class": "note pr-fail",
        text: "Two routes tie for this file; the orchestrator would refuse to choose. Set workflow priorities." }));

      result.appendChild(el("h3", { text: "Steps" }));
      var ol = el("ol", { "class": "pr-steps" });
      ol.appendChild(el("li", {}, [el("div", { "class": "pr-step-name", text: "Deposited" }), stateLine(r.start)]));
      r.steps.forEach(function (s, i) {
        ol.appendChild(el("li", {}, [el("div", { "class": "pr-step-name" }, [
          el("span", { "class": "pr-num", text: String(i + 1) }), workflowChip(s.workflow)]), stateLine(s.state)]));
      });
      if (!r.steps.length) ol.appendChild(el("li", { "class": "muted", text: "Nothing to run: it is already at its target." }));
      result.appendChild(ol);

      if (r.duties.length) {
        result.appendChild(el("h3", { text: "Duties from the start" }));
        var ul = el("ul", {});
        r.duties.forEach(function (o) {
          var ob = data.obligations[o];
          ul.appendChild(el("li", {}, [el("a", { href: "processing-rules.html#obligation-" + o }, [code(o)]),
            txt(": " + ob.sentence + (ob.note ? " " + ob.note : ""))]));
        });
        result.appendChild(ul);
      }
      result.appendChild(el("h3", { text: "Release" }));
      result.appendChild(routeLine("Protected-tier release", r.release));
      result.appendChild(routeLine("Public (Open tier)", r.pub));
      result.appendChild(el("p", { "class": "muted",
        text: "Hover over a zone, move, property or workflow for what it means. The address bar holds this description, so you can share the link." }));
    }

    // A shared link opened in a tab that already shows the page changes only the hash;
    // read it again. (writeHash uses replaceState, which fires no hashchange.)
    window.addEventListener("hashchange", function () {
      state = readHash(data);
      toControls();
      render();
    });
    toControls();
    render();
  }

  // --- the description in the address bar, so it can be shared --------------------
  function readHash(data) {
    var q = {};
    location.hash.replace(/^#/, "").split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) q[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1));
    });
    var names = data.classes.map(function (c) { return c.name; });
    var s = { cls: names.indexOf(q["class"]) >= 0 ? q["class"] : (names.indexOf("FhirNdjsonFile") >= 0 ? "FhirNdjsonFile" : names[0]),
              std: q.std, flags: {}, registered: q.registered !== "no", dims: [] };
    data.flags.forEach(function (f) { s.flags[f.key] = q[f.key] === undefined ? f["default"] : q[f.key] === "yes"; });
    data.dims.forEach(function (d) {
      var other = -1, j = q[d.name] !== undefined ? Number(q[d.name]) : NaN;
      d.options.forEach(function (o, k) { if (o.label === "another value") other = k; });
      s.dims.push(j >= 0 && j < d.options.length ? j : (other >= 0 ? other : 0));
    });
    return s;
  }
  function writeHash(data, s) {
    var parts = ["class=" + encodeURIComponent(s.cls), "std=" + encodeURIComponent(s.std || "")];
    data.flags.forEach(function (f) { parts.push(f.key + "=" + (s.flags[f.key] ? "yes" : "no")); });
    parts.push("registered=" + (s.registered ? "yes" : "no"));
    data.dims.forEach(function (d, i) { if (d.options.length > 1) parts.push(encodeURIComponent(d.name) + "=" + s.dims[i]); });
    history.replaceState(null, "", "#" + parts.join("&"));
  }
})();
