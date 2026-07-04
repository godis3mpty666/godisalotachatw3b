
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const page = $("#app")?.dataset.page || "dashboard";
let settingsCache = null;
let statusCache = null;
let internalNavigation = false;
let shutdownInProgress = false;
// Startup timing can be tuned here without editing the splash markup or CSS.
const STARTUP_SPLASH={minVisibleMs:3900,fadeInMs:1350,fadeOutMs:1200,videoPlaybackRate:.78};

function prepareStartupSplash(){
  const splash=$("#startupSplash");
  if(splash){
    splash.style.setProperty("--splash-fade-in",`${STARTUP_SPLASH.fadeInMs}ms`);
    splash.style.setProperty("--splash-fade-out",`${STARTUP_SPLASH.fadeOutMs}ms`);
  }
  const video=$("#startupKonterfei");
  if(!video)return;
  video.playbackRate=STARTUP_SPLASH.videoPlaybackRate;
  video.play().catch(()=>{});
}
async function finishStartupSplash(){
  const splash=$("#startupSplash");
  if(!splash)return;
  const elapsed=performance.now()-Number(window.STARTUP_SPLASH_STARTED||0);
  const remaining=Math.max(0,STARTUP_SPLASH.minVisibleMs-elapsed);
  if(remaining)await new Promise(resolve=>setTimeout(resolve,remaining));
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  splash.classList.add("isLeaving");
  await new Promise(resolve=>setTimeout(resolve,STARTUP_SPLASH.fadeOutMs+80));
  splash.remove();
}
prepareStartupSplash();

function persistMainWindowState(){
  if(page!=="dashboard")return;
  try{
    const state={
      x:Math.round(window.screenX),y:Math.round(window.screenY),
      width:Math.round(window.outerWidth),height:Math.round(window.outerHeight),
      maximized:window.outerWidth>=screen.availWidth-16&&window.outerHeight>=screen.availHeight-16,
    };
    navigator.sendBeacon("/api/ui-window-state",new Blob([JSON.stringify(state)],{type:"application/json"}));
  }catch(_){ }
}
window.addEventListener("beforeunload",persistMainWindowState);
const TESTER_CREDITS = [
  {name:"JunesGo",links:[
    {label:"Twitch",url:"https://www.twitch.tv/junesgo",icon:"twitch"}
  ]}
];

