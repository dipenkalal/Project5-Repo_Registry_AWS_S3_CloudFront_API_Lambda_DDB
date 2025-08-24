// app.js - Fixed, unified version

const API = "https://o4hzlr5rqd.execute-api.us-east-2.amazonaws.com/prod";

const form = document.getElementById("submitForm");
const msg = document.getElementById("submitMsg");
const list = document.getElementById("list");
const refreshBtn = document.getElementById("refreshBtn");
const loadMoreBtn = document.getElementById("loadMoreBtn");

let nextCursor = null;
let loading = false;

// --- Normalize each item ---
function normalizeItem(it) {
  // Handle DynamoDB attribute values
  const unwrap = (v) =>
    v && typeof v === "object"
      ? ("S" in v ? v.S
        : "N" in v ? Number(v.N)
        : "BOOL" in v ? !!v.BOOL
        : v)
      : v;

  const obj = {};
  for (const [k, v] of Object.entries(it)) obj[k] = unwrap(v);

  return {
    repo_url: obj.repo_url || obj.url || obj.link || "#",
    title: obj.title || obj.project_title || obj.repo || "(untitled)",
    submitter: obj.submitter || obj.author || obj.owner || "",
    description: obj.description || obj.details || "",
    createdAt: obj.createdAt || obj.created_at || obj.ts || obj.timestamp || 0,
    owner: obj.owner,
    repo: obj.repo,
  };
}

// --- Render ---
function render(items, append = false) {
  const frag = document.createDocumentFragment();

  if (!append) list.innerHTML = "";

  if (!items || items.length === 0) {
    if (!append) list.innerHTML = `<div class="text-muted">No submissions yet.</div>`;
    return;
  }

  for (const raw of items) {
    const it = normalizeItem(raw);

    const a = document.createElement("a");
    a.href = it.repo_url;
    a.target = "_blank";
    a.rel = "noopener";

    const card = document.createElement("div");
    card.className = "item";

    const h3 = document.createElement("h3");
    h3.textContent = it.title;

    const meta = document.createElement("p");
    const dt = it.createdAt ? new Date(Number(it.createdAt) * 1000).toLocaleString() : "";
    const ownerRepo = it.owner && it.repo ? `${it.owner}/${it.repo}` : "";
    meta.textContent = [ownerRepo, dt, it.submitter && `by ${it.submitter}`].filter(Boolean).join(" • ");

    const desc = document.createElement("p");
    desc.textContent = it.description;

    card.appendChild(h3);
    card.appendChild(meta);
    card.appendChild(desc);
    a.appendChild(card);
    frag.appendChild(a);
  }

  list.appendChild(frag);
}

// --- API: GET page ---
async function fetchPage(cursor = null) {
  const url = new URL(`${API}/projects`);
  url.searchParams.set("limit", "12");
  if (cursor) url.searchParams.set("cursor", cursor);

  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));

  if (!res.ok) throw new Error(data.error || res.statusText);

  nextCursor = data.next_cursor ?? data.nextCursor ?? data.cursor ?? null;
  loadMoreBtn.style.display = nextCursor ? "inline-flex" : "none";

  return (
    data.items ??
    data.projects ??
    data.data ??
    data.Items ??
    (Array.isArray(data) ? data : [])
  );
}

// --- Actions ---
async function refresh() {
  if (loading) return;
  loading = true;
  try {
    nextCursor = null;
    const items = await fetchPage(null);
    render(items, false);
    msg.textContent = "";
  } catch (e) {
    msg.textContent = `Error: ${e.message}`;
    console.error(e);
  } finally {
    loading = false;
  }
}

async function loadMore() {
  if (!nextCursor || loading) return;
  loading = true;
  try {
    const items = await fetchPage(nextCursor);
    render(items, true);
  } catch (e) {
    msg.textContent = `Error: ${e.message}`;
    console.error(e);
  } finally {
    loading = false;
  }
}

async function submitProject(e) {
  e.preventDefault();
  msg.textContent = "Submitting...";
  const payload = {
    repo_url: document.getElementById("repo_url").value.trim(),
    title: document.getElementById("title").value.trim(),
    submitter: document.getElementById("submitter").value.trim(),
    description: document.getElementById("description").value.trim(),
  };

  try {
    const res = await fetch(`${API}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data.error || res.status);

    msg.textContent = "✅ Submitted!";
    form.reset();
    await refresh();
  } catch (err) {
    msg.textContent = `Error: ${err.message}`;
    console.error(err);
  }
}

// --- Wire up ---
form.addEventListener("submit", submitProject);
refreshBtn.addEventListener("click", refresh);
loadMoreBtn.addEventListener("click", loadMore);

refresh();
