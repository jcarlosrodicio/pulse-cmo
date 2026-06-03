"use client";

// Export the project's plan as a downloadable markdown brief (website fixes +
// steps/actions + strategy) and a standalone, trackable HTML to-do checklist.

import type { Action, Project, ProjectDocument } from "./api";

const ACTION_GROUPS: { types: string[]; label: string }[] = [
  { types: ["seo_fix"], label: "Website / SEO fixes" },
  { types: ["tweet", "linkedin", "hn_post", "article"], label: "Content to publish" },
  { types: ["reddit_reply", "reddit_opportunity", "hn_opportunity"], label: "Community replies" },
  { types: ["market_gap"], label: "Market gaps" },
  { types: ["strategy"], label: "Strategy" },
];

function today(): string {
  try {
    return new Date().toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

function sev(s?: string): string {
  return s ? `[${s.toUpperCase()}] ` : "";
}

export function slugify(s: string): string {
  return (
    (s || "project")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "project"
  );
}

// ---------------------------------------------------------------------------
// Markdown plan
// ---------------------------------------------------------------------------

export function buildPlanMarkdown(
  project: Project,
  actions: Action[],
  docs: ProjectDocument[],
): string {
  const L: string[] = [];
  L.push(`# ${project.name} — Pulse action plan`);
  L.push(`${project.url}  ·  exported ${today()}`);
  L.push("");
  if (project.description) {
    L.push(`> ${project.description}`);
    L.push("");
  }

  // --- Website fixes (the "adjust your site" part) ---
  L.push("## Website fixes");
  L.push("_Things to change on your site, from the latest audits._");
  L.push("");
  let anyFix = false;
  const seo = project.seo_summary;
  if (seo?.findings?.length) {
    anyFix = true;
    L.push(`### On-page SEO — score ${seo.score}/100`);
    for (const f of seo.findings) {
      L.push(`- ${sev(f.severity)}**${f.category}** — ${f.description}`);
      if (f.fix) L.push(`  - Fix: ${f.fix}`);
    }
    L.push("");
  }
  const geo = project.geo_summary;
  if (geo?.findings?.length) {
    anyFix = true;
    L.push(`### AI / GEO readiness — score ${geo.score}/100`);
    for (const f of geo.findings) {
      L.push(`- ${sev(f.severity)}**${f.category}** — ${f.description}`);
      if (f.fix) L.push(`  - Fix: ${f.fix}`);
    }
    L.push("");
  }
  const links = project.links_summary;
  if (links?.broken?.length) {
    anyFix = true;
    L.push("### Broken links");
    for (const b of links.broken) L.push(`- ${b.url} (status ${b.status})`);
    L.push("");
  }
  if (!anyFix) {
    L.push("_No audit findings yet — run a dive, or the SEO / GEO / Links audits._");
    L.push("");
  }

  // --- Steps & actions ---
  L.push("## Steps & actions");
  L.push("");
  const live = actions.filter((a) => a.status !== "dismissed");
  if (!live.length) {
    L.push("_No actions yet — run a dive or a daily pass._");
    L.push("");
  } else {
    const known = new Set(ACTION_GROUPS.flatMap((g) => g.types));
    const groups = [
      ...ACTION_GROUPS.map((g) => ({ label: g.label, items: live.filter((a) => g.types.includes(a.action_type)) })),
      { label: "Other", items: live.filter((a) => !known.has(a.action_type)) },
    ];
    for (const g of groups) {
      if (!g.items.length) continue;
      L.push(`### ${g.label}`);
      L.push("");
      for (const a of g.items) {
        const flag = a.status === "shipped" ? " — ✓ shipped" : "";
        L.push(`#### ${a.title}${flag}`);
        if (a.content?.trim()) {
          L.push("");
          L.push(a.content.trim());
        }
        L.push("");
      }
    }
  }

  // --- Strategy documents ---
  for (const [kind, label] of [
    ["positioning", "Positioning & strategy"],
    ["marketing_strategy", "Marketing strategy"],
  ] as const) {
    const d = docs.find((x) => x.kind === kind);
    if (d?.content_md?.trim()) {
      L.push(`## ${label}`);
      L.push("");
      L.push(d.content_md.trim());
      L.push("");
    }
  }

  return L.join("\n");
}

// ---------------------------------------------------------------------------
// HTML to-do checklist (standalone, persists checks to localStorage)
// ---------------------------------------------------------------------------

type TodoItem = { id: string; label: string; sub?: string; done?: boolean };

function esc(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function buildTodoHtml(project: Project, actions: Action[]): string {
  const sections: { title: string; items: TodoItem[] }[] = [];

  const web: TodoItem[] = [];
  for (const f of project.seo_summary?.findings ?? [])
    web.push({ id: `seo:${f.category}:${f.description}`.slice(0, 140), label: `${f.category}: ${f.description}`, sub: f.fix });
  for (const f of project.geo_summary?.findings ?? [])
    web.push({ id: `geo:${f.category}:${f.description}`.slice(0, 140), label: `${f.category}: ${f.description}`, sub: f.fix });
  for (const b of project.links_summary?.broken ?? [])
    web.push({ id: `link:${b.url}`.slice(0, 140), label: `Fix broken link: ${b.url}`, sub: `status ${b.status}` });
  if (web.length) sections.push({ title: "Website fixes", items: web });

  const acts: TodoItem[] = actions
    .filter((a) => a.status !== "dismissed")
    .map((a) => ({
      id: `action:${a.id}`,
      label: a.title,
      sub: a.action_type.replace(/_/g, " "),
      done: a.status === "shipped",
    }));
  if (acts.length) sections.push({ title: "Marketing actions", items: acts });

  if (!sections.length) sections.push({ title: "To do", items: [{ id: "empty", label: "Nothing yet — run a dive in Pulse, then export again." }] });

  const key = `pulse-todo-${project.id}`;
  const body = sections
    .map(
      (s) => `    <section>
      <h2>${esc(s.title)} <span class="count">${s.items.length}</span></h2>
${s.items
        .map(
          (it) => `      <label class="item${it.done ? " done" : ""}">
        <input type="checkbox" data-id="${esc(it.id)}"${it.done ? " checked" : ""}>
        <span class="txt"><span class="lbl">${esc(it.label)}</span>${it.sub ? `<span class="sub">${esc(it.sub)}</span>` : ""}</span>
      </label>`,
        )
        .join("\n")}
    </section>`,
    )
    .join("\n");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(project.name)} — to-do</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 22px; margin: 0 0 2px; }
  h1 .meta { font-size: 13px; font-weight: 400; color: #777; }
  .bar { height: 8px; background: #e3e3e3; border-radius: 99px; overflow: hidden; margin: 16px 0 6px; }
  .bar > div { height: 100%; background: #f0b429; width: 0; transition: width .2s; }
  .progress { font-size: 13px; color: #777; margin-bottom: 22px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .07em; color: #999; margin: 26px 0 10px; }
  h2 .count { font-weight: 400; opacity: .7; }
  .item { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border: 1px solid #e6e6e6; border-radius: 10px; margin-bottom: 6px; cursor: pointer; background: #fff; }
  .item input { margin-top: 2px; width: 16px; height: 16px; accent-color: #f0b429; cursor: pointer; }
  .txt { display: flex; flex-direction: column; }
  .lbl { font-weight: 500; }
  .sub { font-size: 12.5px; color: #999; margin-top: 1px; }
  .item.done .lbl { text-decoration: line-through; opacity: .5; }
  @media (prefers-color-scheme: dark) {
    body { color: #e6e6e6; background: #151515; }
    .item { background: #1c1c1c; border-color: #2b2b2b; }
    .bar { background: #2b2b2b; }
  }
</style>
</head>
<body>
  <h1>${esc(project.name)} <span class="meta">— to-do · ${esc(project.url)}</span></h1>
  <div class="bar"><div id="barfill"></div></div>
  <div class="progress" id="progress"></div>
${body}
  <script>
    var KEY = ${JSON.stringify(key)};
    var state = {};
    try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
    var boxes = [].slice.call(document.querySelectorAll('input[type=checkbox]'));
    function render() {
      var done = 0;
      boxes.forEach(function (b) {
        var id = b.getAttribute('data-id');
        if (id in state) b.checked = state[id];
        if (b.checked) done++;
        b.closest('.item').classList.toggle('done', b.checked);
      });
      var total = boxes.length;
      var pct = total ? Math.round((done / total) * 100) : 0;
      document.getElementById('barfill').style.width = pct + '%';
      document.getElementById('progress').textContent = done + ' of ' + total + ' done (' + pct + '%)';
    }
    boxes.forEach(function (b) {
      b.addEventListener('change', function () {
        state[b.getAttribute('data-id')] = b.checked;
        try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
        render();
      });
    });
    render();
  </script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------

export function downloadFile(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
