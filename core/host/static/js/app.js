
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const page = $("#app")?.dataset.page || "dashboard";
let settingsCache = null;
let statusCache = null;

function nav(active){
  const items = [
    ["dashboard","Dashboard","/"],["platforms","Plattformen","/plattformen"],["chat","Chat","/chat"],
    ["spotify","Spotis3mptify","/spotis3mptify"],["overlays","Overlay URLs","/overlays"],["plugins","Plugins","/plugins"],["dev","DEV","/dev"]
  ];
  return `<aside class="sidebar"><div class="brand"><div class="logo"></div><div><h1>godisalotachat</h1><div class="ver">Ver. ${window.WEB_VERSION}</div></div><div class="webbased">webbased</div></div><nav class="nav">${items.map(i=>`<a class="${active===i[0]?'active':''}" href="${i[2]}">${i[1]}</a>`).join("")}</nav></aside>`;
}
function shell(active, title, sub, body){
  $("#app").innerHTML = `<div class="layout">${nav(active)}<main class="content"><div class="top"><div><h2>${title}</h2><div class="sub">${sub||""}</div></div></div>${body}</main></div>`;
}
async function api(url, opts){
  const r=await fetch(url,{cache:"no-store",...(opts||{})});
  let data=null;
  try{ data=await r.json(); }catch(e){ data={ok:false,error:String(e||"Ungültige JSON-Antwort")}; }
  if(!r.ok){ data.ok=false; data.http_status=r.status; data.error=data.error||`HTTP ${r.status}`; }
  return data;
}
async function loadAll(){ settingsCache=await api("/api/settings"); statusCache=await api("/api/status"); return {settings:settingsCache,status:statusCache};}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}
function userColor(platform,user){let h=2166136261;for(const c of `${platform}:${user}`){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `hsl(${Math.abs(h)%360} 78% 68%)`;}
function platformMark(p){return ({twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"}[p]||p);}
function platformBadge(p){return `<span class="chatPlatform ${esc(p)}"><img src="/platform-icon/${esc(p)}" alt="">${esc(platformMark(p))}</span>`;}
function platformLabel(p){return ({twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick",spotify:"Spotify",openai:"ChatGPT / OpenAI",meld:"Meld",obs:"OBS"}[p]||p);}
function card(p,cfg){
  const st = cfg.status || "nicht verbunden";
  const ok = st==="verbunden";
  let details = "";
  if(p==="tiktok") details = cfg.detail ? esc(cfg.detail) : `Main: ${esc(cfg.main||"-")}<br>Bot: ${esc(cfg.bot||"-")}`;
  else if(p==="twitch"||p==="youtube"||p==="kick") details = `Main: ${esc(cfg.main||"-")}<br>Bot: ${esc(cfg.bot||"-")}`;
  else if(p==="spotify") details = ``;
  else if(p==="openai") details = cfg.detail ? esc(cfg.detail) : `Modell: ${esc(cfg.model||"-")}`;
  else if(p==="meld") details = cfg.detail ? esc(cfg.detail) : ``;
  else if(p==="obs") details = cfg.detail ? esc(cfg.detail) : ``;
  else details = `Host: ${esc(cfg.host||"-")}:${esc(cfg.port||"-")}`;
  return `<div class="card" data-platform-card="${esc(p)}"><div class="label">${platformLabel(p)}</div><div class="status"><span class="dot ${ok?'ok':''}"></span><span class="statusText">${ok?'Verbunden':'Bereit'}</span></div><div class="small cardDetails">${details}</div></div>`;
}
function updatePlatformCard(p,cfg){
  const el=document.querySelector(`[data-platform-card="${p}"]`);
  if(!el)return;
  const st = cfg.status || "nicht verbunden";
  const ok = st === "verbunden";
  const dot = el.querySelector(".dot");
  const txt = el.querySelector(".statusText");
  const details = el.querySelector(".cardDetails");
  if(dot) dot.classList.toggle("ok", ok);
  if(txt) txt.textContent = ok ? "Verbunden" : (cfg.enabled ? "Nicht verbunden" : "Inaktiv");
  if(details && (p === "meld" || p === "obs" || p === "tiktok" || p === "openai")) details.textContent = cfg.detail || "";
}
let meldDashboardPoll = null;
let obsDashboardPoll = null;
let youtubeDashboardPoll = null;
let tiktokDashboardPoll = null;
function startTikTokDashboardPoll(){
  if(page !== "dashboard" || tiktokDashboardPoll) return;
  let stopped = false;
  const tick = async()=>{
    if(stopped) return;
    try{
      const s = await api("/api/status");
      const tiktok = (s.platforms || {}).tiktok || {};
      updatePlatformCard("tiktok", tiktok);
      if(tiktok.status === "verbunden"){
        stopped = true;
        clearInterval(tiktokDashboardPoll);
        tiktokDashboardPoll = null;
      }
    }catch(e){}
  };
  tiktokDashboardPoll = setInterval(tick, 3000);
  setTimeout(tick, 700);
}
function startYoutubeDashboardPoll(){
  if(page !== "dashboard" || youtubeDashboardPoll) return;
  let stopped = false;
  const tick = async()=>{
    if(stopped) return;
    try{
      const s = await api("/api/status");
      const youtube = (s.platforms || {}).youtube || {};
      updatePlatformCard("youtube", youtube);
      if(youtube.status === "verbunden"){
        stopped = true;
        clearInterval(youtubeDashboardPoll);
        youtubeDashboardPoll = null;
      }
    }catch(e){}
  };
  youtubeDashboardPoll = setInterval(tick, 5000);
  setTimeout(tick, 1000);
}

function startMeldDashboardPoll(){
  if(page !== "dashboard" || meldDashboardPoll) return;
  let stopped = false;
  const tick = async()=>{
    if(stopped) return;
    try{
      const s = await api("/api/status");
      const meld = (s.platforms || {}).meld || {};
      updatePlatformCard("meld", meld);
      if(meld.status === "verbunden"){
        stopped = true;
        clearInterval(meldDashboardPoll);
        meldDashboardPoll = null;
      }
    }catch(e){}
  };
  meldDashboardPoll = setInterval(tick, 3000);
  setTimeout(tick, 600);
}

function startObsDashboardPoll(){
  if(page !== "dashboard" || obsDashboardPoll) return;
  let stopped = false;
  const tick = async()=>{
    if(stopped) return;
    try{
      const s = await api("/api/status");
      const obs = (s.platforms || {}).obs || {};
      updatePlatformCard("obs", obs);
      if(obs.status === "verbunden"){
        stopped = true;
        clearInterval(obsDashboardPoll);
        obsDashboardPoll = null;
      }
    }catch(e){}
  };
  obsDashboardPoll = setInterval(tick, 3000);
  setTimeout(tick, 800);
}
async function renderDashboard(){
  const {status}=await loadAll();
  const p=status.platforms;
  shell("dashboard","Dashboard","Übersicht & Status",`
    <div class="grid cards">${["twitch","tiktok","youtube","kick","spotify","openai","meld","obs"].map(k=>card(k,p[k]||{})).join("")}</div>
    <div class="mainGrid">
      <section class="card chatBox"><div class="label">Live Chat</div><div class="messages" id="messages"></div><div class="sendRow"><input id="testmsg" placeholder="Testnachricht ins Overlay schicken"><button id="sendMsg">Senden</button></div></section>
      <div>
        <section class="card spotifyPreview"><div class="npCoverBox"><div class="disc" id="dashDisc"></div><img id="npCover" alt=""></div><div><div class="label">Spotis3mptify</div><h3 id="npTitle">Kein Song aktiv</h3><div class="small" id="npArtist"></div></div></section>
        <section class="card" style="margin-top:18px"><div class="label">Browserquellen</div><p class="small">Diese URLs direkt in OBS, Meld oder Browserquelle eintragen.</p><div id="dashUrls" class="miniUrls"></div><a class="btn" href="/overlays">Alle URLs öffnen</a></section>
      </div>
    </div>
    <section class="card" style="margin-top:18px"><div class="label">Plugins</div><div id="plugMini" class="pluginGrid"></div></section>`);
  $("#sendMsg").onclick=async()=>{let v=$("#testmsg").value.trim(); if(!v)return; await api("/api/message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v})}); $("#testmsg").value=""; refreshMessages();};
  refreshMessages(); refreshNowPlaying(); loadDashboardUrls();
  $("#plugMini").innerHTML = status.plugins.slice(0,6).map(x=>`<div class="msg"><b>${esc(x.name)}</b><div class="small">${esc(x.status)}</div></div>`).join("");
  if(((status.platforms || {}).tiktok || {}).status !== "verbunden") startTikTokDashboardPoll();
  if(((status.platforms || {}).youtube || {}).status !== "verbunden") startYoutubeDashboardPoll();
  if(((status.platforms || {}).meld || {}).status !== "verbunden") startMeldDashboardPoll();
  if(((status.platforms || {}).obs || {}).status !== "verbunden") startObsDashboardPoll();
}
async function loadDashboardUrls(){
  const box=$("#dashUrls"); if(!box)return;
  const data=await api("/api/overlay-urls");
  const rt=await api("/api/runtime");
  const warn=rt.port_warning ? `<div class="warnBox">${esc(rt.port_warning)}<br><b>Spotify Redirect URI:</b><div class="urlBox">${esc(rt.spotify_redirect_uri)}</div></div>` : "";
  box.innerHTML=warn+(data.main||[]).map(i=>`<div class="urlMini"><b>${esc(i.name)}</b><div class="urlBox">${esc(i.url)}</div></div>`).join("");
}
async function refreshMessages(){
  const m=await api("/api/messages");
  const el=$("#messages"); if(!el)return;
  el.innerHTML=(m.messages||[]).filter(x=>x.message_type==="chat").map(x=>`<div class="msg">${platformBadge(x.platform)} <span class="small">${esc(x.time)}</span> · <b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b><br>${x.html||esc(x.text)}</div>`).join("");
  el.scrollTop=el.scrollHeight;
}
async function refreshNowPlaying(){
  const n=await api("/api/nowplaying");
  if($("#npTitle")) $("#npTitle").textContent=n.title||"Kein Song aktiv";
  if($("#npArtist")) $("#npArtist").textContent=n.artist||"";
  const img=$("#npCover"), disc=$("#dashDisc");
  if(img && disc){
    if(n.cover){ img.src=n.cover; img.style.display="block"; disc.style.display="none"; }
    else { img.removeAttribute("src"); img.style.display="none"; disc.style.display="block"; }
  }
}
function field(name,label,val,type="text"){ return `<label><div>${label}</div><input name="${name}" type="${type}" value="${esc(val||"")}" autocomplete="on" autocapitalize="off" spellcheck="false"></label>`; }
const DEV_LINKS = {
  twitch: "https://dev.twitch.tv/console/apps",
  youtube: "https://console.cloud.google.com/apis/credentials",
  kick: "https://dev.kick.com/",
  spotify: "https://developer.spotify.com/dashboard",
  openai: "https://platform.openai.com/api-keys"
};
function redirectFieldOnly(label,val){
  return `<label><div>${label}</div><input name="redirect_uri" type="text" value="${esc(val||"")}" autocomplete="on" autocapitalize="off" spellcheck="false"></label>`;
}
function devButton(platform){
  const href = DEV_LINKS[platform] || "#";
  return `<a class="btn devBtn" href="${href}" target="_blank" rel="noopener noreferrer" title="Öffne die Developer-Konsole">Dev-Seite</a>`;
}
function redirectField(platform,val){
  const href = DEV_LINKS[platform] || "#";
  return `<label class="redirectWithDev"><div>Redirect URI</div><div class="inlineField"><input name="redirect_uri" type="text" value="${esc(val||"")}" autocomplete="on" autocapitalize="off" spellcheck="false"><a class="btn devBtn" href="${href}" target="_blank" rel="noopener noreferrer">Dev-Seite</a></div></label>`;
}
function normalizeObsFields(form){
  const urlEl=form.querySelector('[name="url"]');
  const hostEl=form.querySelector('[name="host"]');
  const portEl=form.querySelector('[name="port"]');
  let raw=(urlEl?.value||"").trim();
  if(raw){
    try{
      const u=new URL(raw.includes('://') ? raw : 'ws://'+raw);
      if(hostEl && u.hostname) hostEl.value=u.hostname;
      if(portEl && u.port) portEl.value=u.port;
      if(urlEl && hostEl && portEl) urlEl.value=`ws://${hostEl.value || '127.0.0.1'}:${portEl.value || '4455'}`;
    }catch(e){}
  }else if(urlEl && hostEl && portEl){
    urlEl.value=`ws://${hostEl.value || '127.0.0.1'}:${portEl.value || '4455'}`;
  }
}
function sel(name,label,val){return `<label><div>${label}</div><select name="${name}"><option value="false" ${!val?'selected':''}>Nein</option><option value="true" ${val?'selected':''}>Ja</option></select></label>`;}
function platformForm(p,cfg){
  if(p==="tiktok") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("main","Main/Kanal",cfg.main)}${field("bot","Botaccount",cfg.bot)}<div class="hint">TikTok nutzt getrennte gespeicherte Browserprofile für Main und Bot. Es gibt keine Redirect URL. Beim Login öffnet sich die TikTok-Anmeldeseite, dort kannst du dich z.B. per QR-Code anmelden.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="btn tiktokLogin" data-account="main">Main anmelden</button><button type="button" class="btn tiktokLogin" data-account="bot">Bot anmelden</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Main trennen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">Bot trennen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="meld") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("host","Host",cfg.host || "127.0.0.1")}${field("port","Port",cfg.port || "13376")}<div class="hint">Meld Studio braucht keine Anmeldedaten. Wie im Original wird nur per lokalem WebSocket verbunden.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testMeld">Verbindung testen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="obs") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("host","Host",cfg.host || "127.0.0.1")}${field("port","Port",cfg.port || "4455")}${field("password","Passwort",cfg.password,"password")}<div class="hint">OBS WebSocket Standard: <b>ws://127.0.0.1:4455</b>. In OBS muss unter <b>Werkzeuge &gt; WebSocket-Servereinstellungen</b> der WebSocket-Server aktiviert sein.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testObs">Verbindung testen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="spotify") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri || "http://127.0.0.1:5173/callback")}<div class="hint">Spotify braucht keinen Accountnamen. Die Redirect URI ist manuell einstellbar und wird genau so für OAuth benutzt.</div><div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">Spotify anmelden</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Trennen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
  if(p==="openai") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${field("api_key","API-Key",cfg.api_key,"password")}${field("model","Standardmodell",cfg.model || "gpt-5.5")}${field("organization","Organisations-ID (optional)",cfg.organization)}${field("project","Projekt-ID (optional)",cfg.project)}<div class="hint">Der API-Key wird lokal in <b>data/settings.json</b> gespeichert. Ein ChatGPT-Abo enthält nicht automatisch API-Guthaben. Der Verbindungstest ruft nur die Modellliste der offiziellen OpenAI-API ab und erzeugt keine Antwort.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testOpenAI">Verbindung testen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">API-Key entfernen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${field("main","Main/Kanal",cfg.main)}${field("bot","Bot",cfg.bot)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri)}<div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">OAuth Main</a><a class="btn login" data-platform="${p}" data-account="bot" href="#">OAuth Bot</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Main trennen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">Bot trennen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
}
async function renderPlatforms(){
  const {settings,status}=await loadAll(); const p=settings.platforms;
  shell("platforms","Plattformen","Anmeldedaten bleiben im webbased/data Ordner.",["twitch","tiktok","youtube","kick","spotify","openai","meld","obs"].map(k=>`<section class="card platformCard"><h3>${platformLabel(k)}</h3>${platformForm(k,{...(p[k]||{}),...(status.platforms[k]||{})})}</section>`).join(""));
  $$("form[data-platform]").forEach(form=>{
    form.onsubmit=async(e)=>{
      e.preventDefault();
      const pf=form.dataset.platform; const fd=new FormData(form);
      settingsCache = settingsCache || await api("/api/settings");
      settingsCache.platforms[pf] = settingsCache.platforms[pf] || {};
      if(pf === "obs") normalizeObsFields(form);
      const fd2=new FormData(form);
      for(const [k,v] of fd2.entries()) settingsCache.platforms[pf][k] = (k==="enabled"||k==="autoconnect") ? (v==="true") : String(v);
      if(pf === "spotify"){ delete settingsCache.platforms[pf].main; delete settingsCache.platforms[pf].bot; }
      if(pf === "tiktok"){
        settingsCache.platforms[pf].main_account = (settingsCache.platforms[pf].main || "").replace(/^@/, "");
        settingsCache.platforms[pf].bot_account = (settingsCache.platforms[pf].bot || "").replace(/^@/, "");
        settingsCache.platforms[pf].unique_id = settingsCache.platforms[pf].main_account;
        settingsCache.platforms[pf].live_url = settingsCache.platforms[pf].main_account ? `https://www.tiktok.com/@${settingsCache.platforms[pf].main_account}/live` : "";
        settingsCache.platforms[pf].resolved_live_url = settingsCache.platforms[pf].live_url;
      }
      if(pf === "meld"){ delete settingsCache.platforms[pf].password; }
      await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
      alert("Gespeichert");
    };
  });
  $$(".testMeld").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    const fd=new FormData(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.meld = settingsCache.platforms.meld || {};
    for(const [k,v] of fd.entries()) settingsCache.platforms.meld[k] = (k==="enabled"||k==="autoconnect") ? (v==="true") : String(v);
    delete settingsCache.platforms.meld.password;
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/meld");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".testObs").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    normalizeObsFields(form);
    const fd=new FormData(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.obs = settingsCache.platforms.obs || {};
    for(const [k,v] of fd.entries()) settingsCache.platforms.obs[k] = (k==="enabled"||k==="autoconnect") ? (v==="true") : String(v);
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/obs");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".testOpenAI").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    const fd=new FormData(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.openai = settingsCache.platforms.openai || {};
    for(const [k,v] of fd.entries()) settingsCache.platforms.openai[k] = (k==="enabled") ? (v==="true") : String(v);
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/openai");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".tiktokLogin").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    const fd=new FormData(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.tiktok = settingsCache.platforms.tiktok || {};
    for(const [k,v] of fd.entries()) settingsCache.platforms.tiktok[k] = (k==="enabled"||k==="autoconnect") ? (v==="true") : String(v);
    settingsCache.platforms.tiktok.main_account = (settingsCache.platforms.tiktok.main || "").replace(/^@/, "");
    settingsCache.platforms.tiktok.bot_account = (settingsCache.platforms.tiktok.bot || "").replace(/^@/, "");
    settingsCache.platforms.tiktok.unique_id = settingsCache.platforms.tiktok.main_account;
    settingsCache.platforms.tiktok.live_url = settingsCache.platforms.tiktok.main_account ? `https://www.tiktok.com/@${settingsCache.platforms.tiktok.main_account}/live` : "";
    settingsCache.platforms.tiktok.resolved_live_url = settingsCache.platforms.tiktok.live_url;
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api(`/api/tiktok/open/${b.dataset.account || "main"}`);
    const oldText = b.textContent;
    b.textContent = res.ok ? "Loginfenster geöffnet" : "Öffnen fehlgeschlagen";
    setTimeout(()=>{ b.textContent = oldText; }, 3000);
    if(!res.ok) alert(res.error || "TikTok konnte nicht geöffnet werden");
  });
  $$(".login").forEach(a=>a.onclick=async(e)=>{
    e.preventDefault();
    const form=a.closest("form");
    const pf=form.dataset.platform;
    const fd=new FormData(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms[pf] = settingsCache.platforms[pf] || {};
    for(const [k,v] of fd.entries()) settingsCache.platforms[pf][k] = (k==="enabled") ? (v==="true") : String(v);
    if(pf === "spotify"){ delete settingsCache.platforms[pf].main; delete settingsCache.platforms[pf].bot; }
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    window.open(`/oauth/start/${a.dataset.platform}/${a.dataset.account}`,`oauth_${a.dataset.platform}_${a.dataset.account}`,"width=1000,height=800");
  });
  $$(".disconnect").forEach(b=>b.onclick=async()=>{await api(`/api/disconnect/${b.dataset.platform}/${b.dataset.account}`,{method:"POST"}); location.reload();});
}
async function renderChat(){
  const [layout,state]=await Promise.all([api("/api/desktop-chat/layout"),api("/api/desktop-chat/state")]);
  const style=layout.style||{};
  shell("chat","Chat","Gemeinsamer Chat für Dashboard, Browserquelle und Desktopfenster.",`<div class="btnLine"><button class="openDesktopChat">Desktopfenster öffnen</button><button class="secondary editDesktopChat">${state.editing?"Bearbeitung beenden":"Desktopfenster editieren"}</button><a class="btn secondary" href="/chat-browser" target="_blank">Browserfenster öffnen</a></div><section class="card desktopSettings"><h3>Desktopfenster Darstellung</h3><div class="platformForm"><label><div>Hintergrund</div><input name="background" type="color" value="${esc(style.background||"#0d101d")}"></label><label><div>Transparenz</div><input name="opacity" type="range" min="0" max="100" value="${esc(style.opacity??82)}"></label><label><div>Radien</div><input name="radius" type="range" min="0" max="100" value="${esc(style.radius??16)}"></label>${field("fontFamily","Schriftart",style.fontFamily||"Segoe UI")}${field("fontSize","Schriftgröße",style.fontSize||16,"number")}<label><div>Schriftfarbe</div><input name="textColor" type="color" value="${esc(style.textColor||"#ffffff")}"></label></div></section><section class="card chatBox"><div class="messages" id="messages"></div><div class="sendRow"><input id="testmsg" placeholder="Testnachricht ins Overlay schicken"><button id="sendMsg">Senden</button></div></section>`);
  $(".openDesktopChat").onclick=async()=>{const r=await api("/api/desktop-chat/open",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht geöffnet werden");};
  $(".editDesktopChat").onclick=async()=>{const next=!state.editing;await api("/api/desktop-chat/edit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({editing:next})});state.editing=next;$(".editDesktopChat").textContent=next?"Bearbeitung beenden":"Desktopfenster editieren";};
  $$(".desktopSettings input").forEach(input=>input.oninput=async()=>{const next=structuredClone(layout);next.style=next.style||{};next.style[input.name]=input.type==="range"||input.type==="number"?Number(input.value):input.value;await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});Object.assign(layout,next);});
  $("#sendMsg").onclick=async()=>{let v=$("#testmsg").value.trim(); if(!v)return; await api("/api/message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v})}); $("#testmsg").value=""; refreshMessages();};
  refreshMessages();
}
async function renderSpotify(){
  const data=await api("/api/overlay-urls");
  const main=(data.main||[]).find(x=>x.name.includes("Spotis3mptify"));
  shell("spotify","Spotis3mptify","Modularer Pluginbereich für Spotify und das transparente Overlay.",`<section class="card spotifyPreview"><div class="npCoverBox"><div class="disc" id="dashDisc"></div><img id="npCover" alt=""></div><div><div class="label">Aktueller Song</div><h3 id="npTitle">Kein Song aktiv</h3><div class="small" id="npArtist"></div></div></section><section class="card" style="margin-top:18px"><div class="label">Eine Overlay URL für alles</div><div class="urlBox">${esc(main?.url||"")}</div><div class="btnLine"><a class="btn" href="/overlay/spotify" target="_blank">Overlay öffnen / editieren</a><a class="btn secondary" href="/overlays">Alle URLs</a></div></section>`);
  refreshNowPlaying();
}
async function renderOverlays(){
  const data=await api("/api/overlay-urls");
  shell("overlays","Overlay URLs","Wichtig sind Chat Browser und eine komplette Spotis3mptify-Overlay-URL. Einzelquellen bleiben nur für alte Setups erhalten.",`<section class="card">${data.groups.map(g=>`<div class="urlGroup"><h3>${esc(g.title)}</h3>${g.items.map(i=>`<div class="urlItem"><b>${esc(i.name)}</b><div class="urlBox">${esc(i.url)}</div><button class="copy" data-url="${esc(i.url)}">Kopieren</button></div>`).join("")}</div>`).join("")}</section>`);
  $$(".copy").forEach(b=>b.onclick=()=>navigator.clipboard.writeText(b.dataset.url));
}
function pluginStateClass(state){
  const st=String(state||"").toLowerCase();
  if(["connected","running"].includes(st)) return "ok";
  if(["error","failed"].includes(st)) return "bad";
  return "";
}
function schemaLabel(field){return field.label || field.label_de || field.name || field.key || "";}
function schemaTab(field){return field.tab || field.tab_de || field.ui_tab || field.ui_tab_de || "Allgemein";}
function renderPluginField(field, values){
  const key=String(field.key||field.name||"");
  const type=String(field.type||field.kind||"text").toLowerCase();
  const label=esc(schemaLabel(field));
  const help=field.help||field.help_de||"";
  const value=values?.[key];
  if(!key && (type==="separator" || type==="section")) return `<div class="settingsSeparator">${label}</div>`;
  if(type==="separator" || type==="section") return `<div class="settingsSeparator">${label}</div>`;
  if(!key) return "";
  const readonly=field.readonly||field.disabled;
  const ro=readonly?"readonly disabled":"";
  const helpHtml=help?`<div class="hint">${esc(help)}</div>`:"";
  if(type==="bool" || type==="boolean" || type==="checkbox"){
    const checked=(value===true||String(value).toLowerCase()==="true"||String(value)==="1")?"checked":"";
    return `<label class="settingsBool"><input name="${esc(key)}" type="checkbox" ${checked} ${readonly?"disabled":""}><span>${label}</span></label>${helpHtml}`;
  }
  const opts=field.options||field.choices||field.values;
  if((type==="select" || Array.isArray(opts)) && Array.isArray(opts)){
    const options=opts.map(o=>{
      const v=typeof o==="object"?(o.value??o.id??o.key??o.label):o;
      const l=typeof o==="object"?(o.label??o.name??v):o;
      return `<option value="${esc(v)}" ${String(value??"")===String(v)?"selected":""}>${esc(l)}</option>`;
    }).join("");
    return `<label><div>${label}</div><select name="${esc(key)}" ${readonly?"disabled":""}>${options}</select></label>${helpHtml}`;
  }
  const inputType=(type==="number"||type==="int"||type==="float")?"number":(type==="password"?"password":"text");
  return `<label><div>${label}</div><input name="${esc(key)}" type="${inputType}" value="${esc(value??field.default??"")}" ${ro} placeholder="${esc(field.placeholder||"")}"></label>${helpHtml}`;
}
function collectPluginSettings(form, schema){
  const values={};
  for(const field of (schema||[])){
    const key=String(field.key||field.name||"");
    if(!key || field.readonly || field.disabled || String(field.type||"").toLowerCase()==="separator") continue;
    const el=form.elements[key];
    if(!el) continue;
    const type=String(field.type||"").toLowerCase();
    if(type==="bool"||type==="boolean"||type==="checkbox") values[key]=!!el.checked;
    else if(type==="number"||type==="int") values[key]=parseInt(el.value||"0",10)||0;
    else if(type==="float") values[key]=parseFloat(el.value||"0")||0;
    else values[key]=String(el.value??"");
  }
  return values;
}
async function openPluginSettings(pluginId){
  const mount=$("#pluginSettingsMount");
  if(!mount) return;
  mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Settings laden...</h3></section>`;
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Settings</h3><div class="warnBox">${esc(d.error||"Konnte Settings nicht laden")}</div></section>`;return;}
  const schema=d.schema||[];
  const values=d.values||{};
  const tabs=[...new Set(schema.map(schemaTab))];
  const groups=tabs.length?tabs:["Allgemein"];
  const body=groups.map(tab=>`<div class="pluginSettingsGroup"><h4>${esc(tab)}</h4><div class="pluginSettingsFields">${schema.filter(f=>schemaTab(f)===tab || (!tabs.length&&true)).map(f=>renderPluginField(f,values)).join("")}</div></div>`).join("");
  mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>${esc(d.plugin_id)} Settings</h3><div class="small">Wird in data/settings.json unter plugins/${esc(d.plugin_id)} gespeichert und danach neu gestartet.</div></div><button type="button" class="secondary" id="pluginSettingsClose">Schließen</button></div><form id="pluginSettingsForm">${body||"<div class='small'>Dieses Plugin hat kein Settings-Schema.</div>"}<div class="btnLine"><button type="submit">Speichern & neu starten</button><button type="button" class="secondary" id="pluginSettingsCancel">Abbrechen</button><span class="small" id="pluginSettingsResult"></span></div></form></section>`;
  $("#pluginSettingsClose").onclick=()=>mount.innerHTML="";
  $("#pluginSettingsCancel").onclick=()=>mount.innerHTML="";
  $("#pluginSettingsForm").onsubmit=async(ev)=>{
    ev.preventDefault();
    const result=$("#pluginSettingsResult");
    result.textContent="Speichere...";
    const values=collectPluginSettings(ev.currentTarget,schema);
    const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values})});
    result.textContent=out.ok?"Gespeichert und neu gestartet.":`Fehler: ${out.error||"unbekannt"}`;
    if(out.ok) setTimeout(renderPlugins,700);
  };
  mount.scrollIntoView({behavior:"smooth",block:"start"});
}
async function renderPlugins(){
  const s=await api("/api/status");
  const cards=(s.plugins||[]).map(p=>`<section class="card pluginCard"><div class="pluginHead"><h3>${esc(p.name)}</h3><span class="pluginState ${pluginStateClass(p.state)}">${esc(p.state||"ready")}</span></div><div class="small">${esc(p.description||"")}</div><div class="small pluginStatusText">${esc(p.status||p.message||"Bereit")}</div><div class="btnLine"><button type="button" class="pluginSettingsBtn" data-plugin="${esc(p.id)}">Settings</button><a class="btn secondary" href="/dev" title="Logs im DEV-Bereich prüfen">Logs</a></div></section>`).join("");
  shell("plugins","Plugins","Hier stellst du jedes gefundene Plugin direkt ein. Der alte nutzlose Bereit-Button ist weg.",`<div id="pluginSettingsMount"></div><div class="pluginGrid">${cards}</div>`);
  $$(".pluginSettingsBtn").forEach(b=>b.onclick=()=>openPluginSettings(b.dataset.plugin));
}
function formatBytes(value){
  let n=Number(value||0); const units=["B","KB","MB","GB"];
  let i=0; while(n>=1024&&i<units.length-1){n/=1024;i++;}
  return `${n.toFixed(i?1:0)} ${units[i]}`;
}
function formatUptime(seconds){
  const s=Math.max(0,Number(seconds||0)); const h=Math.floor(s/3600); const m=Math.floor((s%3600)/60);
  return `${h}h ${m}m ${Math.floor(s%60)}s`;
}
async function renderDev(){
  shell("dev","DEV","Lokale Entwicklungsdiagnose. Geheimnisse werden in der Logansicht automatisch ausgeblendet.",`
    <div class="devGrid">
      <section class="card"><h3>Runtime</h3><div id="devRuntime" class="devFacts"></div></section>
      <section class="card"><h3>Zustand</h3><div id="devCounts" class="devFacts"></div></section>
      <section class="card"><h3>Plattformen</h3><div id="devPlatforms" class="devFacts"></div></section>
      <section class="card"><h3>Entwicklerlinks</h3><div class="devLinks">
        <a class="btn secondary" target="_blank" href="/debug">Raw Debug</a>
        <a class="btn secondary" target="_blank" href="/api/status">Status JSON</a>
        <a class="btn secondary" target="_blank" href="/api/dev/settings">Settings JSON (bereinigt)</a>
        <a class="btn secondary" target="_blank" href="/api/runtime">Runtime JSON</a>
        <a class="btn secondary" target="_blank" href="/api/overlay-urls">Overlay JSON</a>
      </div></section>
    </div>
    <section class="card devLogCard">
      <div class="devLogHead"><div><h3>Live-Log</h3><div id="devLogMeta" class="small"></div></div><label class="devAuto"><input id="devAutoRefresh" type="checkbox" checked> automatisch aktualisieren</label></div>
      <div id="devLogFilters" class="devLogFilters"></div>
      <div id="devPluginFilters" class="devLogFilters devPluginFilters"></div>
      <textarea id="devLog" class="devLog" readonly spellcheck="false"></textarea>
      <div class="btnLine">
        <button id="devRefresh" type="button">Neu laden</button>
        <button id="devCopy" type="button" class="secondary">Log kopieren</button>
        <button id="devClear" type="button" class="secondary">Log löschen</button>
        <button class="secondary devEvent" data-level="info" type="button">Info-Test</button>
        <button class="secondary devEvent" data-level="warning" type="button">Warnungs-Test</button>
        <button class="secondary devEvent" data-level="error" type="button">Fehler-Test</button>
      </div>
    </section>`);
  let devLogFilter={scope:"all",id:"",label:"Alle"};
  const setLogFilter=(scope,id,label)=>{
    devLogFilter={scope,id:id||"",label};
    $$(".devFilter").forEach(b=>b.classList.toggle("active",b.dataset.scope===scope&&(b.dataset.id||"")===(id||"")));
    $("#devPluginFilters").classList.toggle("visible",scope==="plugins"||scope==="plugin");
    refreshLog();
  };
  let lastFilterSignature="";
  const renderLogFilters=(d)=>{
    const platforms=d.log_filters?.platforms||[];
    const plugins=d.log_filters?.plugins||[];
    const sig=JSON.stringify({platforms,plugins});
    if(sig===lastFilterSignature) return;
    lastFilterSignature=sig;
    const current={...devLogFilter};
    $("#devLogFilters").innerHTML=[
      `<button type="button" class="secondary devFilter" data-scope="all">Alle</button>`,
      `<button type="button" class="secondary devFilter" data-scope="core">Main / Core</button>`,
      ...platforms.map(p=>`<button type="button" class="secondary devFilter" data-scope="platform" data-id="${esc(p)}">${esc(platformLabel(p))}</button>`),
      `<button type="button" class="secondary devFilter" data-scope="plugins">Plugins</button>`
    ].join("");
    $("#devPluginFilters").innerHTML=plugins.map(p=>`<button type="button" class="secondary devFilter" data-scope="plugin" data-id="${esc(p.id)}">${esc(p.name)}</button>`).join("");
    $$(".devFilter").forEach(b=>{
      b.onclick=()=>setLogFilter(b.dataset.scope,b.dataset.id||"",b.textContent.trim());
      b.classList.toggle("active",b.dataset.scope===current.scope&&(b.dataset.id||"")===(current.id||""));
    });
    $("#devPluginFilters").classList.toggle("visible",current.scope==="plugins"||current.scope==="plugin");
  };
  let devLogRequest=0;
  const refreshInfo=async()=>{
    const d=await api("/api/dev/info");
    let liveStatus={platforms:d.platforms||{}};
    try{
      const s=await api("/api/status");
      if(s && s.platforms) liveStatus=s;
    }catch(e){}
    if(d && d.error){
      $("#devRuntime").innerHTML=`<div><b>Fehler</b><span>${esc(d.error)}</span></div>`;
      return;
    }
    renderLogFilters(d);
    $("#devRuntime").innerHTML=[
      ["Version",d.version],["Uptime",formatUptime(d.uptime)],["Port",d.port],["PID",d.pid],
      ["Python",d.python],["Modus",d.frozen?"EXE":"Source"],["Arbeitsordner",d.cwd],["Executable",d.executable],
      ["Daten",d.paths?.data],["Log",d.paths?.log]
    ].map(x=>`<div><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join("");
    $("#devCounts").innerHTML=[
      ["Nachrichten",d.counts?.messages],["Plugins",d.counts?.plugins],["Aktive Plugins",d.counts?.active_plugins],
      ["Auth-Dateien",d.counts?.auth_files],["Freier Speicher",formatBytes(d.disk_free)]
    ].map(x=>`<div><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join("");
    $("#devPlatforms").innerHTML=Object.entries(liveStatus.platforms||{}).map(([name,cfg])=>`<div><b>${esc(platformLabel(name))}</b><span class="${cfg.status==="verbunden"?"devOk":""}">${cfg.enabled?"aktiv":"inaktiv"} · ${esc(cfg.status)}${cfg.detail?" · "+esc(cfg.detail):""}</span></div>`).join("");
  };
  const refreshLog=async(keepPosition=false)=>{
    const box=$("#devLog"); if(!box)return;
    const atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<30;
    const requested={...devLogFilter};
    const requestId=++devLogRequest;
    const query=`?scope=${encodeURIComponent(requested.scope)}&id=${encodeURIComponent(requested.id)}`;
    const d=await api("/api/dev/log"+query);
    if(requestId!==devLogRequest||requested.scope!==devLogFilter.scope||requested.id!==devLogFilter.id)return;
    if(d && d.error){ box.value=`Log laden fehlgeschlagen: ${d.error}`; return; }
    box.value=d.log||"";
    $("#devLogMeta").textContent=`${requested.label} · Serverfilter: ${d.scope||"all"}${d.id?" / "+d.id:""} · ${d.lines||0} Zeilen · ${formatBytes(d.bytes)} gesamt · bereinigte Anzeige · ${new Date().toLocaleTimeString()}`;
    if(!keepPosition||atBottom) box.scrollTop=box.scrollHeight;
  };
  $("#devRefresh").onclick=()=>{refreshInfo();refreshLog();};
  $("#devCopy").onclick=async()=>{await navigator.clipboard.writeText($("#devLog").value);$("#devCopy").textContent="Kopiert";setTimeout(()=>$("#devCopy").textContent="Log kopieren",1500);};
  $("#devClear").onclick=async()=>{if(!confirm("Logdatei wirklich leeren?"))return;await api("/api/dev/log/clear",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});await refreshLog();};
  $$(".devEvent").forEach(b=>b.onclick=async()=>{await api("/api/dev/log/event",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({level:b.dataset.level,message:`Manueller ${b.dataset.level}-Test aus der DEV-Seite`})});await refreshLog();});
  await refreshInfo(); await refreshLog();
  setInterval(()=>{if($("#devAutoRefresh")?.checked){refreshInfo();refreshLog(true);}},2000);
}
({dashboard:renderDashboard,platforms:renderPlatforms,chat:renderChat,spotify:renderSpotify,overlays:renderOverlays,plugins:renderPlugins,dev:renderDev}[page]||renderDashboard)();
setInterval(()=>{ if(page==="dashboard"||page==="chat") refreshMessages(); if(page==="dashboard"||page==="spotify") refreshNowPlaying();},2500);


// Main-UI heartbeat: wenn das Webbased-Browserfenster per X geschlossen wird,
// beendet sich auch der lokale Server/EXE kurz danach. Overlays zählen bewusst
// nicht als Main-UI, damit alte Versionen nicht weiter im Hintergrund hängen.
function webbasedUiHeartbeat(){
  fetch('/api/ui-heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'}).catch(()=>{});
}
webbasedUiHeartbeat();
setInterval(webbasedUiHeartbeat, 2500);
