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
export function inkLine(box, labels) {
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
  root.append(art, caption);
  box.replaceChildren(root);

  let pos = 0, from = 0, to = STOPS[1] - 0.04, started = performance.now(), expected = 1500, current = -1, frame = 0, finished = false;

  function paint() {
    const x = X0 + W * pos;
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