function nav(active){
  const items = [
    ["dashboard","Dashboard","/"],["platforms","Plattformen","/plattformen"],["chat","Chat","/chat"],["obs_meld","OBS/Meld Integration","/obs-meld-integration"],
    ["spotify","Spotis3mptify","/spotis3mptify"],["easyslider","3asyslid3r","/3asyslid3r"],["plugins","Plugins","/plugins"],["chattim3r","Chattim3r","/chattim3r"],["modalot","Modalot","/modalot"],["info3ditor","Info3ditor","/info3ditor"],["settings",L("Einstellungen","Settings"),"/einstellungen"],["dev","DEV","/dev"]
  ];
  const issueUrl = "https://github.com/godis3mpty666/godisalotachatw3b/issues/new?title=" + encodeURIComponent("[Feedback] ") + "&body=" + encodeURIComponent("**Was ist passiert oder was soll verbessert werden?**\n\n\n**So kann man es nachstellen (bei einem Bug):**\n1. \n2. \n\n**Version:** " + (window.WEB_VERSION || "unbekannt") + "\n\n**Zusätzliche Infos / Screenshots:**\n");
  const credits = [
    ["Twitch","https://twitch.tv/godis3mpty","twitch"],
    ["Discord","https://discord.gg/vtBuyrNtE","discord"],
    ["Ko-fi","https://ko-fi.com/godis3mpty","ko-fi"]
  ];
  const testers = TESTER_CREDITS.map(tester=>[tester.name,tester.links[0]?.url||"#",tester.links[0]?.icon||""]);
  return `<aside class="sidebar"><div class="brand"><div class="logo"></div><div><h1>godisalotachat</h1><div class="ver">Ver. ${window.WEB_VERSION}</div></div><div class="webbased">webbased</div></div><nav class="nav">${items.map(i=>`<a class="${active===i[0]?'active':''}" href="${i[2]}">${i[1]}</a>`).join("")}</nav><section class="credits" aria-label="Credits und Community"><div class="creditsLabel">Credits & Community</div><div class="creditsLinks">${credits.map(i=>`<a class="externalBrowserLink" href="${i[1]}" target="_blank" rel="noopener noreferrer"><img src="/platform-icon/${i[2]}" alt=""><span>${i[0]}</span><span class="externalArrow" aria-hidden="true">↗</span></a>`).join("")}</div><button type="button" class="testersButton" id="openTesters"><img src="/platform-icon/twitch" alt=""><span>${L("Tester","Testers")}</span></button><a class="feedbackLink externalBrowserLink" href="${issueUrl}" target="_blank" rel="noopener noreferrer"><span class="feedbackIcon" aria-hidden="true">!</span><span><b>Feedback senden</b><small>Bug oder Idee auf GitHub</small></span><span class="externalArrow" aria-hidden="true">↗</span></a></section></aside><div class="testersModal" id="testersModal" hidden><div class="testersBackdrop" data-close-testers></div><section class="testersDialog" role="dialog" aria-modal="true" aria-labelledby="testersTitle"><div class="testersHead"><div><div class="creditsLabel">Credits</div><h2 id="testersTitle">${L("Tester","Testers")}</h2></div><button type="button" class="secondary" data-close-testers>${L("SchlieÃŸen","Close")}</button></div><div class="testersList">${testers.map(i=>`<a class="testerEntry externalBrowserLink" href="${i[1]}" target="_blank" rel="noopener noreferrer"><img src="/platform-icon/${i[2]}" alt="Twitch"><span><b>${i[0]}</b><small>twitch.tv/${i[0].toLowerCase()}</small></span><span class="externalArrow" aria-hidden="true">↗</span></a>`).join("")}</div></section></div>`;
}
function shell(active, title, sub, body){
  $("#app").innerHTML = `<div class="layout">${nav(active)}<main class="content"><div class="top"><div><h2>${title}</h2><div class="sub">${sub||""}</div></div><div class="topActions"><label class="languagePicker"><span>Sprache</span><select id="appLanguage" aria-label="Sprache"><option value="de" data-i18n-skip>Deutsch</option><option value="en" data-i18n-skip>English</option></select></label><button type="button" id="shutdownApp" class="shutdownBtn" title="EXE schließen">Beenden</button></div></div>${body}</main></div>`;
  const languageSelect=$("#appLanguage");
  if(languageSelect){
    languageSelect.value=window.APP_LANGUAGE==="en"?"en":"de";
    languageSelect.onchange=async()=>{
      languageSelect.disabled=true;
      const result=await api("/api/language",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({language:languageSelect.value})});
      if(result.ok) location.reload(); else {languageSelect.disabled=false;alert(result.error||"Sprache konnte nicht gespeichert werden.");}
    };
  }
  wireShutdownButton();
  wireTestersModal();
}
function wireTestersModal(){
  const modal=$("#testersModal"),open=$("#openTesters");
  if(!modal||!open)return;
  const buttonIcon=$("img",open);if(buttonIcon)buttonIcon.remove();
  const list=$(".testersList",modal);
  if(list)list.innerHTML=TESTER_CREDITS.map(tester=>`<div class="testerEntry"><b>${esc(tester.name)}</b><div class="testerLinks">${tester.links.map(link=>`<a class="testerPlatformLink externalBrowserLink" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer" title="${esc(link.label)}" aria-label="${esc(tester.name)} auf ${esc(link.label)}"><img src="/platform-icon/${encodeURIComponent(link.icon)}" alt="${esc(link.label)}"></a>`).join("")}</div></div>`).join("");
  const close=()=>{modal.hidden=true;document.body.classList.remove("modalOpen");open.focus();};
  open.onclick=()=>{modal.hidden=false;document.body.classList.add("modalOpen");const button=$("button[data-close-testers]",modal);if(button)button.focus();};
  $$('[data-close-testers]',modal).forEach(button=>button.onclick=close);
  modal.onkeydown=event=>{if(event.key==="Escape")close();};
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
  if(a.classList.contains("externalBrowserLink")){
    ev.preventDefault();
    openExternal(a.href);
    return;
  }
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
function L(de,en){return window.APP_LANGUAGE==="en"?en:de;}
function LT(value){return window.t?window.t(String(value??"")):String(value??"");}
function localizedStatusValue(value, fallback="not_connected"){
  const raw=String(value||fallback).trim().toLowerCase().replace(/[ _-]+/g," ");
  const key=({
    "verbunden":"connected","connected":"connected","running":"connected",
    "verbindet":"connecting","connecting":"connecting","starting":"connecting",
    "bereit":"ready","ready":"ready",
    "wartet":"waiting","waiting":"waiting","watching":"waiting",
    "inaktiv":"inactive","inactive":"inactive","disabled":"inactive","deaktiviert":"inactive",
    "aktiv":"active","active":"active",
    "getrennt":"disconnected","disconnected":"disconnected","stopped":"disconnected",
    "nicht verbunden":"not_connected","not connected":"not_connected",
    "fehler":"error","error":"error","failed":"error",
  }[raw]||fallback);
  return ({connected:L("Verbunden","Connected"),connecting:L("Verbindet...","Connecting..."),ready:L("Bereit","Ready"),waiting:L("Wartet","Waiting"),inactive:L("Inaktiv","Inactive"),active:L("Aktiv","Active"),disconnected:L("Getrennt","Disconnected"),error:L("Fehler","Error"),not_connected:L("Nicht verbunden","Not connected")}[key]||String(value||""));
}
function localizedStatusDetail(value){
  let text=String(value||"").trim();
  if(!text)return "";
  const pairs=window.APP_LANGUAGE==="en"?[
    [/\bMain fehlt(?:\/ungültig)?\b/gi,"Main missing"],[/\bBot fehlt(?:\/ungültig)?\b/gi,"Bot missing"],
    [/\bkein OAuth gespeichert\b/gi,"no OAuth saved"],[/\bOAuth gespeichert\b/gi,"OAuth saved"],
    [/\bnicht verbunden\b/gi,"not connected"],[/\bverbunden\b/gi,"connected"],[/\bgetrennt\b/gi,"disconnected"],
    [/\bfehlt\b/gi,"missing"],[/\bungültig\b/gi,"invalid"],[/\bgespeichert\b/gi,"saved"],[/\bbereit\b/gi,"ready"],
  ]:[
    [/YouTube OAuth OK[^\p{L}\p{N}]*waiting for active livestream chat/giu,"YouTube OAuth OK · wartet auf aktiven Livestream-Chat"],
    [/Reading YouTube live chat via web fallback/gi,"Liest den YouTube-Livechat über den Web-Fallback"],
    [/Reading YouTube live chat/gi,"Liest den YouTube-Livechat"],[/YouTube chat stopped\.?/gi,"YouTube-Chat gestoppt"],
    [/Watching for live start/gi,"Wartet auf den Livestream-Start"],[/Watching\s+(#[^|]+)(\s*\|\s*live=)/gi,"Beobachtet $1$2"],[/Watching\s+(#[^|]+)/gi,"Beobachtet $1"],
    [/Waiting for dashboard/gi,"Wartet auf das Dashboard"],[/Starting/gi,"Wird gestartet"],
    [/Reading\s+(#[^ ]+)\s+as\s+([^·|]+)/gi,"Liest $1 als $2"],[/Reading\s+(@?[^·|]+)/gi,"Liest $1"],
    [/Reconnecting to\s+/gi,"Verbindet erneut mit "],[/Connecting to\s+/gi,"Verbindet mit "],
    [/Waiting for main OBS connection/gi,"Wartet auf die OBS-Hauptverbindung"],[/OBS not connected in main tool/gi,"OBS ist im Haupttool nicht verbunden"],
    [/Meld disabled in platforms/gi,"Meld ist unter Plattformen deaktiviert"],[/Auto connect disabled/gi,"Automatische Verbindung deaktiviert"],
    [/Meld connect failed/gi,"Meld-Verbindung fehlgeschlagen"],[/Meld disconnected/gi,"Meld getrennt"],
    [/Meld is not connected/gi,"Meld ist nicht verbunden"],[/Disconnected/gi,"Getrennt"],
    [/TikTok reading disabled in Platforms/gi,"TikTok-Lesen ist unter Plattformen deaktiviert"],
    [/(@[^ ]+) is currently offline\.?/gi,"$1 ist derzeit offline"],[/(@[^ ]+) stream ended\.?/gi,"Stream von $1 beendet"],
    [/IRC stopped\.?/gi,"IRC gestoppt"],[/Idle\s*\/\s*hidden/gi,"Leerlauf / ausgeblendet"],[/Visible:/gi,"Sichtbar:"],
    [/\blive=false\b/gi,"live=nein"],[/\blive=true\b/gi,"live=ja"],[/\blive=unknown\b/gi,"live=unbekannt"],
    [/timed out/gi,"Zeitüberschreitung"],[/timeout/gi,"Zeitüberschreitung"],
    [/\bMain missing\b/gi,"Hauptkonto fehlt"],[/\bBot missing\b/gi,"Bot fehlt"],
    [/\bno OAuth saved\b/gi,"kein OAuth gespeichert"],[/\bOAuth saved\b/gi,"OAuth gespeichert"],
    [/\bnot connected\b/gi,"nicht verbunden"],[/\bconnected\b/gi,"verbunden"],[/\bdisconnected\b/gi,"getrennt"],
    [/\bmissing\b/gi,"fehlt"],[/\binvalid\b/gi,"ungültig"],[/\bsaved\b/gi,"gespeichert"],[/\bready\b/gi,"bereit"],
    [/\bMain\b/g,"Hauptkonto"],
  ];
  for(const [pattern,replacement] of pairs)text=text.replace(pattern,replacement);
  return LT(text);
}
function localizedPlatformStatus(cfg,includeDetail=true){
  const state=localizedStatusValue(cfg?.status,cfg?.enabled===false?"inactive":"not_connected");
  let detail=includeDetail?localizedStatusDetail(cfg?.detail):"";
  if(includeDetail&&cfg&&(cfg.main_status||cfg.bot_status)&&/\b(?:Main|Hauptkonto|Bot)\b/i.test(String(cfg.detail||""))){
    const mainOk=String(cfg.main_status||"").toLowerCase()==="verbunden";
    const botOk=String(cfg.bot_status||"").toLowerCase()==="verbunden";
    detail=`${L("Hauptkonto","Main")} ${mainOk?"OK":L("fehlt","missing")} · Bot ${botOk?"OK":L("fehlt","missing")}`;
  }
  return detail&&detail.toLocaleLowerCase()!==state.toLocaleLowerCase()?`${state} · ${detail}`:state;
}
function localizedPluginStatus(plugin){
  const state=String(plugin.state||"").toLowerCase();
  const label=localizedStatusValue(state||"ready","ready");
  const message=localizedStatusDetail(plugin.message||"").trim();
  return message?`${label} - ${message}`:label;
}
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
  {id:"modalot",label:"Modalot",path:"/modalot",enabled:true},
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
  return {enabled:cfg.enabled!==false,edge,delaySeconds:delay,opacity,buttons:buttons.map(b=>{const id=String(b.id||"").trim()||"dashboard";let path=String(b.path||"/").trim()||"/";if(id==="modalot"&&path==="/plugins?plugin=modalot")path="/modalot";return {id,label:String(b.label||b.id||"Dashboard").trim(),path,enabled:b.enabled!==false};})};
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
  return localizedStatusValue(cfg.status,cfg.enabled?"ready":"inactive");
}
function platformAccountDetails(cfg){
  const platformConnected = cfg.status === "verbunden";
  const mainConnected = platformConnected && (cfg.main_status === "verbunden" || (!cfg.main_status && !cfg.bot_status));
  const botConnected = platformConnected && cfg.bot_status === "verbunden";
  const mainName = cfg.main || cfg.main_account || cfg.channel || cfg.unique_id || cfg.main_username || cfg.main_channel_title || "";
  const botName = cfg.bot || cfg.bot_account || cfg.bot_username || cfg.username || cfg.bot_channel_title || "";
  const rows = [];
  if(mainName) rows.push(`${L("Hauptkonto","Main")}: ${esc(mainName)}${mainConnected ? "" : ` · ${L("nicht verbunden","not connected")}`}`);
  if(botName) rows.push(`Bot: ${esc(botName)}${botConnected ? "" : ` · ${L("nicht verbunden","not connected")}`}`);
  return rows.length ? rows.join("<br>") : L("Keine Konten eingetragen","No accounts entered");
}
function card(p,cfg){
  const st = cfg.status || "nicht verbunden";
  const ok = st==="verbunden";
  const label = statusLabel(cfg);
  let details = "";
  if(p==="tiktok"||p==="twitch"||p==="youtube"||p==="kick") details = platformAccountDetails(cfg);
  else if(p==="spotify") details = ``;
  else if(p==="openai") details = cfg.detail ? esc(localizedStatusDetail(cfg.detail)) : (cfg.status==="verbunden" ? L("API-Key gespeichert","API key saved") : L("OpenAI API-Key fehlt","OpenAI API key missing"));
  else if(p==="meld") details = cfg.detail ? esc(localizedStatusDetail(cfg.detail)) : ``;
  else if(p==="obs") details = cfg.detail ? esc(localizedStatusDetail(cfg.detail)) : ``;
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
  else if(details && (p === "meld" || p === "obs" || p === "openai")) details.textContent = localizedStatusDetail(cfg.detail || "");
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
  $("#plugMini").innerHTML = status.plugins.slice(0,6).map(x=>`<div class="msg"><b>${esc(x.name)}</b><div class="small">${esc(localizedPluginStatus(x))}</div></div>`).join("");
  if(((status.platforms || {}).tiktok || {}).status !== "verbunden") startTikTokDashboardPoll();
  if(((status.platforms || {}).youtube || {}).status !== "verbunden") startYoutubeDashboardPoll();
  if(((status.platforms || {}).meld || {}).status !== "verbunden") startMeldDashboardPoll();
  if(((status.platforms || {}).obs || {}).status !== "verbunden") startObsDashboardPoll();
}
async function refreshDashboardPluginStatuses(){
  if(page!=="dashboard")return;
  const box=$("#plugMini");
  if(!box)return;
  try{
    const status=await api("/api/status");
    box.innerHTML=(status.plugins||[]).slice(0,6).map(x=>`<div class="msg"><b>${esc(x.name)}</b><div class="small">${esc(localizedPluginStatus(x))}</div></div>`).join("");
  }catch(_){ }
}
async function loadDashboardUrls(){
  const box=$("#dashUrls"); if(!box)return;
  const data=await api("/api/overlay-urls");
  const rt=await api("/api/runtime");
  const warn=rt.port_warning ? `<div class="warnBox">${esc(rt.port_warning)}<br><b>Spotify Redirect URI:</b><div class="urlBox">${esc(rt.spotify_redirect_uri)}</div></div>` : "";
  box.innerHTML=warn+(data.main||[]).map(i=>`<div class="urlMini"><b>${esc(LT(i.name))}</b><div class="urlBox">${esc(i.url)}</div></div>`).join("");
}
async function refreshMessages(){
  const m=await api("/api/messages");
  const el=$("#messages"); if(!el)return;
  const showModeration=page==="dashboard"||page==="chat";
  const moderation=(x)=>!showModeration||!["twitch","kick","youtube"].includes(x.platform)||x.source_plugin_id==="modalot"?"":`<span class="dashboardModActions"><button type="button" class="dashboardModAction ban" data-action="ban" data-platform="${esc(x.platform)}" data-user="${esc(x.user)}" data-author-channel-id="${esc(x.author_channel_id||"")}" data-live-chat-id="${esc(x.live_chat_id||"")}" title="${L(`${esc(x.user)} auf ${esc(x.platform)} bannen`,`Ban ${esc(x.user)} on ${esc(x.platform)}`)}" aria-label="${L(`${esc(x.user)} bannen`,`Ban ${esc(x.user)}`)}"><img src="/platform-icon/banhammer" alt=""></button><button type="button" class="dashboardModAction unban" data-action="unban" data-platform="${esc(x.platform)}" data-user="${esc(x.user)}" data-author-channel-id="${esc(x.author_channel_id||"")}" data-live-chat-id="${esc(x.live_chat_id||"")}" title="${L(`${esc(x.user)} auf ${esc(x.platform)} freigeben`,`Unban ${esc(x.user)} on ${esc(x.platform)}`)}" aria-label="${L(`${esc(x.user)} freigeben`,`Unban ${esc(x.user)}`)}"><img src="/platform-icon/unban" alt=""></button></span>`;
  el.innerHTML=(m.messages||[]).filter(x=>x.message_type==="chat"||x.message_type==="moderation_notice").map(x=>showModeration?`<div class="msg dashboardChatMsg">${platformBadge(x.platform)}${moderation(x)} <b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: <span class="dashboardChatText">${x.html||esc(x.text)}</span></div>`:`<div class="msg">${platformBadge(x.platform)} <span class="small">${esc(x.time)}</span> · <b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: ${x.html||esc(x.text)}</div>`).join("");
  el.onclick=async ev=>{const button=ev.target.closest?.(".dashboardModAction");if(!button||button.disabled)return;const action=button.dataset.action,platform=button.dataset.platform,user=button.dataset.user;button.disabled=true;const out=await api("/api/dashboard/moderation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,platform,user,author_channel_id:button.dataset.authorChannelId||"",live_chat_id:button.dataset.liveChatId||""})});button.disabled=false;if(!out.ok)alert(out.error||out.detail||L("Moderationsaktion fehlgeschlagen","Moderation action failed"));};
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
  return `<button type="button" class="btn devBtn" data-url="${esc(href)}" title="${L("Öffnet die Entwicklerkonsole","Opens the developer console")}">${L("Entwicklerseite","Developer page")}</button>`;
}
function redirectField(platform,val){
  const href = DEV_LINKS[platform] || "#";
  return `<label class="redirectWithDev"><div>Redirect URI</div><div class="inlineField"><input name="redirect_uri" type="text" value="${esc(val||"")}" autocomplete="on" autocapitalize="off" spellcheck="false"><button type="button" class="btn devBtn" data-url="${esc(href)}">${L("Entwicklerseite","Developer page")}</button></div></label>`;
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
function sel(name,label,val){return `<label><div>${label}</div><select name="${name}"><option value="false" ${!val?'selected':''}>${L("Nein","No")}</option><option value="true" ${val?'selected':''}>${L("Ja","Yes")}</option></select></label>`;}
function platformForm(p,cfg){
  const enabled=sel("enabled",L("Aktiv","Active"),cfg.enabled), auto=sel("autoconnect",L("Automatisch verbinden","Autoconnect"),cfg.autoconnect ?? true);
  const status=(detail=true)=>`<span class="small">${L("Status","Status")}: ${esc(localizedPlatformStatus(cfg,detail))}</span>`;
  if(p==="tiktok") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("main",L("Hauptkonto/Kanal","Main/Channel"),cfg.main)}${field("bot",L("Botkonto","Bot account"),cfg.bot)}<div class="platformSubBox"><b>${L("Testkanal / fremden Livestream lesen","Read test channel / external livestream")}</b><div class="testChannelFields">${sel("test_channel_enabled",L("Testkanal aktiv","Test channel active"),cfg.test_channel_enabled ?? false)}${field("test_channel",L("Testkanal ohne @","Test channel without @"),cfg.test_channel || "")}</div><div class="hint testChannelHint">${L("Wenn aktiviert, liest das TikTok-Chatplugin Chat, Beitritte, Likes, Geschenke, Follows und Shares aus diesem Kanal. Damit kannst du Warnungen testen, ohne mit deinem eigenen Konto live zu gehen. Der angegebene Kanal muss gerade live sein.","When enabled, the TikTok chat plugin reads chat, joins, likes, gifts, follows and shares from this channel. This lets you test alerts without going live on your own account. The specified channel must currently be live.")}</div></div><div class="hint">${L("TikTok verwendet getrennte gespeicherte Browserprofile für Hauptkonto und Bot. Es gibt keine Redirect-URL. Beim Anmelden öffnet sich die TikTok-Anmeldeseite, auf der du dich beispielsweise per QR-Code anmelden kannst.","TikTok uses separate saved browser profiles for the main account and bot. There is no redirect URL. Signing in opens the TikTok login page, where you can sign in using a QR code, for example.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="btn tiktokLogin" data-account="main">${L("Hauptkonto anmelden","Sign in main")}</button><button type="button" class="btn tiktokLogin" data-account="bot">${L("Bot anmelden","Sign in bot")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Hauptkonto trennen","Disconnect main")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">${L("Bot trennen","Disconnect bot")}</button>${status()}</div></form>`;
  if(p==="meld") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("host","Host",cfg.host||"127.0.0.1")}${field("port","Port",cfg.port||"13376")}<div class="hint">${L("Meld Studio benötigt keine Anmeldedaten. Es wird ausschließlich über einen lokalen WebSocket verbunden.","Meld Studio does not require login credentials. It connects exclusively through a local WebSocket.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testMeld">${L("Verbindung testen","Test connection")}</button>${status()}</div></form>`;
  if(p==="obs") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("host","Host",cfg.host||"127.0.0.1")}${field("port","Port",cfg.port||"4455")}${field("password",L("Passwort","Password"),cfg.password,"password")}<div class="hint">${L("OBS-WebSocket-Standard:","OBS WebSocket default:")} <b>ws://127.0.0.1:4455</b>. ${L("In OBS muss der WebSocket-Server unter Werkzeuge > WebSocket-Servereinstellungen aktiviert sein.","In OBS, the WebSocket server must be enabled under Tools > WebSocket Server Settings.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testObs">${L("Verbindung testen","Test connection")}</button>${status()}</div></form>`;
  if(p==="spotify") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri||"http://127.0.0.1:5173/callback")}<div class="hint">${L("Spotify benötigt keinen Kontonamen. Die Redirect-URI kann manuell eingestellt werden und wird genau so für OAuth verwendet.","Spotify does not require an account name. The redirect URI can be configured manually and is used exactly as entered for OAuth.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><a class="btn login" data-platform="${p}" data-account="main" href="#">${L("Spotify anmelden","Sign in to Spotify")}</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Trennen","Disconnect")}</button>${devButton(p)}${status(false)}</div></form>`;
  if(p==="openai") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("api_key","API key",cfg.api_key,"password")}${field("organization",L("Organisations-ID (optional)","Organization ID (optional)"),cfg.organization)}${field("project",L("Projekt-ID (optional)","Project ID (optional)"),cfg.project)}<div class="hint">${L("Der API-Key wird lokal in data/settings.json gespeichert. Ein ChatGPT-Abonnement enthält nicht automatisch API-Guthaben. Beim Verbinden wird nur die Modellliste der offiziellen OpenAI-API abgerufen; es wird keine Antwort erzeugt. Das Modell wählst du im jeweiligen Plugin.","The API key is stored locally in data/settings.json. A ChatGPT subscription does not automatically include API credit. Connecting only retrieves the model list from the official OpenAI API; no response is generated. Select the model in the relevant plugin.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testOpenAI">${L("ChatGPT verbinden","Connect ChatGPT")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("ChatGPT trennen","Disconnect ChatGPT")}</button>${devButton(p)}${status()}</div></form>`;
  return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("main",L("Hauptkonto/Kanal","Main/Channel"),cfg.main)}${field("bot","Bot",cfg.bot)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri)}<div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><a class="btn login" data-platform="${p}" data-account="main" href="#">OAuth Main</a><a class="btn login" data-platform="${p}" data-account="bot" href="#">OAuth Bot</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Hauptkonto trennen","Disconnect main")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">${L("Bot trennen","Disconnect bot")}</button>${devButton(p)}${status(false)}</div></form>`;
}
async function renderPlatforms(){
  const {settings,status}=await loadAll(); const p=settings.platforms;
  shell("platforms",L("Plattformen","Platforms"),L("Anmeldedaten bleiben im Ordner webbased/data.","Login data remains in the webbased/data folder."),["twitch","tiktok","youtube","kick","spotify","openai","meld","obs"].map(k=>`<section class="card platformCard"><h3>${platformLabel(k)}</h3>${platformForm(k,{...(p[k]||{}),...(status.platforms[k]||{})})}</section>`).join(""));
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
      alert(L("Gespeichert","Saved"));
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
    alert((res.ok ? L("Verbunden: ","Connected: ") : L("Nicht verbunden: ","Not connected: ")) + (res.detail || ""));
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
    alert((res.ok ? L("Verbunden: ","Connected: ") : L("Nicht verbunden: ","Not connected: ")) + (res.detail || ""));
    location.reload();
  });
  $$(".testOpenAI").forEach(b=>b.onclick=async()=>{
    const form=b.closest("form");
    settingsCache = settingsCache || await api("/api/settings");
    settingsCache.platforms.openai = settingsCache.platforms.openai || {};
    applyFormValues(settingsCache.platforms.openai, form);
    await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsCache)});
    const res=await api("/api/test-platform/openai");
    alert((res.ok ? L("Verbunden: ","Connected: ") : L("Nicht verbunden: ","Not connected: ")) + (res.detail || ""));
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
    b.textContent = res.ok ? (res.already_logged_in ? L("Bereits angemeldet","Already signed in") : L("Anmeldefenster geöffnet","Login window opened")) : L("Öffnen fehlgeschlagen","Failed to open");
    setTimeout(()=>{ b.textContent = oldText; }, 3000);
    if(!res.ok) alert(res.error || L("TikTok konnte nicht geöffnet werden","Could not open TikTok"));
  });
  $$(".devBtn").forEach(b=>b.onclick=async()=>{
    const url = b.dataset.url || b.getAttribute("href") || "";
    const oldText = b.textContent;
    b.textContent = L("Geöffnet","Opened");
    const res = await openExternal(url);
    setTimeout(()=>{ b.textContent = oldText; }, 1800);
    if(!res.ok) alert(res.error || L("Entwicklerseite konnte nicht geöffnet werden","Could not open developer page"));
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
    if(!res.ok) alert(res.error || L("OAuth-Anmeldung konnte nicht geöffnet werden","Could not open OAuth login"));
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
  const values={tiktok:[["latest_follow",L("Neuester Follow","Latest follow")],["top_liker",L("Top-Liker","Top liker")],["top_gifter",L("Top-Gifter","Top gifter")],["latest_gift",L("Neuestes Geschenk","Latest gift")],["like_total",L("Like-Zähler","Like counter")]],twitch:[["latest_follow",L("Neuester Follow","Latest follow")],["latest_subscribe",L("Neuestes Abo","Latest subscription")],["latest_raid",L("Letzter Raid","Latest raid")],["latest_donation",L("Letzte Spende","Latest donation")],["latest_bits",L("Letzte Bits","Latest bits")]],youtube:[["latest_member",L("Neuestes Mitglied","Latest member")],["latest_superchat",L("Letzter Superchat","Latest Super Chat")]],kick:[["latest_follow",L("Neuester Follow","Latest follow")],["latest_subscribe",L("Neuestes Abo","Latest subscription")]]};
  const option=(items,selected="")=>items.map(([v,l])=>`<option value="${esc(v)}" ${v===selected?"selected":""}>${esc(l)}</option>`).join("");
  const targetOptions=Object.entries(targets).map(([key,value])=>[key,`${key.toUpperCase()}${value.connected?"":L(" (nicht verbunden)"," (not connected)")}`]);
  const actionLabels={text:L("Text schreiben","Write text"),show:L("Quelle einblenden","Show source"),hide:L("Quelle ausblenden","Hide source"),play:L("Quelle einmal abspielen","Play source once"),scene:L("Szene aktivieren","Activate scene")};
  const textActions=new Set(["text"]);
  const isTextRule=r=>textActions.has(String(r?.action||"text").toLowerCase());
  const isShowRule=r=>String(r?.action||"").toLowerCase()==="show";
  const isLikeCounterRule=r=>String(r?.platform||"").toLowerCase()==="tiktok"&&String(r?.value||"").toLowerCase()==="like_total";
  const savedLikeUsers=()=>[...new Set(rules.map(r=>String(r?.likeUser||r?.like_user||"").trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  const defaultPreview=r=>{
    const label=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value||L("Wert","Value");
    if(isLikeCounterRule(r))return `Test: ${String(r.likeUser||"Chatter")} · ${L("Intervall","Interval")} ${Number(r.likeThreshold||0)||1} Likes`;
    return `Test: ${label}`;
  };
  const localizedPreview=(r,value)=>{
    const raw=String(value||"");
    if(window.APP_LANGUAGE!=="en"||!/^Test:\s*/i.test(raw))return raw;
    if(isLikeCounterRule(r)&&/Intervall/i.test(raw))return defaultPreview(r);
    const label=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value||"Value";
    return `Test: ${label}`;
  };
  const persistRules=async()=>{
    settings.automation_rules=rules;
    return await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settings)});
  };

  shell("obs_meld","OBS/Meld Integration",L("Dauerhafte Live-Werte gezielt in eine OBS- oder Meld-Quelle schreiben.","Write persistent live values to a specific OBS or Meld source."),`<section class="card integrationBuilder"><h3>${L("Neuen Eintrag anlegen","Create new entry")}</h3><div class="integrationFlow"><label><div>1 · ${L("Plattform","Platform")}</div><select id="rulePlatform">${option([["tiktok","TikTok"],["twitch","Twitch"],["youtube","YouTube"],["kick","Kick"]])}</select></label><label><div>2 · ${L("Live-Wert","Live value")}</div><select id="ruleValue"></select></label><label><div>3 · ${L("Ausgabe","Output")}</div><select id="ruleTarget">${option(targetOptions)}</select></label><label><div>4 · ${L("Szene","Scene")}</div><select id="ruleScene"></select></label><label><div>5 · ${L("Quelle","Source")}</div><select id="ruleSource"></select></label></div><div class="integrationName"><label><div>${L("Name dieses Eintrags","Name of this entry")}</div><input id="ruleName" placeholder="${L("z. B. TikTok-Like-Zähler","e.g. TikTok like counter")}"></label><div class="btnLine"><button id="saveRule">${L("Speichern","Save")}</button><button class="secondary" id="clearRule">${L("Ändern abbrechen","Cancel editing")}</button></div></div></section><section class="card"><h3>${L("Gespeicherte Einträge","Saved entries")}</h3><div id="ruleList" class="ruleList"></div></section>`);
  const reloadButton=document.createElement("button");
  reloadButton.className="secondary targetReload";
  reloadButton.textContent=L("Szenen & Quellen neu laden","Reload scenes & sources");
  reloadButton.onclick=async()=>{await api("/api/automation/reload-targets",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});setTimeout(renderObsMeld,900);};
  $(".integrationBuilder").append(reloadButton);

  const actionField=document.createElement("label");
  actionField.innerHTML=`<div>6 · ${L("Aktion","Action")}</div><select id="ruleAction">${option(Object.entries(actionLabels))}</select>`;
  $(".integrationFlow").append(actionField);
  const likeCounterField=document.createElement("div");
  likeCounterField.className="likeCounterFields";
  likeCounterField.innerHTML=`<label><div>Chatter</div><input id="ruleLikeUser" list="ruleLikeUserList" placeholder="${L("TikTok-Name exakt eingeben","Enter exact TikTok name")}"></label><label><div>${L("Auslösen alle X Likes","Trigger every X likes")}</div><input id="ruleLikeThreshold" type="number" min="1" step="1" value="10"></label><datalist id="ruleLikeUserList"></datalist><div class="hint">${L("Gilt nur für TikTok-Like-Zähler: Die Aktion wird bei jedem Intervall dieses Benutzers erneut ausgeführt, z. B. bei 50, 100 und 150 Likes.","Only applies to the TikTok like counter: the action repeats at every interval for this user, e.g. at 50, 100 and 150 likes.")}</div>`;
  $(".integrationFlow").append(likeCounterField);
  const hideSecondsField=document.createElement("label");
  hideSecondsField.className="hideSecondsField";
  hideSecondsField.innerHTML=`<div>${L("Nach X Sekunden ausblenden","Hide after X seconds")}</div><input id="ruleHideSeconds" type="number" min="0" max="3600" step="0.1" value="4"><div class="hint">${L("0 = nicht automatisch ausblenden.","0 = do not hide automatically.")}</div>`;
  $(".integrationFlow").append(hideSecondsField);
  const startupField=document.createElement("label");
  startupField.className="textStartupField";
  startupField.innerHTML=`<div>${L("Text beim Programmstart","Text on tool startup")}</div><select id="ruleStartup"><option value="keep">${L("Letzten Wert behalten","Keep last value")}</option><option value="placeholder">${L("Platzhalter anzeigen","Show placeholder")}</option></select>`;
  $(".integrationFlow").append(startupField);
  const placeholderField=document.createElement("label");
  placeholderField.className="textPlaceholderField";
  placeholderField.innerHTML=`<div>${L("Platzhalter","Placeholder")}</div><input id="rulePlaceholder" value="---" placeholder="${L("z. B. noch keine Daten","e.g. no data yet")}">`;
  $(".integrationFlow").append(placeholderField);

  const fillLikeUserList=()=>{$("#ruleLikeUserList").innerHTML=savedLikeUsers().map(x=>`<option value="${esc(x)}"></option>`).join("");};
  const selectedIsLikeCounter=()=>$("#rulePlatform").value==="tiktok"&&$("#ruleValue").value==="like_total";
  const toggleTextOptions=()=>{const action=$("#ruleAction").value,text=action==="text",placeholder=$("#ruleStartup").value==="placeholder";startupField.hidden=!text;placeholderField.hidden=!text||!placeholder;likeCounterField.hidden=!selectedIsLikeCounter();hideSecondsField.hidden=action!=="show";};
  $("#ruleAction").onchange=toggleTextOptions;$("#ruleStartup").onchange=toggleTextOptions;

  let editIndex=-1;
  const refreshSources=()=>{const target=targets[$("#ruleTarget").value]||{},scene=$("#ruleScene").value,sources=(target.sources_by_scene||{})[scene]||[];$("#ruleSource").innerHTML=option(sources.length?sources.map(x=>[x,x]):[["",L("Keine Quelle in dieser Szene","No source in this scene")]]);};
  const refreshTargets=()=>{const key=$("#ruleTarget").value,target=targets[key]||{},scenes=target.scenes||[];$("#ruleScene").innerHTML=option(scenes.length?scenes.map(x=>[x,x]):[["",L("Zuerst OBS/Meld verbinden","Connect OBS/Meld first")]]);refreshSources();};
  const refreshValues=()=>{$("#ruleValue").innerHTML=option(values[$("#rulePlatform").value]||[]);toggleTextOptions();};
  const readRule=()=>{
    const r={name:$("#ruleName").value.trim()||`${platformLabel($("#rulePlatform").value)} ${$("#ruleValue").selectedOptions[0]?.textContent||L("Wert","Value")}`,platform:$("#rulePlatform").value,value:$("#ruleValue").value,target:$("#ruleTarget").value,scene:$("#ruleScene").value,source:$("#ruleSource").value,action:$("#ruleAction").value,startup:$("#ruleStartup").value,placeholder:$("#rulePlaceholder").value.trim()||"---"};
    if(r.action==="show")r.hideSeconds=Math.max(0,Number($("#ruleHideSeconds").value)||0);
    if(isLikeCounterRule(r)){r.likeUser=$("#ruleLikeUser").value.trim();r.likeThreshold=Math.max(1,Number($("#ruleLikeThreshold").value)||1);}
    return r;
  };
  const runRuleTest=async (r,previewText)=>{
    const body={...r};
    if(isTextRule(r))body.preview=String(previewText||r.testText||defaultPreview(r));
    const out=await api("/api/automation/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    if(!out.ok)console.warn(L("Regeltest fehlgeschlagen","Rule test failed"),out.error);
  };
  const renderRules=()=>{
    fillLikeUserList();
    $("#ruleList").innerHTML=rules.length?rules.map((r,i)=>{
      const textRule=isTextRule(r);
      const testText=localizedPreview(r,r.testText||defaultPreview(r));
      const valueLabel=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value;
      const condition=isLikeCounterRule(r)?` · ${L("Benutzer","User")}: ${esc(r.likeUser||"-")} · ${L("alle","every")} ${esc(r.likeThreshold||"-")} Likes`:"";
      const showInfo=isShowRule(r)?` · ${L("ausblenden nach","hide after")} ${esc(r.hideSeconds??4)}s`:"";
      const testControls=textRule
        ? `<input class="savedRuleTestText" data-i="${i}" value="${esc(testText)}" placeholder="${L("Testtext","Test text")}"><button class="secondary testSavedRule" data-i="${i}">${L("Testen","Test")}</button>`
        : `<button class="secondary testSavedRule" data-i="${i}">${L("Testen","Test")}</button>`;
      return `<div class="ruleRow"><div><b>${esc(r.name)}</b><div class="small">${esc(platformLabel(r.platform))} · ${esc(valueLabel)}${condition} → ${esc((r.target||"").toUpperCase())} · ${esc(r.scene||"-")} · ${esc(r.source||"-")} · ${esc(actionLabels[r.action]||r.action||actionLabels.text)}${showInfo}</div></div><div class="btnLine">${testControls}<button class="secondary editRule" data-i="${i}">${L("Ändern","Edit")}</button><button class="secondary deleteRule" data-i="${i}">${L("Löschen","Delete")}</button></div></div>`;
    }).join(""):`<div class="hint">${L("Noch keine Einträge. Lege oben einen dauerhaften Live-Wert an.","No entries yet. Create a persistent live value above.")}</div>`;
    let testTextSaveTimer=null;
    const queueTestTextSave=()=>{clearTimeout(testTextSaveTimer);testTextSaveTimer=setTimeout(()=>persistRules(),450);};
    $$('.savedRuleTestText').forEach(input=>{
      input.oninput=()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;queueTestTextSave();};
      input.onchange=async()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;await persistRules();};
    });
    $$('.testSavedRule').forEach(b=>b.onclick=async()=>{const i=Number(b.dataset.i);const r=rules[i];if(!r)return;const input=$(`.savedRuleTestText[data-i="${i}"]`);if(input){r.testText=input.value;await persistRules();await runRuleTest(r,input.value);}else{await runRuleTest(r);}});
    $$('.editRule').forEach(b=>b.onclick=()=>{const r=rules[Number(b.dataset.i)];editIndex=Number(b.dataset.i);$("#rulePlatform").value=r.platform;refreshValues();$("#ruleValue").value=r.value;toggleTextOptions();$("#ruleTarget").value=r.target;refreshTargets();$("#ruleScene").value=r.scene||"";refreshSources();$("#ruleSource").value=r.source||"";$("#ruleAction").value=r.action||"text";$("#ruleStartup").value=r.startup||"keep";$("#rulePlaceholder").value=r.placeholder||"---";$("#ruleHideSeconds").value=r.hideSeconds??r.hide_seconds??4;$("#ruleLikeUser").value=r.likeUser||r.like_user||"";$("#ruleLikeThreshold").value=r.likeThreshold||r.like_threshold||10;toggleTextOptions();$("#ruleName").value=r.name;$("#saveRule").textContent=L("Änderung speichern","Save changes");});
    $$('.deleteRule').forEach(b=>b.onclick=async()=>{rules.splice(Number(b.dataset.i),1);await persistRules();renderRules();});
  };
  $("#rulePlatform").onchange=()=>{refreshValues();};$("#ruleValue").onchange=toggleTextOptions;$("#ruleTarget").onchange=refreshTargets;$("#ruleScene").onchange=refreshSources;
  $("#clearRule").onclick=()=>{editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleHideSeconds").value=4;$("#saveRule").textContent=L("Speichern","Save");};
  $("#saveRule").onclick=async()=>{const r=readRule();if(isLikeCounterRule(r)&&!r.likeUser){alert(L("Bitte einen Chatter für den Like-Zähler eintragen.","Please enter a chatter for the like counter."));return;}if(editIndex>=0){r.testText=rules[editIndex]?.testText||defaultPreview(r);rules[editIndex]=r;}else{r.testText=defaultPreview(r);rules.push(r);}const out=await persistRules();if(!out.ok){console.warn(L("Regel speichern fehlgeschlagen","Failed to save rule"),out.error);return;}editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleHideSeconds").value=4;$("#saveRule").textContent=L("Speichern","Save");renderRules();};
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
function schemaLocalized(field, name, fallback=""){
  const english=window.APP_LANGUAGE==="en";
  return (english?(field[`${name}_en`]??field[name]):(field[`${name}_de`]??field[name]))??fallback;
}
function schemaLabel(field){return schemaLocalized(field,"label",field.name||field.key||"");}
function schemaTab(field){return schemaLocalized(field,"tab",schemaLocalized(field,"ui_tab",L("Allgemein","General")));}
function renderPluginField(field, values){
  const key=String(field.key||field.name||"");
  const type=String(field.type||field.kind||"text").toLowerCase();
  const label=esc(schemaLabel(field));
  const help=schemaLocalized(field,"help","");
  const placeholder=schemaLocalized(field,"placeholder","");
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
    const buttonText=schemaLocalized(field,"button_text",schemaLocalized(field,"text",schemaLabel(field)||L("Ausführen","Run")));
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
      const l=typeof o==="object"?schemaLocalized(o,"label",o.name??v):o;
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
    return `<label class="${cls}"${hideAttrs}><div>${label}</div><textarea name="${esc(key)}" ${ro} placeholder="${esc(placeholder)}">${esc(value??field.default??"")}</textarea></label>${helpHtml}`;
  }
  const inputType=(type==="number"||type==="int"||type==="float")?"number":(type==="password"?"password":"text");
  return `<label class="${cls}"${hideAttrs}><div>${label}</div><input name="${esc(key)}" type="${inputType}" value="${esc(value??field.default??"")}" ${ro} placeholder="${esc(placeholder)}"></label>${helpHtml}`;
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
// Canonical Info3ditor UI. Keep every visible string explicit so the global
// fallback translator never produces mixed labels inside compound phrases.
function openInfo3ditorSettings(mount, values){
  let presets=[];
  try{const raw=JSON.parse(values.presets_json||'{"presets":[]}');presets=Array.isArray(raw.presets)?raw.presets:[];}catch(e){}
  const fields={
    twitch:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie / Spiel","Category / game")],["game_id",L("Spiel-ID (optional)","Game ID (optional)")],["tags","Tags"],["description",L("Beschreibung / Notiz","Description / note")]],
    youtube:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie","Category")],["tags","Tags"],["description",L("Beschreibung","Description")]],
    kick:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie","Category")],["tags","Tags"],["description",L("Beschreibung / Notiz","Description / note")]],
    tiktok:[["title",L("Live-Titel","Live title")],["category",L("Kategorie","Category")],["description",L("Nicht verfügbar","Not available")]],
  };
  const platformNames={twitch:"Twitch",youtube:"YouTube",kick:"Kick",tiktok:"TikTok"};
  const raw=()=>JSON.stringify({presets});
  const save=()=>api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:raw()}})});
  const send=preset=>api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:raw(),selected_preset_id:preset.id}})});
  const resultText=out=>out.ok?L("Vorgang erfolgreich.","Action completed."):`${L("Fehler","Error")}: ${out.error||'?'}`;
  const list=()=>{
    mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor ${L("Vorlagen","Presets")}</h3><div class="small">${L("Verwalte deine Spiel- und Plattforminformationen.","Manage your game and platform information.")}</div></div><button class="secondary" id="pluginSettingsClose">${L("Schließen","Close")}</button></div><div class="btnLine"><button id="infoNew">${L("Vorlage anlegen","Create preset")}</button></div><div class="infoPresetList">${presets.map((preset,index)=>`<div class="infoPresetRow"><b>${esc(preset.name||L("Unbenannt","Untitled"))}</b><div class="btnLine"><button class="infoSendPreset" data-preset="${index}">${L("Senden","Send")}</button><button class="secondary infoEditPreset" data-preset="${index}">${L("Bearbeiten","Edit")}</button><button class="secondary infoDeletePreset" data-preset="${index}">${L("Löschen","Delete")}</button></div></div>`).join('')||`<div class="small">${L("Noch keine Vorlagen angelegt.","No presets created yet.")}</div>`}</div><div class="small" id="infoResult"></div></section>`;
    $('#pluginSettingsClose',mount).onclick=()=>mount.innerHTML='';
    $('#infoNew',mount).onclick=()=>editor({id:`preset_${Date.now()}`,name:L("Neue Vorlage","New preset"),platforms:{}},-1);
    $$('.infoSendPreset',mount).forEach(button=>button.onclick=async()=>{$('#infoResult',mount).textContent=L("Sende...","Sending...");const out=await send(presets[Number(button.dataset.preset)]);$('#infoResult',mount).textContent=out.ok?L("Sendevorgang gestartet.","Sending started."):resultText(out)});
    $$('.infoEditPreset',mount).forEach(button=>button.onclick=()=>editor(structuredClone(presets[Number(button.dataset.preset)]),Number(button.dataset.preset)));
    $$('.infoDeletePreset',mount).forEach(button=>button.onclick=async()=>{presets.splice(Number(button.dataset.preset),1);const out=await save();if(out.ok)list();else $('#infoResult',mount).textContent=resultText(out)});
  };
  const editor=(preset,index)=>{
    preset.platforms=preset.platforms||{};
    const blocks=Object.entries(fields).map(([platform,rows])=>{const d=preset.platforms[platform]||{};const locked=platform==='tiktok';return `<section class="infoPlatform"><div class="infoPlatformHead"><h3>${platformNames[platform]}</h3><label><input type="checkbox" data-info="${platform}.enabled" ${d.enabled?'checked':''} ${locked?'disabled':''}> ${locked?L("Noch nicht zum Senden verfügbar","Not available for sending yet"):L("Beim Senden aktiv","Enabled when sending")}</label></div><div class="platformForm">${rows.map(([key,label])=>`<label><div>${esc(label)}</div>${key==='description'?`<textarea data-info="${platform}.${key}" ${locked?'disabled':''}>${esc(locked?L("TikTok wird aktuell nicht unterstützt.","TikTok is not currently supported."):d[key]||'')}</textarea>`:`<input data-info="${platform}.${key}" value="${esc(d[key]||'')}" ${locked?'disabled':''}>`}</label>`).join('')}</div></section>`}).join('');
    mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>${index<0?L("Vorlage anlegen","Create preset"):L("Vorlage bearbeiten","Edit preset")}</h3><div class="small">${L("Titel, Kategorie und Aktivierung je Plattform festlegen.","Set title, category and activation for each platform.")}</div></div><button class="secondary" id="infoBack">${L("Zurück","Back")}</button></div><div class="platformForm"><label><div>${L("Vorlagenname","Preset name")}</div><input id="infoName" value="${esc(preset.name||'')}"></label></div>${blocks}<div class="btnLine"><button id="infoSave">${L("Vorlage speichern","Save preset")}</button><span class="small" id="infoResult"></span></div></section>`;
    $('#infoBack',mount).onclick=list;
    $('#infoSave',mount).onclick=async()=>{preset.name=$('#infoName',mount).value.trim()||L("Neue Vorlage","New preset");$$('[data-info]',mount).forEach(input=>{const [platform,key]=input.dataset.info.split('.');preset.platforms[platform]=preset.platforms[platform]||{};preset.platforms[platform][key]=input.type==='checkbox'?input.checked:input.value.trim();});preset.platforms.tiktok.enabled=false;if(index<0)presets.push(preset);else presets[index]=preset;const out=await save();if(out.ok)list();else $('#infoResult',mount).textContent=resultText(out)};
  };
  list();
}

