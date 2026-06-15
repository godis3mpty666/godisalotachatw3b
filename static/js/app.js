
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const page = $("#app")?.dataset.page || "dashboard";
let settingsCache = null;
let statusCache = null;

function nav(active){
  const items = [
    ["dashboard","Dashboard","/"],["platforms","Plattformen","/plattformen"],["chat","Chat","/chat"],
    ["spotify","Spotis3mptify","/spotis3mptify"],["overlays","Overlay URLs","/overlays"],["plugins","Plugins","/plugins"]
  ];
  return `<aside class="sidebar"><div class="brand"><div class="logo"></div><div><h1>godisalotachat</h1><div class="ver">Ver. ${window.WEB_VERSION}</div></div><div class="webbased">webbased</div></div><nav class="nav">${items.map(i=>`<a class="${active===i[0]?'active':''}" href="${i[2]}">${i[1]}</a>`).join("")}</nav></aside>`;
}
function shell(active, title, sub, body){
  $("#app").innerHTML = `<div class="layout">${nav(active)}<main class="content"><div class="top"><div><h2>${title}</h2><div class="sub">${sub||""}</div></div></div>${body}</main></div>`;
}
async function api(url, opts){ const r=await fetch(url,{cache:"no-store",...(opts||{})}); return r.json(); }
async function loadAll(){ settingsCache=await api("/api/settings"); statusCache=await api("/api/status"); return {settings:settingsCache,status:statusCache};}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}
function platformLabel(p){return ({twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick",spotify:"Spotify",meld:"Meld",obs:"OBS"}[p]||p);}
function card(p,cfg){
  const st = cfg.status || "nicht verbunden";
  const ok = st==="verbunden";
  let details = "";
  if(p==="tiktok") details = cfg.detail ? esc(cfg.detail) : `Main: ${esc(cfg.main||"-")}<br>Bot: ${esc(cfg.bot||"-")}`;
  else if(p==="twitch"||p==="youtube"||p==="kick") details = `Main: ${esc(cfg.main||"-")}<br>Bot: ${esc(cfg.bot||"-")}`;
  else if(p==="spotify") details = ``;
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
  if(txt) txt.textContent = ok ? "Verbunden" : "Bereit";
  if(details && (p === "meld" || p === "obs" || p === "tiktok")) details.textContent = cfg.detail || "";
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
    <div class="grid cards">${["twitch","tiktok","youtube","kick","spotify","meld","obs"].map(k=>card(k,p[k]||{})).join("")}</div>
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
  el.innerHTML=(m.messages||[]).map(x=>`<div class="msg"><span class="small">${esc(x.platform)} · ${esc(x.time)}</span> · <b>${esc(x.user)}</b><br>${esc(x.text)}</div>`).join("");
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
  spotify: "https://developer.spotify.com/dashboard"
};
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
  if(p==="obs") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("host","Host",cfg.host || "127.0.0.1")}${field("port","Port",cfg.port || "4455")}${field("password","Passwort",cfg.password,"password")}<div class="hint">OBS WebSocket Standard: <b>ws://127.0.0.1:4455</b>. Normalerweise musst du nur das Passwort eintragen.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testObs">Verbindung testen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="spotify") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectField(p,cfg.redirect_uri || "http://127.0.0.1:5173/callback")}<div class="hint">Spotify braucht keinen Accountnamen. Die Redirect URI ist manuell einstellbar und wird genau so für OAuth benutzt.</div><div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">Spotify anmelden</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Trennen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
  return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${field("main","Main/Kanal",cfg.main)}${field("bot","Bot",cfg.bot)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectField(p,cfg.redirect_uri)}<div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">OAuth Main</a><a class="btn login" data-platform="${p}" data-account="bot" href="#">OAuth Bot</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Main trennen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">Bot trennen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
}
async function renderPlatforms(){
  const {settings,status}=await loadAll(); const p=settings.platforms;
  shell("platforms","Plattformen","Anmeldedaten bleiben im webbased/data Ordner.",["twitch","tiktok","youtube","kick","spotify","meld","obs"].map(k=>`<section class="card platformCard"><h3>${platformLabel(k)}</h3>${platformForm(k,{...(p[k]||{}),...(status.platforms[k]||{})})}</section>`).join(""));
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
  shell("chat","Chat","Testbereich für Chat und transparentes Chat-Browseroverlay.",`<section class="card chatBox"><div class="messages" id="messages"></div><div class="sendRow"><input id="testmsg" placeholder="Testnachricht ins Overlay schicken"><button id="sendMsg">Senden</button></div></section>`);
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
async function renderPlugins(){
  const s=await api("/api/status");
  shell("plugins","Plugins","Ordnerstruktur wie beim regulären Tool: plugins/ und data/plugins/ sind vorhanden.",`<div class="pluginGrid">${s.plugins.map(p=>`<section class="card"><h3>${esc(p.name)}</h3><div class="small">${esc(p.description||"")}</div><div class="btnLine"><button class="secondary">Bereit</button></div></section>`).join("")}</div>`);
}
({dashboard:renderDashboard,platforms:renderPlatforms,chat:renderChat,spotify:renderSpotify,overlays:renderOverlays,plugins:renderPlugins}[page]||renderDashboard)();
setInterval(()=>{ if(page==="dashboard"||page==="chat") refreshMessages(); if(page==="dashboard"||page==="spotify") refreshNowPlaying();},2500);


// Main-UI heartbeat: wenn das Webbased-Browserfenster per X geschlossen wird,
// beendet sich auch der lokale Server/EXE kurz danach. Overlays zählen bewusst
// nicht als Main-UI, damit alte Versionen nicht weiter im Hintergrund hängen.
function webbasedUiHeartbeat(){
  fetch('/api/ui-heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'}).catch(()=>{});
}
webbasedUiHeartbeat();
setInterval(webbasedUiHeartbeat, 2500);
