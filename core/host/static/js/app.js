
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const page = $("#app")?.dataset.page || "dashboard";
let settingsCache = null;
let statusCache = null;
let internalNavigation = false;
let shutdownInProgress = false;

function nav(active){
  const items = [
    ["dashboard","Dashboard","/"],["platforms","Plattformen","/plattformen"],["chat","Chat","/chat"],["obs_meld","OBS/Meld Integration","/obs-meld-integration"],
    ["spotify","Spotis3mptify","/spotis3mptify"],["easyslider","3asyslid3r","/3asyslid3r"],["overlays","Overlay URLs","/overlays"],["plugins","Plugins","/plugins"],["dev","DEV","/dev"]
  ];
  const issueUrl = "https://github.com/godis3mpty666/godisalotachatw3b/issues/new?title=" + encodeURIComponent("[Feedback] ") + "&body=" + encodeURIComponent("**Was ist passiert oder was soll verbessert werden?**\n\n\n**So kann man es nachstellen (bei einem Bug):**\n1. \n2. \n\n**Version:** " + (window.WEB_VERSION || "unbekannt") + "\n\n**Zusätzliche Infos / Screenshots:**\n");
  const credits = [
    ["Twitch","https://twitch.tv/godis3mpty","twitch"],
    ["Discord","https://discord.gg/vtBuyrNtE","discord"],
    ["Ko-fi","https://ko-fi.com/godis3mpty","ko-fi"]
  ];
  return `<aside class="sidebar"><div class="brand"><div class="logo"></div><div><h1>godisalotachat</h1><div class="ver">Ver. ${window.WEB_VERSION}</div></div><div class="webbased">webbased</div></div><nav class="nav">${items.map(i=>`<a class="${active===i[0]?'active':''}" href="${i[2]}">${i[1]}</a>`).join("")}</nav><section class="credits" aria-label="Credits und Community"><div class="creditsLabel">Credits & Community</div><div class="creditsLinks">${credits.map(i=>`<a href="${i[1]}" target="_blank" rel="noopener noreferrer"><img src="/platform-icon/${i[2]}" alt=""><span>${i[0]}</span><span class="externalArrow" aria-hidden="true">↗</span></a>`).join("")}</div><a class="feedbackLink" href="${issueUrl}" target="_blank" rel="noopener noreferrer"><span class="feedbackIcon" aria-hidden="true">!</span><span><b>Feedback senden</b><small>Bug oder Idee auf GitHub</small></span><span class="externalArrow" aria-hidden="true">↗</span></a></section></aside>`;
}
function shell(active, title, sub, body){
  $("#app").innerHTML = `<div class="layout">${nav(active)}<main class="content"><div class="top"><div><h2>${title}</h2><div class="sub">${sub||""}</div></div><button type="button" id="shutdownApp" class="shutdownBtn" title="EXE schließen">Beenden</button></div>${body}</main></div>`;
  wireShutdownButton();
}
async function shutdownApp(){
  const btn = $("#shutdownApp");
  if(btn && btn.disabled) return;
  if(btn){ btn.disabled = true; btn.textContent = "Schließt…"; }
  shutdownInProgress = true;
  try{
    await api("/api/shutdown",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}",timeoutMs:2500});
  }catch(_){ }
  document.body.innerHTML = `<div class="shutdownScreen"><div><h1>godisalotachat wird geschlossen</h1><p>Dieses Fenster schließt sich gleich automatisch.</p></div></div>`;
  setTimeout(()=>{ try{ window.open("","_self"); window.close(); }catch(_){} },3000);
  setTimeout(()=>{
    document.body.innerHTML = `<div class="shutdownScreen"><div><h1>godisalotachat ist geschlossen</h1><p>Falls der Tab offen bleibt, kannst du ihn schließen.</p></div></div>`;
  },3600);
}
function wireShutdownButton(){
  const btn = $("#shutdownApp");
  if(btn) btn.onclick = shutdownApp;
}
document.addEventListener("click", ev=>{
  const a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
  if(!a) return;
  try{
    const u = new URL(a.getAttribute("href"), location.href);
    if(u.origin === location.origin && !a.target) internalNavigation = true;
  }catch(_){}
}, true);
window.addEventListener("pagehide", ()=>{
  if(shutdownInProgress || internalNavigation) return;
  // Closing or suspending the UI must never stop the backend, plugins, or overlays.
});
async function api(url, opts){
  const r=await fetch(url,{cache:"no-store",...(opts||{})});
  let data=null;
  try{ data=await r.json(); }catch(e){ data={ok:false,error:String(e||"Ungültige JSON-Antwort")}; }
  if(!r.ok){ data.ok=false; data.http_status=r.status; data.error=data.error||`HTTP ${r.status}`; }
  return data;
}
api = async function(url, opts){
  opts = opts || {};
  const timeoutMs = Number(opts.timeoutMs || 8000);
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeoutMs);
  try{
    const r=await fetch(url,{cache:"no-store",...opts,signal:controller.signal});
    let data=null;
    try{ data=await r.json(); }catch(e){ data={ok:false,error:String(e||"Ungueltige JSON-Antwort")}; }
    if(!r.ok){ data.ok=false; data.http_status=r.status; data.error=data.error||`HTTP ${r.status}`; }
    return data;
  }catch(e){
    const aborted = e && e.name === "AbortError";
    return {ok:false,error:aborted ? `Timeout nach ${Math.round(timeoutMs/1000)}s: ${url}` : String(e||"Netzwerkfehler")};
  }finally{
    clearTimeout(timer);
  }
};
async function openExternal(url){
  const res = await api(`/api/open-external?url=${encodeURIComponent(url)}`, {timeoutMs:2500});
  if(!res.ok) window.open(url, "_blank", "noopener,noreferrer");
  return res;
}
async function loadAll(){ settingsCache=await api("/api/settings"); statusCache=await api("/api/status"); return {settings:settingsCache,status:statusCache};}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}
function userColor(platform,user){let h=2166136261;for(const c of `${platform}:${user}`){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `hsl(${Math.abs(h)%360} 78% 68%)`;}
function platformMark(p){return ({twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"}[p]||p);}
function platformBadge(p){return `<span class="chatPlatform"><img src="/platform-icon/${esc(p)}" alt="${esc(platformMark(p))}"></span>`;}
function platformLabel(p){return ({twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick",spotify:"Spotify",openai:"ChatGPT / OpenAI",meld:"Meld",obs:"OBS"}[p]||p);}
function defaultEasysliderSettings(){return {enabled:true,edge:"left",delaySeconds:2,opacity:82,buttons:[
  {id:"dashboard",label:"Dashboard",path:"/",enabled:true},
  {id:"platforms",label:"Plattformen",path:"/plattformen",enabled:true},
  {id:"chat",label:"Chat",path:"/chat",enabled:true},
  {id:"obs_meld",label:"OBS/Meld Integration",path:"/obs-meld-integration",enabled:false},
  {id:"spotify",label:"Spotis3mptify",path:"/spotis3mptify",enabled:false},
  {id:"modalot",label:"Modalot",path:"/plugins?plugin=modalot",enabled:true},
  {id:"plugins",label:"Plugins",path:"/plugins",enabled:true},
  {id:"dev",label:"DEV",path:"/dev",enabled:true}
]};}
function normalizeEasysliderClient(cfg){
  const d=defaultEasysliderSettings();
  cfg=cfg&&typeof cfg==="object"?cfg:{};
  const edge=["left","right","top","bottom"].includes(cfg.edge)?cfg.edge:d.edge;
  const delay=Math.max(0,Math.min(120,Number(cfg.delaySeconds??d.delaySeconds)||0));
  const opacity=Math.max(0,Math.min(100,Number(cfg.opacity??d.opacity)||0));
  const buttons=Array.isArray(cfg.buttons)&&cfg.buttons.length?cfg.buttons:d.buttons;
  return {enabled:cfg.enabled!==false,edge,delaySeconds:delay,opacity,buttons:buttons.map(b=>({id:String(b.id||"").trim()||"dashboard",label:String(b.label||b.id||"Dashboard").trim(),path:String(b.path||"/").trim()||"/",enabled:b.enabled!==false}))};
}
async function mountEasysliderRail(){
  const old=$("#easysliderRail");
  if(old) old.remove();
  const settings=normalizeEasysliderClient((settingsCache&&settingsCache.ui&&settingsCache.ui["3asyslid3r"])||((await api("/api/settings")).ui||{})["3asyslid3r"]);
  const activeButtons=(settings.buttons||[]).filter(b=>b.enabled!==false);
  if(!settings.enabled || page==="easyslider" || !activeButtons.length) return;
  const rail=document.createElement("div");
  rail.id="easysliderRail";
  rail.className=`easysliderRail edge-${settings.edge}`;
  rail.style.setProperty("--easyslider-opacity",String(settings.opacity/100));
  rail.innerHTML=`<div class="easysliderInner">${activeButtons.map(b=>`<button type="button" class="easysliderButton" data-path="${esc(b.path)}" title="${esc(b.label)}"><img src="/slider-asset/${encodeURIComponent(b.id)}.png?v=${encodeURIComponent(window.WEB_VERSION||"")}" alt="" onerror="this.remove()"><span>${esc(b.label)}</span></button>`).join("")}</div>`;
  document.body.appendChild(rail);
  let opened=false;
  const open=()=>{if(opened)return;opened=true;rail.classList.add("open");};
  const delayMs=Math.round(settings.delaySeconds*1000);
  const timer=setTimeout(open,delayMs);
  rail.addEventListener("mouseenter",open);
  rail.addEventListener("focusin",open);
  rail.addEventListener("click",async ev=>{
    const btn=ev.target.closest(".easysliderButton");
    if(!btn)return;
    clearTimeout(timer);
    rail.classList.remove("open");
    const target=btn.dataset.path||"/";
    await api("/api/3asyslid3r/activate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:target}),timeoutMs:2500});
    const here=location.pathname+location.search;
    if(here!==target) location.href=target;
  });
}
function statusLabel(cfg){
  const raw = String(cfg.status || (cfg.enabled ? "bereit" : "inaktiv")).toLowerCase();
  if(raw === "verbunden") return "Verbunden";
  if(raw === "inaktiv") return "Inaktiv";
  if(raw === "bereit") return "Bereit";
  return "Nicht verbunden";
}
function platformAccountDetails(cfg){
  const platformConnected = cfg.status === "verbunden";
  const mainConnected = platformConnected && (cfg.main_status === "verbunden" || (!cfg.main_status && !cfg.bot_status));
  const botConnected = platformConnected && cfg.bot_status === "verbunden";
  const mainName = cfg.main || cfg.main_account || cfg.channel || cfg.unique_id || cfg.main_username || cfg.main_channel_title || "";
  const botName = cfg.bot || cfg.bot_account || cfg.bot_username || cfg.username || cfg.bot_channel_title || "";
  const rows = [];
  if(mainName) rows.push(`Main: ${esc(mainName)}${mainConnected ? "" : " · nicht verbunden"}`);
  if(botName) rows.push(`Bot: ${esc(botName)}${botConnected ? "" : " · nicht verbunden"}`);
  return rows.length ? rows.join("<br>") : "Keine Accounts eingetragen";
}
function card(p,cfg){
  const st = cfg.status || "nicht verbunden";
  const ok = st==="verbunden";
  const label = statusLabel(cfg);
  let details = "";
  if(p==="tiktok"||p==="twitch"||p==="youtube"||p==="kick") details = platformAccountDetails(cfg);
  else if(p==="spotify") details = ``;
  else if(p==="openai") details = cfg.detail ? esc(cfg.detail) : (cfg.status==="verbunden" ? "API-Key gespeichert" : "OpenAI API-Key fehlt");
  else if(p==="meld") details = cfg.detail ? esc(cfg.detail) : ``;
  else if(p==="obs") details = cfg.detail ? esc(cfg.detail) : ``;
  else details = `Host: ${esc(cfg.host||"-")}:${esc(cfg.port||"-")}`;
  return `<div class="card" data-platform-card="${esc(p)}"><div class="label">${platformLabel(p)}</div><div class="status"><span class="dot ${ok?'ok':''}"></span><span class="statusText">${label}</span></div><div class="small cardDetails">${details}</div></div>`;
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
  if(txt) txt.textContent = statusLabel(cfg);
  if(details && (p === "tiktok" || p === "twitch" || p === "youtube" || p === "kick")) details.innerHTML = platformAccountDetails(cfg);
  else if(details && (p === "meld" || p === "obs" || p === "openai")) details.textContent = cfg.detail || "";
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
  const showModeration=page==="dashboard"||page==="chat";
  const moderation=(x)=>!showModeration||!["twitch","kick","youtube"].includes(x.platform)||x.source_plugin_id==="modalot"?"":`<span class="dashboardModActions"><button type="button" class="dashboardModAction ban" data-action="ban" data-platform="${esc(x.platform)}" data-user="${esc(x.user)}" data-author-channel-id="${esc(x.author_channel_id||"")}" data-live-chat-id="${esc(x.live_chat_id||"")}" title="${esc(x.user)} auf ${esc(x.platform)} bannen" aria-label="${esc(x.user)} bannen"><img src="/platform-icon/banhammer" alt=""></button><button type="button" class="dashboardModAction unban" data-action="unban" data-platform="${esc(x.platform)}" data-user="${esc(x.user)}" data-author-channel-id="${esc(x.author_channel_id||"")}" data-live-chat-id="${esc(x.live_chat_id||"")}" title="${esc(x.user)} auf ${esc(x.platform)} freigeben" aria-label="${esc(x.user)} freigeben"><img src="/platform-icon/unban" alt=""></button></span>`;
  el.innerHTML=(m.messages||[]).filter(x=>x.message_type==="chat"||x.message_type==="moderation_notice").map(x=>showModeration?`<div class="msg dashboardChatMsg">${platformBadge(x.platform)}${moderation(x)} <b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: <span class="dashboardChatText">${x.html||esc(x.text)}</span></div>`:`<div class="msg">${platformBadge(x.platform)} <span class="small">${esc(x.time)}</span> · <b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: ${x.html||esc(x.text)}</div>`).join("");
  el.onclick=async ev=>{const button=ev.target.closest?.(".dashboardModAction");if(!button||button.disabled)return;const action=button.dataset.action,platform=button.dataset.platform,user=button.dataset.user;button.disabled=true;const out=await api("/api/dashboard/moderation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,platform,user,author_channel_id:button.dataset.authorChannelId||"",live_chat_id:button.dataset.liveChatId||""})});button.disabled=false;if(!out.ok)alert(out.error||out.detail||"Moderationsaktion fehlgeschlagen");};
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
function applyFormValues(target, form, options={}){
  target = target || {};
  const preserveEmptyPassword = options.preserveEmptyPassword !== false;
  const boolKeys = new Set(options.boolKeys || ["enabled","autoconnect"]);
  for(const [k,v] of new FormData(form).entries()){
    const el = form.elements[k];
    if(preserveEmptyPassword && el && el.type === "password" && !String(v||"").trim() && target[k]){
      continue;
    }
    target[k] = boolKeys.has(k) ? (v==="true") : String(v);
  }
  return target;
}
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
  return `<button type="button" class="btn devBtn" data-url="${esc(href)}" title="Oeffne die Developer-Konsole">Dev-Seite</button>`;
}
function redirectField(platform,val){
  const href = DEV_LINKS[platform] || "#";
  return `<label class="redirectWithDev"><div>Redirect URI</div><div class="inlineField"><input name="redirect_uri" type="text" value="${esc(val||"")}" autocomplete="on" autocapitalize="off" spellcheck="false"><button type="button" class="btn devBtn" data-url="${esc(href)}">Dev-Seite</button></div></label>`;
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
  if(p==="tiktok") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("main","Main/Kanal",cfg.main)}${field("bot","Botaccount",cfg.bot)}<div class="platformSubBox"><b>Testkanal / Fremd-Live lesen</b>${sel("test_channel_enabled","Testkanal aktiv",cfg.test_channel_enabled ?? false)}${field("test_channel","Testkanal ohne @",cfg.test_channel || "")}<div class="hint">Wenn aktiv, liest das TikTok-Chatplugin Chat, Joins, Likes, Gifts, Follows und Shares aus diesem Kanal. So kannst du Alerts testen, ohne mit deinem eigenen Account live zu gehen. Der angegebene Kanal muss selbst gerade live sein.</div></div><div class="hint">TikTok nutzt getrennte gespeicherte Browserprofile für Main und Bot. Es gibt keine Redirect URL. Beim Login öffnet sich die TikTok-Anmeldeseite, dort kannst du dich z.B. per QR-Code anmelden.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="btn tiktokLogin" data-account="main">Main anmelden</button><button type="button" class="btn tiktokLogin" data-account="bot">Bot anmelden</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Main trennen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">Bot trennen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="meld") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("host","Host",cfg.host || "127.0.0.1")}${field("port","Port",cfg.port || "13376")}<div class="hint">Meld Studio braucht keine Anmeldedaten. Wie im Original wird nur per lokalem WebSocket verbunden.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testMeld">Verbindung testen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="obs") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("host","Host",cfg.host || "127.0.0.1")}${field("port","Port",cfg.port || "4455")}${field("password","Passwort",cfg.password,"password")}<div class="hint">OBS WebSocket Standard: <b>ws://127.0.0.1:4455</b>. In OBS muss unter <b>Werkzeuge &gt; WebSocket-Servereinstellungen</b> der WebSocket-Server aktiviert sein.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testObs">Verbindung testen</button><span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " · "+esc(cfg.detail) : ""}</span></div></form>`;
  if(p==="spotify") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri || "http://127.0.0.1:5173/callback")}<div class="hint">Spotify braucht keinen Accountnamen. Die Redirect URI ist manuell einstellbar und wird genau so für OAuth benutzt.</div><div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">Spotify anmelden</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Trennen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
  if(p==="openai") return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("api_key","API-Key",cfg.api_key,"password")}${field("organization","Organisations-ID (optional)",cfg.organization)}${field("project","Projekt-ID (optional)",cfg.project)}<div class="hint">Der API-Key wird lokal in <b>data/settings.json</b> gespeichert. Ein ChatGPT-Abo enthaelt nicht automatisch API-Guthaben. Beim Verbinden wird nur die Modellliste der offiziellen OpenAI-API abgerufen und keine Antwort erzeugt. Modelle waehlst du im jeweiligen Plugin.</div><div class="btnLine"><button type="submit">Speichern</button><button type="button" class="secondary testOpenAI">ChatGPT verbinden</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">ChatGPT trennen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}${cfg.detail ? " - "+esc(cfg.detail) : ""}</span></div></form>`;
  return `<form class="platformForm" data-platform="${p}">${sel("enabled","Aktiv",cfg.enabled)}${sel("autoconnect","Autoconnect",cfg.autoconnect ?? true)}${field("main","Main/Kanal",cfg.main)}${field("bot","Bot",cfg.bot)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri)}<div class="btnLine"><button type="submit">Speichern</button><a class="btn login" data-platform="${p}" data-account="main" href="#">OAuth Main</a><a class="btn login" data-platform="${p}" data-account="bot" href="#">OAuth Bot</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">Main trennen</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">Bot trennen</button>${devButton(p)}<span class="small">Status: ${esc(cfg.status||"nicht verbunden")}</span></div></form>`;
}
async function renderPlatforms(){
  const {settings,status}=await loadAll(); const p=settings.platforms;
  shell("platforms","Plattformen","Anmeldedaten bleiben im webbased/data Ordner.",["twitch","tiktok","youtube","kick","spotify","openai","meld","obs"].map(k=>`<section class="card platformCard"><h3>${platformLabel(k)}</h3>${platformForm(k,{...(p[k]||{}),...(status.platforms[k]||{})})}</section>`).join(""));
  $$("form[data-platform]").forEach(form=>{
    form.onsubmit=async(e)=>{
      e.preventDefault();
      const pf=form.dataset.platform;
      settingsCache = settingsCache || await api("/api/settings");
      settingsCache.platforms[pf] = settingsCache.platforms[pf] || {};
      if(pf === "obs") normalizeObsFields(form);
      applyFormValues(settingsCache.platforms[pf], form);
      if(pf === "openai"){ delete settingsCache.platforms[pf].model; }
      if(pf === "spotify"){ delete settingsCache.platforms[pf].main; delete settingsCache.platforms[pf].bot; }
      if(pf === "tiktok"){
        settingsCache.platforms[pf].main_account = (settingsCache.platforms[pf].main || "").replace(/^@/, "");
        settingsCache.platforms[pf].bot_account = (settingsCache.platforms[pf].bot || "").replace(/^@/, "");
        settingsCache.platforms[pf].test_channel = (settingsCache.platforms[pf].test_channel || "").replace(/^@/, "");
        settingsCache.platforms[pf].unique_id = settingsCache.platforms[pf].main_account;
        const testEnabled = settingsCache.platforms[pf].test_channel_enabled === "true" || settingsCache.platforms[pf].test_channel_enabled === true;
        const readChannel = testEnabled && settingsCache.platforms[pf].test_channel ? settingsCache.platforms[pf].test_channel : settingsCache.platforms[pf].main_account;
        settingsCache.platforms[pf].active_read_channel = readChannel || "";
        settingsCache.platforms[pf].live_url = readChannel ? `https://www.tiktok.com/@${readChannel}/live` : "";
        settingsCache.platforms[pf].resolved_live_url = settingsCache.platforms[pf].live_url;
      }
      if(pf === "meld"){ delete settingsCache.platforms[pf].password; }
      await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
      alert("Gespeichert");
    };
  });
  $$(".testMeld").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.meld = settingsCache.platforms.meld || {};
    applyFormValues(settingsCache.platforms.meld, form);
    delete settingsCache.platforms.meld.password;
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/meld");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".testObs").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    normalizeObsFields(form);
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.obs = settingsCache.platforms.obs || {};
    applyFormValues(settingsCache.platforms.obs, form);
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/obs");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".testOpenAI").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.openai = settingsCache.platforms.openai || {};
    applyFormValues(settingsCache.platforms.openai, form);
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/openai");
    alert((res.ok ? "Verbunden: " : "Nicht verbunden: ") + (res.detail || ""));
    location.reload();
  });
  $$(".tiktokLogin").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.tiktok = settingsCache.platforms.tiktok || {};
    applyFormValues(settingsCache.platforms.tiktok, form);
    settingsCache.platforms.tiktok.main_account = (settingsCache.platforms.tiktok.main || "").replace(/^@/, "");
    settingsCache.platforms.tiktok.bot_account = (settingsCache.platforms.tiktok.bot || "").replace(/^@/, "");
    settingsCache.platforms.tiktok.test_channel = (settingsCache.platforms.tiktok.test_channel || "").replace(/^@/, "");
    settingsCache.platforms.tiktok.unique_id = settingsCache.platforms.tiktok.main_account;
    const testEnabled = settingsCache.platforms.tiktok.test_channel_enabled === "true" || settingsCache.platforms.tiktok.test_channel_enabled === true;
    const readChannel = testEnabled && settingsCache.platforms.tiktok.test_channel ? settingsCache.platforms.tiktok.test_channel : settingsCache.platforms.tiktok.main_account;
    settingsCache.platforms.tiktok.active_read_channel = readChannel || "";
    settingsCache.platforms.tiktok.live_url = readChannel ? `https://www.tiktok.com/@${readChannel}/live` : "";
    settingsCache.platforms.tiktok.resolved_live_url = settingsCache.platforms.tiktok.live_url;
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api(`/api/tiktok/open/${b.dataset.account || "main"}`);
    const oldText = b.textContent;
    b.textContent = res.ok ? (res.already_logged_in ? "Bereits angemeldet" : "Loginfenster geöffnet") : "Öffnen fehlgeschlagen";
    setTimeout(()=>{ b.textContent = oldText; }, 3000);
    if(!res.ok) alert(res.error || "TikTok konnte nicht geöffnet werden");
  });
  $$(".devBtn").forEach(b=>b.onclick=async()=>{
    const url = b.dataset.url || b.getAttribute("href") || "";
    const oldText = b.textContent;
    b.textContent = "Geoeffnet";
    const res = await openExternal(url);
    setTimeout(()=>{ b.textContent = oldText; }, 1800);
    if(!res.ok) alert(res.error || "Dev-Seite konnte nicht geoeffnet werden");
  });
  $$(".login").forEach(a=>a.onclick=async(e)=>{
    e.preventDefault();
    const form=a.closest("form");
    const pf=form.dataset.platform;
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms[pf] = settingsCache.platforms[pf] || {};
    applyFormValues(settingsCache.platforms[pf], form, {boolKeys:["enabled"]});
    if(pf === "spotify"){ delete settingsCache.platforms[pf].main; delete settingsCache.platforms[pf].bot; }
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res = await api(`/api/oauth/open/${a.dataset.platform}/${a.dataset.account}`, {timeoutMs:2500});
    if(!res.ok) alert(res.error || "OAuth-Anmeldung konnte nicht geoeffnet werden");
  });
  $$(".disconnect").forEach(b=>b.onclick=async()=>{await api(`/api/disconnect/${b.dataset.platform}/${b.dataset.account}`,{method:"POST"}); location.reload();});
}
async function renderChat(){
  const [layout,state]=await Promise.all([api("/api/desktop-chat/layout"),api("/api/desktop-chat/state")]);
  const style=layout.style||{};
  const alerts=layout.alerts||{}, alertPlatforms=alerts.platforms||{};
  queueMicrotask(()=>{const edit=$(".editDesktopChat");if(!edit||$(".closeDesktopChat"))return;const reset=document.createElement("button");reset.className="secondary resetDesktopChat";reset.textContent="Desktopfenster zuruecksetzen";reset.onclick=async()=>{if(!confirm("Desktopfenster auf Standardposition und -groesse zuruecksetzen?"))return;const r=await api("/api/desktop-chat/reset",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht zurueckgesetzt werden");};const close=document.createElement("button");close.className="secondary closeDesktopChat";close.textContent="Desktopfenster schliessen";close.onclick=async()=>{const r=await api("/api/desktop-chat/close",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht geschlossen werden");};edit.before(reset,close);});
  shell("chat","Chat","Gemeinsamer Chat für Dashboard, Browserquelle und Desktopfenster.",`<div class="btnLine"><button class="openDesktopChat">Desktopfenster öffnen</button><button class="secondary editDesktopChat">${state.editing?"Bearbeitung beenden":"Desktopfenster editieren"}</button><a class="btn secondary" href="/chat-browser" target="_blank">Browserfenster öffnen</a></div><section class="card desktopSettings"><h3>Desktopfenster Darstellung</h3><div class="platformForm"><label><div>Hintergrund</div><input name="background" type="color" value="${esc(style.background||"#0d101d")}"></label><label><div>Transparenz</div><input name="opacity" type="range" min="0" max="100" value="${esc(style.opacity??82)}"></label><label><div>Radien</div><input name="radius" type="range" min="0" max="100" value="${esc(style.radius??16)}"></label>${field("fontFamily","Schriftart",style.fontFamily||"Segoe UI")}${field("fontSize","Schriftgröße",style.fontSize||16,"number")}<label><div>Schriftfarbe</div><input name="textColor" type="color" value="${esc(style.textColor||"#ffffff")}"></label><label><div>Desktopfenster beim Toolstart öffnen</div><input class="desktopAutoStart" type="checkbox" ${layout.autoStart?"checked":""}></label></div></section><section class="card chatBox"><div class="messages" id="messages"></div><div class="sendRow"><input id="testmsg" placeholder="Testnachricht ins Overlay schicken"><button id="sendMsg">Senden</button></div></section>`);
  const alertSettings=document.createElement("section");alertSettings.className="card desktopSettings";alertSettings.innerHTML=`<h3>Alertbereich im Desktopfenster</h3><div class="platformForm"><label><div>Alertbereich anzeigen</div><input class="alertEnabled" type="checkbox" ${alerts.enabled!==false?"checked":""}></label><label><div>Alerts gleichzeitig</div><input class="alertMaxItems" type="number" min="1" max="20" value="${esc(alerts.maxItems??5)}"></label><label><div>Uhrzeit anzeigen</div><input class="alertTimestamp" type="checkbox" ${alerts.showTimestamp!==false?"checked":""}></label><div class="hint">Im Bearbeitungsmodus ist „Alerts“ ein eigenes, frei verschiebbares Element. Welche Eventtypen entstehen, wird weiterhin im Alert-Plugin je Plattform gesteuert.</div><div class="alertPlatformToggles">${["twitch","tiktok","youtube","kick"].map(p=>`<label>${platformBadge(p)} <span>${platformLabel(p)}</span><input class="alertPlatform" data-platform="${p}" type="checkbox" ${alertPlatforms[p]!==false?"checked":""}></label>`).join("")}</div></div>`;$(".chatBox").before(alertSettings);
  $(".alertTimestamp")?.closest("label")?.remove();
  $(".openDesktopChat").onclick=async()=>{const r=await api("/api/desktop-chat/open",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht geöffnet werden");};
  $(".editDesktopChat").onclick=async()=>{const next=!state.editing;await api("/api/desktop-chat/edit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({editing:next})});state.editing=next;$(".editDesktopChat").textContent=next?"Bearbeitung beenden":"Desktopfenster editieren";};
  $$(".desktopSettings input[name]").forEach(input=>input.oninput=async()=>{const next=structuredClone(layout);next.style=next.style||{};next.style[input.name]=input.type==="range"||input.type==="number"?Number(input.value):input.value;await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});Object.assign(layout,next);});
  $(".desktopAutoStart").onchange=async e=>{const next=structuredClone(layout);next.autoStart=e.target.checked;await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});Object.assign(layout,next);};
  const saveAlertSettings=async()=>{const next=structuredClone(layout);next.alerts={enabled:$(".alertEnabled").checked,maxItems:Number($(".alertMaxItems").value)||5,showTimestamp:false,platforms:Object.fromEntries($$(".alertPlatform").map(input=>[input.dataset.platform,input.checked]))};const r=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(r.ok)Object.assign(layout,next);};
  $$(".alertEnabled,.alertPlatform").forEach(input=>input.onchange=saveAlertSettings);$(".alertMaxItems").onchange=saveAlertSettings;
  $("#sendMsg").onclick=async()=>{let v=$("#testmsg").value.trim(); if(!v)return; await api("/api/message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v})}); $("#testmsg").value=""; refreshMessages();};
  refreshMessages();
}
async function renderObsMeld(){
  const [settings,targetData]=await Promise.all([api("/api/settings"),api("/api/automation/targets")]);
  const rules=Array.isArray(settings.automation_rules)?settings.automation_rules:[];
  const targets=targetData.targets||{};
  const values={tiktok:[["latest_follow","Neuester Follow"],["top_liker","Top-Liker"],["top_gifter","Top-Gifter"],["latest_gift","Neuestes Gift"],["like_total","Like-Zähler"]],twitch:[["latest_follow","Neuester Follow"],["latest_subscribe","Neuester Sub"],["latest_raid","Letzter Raid"],["latest_donation","Letzte Donation"],["latest_bits","Letzte Bits"]],youtube:[["latest_member","Neuestes Mitglied"],["latest_superchat","Letzter Superchat"]],kick:[["latest_follow","Neuester Follow"],["latest_subscribe","Neuester Sub"]]};
  const option=(items,selected="")=>items.map(([v,l])=>`<option value="${esc(v)}" ${v===selected?"selected":""}>${esc(l)}</option>`).join("");
  const targetOptions=Object.entries(targets).map(([key,value])=>[key,`${key.toUpperCase()}${value.connected?"":" (nicht verbunden)"}`]);
  const textActions=new Set(["text"]);
  const isTextRule=r=>textActions.has(String(r?.action||"text").toLowerCase());
  const isShowRule=r=>String(r?.action||"").toLowerCase()==="show";
  const isLikeCounterRule=r=>String(r?.platform||"").toLowerCase()==="tiktok"&&String(r?.value||"").toLowerCase()==="like_total";
  const savedLikeUsers=()=>[...new Set(rules.map(r=>String(r?.likeUser||r?.like_user||"").trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  const defaultPreview=r=>{
    const label=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value||"Wert";
    if(isLikeCounterRule(r))return `Test: ${String(r.likeUser||"Chatter")} · Intervall ${Number(r.likeThreshold||0)||1} Likes`;
    return `Test: ${label}`;
  };
  const persistRules=async()=>{
    settings.automation_rules=rules;
    return await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settings)});
  };

  shell("obs_meld","OBS/Meld Integration","Dauerhafte Live-Werte gezielt in eine OBS- oder Meld-Quelle schreiben.",`<section class="card integrationBuilder"><h3>Neuen Eintrag anlegen</h3><div class="integrationFlow"><label><div>1 · Plattform</div><select id="rulePlatform">${option([["tiktok","TikTok"],["twitch","Twitch"],["youtube","YouTube"],["kick","Kick"]])}</select></label><label><div>2 · Live-Wert</div><select id="ruleValue"></select></label><label><div>3 · Ausgabe</div><select id="ruleTarget">${option(targetOptions)}</select></label><label><div>4 · Szene</div><select id="ruleScene"></select></label><label><div>5 · Quelle</div><select id="ruleSource"></select></label></div><div class="integrationName"><label><div>Name dieses Eintrags</div><input id="ruleName" placeholder="z. B. TikTok Like-Zähler Aktion"></label><div class="btnLine"><button id="saveRule">Speichern</button><button class="secondary" id="clearRule">Ändern abbrechen</button></div></div></section><section class="card"><h3>Gespeicherte Einträge</h3><div id="ruleList" class="ruleList"></div></section>`);
  const reloadButton=document.createElement("button");
  reloadButton.className="secondary targetReload";
  reloadButton.textContent="Szenen & Quellen neu laden";
  reloadButton.onclick=async()=>{await api("/api/automation/reload-targets",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});setTimeout(renderObsMeld,900);};
  $(".integrationBuilder").append(reloadButton);

  const actionField=document.createElement("label");
  actionField.innerHTML=`<div>6 · Aktion</div><select id="ruleAction"><option value="text">Live-Wert als Text schreiben</option><option value="show">Quelle einblenden</option><option value="hide">Quelle ausblenden</option><option value="play">Quelle einmal abspielen</option><option value="scene">Szene aktivieren</option></select>`;
  $(".integrationFlow").append(actionField);
  const likeCounterField=document.createElement("div");
  likeCounterField.className="likeCounterFields";
  likeCounterField.innerHTML=`<label><div>Chatter</div><input id="ruleLikeUser" list="ruleLikeUserList" placeholder="TikTok-Name exakt eingeben"></label><label><div>Auslösen alle X Likes</div><input id="ruleLikeThreshold" type="number" min="1" step="1" value="10"></label><datalist id="ruleLikeUserList"></datalist><div class="hint">Gilt nur für TikTok Like-Zähler: Die Aktion läuft wiederkehrend bei jedem Intervall dieses Users, z. B. 50, 100, 150 Likes.</div>`;
  $(".integrationFlow").append(likeCounterField);
  const hideSecondsField=document.createElement("label");
  hideSecondsField.className="hideSecondsField";
  hideSecondsField.innerHTML=`<div>Nach X Sekunden ausblenden</div><input id="ruleHideSeconds" type="number" min="0" max="3600" step="0.1" value="4"><div class="hint">0 = nicht automatisch ausblenden.</div>`;
  $(".integrationFlow").append(hideSecondsField);
  const startupField=document.createElement("label");
  startupField.className="textStartupField";
  startupField.innerHTML=`<div>Text beim Toolstart</div><select id="ruleStartup"><option value="keep">Letzten Wert behalten</option><option value="placeholder">Platzhalter anzeigen</option></select>`;
  $(".integrationFlow").append(startupField);
  const placeholderField=document.createElement("label");
  placeholderField.className="textPlaceholderField";
  placeholderField.innerHTML=`<div>Platzhalter</div><input id="rulePlaceholder" value="---" placeholder="z. B. Noch keine Daten">`;
  $(".integrationFlow").append(placeholderField);

  const fillLikeUserList=()=>{$("#ruleLikeUserList").innerHTML=savedLikeUsers().map(x=>`<option value="${esc(x)}"></option>`).join("");};
  const selectedIsLikeCounter=()=>$("#rulePlatform").value==="tiktok"&&$("#ruleValue").value==="like_total";
  const toggleTextOptions=()=>{const action=$("#ruleAction").value,text=action==="text",placeholder=$("#ruleStartup").value==="placeholder";startupField.hidden=!text;placeholderField.hidden=!text||!placeholder;likeCounterField.hidden=!selectedIsLikeCounter();hideSecondsField.hidden=action!=="show";};
  $("#ruleAction").onchange=toggleTextOptions;$("#ruleStartup").onchange=toggleTextOptions;

  let editIndex=-1;
  const refreshSources=()=>{const target=targets[$("#ruleTarget").value]||{},scene=$("#ruleScene").value,sources=(target.sources_by_scene||{})[scene]||[];$("#ruleSource").innerHTML=option(sources.length?sources.map(x=>[x,x]):[["","Keine Quelle in dieser Szene"]]);};
  const refreshTargets=()=>{const key=$("#ruleTarget").value,target=targets[key]||{},scenes=target.scenes||[];$("#ruleScene").innerHTML=option(scenes.length?scenes.map(x=>[x,x]):[["","Zuerst OBS/Meld verbinden"]]);refreshSources();};
  const refreshValues=()=>{$("#ruleValue").innerHTML=option(values[$("#rulePlatform").value]||[]);toggleTextOptions();};
  const readRule=()=>{
    const r={name:$("#ruleName").value.trim()||`${platformLabel($("#rulePlatform").value)} ${$("#ruleValue").selectedOptions[0]?.textContent||"Wert"}`,platform:$("#rulePlatform").value,value:$("#ruleValue").value,target:$("#ruleTarget").value,scene:$("#ruleScene").value,source:$("#ruleSource").value,action:$("#ruleAction").value,startup:$("#ruleStartup").value,placeholder:$("#rulePlaceholder").value.trim()||"---"};
    if(r.action==="show")r.hideSeconds=Math.max(0,Number($("#ruleHideSeconds").value)||0);
    if(isLikeCounterRule(r)){r.likeUser=$("#ruleLikeUser").value.trim();r.likeThreshold=Math.max(1,Number($("#ruleLikeThreshold").value)||1);}
    return r;
  };
  const runRuleTest=async (r,previewText)=>{
    const body={...r};
    if(isTextRule(r))body.preview=String(previewText||r.testText||defaultPreview(r));
    const out=await api("/api/automation/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    if(!out.ok)console.warn("Regeltest fehlgeschlagen",out.error);
  };
  const renderRules=()=>{
    fillLikeUserList();
    $("#ruleList").innerHTML=rules.length?rules.map((r,i)=>{
      const textRule=isTextRule(r);
      const testText=String(r.testText||defaultPreview(r));
      const valueLabel=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value;
      const condition=isLikeCounterRule(r)?` · User: ${esc(r.likeUser||"-")} · alle ${esc(r.likeThreshold||"-")} Likes`:"";
      const showInfo=isShowRule(r)?` · ausblenden nach ${esc(r.hideSeconds??4)}s`:"";
      const testControls=textRule
        ? `<input class="savedRuleTestText" data-i="${i}" value="${esc(testText)}" placeholder="Testtext"><button class="secondary testSavedRule" data-i="${i}">Testen</button>`
        : `<button class="secondary testSavedRule" data-i="${i}">Testen</button>`;
      return `<div class="ruleRow"><div><b>${esc(r.name)}</b><div class="small">${esc(platformLabel(r.platform))} · ${esc(valueLabel)}${condition} → ${esc((r.target||"").toUpperCase())} · ${esc(r.scene||"-")} · ${esc(r.source||"-")} · ${esc(r.action||"text")}${showInfo}</div></div><div class="btnLine">${testControls}<button class="secondary editRule" data-i="${i}">Ändern</button><button class="secondary deleteRule" data-i="${i}">Löschen</button></div></div>`;
    }).join(""):`<div class="hint">Noch keine Einträge. Lege oben gezielt einen dauerhaften Live-Wert an.</div>`;
    let testTextSaveTimer=null;
    const queueTestTextSave=()=>{clearTimeout(testTextSaveTimer);testTextSaveTimer=setTimeout(()=>persistRules(),450);};
    $$('.savedRuleTestText').forEach(input=>{
      input.oninput=()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;queueTestTextSave();};
      input.onchange=async()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;await persistRules();};
    });
    $$('.testSavedRule').forEach(b=>b.onclick=async()=>{const i=Number(b.dataset.i);const r=rules[i];if(!r)return;const input=$(`.savedRuleTestText[data-i="${i}"]`);if(input){r.testText=input.value;await persistRules();await runRuleTest(r,input.value);}else{await runRuleTest(r);}});
    $$('.editRule').forEach(b=>b.onclick=()=>{const r=rules[Number(b.dataset.i)];editIndex=Number(b.dataset.i);$("#rulePlatform").value=r.platform;refreshValues();$("#ruleValue").value=r.value;toggleTextOptions();$("#ruleTarget").value=r.target;refreshTargets();$("#ruleScene").value=r.scene||"";refreshSources();$("#ruleSource").value=r.source||"";$("#ruleAction").value=r.action||"text";$("#ruleStartup").value=r.startup||"keep";$("#rulePlaceholder").value=r.placeholder||"---";$("#ruleHideSeconds").value=r.hideSeconds??r.hide_seconds??4;$("#ruleLikeUser").value=r.likeUser||r.like_user||"";$("#ruleLikeThreshold").value=r.likeThreshold||r.like_threshold||10;toggleTextOptions();$("#ruleName").value=r.name;$("#saveRule").textContent="Änderung speichern";});
    $$('.deleteRule').forEach(b=>b.onclick=async()=>{rules.splice(Number(b.dataset.i),1);await persistRules();renderRules();});
  };
  $("#rulePlatform").onchange=()=>{refreshValues();};$("#ruleValue").onchange=toggleTextOptions;$("#ruleTarget").onchange=refreshTargets;$("#ruleScene").onchange=refreshSources;
  $("#clearRule").onclick=()=>{editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleHideSeconds").value=4;$("#saveRule").textContent="Speichern";};
  $("#saveRule").onclick=async()=>{const r=readRule();if(isLikeCounterRule(r)&&!r.likeUser){alert("Bitte einen Chatter für den Like-Zähler eintragen.");return;}if(editIndex>=0){r.testText=rules[editIndex]?.testText||defaultPreview(r);rules[editIndex]=r;}else{r.testText=defaultPreview(r);rules.push(r);}const out=await persistRules();if(!out.ok){console.warn("Regel speichern fehlgeschlagen",out.error);return;}editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleHideSeconds").value=4;$("#saveRule").textContent="Speichern";renderRules();};
  fillLikeUserList();refreshValues();refreshTargets();toggleTextOptions();renderRules();
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
  const wide=(field.wide||field.full_width||field.fullWidth||field.span==="full")?" wide":"";
  const compact=(field.compact||field.dense)?" compact":"";
  const hideIf=field.hide_if||field.hideIf||null;
  const hideMode=field.hide_mode||field.hideMode||"";
  const hideAttrs=hideIf&&hideIf.key?` data-hide-key="${esc(hideIf.key)}" data-hide-value="${esc(hideIf.value??"")}"${hideMode?` data-hide-mode="${esc(hideMode)}"`:""}`:"";
  const cls=(wide+compact).trim();
  const helpHtml=help?`<div class="hint${wide}">${esc(help)}</div>`:"";
  if(type==="button" || type==="action"){
    const buttonText=field.button_text||field.text||label||"Ausführen";
    return `<label class="settingsAction${wide}${compact}"${hideAttrs}><div>${label}</div><button type="button" class="secondary pluginActionBtn" data-key="${esc(key)}" ${readonly?"disabled":""}>${esc(buttonText)}</button></label>${helpHtml}`;
  }
  if(type==="bool" || type==="boolean" || type==="checkbox"){
    const checked=(value===true||String(value).toLowerCase()==="true"||String(value)==="1")?"checked":"";
    return `<label class="settingsBool${wide}${compact}"${hideAttrs}><input name="${esc(key)}" type="checkbox" ${checked} ${readonly?"disabled":""}><span>${label}</span></label>${helpHtml}`;
  }
  const opts=field.options||field.choices||field.values;
  if((type==="select" || Array.isArray(opts)) && Array.isArray(opts)){
    const normalizedOpts=[...opts];
    if(String(value??"") && !normalizedOpts.some(o=>String(typeof o==="object"?(o.value??o.id??o.key??o.label):o)===String(value))){
      normalizedOpts.unshift({value:String(value),label:`${String(value)} (gespeichert)`});
    }
    const options=normalizedOpts.map(o=>{
      const v=typeof o==="object"?(o.value??o.id??o.key??o.label):o;
      const l=typeof o==="object"?(o.label??o.name??v):o;
      return `<option value="${esc(v)}" ${String(value??"")===String(v)?"selected":""}>${esc(l)}</option>`;
    }).join("");
    return `<label class="${cls}"${hideAttrs}><div>${label}</div><select name="${esc(key)}" ${readonly?"disabled":""}>${options}</select></label>${helpHtml}`;
  }
  if(type==="taglist" || type==="chips" || type==="userlist"){
    return `<div class="settingsTagListField ${cls}"${hideAttrs} data-enhanced-taglist="1" data-key="${esc(key)}"><div class="settingsFieldTitle">${label}</div><input class="tagListInput" type="text" placeholder="${esc(field.placeholder||"Eintrag eingeben und Enter drücken")}" ${readonly?"disabled":""}><div class="tagListChips"></div><textarea name="${esc(key)}" class="tagListValue" ${ro}>${esc(value??field.default??"")}</textarea></div>${helpHtml}`;
  }
  if(type==="template" || type==="template_editor"){
    const tokens=Array.isArray(field.tokens)?field.tokens:["{user}","{platform}","{word}","{action}","{duration}"];
    return `<div class="settingsTemplateField ${cls}"${hideAttrs} data-enhanced-template="1" data-key="${esc(key)}"><div class="settingsFieldTitle">${label}</div><textarea name="${esc(key)}" ${ro} placeholder="${esc(field.placeholder||"")}">${esc(value??field.default??"")}</textarea><div class="templateTokenRow">${tokens.map(t=>`<button type="button" class="secondary templateToken" data-token="${esc(t)}" ${readonly?"disabled":""}>${esc(t)}</button>`).join("")}</div><div class="templatePreview"><span>Vorschau:</span> <b></b></div></div>${helpHtml}`;
  }
  if(type==="multiline" || type==="textarea"){
    return `<label class="${cls}"${hideAttrs}><div>${label}</div><textarea name="${esc(key)}" ${ro} placeholder="${esc(field.placeholder||"")}">${esc(value??field.default??"")}</textarea></label>${helpHtml}`;
  }
  const inputType=(type==="number"||type==="int"||type==="float")?"number":(type==="password"?"password":"text");
  return `<label class="${cls}"${hideAttrs}><div>${label}</div><input name="${esc(key)}" type="${inputType}" value="${esc(value??field.default??"")}" ${ro} placeholder="${esc(field.placeholder||"")}"></label>${helpHtml}`;
}

function initPluginEnhancedFields(root){
  if(!root) return;
  $$('[data-enhanced-taglist="1"]', root).forEach(box=>{
    const area=box.querySelector('textarea.tagListValue');
    const input=box.querySelector('input.tagListInput');
    const chips=box.querySelector('.tagListChips');
    if(!area || !input || !chips || box.dataset.ready === "1") return;
    box.dataset.ready="1";
    const parse=()=>String(area.value||"").split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean);
    const sync=(items)=>{area.value=[...new Set(items.map(x=>x.trim()).filter(Boolean))].join("\n"); render(); area.dispatchEvent(new Event('change',{bubbles:true}));};
    const render=()=>{
      const items=parse();
      chips.innerHTML=items.length?items.map((item,idx)=>`<button type="button" class="tagChip" data-idx="${idx}" title="Entfernen">${esc(item)}<span>×</span></button>`).join(""):`<div class="emptyChips">Noch keine ignorierten User.</div>`;
      $$('.tagChip', chips).forEach(btn=>btn.onclick=()=>{const next=parse(); next.splice(Number(btn.dataset.idx||0),1); sync(next);});
    };
    input.addEventListener('keydown', ev=>{
      if(ev.key !== 'Enter') return;
      ev.preventDefault();
      const val=String(input.value||"").trim().replace(/^[@#]+/,"");
      if(!val) return;
      sync([...parse(), val]);
      input.value="";
    });
    input.addEventListener('blur', ()=>{
      const val=String(input.value||"").trim().replace(/^[@#]+/,"");
      if(!val) return;
      sync([...parse(), val]);
      input.value="";
    });
    render();
  });
  $$('[data-enhanced-template="1"]', root).forEach(box=>{
    const area=box.querySelector('textarea');
    const preview=box.querySelector('.templatePreview b');
    if(!area || box.dataset.ready === "1") return;
    box.dataset.ready="1";
    const update=()=>{
      if(preview){
        let sample=String(area.value||"");
        const repl={"{user}":"baduser","{platform}":"twitch","{word}":"spamwort","{action}":"timeout","{duration}":"600"};
        for(const [k,v] of Object.entries(repl)) sample=sample.split(k).join(v);
        preview.textContent=sample || "leer";
      }
    };
    $$('.templateToken', box).forEach(btn=>btn.onclick=()=>{
      const token=btn.dataset.token||"";
      const start=area.selectionStart ?? area.value.length;
      const end=area.selectionEnd ?? area.value.length;
      area.value=area.value.slice(0,start)+token+area.value.slice(end);
      const pos=start+token.length;
      area.focus();
      area.setSelectionRange(pos,pos);
      area.dispatchEvent(new Event('input',{bubbles:true}));
      area.dispatchEvent(new Event('change',{bubbles:true}));
      update();
    });
    area.addEventListener('input', update);
    update();
  });
}

function collectPluginSettings(form, schema){
  const values={};
  for(const field of (schema||[])){
    const key=String(field.key||field.name||"");
    const type=String(field.type||"").toLowerCase();
    if(!key || field.readonly || field.disabled || ["separator","section","button","action"].includes(type)) continue;
    const el=form.elements[key];
    if(!el) continue;
    if(type==="bool"||type==="boolean"||type==="checkbox") values[key]=!!el.checked;
    else if(type==="number"||type==="int") values[key]=parseInt(el.value||"0",10)||0;
    else if(type==="float") values[key]=parseFloat(el.value||"0")||0;
    else values[key]=String(el.value??"");
  }
  return values;
}
async function enrichPluginSchema(pluginId, schema, values){
  const out=(schema||[]).map(f=>({...f}));
  if(pluginId !== "botalot") return out;
  const modelField=out.find(f=>String(f.key||f.name||"")==="openai_model");
  if(!modelField) return out;
  modelField.type="select";
  try{
    const res=await api("/api/openai/models");
    const models=Array.isArray(res.models)?res.models:[];
    if(models.length){
      modelField.options=models.map(m=>({value:m,label:m}));
      if(!values.openai_model || !models.includes(values.openai_model)) values.openai_model=models[0];
      return out;
    }
    modelField.options=[{value:String(values.openai_model||""),label:res.detail||"Keine passenden Modelle gefunden"}];
  }catch(e){
    modelField.options=[{value:String(values.openai_model||""),label:"Modelle konnten nicht geladen werden"}];
  }
  return out;
}
function applyPluginSettingsVisibility(root){
  if(!root) return;
  const refresh=()=>{
    $$('[data-hide-key]', root).forEach(el=>{
      const key=el.dataset.hideKey;
      const val=el.dataset.hideValue;
      const ctrl=root.elements ? root.elements[key] : root.querySelector(`[name="${CSS.escape(key)}"]`);
      let current="";
      if(ctrl){
        if(ctrl.type==="checkbox") current=ctrl.checked?"true":"false";
        else current=String(ctrl.value??"");
      }
      const shouldHide=current===String(val);
      if(el.dataset.hideMode === "invisible"){
        el.style.visibility=shouldHide?"hidden":"";
        el.style.pointerEvents=shouldHide?"none":"";
        el.setAttribute("aria-hidden", shouldHide?"true":"false");
      }else{
        el.style.display=shouldHide?"none":"";
      }
    });
  };
  refresh();
  $$('select,input,textarea', root).forEach(el=>el.addEventListener('change', refresh));
}
function openInfo3ditorSettings(mount, values){
  let state={presets:[]},selected=0;
  try{const raw=JSON.parse(values.presets_json||'{"presets":[]}');state.presets=Array.isArray(raw.presets)?raw.presets:[];}catch(e){}
  const fields={twitch:[['title','Streamtitel'],['category','Kategorie / Game'],['game_id','Game-ID (optional)'],['tags','Tags (Komma getrennt)'],['description','Beschreibung / Notiz']],youtube:[['title','Titel'],['description','Beschreibung'],['category','Kategorie'],['tags','Tags (Komma getrennt)']],kick:[['title','Titel'],['category','Kategorie'],['description','Beschreibung / Notiz'],['tags','Tags (Komma getrennt)']],tiktok:[['title','Live-Titel'],['description','Beschreibung / Notiz']]};
  const empty=()=>({id:'preset_'+Date.now(),name:'Neues Spiel',platforms:{twitch:{enabled:false},youtube:{enabled:false},kick:{enabled:false},tiktok:{enabled:false}}});
  const current=()=>state.presets[selected]||null;
  const draw=()=>{const p=current();if(!p){mount.innerHTML='<section class="card pluginSettingsCard"><button id="infoNew">Spiel anlegen</button></section>';$('#infoNew',mount).onclick=()=>{state.presets.push(empty());selected=state.presets.length-1;draw()};return;}p.platforms=p.platforms||{};const tabs=Object.entries(fields).map(([platform,rows])=>{const d=p.platforms[platform]||{};return `<details class="pluginSettingsGroup" open><summary><b>${esc(platform)}</b></summary><div class="platformForm"><label><div>Aktiv senden</div><input type="checkbox" data-info="${platform}.enabled" ${d.enabled?'checked':''} ${platform==='tiktok'?'disabled':''}></label>${rows.map(([key,label])=>`<label><div>${esc(label)}</div>${key==='description'?`<textarea data-info="${platform}.${key}">${esc(d[key]||'')}</textarea>`:`<input data-info="${platform}.${key}" value="${esc(d[key]||'')}">`}</label>`).join('')}</div></details>`}).join('');mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor Presets</h3><div class="small">Ein Spiel anlegen, Plattformdaten pflegen und an aktivierte Plattformen senden.</div></div><button class="secondary" id="pluginSettingsClose">Schließen</button></div><div class="btnLine"><select id="infoPreset">${state.presets.map((x,i)=>`<option value="${i}" ${i===selected?'selected':''}>${esc(x.name||'Unbenannt')}</option>`).join('')}</select><button id="infoNew">Spiel anlegen</button><button class="secondary" id="infoDelete">Löschen</button></div><div class="platformForm"><label><div>Spiel / Presetname</div><input id="infoName" value="${esc(p.name||'')}"></label></div>${tabs}<div class="btnLine"><button id="infoSave">Speichern</button><button class="secondary" id="infoSend">An aktivierte Plattformen senden</button><span class="small" id="infoResult"></span></div></section>`;$('#pluginSettingsClose',mount).onclick=()=>mount.innerHTML='';$('#infoPreset',mount).onchange=e=>{selected=Number(e.target.value);draw()};$('#infoNew',mount).onclick=()=>{state.presets.push(empty());selected=state.presets.length-1;draw()};$('#infoDelete',mount).onclick=()=>{state.presets.splice(selected,1);selected=Math.max(0,selected-1);draw()};const collect=()=>{p.name=$('#infoName',mount).value.trim()||'Neues Spiel';for(const el of $$('[data-info]',mount)){const [platform,key]=el.dataset.info.split('.');p.platforms[platform]=p.platforms[platform]||{};p.platforms[platform][key]=el.type==='checkbox'?el.checked:el.value.trim();}p.platforms.tiktok.enabled=false;return JSON.stringify({presets:state.presets});};const save=async()=>api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:collect()}})});$('#infoSave',mount).onclick=async()=>{const r=await save();$('#infoResult',mount).textContent=r.ok?'Gespeichert.':'Fehler: '+(r.error||'?')};$('#infoSend',mount).onclick=async()=>{const raw=collect();const r=await api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:raw,selected_preset_id:p.id}})});$('#infoResult',mount).textContent=r.ok?'Sendevorgang gestartet.':'Fehler: '+(r.error||'?')};};draw();
}
function openInfo3ditorSettings(mount, values){
  let presets=[];
  let selected=0;
  try{const raw=JSON.parse(values.presets_json||'{"presets":[]}');presets=Array.isArray(raw.presets)?raw.presets:[];}catch(e){}
  const platformFields={
    twitch:[['title','Streamtitel'],['category','Kategorie / Game'],['game_id','Game-ID (optional)'],['tags','Tags'],['description','Beschreibung / Notiz']],
    youtube:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung']],
    kick:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung / Notiz']],
    tiktok:[['title','Live-Titel'],['category','Kategorie'],['description','Nicht verfügbar']],
  };
  const newPreset=()=>({id:`preset_${Date.now()}`,name:'Neues Spiel',platforms:{twitch:{enabled:false},youtube:{enabled:false},kick:{enabled:false},tiktok:{enabled:false}}});
  const serialize=()=>JSON.stringify({presets});
  const render=()=>{
    const preset=presets[selected];
    if(!preset){mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Info3ditor Presets</h3><button id="infoNew">Spiel anlegen</button></section>`;$('#infoNew',mount).onclick=()=>{presets.push(newPreset());selected=presets.length-1;render()};return;}
    preset.platforms=preset.platforms||{};
    const platformBlocks=Object.entries(platformFields).map(([platform,fields])=>{
      const data=preset.platforms[platform]||{};
      const unavailable=platform==='tiktok';
      return `<section class="infoPlatform"><div class="infoPlatformHead"><h3>${esc(platform)}</h3><label><input type="checkbox" data-info="${platform}.enabled" ${data.enabled?'checked':''} ${unavailable?'disabled':''}> ${unavailable?'Noch nicht sendbar':'Beim Senden aktiv'}</label></div><div class="platformForm">${fields.map(([key,label])=>`<label><div>${esc(label)}</div>${key==='description'?`<textarea data-info="${platform}.${key}" ${unavailable?'disabled':''}>${esc(unavailable?'TikTok wird aktuell nicht unterstützt.':data[key]||'')}</textarea>`:`<input data-info="${platform}.${key}" value="${esc(data[key]||'')}" ${unavailable?'disabled':''}>`}</label>`).join('')}</div></section>`;
    }).join('');
    mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor Presets</h3><div class="small">Lege Spiele an und sende Titel/Kategorie an die je Preset aktivierten Plattformen.</div></div><button class="secondary" id="pluginSettingsClose">Schließen</button></div><div class="btnLine infoPresetButtons">${presets.map((item,index)=>`<button class="secondary infoPresetBtn ${index===selected?'active':''}" data-preset="${index}">${esc(item.name||'Unbenannt')}</button>`).join('')}<button id="infoNew">Spiel anlegen</button><button class="secondary" id="infoDelete">Löschen</button></div><div class="platformForm"><label><div>Spiel / Presetname</div><input id="infoName" value="${esc(preset.name||'')}"></label></div>${platformBlocks}<div class="btnLine"><button id="infoSave">Speichern</button><button class="secondary" id="infoSend">An aktivierte Plattformen senden</button><span class="small" id="infoResult"></span></div></section>`;
    $('#pluginSettingsClose',mount).onclick=()=>mount.innerHTML='';
    $$('.infoPresetBtn',mount).forEach(button=>button.onclick=()=>{selected=Number(button.dataset.preset);render()});
    $('#infoNew',mount).onclick=()=>{presets.push(newPreset());selected=presets.length-1;render()};
    $('#infoDelete',mount).onclick=()=>{presets.splice(selected,1);selected=Math.max(0,selected-1);render()};
    const collect=()=>{preset.name=$('#infoName',mount).value.trim()||'Neues Spiel';$$('[data-info]',mount).forEach(input=>{const [platform,key]=input.dataset.info.split('.');preset.platforms[platform]=preset.platforms[platform]||{};preset.platforms[platform][key]=input.type==='checkbox'?input.checked:input.value.trim();});preset.platforms.tiktok.enabled=false;return serialize();};
    $('#infoSave',mount).onclick=async()=>{const out=await api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:collect()}})});$('#infoResult',mount).textContent=out.ok?'Gespeichert.':'Fehler: '+(out.error||'?')};
    $('#infoSend',mount).onclick=async()=>{const out=await api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:collect(),selected_preset_id:preset.id}})});$('#infoResult',mount).textContent=out.ok?'Sendevorgang gestartet.':'Fehler: '+(out.error||'?')};
  };
  render();
}
function openInfo3ditorSettings(mount, values){
  let presets=[];
  try{const raw=JSON.parse(values.presets_json||'{"presets":[]}');presets=Array.isArray(raw.presets)?raw.presets:[];}catch(e){}
  const fields={twitch:[['title','Streamtitel'],['category','Kategorie / Game'],['game_id','Game-ID (optional)'],['tags','Tags'],['description','Beschreibung / Notiz']],youtube:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung']],kick:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung / Notiz']],tiktok:[['title','Live-Titel'],['category','Kategorie'],['description','Nicht verfügbar']]};
  const save=async()=>api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:JSON.stringify({presets})}})});
  const send=async preset=>api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:JSON.stringify({presets}),selected_preset_id:preset.id}})});
  const showList=()=>{mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor</h3><div class="small">Ein Spiel anklicken, um dessen Streaminfos an die aktivierten Plattformen zu senden.</div></div><button class="secondary" id="pluginSettingsClose">Schließen</button></div><div class="btnLine infoPresetButtons">${presets.map((preset,index)=>`<button class="infoSendPreset" data-preset="${index}">${esc(preset.name||'Unbenannt')}</button>`).join('')}<button class="secondary" id="infoNew">Spiel anlegen</button></div><div class="small" id="infoResult">${presets.length?'':'Noch keine Spiele angelegt.'}</div></section>`;$('#pluginSettingsClose',mount).onclick=()=>mount.innerHTML='';$('#infoNew',mount).onclick=()=>showEditor({id:`preset_${Date.now()}`,name:'Neues Spiel',platforms:{twitch:{enabled:false},youtube:{enabled:false},kick:{enabled:false},tiktok:{enabled:false}}});$$('.infoSendPreset',mount).forEach(button=>button.onclick=async()=>{const out=await send(presets[Number(button.dataset.preset)]);$('#infoResult',mount).textContent=out.ok?'Sendevorgang gestartet.':'Fehler: '+(out.error||'?')});};
  const showEditor=preset=>{preset.platforms=preset.platforms||{};const blocks=Object.entries(fields).map(([platform,rows])=>{const d=preset.platforms[platform]||{};const locked=platform==='tiktok';return `<section class="infoPlatform"><div class="infoPlatformHead"><h3>${esc(platform)}</h3><label><input type="checkbox" data-info="${platform}.enabled" ${d.enabled?'checked':''} ${locked?'disabled':''}> ${locked?'Noch nicht sendbar':'Beim Senden aktiv'}</label></div><div class="platformForm">${rows.map(([key,label])=>`<label><div>${esc(label)}</div>${key==='description'?`<textarea data-info="${platform}.${key}" ${locked?'disabled':''}>${esc(locked?'TikTok wird aktuell nicht unterstützt.':d[key]||'')}</textarea>`:`<input data-info="${platform}.${key}" value="${esc(d[key]||'')}" ${locked?'disabled':''}>`}</label>`).join('')}</div></section>`}).join('');mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Neues Spiel anlegen</h3><div class="small">Plattformdaten eintragen und anschließend speichern.</div></div><button class="secondary" id="infoBack">Abbrechen</button></div><div class="platformForm"><label><div>Spiel / Presetname</div><input id="infoName" value="${esc(preset.name||'')}"></label></div>${blocks}<div class="btnLine"><button id="infoSave">Spiel speichern</button><span class="small" id="infoResult"></span></div></section>`;$('#infoBack',mount).onclick=showList;$('#infoSave',mount).onclick=async()=>{preset.name=$('#infoName',mount).value.trim()||'Neues Spiel';$$('[data-info]',mount).forEach(input=>{const [platform,key]=input.dataset.info.split('.');preset.platforms[platform]=preset.platforms[platform]||{};preset.platforms[platform][key]=input.type==='checkbox'?input.checked:input.value.trim();});preset.platforms.tiktok.enabled=false;presets.push(preset);const out=await save();if(out.ok)showList();else $('#infoResult',mount).textContent='Fehler: '+(out.error||'?')};};
  showList();
}
function openInfo3ditorSettings(mount, values){
  let presets=[];
  try{const raw=JSON.parse(values.presets_json||'{"presets":[]}');presets=Array.isArray(raw.presets)?raw.presets:[];}catch(e){}
  const fields={twitch:[['title','Streamtitel'],['category','Kategorie / Game'],['game_id','Game-ID (optional)'],['tags','Tags'],['description','Beschreibung / Notiz']],youtube:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung']],kick:[['title','Streamtitel'],['category','Kategorie'],['tags','Tags'],['description','Beschreibung / Notiz']],tiktok:[['title','Live-Titel'],['category','Kategorie'],['description','Nicht verfügbar']]};
  const raw=()=>JSON.stringify({presets});
  const save=()=>api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:raw()}})});
  const send=preset=>api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:raw(),selected_preset_id:preset.id}})});
  const list=()=>{mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor Presets</h3><div class="small">Verwalte deine Spiel- und Plattforminfos.</div></div><button class="secondary" id="pluginSettingsClose">Schließen</button></div><div class="btnLine"><button id="infoNew">Preset anlegen</button></div><div class="infoPresetList">${presets.map((preset,index)=>`<div class="infoPresetRow"><b>${esc(preset.name||'Unbenannt')}</b><div class="btnLine"><button class="infoSendPreset" data-preset="${index}">Senden</button><button class="secondary infoEditPreset" data-preset="${index}">Bearbeiten</button><button class="secondary infoDeletePreset" data-preset="${index}">Löschen</button></div></div>`).join('')||'<div class="small">Noch keine Presets angelegt.</div>'}</div><div class="small" id="infoResult"></div></section>`;$('#pluginSettingsClose',mount).onclick=()=>mount.innerHTML='';$('#infoNew',mount).onclick=()=>editor({id:`preset_${Date.now()}`,name:'Neues Preset',platforms:{}},-1);$$('.infoSendPreset',mount).forEach(button=>button.onclick=async()=>{const out=await send(presets[Number(button.dataset.preset)]);$('#infoResult',mount).textContent=out.ok?'Sendevorgang gestartet.':'Fehler: '+(out.error||'?')});$$('.infoEditPreset',mount).forEach(button=>button.onclick=()=>editor(structuredClone(presets[Number(button.dataset.preset)]),Number(button.dataset.preset)));$$('.infoDeletePreset',mount).forEach(button=>button.onclick=async()=>{presets.splice(Number(button.dataset.preset),1);const out=await save();if(out.ok)list();else $('#infoResult',mount).textContent='Fehler: '+(out.error||'?')});};
  const editor=(preset,index)=>{preset.platforms=preset.platforms||{};const blocks=Object.entries(fields).map(([platform,rows])=>{const d=preset.platforms[platform]||{};const locked=platform==='tiktok';return `<section class="infoPlatform"><div class="infoPlatformHead"><h3>${esc(platform)}</h3><label><input type="checkbox" data-info="${platform}.enabled" ${d.enabled?'checked':''} ${locked?'disabled':''}> ${locked?'Noch nicht sendbar':'Beim Senden aktiv'}</label></div><div class="platformForm">${rows.map(([key,label])=>`<label><div>${esc(label)}</div>${key==='description'?`<textarea data-info="${platform}.${key}" ${locked?'disabled':''}>${esc(locked?'TikTok wird aktuell nicht unterstützt.':d[key]||'')}</textarea>`:`<input data-info="${platform}.${key}" value="${esc(d[key]||'')}" ${locked?'disabled':''}>`}</label>`).join('')}</div></section>`}).join('');mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>${index<0?'Preset anlegen':'Preset bearbeiten'}</h3><div class="small">Titel, Kategorie und Aktivierung je Plattform festlegen.</div></div><button class="secondary" id="infoBack">Zurück</button></div><div class="platformForm"><label><div>Presetname</div><input id="infoName" value="${esc(preset.name||'')}"></label></div>${blocks}<div class="btnLine"><button id="infoSave">Preset speichern</button><span class="small" id="infoResult"></span></div></section>`;$('#infoBack',mount).onclick=list;$('#infoSave',mount).onclick=async()=>{preset.name=$('#infoName',mount).value.trim()||'Neues Preset';$$('[data-info]',mount).forEach(input=>{const [platform,key]=input.dataset.info.split('.');preset.platforms[platform]=preset.platforms[platform]||{};preset.platforms[platform][key]=input.type==='checkbox'?input.checked:input.value.trim();});preset.platforms.tiktok.enabled=false;if(index<0)presets.push(preset);else presets[index]=preset;const out=await save();if(out.ok)list();else $('#infoResult',mount).textContent='Fehler: '+(out.error||'?')};};
  list();
}
async function openPluginSettings(pluginId){
  const mount=$("#pluginSettingsMount");
  if(!mount) return;
  mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Settings laden...</h3></section>`;
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Settings</h3><div class="warnBox">${esc(d.error||"Konnte Settings nicht laden")}</div></section>`;return;}
  if(pluginId==="info3ditor"){openInfo3ditorSettings(mount,d.values||{});return;}
  let schema=d.schema||[];
  const values=d.values||{};
  schema=await enrichPluginSchema(pluginId,schema,values);
  const tabs=[...new Set(schema.map(schemaTab))];
  const groups=tabs.length?tabs:["Allgemein"];
  const tabButtons=groups.map((tab,i)=>`<button type="button" class="pluginSettingsTabBtn ${i===0?"active":""}" data-tab="${esc(tab)}">${esc(tab)}</button>`).join("");
  const body=groups.map((tab,i)=>`<div class="pluginSettingsGroup ${i===0?"active":""}" data-tab="${esc(tab)}"><div class="pluginSettingsFields">${schema.filter(f=>schemaTab(f)===tab || (!tabs.length&&true)).map(f=>renderPluginField(f,values)).join("")}</div></div>`).join("");
  mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>${esc(d.plugin_id)} Settings</h3><div class="small">Wird in data/settings.json unter plugins/${esc(d.plugin_id)} gespeichert und danach neu gestartet.</div></div><button type="button" class="secondary" id="pluginSettingsClose">Schließen</button></div>${groups.length>1?`<div class="pluginSettingsTabs">${tabButtons}</div>`:""}<form id="pluginSettingsForm">${body||"<div class='small'>Dieses Plugin hat kein Settings-Schema.</div>"}<div class="btnLine"><button type="submit">Speichern & neu starten</button><button type="button" class="secondary" id="pluginSettingsCancel">Abbrechen</button><span class="small" id="pluginSettingsResult"></span></div></form></section>`;
  $("#pluginSettingsClose").onclick=()=>mount.innerHTML="";
  $("#pluginSettingsCancel").onclick=()=>mount.innerHTML="";
  $$(".pluginSettingsTabBtn", mount).forEach(btn=>btn.onclick=()=>{
    const tab=btn.dataset.tab;
    $$(".pluginSettingsTabBtn", mount).forEach(b=>b.classList.toggle("active", b===btn));
    $$(".pluginSettingsGroup", mount).forEach(g=>g.classList.toggle("active", g.dataset.tab===tab));
  });
  initPluginEnhancedFields($("#pluginSettingsForm"));
  applyPluginSettingsVisibility($("#pluginSettingsForm"));
  $$(".pluginActionBtn", $("#pluginSettingsForm")).forEach(btn=>btn.onclick=async()=>{
    const form=$("#pluginSettingsForm");
    const result=$("#pluginSettingsResult");
    result.textContent="Führe Aktion aus...";
    const values=collectPluginSettings(form,schema);
    const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/action`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:btn.dataset.key,values})});
    result.textContent=out.ok?(out.detail||"Aktion ausgeführt."):`Fehler: ${out.error||out.detail||"Aktion fehlgeschlagen"}`;
  });
  $("#pluginSettingsForm").onsubmit=async(ev)=>{
    ev.preventDefault();
    const result=$("#pluginSettingsResult");
    result.textContent="Speichere...";
    const values=collectPluginSettings(ev.currentTarget,schema);
    const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values})});
    result.textContent=out.ok?"Gespeichert und neu gestartet.":`Fehler: ${out.error||"unbekannt"}`;
    if(out.ok) setTimeout(()=>{ mount.innerHTML=""; renderPlugins(); },700);
  };
  mount.scrollIntoView({behavior:"smooth",block:"start"});
}
async function togglePluginEnabled(pluginId, enabled){
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){alert(d.error||"Konnte Plugin-Settings nicht laden");return;}
  const values={...(d.values||{}),enabled:!!enabled};
  const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values})});
  if(!out.ok){alert(out.error||"Plugin konnte nicht umgeschaltet werden");return;}
  setTimeout(renderPlugins,500);
}
async function restartPlugin(pluginId){
  const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/restart`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
  if(!out.ok){alert(out.error||"Plugin konnte nicht neu gestartet werden");return;}
  setTimeout(renderPlugins,500);
}
async function renderEasyslider(){
  const settings=normalizeEasysliderClient(((await api("/api/settings")).ui||{})["3asyslid3r"]);
  shell("easyslider","3asyslid3r","Schnellleiste am Fensterrand.",`
    <section class="card easysliderSettings">
      <form id="easysliderForm" class="platformForm">
        <label><div>Aktiv</div><select name="enabled"><option value="true" ${settings.enabled?"selected":""}>Ja</option><option value="false" ${!settings.enabled?"selected":""}>Nein</option></select></label>
        <label><div>Bildschirmrand</div><select name="edge">${[["left","Links"],["right","Rechts"],["top","Oben"],["bottom","Unten"]].map(([v,l])=>`<option value="${v}" ${settings.edge===v?"selected":""}>${l}</option>`).join("")}</select></label>
        <label><div>Sekunden bis offen</div><input name="delaySeconds" type="number" min="0" max="120" step="0.5" value="${esc(settings.delaySeconds)}"></label>
        <label><div>Transparenz</div><input name="opacity" type="range" min="0" max="100" value="${esc(settings.opacity)}"></label>
        <div class="hint">PNG-Ordner: assets\\pics\\3asyslid3r</div>
      </form>
    </section>
    <section class="card easysliderSettings">
      <h3>Buttons</h3>
      <div id="easysliderButtons" class="easysliderButtonList"></div>
      <div class="btnLine"><button id="easysliderSave" type="button">Speichern</button><button id="easysliderTest" type="button" class="secondary">Dashboard testen</button><span id="easysliderResult" class="small"></span></div>
    </section>`);
  const form=$("#easysliderForm");
  const defaults=defaultEasysliderSettings().buttons;
  const byId=new Map((settings.buttons||[]).map(b=>[b.id,b]));
  const buttons=defaults.map(d=>({...d,...(byId.get(d.id)||{})}));
  $("#easysliderButtons").innerHTML=buttons.map((b,i)=>`<label class="easysliderButtonRow"><input type="checkbox" data-index="${i}" ${b.enabled!==false?"checked":""}><div><b>${esc(b.label)}</b><span>${esc(b.path)}</span></div><img src="/slider-asset/${encodeURIComponent(b.id)}.png?v=${encodeURIComponent(window.WEB_VERSION||"")}" alt="" onerror="this.remove()"></label>`).join("");
  const collect=()=>normalizeEasysliderClient({
    enabled:form.elements.enabled.value==="true",
    edge:form.elements.edge.value,
    delaySeconds:Number(form.elements.delaySeconds.value)||0,
    opacity:Number(form.elements.opacity.value)||0,
    buttons:buttons.map((b,i)=>({...b,enabled:$(`input[data-index="${i}"]`,$("#easysliderButtons")).checked}))
  });
  $("#easysliderSave").onclick=async()=>{
    const result=$("#easysliderResult");
    result.textContent="Speichere...";
    const out=await api("/api/3asyslid3r/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(collect())});
    result.textContent=out.ok?"Gespeichert.":`Fehler: ${out.error||"unbekannt"}`;
    if(out.ok){settingsCache=null;}
  };
  $("#easysliderTest").onclick=async()=>{
    await api("/api/3asyslid3r/activate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:"/"}),timeoutMs:2500});
    location.href="/";
  };
}
async function renderPlugins(){
  const s=await api("/api/status");
  const cards=(s.plugins||[]).map(p=>`<section class="card pluginCard"><div class="pluginHead"><h3>${esc(p.name)}</h3><span class="pluginState ${pluginStateClass(p.state)}">${esc(p.state||"ready")}</span></div><div class="small">${esc(p.description||"")}</div><div class="small pluginStatusText">${esc(p.status||p.message||"Bereit")}</div><div class="btnLine"><button type="button" class="pluginSettingsBtn" data-plugin="${esc(p.id)}">Settings</button><a class="btn secondary" href="/dev" title="Logs im DEV-Bereich prüfen">Logs</a></div></section>`).join("");
  shell("plugins","Plugins","Hier stellst du jedes gefundene Plugin direkt ein. Der alte nutzlose Bereit-Button ist weg.",`<div id="pluginSettingsMount"></div><div class="pluginGrid">${cards}</div>`);
  $$(".pluginSettingsBtn").forEach(b=>b.onclick=()=>openPluginSettings(b.dataset.plugin));
}
function addPluginToggleButtons(plugins){
  $$(".pluginSettingsBtn").forEach(btn=>{
    const p=(plugins||[]).find(x=>String(x.id)===String(btn.dataset.plugin));
    if(!p || btn.parentElement?.querySelector(".pluginToggleBtn")) return;
    const toggle=document.createElement("button");
    toggle.type="button";
    toggle.className=`pluginToggleBtn ${p.enabled?"disable":"enable"}`;
    toggle.textContent=p.enabled?"Deaktivieren":"Aktivieren";
    toggle.onclick=()=>togglePluginEnabled(p.id,!p.enabled);
    btn.parentElement?.insertBefore(toggle,btn);
    const restart=document.createElement("button");
    restart.type="button";
    restart.className="pluginRestartBtn secondary";
    restart.textContent="Restart";
    restart.onclick=()=>restartPlugin(p.id);
    btn.parentElement?.insertBefore(restart,btn);
  });
}
const renderPluginsWithoutToggle=renderPlugins;
renderPlugins=async function(){
  await renderPluginsWithoutToggle();
  const s=await api("/api/status");
  addPluginToggleButtons(s.plugins||[]);
  try{
    const wanted=new URLSearchParams(location.search).get("plugin");
    if(wanted) setTimeout(()=>openPluginSettings(wanted),150);
  }catch(_){}
};
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
      <div class="devLogFilters"><select id="devLogLevel"><option value="all">Alle Level</option><option value="error">Fehler</option><option value="warning">Warnungen</option><option value="status">Status</option><option value="metric">Metriken</option><option value="info">Info</option></select><input id="devLogSearch" type="search" placeholder="Log durchsuchen"></div>
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
  let devLogLevel="all";
  let devLogSearch="";
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
    const level=devLogLevel;
    const search=devLogSearch;
    const query=`?scope=${encodeURIComponent(requested.scope)}&id=${encodeURIComponent(requested.id)}&level=${encodeURIComponent(level)}&q=${encodeURIComponent(search)}`;
    const d=await api("/api/dev/log"+query);
    if(requestId!==devLogRequest||requested.scope!==devLogFilter.scope||requested.id!==devLogFilter.id||level!==devLogLevel||search!==devLogSearch)return;
    if(d && d.error){ box.value=`Log laden fehlgeschlagen: ${d.error}`; return; }
    box.value=d.log||"";
    $("#devLogMeta").textContent=`${requested.label} · ${d.level||"all"}${d.search?" · Suche: "+d.search:""} · ${d.lines||0} Zeilen · ${formatBytes(d.bytes)} gesamt · bereinigte Anzeige · ${new Date().toLocaleTimeString()}`;
    if(!keepPosition||atBottom) box.scrollTop=box.scrollHeight;
  };
  $("#devLogLevel").onchange=()=>{devLogLevel=$("#devLogLevel").value||"all";refreshLog();};
  $("#devLogSearch").oninput=()=>{devLogSearch=$("#devLogSearch").value.trim();refreshLog();};
  $("#devRefresh").onclick=()=>{refreshInfo();refreshLog();};
  $("#devCopy").onclick=async()=>{await navigator.clipboard.writeText($("#devLog").value);$("#devCopy").textContent="Kopiert";setTimeout(()=>$("#devCopy").textContent="Log kopieren",1500);};
  $("#devClear").onclick=async()=>{if(!confirm("Logdatei wirklich leeren?"))return;await api("/api/dev/log/clear",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});await refreshLog();};
  $$(".devEvent").forEach(b=>b.onclick=async()=>{await api("/api/dev/log/event",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({level:b.dataset.level,message:`Manueller ${b.dataset.level}-Test aus der DEV-Seite`})});await refreshLog();});
  await refreshInfo(); await refreshLog();
  setInterval(()=>{if($("#devAutoRefresh")?.checked){refreshInfo();refreshLog(true);}},2000);
}
async function bootPage(){
  try{
    await (({dashboard:renderDashboard,platforms:renderPlatforms,chat:renderChat,obs_meld:renderObsMeld,spotify:renderSpotify,easyslider:renderEasyslider,overlays:renderOverlays,plugins:renderPlugins,dev:renderDev}[page]||renderDashboard)());
  }catch(e){
    try{
      await api("/api/client-error",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({level:"error",message:String(e&&e.stack||e)})});
    }catch(_){}
    shell(page,"Fehler","Die Oberfläche läuft weiter; Details stehen im DEV-Log.",`<section class="card"><div class="warnBox">${esc(String(e&&e.message||e||"Unbekannter Fehler"))}</div><div class="btnLine"><button onclick="location.reload()">Neu laden</button><a class="btn secondary" href="/dev">DEV-Log</a></div></section>`);
  }
}
bootPage();
setInterval(()=>{
  if(page==="dashboard"||page==="chat") refreshMessages().catch(()=>{});
  if(page==="dashboard"||page==="spotify") refreshNowPlaying().catch(()=>{});
},2500);


// Main-UI heartbeat: dient nur noch zur Erkennung/Reparatur der Oberfläche.
// Der lokale Server darf davon niemals beendet werden. Es wird auch kein neuer
// Browser-Tab geöffnet: Reload passiert ausschließlich im bereits vorhandenen Tab.
let webbasedHeartbeatBusy = false;
let webbasedHeartbeatMisses = 0;
let webbasedLastReloadNonce = String(sessionStorage.getItem('webbasedLastReloadNonce') || '');
function webbasedReloadSameTab(nonce){
  const n = String(nonce || Date.now());
  if(webbasedLastReloadNonce === n) return;
  webbasedLastReloadNonce = n;
  try{ sessionStorage.setItem('webbasedLastReloadNonce', n); }catch(_){}
  const url = new URL(location.href);
  url.searchParams.set('reload', n);
  setTimeout(()=>{ location.replace(url.toString()); }, 250);
}
async function webbasedUiHeartbeat(){
  if(webbasedHeartbeatBusy) return;
  webbasedHeartbeatBusy = true;
  try{
    const r = await fetch('/api/ui-heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'});
    if(!r.ok) throw new Error('heartbeat '+r.status);
    const data = await r.json().catch(()=>({}));
    webbasedHeartbeatMisses = 0;
    if(data && data.navigate && data.navigate_path){
      const target = String(data.navigate_path || "/");
      const here = location.pathname + location.search;
      if(here !== target) location.href = target;
      return;
    }
    if(data && data.reload){
      webbasedReloadSameTab(data.reload_nonce);
      return;
    }
  }catch(_){
    webbasedHeartbeatMisses++;
    if(webbasedHeartbeatMisses >= 2){
      webbasedReloadSameTab('miss-'+Date.now());
    }
  }finally{
    webbasedHeartbeatBusy = false;
  }
}
webbasedUiHeartbeat();
setInterval(webbasedUiHeartbeat, 2500);
window.addEventListener('focus', webbasedUiHeartbeat);
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) webbasedUiHeartbeat(); });
