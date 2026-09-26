const app = document.getElementById("app");
const tokenKey = "funnyc_token";
const meKey = "funnyc_me";
let token = localStorage.getItem(tokenKey);
let me = JSON.parse(localStorage.getItem(meKey) || "null");
let posts = [];
let idx = 0;
let startX = 0;
let startY = 0;
let version = "";

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (token) headers.Authorization = "Bearer " + token;
  const r = await fetch(path, Object.assign({}, opts, { headers }));
  const text = await r.text();
  const data = text ? JSON.parse(text) : {};
  if (!r.ok) throw new Error(data.detail || text || "erro");
  return data;
}

function render() {
  if (!token) return loginView();
  stageView();
}

function loginView() {
  app.innerHTML = `
    <div class="login">
      <h1>Funnyc</h1>
      <p>memes. smiles. caos.</p>
      <input id="user" placeholder="username" value="demo" />
      <input id="pass" type="password" placeholder="senha" value="demo123" />
      <input id="email" placeholder="email (só no cadastro)" />
      <div class="err" id="err"></div>
      <button class="go" id="enter">entrar</button>
      <button class="go" id="reg" style="background:#222;color:#c8f542">criar conta</button>
    </div>`;
  document.getElementById("enter").onclick = () => auth("/api/auth/login", false);
  document.getElementById("reg").onclick = () => auth("/api/auth/register", true);
}

async function auth(path, isReg) {
  const err = document.getElementById("err");
  err.textContent = "";
  try {
    const body = {
      username: document.getElementById("user").value.trim(),
      password: document.getElementById("pass").value,
    };
    if (isReg) body.email = document.getElementById("email").value.trim();
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    token = data.access_token;
    me = data.user;
    localStorage.setItem(tokenKey, token);
    localStorage.setItem(meKey, JSON.stringify(me));
    await loadFeed();
  } catch (e) {
    err.textContent = e.message;
  }
}

async function loadFeed() {
  app.innerHTML = `<div class="screen"><div class="stage" style="display:grid;place-items:center">carregando...</div></div>`;
  try {
    posts = await api("/api/feed/featured");
    if (!posts.length) posts = await api("/api/feed/collective");
    idx = 0;
    stageView();
  } catch (e) {
    app.innerHTML = `<div class="login"><p>${e.message}</p><button class="go" id="retry">tentar de novo</button></div>`;
    document.getElementById("retry").onclick = loadFeed;
  }
}

function stageView() {
  const p = posts[idx];
  const letter = (me && me.username ? me.username[0] : "?").toUpperCase();
  if (!p) {
    app.innerHTML = `<div class="login"><p>Nenhum meme ainda.</p></div>`;
    return;
  }
  app.innerHTML = `
    <div class="screen">
      <div class="stage" id="stage">
        <div class="meme"><img src="${p.media_url}" alt="" /></div>
        <div class="shade"></div>
        <div class="cap">
          <h2>${escapeHtml(p.caption || "")}</h2>
          <div class="tags">${(p.tags || []).map((t) => "#" + t).join("  ")}</div>
          <div class="hint">lado: próximo · baixo: comentários · cima: perfil · segura: menu</div>
        </div>
        <div class="side">
          <button class="round" id="smile">☺</button>
          <span>${p.smiles_count}</span>
          <button class="round" id="com">💬</button>
          <span>${p.comments_count}</span>
        </div>
      </div>
      <div class="bar">
        <button id="home">⚡</button>
        <button class="plus" id="plus">+</button>
        <button class="av" id="me">${letter}</button>
      </div>
    </div>`;
  const stage = document.getElementById("stage");
  stage.addEventListener("touchstart", onStart, { passive: true });
  stage.addEventListener("touchend", onEnd);
  stage.addEventListener("mousedown", onStart);
  stage.addEventListener("mouseup", onEnd);
  let hold;
  stage.addEventListener("touchstart", () => { hold = setTimeout(openMenu, 450); }, { passive: true });
  stage.addEventListener("touchend", () => clearTimeout(hold));
  stage.addEventListener("contextmenu", (e) => { e.preventDefault(); openMenu(); });
  document.getElementById("smile").onclick = smile;
  document.getElementById("com").onclick = openComments;
  document.getElementById("plus").onclick = openUpload;
  document.getElementById("me").onclick = () => openProfile(me.username);
  document.getElementById("home").onclick = loadFeed;
}

function onStart(e) {
  const t = e.changedTouches ? e.changedTouches[0] : e;
  startX = t.clientX;
  startY = t.clientY;
}
function onEnd(e) {
  const t = e.changedTouches ? e.changedTouches[0] : e;
  const dx = t.clientX - startX;
  const dy = t.clientY - startY;
  if (Math.abs(dx) < 40 && Math.abs(dy) < 40) return;
  if (Math.abs(dx) > Math.abs(dy)) {
    if (dx < 0 && idx < posts.length - 1) { idx += 1; stageView(); }
    if (dx > 0 && idx > 0) { idx -= 1; stageView(); }
  } else {
    if (dy > 70) openComments();
    if (dy < -70) openProfile(posts[idx].username);
  }
}

