// The ink line: a pen nib draws across the stages of a check while it runs. Each stage starts when that step
// really starts; inside a stage the line eases forward without ever reaching the next stage by itself, so it
// never claims progress that hasn't happened. With "reduce motion" on, it jumps from stage to stage.
const NS = "http://www.w3.org/2000/svg";
const X0 = 20, STOPS = [0, 0.34, 0.68, 1];
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, reduced() ? 0 : ms));

function svg(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/**
 * Draws the line into `box` (replacing what's there). labels: four stage names; the last is the finish.
 * Returns { stage(i, text, expectedMs), finish(text), fail() }.
 */
export function inkLine(box, labels, { big = false } = {}) {
  const root = document.createElement("div");
  root.className = "ink-progress";
  // Drawn at the box's real width, so the line and nib keep their size in a narrow panel. Narrow: no labels.
  const width = box.clientWidth >= 560 ? 800 : Math.max(260, box.clientWidth || 320);
  const W = width - 2 * X0, narrow = width < 800;
  root.classList.toggle("narrow", narrow);
  const art = svg("svg", { viewBox: `0 0 ${width} ${narrow ? 64 : 92}`, role: "img", "aria-hidden": "true" });
  art.append(svg("line", { x1: X0, y1: 40, x2: X0 + W, y2: 40, class: "ink-track" }));
  const drawn = svg("line", { x1: X0, y1: 40, x2: X0, y2: 40, class: "ink-drawn" });
  art.append(drawn);
  const dots = STOPS.map((s, i) => {
    const cx = X0 + W * s;
    const dot = svg("circle", { cx, cy: 40, r: 5, class: "ink-dot" });
    const text = svg("text", { x: cx, y: 78, class: "ink-label", "text-anchor": i === 0 ? "start" : i === 3 ? "end" : "middle" });
    text.textContent = labels[i];
    art.append(dot, text);
    return { dot, text, at: s };
  });
  const nib = svg("g", { class: "ink-nib" });
  nib.append(svg("path", { d: "M0 0 L-7 -22 L0 -34 L7 -22 Z", class: "ink-nib-body" }),
    svg("line", { x1: 0, y1: -4, x2: 0, y2: -20, class: "ink-nib-slit" }), svg("circle", { cx: 0, cy: -22, r: 2, class: "ink-nib-slit" }));
  art.append(nib);
  const caption = document.createElement("p");
  caption.className = "ink-caption";
  caption.setAttribute("role", "status");
  // The inkwell: fills with ink as each real step finishes; a drop falls in when the report is ready.
  const well = inkwell(big);
  root.append(well, art, caption);
  box.replaceChildren(root);
  const fill = (f) => well.style.setProperty("--level", f);

  let pos = 0, from = 0, to = STOPS[1] - 0.04, started = performance.now(), expected = 1500, current = -1, frame = 0, finished = false;

  function paint() {
    const x = X0 + W * pos;
    fill(pos);
    drawn.setAttribute("x2", x);
    nib.setAttribute("transform", `translate(${x},40) rotate(-38)`);
    nib.style.opacity = finished ? 0 : 1;
    dots.forEach((d, i) => {
      const reached = pos >= d.at - 0.001;
      d.dot.classList.toggle("on", reached);
      d.dot.setAttribute("r", i === 3 && finished ? 9 : 5);
      d.text.classList.toggle("on", i === current);
    });
  }

  function tick(now) {
    // Within a stage: ease from its start toward (never past) its end, over about the time the step usually takes.
    const goal = from + (to - from) * (1 - Math.exp(-(now - started) / expected));
    pos += (goal - pos) * 0.12;
    paint();
    if (!finished) frame = requestAnimationFrame(tick);
  }

  function stage(i, text, expectedMs = 1500) {
    current = i;
    caption.textContent = text;
    from = Math.max(pos, STOPS[i]);
    to = STOPS[i + 1] - 0.04;
    expected = expectedMs;
    started = performance.now();
    if (reduced()) { pos = from; paint(); return; }
    if (!frame) frame = requestAnimationFrame(tick);
  }

  /** Draws to the end and settles. Resolves when the line has finished, so the results can fade in after it. */
  async function finish(text) {
    current = 3;
    well.classList.add("full");
    cancelAnimationFrame(frame); frame = 0;
    if (!reduced()) {
      const start = pos, t0 = performance.now(), ms = 450;
      await new Promise((resolve) => {
        const step = (now) => {
          const t = Math.min(1, (now - t0) / ms);
          pos = start + (1 - start) * (1 - (1 - t) ** 3);
          paint();
          t < 1 ? requestAnimationFrame(step) : resolve();
        };
        requestAnimationFrame(step);
      });
    }
    pos = 1; finished = true; paint();
    caption.replaceChildren();
    caption.append(Object.assign(document.createElement("strong"), { textContent: "Done. " }), text);
    await wait(350);
  }

  function fail() { cancelAnimationFrame(frame); frame = 0; finished = true; root.remove(); }

  paint();
  return { stage, finish, fail, wait };
}

/** A glass inkwell whose ink rises to --level (0 to 1). Static markup only. */
export function inkwell(big = false) {
  const box = document.createElement("div");
  box.className = `inkwell${big ? " big" : ""}`;
  box.setAttribute("aria-hidden", "true");
  box.innerHTML = `<svg viewBox="0 0 120 130"><defs><clipPath id="iw-clip${big ? "-b" : ""}"><path d="M20 52 Q20 40 36 38 L84 38 Q100 40 100 52 L100 108 Q100 120 88 120 L32 120 Q20 120 20 108 Z"/></clipPath>
<linearGradient id="iw-glass${big ? "-b" : ""}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset=".5" stop-color="#f0f0f0" stop-opacity=".25"/><stop offset="1" stop-color="#d6d6d6" stop-opacity=".75"/></linearGradient>
<linearGradient id="iw-ink${big ? "-b" : ""}" x1="0" x2="1"><stop offset="0" stop-color="#1a1a1a"/><stop offset=".55" stop-color="#0a0a0a"/><stop offset="1" stop-color="#000000"/></linearGradient></defs>
<ellipse cx="60" cy="123" rx="46" ry="6" class="iw-shadow"/>
<g clip-path="url(#iw-clip${big ? "-b" : ""})"><g class="iw-ink"><rect x="14" y="36" width="92" height="88" fill="url(#iw-ink${big ? "-b" : ""})"/><ellipse cx="60" cy="36" rx="42" ry="5" fill="#3a3a3a"/></g></g>
<path d="M20 52 Q20 40 36 38 L84 38 Q100 40 100 52 L100 108 Q100 120 88 120 L32 120 Q20 120 20 108 Z" fill="url(#iw-glass${big ? "-b" : ""})" class="iw-glass"/>
<rect x="44" y="22" width="32" height="17" rx="4" class="iw-neck"/><rect x="41" y="18" width="38" height="7" rx="3" class="iw-cap"/>
<path d="M30 56 Q31 82 30 108" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".6" fill="none"/>
<path class="iw-drop" d="M60 0 Q54 9 60 16 Q66 9 60 0Z" fill="#0a0a0a"/></svg>`;
  return box;
}

/**
 * The check as a whole temporary page: the inkwell and the ink line, then "Done!", then it fades away to reveal
 * the results. Returns { box (where the ink line goes), done(title, sub), close() }.
 */
export function checkScreen() {
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const screen = document.createElement("div");
  screen.className = "welcome-screen check-screen";
  screen.setAttribute("role", "status");
  const box = document.createElement("div");
  box.className = "check-inner";
  screen.append(box);
  document.body.append(screen);
  const close = () => new Promise((resolve) => {
    screen.classList.add("leaving");
    setTimeout(() => { screen.remove(); resolve(); }, calm ? 0 : 450);
  });
  /** "Done!" with the full inkwell for a breath; resolves when it's time to show the results. */
  const done = (title, sub) => {
    const well = inkwell(true);
    well.classList.add("full");
    well.style.setProperty("--level", 1);
    const h = Object.assign(document.createElement("h1"), { textContent: title });
    const p = Object.assign(document.createElement("p"), { textContent: sub });
    box.replaceChildren(Object.assign(document.createElement("div"), { className: "done-inner" }));
    box.firstChild.append(well, h, p);
    return new Promise((resolve) => setTimeout(resolve, calm ? 700 : 1500));
  };
  return { box, done, close };
}