async function openPluginSettings(pluginId){
  const mount=$("#pluginSettingsMount");
  if(!mount) return;
  mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Einstellungen werden geladen...</h3></section>`;
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Einstellungen</h3><div class="warnBox">${esc(d.error||"Einstellungen konnten nicht geladen werden")}</div></section>`;return;}
  if(pluginId==="info3ditor"){openInfo3ditorSettings(mount,d.values||{});return;}
  let schema=d.schema||[];
  const values=d.values||{};
  schema=await enrichPluginSchema(pluginId,schema,values);
  const tabs=[...new Set(schema.map(schemaTab))];
  const groups=tabs.length?tabs:["Allgemein"];
  const tabButtons=groups.map((tab,i)=>`<button type="button" class="pluginSettingsTabBtn ${i===0?"active":""}" data-tab="${esc(tab)}">${esc(tab)}</button>`).join("");
  const body=groups.map((tab,i)=>`<div class="pluginSettingsGroup ${i===0?"active":""}" data-tab="${esc(tab)}"><div class="pluginSettingsFields">${schema.filter(f=>schemaTab(f)===tab || (!tabs.length&&true)).map(f=>renderPluginField(f,values)).join("")}</div></div>`).join("");
  mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>${esc(d.plugin_id)} ${L("Einstellungen","Settings")}</h3><div class="small">${L(`Wird in data/settings.json unter plugins/${esc(d.plugin_id)} gespeichert und danach neu gestartet.`,`Stored in data/settings.json under plugins/${esc(d.plugin_id)} and then restarted.`)}</div></div><button type="button" class="secondary" id="pluginSettingsClose">${L("Schließen","Close")}</button></div>${groups.length>1?`<div class="pluginSettingsTabs">${tabButtons}</div>`:""}<form id="pluginSettingsForm">${body||`<div class='small'>${L("Dieses Plugin hat kein Einstellungsschema.","This plugin has no settings schema.")}</div>`}<div class="btnLine"><button type="submit">${L("Speichern & neu starten","Save & restart")}</button><button type="button" class="secondary" id="pluginSettingsCancel">${L("Abbrechen","Cancel")}</button><span class="small" id="pluginSettingsResult"></span></div></form></section>`;
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
    if(out.ok) setTimeout(()=>{if(page===pluginId)location.reload();else{mount.innerHTML="";renderPlugins();}},700);
  };
  mount.scrollIntoView({behavior:"smooth",block:"start"});
}
async function renderDedicatedPlugin(pluginId,title,description){
  shell(pluginId,title,description,`<div id="pluginSettingsMount"></div>`);
  await openPluginSettings(pluginId);
  const close=$("#pluginSettingsClose",$("#pluginSettingsMount"));
  if(close)close.hidden=true;
  const cancel=$("#pluginSettingsCancel",$("#pluginSettingsMount"));
  if(cancel)cancel.hidden=true;
}
async function togglePluginEnabled(pluginId, enabled){
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){alert(d.error||"Plugin-Einstellungen konnten nicht geladen werden");return;}
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
        <label><div>${L("Aktiv","Enabled")}</div><select name="enabled"><option value="true" ${settings.enabled?"selected":""}>${L("Ja","Yes")}</option><option value="false" ${!settings.enabled?"selected":""}>${L("Nein","No")}</option></select></label>
        <label><div>${L("Bildschirmrand","Screen edge")}</div><select name="edge">${[["left",L("Links","Left")],["right",L("Rechts","Right")],["top",L("Oben","Top")],["bottom",L("Unten","Bottom")]].map(([v,l])=>`<option value="${v}" ${settings.edge===v?"selected":""}>${l}</option>`).join("")}</select></label>
        <label><div>${L("VerzÃ¶gerung bis zum Ã–ffnen (Sekunden)","Delay before opening (seconds)")}</div><input name="delaySeconds" type="number" min="0" max="120" step="0.5" value="${esc(settings.delaySeconds)}"></label>
        <label><div>${L("Transparenz","Opacity")}</div><input name="opacity" type="range" min="0" max="100" value="${esc(settings.opacity)}"></label>
        <div class="hint">${L("PNG-Ordner","PNG folder")}: assets\\pics\\3asyslid3r</div>
      </form>
    </section>
    <section class="card easysliderSettings">
      <h3>${L("SchaltflÃ¤chen","Buttons")}</h3>
      <div id="easysliderButtons" class="easysliderButtonList"></div>
      <div class="btnLine"><button id="easysliderSave" type="button">${L("Speichern","Save")}</button><button id="easysliderTest" type="button" class="secondary">${L("Dashboard testen","Test dashboard")}</button><span id="easysliderResult" class="small"></span></div>
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
    result.textContent=L("Speichere...","Saving...");
    const out=await api("/api/3asyslid3r/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(collect())});
    result.textContent=out.ok?L("Gespeichert.","Saved."):`${L("Fehler","Error")}: ${out.error||L("unbekannt","unknown")}`;
    if(out.ok){settingsCache=null;}
  };
  $("#easysliderTest").onclick=async()=>{
    await api("/api/3asyslid3r/activate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:"/"}),timeoutMs:2500});
    location.href="/";
  };
}
async function renderPlugins(){
  const s=await api("/api/status");
  const cards=(s.plugins||[]).map(p=>`<section class="card pluginCard"><div class="pluginHead"><h3>${esc(p.name)}</h3><span class="pluginState ${pluginStateClass(p.state)}">${esc(p.state||"ready")}</span></div><div class="small">${esc(p.description||"")}</div><div class="small pluginStatusText">${esc(p.status||p.message||"Bereit")}</div><div class="btnLine"><button type="button" class="pluginSettingsBtn" data-plugin="${esc(p.id)}">Einstellungen</button><a class="btn secondary" href="/dev" title="Protokolle im DEV-Bereich prüfen">Protokolle</a></div></section>`).join("");
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
    restart.textContent="Neustart";
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
      <section class="card"><h3>Laufzeit</h3><div id="devRuntime" class="devFacts"></div></section>
      <section class="card"><h3>Zustand</h3><div id="devCounts" class="devFacts"></div></section>
      <section class="card"><h3>Plattformen</h3><div id="devPlatforms" class="devFacts"></div></section>
      <section class="card"><h3>Entwicklerlinks</h3><div class="devLinks">
        <a class="btn secondary" target="_blank" href="/debug">Ungefilterte Diagnose</a>
        <a class="btn secondary" target="_blank" href="/api/status">Status JSON</a>
        <a class="btn secondary" target="_blank" href="/api/dev/settings">Einstellungen-JSON (bereinigt)</a>
        <a class="btn secondary" target="_blank" href="/api/runtime">Laufzeit-JSON</a>
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
      ["Python",d.python],["Modus",d.frozen?"EXE":"Quellcode"],["Arbeitsordner",d.cwd],["Programmdatei",d.executable],
      ["Daten",d.paths?.data],["Log",d.paths?.log]
    ].map(x=>`<div><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join("");
    $("#devCounts").innerHTML=[
      ["Nachrichten",d.counts?.messages],["Plugins",d.counts?.plugins],["Aktive Plugins",d.counts?.active_plugins],
      ["Auth-Dateien",d.counts?.auth_files],["Freier Speicher",formatBytes(d.disk_free)]
    ].map(x=>`<div><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join("");
    $("#devPlatforms").innerHTML=Object.entries(liveStatus.platforms||{}).map(([name,cfg])=>`<div><b>${esc(platformLabel(name))}</b><span class="${cfg.status==="verbunden"?"devOk":""}">${localizedStatusValue(cfg.enabled?"active":"inactive")} · ${esc(localizedPlatformStatus(cfg,true))}</span></div>`).join("");
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
async function renderChattim3r(){
  shell("chattim3r","Chattim3r",L("Wiederkehrende Chatnachrichten automatisch an ausgewählte Plattformen senden.","Automatically send recurring chat messages to selected platforms."),`
    <section class="card timerEditor"><h3 id="timerFormTitle">${L("Neuen Eintrag anlegen","Create new entry")}</h3>
      <form id="timerForm"><div class="timerFields">
        <label><div>${L("Intervall in Minuten","Interval in minutes")}</div><input id="timerMinutes" type="number" min="1" step="1" value="30" required></label>
        <label class="timerText"><div>${L("Nachricht","Message")}</div><textarea id="timerText" rows="3" maxlength="1000" required></textarea></label>
      </div><div class="timerPlatforms"><b>${L("Plattformen","Platforms")}</b>${["twitch","tiktok","youtube","kick"].map(p=>`<label><input type="checkbox" name="timerPlatform" value="${p}"> ${platformLabel(p)}</label>`).join("")}</div>
      <div class="btnLine"><button type="submit" id="timerSave">${L("Speichern","Save")}</button><button type="button" class="secondary" id="timerCancel" hidden>${L("Abbrechen","Cancel")}</button></div></form>
    </section><section class="card"><h3>${L("Gespeicherte Einträge","Saved entries")}</h3><div id="timerList" class="timerList"></div></section>`);
  let entries=[], editing="";
  const load=async()=>{const out=await api("/api/chattim3r");entries=Array.isArray(out.entries)?out.entries:[];draw();};
  const reset=()=>{editing="";$("#timerForm").reset();$("#timerMinutes").value=30;$("#timerCancel").hidden=true;$("#timerFormTitle").textContent=L("Neuen Eintrag anlegen","Create new entry");};
  const draw=()=>{$("#timerList").innerHTML=entries.map(e=>`<div class="timerRow"><div><b>${esc(e.text)}</b><span>${esc(e.minutes)} min · ${(e.platforms||[]).map(platformLabel).join(", ")}</span></div><div class="btnLine"><button class="secondary timerEdit" data-id="${esc(e.id)}">${L("Bearbeiten","Edit")}</button><button class="secondary timerTest" data-id="${esc(e.id)}">${L("Testen","Test")}</button><button class="secondary timerDelete" data-id="${esc(e.id)}">${L("Löschen","Delete")}</button></div></div>`).join("")||`<div class="small">${L("Noch keine Einträge gespeichert.","No entries saved yet.")}</div>`;
    $$(".timerEdit").forEach(b=>b.onclick=()=>{const e=entries.find(x=>x.id===b.dataset.id);if(!e)return;editing=e.id;$("#timerMinutes").value=e.minutes;$("#timerText").value=e.text;$$('[name="timerPlatform"]').forEach(x=>x.checked=(e.platforms||[]).includes(x.value));$("#timerCancel").hidden=false;$("#timerFormTitle").textContent=L("Eintrag bearbeiten","Edit entry");scrollTo({top:0,behavior:"smooth"});});
    $$(".timerTest").forEach(b=>b.onclick=async()=>{const old=b.textContent;b.disabled=true;b.textContent=L("Wird gesendet…","Sending…");const out=await api("/api/chattim3r/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:b.dataset.id})});b.disabled=false;b.textContent=out.ok?L("Gesendet","Sent"):L("Fehlgeschlagen","Failed");setTimeout(()=>{b.textContent=old},1600);if(!out.ok)alert(out.error||L("Test fehlgeschlagen","Test failed"));});
    $$(".timerDelete").forEach(b=>b.onclick=async()=>{if(!confirm(L("Eintrag wirklich löschen?","Really delete this entry?")))return;const out=await api("/api/chattim3r/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:b.dataset.id})});if(out.ok){entries=out.entries||[];draw();}});};
  $("#timerCancel").onclick=reset;
  $("#timerForm").onsubmit=async ev=>{ev.preventDefault();const platforms=$$('[name="timerPlatform"]:checked').map(x=>x.value);if(!platforms.length){alert(L("Bitte mindestens eine Plattform auswählen.","Please select at least one platform."));return;}const payload={id:editing,minutes:Number($("#timerMinutes").value),text:$("#timerText").value.trim(),platforms};const out=await api("/api/chattim3r",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(!out.ok){alert(out.error||L("Speichern fehlgeschlagen","Save failed"));return;}entries=out.entries||[];reset();draw();};
  await load();
}
const SOUND_ALERTS={
  twitch:[["twitch_follow","Follow"],["twitch_join",L("Beitritt","Join")],["twitch_sub","Sub"],["twitch_resub","Resub"],["twitch_subgift","Sub-Geschenk"],["twitch_raid","Raid"],["twitch_cheer","Cheer / Bits"]],
  tiktok:[["tiktok_follow","Follow"],["tiktok_join",L("Beitritt","Join")],["tiktok_like","Like"],["tiktok_gift",L("Geschenk","Gift")],["tiktok_share",L("Teilen","Share")]],
  youtube:[["youtube_superchat","Super Chat"],["youtube_supersticker","Super Sticker"],["youtube_member",L("Mitglied","Member")],["youtube_gift",L("Mitgliedschaftsgeschenk","Membership gift")]],
  kick:[["kick_follow","Follow"],["kick_sub","Sub"],["kick_gift",L("Sub-Geschenk","Sub gift")],["kick_raid","Raid"],["kick_join",L("Beitritt","Join")]]
};
function soundOptions(sounds,value){
  return `<option value="">${L("Stumm","Muted")}</option>`+sounds.map(name=>`<option value="${esc(name)}" ${name===value?"selected":""}>${esc(name)}</option>`).join("");
}
async function audioOutputDevices(){
  if(!navigator.mediaDevices?.enumerateDevices)return [];
  try{return (await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==="audiooutput");}catch(_){return []}
}
function resolveSavedDeviceId(devices,id,label){
  if(!id||id==="__default__"||devices.some(device=>device.deviceId===id))return id||"";
  const wanted=String(label||"").trim().toLocaleLowerCase();
  const match=wanted?devices.find(device=>String(device.label||"").trim().toLocaleLowerCase()===wanted):null;
  return match?.deviceId||id;
}
async function renderSettings(){
  const [all,soundData,devices]=await Promise.all([api("/api/settings"),api("/api/sounds"),audioOutputDevices()]);
  const cfg=all.general?.sound||{}, sounds=Array.isArray(soundData.sounds)?soundData.sounds:[], alerts=cfg.alerts||{};
  cfg.output_device=resolveSavedDeviceId(devices,cfg.output_device,cfg.output_device_label);
  cfg.stream_output_device=resolveSavedDeviceId(devices,cfg.stream_output_device,cfg.stream_output_device_label);
  const deviceRows=devices.map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||`${L("Audiogerät","Audio device")} ${i+1}`)}</option>`).join("");
  const knownDeviceIds=new Set(devices.map(d=>d.deviceId));
  const savedBroadcaster=cfg.output_device&&!knownDeviceIds.has(cfg.output_device)?`<option value="${esc(cfg.output_device)}">${esc(cfg.output_device_label||L("Gespeichertes Broadcaster-Gerät","Saved broadcaster device"))}</option>`:"";
  const savedStream=cfg.stream_output_device&&!['',"__default__"].includes(cfg.stream_output_device)&&!knownDeviceIds.has(cfg.stream_output_device)?`<option value="${esc(cfg.stream_output_device)}">${esc(cfg.stream_output_device_label||L("Gespeichertes Stream-Gerät","Saved stream device"))}</option>`:"";
  const deviceOptions=`<option value="">${L("System-Standardgerät","System default device")}</option>${savedBroadcaster}${deviceRows}`;
  const streamDeviceOptions=`<option value="">${L("Nicht ausgeben","No output")}</option><option value="__default__">${L("System-Standardgerät","System default device")}</option>${savedStream}${deviceRows}`;
  const tabs=[["general",L("Allgemein","General")],...Object.keys(SOUND_ALERTS).map(p=>[p,platformLabel(p)])];
  const groups=tabs.map(([tab,label],index)=>{
    if(tab==="general")return `<div class="soundSettingsGroup ${index===0?"active":""}" data-sound-tab="general"><div class="soundSettingsGrid"><label><div>${L("Broadcaster-Ausgabe (Chat + Alerts)","Broadcaster output (chat + alerts)")}</div><select id="soundDevice">${deviceOptions}</select></label><label><div>${L("Stream-Ausgabe (nur Alerts)","Stream output (alerts only)")}</div><select id="streamSoundDevice">${streamDeviceOptions}</select></label><label><div>${L("Alle eingehenden Chatnachrichten","All incoming chat messages")}</div><select id="chatSound">${soundOptions(sounds,cfg.chat_sound||"")}</select></label></div><div class="btnLine soundDeviceActions"><button type="button" class="secondary" id="loadSoundDevices">${L("Geräteliste aktualisieren","Refresh device list")}</button><button type="button" class="secondary" id="openSoundFolder">${L("Soundordner öffnen","Open sound folder")}</button><span class="small" id="soundDeviceHint">${L("Der Broadcaster hört Chat und Alerts. An den Stream werden ausschließlich Alerts ausgegeben.","The broadcaster hears chat and alerts. Only alerts are sent to the stream output.")}</span></div><div class="hint">${L("Sounddateien kommen aus assets/sound. Unterstützt werden MP3, WAV, OGG, M4A, AAC und FLAC.","Sound files are loaded from assets/sound. MP3, WAV, OGG, M4A, AAC and FLAC are supported.")}</div></div>`;
    const pCfg=alerts[tab]||{};
    return `<div class="soundSettingsGroup" data-sound-tab="${tab}"><div class="soundPlatformHead">${platformBadge(tab)}<h3>${label}</h3></div><div class="soundSettingsGrid">${SOUND_ALERTS[tab].map(([key,name])=>`<label><div>${esc(name)}</div><select data-sound-platform="${tab}" data-sound-event="${key}">${soundOptions(sounds,pCfg[key]||"")}</select></label>`).join("")}</div></div>`;
  }).join("");
  shell("settings",L("Einstellungen","Settings"),L("Allgemeine Einstellungen für das gesamte Tool.","General settings for the entire tool."),`<section class="card pluginSettingsCard"><h3 class="settingsSectionTitle">${L("Sounds","Sounds")}</h3><div class="pluginSettingsTabs">${tabs.map(([key,label],i)=>`<button type="button" class="pluginSettingsTabBtn soundTab ${i===0?"active":""}" data-tab="${key}">${label}</button>`).join("")}</div><form id="soundSettingsForm">${groups}<div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary" id="testSelectedSound">${L("Ausgewählten Sound testen","Test selected sound")}</button><span class="small" id="soundSettingsResult"></span></div></form></section>`);
  $("#soundDevice").value=cfg.output_device||"";
  $("#streamSoundDevice").value=cfg.stream_output_device||"";
  $$(".soundTab").forEach(btn=>btn.onclick=()=>{$$(".soundTab").forEach(x=>x.classList.toggle("active",x===btn));$$(".soundSettingsGroup").forEach(x=>x.classList.toggle("active",x.dataset.soundTab===btn.dataset.tab));});
  $$('#soundSettingsForm select:not(#soundDevice)').forEach(select=>select.onchange=()=>{if(select.value&&select.value!=="__off__")playConfiguredSound(select.value,$("#soundDevice")?.value||"");});
  $("#openSoundFolder").onclick=async()=>{const out=await api("/api/sounds/open-folder",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!out.ok)$("#soundDeviceHint").textContent=out.error||L("Soundordner konnte nicht geöffnet werden.","Could not open the sound folder.");};
  $("#loadSoundDevices").onclick=async()=>{
    const button=$("#loadSoundDevices"),hint=$("#soundDeviceHint"),select=$("#soundDevice");button.disabled=true;
    try{
      let chosen=null;
      if(typeof navigator.mediaDevices?.selectAudioOutput==="function")chosen=await navigator.mediaDevices.selectAudioOutput();
      else if(typeof navigator.mediaDevices?.getUserMedia==="function"){const stream=await navigator.mediaDevices.getUserMedia({audio:true});stream.getTracks().forEach(track=>track.stop());}
      const streamSelect=$("#streamSoundDevice"),oldStream=streamSelect.value,oldStreamLabel=streamSelect.selectedOptions[0]?.textContent||"";
      const oldBroadcaster=select.value,oldBroadcasterLabel=select.selectedOptions[0]?.textContent||"";
      const found=await audioOutputDevices(),selected=chosen?.deviceId||oldBroadcaster;
      select.innerHTML=`<option value="">${L("System-Standardgerät","System default device")}</option>`+found.map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||`${L("Audiogerät","Audio device")} ${i+1}`)}</option>`).join("");
      streamSelect.innerHTML=`<option value="">${L("Nicht ausgeben","No output")}</option><option value="__default__">${L("System-Standardgerät","System default device")}</option>`+found.map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||`${L("Audiogerät","Audio device")} ${i+1}`)}</option>`).join("");
      select.value=selected;if(select.value!==selected&&selected)select.append(new Option(chosen?.label||oldBroadcasterLabel||L("Gespeichertes Broadcaster-Gerät","Saved broadcaster device"),selected,true,true));
      streamSelect.value=oldStream;if(streamSelect.value!==oldStream&&oldStream)streamSelect.append(new Option(oldStreamLabel||L("Gespeichertes Stream-Gerät","Saved stream device"),oldStream,true,true));
      hint.textContent=found.length?L(`${found.length} Audiogerät(e) gefunden.`,`Found ${found.length} audio device(s).`):L("Keine Audiogeräte gefunden.","No audio devices found.");
    }catch(e){hint.textContent=L("Gerätefreigabe wurde abgebrochen oder vom Browser blockiert.","Device access was cancelled or blocked by the browser.");}
    finally{button.disabled=false;}
  };
  $("#testSelectedSound").onclick=async()=>{
    const group=$(".soundSettingsGroup.active"),isChatTest=group?.dataset.soundTab==="general";
    const select=isChatTest?$("#chatSound"):group?.querySelector('[data-sound-event]');
    const name=select?.value;if(!name)return;
    if(isChatTest)await playConfiguredSound(name,$("#soundDevice")?.value||"",true);
    else await playSoundForAudience(name,true,{output_device:$("#soundDevice")?.value||"",stream_output_device:$("#streamSoundDevice")?.value||""});
  };
  $("#soundSettingsForm").onsubmit=async ev=>{ev.preventDefault();const broadcaster=$("#soundDevice"),stream=$("#streamSoundDevice");const next={enabled:true,output_device:broadcaster.value,output_device_label:broadcaster.selectedOptions[0]?.textContent||"",stream_output_device:stream.value,stream_output_device_label:stream.selectedOptions[0]?.textContent||"",chat_sound:$("#chatSound").value,alerts:{}};$$('[data-sound-platform]').forEach(el=>{const p=el.dataset.soundPlatform;next.alerts[p]=next.alerts[p]||{};next.alerts[p][el.dataset.soundEvent]=el.value;});const out=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({general:{sound:next}})});$("#soundSettingsResult").textContent=out.ok?L("Gespeichert.","Saved."):out.error||L("Fehler beim Speichern.","Could not save.");if(out.ok)soundRuntimeConfig=next;};
}
let soundRuntimeConfig=null;
let soundSeen=new Set();
let soundBaselineReady=false;
function soundMessageKey(item){return [item.id||"",item.message_id||"",item.platform||"",item.time||"",item.user||"",item.text||"",item.event_type||item.alert_type||item.message_type||""].join("|");}
async function playConfiguredSound(name,deviceId="",fallbackToDefault=false){
  if(!name||name==="__off__")return false;
  try{
    const audio=new Audio(`/sound-asset/${encodeURIComponent(name)}`);
    if(deviceId&&deviceId!=="__default__"&&typeof audio.setSinkId==="function"){
      try{await audio.setSinkId(deviceId);}
      catch(error){console.warn("Audiogerät ist nicht verfügbar",error);return false;}
    }
    await audio.play();
    return true;
  }catch(e){console.warn("Sound konnte nicht abgespielt werden",e);return false;}
}
async function playSoundForAudience(name,isAlert,cfg){
  const broadcaster=cfg.output_device||"";
  const broadcasterPlay=playConfiguredSound(name,broadcaster,true);
  if(!isAlert)return;
  const stream=cfg.stream_output_device||"";
  const sameDevice=stream==="__default__"?(broadcaster===""||broadcaster==="default"):(stream&&stream===broadcaster);
  if(stream&&!sameDevice)playConfiguredSound(name,stream,false);
  return broadcasterPlay;
}
function configuredSoundForMessage(item,cfg){
  const platform=String(item.platform||"").toLowerCase();
  if(!Object.prototype.hasOwnProperty.call(SOUND_ALERTS,platform))return "";
  const type=String(item.message_type||item.type||"chat").toLowerCase();
  if(["chat","message","comment"].includes(type))return cfg.chat_sound||"";
  const raw=String(item.event_type||item.alert_type||item.message_type||item.type||"").toLowerCase();
  const platformCfg=cfg.alerts?.[platform]||{};
  const prefixed=raw.startsWith(platform+"_")?raw:`${platform}_${raw}`;
  for(const key of [raw,prefixed]){if(Object.prototype.hasOwnProperty.call(platformCfg,key))return platformCfg[key]||"";}
  return "";
}
async function pollIncomingSounds(){
  try{
    if(!soundRuntimeConfig){
      const all=await api("/api/settings");soundRuntimeConfig=all.general?.sound||{};
      const devices=await audioOutputDevices();
      soundRuntimeConfig.output_device=resolveSavedDeviceId(devices,soundRuntimeConfig.output_device,soundRuntimeConfig.output_device_label);
      soundRuntimeConfig.stream_output_device=resolveSavedDeviceId(devices,soundRuntimeConfig.stream_output_device,soundRuntimeConfig.stream_output_device_label);
    }
    const out=await api("/api/messages");
    const messages=Array.isArray(out.messages)?out.messages:[];
    if(!soundBaselineReady){messages.forEach(item=>soundSeen.add(soundMessageKey(item)));soundBaselineReady=true;return;}
    for(const item of messages){
      const key=soundMessageKey(item);if(soundSeen.has(key))continue;soundSeen.add(key);
      const name=configuredSoundForMessage(item,soundRuntimeConfig);
      const type=String(item.message_type||item.type||"chat").toLowerCase();
      const isAlert=!["chat","message","comment"].includes(type);
      if(name)playSoundForAudience(name,isAlert,soundRuntimeConfig);
    }
    if(soundSeen.size>600)soundSeen=new Set(messages.map(soundMessageKey));
  }catch(_){}
}
async function bootPage(){
  try{
    await (({dashboard:renderDashboard,platforms:renderPlatforms,chat:renderChat,obs_meld:renderObsMeld,spotify:renderSpotify,easyslider:renderEasyslider,overlays:renderOverlays,plugins:renderPlugins,settings:renderSettings,chattim3r:renderChattim3r,modalot:()=>renderDedicatedPlugin("modalot","Modalot",L("Moderation und Regeln zentral verwalten.","Manage moderation and rules centrally.")),info3ditor:()=>renderDedicatedPlugin("info3ditor","Info3ditor",L("Streaminformationen und Vorlagen verwalten.","Manage stream information and presets.")),dev:renderDev}[page]||renderDashboard)());
  }catch(e){
    try{
      await api("/api/client-error",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({level:"error",message:String(e&&e.stack||e)})});
    }catch(_){}
    shell(page,"Fehler","Die Oberfläche läuft weiter; Details stehen im DEV-Log.",`<section class="card"><div class="warnBox">${esc(String(e&&e.message||e||"Unbekannter Fehler"))}</div><div class="btnLine"><button onclick="location.reload()">Neu laden</button><a class="btn secondary" href="/dev">DEV-Log</a></div></section>`);
  }finally{
    if(page==="dashboard"){
      await finishStartupSplash();
      try{await api("/api/ui-ready",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}",timeoutMs:2000});}catch(_){ }
    }
  }
}
bootPage();
pollIncomingSounds();
setInterval(pollIncomingSounds,1000);
setInterval(()=>{
  if(page==="dashboard"||page==="chat") refreshMessages().catch(()=>{});
  if(page==="dashboard"||page==="spotify") refreshNowPlaying().catch(()=>{});
  if(page==="dashboard") refreshDashboardPluginStatuses().catch(()=>{});
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