async function smile() {
  const p = await api("/api/posts/" + posts[idx].id + "/smile", { method: "POST" });
  posts[idx] = p;
  stageView();
}

function openMenu() {
  const wrap = document.createElement("div");
  wrap.className = "menu";
  wrap.innerHTML = `
    <button id="m-share">Compartilhar</button>
    <button id="m-save">Salvar</button>
    <button id="m-prof">Perfil de @${posts[idx].username}</button>
    <button id="m-com">Comentários</button>
    <button id="m-rep">Denunciar</button>
    <button id="m-x">Fechar</button>`;
  document.querySelector(".stage").appendChild(wrap);
  wrap.querySelector("#m-x").onclick = () => wrap.remove();
  wrap.querySelector("#m-share").onclick = async () => {
    await navigator.clipboard.writeText(posts[idx].media_url);
    wrap.remove();
  };
  wrap.querySelector("#m-save").onclick = async () => {
    await api("/api/posts/" + posts[idx].id + "/collect", { method: "POST" });
    wrap.remove();
  };
  wrap.querySelector("#m-prof").onclick = () => openProfile(posts[idx].username);
  wrap.querySelector("#m-com").onclick = openComments;
  wrap.querySelector("#m-rep").onclick = () => { alert("Denúncia enviada"); wrap.remove(); };
}

async function openComments() {
  const p = posts[idx];
  const rows = await api("/api/comments/" + p.id);
  app.innerHTML = `
    <div class="sheet">
      <header><button id="back">↓  comentários</button></header>
      <div class="list">${rows.map((c) => `<div class="row"><b>@${c.username}</b>${escapeHtml(c.text)}</div>`).join("") || "<div class='muted'>ninguém comentou ainda</div>"}</div>
      <div class="composer"><input id="ct" placeholder="escreve um comentário" /><button class="plus" id="send">ok</button></div>
    </div>`;
  document.getElementById("back").onclick = stageView;
  document.getElementById("send").onclick = async () => {
    const text = document.getElementById("ct").value.trim();
    if (!text) return;
    await api("/api/comments/" + p.id, { method: "POST", body: JSON.stringify({ text }) });
    openComments();
  };
}

async function openProfile(username) {
  const u = await api("/api/users/" + username);
  app.innerHTML = `
    <div class="sheet">
      <header><button id="back">↑  @${u.username}</button></header>
      <div class="list">
        <p class="muted">${escapeHtml(u.bio || "")}</p>
        <p class="muted">${u.posts_count} memes · ${u.followers} followers</p>
        ${(u.posts || []).map((p) => `<div class="row"><img src="${p.media_url}" style="width:100%;border-radius:8px" /></div>`).join("")}
        ${u.is_me ? `<button class="go" id="out" style="background:#222;color:#fff">sair</button>` : `<button class="go" id="fol">${u.is_following ? "seguindo" : "seguir"}</button>`}
      </div>
    </div>`;
  document.getElementById("back").onclick = stageView;
  const out = document.getElementById("out");
  if (out) out.onclick = () => { token = null; me = null; localStorage.clear(); render(); };
  const fol = document.getElementById("fol");
  if (fol) fol.onclick = async () => { await api("/api/users/" + username + "/follow", { method: "POST" }); openProfile(username); };
}

function openUpload() {
  app.innerHTML = `
    <div class="sheet">
      <header><button id="back">fechar</button></header>
      <div class="list">
        <input id="file" type="file" accept="image/*" />
        <input id="cap" placeholder="legenda" />
        <input id="tags" placeholder="tags  ex: gatos humor" />
        <div class="err" id="err"></div>
        <button class="go" id="send">postar</button>
      </div>
    </div>`;
  document.getElementById("back").onclick = stageView;
  document.getElementById("send").onclick = async () => {
    const f = document.getElementById("file").files[0];
    if (!f) { document.getElementById("err").textContent = "escolhe uma imagem"; return; }
    const fd = new FormData();
    fd.append("file", f);
    fd.append("caption", document.getElementById("cap").value);
    fd.append("tags", document.getElementById("tags").value);
    const r = await fetch("/api/posts", { method: "POST", headers: { Authorization: "Bearer " + token }, body: fd });
    if (!r.ok) { document.getElementById("err").textContent = "falhou o upload"; return; }
    await loadFeed();
  };
}

function escapeHtml(s) {
  return String(s)
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join("&#39;");
}
async function watchUpdates() {
  try {
    const v = await api("/api/version");
    const mark = String(v.v);
    if (version && version !== mark) location.reload();
    version = mark;
  } catch (_) {}
}

render();
if (token) loadFeed();
setInterval(watchUpdates, 4000);
watchUpdates();
