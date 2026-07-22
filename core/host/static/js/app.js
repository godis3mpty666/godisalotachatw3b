
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
const page = $("#app")?.dataset.page || "dashboard";
let settingsCache = null;
let statusCache = null;
let internalNavigation = false;
let shutdownInProgress = false;
// Startup timing can be tuned here without editing the splash markup or CSS.
const STARTUP_SPLASH={minVisibleMs:3900,fadeInMs:1350,fadeOutMs:1200,videoPlaybackRate:.78};
const windowsColorScheme=window.matchMedia?.("(prefers-color-scheme: light)");
let selectedColorScheme="system";
const COLOR_SCHEMES=["system","dark","light","neon","purple","ocean","forest","custom"];
const DEFAULT_CUSTOM_COLORS={background:"#070914",panel:"#111421",text:"#f7f8ff",accent:"#865cff",secondary:"#5fd7ff"};
function applyColorScheme(value,customColors=null){
  selectedColorScheme=COLOR_SCHEMES.includes(String(value))?String(value):"system";
  const effective=selectedColorScheme==="system"?(windowsColorScheme?.matches?"light":"dark"):selectedColorScheme;
  document.documentElement.dataset.colorScheme=effective;
  for(const name of ["--bg","--panel","--panel2","--soft","--line","--text","--muted","--purple","--cyan"])document.documentElement.style.removeProperty(name);
  if(effective==="custom"){
    const colors={...DEFAULT_CUSTOM_COLORS,...(customColors||{})};
    document.documentElement.style.setProperty("--bg",colors.background);
    document.documentElement.style.setProperty("--panel",colors.panel);
    document.documentElement.style.setProperty("--panel2",colors.panel);
    document.documentElement.style.setProperty("--soft",colors.panel);
    document.documentElement.style.setProperty("--line",colors.secondary);
    document.documentElement.style.setProperty("--text",colors.text);
    document.documentElement.style.setProperty("--muted",colors.text);
    document.documentElement.style.setProperty("--purple",colors.accent);
    document.documentElement.style.setProperty("--cyan",colors.secondary);
  }
  try{localStorage.setItem("godisalotachat.colorScheme",JSON.stringify({scheme:selectedColorScheme,custom_colors:customColors||{}}));}catch(_){}
}
function normalizedVolume(value){const number=Number(value);return Number.isFinite(number)?Math.max(0,Math.min(100,number)):100;}
try{const stored=JSON.parse(localStorage.getItem("godisalotachat.colorScheme")||"{}");applyColorScheme(stored.scheme||"system",stored.custom_colors);}catch(_){applyColorScheme("system");}
windowsColorScheme?.addEventListener?.("change",()=>{if(selectedColorScheme==="system")applyColorScheme("system");});

function prepareStartupSplash(){
  const splash=$("#startupSplash");
  let alreadyShown=false;
  try{alreadyShown=sessionStorage.getItem("godisalotachat.startupSplashShown")==="1";}catch(_){}
  if(splash&&alreadyShown){splash.remove();return;}
  if(splash){
    try{sessionStorage.setItem("godisalotachat.startupSplashShown","1");}catch(_){}
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

function dashboardNavItems(){
  return [
    ["dashboard","Dashboard","/"],["platforms","Plattformen","/plattformen"],["chat","Chat","/chat"],["obs_meld","OBS/Meld Integration","/obs-meld-integration"],
    ["info3ditor","Info3ditor","/info3ditor"],["gam3pick3r","gam3pick3r","/gam3pick3r"],["chattim3r","Chattim3r","/chattim3r"],["commands","commands","/commands"],["plugins","Plugins","/plugins"],["modalot","Modalot","/modalot"],["easyslider","3asyslid3r","/3asyslid3r"],["endstream","3ndstr3am","/3ndstr3am"],["settings",L("Einstellungen","Settings"),"/einstellungen"],["tutorials","Tutorials","/tutorials"],["dev","DEV","/dev"]
  ];
}

function nav(active){
  const items = dashboardNavItems();
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
function chatBadges(m){return (Array.isArray(m?.badges)?m.badges:[]).map(b=>{const url=String(b.url||"").trim();if(!url)return "";const title=esc(b.title||b.kind||"Badge");return `<span class="chatRoleBadge" title="${title}"><img src="${esc(url)}" alt="${title}"></span>`;}).join("");}
function platformLabel(p){return ({timer:L("Timer (plattformunabhängig)","Timer (platform-independent)"),twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick",spotify:"Spotify",openai:"ChatGPT / OpenAI",meld:"Meld",obs:"OBS"}[p]||p);}
function defaultEasysliderSettings(){return {enabled:true,edge:"left",delaySeconds:2,opacity:82,buttons:dashboardNavItems().map(([id,label,path])=>({id,label,path,enabled:true}))};}
function normalizeEasysliderClient(cfg){
  const d=defaultEasysliderSettings();
  cfg=cfg&&typeof cfg==="object"?cfg:{};
  const edge=["left","right","top","bottom"].includes(cfg.edge)?cfg.edge:d.edge;
  const delay=Math.max(0,Math.min(120,Number(cfg.delaySeconds??d.delaySeconds)||0));
  const opacity=Math.max(0,Math.min(100,Number(cfg.opacity??d.opacity)||0));
  const rawButtons=Array.isArray(cfg.buttons)?cfg.buttons:[];
  const savedById=new Map(rawButtons.map(b=>[String(b.id||"").trim(),b]).filter(([id])=>id));
  const seen=new Set();
  const cleanButton=b=>{const id=String(b.id||"").trim()||"dashboard";let path=String(b.path||"/").trim()||"/";if(id==="modalot"&&path==="/plugins?plugin=modalot")path="/modalot";return {id,label:String(b.label||b.id||"Dashboard").trim(),path,enabled:b.enabled!==false};};
  const buttons=d.buttons.map(base=>{seen.add(base.id);return cleanButton({...base,...(savedById.get(base.id)||{})});});
  rawButtons.forEach(raw=>{const b=cleanButton(raw);if(!seen.has(b.id)){seen.add(b.id);buttons.push(b);}});
  return {enabled:cfg.enabled!==false,edge,delaySeconds:delay,opacity,buttons};
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
  el.innerHTML=(m.messages||[]).filter(x=>x.message_type==="chat"||x.message_type==="moderation_notice").map(x=>showModeration?`<div class="msg dashboardChatMsg">${platformBadge(x.platform)}${moderation(x)} ${chatBadges(x)}<b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: <span class="dashboardChatText">${x.html||esc(x.text)}</span></div>`:`<div class="msg">${platformBadge(x.platform)} <span class="small">${esc(x.time)}</span> · ${chatBadges(x)}<b style="color:${userColor(x.platform,x.user)}">${esc(x.user)}</b>: ${x.html||esc(x.text)}</div>`).join("");
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
  const status=(detail=true)=>`<span class="small" data-platform-status="${esc(p)}" data-status-detail="${detail?"1":"0"}">${L("Status","Status")}: ${esc(localizedPlatformStatus(cfg,detail))}</span>`;
  if(p==="tiktok") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("main",L("Hauptkonto/Kanal","Main/Channel"),cfg.main)}${field("bot",L("Botkonto","Bot account"),cfg.bot)}<div class="platformSubBox"><b>${L("Testkanal / fremden Livestream lesen","Read test channel / external livestream")}</b><div class="testChannelFields">${sel("test_channel_enabled",L("Testkanal aktiv","Test channel active"),cfg.test_channel_enabled ?? false)}${field("test_channel",L("Testkanal ohne @","Test channel without @"),cfg.test_channel || "")}</div><div class="hint testChannelHint">${L("Wenn aktiviert, liest das TikTok-Chatplugin Chat, Beitritte, Likes, Geschenke, Follows und Shares aus diesem Kanal. Damit kannst du Warnungen testen, ohne mit deinem eigenen Konto live zu gehen. Der angegebene Kanal muss gerade live sein.","When enabled, the TikTok chat plugin reads chat, joins, likes, gifts, follows and shares from this channel. This lets you test alerts without going live on your own account. The specified channel must currently be live.")}</div></div><div class="hint">${L("TikTok verwendet getrennte gespeicherte Browserprofile für Hauptkonto und Bot. Es gibt keine Redirect-URL. Beim Anmelden öffnet sich die TikTok-Anmeldeseite, auf der du dich beispielsweise per QR-Code anmelden kannst.","TikTok uses separate saved browser profiles for the main account and bot. There is no redirect URL. Signing in opens the TikTok login page, where you can sign in using a QR code, for example.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="btn tiktokLogin" data-account="main">${L("Hauptkonto anmelden","Sign in main")}</button><button type="button" class="btn tiktokLogin" data-account="bot">${L("Bot anmelden","Sign in bot")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Hauptkonto trennen","Disconnect main")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">${L("Bot trennen","Disconnect bot")}</button>${status()}</div></form>`;
  if(p==="meld") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("host","Host",cfg.host||"127.0.0.1")}${field("port","Port",cfg.port||"13376")}<div class="hint">${L("Meld Studio benötigt keine Anmeldedaten. Es wird ausschließlich über einen lokalen WebSocket verbunden.","Meld Studio does not require login credentials. It connects exclusively through a local WebSocket.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testMeld">${L("Verbindung testen","Test connection")}</button>${status()}</div></form>`;
  if(p==="obs") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("host","Host",cfg.host||"127.0.0.1")}${field("port","Port",cfg.port||"4455")}${field("password",L("Passwort","Password"),cfg.password,"password")}<div class="hint">${L("OBS-WebSocket-Standard:","OBS WebSocket default:")} <b>ws://127.0.0.1:4455</b>. ${L("In OBS muss der WebSocket-Server unter Werkzeuge > WebSocket-Servereinstellungen aktiviert sein.","In OBS, the WebSocket server must be enabled under Tools > WebSocket Server Settings.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testObs">${L("Verbindung testen","Test connection")}</button>${status()}</div></form>`;
  if(p==="spotify") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri||"http://127.0.0.1:5173/callback")}<div class="hint">${L("Spotify benötigt keinen Kontonamen. Die Redirect-URI kann manuell eingestellt werden und wird genau so für OAuth verwendet.","Spotify does not require an account name. The redirect URI can be configured manually and is used exactly as entered for OAuth.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><a class="btn login" data-platform="${p}" data-account="main" href="#">${L("Spotify anmelden","Sign in to Spotify")}</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Trennen","Disconnect")}</button>${devButton(p)}${status(false)}</div></form>`;
  if(p==="openai") return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("api_key","API key",cfg.api_key,"password")}${field("organization",L("Organisations-ID (optional)","Organization ID (optional)"),cfg.organization)}${field("project",L("Projekt-ID (optional)","Project ID (optional)"),cfg.project)}<div class="hint">${L("Der API-Key wird lokal in data/settings.json gespeichert. Ein ChatGPT-Abonnement enthält nicht automatisch API-Guthaben. Beim Verbinden wird nur die Modellliste der offiziellen OpenAI-API abgerufen; es wird keine Antwort erzeugt. Das Modell wählst du im jeweiligen Plugin.","The API key is stored locally in data/settings.json. A ChatGPT subscription does not automatically include API credit. Connecting only retrieves the model list from the official OpenAI API; no response is generated. Select the model in the relevant plugin.")}</div><div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary testOpenAI">${L("ChatGPT verbinden","Connect ChatGPT")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("ChatGPT trennen","Disconnect ChatGPT")}</button>${devButton(p)}${status()}</div></form>`;
  return `<form class="platformForm" data-platform="${p}">${enabled}${auto}${field("main",L("Hauptkonto/Kanal","Main/Channel"),cfg.main)}${field("bot","Bot",cfg.bot)}${field("client_id","Client ID",cfg.client_id)}${field("client_secret","Client Secret",cfg.client_secret,"password")}${redirectFieldOnly("Redirect URI",cfg.redirect_uri)}<div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><a class="btn login" data-platform="${p}" data-account="main" href="#">OAuth Main</a><a class="btn login" data-platform="${p}" data-account="bot" href="#">OAuth Bot</a><button type="button" class="secondary disconnect" data-platform="${p}" data-account="main">${L("Hauptkonto trennen","Disconnect main")}</button><button type="button" class="secondary disconnect" data-platform="${p}" data-account="bot">${L("Bot trennen","Disconnect bot")}</button>${devButton(p)}${status(false)}</div></form>`;
}
async function renderPlatforms(){
  const settings=settingsCache=await api("/api/settings");
  const status={platforms:{}};
  const p=settings.platforms||{};
  shell("platforms",L("Plattformen","Platforms"),L("Anmeldedaten bleiben im Ordner webbased/data.","Login data remains in the webbased/data folder."),["twitch","tiktok","youtube","kick","spotify","openai","meld","obs"].map(k=>`<section class="card platformCard"><h3>${platformLabel(k)}</h3>${platformForm(k,{...(p[k]||{}),...(status.platforms[k]||{})})}</section>`).join(""));
  api("/api/status").then(freshStatus=>{
    statusCache=freshStatus;
    $$('[data-platform-status]').forEach(el=>{
      const platform=el.dataset.platformStatus;
      const cfg={...(p[platform]||{}),...((freshStatus.platforms||{})[platform]||{})};
      el.textContent=`${L("Status","Status")}: ${localizedPlatformStatus(cfg,el.dataset.statusDetail==="1")}`;
    });
  }).catch(()=>{});
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
async function renderTutorials(){
  const all=await api("/api/settings");
  const spotify=(all.platforms=all.platforms||{},all.platforms.spotify=all.platforms.spotify||{});
  const twitch=(all.platforms.twitch=all.platforms.twitch||{});
  const kick=(all.platforms.kick=all.platforms.kick||{});
  const openai=(all.platforms.openai=all.platforms.openai||{});
  const tiktok=(all.platforms.tiktok=all.platforms.tiktok||{});
  const obs=(all.platforms.obs=all.platforms.obs||{});
  const meld=(all.platforms.meld=all.platforms.meld||{});
  const platforms=[
    {id:"spotify",name:"Spotify",icon:"spotify",description:"Create an app, enter credentials, and connect Spotify.",ready:true},
    {id:"twitch",name:"Twitch",icon:"twitch",description:"Developer app, OAuth accounts, and chat connection.",ready:true},
    {id:"kick",name:"Kick",icon:"kick",description:"Developer app, OAuth, and channel connection.",ready:true},
    {id:"youtube",name:"YouTube",icon:"youtube",description:"Google Cloud project, OAuth, and live chat."},
    {id:"tiktok",name:"TikTok",icon:"tiktok",description:"Browser login, channel selection, and chat access.",ready:true},
    {id:"obs",name:"OBS",icon:"obs",description:"Enable WebSocket and connect your local OBS instance.",ready:true},
    {id:"meld",name:"MELD",icon:"meld",description:"Connect MELD Studio through its local WebSocket.",ready:true},
    {id:"gpt",name:"GPT",icon:"openai",description:"Create an API key and connect the OpenAI API.",ready:true}
  ];
  const steps=[
    {title:"Open the Spotify Developer Dashboard",text:"Open the Spotify Developer Dashboard and click Create app.",image:"01_spotify_dashboard_create_app_crop.png"},
    {title:"Create your app",text:"Enter an app name and a short app description. Then create the app.",image:"02_spotify_create_app_form_context.png"},
    {title:"Copy Client ID and Client Secret",text:"Copy the Client ID and Client Secret from your Spotify app and paste them below.",image:"03_spotify_client_credentials_crop.png",credentials:true},
    {title:"Paste the Redirect URI in Spotify",text:"Copy the Redirect URI shown below, paste it into Redirect URIs in Spotify, and click Add.",image:"04_spotify_redirect_uri_crop.png",redirect:true},
    {title:"Save the Spotify app",text:"Save the Spotify app settings after the Redirect URI is added.",image:"05_spotify_save_button_crop.png",redirect:true},
    {title:"Save and connect Spotify",text:"Paste the Spotify credentials into godisalotachat, save them, and start the Spotify sign-in.",image:"06_spotify_webbased_save_connect_context.png",credentials:true,redirect:true,connect:true}
  ];
  const twitchSteps=[
    {title:"Open the Twitch Developer Console",text:"Sign in to the Twitch Developer Console. The account must have a verified email address and two-factor authentication enabled.",image:"01_twitch_entwicklerkonsole_oeffnen_markieren.png"},
    {title:"Register one application",text:"Open Applications, choose Register Your Application, enter a unique name, and select a suitable category. This application is used for both Main and Bot.",image:"02_twitch_anwendung_registrieren_markieren.png"},
    {title:"Add the OAuth Redirect URL",text:"Add the Redirect URL shown below under OAuth Redirect URLs and click Add before creating or saving the application.",image:"03_twitch_redirect_url_eintragen_markieren.png",redirect:true},
    {title:"Copy Client ID and create a Secret",text:"Open Manage for the application, copy the Client ID, click New Secret once, and copy the generated Client Secret.",image:"04_twitch_client_id_und_secret_markieren.png",credentials:true},
    {title:"Enter Main and Bot accounts",text:"Enter the Twitch login name of your broadcaster account and the separate Twitch login name used by your bot.",image:"05_twitch_main_und_botnamen_eintragen_markieren.png",accounts:true},
    {title:"Save and connect both accounts",text:"Save the shared application details, then sign in once with Main and once with Bot. Twitch will ask which account should authorize the application.",image:"06_twitch_main_und_bot_anmelden_markieren.png",connect:true}
  ];
  const kickSteps=[
    {title:"Open KICK Dev",text:"Sign in to KICK and open the developer area from your account settings.",image:"01_kick_entwicklerbereich_oeffnen_markieren.png"},
    {title:"Create one KICK application",text:"Create one application for godisalotachat. The same application is used for both Main and Bot.",image:"02_kick_anwendung_erstellen_markieren.png"},
    {title:"Add the Redirect URI",text:"Add the Redirect URI shown below to the application. It must match exactly for the OAuth flow.",image:"03_kick_redirect_uri_eintragen_markieren.png",redirect:true},
    {title:"Copy Client ID and Client Secret",text:"Copy the Client ID and Client Secret generated for your KICK application.",image:"04_kick_client_id_und_secret_markieren.png",credentials:true},
    {title:"Enter Main and Bot accounts",text:"Enter the KICK channel name used by the broadcaster and the separate account name used by the bot.",image:"05_kick_main_und_botnamen_eintragen_markieren.png",accounts:true},
    {title:"Save and connect both accounts",text:"Save the shared application details, then authorize Main and Bot separately.",image:"06_kick_main_und_bot_anmelden_markieren.png",connect:true}
  ];
  const gptSteps=[
    {title:"Open the OpenAI API Platform",text:"Sign in to the OpenAI API Platform. ChatGPT subscriptions and API billing are separate products.",image:"01_gpt_api_plattform_oeffnen_markieren.png"},
    {title:"Check API billing",text:"Open the API billing settings and add billing or prepaid credit if the API account has no available credit.",image:"02_gpt_api_abrechnung_einrichten_markieren.png"},
    {title:"Select a project and create a key",text:"Select the project that should own the key, open API Keys, and choose Create new secret key.",image:"03_gpt_projekt_und_api_key_erstellen_markieren.png"},
    {title:"Copy the API key",text:"Copy the secret key immediately. OpenAI shows the full secret only once. Organization and Project IDs are optional here.",image:"04_gpt_api_key_kopieren_markieren.png",credentials:true},
    {title:"Save and connect the OpenAI API",text:"Save the key locally and test it by loading the available model list. This test does not generate a paid model response.",image:"05_gpt_speichern_und_verbinden_markieren.png",credentials:true,connect:true}
  ];
  const tiktokSteps=[
    {title:"Enter Main and Bot account names",text:"Enter both TikTok usernames without the @ sign. Main is your broadcaster account; Bot is the separate account used for bot actions.",image:"01_tiktok_haupt_und_botnamen_eintragen_markieren.png",accounts:true},
    {title:"Sign in the Main account",text:"Save the account names, open the Main login window, and sign in with the broadcaster account. If TikTok shows a QR code, scan it with the matching account.",image:"02_tiktok_hauptkonto_anmelden_und_qr_code_markieren.png",mainLogin:true},
    {title:"Sign in the Bot account",text:"Open the separate Bot login window and sign in with the bot account. Check carefully that the browser is not still using the Main account.",image:"03_tiktok_botkonto_anmelden_und_qr_code_markieren.png",botLogin:true},
    {title:"Configure an optional test channel",text:"Enable Test channel only when you want to read another live channel for testing. Enter its username without @. The selected channel must currently be live.",image:"04_tiktok_testkanal_aktivieren_und_namen_markieren.png",testChannel:true},
    {title:"Save and check the connection",text:"Save the settings. The active read channel is the test channel when enabled; otherwise it is your Main account. Check the platform status after the selected channel goes live.",image:"05_tiktok_speichern_und_status_pruefen_markieren.png",accounts:true,testChannel:true,connect:true}
  ];
  const obsSteps=[
    {title:"Open the Tools menu in OBS",text:"Start OBS Studio and open Tools in the top menu bar.",image:"01_obs_werkzeuge_menue_markieren.png"},
    {title:"Open WebSocket Server Settings",text:"Choose WebSocket Server Settings. OBS Studio 28 and newer already include obs-websocket.",image:"02_obs_websocket_servereinstellungen_markieren.png"},
    {title:"Enable the WebSocket server",text:"Enable the WebSocket server and keep authentication enabled. A password prevents unauthorized programs from controlling OBS.",image:"03_obs_websocket_server_und_authentifizierung_aktivieren_markieren.png"},
    {title:"Copy port and password",text:"Keep the server port, normally 4455, and copy or set the WebSocket password. Show Connect Info can display the current connection information.",image:"04_obs_port_passwort_und_verbindungsinfo_markieren.png"},
    {title:"Save and test the OBS connection",text:"Enter host, port, and password below, save them, and test the local WebSocket connection.",image:"05_obs_daten_eintragen_speichern_und_testen_markieren.png",credentials:true,connect:true}
  ];
  const meldSteps=[
    {title:"Open MELD Settings",text:"Start MELD Studio and open Settings.",image:"01_meld_einstellungen_oeffnen_markieren.png"},
    {title:"Allow remote connections",text:"Open Advanced and enable Allow remote connections. This starts MELD's local WebChannel interface.",image:"02_meld_erweitert_remote_verbindungen_aktivieren_markieren.png"},
    {title:"Save and test the MELD connection",text:"Keep the local defaults 127.0.0.1 and port 13376, save them in godisalotachat, and test the connection.",image:"03_meld_speichern_und_verbindung_testen_markieren.png",connect:true}
  ];
  const tutorialDe={
    "Create an app, enter credentials, and connect Spotify.":"App anlegen, Zugangsdaten eintragen und Spotify verbinden.","Developer app, OAuth accounts, and chat connection.":"Entwickler-App, OAuth-Konten und Chatverbindung einrichten.","Developer app, OAuth, and channel connection.":"Entwickler-App, OAuth und Kanalverbindung einrichten.","Google Cloud project, OAuth, and live chat.":"Google-Cloud-Projekt, OAuth und Livechat einrichten.","Browser login, channel selection, and chat access.":"Browser-Anmeldung, Kanalauswahl und Chat-Zugriff einrichten.","Enable WebSocket and connect your local OBS instance.":"WebSocket aktivieren und die lokale OBS-Instanz verbinden.","Connect MELD Studio through its local WebSocket.":"MELD Studio über den lokalen WebSocket verbinden.","Create an API key and connect the OpenAI API.":"API-Key erstellen und die OpenAI API verbinden.",
    "Open the Spotify Developer Dashboard":"Spotify Developer Dashboard öffnen","Open the Spotify Developer Dashboard and click Create app.":"Öffne das Spotify Developer Dashboard und klicke auf Create app.","Create your app":"App erstellen","Enter an app name and a short app description. Then create the app.":"Trage einen App-Namen und eine kurze Beschreibung ein und erstelle anschließend die App.","Add the Redirect URI":"Redirect URI hinzufügen","Open the app settings, add the Redirect URI shown below under Redirect URIs, and save it.":"Öffne die App-Einstellungen, trage die unten angezeigte Redirect URI unter Redirect URIs ein und speichere sie.","Copy the Client ID":"Client ID kopieren","Copy the Client ID from your Spotify app and paste it below.":"Kopiere die Client ID aus deiner Spotify-App und füge sie unten ein.","Copy the Client Secret":"Client Secret kopieren","Click View client secret, copy the Client Secret, and paste it below.":"Klicke auf View client secret, kopiere das Client Secret und füge es unten ein.","Save and connect Spotify":"Spotify speichern und verbinden","Save the app settings, then save your credentials and start the Spotify sign-in.":"Speichere die App-Einstellungen und Zugangsdaten und starte anschließend die Spotify-Anmeldung.",
    "Open the Twitch Developer Console":"Twitch Developer Console öffnen","Sign in to the Twitch Developer Console. The account must have a verified email address and two-factor authentication enabled.":"Melde dich in der Twitch Developer Console an. Das Konto benötigt eine bestätigte E-Mail-Adresse und aktivierte Zwei-Faktor-Authentifizierung.","Register one application":"Eine Anwendung registrieren","Open Applications, choose Register Your Application, enter a unique name, and select a suitable category. This application is used for both Main and Bot.":"Öffne Applications, wähle Register Your Application, vergib einen eindeutigen Namen und wähle eine passende Kategorie. Diese App wird für Main und Bot verwendet.","Add the OAuth Redirect URL":"OAuth Redirect URL hinzufügen","Add the Redirect URL shown below under OAuth Redirect URLs and click Add before creating or saving the application.":"Trage die unten angezeigte Redirect URL unter OAuth Redirect URLs ein und klicke vor dem Erstellen oder Speichern der App auf Add.","Copy Client ID and create a Secret":"Client ID kopieren und Secret erstellen","Open Manage for the application, copy the Client ID, click New Secret once, and copy the generated Client Secret.":"Öffne Manage für die App, kopiere die Client ID, klicke einmal auf New Secret und kopiere das erzeugte Client Secret.","Enter Main and Bot accounts":"Main- und Botkonten eintragen","Enter the Twitch login name of your broadcaster account and the separate Twitch login name used by your bot.":"Trage den Twitch-Anmeldenamen deines Hauptkontos und den separaten Anmeldenamen des Botkontos ein.","Save and connect both accounts":"Beide Konten speichern und verbinden","Save the shared application details, then sign in once with Main and once with Bot. Twitch will ask which account should authorize the application.":"Speichere die gemeinsamen App-Daten und melde anschließend Main und Bot getrennt an. Twitch fragt jeweils, welches Konto die App autorisieren soll.",
    "Open KICK Dev":"KICK Dev öffnen","Sign in to KICK and open the developer area from your account settings.":"Melde dich bei KICK an und öffne den Entwicklerbereich in deinen Kontoeinstellungen.","Create one KICK application":"Eine KICK-Anwendung erstellen","Create one application for godisalotachat. The same application is used for both Main and Bot.":"Erstelle eine Anwendung für godisalotachat. Dieselbe Anwendung wird für Main und Bot verwendet.","Add the Redirect URI":"Redirect URI hinzufügen","Add the Redirect URI shown below to the application. It must match exactly for the OAuth flow.":"Trage die unten angezeigte Redirect URI in der Anwendung ein. Sie muss für OAuth exakt übereinstimmen.","Copy Client ID and Client Secret":"Client ID und Client Secret kopieren","Copy the Client ID and Client Secret generated for your KICK application.":"Kopiere Client ID und Client Secret deiner KICK-Anwendung.","Enter the KICK channel name used by the broadcaster and the separate account name used by the bot.":"Trage den KICK-Kanalnamen des Hauptkontos und den separaten Kontonamen des Bots ein.","Save the shared application details, then authorize Main and Bot separately.":"Speichere die gemeinsamen App-Daten und autorisiere Main und Bot anschließend getrennt.",
    "Open the OpenAI API Platform":"OpenAI API-Plattform öffnen","Sign in to the OpenAI API Platform. ChatGPT subscriptions and API billing are separate products.":"Melde dich auf der OpenAI API-Plattform an. ChatGPT-Abonnements und API-Abrechnung sind getrennte Produkte.","Check API billing":"API-Abrechnung prüfen","Open the API billing settings and add billing or prepaid credit if the API account has no available credit.":"Öffne die API-Abrechnung und hinterlege eine Zahlungsmethode oder Prepaid-Guthaben, falls kein API-Guthaben verfügbar ist.","Select a project and create a key":"Projekt auswählen und Key erstellen","Select the project that should own the key, open API Keys, and choose Create new secret key.":"Wähle das Projekt für den Key, öffne API Keys und klicke auf Create new secret key.","Copy the API key":"API-Key kopieren","Copy the secret key immediately. OpenAI shows the full secret only once. Organization and Project IDs are optional here.":"Kopiere den geheimen Key sofort. OpenAI zeigt ihn vollständig nur einmal an. Organization- und Project-ID sind hier optional.","Save and connect the OpenAI API":"OpenAI API speichern und verbinden","Save the key locally and test it by loading the available model list. This test does not generate a paid model response.":"Speichere den Key lokal und teste ihn durch Laden der verfügbaren Modellliste. Dabei wird keine kostenpflichtige Modellantwort erzeugt.",
    "Enter Main and Bot account names":"Main- und Botnamen eintragen","Enter both TikTok usernames without the @ sign. Main is your broadcaster account; Bot is the separate account used for bot actions.":"Trage beide TikTok-Namen ohne @ ein. Main ist dein Hauptkonto, Bot das getrennte Konto für Botaktionen.","Sign in the Main account":"Hauptkonto anmelden","Save the account names, open the Main login window, and sign in with the broadcaster account. If TikTok shows a QR code, scan it with the matching account.":"Speichere die Kontonamen, öffne das Main-Anmeldefenster und melde das Hauptkonto an. Zeigt TikTok einen QR-Code, scanne ihn mit dem passenden Konto.","Sign in the Bot account":"Botkonto anmelden","Open the separate Bot login window and sign in with the bot account. Check carefully that the browser is not still using the Main account.":"Öffne das getrennte Bot-Anmeldefenster und melde das Botkonto an. Prüfe genau, dass der Browser nicht noch das Hauptkonto verwendet.","Configure an optional test channel":"Optionalen Testkanal einrichten","Enable Test channel only when you want to read another live channel for testing. Enter its username without @. The selected channel must currently be live.":"Aktiviere den Testkanal nur, wenn du einen anderen Livekanal zum Testen lesen möchtest. Trage den Namen ohne @ ein. Der Kanal muss gerade live sein.","Save and check the connection":"Speichern und Verbindung prüfen","Save the settings. The active read channel is the test channel when enabled; otherwise it is your Main account. Check the platform status after the selected channel goes live.":"Speichere die Einstellungen. Bei aktiviertem Testkanal wird dieser gelesen, sonst dein Hauptkonto. Prüfe den Plattformstatus, sobald der gewählte Kanal live ist.",
    "Open the Tools menu in OBS":"Werkzeuge-Menü in OBS öffnen","Start OBS Studio and open Tools in the top menu bar.":"Starte OBS Studio und öffne Werkzeuge in der oberen Menüleiste.","Open WebSocket Server Settings":"WebSocket-Servereinstellungen öffnen","Choose WebSocket Server Settings. OBS Studio 28 and newer already include obs-websocket.":"Wähle WebSocket-Servereinstellungen. Ab OBS Studio 28 ist obs-websocket bereits enthalten.","Enable the WebSocket server":"WebSocket-Server aktivieren","Enable the WebSocket server and keep authentication enabled. A password prevents unauthorized programs from controlling OBS.":"Aktiviere den WebSocket-Server und lasse die Authentifizierung eingeschaltet. Das Passwort schützt OBS vor unerlaubter Steuerung.","Copy port and password":"Port und Passwort kopieren","Keep the server port, normally 4455, and copy or set the WebSocket password. Show Connect Info can display the current connection information.":"Übernimm den Server-Port, normalerweise 4455, und kopiere oder setze das WebSocket-Passwort. Show Connect Info zeigt die aktuellen Verbindungsdaten.","Save and test the OBS connection":"OBS-Verbindung speichern und testen","Enter host, port, and password below, save them, and test the local WebSocket connection.":"Trage unten Host, Port und Passwort ein, speichere sie und teste die lokale WebSocket-Verbindung.",
    "Open MELD Settings":"MELD-Einstellungen öffnen","Start MELD Studio and open Settings.":"Starte MELD Studio und öffne die Einstellungen.","Allow remote connections":"Remote-Verbindungen erlauben","Open Advanced and enable Allow remote connections. This starts MELD's local WebChannel interface.":"Öffne Erweitert bzw. Advanced und aktiviere Allow remote connections. Dadurch startet MELDs lokale WebChannel-Schnittstelle.","Save and test the MELD connection":"MELD-Verbindung speichern und testen","Keep the local defaults 127.0.0.1 and port 13376, save them in godisalotachat, and test the connection.":"Behalte die lokalen Standardwerte 127.0.0.1 und Port 13376 bei, speichere sie in godisalotachat und teste die Verbindung."
  };
  Object.assign(tutorialDe,{
    "Copy Client ID and Client Secret":"Client ID und Client Secret kopieren",
    "Copy the Client ID and Client Secret from your Spotify app and paste them below.":"Kopiere Client ID und Client Secret aus deiner Spotify-App und fuege beide unten ein.",
    "Paste the Redirect URI in Spotify":"Redirect URI in Spotify einfuegen",
    "Copy the Redirect URI shown below, paste it into Redirect URIs in Spotify, and click Add.":"Kopiere die unten angezeigte Redirect URI, fuege sie in Spotify unter Redirect URIs ein und klicke auf Add.",
    "Save the Spotify app":"Spotify-App speichern",
    "Save the Spotify app settings after the Redirect URI is added.":"Speichere die Spotify-App-Einstellungen, nachdem die Redirect URI hinzugefuegt wurde.",
    "Paste the Spotify credentials into godisalotachat, save them, and start the Spotify sign-in.":"Fuege die Spotify-Zugangsdaten in godisalotachat ein, speichere sie und starte die Spotify-Anmeldung."
  });
  const tutorialCopy=value=>L(tutorialDe[String(value)]||String(value),String(value));
  const tutorialCounter=(index,total)=>L(`Schritt ${index+1} von ${total}`,`Step ${index+1} of ${total}`);
  const showOverview=()=>{
    shell("tutorials","Tutorials",L("Wähle eine Plattform, um die geführte Einrichtung zu starten.","Choose a platform to start its guided setup."),`<section class="card tutorialOverview"><div class="tutorialOverviewHead"><h3>${L("Plattform auswählen","Choose a platform")}</h3><p>${L("Jede Plattform besitzt eine eigene Schritt-für-Schritt-Einrichtung.","Each platform has its own step-by-step setup.")}</p></div><div class="tutorialPlatformGrid">${platforms.map(item=>`<button type="button" class="tutorialPlatformCard ${item.ready?"ready":"coming"}" data-tutorial-platform="${item.id}" ${item.ready?"":"disabled"}><img src="/platform-icon/${encodeURIComponent(item.icon)}" alt="${esc(item.name)}" onerror="this.onerror=null;this.src='/static/img/app.png'"><span><b>${esc(item.name)}</b><small>${esc(tutorialCopy(item.description))}</small></span><em>${item.ready?L("Tutorial starten","Start tutorial"):L("Demnächst","Coming soon")}</em></button>`).join("")}</div></section>`);
    const spotifyButton=$('[data-tutorial-platform="spotify"]');
    if(spotifyButton)spotifyButton.onclick=showSpotify;
    const twitchButton=$('[data-tutorial-platform="twitch"]');
    if(twitchButton)twitchButton.onclick=showTwitch;
    const kickButton=$('[data-tutorial-platform="kick"]');
    if(kickButton)kickButton.onclick=showKick;
    const gptButton=$('[data-tutorial-platform="gpt"]');
    if(gptButton)gptButton.onclick=showGpt;
    const tiktokButton=$('[data-tutorial-platform="tiktok"]');
    if(tiktokButton)tiktokButton.onclick=showTiktok;
    const obsButton=$('[data-tutorial-platform="obs"]');
    if(obsButton)obsButton.onclick=showObs;
    const meldButton=$('[data-tutorial-platform="meld"]');
    if(meldButton)meldButton.onclick=showMeld;
  };
  const showSpotify=()=>{
  let index=0;
  shell("tutorials","Tutorials",L("Spotify Schritt für Schritt einrichten.","Spotify setup — guided step by step."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="Spotify setup step"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" class="secondary" id="tutorialDashboard">${L("Spotify Dashboard öffnen","Open Spotify Dashboard")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
  const render=()=>{
    const step=steps[index];
    $("#tutorialSteps").innerHTML=steps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");
    $("#tutorialCounter").textContent=tutorialCounter(index,steps.length);
    $("#tutorialTitle").textContent=tutorialCopy(step.title);
    $("#tutorialText").textContent=tutorialCopy(step.text);
    $("#tutorialImage").src=`/tutorial-asset/spotify/${encodeURIComponent(step.image)}`;
    $("#tutorialImage").alt=tutorialCopy(step.title);
    $("#tutorialProgressBar").style.width=`${(index+1)/steps.length*100}%`;
    const redirect=esc(spotify.redirect_uri||"http://127.0.0.1:5173/callback");
    $("#tutorialFields").innerHTML=`${step.redirect?`<label><div>Redirect URI</div><input id="tutorialRedirect" value="${redirect}" autocomplete="off"></label>`:""}${step.credentials?`<label><div>Client ID</div><input id="tutorialClientId" value="${esc(spotify.client_id||"")}" autocomplete="off"></label><label><div>Client Secret</div><input id="tutorialClientSecret" type="password" value="${esc(spotify.client_secret||"")}" autocomplete="off"></label>`:""}`;
    $("#tutorialPrev").disabled=index===0;
    $("#tutorialNext").textContent=step.connect?L("Spotify speichern & verbinden","Save & connect Spotify"):L("Weiter","Next");
    $$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});
  };
  const capture=()=>{
    const redirect=$("#tutorialRedirect"),clientId=$("#tutorialClientId"),clientSecret=$("#tutorialClientSecret");
    if(redirect)spotify.redirect_uri=redirect.value.trim();
    if(clientId)spotify.client_id=clientId.value.trim();
    if(clientSecret)spotify.client_secret=clientSecret.value.trim();
  };
  const save=async()=>{
    capture();spotify.enabled=true;spotify.autoconnect=true;
    return api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});
  };
  $("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};
  $("#tutorialOverviewBack").onclick=showOverview;
  $("#tutorialDashboard").onclick=()=>openExternal("https://developer.spotify.com/dashboard");
  $("#tutorialNext").onclick=async()=>{
    capture();
    if(index<steps.length-1){index++;render();return;}
    const result=$("#tutorialResult");result.textContent=L("Spotify-Einstellungen werden gespeichert...","Saving Spotify settings...");
    if(!spotify.client_id||!spotify.client_secret){result.textContent=L("Client ID und Client Secret werden benötigt.","Client ID and Client Secret are required.");return;}
    const saved=await save();
    if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
    result.textContent=L("Gespeichert. Spotify-Anmeldung wird geöffnet...","Saved. Opening Spotify sign-in...");
    const opened=await api("/api/oauth/open/spotify/main",{timeoutMs:2500});
    if(!opened.ok)result.textContent=L("Gespeichert, aber die Spotify-Anmeldung konnte nicht geöffnet werden: ","Saved, but Spotify sign-in could not be opened: ")+(opened.error||L("Unbekannter Fehler","Unknown error"));
  };
  render();
  };
  const showTwitch=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("Twitch einrichten – eine App, zwei Konto-Autorisierungen.","Twitch setup — one application, two account authorizations."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="Twitch setup step"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" class="secondary" id="tutorialDashboard">${L("Twitch Developer Console öffnen","Open Twitch Developer Console")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{
      const redirect=$("#tutorialRedirect"),clientId=$("#tutorialClientId"),clientSecret=$("#tutorialClientSecret"),main=$("#tutorialMainAccount"),bot=$("#tutorialBotAccount");
      if(redirect){twitch.redirect_uri=redirect.value.trim();twitch.redirect_url=twitch.redirect_uri;}
      if(clientId)twitch.client_id=clientId.value.trim();
      if(clientSecret)twitch.client_secret=clientSecret.value.trim();
      if(main){twitch.main=main.value.trim().replace(/^@/,"");twitch.main_account=twitch.main;twitch.channel=twitch.main;}
      if(bot){twitch.bot=bot.value.trim().replace(/^@/,"");twitch.bot_account=twitch.bot;twitch.bot_username=twitch.bot;}
    };
    const save=async()=>{
      capture();twitch.enabled=true;twitch.autoconnect=true;
      return api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});
    };
    const saveAndLogin=async account=>{
      const result=$("#tutorialResult");
      capture();
      if(!twitch.client_id||!twitch.client_secret||!twitch.main||!twitch.bot){result.textContent=L("Client ID, Client Secret, Hauptkonto und Botkonto werden benötigt.","Client ID, Client Secret, Main account, and Bot account are required.");return;}
      result.textContent=L("Twitch-Einstellungen werden gespeichert...","Saving Twitch settings...");
      const saved=await save();
      if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      result.textContent=L(`Gespeichert. Twitch-${account==='main'?"Hauptkonto":"Botkonto"}-Anmeldung wird geöffnet...`,`Saved. Opening Twitch ${account==='main'?"Main":"Bot"} sign-in...`);
      const opened=await api(`/api/oauth/open/twitch/${account}`,{timeoutMs:2500});
      if(!opened.ok)result.textContent=L("Gespeichert, aber die Twitch-Anmeldung konnte nicht geöffnet werden: ","Saved, but Twitch sign-in could not be opened: ")+(opened.error||L("Unbekannter Fehler","Unknown error"));
    };
    const render=()=>{
      const step=twitchSteps[index],redirect=esc(twitch.redirect_uri||twitch.redirect_url||"http://localhost:17564/callback/");
      $("#tutorialSteps").innerHTML=twitchSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");
      $("#tutorialCounter").textContent=tutorialCounter(index,twitchSteps.length);
      $("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);
      $("#tutorialImage").src=`/tutorial-asset/twitch/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);
      $("#tutorialProgressBar").style.width=`${(index+1)/twitchSteps.length*100}%`;
      const credentials=step.credentials||step.connect,accounts=step.accounts||step.connect;
      $("#tutorialFields").innerHTML=`${step.redirect||step.connect?`<label><div>OAuth Redirect URL</div><input id="tutorialRedirect" value="${redirect}" autocomplete="off"></label>`:""}${credentials?`<label><div>Client ID</div><input id="tutorialClientId" value="${esc(twitch.client_id||"")}" autocomplete="off"></label><label><div>Client Secret</div><input id="tutorialClientSecret" type="password" value="${esc(twitch.client_secret||"")}" autocomplete="off"></label>`:""}${accounts?`<label><div>${L("Name des Hauptkontos","Main account name")}</div><input id="tutorialMainAccount" value="${esc(twitch.main_account||twitch.main||"")}" autocomplete="off"></label><label><div>${L("Name des Botkontos","Bot account name")}</div><input id="tutorialBotAccount" value="${esc(twitch.bot_account||twitch.bot||"")}" autocomplete="off"></label>`:""}${step.connect?`<div class="tutorialConnectChoices"><button type="button" id="tutorialConnectMain">${L("Speichern & Hauptkonto anmelden","Save & sign in Main")}</button><button type="button" id="tutorialConnectBot">${L("Speichern & Botkonto anmelden","Save & sign in Bot")}</button></div>`:""}`;
      $("#tutorialPrev").disabled=index===0;$("#tutorialNext").hidden=!!step.connect;
      $$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});
      if(step.connect){$("#tutorialConnectMain").onclick=()=>saveAndLogin("main");$("#tutorialConnectBot").onclick=()=>saveAndLogin("bot");}
    };
    $("#tutorialOverviewBack").onclick=showOverview;
    $("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};
    $("#tutorialDashboard").onclick=()=>openExternal("https://dev.twitch.tv/console/apps");
    $("#tutorialNext").onclick=()=>{capture();if(index<twitchSteps.length-1){index++;render();}};
    render();
  };
  const showKick=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("KICK einrichten – eine App, zwei Konto-Autorisierungen.","KICK setup — one application, two account authorizations."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="KICK setup step"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" class="secondary" id="tutorialDashboard">${L("KICK Dev öffnen","Open KICK Dev")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{
      const redirect=$("#tutorialRedirect"),clientId=$("#tutorialClientId"),clientSecret=$("#tutorialClientSecret"),main=$("#tutorialMainAccount"),bot=$("#tutorialBotAccount");
      if(redirect){kick.redirect_uri=redirect.value.trim();kick.redirect_url=kick.redirect_uri;}
      if(clientId)kick.client_id=clientId.value.trim();if(clientSecret)kick.client_secret=clientSecret.value.trim();
      if(main){kick.main=main.value.trim().replace(/^@/,"");kick.main_account=kick.main;kick.channel=kick.main;}
      if(bot){kick.bot=bot.value.trim().replace(/^@/,"");kick.bot_account=kick.bot;kick.bot_username=kick.bot;}
    };
    const save=async()=>{capture();kick.enabled=true;kick.autoconnect=true;return api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});};
    const saveAndLogin=async account=>{
      const result=$("#tutorialResult");capture();
      if(!kick.client_id||!kick.client_secret||!kick.main||!kick.bot){result.textContent=L("Client ID, Client Secret, Hauptkonto und Botkonto werden benötigt.","Client ID, Client Secret, Main account, and Bot account are required.");return;}
      result.textContent=L("KICK-Einstellungen werden gespeichert...","Saving KICK settings...");const saved=await save();
      if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      result.textContent=L(`Gespeichert. KICK-${account==='main'?"Hauptkonto":"Botkonto"}-Anmeldung wird geöffnet...`,`Saved. Opening KICK ${account==='main'?"Main":"Bot"} sign-in...`);
      const opened=await api(`/api/oauth/open/kick/${account}`,{timeoutMs:2500});
      if(!opened.ok)result.textContent=L("Gespeichert, aber die KICK-Anmeldung konnte nicht geöffnet werden: ","Saved, but KICK sign-in could not be opened: ")+(opened.error||L("Unbekannter Fehler","Unknown error"));
    };
    const render=()=>{
      const step=kickSteps[index],redirect=esc(kick.redirect_uri||kick.redirect_url||"http://localhost:17865/kick/callback");
      $("#tutorialSteps").innerHTML=kickSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");
      $("#tutorialCounter").textContent=tutorialCounter(index,kickSteps.length);$("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);
      $("#tutorialImage").src=`/tutorial-asset/kick/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);$("#tutorialProgressBar").style.width=`${(index+1)/kickSteps.length*100}%`;
      const credentials=step.credentials||step.connect,accounts=step.accounts||step.connect;
      $("#tutorialFields").innerHTML=`${step.redirect||step.connect?`<label><div>Redirect URI</div><input id="tutorialRedirect" value="${redirect}" autocomplete="off"></label>`:""}${credentials?`<label><div>Client ID</div><input id="tutorialClientId" value="${esc(kick.client_id||"")}" autocomplete="off"></label><label><div>Client Secret</div><input id="tutorialClientSecret" type="password" value="${esc(kick.client_secret||"")}" autocomplete="off"></label>`:""}${accounts?`<label><div>${L("Name des Hauptkontos","Main account name")}</div><input id="tutorialMainAccount" value="${esc(kick.main_account||kick.main||"")}" autocomplete="off"></label><label><div>${L("Name des Botkontos","Bot account name")}</div><input id="tutorialBotAccount" value="${esc(kick.bot_account||kick.bot||"")}" autocomplete="off"></label>`:""}${step.connect?`<div class="tutorialConnectChoices"><button type="button" id="tutorialConnectMain">${L("Speichern & Hauptkonto anmelden","Save & sign in Main")}</button><button type="button" id="tutorialConnectBot">${L("Speichern & Botkonto anmelden","Save & sign in Bot")}</button></div>`:""}`;
      $("#tutorialPrev").disabled=index===0;$("#tutorialNext").hidden=!!step.connect;
      $$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});
      if(step.connect){$("#tutorialConnectMain").onclick=()=>saveAndLogin("main");$("#tutorialConnectBot").onclick=()=>saveAndLogin("bot");}
    };
    $("#tutorialOverviewBack").onclick=showOverview;$("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};
    $("#tutorialDashboard").onclick=()=>openExternal("https://dev.kick.com/");$("#tutorialNext").onclick=()=>{capture();if(index<kickSteps.length-1){index++;render();}};render();
  };
  const showGpt=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("OpenAI API einrichten – Projekt-Key erstellen und Verbindung prüfen.","OpenAI API setup — create a project key and verify the connection."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="OpenAI API setup step"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" class="secondary" id="tutorialDashboard">${L("OpenAI API Keys öffnen","Open OpenAI API Keys")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{const key=$("#tutorialApiKey"),org=$("#tutorialOrganization"),project=$("#tutorialProject");if(key)openai.api_key=key.value.trim();if(org)openai.organization=org.value.trim();if(project)openai.project=project.value.trim();};
    const saveAndConnect=async()=>{
      const result=$("#tutorialResult");capture();if(!openai.api_key){result.textContent=L("Ein OpenAI API-Key wird benötigt.","An OpenAI API key is required.");return;}
      openai.enabled=true;openai.autoconnect=true;delete openai.model;result.textContent=L("OpenAI API-Key wird gespeichert...","Saving the OpenAI API key...");
      const saved=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});
      if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      result.textContent=L("Gespeichert. OpenAI-API-Verbindung wird geprüft...","Saved. Checking the OpenAI API connection...");const checked=await api("/api/test-platform/openai",{timeoutMs:15000});
      result.textContent=checked.ok?L("Verbunden: ","Connected: ")+(checked.detail||L("OpenAI API-Key geprüft","OpenAI API key verified")):L("Verbindung fehlgeschlagen: ","Connection failed: ")+(checked.detail||checked.error||L("Unbekannter Fehler","Unknown error"));
    };
    const render=()=>{
      const step=gptSteps[index];$("#tutorialSteps").innerHTML=gptSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");
      $("#tutorialCounter").textContent=tutorialCounter(index,gptSteps.length);$("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);
      $("#tutorialImage").src=`/tutorial-asset/gpt/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);$("#tutorialProgressBar").style.width=`${(index+1)/gptSteps.length*100}%`;
      $("#tutorialFields").innerHTML=step.credentials?`<label><div>API-Key</div><input id="tutorialApiKey" type="password" value="${esc(openai.api_key||"")}" autocomplete="off"></label><label><div>${L("Organization ID (optional)","Organization ID (optional)")}</div><input id="tutorialOrganization" value="${esc(openai.organization||"")}" autocomplete="off"></label><label><div>${L("Project ID (optional)","Project ID (optional)")}</div><input id="tutorialProject" value="${esc(openai.project||"")}" autocomplete="off"></label>`:"";
      $("#tutorialPrev").disabled=index===0;$("#tutorialNext").textContent=step.connect?L("OpenAI API speichern & verbinden","Save & connect OpenAI API"):L("Weiter","Next");
      $$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});
    };
    $("#tutorialOverviewBack").onclick=showOverview;$("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};
    $("#tutorialDashboard").onclick=()=>openExternal("https://platform.openai.com/api-keys");$("#tutorialNext").onclick=()=>{capture();if(index<gptSteps.length-1){index++;render();}else saveAndConnect();};render();
  };
  const showTiktok=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("TikTok einrichten – getrennte Browserprofile für Main und Bot.","TikTok setup — separate browser profiles for Main and Bot."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="TikTok setup step"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{
      const main=$("#tutorialMainAccount"),bot=$("#tutorialBotAccount"),testEnabled=$("#tutorialTestEnabled"),testChannel=$("#tutorialTestChannel");
      if(main){tiktok.main=main.value.trim().replace(/^@/,"");tiktok.main_account=tiktok.main;tiktok.unique_id=tiktok.main;}
      if(bot){tiktok.bot=bot.value.trim().replace(/^@/,"");tiktok.bot_account=tiktok.bot;}
      if(testEnabled)tiktok.test_channel_enabled=testEnabled.checked;
      if(testChannel)tiktok.test_channel=testChannel.value.trim().replace(/^@/,"");
      const useTest=!!tiktok.test_channel_enabled&&!!tiktok.test_channel;
      tiktok.active_read_channel=useTest?tiktok.test_channel:(tiktok.main_account||"");
      tiktok.live_url=tiktok.active_read_channel?`https://www.tiktok.com/@${tiktok.active_read_channel}/live`:"";
      tiktok.resolved_live_url=tiktok.live_url;
    };
    const save=async()=>{capture();tiktok.enabled=true;tiktok.autoconnect=true;return api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});};
    const saveAndOpen=async account=>{
      const result=$("#tutorialResult");capture();const accountName=account==="main"?tiktok.main:tiktok.bot;
      if(!accountName){result.textContent=L(`Trage zuerst den Namen des ${account==='main'?"Hauptkontos":"Botkontos"} ein.`,`Enter the ${account==='main'?"Main":"Bot"} account name first.`);return;}
      result.textContent=L("TikTok-Einstellungen werden gespeichert...","Saving TikTok settings...");const saved=await save();if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      result.textContent=L(`Das getrennte ${account==='main'?"Hauptkonto":"Botkonto"}-Anmeldefenster wird geöffnet...`,`Opening the separate ${account==='main'?"Main":"Bot"} login window...`);
      const opened=await api(`/api/tiktok/open/${account}`,{timeoutMs:10000});
      result.textContent=opened.ok?(opened.already_logged_in?L(`${account==='main'?"Hauptkonto":"Botkonto"} ist bereits angemeldet.`,`${account==='main'?"Main":"Bot"} is already signed in.`):L(`${account==='main'?"Hauptkonto":"Botkonto"}-Anmeldefenster geöffnet. Schließe die Anmeldung dort ab.`,`${account==='main'?"Main":"Bot"} login window opened. Complete the login there.`)):L("TikTok konnte nicht geöffnet werden: ","Could not open TikTok: ")+(opened.error||L("Unbekannter Fehler","Unknown error"));
    };
    const saveFinal=async()=>{
      const result=$("#tutorialResult");capture();if(!tiktok.main||!tiktok.bot){result.textContent=L("Hauptkonto und Botkonto werden benötigt.","Main and Bot account names are required.");return;}
      if(tiktok.test_channel_enabled&&!tiktok.test_channel){result.textContent=L("Trage einen Testkanal ein oder deaktiviere ihn.","Enter a test channel or disable Test channel.");return;}
      const saved=await save();if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      const status=await api("/api/status");const state=status.platforms?.tiktok||{};
      result.textContent=L(`Gespeichert. Aktiver Lesekanal: ${tiktok.active_read_channel||"keiner"}. Status: ${localizedPlatformStatus(state,true)}.`,`Saved. Active read channel: ${tiktok.active_read_channel||"none"}. Status: ${localizedPlatformStatus(state,true)}.`);
    };
    const render=()=>{
      const step=tiktokSteps[index];$("#tutorialSteps").innerHTML=tiktokSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");
      $("#tutorialCounter").textContent=tutorialCounter(index,tiktokSteps.length);$("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);
      $("#tutorialImage").src=`/tutorial-asset/tiktok/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);$("#tutorialProgressBar").style.width=`${(index+1)/tiktokSteps.length*100}%`;
      $("#tutorialFields").innerHTML=`${step.accounts?`<label><div>${L("Hauptkonto ohne @","Main account name (without @)")}</div><input id="tutorialMainAccount" value="${esc(tiktok.main_account||tiktok.main||"")}" autocomplete="off"></label><label><div>${L("Botkonto ohne @","Bot account name (without @)")}</div><input id="tutorialBotAccount" value="${esc(tiktok.bot_account||tiktok.bot||"")}" autocomplete="off"></label>`:""}${step.testChannel?`<label class="tutorialCheckbox"><input id="tutorialTestEnabled" type="checkbox" ${tiktok.test_channel_enabled?"checked":""}><span>${L("Testkanal aktivieren","Enable test channel")}</span></label><label><div>${L("Testkanal ohne @","Test channel name (without @)")}</div><input id="tutorialTestChannel" value="${esc(tiktok.test_channel||"")}" autocomplete="off"></label>`:""}${step.mainLogin?`<div class="tutorialConnectChoices one"><button type="button" id="tutorialLoginMain">${L("Speichern & Hauptkonto-Anmeldung öffnen","Save & open Main login")}</button></div>`:""}${step.botLogin?`<div class="tutorialConnectChoices one"><button type="button" id="tutorialLoginBot">${L("Speichern & Botkonto-Anmeldung öffnen","Save & open Bot login")}</button></div>`:""}`;
      $("#tutorialPrev").disabled=index===0;$("#tutorialNext").textContent=step.connect?L("TikTok-Einstellungen speichern","Save TikTok settings"):L("Weiter","Next");
      $$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});
      if(step.mainLogin)$("#tutorialLoginMain").onclick=()=>saveAndOpen("main");if(step.botLogin)$("#tutorialLoginBot").onclick=()=>saveAndOpen("bot");
    };
    $("#tutorialOverviewBack").onclick=showOverview;$("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};
    $("#tutorialNext").onclick=()=>{capture();if(index<tiktokSteps.length-1){index++;render();}else saveFinal();};render();
  };
  const showObs=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("OBS-WebSocket einrichten und die lokale Verbindung testen.","OBS WebSocket setup — configure and test the local connection."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="OBS WebSocket setup"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{const host=$("#tutorialObsHost"),port=$("#tutorialObsPort"),password=$("#tutorialObsPassword");if(host)obs.host=host.value.trim();if(port)obs.port=port.value.trim();if(password)obs.password=password.value;obs.url=`ws://${obs.host||"127.0.0.1"}:${obs.port||"4455"}`;};
    const saveAndTest=async()=>{
      const result=$("#tutorialResult");capture();obs.enabled=true;obs.autoconnect=true;result.textContent=L("OBS-Einstellungen werden gespeichert...","Saving OBS settings...");
      const saved=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}
      result.textContent=L("Gespeichert. OBS-Verbindung wird getestet...","Saved. Testing the OBS connection...");const checked=await api("/api/test-platform/obs",{timeoutMs:10000});
      result.textContent=checked.ok?L("Verbunden: ","Connected: ")+(checked.detail||"OBS WebSocket"):L("Verbindung fehlgeschlagen: ","Connection failed: ")+(checked.detail||checked.error||L("Unbekannter Fehler","Unknown error"));
    };
    const render=()=>{const step=obsSteps[index];$("#tutorialSteps").innerHTML=obsSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");$("#tutorialCounter").textContent=L(`Schritt ${index+1} von ${obsSteps.length}`,`Step ${index+1} of ${obsSteps.length}`);$("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);$("#tutorialImage").src=`/tutorial-asset/obs/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);$("#tutorialProgressBar").style.width=`${(index+1)/obsSteps.length*100}%`;$("#tutorialFields").innerHTML=step.credentials?`<label><div>Host</div><input id="tutorialObsHost" value="${esc(obs.host||"127.0.0.1")}"></label><label><div>Port</div><input id="tutorialObsPort" value="${esc(obs.port||"4455")}"></label><label><div>${L("Passwort","Password")}</div><input id="tutorialObsPassword" type="password" value="${esc(obs.password||"")}"></label>`:"";$("#tutorialPrev").disabled=index===0;$("#tutorialNext").textContent=step.connect?L("Speichern & Verbindung testen","Save & test connection"):L("Weiter","Next");$$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});};
    $("#tutorialOverviewBack").onclick=showOverview;$("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};$("#tutorialNext").onclick=()=>{capture();if(index<obsSteps.length-1){index++;render();}else saveAndTest();};render();
  };
  const showMeld=()=>{
    let index=0;
    shell("tutorials","Tutorials",L("MELD-Remoteverbindung aktivieren und lokal testen.","Enable MELD remote connections and test locally."),`<section class="card tutorialWizard"><button type="button" class="secondary tutorialOverviewBack" id="tutorialOverviewBack">← ${L("Alle Plattformen","All platforms")}</button><div class="tutorialLayout"><aside class="tutorialSteps" id="tutorialSteps"></aside><div class="tutorialMain"><div class="tutorialProgress"><span id="tutorialProgressBar"></span></div><div class="tutorialCounter" id="tutorialCounter"></div><h3 id="tutorialTitle"></h3><p id="tutorialText"></p><div class="tutorialImageFrame"><img id="tutorialImage" alt="MELD setup"></div><div id="tutorialFields" class="tutorialFields"></div><div class="btnLine tutorialActions"><button type="button" class="secondary" id="tutorialPrev">${L("Zurück","Back")}</button><button type="button" id="tutorialNext">${L("Weiter","Next")}</button></div><div class="small" id="tutorialResult"></div></div></div></section>`);
    const capture=()=>{const host=$("#tutorialMeldHost"),port=$("#tutorialMeldPort");if(host)meld.host=host.value.trim()||"127.0.0.1";if(port)meld.port=port.value.trim()||"13376";};
    const saveAndTest=async()=>{const result=$("#tutorialResult");capture();meld.enabled=true;meld.autoconnect=true;delete meld.password;all.plugins=all.plugins||{};all.plugins.meld_control=all.plugins.meld_control||{};all.plugins.meld_control.enabled=true;result.textContent=L("MELD-Einstellungen werden gespeichert...","Saving MELD settings...");const saved=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(all)});if(!saved.ok){result.textContent=L("Speichern fehlgeschlagen: ","Could not save: ")+(saved.error||L("Unbekannter Fehler","Unknown error"));return;}result.textContent=L("Gespeichert. MELD-Verbindung wird getestet...","Saved. Testing the MELD connection...");const checked=await api("/api/test-platform/meld",{timeoutMs:10000});result.textContent=checked.ok?L("Verbunden: ","Connected: ")+(checked.detail||"MELD"):L("Verbindung fehlgeschlagen: ","Connection failed: ")+(checked.detail||checked.error||L("Unbekannter Fehler","Unknown error"));};
    const render=()=>{const step=meldSteps[index];$("#tutorialSteps").innerHTML=meldSteps.map((item,i)=>`<button type="button" class="tutorialStep ${i===index?"active":""} ${i<index?"done":""}" data-step="${i}"><span>${i+1}</span><b>${esc(tutorialCopy(item.title))}</b></button>`).join("");$("#tutorialCounter").textContent=tutorialCounter(index,meldSteps.length);$("#tutorialTitle").textContent=tutorialCopy(step.title);$("#tutorialText").textContent=tutorialCopy(step.text);$("#tutorialImage").src=`/tutorial-asset/meld/${encodeURIComponent(step.image)}`;$("#tutorialImage").alt=tutorialCopy(step.title);$("#tutorialProgressBar").style.width=`${(index+1)/meldSteps.length*100}%`;$("#tutorialFields").innerHTML=step.connect?`<label><div>Host</div><input id="tutorialMeldHost" value="${esc(meld.host||"127.0.0.1")}"></label><label><div>Port</div><input id="tutorialMeldPort" value="${esc(meld.port||"13376")}"></label>`:"";$("#tutorialPrev").disabled=index===0;$("#tutorialNext").textContent=step.connect?L("Speichern & Verbindung testen","Save & test connection"):L("Weiter","Next");$$(".tutorialStep").forEach(button=>button.onclick=()=>{capture();index=Number(button.dataset.step);render();});};
    $("#tutorialOverviewBack").onclick=showOverview;$("#tutorialPrev").onclick=()=>{capture();if(index>0){index--;render();}};$("#tutorialNext").onclick=()=>{capture();if(index<meldSteps.length-1){index++;render();}else saveAndTest();};render();
  };
  showOverview();
}
async function renderChat(){
  const [layout,state]=await Promise.all([api("/api/desktop-chat/layout"),api("/api/desktop-chat/state")]);
  const style=layout.style||{};
  const alerts=layout.alerts||{}, alertPlatforms=alerts.platforms||{};
  const viewers=layout.viewers||{};
  const spotify=layout.spotify||{};
  const systemInfo=layout.systemInfo||{};
  queueMicrotask(()=>{const edit=$(".editDesktopChat");if(!edit||$(".closeDesktopChat"))return;const reset=document.createElement("button");reset.className="secondary resetDesktopChat";reset.textContent="Desktopfenster zuruecksetzen";reset.onclick=async()=>{if(!confirm("Desktopfenster auf Standardposition und -groesse zuruecksetzen?"))return;const r=await api("/api/desktop-chat/reset",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht zurueckgesetzt werden");};const close=document.createElement("button");close.className="secondary closeDesktopChat";close.textContent="Desktopfenster schliessen";close.onclick=async()=>{const r=await api("/api/desktop-chat/close",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht geschlossen werden");};edit.before(reset,close);});
  shell("chat","Chat","Gemeinsamer Chat für Dashboard, Browserquelle und Desktopfenster.",`<div class="btnLine"><button class="openDesktopChat">Desktopfenster öffnen</button><button class="secondary editDesktopChat">${state.editing?"Bearbeitung beenden":"Desktopfenster editieren"}</button><a class="btn secondary" href="/chat-browser" target="_blank">Browserfenster öffnen</a></div><section class="card desktopSettings"><h3>Desktopfenster Darstellung</h3><div class="platformForm"><label><div>Hintergrundfarbe</div><input name="background" type="color" value="${esc(style.background||"#0d101d")}"></label><label><div>Transparenz</div><input name="opacity" type="range" min="0" max="100" value="${esc(style.opacity??82)}"></label><label><div>Radien</div><input name="radius" type="range" min="0" max="100" value="${esc(style.radius??16)}"></label>${field("fontFamily","Schriftart",style.fontFamily||"Segoe UI")}${field("fontSize","Schriftgröße",style.fontSize||16,"number")}<label><div>Schriftfarbe</div><input name="textColor" type="color" value="${esc(style.textColor||"#ffffff")}"></label><label><div>Desktopfenster beim Toolstart öffnen</div><input class="desktopAutoStart" type="checkbox" ${layout.autoStart?"checked":""}></label></div></section><section class="card chatBox"><div class="messages" id="messages"></div><div class="sendRow"><input id="testmsg" placeholder="Testnachricht ins Overlay schicken"><button id="sendMsg">Senden</button></div></section>`);
  const alertSettings=document.createElement("section");alertSettings.className="card desktopSettings";alertSettings.innerHTML=`<h3>${L("Alertbereich im Desktopfenster","Alert area in desktop window")}</h3><div class="platformForm"><label><div>${L("Alertbereich anzeigen","Show alert area")}</div><input class="alertEnabled" type="checkbox" ${alerts.enabled!==false?"checked":""}></label><label><div>${L("Alerts gleichzeitig","Simultaneous alerts")}</div><input class="alertMaxItems" type="number" min="1" max="20" value="${esc(alerts.maxItems??5)}"></label><label><div>${L("Uhrzeit anzeigen","Show time")}</div><input class="alertTimestamp" type="checkbox" ${alerts.showTimestamp!==false?"checked":""}></label><div class="alertPlatformToggles">${["twitch","tiktok","youtube","kick"].map(p=>`<label>${platformBadge(p)} <span>${platformLabel(p)}</span><input class="alertPlatform" data-platform="${p}" type="checkbox" ${alertPlatforms[p]!==false?"checked":""}></label>`).join("")}</div></div>`;$(".chatBox").before(alertSettings);
  const systemSettings=document.createElement("section");systemSettings.className="card desktopSettings";systemSettings.innerHTML=`<h3>${L("Systeminfo","System information")}</h3><div class="platformForm"><label><div>${L("Systemwarnungen anzeigen","Show system warnings")}</div><input class="systemInfoEnabled" type="checkbox" ${systemInfo.enabled!==false?"checked":""}></label><div class="hint">${L("Eigenes frei platzierbares Feld. Im Stream unsichtbar und nur bei einem echten Systemfehler sichtbar, zum Beispiel wenn keine Internetverbindung besteht.","Separate freely positionable field. Hidden on stream and shown only for a real system error, such as no internet connection.")}</div></div>`;alertSettings.after(systemSettings);
  const viewerSettings=document.createElement("section");viewerSettings.className="card desktopSettings";viewerSettings.innerHTML=`<h3>Zuschauerzahl</h3><div class="platformForm viewerCountSettings"><label><div>Zuschauerzahl anzeigen</div><input class="viewerCountEnabled" type="checkbox" ${viewers.enabled!==false?"checked":""}></label></div>`;systemSettings.after(viewerSettings);
  const spotifySettings=document.createElement("section");spotifySettings.className="card desktopSettings";spotifySettings.innerHTML=`<h3>Spotify im Desktopfenster</h3><div class="platformForm viewerCountSettings"><label><div>Spotify-Infobereich anzeigen</div><input class="spotifyInfoEnabled" type="checkbox" ${spotify.enabled===true?"checked":""}></label><div class="hint">Im Bearbeitungsmodus ist der Spotify-Bereich ein eigenes Element und kann ueber oder neben der Zuschauerzahl platziert werden.</div></div>`;viewerSettings.after(spotifySettings);
  $(".alertTimestamp")?.closest("label")?.remove();
  $(".openDesktopChat").onclick=async()=>{const r=await api("/api/desktop-chat/open",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!r.ok)alert(r.error||"Desktopfenster konnte nicht geöffnet werden");};
  $(".editDesktopChat").onclick=async()=>{const next=!state.editing;await api("/api/desktop-chat/edit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({editing:next})});state.editing=next;$(".editDesktopChat").textContent=next?"Bearbeitung beenden":"Desktopfenster editieren";};
  $$(".desktopSettings input[name]").forEach(input=>input.oninput=async()=>{const current=await api("/api/desktop-chat/layout");const next=current&&current.ok!==false?structuredClone(current):structuredClone(layout);next.style=next.style||{};next.style[input.name]=input.type==="range"||input.type==="number"?Number(input.value):input.value;const out=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(out.ok!==false)Object.assign(layout,next);});
  $(".desktopAutoStart").onchange=async e=>{const next=structuredClone(layout);next.autoStart=e.target.checked;await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});Object.assign(layout,next);};
  const saveAlertSettings=async()=>{const next=structuredClone(layout);next.alerts={enabled:$(".alertEnabled").checked,maxItems:Number($(".alertMaxItems").value)||5,showTimestamp:false,platforms:Object.fromEntries($$(".alertPlatform").map(input=>[input.dataset.platform,input.checked]))};const r=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(r.ok)Object.assign(layout,next);};
  $$(".alertEnabled,.alertPlatform").forEach(input=>input.onchange=saveAlertSettings);$(".alertMaxItems").onchange=saveAlertSettings;
  $(".systemInfoEnabled").onchange=async e=>{const current=await api("/api/desktop-chat/layout");const next=current&&current.ok!==false?structuredClone(current):structuredClone(layout);next.systemInfo={enabled:e.target.checked};const out=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(out.ok!==false)Object.assign(layout,next);};
  $(".viewerCountEnabled").onchange=async e=>{const current=await api("/api/desktop-chat/layout");const next=current&&current.ok!==false?structuredClone(current):structuredClone(layout);next.viewers={enabled:e.target.checked};const out=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(out.ok!==false)Object.assign(layout,next);};
  $(".spotifyInfoEnabled").onchange=async e=>{const current=await api("/api/desktop-chat/layout");const next=current&&current.ok!==false?structuredClone(current):structuredClone(layout);const wasEnabled=next.spotify?.enabled===true;next.spotify={enabled:e.target.checked};if(e.target.checked&&!wasEnabled){const v=next.viewerBar||{x:16,y:16,w:720,h:64};const h=Math.max(58,Math.min(90,Number(v.h||64)+12));let y=Number(v.y||16)-h-8;if(y<0)y=Number(v.y||16)+Number(v.h||64)+8;next.spotifyPanel={x:Number(v.x||16),y,w:Number(v.w||720),h};const bottom=y+h+8;if(next.chatPanel&&Number(next.chatPanel.y||0)<bottom){const dy=bottom-Number(next.chatPanel.y||0);next.chatPanel.y=Number(next.chatPanel.y||0)+dy;if(next.alertPanel)next.alertPanel.y=Number(next.alertPanel.y||0)+dy;}}const out=await api("/api/desktop-chat/layout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(next)});if(out.ok!==false)Object.assign(layout,next);};
  $("#sendMsg").onclick=async()=>{let v=$("#testmsg").value.trim(); if(!v)return; await api("/api/message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v})}); $("#testmsg").value=""; refreshMessages();};
  refreshMessages();
}
async function renderObsMeld(){
  const settings=await api("/api/settings");
  const rules=Array.isArray(settings.automation_rules)?settings.automation_rules:[];
  rules.forEach((rule,index)=>{if(!rule.id)rule.id=`rule-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`;});
  const targets={obs:{connected:false,loading:true,scenes:[],sources:[],sources_by_scene:{},filters_by_scene:{}},meld:{connected:false,loading:true,scenes:[],sources:[],sources_by_scene:{}}};
  const targetLoad=(async()=>{
    let data={targets:{}};
    for(let attempt=0;attempt<4;attempt++){
      data=await api("/api/automation/targets",{timeoutMs:5000});
      const meld=data?.targets?.meld||{};
      if(meld.connected||(meld.scenes||[]).length||attempt===3)break;
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    return data;
  })();
  const values={timer:[["interval",L("Alle X Minuten","Every X minutes")]],tiktok:[["latest_follow",L("Neuester Follow","Latest follow")],["top_liker",L("Top-Liker","Top liker")],["top_gifter",L("Top-Gifter","Top gifter")],["latest_gift",L("Neuestes Geschenk","Latest gift")],["like_total",L("Like-Zähler","Like counter")]],twitch:[["latest_follow",L("Neuester Follow","Latest follow")],["latest_subscribe",L("Neuestes Abo","Latest subscription")],["latest_raid",L("Letzter Raid","Latest raid")],["latest_donation",L("Letzte Spende","Latest donation")],["latest_bits",L("Letzte Bits","Latest bits")],["latest_viewer_streak",L("Viewer-Streak","Viewer streak")]],youtube:[["latest_member",L("Neuestes Mitglied","Latest member")],["latest_superchat",L("Letzter Superchat","Latest Super Chat")]],kick:[["latest_follow",L("Neuester Follow","Latest follow")],["latest_subscribe",L("Neuestes Abo","Latest subscription")]]};
  const option=(items,selected="")=>items.map(([v,l])=>`<option value="${esc(v)}" ${v===selected?"selected":""}>${esc(l)}</option>`).join("");
  const targetLabel=(key,value)=>`${key.toUpperCase()}${value.loading?L(" (lädt...)"," (loading...)"):(value.connected?"":String(value.detail||"").includes("aufgebaut")?L(" (verbindet...)"," (connecting...)"):L(" (nicht verbunden)"," (not connected)"))}`;
  const targetOptions=()=>Object.entries(targets).map(([key,value])=>[key,targetLabel(key,value)]);
  const actionLabels={text:L("Text schreiben + zeitweise einblenden","Write text + show temporarily"),text_show:L("Text schreiben + Quelle neu einblenden","Write text + re-show source"),show:L("Quelle einblenden","Show source"),play:L("Medienquelle abspielen","Play media source"),scene:L("Szene aktivieren","Activate scene"),filter_on:L("OBS-Szenenfilter aktivieren","Enable OBS scene filter"),filter_off:L("OBS-Szenenfilter deaktivieren","Disable OBS scene filter")};
  const filterActions=new Set(["filter_on","filter_off"]);
  const actionOptions=()=>Object.entries(actionLabels).filter(([key])=>($("#ruleTarget")?.value==="obs"||!filterActions.has(key))&&($("#rulePlatform")?.value!=="timer"||!textActions.has(key)));
  const textActions=new Set(["text","text_show"]);
  const isTextRule=r=>textActions.has(String(r?.action||"text").toLowerCase());
  const isShowRule=r=>String(r?.action||"").toLowerCase()==="show";
  const isLikeCounterRule=r=>String(r?.platform||"").toLowerCase()==="tiktok"&&String(r?.value||"").toLowerCase()==="like_total";
  const isViewerStreakRule=r=>String(r?.platform||"").toLowerCase()==="twitch"&&String(r?.value||"").toLowerCase()==="latest_viewer_streak";
  const savedLikeUsers=()=>[...new Set(rules.map(r=>String(r?.likeUser||r?.like_user||"").trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  const defaultPreview=r=>{
    const label=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value||L("Wert","Value");
    if(isLikeCounterRule(r))return `Test: ${String(r.likeUser||"Chatter")} · ${L("Intervall","Interval")} ${Number(r.likeThreshold||0)||1} Likes`;
    if(isViewerStreakRule(r)){return String(r.streakTemplate||L("<user> hat einen Streak von <amount> Streams erreicht","<user> reached a streak of <amount> streams")).replaceAll("<user>","TestViewer").replaceAll("<amount>","3").replaceAll("{user}","TestViewer").replaceAll("{amount}","3");}
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
    return await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({automation_rules:rules})});
  };

  shell("obs_meld","OBS/Meld Integration",L("Dauerhafte Live-Werte oder zeitgesteuerte Aktionen gezielt in OBS oder Meld ausführen.","Write persistent live values or run timed actions in OBS or Meld."),`<section class="card integrationBuilder"><div class="integrationHead"><div><h3>${L("Neuen Eintrag anlegen","Create new entry")}</h3><div class="small">${L("Wähle zuerst den Auslöser. Weitere Optionen erscheinen passend zur Aktion.","Choose the trigger first. More options appear depending on the action.")}</div></div></div><div class="integrationFlow"><label><div>1 · ${L("Plattform/Timer","Platform/Timer")}</div><select id="rulePlatform">${option([["timer",L("Timer (plattformunabhängig)","Timer (platform-independent)")],["tiktok","TikTok"],["twitch","Twitch"],["youtube","YouTube"],["kick","Kick"]])}</select></label><label><div>2 · ${L("Live-Wert/Auslöser","Live value/trigger")}</div><select id="ruleValue"></select></label><label><div>3 · ${L("Ausgabe","Output")}</div><select id="ruleTarget">${option(targetOptions())}</select></label><label><div>4 · ${L("Szene","Scene")}</div><select id="ruleScene"></select></label><label><div>5 · ${L("Quelle","Source")}</div><select id="ruleSource"></select></label></div><div class="integrationName"><label><div>${L("Name dieses Eintrags","Name of this entry")}</div><input id="ruleName" placeholder="${L("z. B. Layer nach 30 Sekunden","e.g. layer after 30 seconds")}"></label><div class="ruleFormActions"><button id="saveRule">${L("Speichern","Save")}</button><button class="secondary" id="clearRule">${L("Ändern abbrechen","Cancel editing")}</button></div></div></section><section class="card integrationListCard"><div class="integrationListHead"><div><h3>${L("Gespeicherte Einträge","Saved entries")}</h3><span class="small">${L("Einträge aufeinander ziehen, um sie zu gruppieren.","Drag entries onto each other to group them.")}</span></div></div><div id="ruleUngroupDrop" class="ruleUngroupDrop">${L("Eintrag hier ablegen, um ihn aus der Gruppe zu lösen","Drop entry here to remove it from its group")}</div><div id="ruleList" class="ruleList"></div></section>`);
  const reloadButton=document.createElement("button");
  reloadButton.className="secondary targetReload";
  reloadButton.textContent=L("Szenen & Quellen neu laden","Reload scenes & sources");
  reloadButton.onclick=async()=>{await api("/api/automation/reload-targets",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});setTimeout(renderObsMeld,900);};
  $(".integrationBuilder").append(reloadButton);

  const actionField=document.createElement("label");
  actionField.innerHTML=`<div>6 · ${L("Aktion","Action")}</div><select id="ruleAction">${option(actionOptions())}</select>`;
  $(".integrationFlow").append(actionField);
  const timerDelayField=document.createElement("label");
  timerDelayField.className="timerDelayField";
  timerDelayField.innerHTML=`<div>7 · ${L("Alle X Minuten auslösen","Trigger every X minutes")}</div><input id="ruleIntervalMinutes" type="number" min="0.1" max="1440" step="0.1" value="5" title="${esc(L("Die Aktion wird in diesem Minutenintervall wiederholt.","The action repeats at this interval in minutes."))}">`;
  $(".integrationFlow").append(timerDelayField);
  const likeCounterField=document.createElement("div");
  likeCounterField.className="likeCounterFields";
  likeCounterField.innerHTML=`<label><div>7 · Chatter</div><input id="ruleLikeUser" title="${esc(L("TikTok-Name exakt eingeben","Enter exact TikTok name"))}" list="ruleLikeUserList" placeholder="${L("TikTok-Name exakt eingeben","Enter exact TikTok name")}"></label><label><div>8 · ${L("Auslösen alle X Likes","Trigger every X likes")}</div><input id="ruleLikeThreshold" title="${esc(L("Die Aktion wird bei jedem Intervall erneut ausgeführt, z. B. bei 50, 100 und 150 Likes.","The action repeats at every interval, e.g. at 50, 100 and 150 likes."))}" type="number" min="1" step="1" value="10"></label><datalist id="ruleLikeUserList"></datalist>`;
  $(".integrationFlow").append(likeCounterField);
  const viewerStreakField=document.createElement("div");
  viewerStreakField.className="viewerStreakFields";
  viewerStreakField.innerHTML=`<label><div>7 · ${L("Gesendeter Text","Text to send")}</div><input id="ruleStreakTemplate" title="${esc(L("Vorlagen: <user> = Twitch-Name, <amount> = Anzahl der Streams","Templates: <user> = Twitch name, <amount> = stream count"))}" value="${esc(L("<user> hat einen Streak von <amount> Streams erreicht","<user> reached a streak of <amount> streams"))}"></label><label class="settingsBool"><input id="ruleWriteToFile" type="checkbox"><span>${L("Zusätzlich in Datei schreiben","Also write to file")}</span></label><label class="viewerFileField"><div>${L("Ordner unter data","Folder under data")}</div><input id="ruleFileDirectory" value="twitch_alert" placeholder="twitch_alert"></label><label class="viewerFileField"><div>${L("Dateiname","File name")}</div><input id="ruleFileName" value="viewerstreak.txt" placeholder="viewerstreak.txt"></label>`;
  $(".integrationFlow").append(viewerStreakField);
  const hideSecondsField=document.createElement("label");
  hideSecondsField.className="hideSecondsField";
  hideSecondsField.innerHTML=`<div>7 · ${L("Nach X Sekunden ausblenden/zurück","Hide/back after X seconds")}</div><input id="ruleHideSeconds" title="${esc(L("0 = nicht automatisch ausblenden oder zurückschalten.","0 = do not hide or switch back automatically."))}" type="number" min="0" max="3600" step="0.1" value="4">`;
  $(".integrationFlow").append(hideSecondsField);
  const filterField=document.createElement("label");
  filterField.className="filterField";
  filterField.innerHTML=`<div>7 · ${L("Szenenfilter","Scene filter")}</div><select id="ruleFilter"></select>`;
  $(".integrationFlow").append(filterField);
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
  const updateViewerFileFields=()=>{$$(".viewerFileField").forEach(field=>field.hidden=!$("#ruleWriteToFile").checked);};
  const isFilterAction=()=>filterActions.has($("#ruleAction")?.value);
  const refreshActions=()=>{const select=$("#ruleAction");if(!select)return;const selected=select.value;select.innerHTML=option(actionOptions(),selected);if(selected&&[...select.options].some(item=>item.value===selected))select.value=selected;else select.value=select.options[0]?.value||"show";};
  const toggleTextOptions=()=>{const action=$("#ruleAction").value,text=isTextRule({action}),placeholder=$("#ruleStartup").value==="placeholder",streak=text&&$("#rulePlatform").value==="twitch"&&$("#ruleValue").value==="latest_viewer_streak",timerRule=$("#rulePlatform").value==="timer",filterAction=isFilterAction()&&$("#ruleTarget").value==="obs",timedAction=["text","show","text_show","play","scene"].includes(action);timerDelayField.hidden=!timerRule;timerDelayField.style.display=timerRule?"":"none";startupField.hidden=!text||streak||timerRule;startupField.style.display=text&&!streak&&!timerRule?"":"none";placeholderField.hidden=!text||!placeholder||streak||timerRule;placeholderField.style.display=text&&placeholder&&!streak&&!timerRule?"":"none";likeCounterField.hidden=!selectedIsLikeCounter();likeCounterField.style.display=selectedIsLikeCounter()?"":"none";viewerStreakField.hidden=!streak;viewerStreakField.style.display=streak?"":"none";hideSecondsField.hidden=!timedAction;hideSecondsField.style.display=timedAction?"":"none";filterField.hidden=!filterAction;filterField.style.display=filterAction?"":"none";$("#ruleSource").closest("label").hidden=filterAction||action==="scene";};
  $("#ruleAction").onchange=()=>{toggleTextOptions();refreshFilters();};$("#ruleStartup").onchange=toggleTextOptions;
  $("#ruleWriteToFile").onchange=updateViewerFileFields;

  let editIndex=-1;
  const refreshFilters=()=>{const target=targets[$("#ruleTarget").value]||{},scene=$("#ruleScene").value,filters=(target.filters_by_scene||{})[scene]||[];$("#ruleFilter").innerHTML=option(filters.length?filters.map(x=>[x,x]):[["",L("Keine Filter in dieser Szene","No filters in this scene")]]);};
  const refreshSources=()=>{const target=targets[$("#ruleTarget").value]||{},scene=$("#ruleScene").value,sources=(target.sources_by_scene||{})[scene]||[];$("#ruleSource").innerHTML=option(sources.length?sources.map(x=>[x,x]):[["",L("Keine Quelle in dieser Szene","No source in this scene")]]);refreshFilters();};
  const refreshTargets=()=>{refreshActions();const key=$("#ruleTarget").value,target=targets[key]||{},scenes=target.scenes||[];$("#ruleScene").innerHTML=option(scenes.length?scenes.map(x=>[x,x]):[[target.loading?"loading":"",target.loading?L("Szenen werden geladen...","Loading scenes..."):L("Zuerst OBS/Meld verbinden","Connect OBS/Meld first")]]);refreshSources();toggleTextOptions();};
  const refreshValues=()=>{$("#ruleValue").innerHTML=option(values[$("#rulePlatform").value]||[]);if(editIndex>=0){const rule=rules[editIndex];$("#ruleIntervalMinutes").value=rule?.intervalMinutes??rule?.interval_minutes??5;}toggleTextOptions();};
  const readRule=()=>{
    const previous=editIndex>=0?rules[editIndex]:{};
    const r={id:previous.id||`rule-${Date.now()}-${Math.random().toString(16).slice(2)}`,parentTrigger:previous.parentTrigger||previous.parent_trigger||"",groupName:previous.groupName||previous.group_name||"",name:$("#ruleName").value.trim()||`${platformLabel($("#rulePlatform").value)} ${$("#ruleValue").selectedOptions[0]?.textContent||L("Wert","Value")}`,platform:$("#rulePlatform").value,value:$("#ruleValue").value,target:$("#ruleTarget").value,scene:$("#ruleScene").value,source:$("#ruleSource").value,filter:$("#ruleFilter").value,action:$("#ruleAction").value,startup:$("#ruleStartup").value,placeholder:$("#rulePlaceholder").value.trim()||"---"};
    if(r.platform==="timer")r.intervalMinutes=Math.max(0.1,Math.min(1440,Number($("#ruleIntervalMinutes").value)||1));
    if(["text","show","text_show","play","scene"].includes(r.action))r.hideSeconds=Math.max(0,Number($("#ruleHideSeconds").value)||0);
    if(isLikeCounterRule(r)){r.likeUser=$("#ruleLikeUser").value.trim();r.likeThreshold=Math.max(1,Number($("#ruleLikeThreshold").value)||1);}
    if(isViewerStreakRule(r))r.streakTemplate=$("#ruleStreakTemplate").value.trim()||L("<user> hat einen Streak von <amount> Streams erreicht","<user> reached a streak of <amount> streams");
    if(isViewerStreakRule(r)){r.writeToFile=$("#ruleWriteToFile").checked;r.fileDirectory=$("#ruleFileDirectory").value.trim()||"twitch_alert";r.fileName=$("#ruleFileName").value.trim()||"viewerstreak.txt";}
    return r;
  };
  const runRuleTest=async (r,previewText)=>{
    const body={...r};
    if(isTextRule(r))body.preview=String(previewText||r.testText||defaultPreview(r));
    const result=$("#ruleTestResult");
    if(result)result.textContent=L("Teste...","Testing...");
    const out=await api("/api/automation/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const message=out.ok?(out.detail||L("Test gesendet.","Test sent.")):(out.error||out.detail||L("Regeltest fehlgeschlagen","Rule test failed"));
    if(result)result.textContent=message;
    if(!out.ok)console.warn(L("Regeltest fehlgeschlagen","Rule test failed"),message);
    return out;
  };
  const renderRules=()=>{
    fillLikeUserList();
    const orderedRules=rules.map((r,i)=>({r,i})).reverse();
    $("#ruleList").innerHTML=orderedRules.length?orderedRules.map(({r,i})=>{
      const textRule=isTextRule(r);
      const testText=localizedPreview(r,r.testText||defaultPreview(r));
      const valueLabel=(values[r.platform]||[]).find(x=>x[0]===r.value)?.[1]||r.value;
      const condition=isLikeCounterRule(r)?` · ${L("Benutzer","User")}: ${esc(r.likeUser||"-")} · ${L("alle","every")} ${esc(r.likeThreshold||"-")} Likes`:r.platform==="timer"?` · ${L("alle","every")} ${esc(r.intervalMinutes??r.interval_minutes??1)} ${L("Minuten","minutes")}`:"";
      const fileInfo=isViewerStreakRule(r)&&(r.writeToFile??r.write_to_file)?` · ${L("Datei","File")}: data/${esc(r.fileDirectory||r.file_directory||"twitch_alert")}/${esc(r.fileName||r.file_name||"viewerstreak.txt")}`:"";
      const actionKey=String(r.action||"").toLowerCase();
      const sceneSeconds=Number(r.hideSeconds??r.hide_seconds??0)||0;
      const showInfo=["text","show","text_show","play"].includes(actionKey)?` · ${L("ausblenden nach","hide after")} ${esc(r.hideSeconds??4)}s`:actionKey==="scene"?(sceneSeconds>0?` · ${L("zurück nach","back after")} ${esc(sceneSeconds)}s`:` · ${L("bleibt aktiv","stays active")}`):"";
      const targetItem=["filter_on","filter_off"].includes(actionKey)?`${esc(r.scene||"-")} · ${esc(r.filter||"-")}`:actionKey==="scene"?`${esc(r.scene||"-")}`:`${esc(r.scene||"-")} · ${esc(r.source||"-")}`;
      const testControls=textRule
        ? `<label class="ruleTestField"><span>${L("Testtext","Test text")}</span><input class="savedRuleTestText" data-i="${i}" value="${esc(testText)}" placeholder="${L("Testtext","Test text")}"></label><button class="secondary testSavedRule" data-i="${i}">${L("Testen","Test")}</button>`
        : `<button class="secondary testSavedRule" data-i="${i}">${L("Testen","Test")}</button>`;
      return `<div class="ruleRow" draggable="true" data-rule-index="${i}" title="${L("Ziehen, um diesen Eintrag zu gruppieren oder zu lösen","Drag to group or ungroup this entry")}"><span class="ruleDragHandle" aria-hidden="true">⠿</span><div class="ruleMeta"><b>${esc(r.name)}</b><div class="small">${esc(platformLabel(r.platform))} · ${esc(valueLabel)}${condition}${fileInfo} → ${esc((r.target||"").toUpperCase())} · ${targetItem} · ${esc(actionLabels[r.action]||r.action||actionLabels.text)}${showInfo}</div></div><div class="ruleActions ${textRule?"hasText":"noText"}">${testControls}<button class="secondary editRule" data-i="${i}">${L("Ändern","Edit")}</button><button class="secondary deleteRule" data-i="${i}">${L("Löschen","Delete")}</button></div></div>`;
    }).join(""):`<div class="hint">${L("Noch keine Einträge. Lege oben einen dauerhaften Live-Wert an.","No entries yet. Create a persistent live value above.")}</div>`;
    $("#ruleList").insertAdjacentHTML("beforeend",`<div class="hint" id="ruleTestResult"></div>`);
    rules.forEach((root,rootIndex)=>{
      if(root.parentTrigger)return;
      const childIndices=rules.map((rule,index)=>String(rule.parentTrigger||rule.parent_trigger||"")===String(root.id)?index:-1).filter(index=>index>=0);
      if(!childIndices.length)return;
      const rootRow=$(`.editRule[data-i="${rootIndex}"]`)?.closest(".ruleRow");if(!rootRow)return;
      const folder=document.createElement("section");folder.className="triggerFolder";folder.dataset.rootIndex=String(rootIndex);folder.innerHTML=`<header class="triggerFolderHeader"><span>${L("Gemeinsamer Eintrag","Combined entry")}</span><input class="triggerGroupName" data-i="${rootIndex}" value="${esc(root.groupName||root.group_name||L("Neue Gruppe","New group"))}" aria-label="${L("Gruppenname","Group name")}"></header>`;rootRow.parentNode.insertBefore(folder,rootRow);folder.append(rootRow);rootRow.classList.add("triggerFolderMain");
      const groupButton=document.createElement("button");groupButton.type="button";groupButton.className="secondary testRuleGroup";groupButton.dataset.indices=[rootIndex,...childIndices].join(",");groupButton.textContent=L("Gruppe testen","Test group");$(".triggerFolderHeader",folder)?.append(groupButton);
      childIndices.forEach(index=>{const row=$(`.editRule[data-i="${index}"]`)?.closest(".ruleRow");if(row){row.classList.add("triggerFolderChild");folder.append(row);}});
    });
    let testTextSaveTimer=null;
    const queueTestTextSave=()=>{clearTimeout(testTextSaveTimer);testTextSaveTimer=setTimeout(()=>persistRules(),450);};
    $$('.savedRuleTestText').forEach(input=>{
      input.oninput=()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;queueTestTextSave();};
      input.onchange=async()=>{const i=Number(input.dataset.i);if(!rules[i])return;rules[i].testText=input.value;await persistRules();};
    });
    $$('.triggerGroupName').forEach(input=>{
      input.onkeydown=event=>{if(event.key==="Enter")input.blur();};
      input.onchange=async()=>{const root=rules[Number(input.dataset.i)];if(!root)return;root.groupName=input.value.trim()||L("Neue Gruppe","New group");input.value=root.groupName;await persistRules();};
    });
    let draggedRuleIndex=-1;
    const rootIndexOf=index=>{const parentId=String(rules[index]?.parentTrigger||rules[index]?.parent_trigger||"");if(!parentId)return index;const rootIndex=rules.findIndex(rule=>String(rule.id)===parentId);return rootIndex>=0?rootIndex:index;};
    const groupRules=async(sourceIndex,targetIndex)=>{
      if(!rules[sourceIndex]||!rules[targetIndex]||sourceIndex===targetIndex)return;
      const targetRootIndex=rootIndexOf(targetIndex),sourceRootIndex=rootIndexOf(sourceIndex);
      if(targetRootIndex===sourceRootIndex)return;
      const source=rules[sourceIndex],targetRoot=rules[targetRootIndex];
      const sourceId=String(source.id||""),targetId=String(targetRoot.id||"");
      if(!sourceId||!targetId)return;
      rules.forEach(rule=>{if(String(rule.parentTrigger||rule.parent_trigger||"")===sourceId)rule.parentTrigger=targetId;});
      source.parentTrigger=targetId;source.groupName="";
      targetRoot.parentTrigger="";
      if(!String(targetRoot.groupName||targetRoot.group_name||"").trim())targetRoot.groupName=`${targetRoot.name||L("Eintrag","Entry")} + ${source.name||L("Eintrag","Entry")}`;
      await persistRules();renderRules();
    };
    const ungroupRule=async sourceIndex=>{
      const source=rules[sourceIndex];if(!source)return;
      const parentId=String(source.parentTrigger||source.parent_trigger||"");
      if(parentId){source.parentTrigger="";source.groupName="";await persistRules();renderRules();return;}
      const children=rules.filter(rule=>String(rule.parentTrigger||rule.parent_trigger||"")===String(source.id));
      if(!children.length)return;
      const promoted=children[0];promoted.parentTrigger="";promoted.groupName=source.groupName||source.group_name||L("Neue Gruppe","New group");
      children.slice(1).forEach(rule=>{rule.parentTrigger=promoted.id;});source.groupName="";
      await persistRules();renderRules();
    };
    $$('.ruleRow').forEach(row=>{
      row.ondragstart=event=>{if(event.target.closest?.("button,input,select,textarea")){event.preventDefault();return;}draggedRuleIndex=Number(row.dataset.ruleIndex);row.classList.add("dragging");event.dataTransfer.effectAllowed="move";event.dataTransfer.setData("text/plain",String(draggedRuleIndex));$("#ruleUngroupDrop")?.classList.add("active");};
      row.ondragend=()=>{row.classList.remove("dragging");$$('.dragOver').forEach(item=>item.classList.remove("dragOver"));$("#ruleUngroupDrop")?.classList.remove("active","dragOver");draggedRuleIndex=-1;};
      row.ondragover=event=>{event.preventDefault();event.dataTransfer.dropEffect="move";row.classList.add("dragOver");};
      row.ondragleave=()=>row.classList.remove("dragOver");
      row.ondrop=event=>{event.preventDefault();event.stopPropagation();row.classList.remove("dragOver");const source=draggedRuleIndex>=0?draggedRuleIndex:Number(event.dataTransfer.getData("text/plain"));groupRules(source,Number(row.dataset.ruleIndex));};
    });
    $$('.triggerFolder').forEach(folder=>{folder.ondragover=event=>{event.preventDefault();folder.classList.add("dragOver");};folder.ondragleave=event=>{if(!folder.contains(event.relatedTarget))folder.classList.remove("dragOver");};folder.ondrop=event=>{event.preventDefault();folder.classList.remove("dragOver");const source=draggedRuleIndex>=0?draggedRuleIndex:Number(event.dataTransfer.getData("text/plain"));groupRules(source,Number(folder.dataset.rootIndex));};});
    const ungroupDrop=$("#ruleUngroupDrop");if(ungroupDrop){ungroupDrop.ondragover=event=>{event.preventDefault();ungroupDrop.classList.add("dragOver");};ungroupDrop.ondragleave=()=>ungroupDrop.classList.remove("dragOver");ungroupDrop.ondrop=event=>{event.preventDefault();ungroupDrop.classList.remove("dragOver");const source=draggedRuleIndex>=0?draggedRuleIndex:Number(event.dataTransfer.getData("text/plain"));ungroupRule(source);};}
    $$('.testSavedRule').forEach(b=>b.onclick=async()=>{
      const i=Number(b.dataset.i),r=rules[i];
      if(!r)return;
      const input=$(`.savedRuleTestText[data-i="${i}"]`);
      const preview=input?input.value:(r.testText||defaultPreview(r));
      const old=b.textContent;
      b.disabled=true;
      b.textContent=L("Teste...","Testing...");
      try{
        if(input)r.testText=input.value;
        const out=await runRuleTest({...r},preview);
        if(input&&out.ok)await persistRules();
      }finally{
        b.disabled=false;
        b.textContent=old;
      }
    });
    $$('.testRuleGroup').forEach(button=>button.onclick=async()=>{const indices=String(button.dataset.indices||"").split(",").map(Number).filter(Number.isFinite);const old=button.textContent;button.disabled=true;button.textContent=L("Gruppe läuft...","Testing group...");try{await Promise.all(indices.map(index=>{const rule=rules[index];return rule?runRuleTest({...rule},rule.testText||defaultPreview(rule)):Promise.resolve();}));}finally{button.disabled=false;button.textContent=old;}});
    $$('.editRule').forEach(b=>b.onclick=()=>{const r=rules[Number(b.dataset.i)];editIndex=Number(b.dataset.i);$("#rulePlatform").value=r.platform;refreshValues();$("#ruleValue").value=r.value;$("#ruleTarget").value=r.target;refreshTargets();$("#ruleScene").value=r.scene||"";refreshSources();$("#ruleSource").value=r.source||"";$("#ruleAction").value=r.action||"text";$("#ruleFilter").value=r.filter||r.filterName||r.filter_name||"";$("#ruleStartup").value=r.startup||"keep";$("#rulePlaceholder").value=r.placeholder||"---";$("#ruleHideSeconds").value=r.hideSeconds??r.hide_seconds??4;$("#ruleLikeUser").value=r.likeUser||r.like_user||"";$("#ruleLikeThreshold").value=r.likeThreshold||r.like_threshold||10;$("#ruleStreakTemplate").value=r.streakTemplate||r.streak_template||(r.streakOutput==="name"?"<user>":r.streakOutput==="count"?"<amount>":L("<user> hat einen Streak von <amount> Streams erreicht","<user> reached a streak of <amount> streams"));$("#ruleWriteToFile").checked=!!(r.writeToFile??r.write_to_file);$("#ruleFileDirectory").value=r.fileDirectory||r.file_directory||"twitch_alert";$("#ruleFileName").value=r.fileName||r.file_name||"viewerstreak.txt";updateViewerFileFields();toggleTextOptions();$("#ruleName").value=r.name;$("#saveRule").textContent=L("Änderung speichern","Save changes");});
    $$('.deleteRule').forEach(b=>b.onclick=async()=>{const index=Number(b.dataset.i),removedId=String(rules[index]?.id||"");rules.splice(index,1);if(removedId)rules.forEach(rule=>{if(String(rule.parentTrigger||rule.parent_trigger||"")===removedId)rule.parentTrigger="";});await persistRules();renderRules();});
  };
  $("#rulePlatform").onchange=()=>{refreshValues();refreshActions();toggleTextOptions();};$("#ruleValue").onchange=toggleTextOptions;$("#ruleTarget").onchange=refreshTargets;$("#ruleScene").onchange=refreshSources;
  $("#clearRule").onclick=()=>{editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleIntervalMinutes").value=5;$("#ruleHideSeconds").value=4;$("#ruleWriteToFile").checked=false;updateViewerFileFields();$("#saveRule").textContent=L("Speichern","Save");};
  $("#saveRule").onclick=async()=>{const r=readRule();if(isLikeCounterRule(r)&&!r.likeUser){alert(L("Bitte einen Chatter für den Like-Zähler eintragen.","Please enter a chatter for the like counter."));return;}if(["filter_on","filter_off"].includes(r.action)){if(r.target!=="obs"){alert(L("Filteraktionen sind nur für OBS verfügbar.","Filter actions are only available for OBS."));return;}if(!r.scene||!r.filter){alert(L("Bitte Szene und Filter auswählen.","Please choose a scene and filter."));return;}}if(editIndex>=0){r.testText=rules[editIndex]?.testText||defaultPreview(r);rules[editIndex]=r;}else{r.testText=defaultPreview(r);rules.push(r);}const out=await persistRules();if(!out.ok){console.warn(L("Regel speichern fehlgeschlagen","Failed to save rule"),out.error);return;}editIndex=-1;$("#ruleName").value="";$("#ruleLikeUser").value="";$("#ruleLikeThreshold").value=10;$("#ruleHideSeconds").value=4;$("#saveRule").textContent=L("Speichern","Save");renderRules();};
  fillLikeUserList();refreshValues();refreshTargets();if($("#rulePlatform").value==="timer"&&isTextRule({action:$("#ruleAction").value}))$("#ruleAction").value="show";toggleTextOptions();updateViewerFileFields();renderRules();
  targetLoad.then(targetData=>{
    const loaded=targetData?.targets||{};
    for(const key of ["obs","meld"])Object.assign(targets[key],{loading:false},loaded[key]||{});
    const targetSelect=$("#ruleTarget");
    if(!targetSelect)return;
    const selected=targetSelect.value;
    targetSelect.innerHTML=option(targetOptions(),selected);
    if(selected)targetSelect.value=selected;
    refreshTargets();
    renderRules();
  });
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
function schemaTab(field){
  const raw=schemaLocalized(field,"tab",schemaLocalized(field,"ui_tab",L("Allgemein","General")));
  if(window.APP_LANGUAGE==="en")return raw;
  return ({
    Main:"Allgemein",
    Games:"Spiele",
    Delete:"Löschen",
    Stream:"Stream",
    Vote:"Abstimmung",
    Picker:"Picker",
    Chat:"Chat",
    Twitch:"Twitch",
    YouTube:"YouTube",
    Kick:"Kick",
    Overlay:"Overlay"
  })[raw]||raw;
}
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
    twitch:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie / Spiel","Category / game")],["tags","Tags"],["description",L("Beschreibung / Notiz","Description / note")]],
    youtube:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie","Category")],["tags","Tags"],["description",L("Beschreibung","Description")]],
    kick:[["title",L("Streamtitel","Stream title")],["category",L("Kategorie","Category")],["tags","Tags"],["description",L("Beschreibung / Notiz","Description / note")]],
    tiktok:[["title",L("Live-Titel","Live title")],["category",L("Kategorie","Category")],["description",L("Nicht verfügbar","Not available")]],
  };
  const platformNames={twitch:"Twitch",youtube:"YouTube",kick:"Kick",tiktok:"TikTok"};
  const raw=()=>JSON.stringify({presets});
  const save=()=>api('/api/plugins/info3ditor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:{autoconnect:true,presets_json:raw()}})});
  const send=preset=>api('/api/plugins/info3ditor/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'send_web_preset',values:{autoconnect:true,presets_json:raw(),selected_preset_id:preset.id}})});
  const resultText=out=>out.ok?L("Vorgang erfolgreich.","Action completed."):`${L("Fehler","Error")}: ${out.error||'?'}`;
  const presetSummary=preset=>{
    const platforms=preset.platforms||{};
    const data=[platforms.twitch,platforms.youtube,platforms.kick,platforms.tiktok].find(item=>item&&(item.title||item.category))||{};
    return `<div class="infoPresetSummary"><span>${L("Streamtitel","Stream title")}: ${esc(data.title||'-')}</span><span>${L("Kategorie","Category")}: ${esc(data.category||'-')}</span></div>`;
  };
  const list=()=>{
    mount.innerHTML=`<section class="card pluginSettingsCard infoSettingsCard"><div class="pluginSettingsHead"><div><h3>Info3ditor ${L("Vorlagen","Presets")}</h3><div class="small">${L("Verwalte deine Spiel- und Plattforminformationen.","Manage your game and platform information.")}</div></div><button class="secondary" id="pluginSettingsClose">${L("Schließen","Close")}</button></div><div class="btnLine infoCreateLine"><button id="infoNew">${L("Vorlage anlegen","Create preset")}</button></div><div class="infoPresetList">${presets.map((preset,index)=>`<div class="infoPresetRow"><div class="infoPresetInfo"><b>${esc(preset.name||L("Unbenannt","Untitled"))}</b>${presetSummary(preset)}</div><div class="btnLine infoPresetActions"><button class="infoSendPreset" data-preset="${index}">${L("Senden","Send")}</button><button class="secondary infoEditPreset" data-preset="${index}">${L("Bearbeiten","Edit")}</button><button class="secondary infoDeletePreset" data-preset="${index}">${L("Löschen","Delete")}</button></div></div>`).join('')||`<div class="small">${L("Noch keine Vorlagen angelegt.","No presets created yet.")}</div>`}</div><div class="small" id="infoResult"></div></section>`;
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

async function openCommandsSettings(mount, values, defaults={}){
  const platformNames={twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"};
  const option=(items,selected="")=>items.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(selected)?"selected":""}>${esc(l)}</option>`).join("");
  const actionLabels={text:L("Text schreiben","Write text"),show:L("Quelle einblenden","Show source"),hide:L("Quelle ausblenden","Hide source"),trigger:L("Trigger auslösen","Trigger event"),play:L("Medienquelle abspielen","Play media source"),scene:L("Szene aktivieren","Activate scene")};
  let automationTargets={obs:{connected:false,scenes:[],sources_by_scene:{}},meld:{connected:false,scenes:[],sources_by_scene:{}}};
  const automationTargetsLoad=api("/api/automation/targets").catch(()=>({targets:{}}));
  const targetOptions=()=>Object.entries(automationTargets).map(([key,value])=>[key,`${key.toUpperCase()}${value.connected?"":L(" (nicht verbunden)"," (not connected)")}`]);
  const empty=()=>({id:`cmd_${Date.now()}`,enabled:false,name:"",trigger:"!",cooldown_seconds:0,sources:{twitch:true,tiktok:true,youtube:true,kick:true},chat_enabled:true,response:"",reply_same_platform:true,targets:{twitch:false,tiktok:false,youtube:false,kick:false},obs_enabled:false,obs_hotkey:"",meld_enabled:false,meld_action:"",output_enabled:false,output_target:"obs",output_action:"show",output_scene:"",output_source:"",output_text:"{user}"});
  let state={enabled:values.enabled!==false,commands_enabled:true,default_cooldown_seconds:Number(values.default_cooldown_seconds??15)||0,commands:[]};
  const parse=raw=>{try{const d=JSON.parse(String(raw||""));return Array.isArray(d)?d:(Array.isArray(d.commands)?d.commands:[])}catch(_){return []}};
  state.commands=parse(values.commands_json);
  if(!state.commands.length)state.commands=parse(defaults.commands_json);
  const normalize=cmd=>{cmd={...empty(),...(cmd||{})};cmd.sources={twitch:true,tiktok:true,youtube:true,kick:true,...(cmd.sources||{})};cmd.targets={twitch:false,tiktok:false,youtube:false,kick:false,...(cmd.targets||{})};if(['callFunctionWithArgs:lurk-alert:triggerLurk:["{user}"]','switchScene:scn_13;evalJs:lyr_42:window.triggerLurk("{user}")'].includes(String(cmd.meld_action||"").trim()))cmd.meld_action='switchScene:scn_13;callFunctionWithArgs:lyr_42:triggerLurk:["{user}"]';cmd.output_target=["obs","meld"].includes(String(cmd.output_target||"").toLowerCase())?String(cmd.output_target).toLowerCase():"obs";cmd.output_action=["text","show","hide","trigger","play","scene"].includes(String(cmd.output_action||"").toLowerCase())?String(cmd.output_action).toLowerCase():"show";cmd.output_enabled=!!cmd.output_enabled;if(!String(cmd.trigger||"").trim())cmd.trigger="!";return cmd};
  state.commands=state.commands.map(normalize);
  let editing="";
  const save=async()=>api("/api/plugins/commands/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values:{enabled:state.enabled,commands_enabled:true,default_cooldown_seconds:state.default_cooldown_seconds,commands_json:JSON.stringify({commands:state.commands})}})});
  const action=async key=>api("/api/plugins/commands/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key,values:{enabled:state.enabled,commands_enabled:true,default_cooldown_seconds:state.default_cooldown_seconds,commands_json:JSON.stringify({commands:state.commands})}})});
  const collect=()=>{const cmd=normalize(editing?(state.commands.find(x=>x.id===editing)||{}):empty());cmd.enabled=$("#cmdEnabled").checked;cmd.name=$("#cmdName").value.trim()||$("#cmdTrigger").value.trim()||"Command";cmd.trigger=$("#cmdTrigger").value.trim();if(cmd.trigger&&!"!/".includes(cmd.trigger[0]))cmd.trigger="!"+cmd.trigger;cmd.cooldown_seconds=Number($("#cmdCooldown").value)||0;cmd.chat_enabled=$("#cmdChatEnabled").checked;cmd.response=$("#cmdResponse").value.trim();cmd.reply_same_platform=$("#cmdReplySame").checked;cmd.output_enabled=$("#cmdOutputEnabled").checked;cmd.output_target=$("#cmdOutputTarget").value;cmd.output_action=$("#cmdOutputAction").value;cmd.output_scene=$("#cmdOutputScene").value;cmd.output_source=$("#cmdOutputSource").value;cmd.output_text=$("#cmdOutputText").value.trim();cmd.obs_enabled=$("#cmdObsEnabled").checked;cmd.obs_hotkey=$("#cmdObsHotkey").value.trim();cmd.meld_enabled=$("#cmdMeldEnabled").checked;cmd.meld_action=$("#cmdMeldAction").value.trim();["source","target"].forEach(kind=>{const key=kind==="source"?"sources":"targets";cmd[key]=cmd[key]||{};Object.keys(platformNames).forEach(p=>cmd[key][p]=$(`#cmd_${kind}_${p}`).checked)});return cmd};
  const refreshOutputSources=()=>{const target=automationTargets[$("#cmdOutputTarget").value]||{},scene=$("#cmdOutputScene").value,sources=(target.sources_by_scene||{})[scene]||[];$("#cmdOutputSource").innerHTML=option(sources.length?sources.map(x=>[x,x]):[["",L("Keine Quelle in dieser Szene","No source in this scene")]],$("#cmdOutputSource").dataset.value||"");$("#cmdOutputSource").dataset.value="";};
  const refreshOutputTargets=()=>{const target=automationTargets[$("#cmdOutputTarget").value]||{},scenes=target.scenes||[];$("#cmdOutputScene").innerHTML=option(scenes.length?scenes.map(x=>[x,x]):[["",L("Zuerst OBS/Meld verbinden","Connect OBS/Meld first")]],$("#cmdOutputScene").dataset.value||"");$("#cmdOutputScene").dataset.value="";refreshOutputSources();};
  const toggleOutputFields=()=>{const action=$("#cmdOutputAction").value;$("#cmdOutputScene").closest("label").hidden=!$("#cmdOutputEnabled").checked;$("#cmdOutputSource").closest("label").hidden=!$("#cmdOutputEnabled").checked||action==="scene";$("#cmdOutputText").closest("label").hidden=!$("#cmdOutputEnabled").checked||action!=="text";};
  const fill=cmd=>{cmd=normalize(cmd);editing=cmd.id||"";$("#commandsEditor").hidden=false;$("#cmdFormTitle").textContent=editing?L("Command bearbeiten","Edit command"):L("Neuen Command anlegen","Create command");$("#cmdEnabled").checked=!!cmd.enabled;$("#cmdName").value=cmd.name||"";$("#cmdTrigger").value=cmd.trigger||"!";$("#cmdCooldown").value=Number(cmd.cooldown_seconds||0);$("#cmdChatEnabled").checked=cmd.chat_enabled!==false;$("#cmdResponse").value=cmd.response||"";$("#cmdReplySame").checked=cmd.reply_same_platform!==false;$("#cmdOutputEnabled").checked=!!cmd.output_enabled;$("#cmdOutputTarget").value=cmd.output_target||"obs";$("#cmdOutputAction").value=cmd.output_action||"show";$("#cmdOutputScene").dataset.value=cmd.output_scene||"";$("#cmdOutputSource").dataset.value=cmd.output_source||"";refreshOutputTargets();$("#cmdOutputText").value=cmd.output_text||"{user}";toggleOutputFields();$("#cmdObsEnabled").checked=!!cmd.obs_enabled;$("#cmdObsHotkey").value=cmd.obs_hotkey||"";$("#cmdMeldEnabled").checked=!!cmd.meld_enabled;$("#cmdMeldAction").value=cmd.meld_action||"";Object.keys(platformNames).forEach(p=>{$(`#cmd_source_${p}`).checked=cmd.sources?.[p]!==false;$(`#cmd_target_${p}`).checked=cmd.targets?.[p]===true});$("#cmdCancel").hidden=false;};
  const reset=()=>{editing="";$("#commandsEditor").hidden=true;};
  const renderList=()=>{$("#commandsList").innerHTML=state.commands.map(raw=>{const cmd=normalize(raw);const output=cmd.output_enabled?` · ${esc((cmd.output_target||"").toUpperCase())} ${esc(actionLabels[cmd.output_action]||cmd.output_action)} ${esc(cmd.output_action==="scene"?(cmd.output_scene||"-"):`${cmd.output_scene||"-"} / ${cmd.output_source||"-"}`)}`:"";return `<div class="infoPresetRow"><div><b>${esc(cmd.trigger||"!")}</b><span>${esc(cmd.name||"Command")} · ${cmd.enabled?L("aktiv","enabled"):L("deaktiviert","disabled")} · ${Object.entries(cmd.sources||{}).filter(([,v])=>v!==false).map(([p])=>platformNames[p]||p).join(", ")}${output}</span></div><div class="btnLine"><button class="secondary commandTest" data-id="${esc(cmd.id)}">${L("Testen","Test")}</button><button class="secondary commandEdit" data-id="${esc(cmd.id)}">${L("Bearbeiten","Edit")}</button><button class="secondary commandDelete" data-id="${esc(cmd.id)}">${L("Löschen","Delete")}</button></div></div>`}).join("")||`<div class="small">${L("Noch keine Commands gespeichert.","No commands saved yet.")}</div>`;$$(".commandEdit",mount).forEach(b=>b.onclick=()=>{const cmd=state.commands.find(x=>x.id===b.dataset.id);if(cmd){fill(cmd);scrollTo({top:0,behavior:"smooth"})}});$$(".commandDelete",mount).forEach(b=>b.onclick=async()=>{if(!confirm(L("Command wirklich löschen?","Really delete this command?")))return;state.commands=state.commands.filter(x=>x.id!==b.dataset.id);const out=await save();$("#commandsResult").textContent=out.ok?L("Gelöscht.","Deleted."):resultText(out);renderList();});$$(".commandTest",mount).forEach(b=>b.onclick=async()=>{const old=b.textContent;b.disabled=true;b.textContent=L("Test läuft...","Testing...");if(editing&&editing===b.dataset.id&&!$("#commandsEditor").hidden){const cmd=collect();const idx=state.commands.findIndex(x=>x.id===cmd.id);if(idx>=0)state.commands[idx]=cmd;}const out=await action(`test_command:${b.dataset.id}`);b.disabled=false;b.textContent=out.ok?L("Getestet","Tested"):L("Fehler","Error");$("#commandsResult").textContent=out.detail||resultText(out);setTimeout(()=>b.textContent=old,1400);if(!out.ok)alert(out.error||out.detail||L("Test fehlgeschlagen","Test failed"));});};
  mount.innerHTML=`<section class="card pluginSettingsCard"><div class="pluginSettingsHead"><div><h3>Commands</h3><div class="small">${L("Eigene Chat-Commands ohne Limit verwalten.","Manage custom chat commands without a fixed limit.")}</div></div><button type="button" class="secondary" id="pluginSettingsClose">${L("Schließen","Close")}</button></div><div class="platformForm"><label class="settingsBool"><input type="checkbox" id="commandsEnabled" ${state.enabled?"checked":""}><span>${L("Plugin aktiv","Plugin enabled")}</span></label><label class="settingsBool"><input type="checkbox" id="commandsRun" ${state.commands_enabled?"checked":""}><span>${L("Commands ausführen","Run commands")}</span></label><label><div>${L("Standard-Cooldown Sekunden","Default cooldown seconds")}</div><input id="commandsCooldown" type="number" min="0" max="3600" value="${esc(state.default_cooldown_seconds)}"></label></div><form id="commandsForm"><section class="infoPlatform"><div class="infoPlatformHead"><h3 id="cmdFormTitle">${L("Neuen Command anlegen","Create command")}</h3><button type="button" class="secondary" id="cmdNew">+ Command</button></div><div class="platformForm"><label class="settingsBool"><input type="checkbox" id="cmdEnabled"><span>${L("Aktiv","Enabled")}</span></label><label><div>Name</div><input id="cmdName" placeholder="Lurk"></label><label><div>Trigger</div><input id="cmdTrigger" placeholder="!lurk oder /lurk"></label><label><div>Cooldown</div><input id="cmdCooldown" type="number" min="0" max="3600" value="0"></label></div><div class="timerPlatforms"><b>${L("Quellplattformen","Source platforms")}</b>${Object.entries(platformNames).map(([p,n])=>`<label><input type="checkbox" id="cmd_source_${p}"> ${n}</label>`).join("")}</div><label><div>${L("Antworttext","Reply text")}</div><textarea id="cmdResponse" placeholder="{user} verpieselt sich in die Hecke und beobachtet das Geschehen."></textarea></label><div class="platformForm"><label class="settingsBool"><input type="checkbox" id="cmdChatEnabled"><span>${L("Chatantwort senden","Send chat reply")}</span></label><label class="settingsBool"><input type="checkbox" id="cmdReplySame"><span>${L("Antwort in Ursprungschat","Reply in source chat")}</span></label></div><div class="timerPlatforms"><b>${L("Zusätzliche Zielplattformen","Additional target platforms")}</b>${Object.entries(platformNames).map(([p,n])=>`<label><input type="checkbox" id="cmd_target_${p}"> ${n}</label>`).join("")}</div><div class="platformForm"><label class="settingsBool"><input type="checkbox" id="cmdOutputEnabled"><span>OBS/Meld</span></label><label><div>${L("Ausgabe","Output")}</div><select id="cmdOutputTarget">${option(targetOptions())}</select></label><label><div>${L("Aktion","Action")}</div><select id="cmdOutputAction">${option(Object.entries(actionLabels))}</select></label><label><div>${L("Szene","Scene")}</div><select id="cmdOutputScene"></select></label><label><div>${L("Quelle","Source")}</div><select id="cmdOutputSource"></select></label><label><div>${L("Text","Text")}</div><input id="cmdOutputText" placeholder="{user}"></label></div><details><summary>${L("Erweitert: Hotkey / rohe Meld-Aktion","Advanced: hotkey / raw Meld action")}</summary><div class="platformForm"><label class="settingsBool"><input type="checkbox" id="cmdObsEnabled"><span>OBS Hotkey</span></label><label><div>OBS Hotkey</div><input id="cmdObsHotkey" placeholder="Shift+F10"></label><label class="settingsBool"><input type="checkbox" id="cmdMeldEnabled"><span>Meld Raw</span></label><label><div>Meld Aktion</div><input id="cmdMeldAction" placeholder='callFunctionWithArgs:lurk-alert:triggerLurk:["{user}"]'></label></div></details><div class="small">${L("Platzhalter","Placeholders")}: {user}, {platform}, {command}, {args}, {text}</div><div class="btnLine"><button type="submit" id="cmdSave">${L("Command speichern","Save command")}</button><button type="button" class="secondary" id="cmdCancel" hidden>${L("Abbrechen","Cancel")}</button><span class="small" id="commandsResult"></span></div></section></form></section><section class="card"><h3>${L("Gespeicherte Commands","Saved commands")}</h3><div id="commandsList" class="timerList"></div></section>`;
  $(".pluginSettingsHead h3",mount).textContent="commands";
  $(".pluginSettingsHead h3",mount).setAttribute("data-i18n-skip","");
  const runToggle=$("#commandsRun",mount);
  if(runToggle)runToggle.closest("label").remove();
  $("#commandsForm",mount).insertAdjacentHTML("beforebegin",`<div class="btnLine"><button type="button" id="cmdNewTop">+ Command</button><span class="small" id="commandsResult"></span></div>`);
  const editor=$(".infoPlatform",$("#commandsForm"));
  if(editor){editor.id="commandsEditor";editor.hidden=true;}
  const innerResult=$("#commandsResult",$("#commandsForm"));
  if(innerResult)innerResult.remove();
  const meldAction=$("#cmdMeldAction",mount);
  if(meldAction)meldAction.placeholder='switchScene:scn_13;callFunctionWithArgs:lyr_42:triggerLurk:["{user}"]';
  const reloadTargets=document.createElement("button");
  reloadTargets.type="button";
  reloadTargets.className="secondary";
  reloadTargets.textContent=L("Szenen & Quellen neu laden","Reload scenes & sources");
  reloadTargets.onclick=async()=>{await api("/api/automation/reload-targets",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});try{const targetData=await api("/api/automation/targets");automationTargets=targetData.targets||automationTargets;$("#cmdOutputTarget").innerHTML=option(targetOptions(),$("#cmdOutputTarget").value);refreshOutputTargets();}catch(_){}};
  $("#cmdOutputEnabled").closest(".platformForm").append(reloadTargets);
  $("#pluginSettingsClose").onclick=()=>mount.innerHTML="";
  $("#cmdNewTop").onclick=()=>fill(empty());$("#cmdNew").onclick=()=>fill(empty());$("#cmdCancel").onclick=reset;
  $("#cmdOutputEnabled").onchange=toggleOutputFields;$("#cmdOutputTarget").onchange=refreshOutputTargets;$("#cmdOutputScene").onchange=refreshOutputSources;$("#cmdOutputAction").onchange=toggleOutputFields;
  $("#commandsEnabled").onchange=e=>state.enabled=e.target.checked;$("#commandsCooldown").onchange=e=>state.default_cooldown_seconds=Number(e.target.value)||0;
  $("#commandsForm").onsubmit=async ev=>{ev.preventDefault();const cmd=collect();if(!cmd.trigger||!"!/".includes(cmd.trigger[0])){alert(L("Trigger muss mit ! oder / beginnen.","Trigger must start with ! or /."));return;}const idx=state.commands.findIndex(x=>x.id===cmd.id);if(idx>=0)state.commands[idx]=cmd;else state.commands.push(cmd);const out=await save();$("#commandsResult").textContent=out.ok?L("Gespeichert.","Saved."):resultText(out);if(out.ok){reset();renderList();}};
  refreshOutputTargets();toggleOutputFields();reset();renderList();
  automationTargetsLoad.then(targetData=>{
    if(!mount.isConnected||!$("#cmdOutputTarget",mount))return;
    const loaded=targetData?.targets||{};
    for(const key of ["obs","meld"])Object.assign(automationTargets[key],loaded[key]||{});
    const targetSelect=$("#cmdOutputTarget",mount);
    const selected=targetSelect.value;
    targetSelect.innerHTML=option(targetOptions(),selected);
    if(selected)targetSelect.value=selected;
    refreshOutputTargets();
  });
}

async function openPluginSettings(pluginId){
  const mount=$("#pluginSettingsMount");
  if(!mount) return;
  mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Einstellungen werden geladen...</h3></section>`;
  const d=await api(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
  if(!d.ok){mount.innerHTML=`<section class="card pluginSettingsCard"><h3>Einstellungen</h3><div class="warnBox">${esc(d.error||"Einstellungen konnten nicht geladen werden")}</div></section>`;return;}
  if(pluginId==="info3ditor"){openInfo3ditorSettings(mount,d.values||{});return;}
  if(pluginId==="commands"){await openCommandsSettings(mount,d.values||{},d.defaults||{});return;}
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
  setTimeout(renderPlugins,250);setTimeout(renderPlugins,1500);setTimeout(renderPlugins,4000);
}
async function restartPlugin(pluginId){
  const out=await api(`/api/plugins/${encodeURIComponent(pluginId)}/restart`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
  if(!out.ok){alert(out.error||"Plugin konnte nicht neu gestartet werden");return;}
  setTimeout(renderPlugins,250);setTimeout(renderPlugins,1500);setTimeout(renderPlugins,4000);
}
async function renderEasyslider(){
  const settings=normalizeEasysliderClient(((await api("/api/settings")).ui||{})["3asyslid3r"]);
  shell("easyslider","3asyslid3r","Schnellleiste am Fensterrand.",`
    <section class="card easysliderSettings">
      <form id="easysliderForm" class="platformForm">
        <label><div>${L("Aktiv","Enabled")}</div><select name="enabled"><option value="true" ${settings.enabled?"selected":""}>${L("Ja","Yes")}</option><option value="false" ${!settings.enabled?"selected":""}>${L("Nein","No")}</option></select></label>
        <label><div>${L("Bildschirmrand","Screen edge")}</div><select name="edge">${[["left",L("Links","Left")],["right",L("Rechts","Right")],["top",L("Oben","Top")],["bottom",L("Unten","Bottom")]].map(([v,l])=>`<option value="${v}" ${settings.edge===v?"selected":""}>${l}</option>`).join("")}</select></label>
        <label><div>${L("Verzögerung bis zum Öffnen (Sekunden)","Delay before opening (seconds)")}</div><input name="delaySeconds" type="number" min="0" max="120" step="0.5" value="${esc(settings.delaySeconds)}"></label>
        <label><div>${L("Transparenz","Opacity")}</div><input name="opacity" type="range" min="0" max="100" value="${esc(settings.opacity)}"></label>
        <div class="hint">${L("PNG-Ordner","PNG folder")}: assets\\pics\\3asyslid3r</div>
      </form>
    </section>
    <section class="card easysliderSettings">
      <h3>${L("Schaltflächen","Buttons")}</h3>
      <div id="easysliderButtons" class="easysliderButtonList"></div>
      <div class="btnLine"><button id="easysliderSave" type="button">${L("Speichern","Save")}</button><button id="easysliderTest" type="button" class="secondary">${L("Dashboard testen","Test dashboard")}</button><span id="easysliderResult" class="small"></span></div>
    </section>`);
  const form=$("#easysliderForm");
  const defaults=defaultEasysliderSettings().buttons;
  const byId=new Map((settings.buttons||[]).map(b=>[b.id,b]));
  const buttons=defaults.map(d=>({...d,...(byId.get(d.id)||{})}));
  $("#easysliderButtons").innerHTML=buttons.map((b,i)=>`<label class="easysliderButtonRow"><input type="checkbox" data-index="${i}" ${b.enabled!==false?"checked":""}><span class="easysliderCheckmark" aria-hidden="true"></span><span class="easysliderButtonIcon"><img src="/slider-asset/${encodeURIComponent(b.id)}.png?v=${encodeURIComponent(window.WEB_VERSION||"")}" alt="" onerror="this.remove()"></span><span class="easysliderButtonMeta"><b>${esc(b.label)}</b><small>${esc(b.path)}</small></span></label>`).join("");
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
async function renderEndstream(){
  const initial=await api("/api/3ndstr3am");
  const cfg={message:"",platforms:["twitch","tiktok","youtube","kick"],tools:["obs"],delay_seconds:60,...(initial.settings||{})};
  const platformLabels={twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"};
  shell("endstream","3ndstr3am",L("Stream kontrolliert beenden und Zuschauer verabschieden.","End the stream in a controlled way and say goodbye to viewers."),`
    <section class="card endstreamHero">
      <div><h3>${L("Stream-Abschluss","Stream ending")}</h3><p class="hint">${L("Die Nachricht wird beim Start sofort gesendet. Nach dem Countdown wird das ausgewählte Streamingtool gestoppt.","The message is sent immediately. The selected streaming tool stops after the countdown.")}</p></div>
      <div id="endstreamClock" class="endstreamClock">--:--</div>
    </section>
    <section class="card">
      <form id="endstreamForm" class="platformForm">
        <label class="endstreamWide"><div>${L("Abschiedsnachricht","Goodbye message")}</div><textarea name="message" rows="5" maxlength="1000" placeholder="${L("Danke fürs Zuschauen! Bis zum nächsten Stream.","Thanks for watching! See you next stream.")}">${esc(cfg.message||"")}</textarea></label>
        <fieldset class="endstreamWide"><legend>${L("Chatnachricht senden an","Send chat message to")}</legend><div class="endstreamChoices">${Object.entries(platformLabels).map(([id,label])=>`<label class="checkLine"><input type="checkbox" name="endPlatform" value="${id}" ${(cfg.platforms||[]).includes(id)?"checked":""}><span>${label}</span></label>`).join("")}</div></fieldset>
        <fieldset class="endstreamWide"><legend>${L("Streamingtool beenden","Stop streaming tool")}</legend><div class="endstreamChoices"><label class="checkLine"><input type="checkbox" name="endTool" value="obs" ${(cfg.tools||[]).includes("obs")?"checked":""}><span>OBS</span></label><label class="checkLine"><input type="checkbox" name="endTool" value="meld" ${(cfg.tools||[]).includes("meld")?"checked":""}><span>Meld</span></label></div></fieldset>
        <label><div>${L("Countdown bis Streamende (Sekunden)","Countdown until stream end (seconds)")}</div><input name="delay_seconds" type="number" min="0" max="86400" step="1" value="${esc(cfg.delay_seconds)}"></label>
      </form>
      <div class="btnLine"><button id="endstreamStart" type="button" class="danger">${L("Streamende starten","Start stream ending")}</button><button id="endstreamCancel" type="button" class="secondary">${L("Abbrechen","Cancel")}</button><button id="endstreamSave" type="button" class="secondary">${L("Einstellungen speichern","Save settings")}</button></div>
      <div id="endstreamResult" class="small"></div>
    </section>`);
  const form=$("#endstreamForm"),result=$("#endstreamResult"),clock=$("#endstreamClock");
  let status=initial.status||{state:"idle",ends_at:0};
  const payload=()=>({message:form.elements.message.value.trim(),platforms:$$('[name="endPlatform"]:checked',form).map(x=>x.value),tools:$$('[name="endTool"]:checked',form).map(x=>x.value),delay_seconds:Math.max(0,Number(form.elements.delay_seconds.value)||0)});
  const paint=()=>{const active=status.state==="countdown";const left=active?Math.max(0,Math.ceil(Number(status.ends_at||0)-Date.now()/1000)):0;clock.textContent=active?`${String(Math.floor(left/60)).padStart(2,"0")}:${String(left%60).padStart(2,"0")}`:"--:--";clock.classList.toggle("active",active);$("#endstreamStart").disabled=active;$("#endstreamCancel").disabled=!active;if(status.message)result.textContent=status.message;};
  const save=async()=>{const out=await api("/api/3ndstr3am/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});result.textContent=out.ok?L("Einstellungen gespeichert.","Settings saved."):out.error||L("Speichern fehlgeschlagen.","Save failed.");return out;};
  $("#endstreamSave").onclick=save;
  $("#endstreamStart").onclick=async()=>{if(!confirm(L("Streamende wirklich starten? Die Chatnachricht wird sofort gesendet.","Really start ending the stream? The chat message is sent immediately.")))return;const out=await api("/api/3ndstr3am/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});if(!out.ok){alert(out.error||L("Start fehlgeschlagen.","Start failed."));return;}status=out.status;paint();};
  $("#endstreamCancel").onclick=async()=>{const out=await api("/api/3ndstr3am/cancel",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(out.ok)status=out.status;else alert(out.error||L("Abbrechen fehlgeschlagen.","Cancel failed."));paint();};
  const poll=async()=>{try{const out=await api("/api/3ndstr3am",{timeoutMs:2000});if(out.ok)status=out.status||status;paint();}catch(_){ }if(document.body.contains(clock))setTimeout(poll,1000);};
  paint();setTimeout(poll,1000);
}
async function renderPlugins(){
  const s=await api("/api/plugins");
  const plugins=s.plugins||[];
  const activeCount=plugins.filter(p=>p.enabled).length;
  const errorCount=plugins.filter(p=>["error","failed"].includes(String(p.state||"").toLowerCase())).length;
  const cards=plugins.map(p=>{
    const state=String(p.state||"ready");
    const status=String(p.status||p.message||L("Bereit","Ready"));
    const icon=pluginIconId(p);
    const searchable=[p.name,p.id].join(" ").toLowerCase();
    return `<section class="card pluginCard" data-plugin-card data-enabled="${p.enabled?"1":"0"}" data-state="${esc(state.toLowerCase())}" data-search="${esc(searchable)}"><div class="pluginHead"><div class="pluginIdentity"><span class="pluginGlyph icon-${esc(icon)}" aria-hidden="true"><img src="/platform-icon/${encodeURIComponent(icon)}" alt="" onerror="this.parentElement.classList.add('missingIcon');this.remove()"><b>${esc(String(p.name||p.id||"?").trim().slice(0,1).toUpperCase()||"?")}</b></span><div><h3>${esc(p.name)}</h3><div class="pluginMeta"><span>${L("Version","Version")} ${esc(p.version||"-")}</span><span>${esc(p.id||"")}</span></div></div></div><span class="pluginState ${pluginStateClass(p.state)}">${esc(state)}</span></div><div class="small pluginDescription">${esc(p.description||"")}</div><div class="pluginStatusLine"><span class="pluginEnabled ${p.enabled?"ok":"off"}">${p.enabled?L("Aktiv","Active"):L("Inaktiv","Inactive")}</span><span class="small pluginStatusText">${esc(status)}</span></div><div class="btnLine pluginActions"><button type="button" class="pluginSettingsBtn" data-plugin="${esc(p.id)}">${L("Einstellungen","Settings")}</button><a class="btn secondary" href="/dev" title="${L("Protokolle im DEV-Bereich prüfen","Check logs in DEV area")}">${L("Protokolle","Logs")}</a></div></section>`;
  }).join("");
  shell("plugins",L("Plugins","Plugins"),L("Gefundene Plugins durchsuchen, prüfen und direkt konfigurieren.","Search, inspect and configure detected plugins."),`
    <div id="pluginSettingsMount"></div>
    <div class="pluginOverview">
      <div class="pluginStats" aria-label="${L("Plugin Übersicht","Plugin overview")}">
        <div><b>${plugins.length}</b><span>${L("Gefunden","Found")}</span></div>
        <div><b>${activeCount}</b><span>${L("Aktiv","Active")}</span></div>
        <div><b>${errorCount}</b><span>${L("Fehler","Errors")}</span></div>
      </div>
      <div class="pluginTools">
        <label class="pluginSearch"><span>${L("Suchen","Search")}</span><input id="pluginSearch" type="search" placeholder="${L("Plugin suchen...","Search plugins...")}"></label>
        <div class="pluginFilters" role="group" aria-label="${L("Plugin Filter","Plugin filters")}">
          <button type="button" class="secondary active" data-plugin-filter="all">${L("Alle","All")}</button>
          <button type="button" class="secondary" data-plugin-filter="active">${L("Aktiv","Active")}</button>
          <button type="button" class="secondary" data-plugin-filter="inactive">${L("Inaktiv","Inactive")}</button>
          <button type="button" class="secondary" data-plugin-filter="issues">${L("Fehler","Issues")}</button>
        </div>
      </div>
    </div>
    <div class="pluginGrid">${cards||`<section class="card pluginEmpty">${L("Keine Plugins gefunden.","No plugins found.")}</section>`}</div>`);
  $$(".pluginSettingsBtn").forEach(b=>b.onclick=()=>openPluginSettings(b.dataset.plugin));
  addPluginToggleButtons(s.plugins||[]);
  wirePluginListFilters();
}
function pluginIconId(plugin){
  const id=String(plugin?.id||"").toLowerCase();
  const name=String(plugin?.name||"").toLowerCase();
  if(["al3rtalot","botalot","bridg3alot","commands","gam3pick3r","info3ditor","modalot","tutorials"].includes(id))return "godisalotachat";
  if(["alertalot","bridgalot","gamepicker","infoeditor"].some(alias=>id.includes(alias)||name.includes(alias)))return "godisalotachat";
  if(id.includes("twitch")||name.includes("twitch"))return "twitch";
  if(id.includes("tiktok")||name.includes("tiktok"))return "tiktok";
  if(id.includes("youtube")||name.includes("youtube"))return "youtube";
  if(id.includes("kick")||name.includes("kick"))return "kick";
  if(id.includes("spotify")||id.includes("spoti")||name.includes("spotify")||name.includes("spoti"))return "spotify";
  if(id.includes("obs")||name.includes("obs"))return "obs";
  if(id.includes("meld")||name.includes("meld"))return "meld";
  if(id.includes("gpt")||name.includes("openai"))return "gpt";
  return "gpt";
}
function wirePluginListFilters(){
  const search=$("#pluginSearch");
  const filters=$$("[data-plugin-filter]");
  const cards=$$("[data-plugin-card]");
  const apply=()=>{
    const query=String(search?.value||"").trim().toLowerCase();
    const mode=filters.find(b=>b.classList.contains("active"))?.dataset.pluginFilter||"all";
    cards.forEach(card=>{
      const state=String(card.dataset.state||"");
      const enabled=card.dataset.enabled==="1";
      const matchesText=!query || String(card.dataset.search||"").includes(query);
      const matchesMode=mode==="all" || (mode==="active"&&enabled) || (mode==="inactive"&&!enabled) || (mode==="issues"&&["error","failed"].includes(state));
      card.hidden=!(matchesText&&matchesMode);
    });
  };
  if(search)search.oninput=apply;
  filters.forEach(btn=>btn.onclick=()=>{filters.forEach(b=>b.classList.toggle("active",b===btn));apply();});
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
        <label class="timerText"><div>${L("Nachricht","Message")}</div><textarea id="timerText" data-i18n-skip rows="3" maxlength="1000" required></textarea></label>
      </div><div class="timerPlatforms"><b>${L("Plattformen","Platforms")}</b>${["twitch","tiktok","youtube","kick"].map(p=>`<label><input type="checkbox" name="timerPlatform" value="${p}"> ${platformLabel(p)}</label>`).join("")}</div>
      <div class="btnLine"><button type="submit" id="timerSave">${L("Speichern","Save")}</button><button type="button" class="secondary" id="timerCancel" hidden>${L("Abbrechen","Cancel")}</button></div></form>
    </section><section class="card"><h3>${L("Gespeicherte Einträge","Saved entries")}</h3><div id="timerList" class="timerList"></div></section>`);
  let entries=[], editing="";
  const load=async()=>{const out=await api("/api/chattim3r");entries=Array.isArray(out.entries)?out.entries:[];draw();};
  const reset=()=>{editing="";$("#timerForm").reset();$("#timerMinutes").value=30;$("#timerCancel").hidden=true;$("#timerFormTitle").textContent=L("Neuen Eintrag anlegen","Create new entry");};
  const draw=()=>{$("#timerList").innerHTML=entries.map(e=>`<div class="timerRow"><div><b data-i18n-skip>${esc(e.text)}</b><span>${esc(e.minutes)} min · ${(e.platforms||[]).map(platformLabel).join(", ")}</span></div><div class="btnLine"><button class="secondary timerEdit" data-id="${esc(e.id)}">${L("Bearbeiten","Edit")}</button><button class="secondary timerTest" data-id="${esc(e.id)}">${L("Testen","Test")}</button><button class="secondary timerDelete" data-id="${esc(e.id)}">${L("Löschen","Delete")}</button></div></div>`).join("")||`<div class="small">${L("Noch keine Einträge gespeichert.","No entries saved yet.")}</div>`;
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
  const volume=normalizedVolume(cfg.volume),uiCfg=all.ui||{},colorScheme=String(uiCfg.color_scheme||"system"),customColors={...DEFAULT_CUSTOM_COLORS,...(uiCfg.custom_colors||{})};
  applyColorScheme(colorScheme,customColors);
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
    if(tab==="general")return `<div class="soundSettingsGroup ${index===0?"active":""}" data-sound-tab="general"><div class="soundSettingsGrid"><label><div>${L("Broadcaster-Ausgabe (Chat + Alerts)","Broadcaster output (chat + alerts)")}</div><select id="soundDevice">${deviceOptions}</select></label><label><div>${L("Stream-Ausgabe (nur Alerts)","Stream output (alerts only)")}</div><select id="streamSoundDevice">${streamDeviceOptions}</select></label><label><div>${L("Alle eingehenden Chatnachrichten","All incoming chat messages")}</div><select id="chatSound">${soundOptions(sounds,cfg.chat_sound||"")}</select></label><label class="soundVolumeControl"><div>${L("Lautstärke","Volume")} <output id="soundVolumeValue">${volume}%</output></div><input id="soundVolume" type="range" min="0" max="100" step="1" value="${volume}"></label></div><div class="btnLine soundDeviceActions"><button type="button" class="secondary" id="authorizeSoundDevices">${L("Audiogeräte freigeben","Authorize audio devices")}</button><button type="button" class="secondary" id="loadSoundDevices">${L("Geräteliste aktualisieren","Refresh device list")}</button><button type="button" class="secondary" id="openSoundFolder">${L("Soundordner öffnen","Open sound folder")}</button><span class="small" id="soundDeviceHint">${L("Der Broadcaster hört Chat und Alerts. An den Stream werden ausschließlich Alerts ausgegeben.","The broadcaster hears chat and alerts. Only alerts are sent to the stream output.")}</span></div><div class="hint">${L("Sounddateien kommen aus assets/sound. Unterstützt werden MP3, WAV, OGG, M4A, AAC und FLAC.","Sound files are loaded from assets/sound. MP3, WAV, OGG, M4A, AAC and FLAC are supported.")}</div></div>`;
    const pCfg=alerts[tab]||{};
    return `<div class="soundSettingsGroup" data-sound-tab="${tab}"><div class="soundPlatformHead">${platformBadge(tab)}<h3>${label}</h3></div><div class="soundSettingsGrid">${SOUND_ALERTS[tab].map(([key,name])=>`<label><div>${esc(name)}</div><select data-sound-platform="${tab}" data-sound-event="${key}">${soundOptions(sounds,pCfg[key]||"")}</select></label>`).join("")}</div></div>`;
  }).join("");
  const themeOptions=[["system",L("Windows-Systemeinstellung","Windows system setting")],["dark",L("Dunkel","Dark")],["light",L("Hell","Light")],["neon","Neon"],["purple",L("Violett","Purple")],["ocean",L("Ozean","Ocean")],["forest",L("Wald","Forest")],["custom",L("Eigenes Farbschema","Custom color scheme")]];
  const colorField=(key,label)=>`<label><div>${label}</div><input type="color" data-custom-color="${key}" value="${esc(customColors[key])}"></label>`;
  shell("settings",L("Einstellungen","Settings"),L("Allgemeine Einstellungen für das gesamte Tool.","General settings for the entire tool."),`<section class="card pluginSettingsCard"><h3 class="settingsSectionTitle">${L("Sounds","Sounds")}</h3><div class="pluginSettingsTabs">${tabs.map(([key,label],i)=>`<button type="button" class="pluginSettingsTabBtn soundTab ${i===0?"active":""}" data-tab="${key}">${label}</button>`).join("")}</div><form id="soundSettingsForm">${groups}<div class="btnLine"><button type="submit">${L("Speichern","Save")}</button><button type="button" class="secondary" id="testSelectedSound">${L("Ausgewählten Sound testen","Test selected sound")}</button><span class="small" id="soundSettingsResult"></span></div></form></section><section class="card pluginSettingsCard colorSchemeCard"><h3 class="settingsSectionTitle">${L("Farbschema","Color scheme")}</h3><form id="colorSchemeForm"><div class="soundSettingsGrid"><label><div>${L("Farbschema auswählen","Select color scheme")}</div><select id="colorScheme">${themeOptions.map(([value,label])=>`<option value="${value}">${label}</option>`).join("")}</select></label></div><div id="customColorFields" class="customColorFields">${colorField("background",L("Hintergrund","Background"))}${colorField("panel",L("Flächen","Panels"))}${colorField("text",L("Text","Text"))}${colorField("accent",L("Akzentfarbe","Accent color"))}${colorField("secondary",L("Zweitfarbe","Secondary color"))}</div><div class="btnLine"><button type="submit">${L("Farbschema speichern","Save color scheme")}</button><span class="small" id="colorSchemeResult"></span></div></form></section>`);
  $("#soundDevice").value=cfg.output_device||"";
  $("#streamSoundDevice").value=cfg.stream_output_device||"";
  $("#colorScheme").value=COLOR_SCHEMES.includes(colorScheme)?colorScheme:"system";
  const collectCustomColors=()=>Object.fromEntries($$("[data-custom-color]").map(input=>[input.dataset.customColor,input.value]));
  const previewColorScheme=()=>{const scheme=$("#colorScheme").value;$("#customColorFields").hidden=scheme!=="custom";applyColorScheme(scheme,collectCustomColors());};
  $("#colorScheme").onchange=previewColorScheme;
  $$("[data-custom-color]").forEach(input=>input.oninput=previewColorScheme);
  previewColorScheme();
  $("#soundVolume").oninput=()=>{$("#soundVolumeValue").textContent=`${$("#soundVolume").value}%`;};
  $$(".soundTab").forEach(btn=>btn.onclick=()=>{$$(".soundTab").forEach(x=>x.classList.toggle("active",x===btn));$$(".soundSettingsGroup").forEach(x=>x.classList.toggle("active",x.dataset.soundTab===btn.dataset.tab));});
  $$('#soundSettingsForm select:not(#soundDevice)').forEach(select=>select.onchange=()=>{if(select.value&&select.value!=="__off__")playConfiguredSound(select.value,$("#soundDevice")?.value||"");});
  $("#openSoundFolder").onclick=async()=>{const out=await api("/api/sounds/open-folder",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});if(!out.ok)$("#soundDeviceHint").textContent=out.error||L("Soundordner konnte nicht geöffnet werden.","Could not open the sound folder.");};
  $("#loadSoundDevices").onclick=async()=>{
    const button=$("#loadSoundDevices"),hint=$("#soundDeviceHint"),select=$("#soundDevice");button.disabled=true;
    try{
      const streamSelect=$("#streamSoundDevice"),oldStream=streamSelect.value,oldStreamLabel=streamSelect.selectedOptions[0]?.textContent||"";
      const oldBroadcaster=select.value,oldBroadcasterLabel=select.selectedOptions[0]?.textContent||"";
      const found=await audioOutputDevices(),selected=resolveSavedDeviceId(found,oldBroadcaster,oldBroadcasterLabel);
      select.innerHTML=`<option value="">${L("System-Standardgerät","System default device")}</option>`+found.map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||`${L("Audiogerät","Audio device")} ${i+1}`)}</option>`).join("");
      streamSelect.innerHTML=`<option value="">${L("Nicht ausgeben","No output")}</option><option value="__default__">${L("System-Standardgerät","System default device")}</option>`+found.map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||`${L("Audiogerät","Audio device")} ${i+1}`)}</option>`).join("");
      select.value=selected;if(select.value!==selected&&selected)select.append(new Option(oldBroadcasterLabel||L("Gespeichertes Broadcaster-Gerät","Saved broadcaster device"),selected,true,true));
      streamSelect.value=oldStream;if(streamSelect.value!==oldStream&&oldStream)streamSelect.append(new Option(oldStreamLabel||L("Gespeichertes Stream-Gerät","Saved stream device"),oldStream,true,true));
      hint.textContent=found.length?L(`${found.length} Audiogerät(e) gefunden.`,`Found ${found.length} audio device(s).`):L("Keine Audiogeräte gefunden.","No audio devices found.");
    }catch(e){hint.textContent=L("Gerätefreigabe wurde abgebrochen oder vom Browser blockiert.","Device access was cancelled or blocked by the browser.");}
    finally{button.disabled=false;}
  };
  $("#authorizeSoundDevices").onclick=async()=>{
    const button=$("#authorizeSoundDevices"),hint=$("#soundDeviceHint"),saved=$("#soundDevice")?.value||"";button.disabled=true;
    try{
      if(typeof navigator.mediaDevices?.selectAudioOutput==="function")await navigator.mediaDevices.selectAudioOutput(saved?{deviceId:saved}:undefined);
      else if(typeof navigator.mediaDevices?.getUserMedia==="function"){const mediaStream=await navigator.mediaDevices.getUserMedia({audio:true});mediaStream.getTracks().forEach(track=>track.stop());}
      await $("#loadSoundDevices").onclick();
      hint.textContent=L("Audiogeräte wurden freigegeben und vollständig neu geladen.","Audio devices were authorized and fully reloaded.");
    }catch(e){hint.textContent=L("Gerätefreigabe wurde abgebrochen oder vom Browser blockiert.","Device access was cancelled or blocked by the browser.");}
    finally{button.disabled=false;}
  };
  $("#testSelectedSound").onclick=async()=>{
    const group=$(".soundSettingsGroup.active"),isChatTest=group?.dataset.soundTab==="general";
    const select=isChatTest?$("#chatSound"):group?.querySelector('[data-sound-event]');
    const name=select?.value;if(!name)return;
    const testVolume=Number($("#soundVolume")?.value??100);
    if(isChatTest)await playConfiguredSound(name,$("#soundDevice")?.value||"",true,true,false,testVolume);
    else await playSoundForAudience(name,true,{output_device:$("#soundDevice")?.value||"",stream_output_device:$("#streamSoundDevice")?.value||"",volume:testVolume},true);
  };
  $("#soundSettingsForm").onsubmit=async ev=>{ev.preventDefault();const broadcaster=$("#soundDevice"),stream=$("#streamSoundDevice");const next={enabled:true,output_device:broadcaster.value,output_device_label:broadcaster.selectedOptions[0]?.textContent||"",stream_output_device:stream.value,stream_output_device_label:stream.selectedOptions[0]?.textContent||"",chat_sound:$("#chatSound").value,volume:Number($("#soundVolume").value),alerts:{}};$$('[data-sound-platform]').forEach(el=>{const p=el.dataset.soundPlatform;next.alerts[p]=next.alerts[p]||{};next.alerts[p][el.dataset.soundEvent]=el.value;});const out=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({general:{sound:next}})});$("#soundSettingsResult").textContent=out.ok?L("Gespeichert.","Saved."):out.error||L("Fehler beim Speichern.","Could not save.");if(out.ok)soundRuntimeConfig=next;};
  $("#colorSchemeForm").onsubmit=async ev=>{ev.preventDefault();const next={color_scheme:$("#colorScheme").value,custom_colors:collectCustomColors()};const out=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ui:next})});$("#colorSchemeResult").textContent=out.ok?L("Gespeichert.","Saved."):out.error||L("Fehler beim Speichern.","Could not save.");if(out.ok)applyColorScheme(next.color_scheme,next.custom_colors);};
}
let soundRuntimeConfig=null;
let soundSeen=new Set();
let soundBaselineReady=false;
let soundPollBusy=false;
let visibleChatSoundPollBusy=false;
let incomingSoundQueue=Promise.resolve();
function soundMessageKey(item){return [item.id||"",item.message_id||"",item.platform||"",item.time||"",item.user||"",item.text||"",item.event_type||item.alert_type||item.message_type||""].join("|");}
function enqueueIncomingSound(name,isAlert,cfg){
  const snapshot={...cfg,alerts:{...(cfg.alerts||{})}};
  // A chat notification belongs to the instant its row appears; it must not
  // wait behind an older sound in the alert queue.
  if(!isAlert){playSoundForAudience(name,false,snapshot,false,false);return;}
  incomingSoundQueue=incomingSoundQueue.catch(()=>false).then(()=>playSoundForAudience(name,isAlert,snapshot,false,true));
}
async function playConfiguredSound(name,deviceId="",fallbackToDefault=false,requestPermission=false,waitUntilEnded=false,volume=100){
  if(!name||name==="__off__")return false;
  try{
    const audio=new Audio(`/sound-asset/${encodeURIComponent(name)}`);
    audio.volume=normalizedVolume(volume)/100;
    if(deviceId&&deviceId!=="__default__"&&typeof audio.setSinkId==="function"){
      try{await audio.setSinkId(deviceId);}
      catch(error){
        if(requestPermission&&typeof navigator.mediaDevices?.selectAudioOutput==="function"){
          try{
            const chosen=await navigator.mediaDevices.selectAudioOutput({deviceId});
            await audio.setSinkId(chosen.deviceId);
          }catch(permissionError){console.warn("Audiogerät wurde nicht freigegeben",permissionError);return false;}
        }else{console.warn("Audiogerät ist nicht verfügbar",error);return false;}
      }
    }
    await audio.play();
    if(waitUntilEnded)await new Promise(resolve=>{const done=()=>resolve();audio.addEventListener("ended",done,{once:true});audio.addEventListener("error",done,{once:true});setTimeout(done,30000);});
    return true;
  }catch(e){console.warn("Sound konnte nicht abgespielt werden",e);return false;}
}
async function playSoundForAudience(name,isAlert,cfg,requestPermission=false,waitUntilEnded=false){
  const broadcaster=cfg.output_device||"";
  const volume=normalizedVolume(cfg.volume);
  const broadcasterPlay=playConfiguredSound(name,broadcaster,true,requestPermission,waitUntilEnded,volume);
  if(!isAlert)return broadcasterPlay;
  const stream=cfg.stream_output_device||"";
  const sameDevice=stream==="__default__"?(broadcaster===""||broadcaster==="default"):(stream&&stream===broadcaster);
  const streamPlay=stream&&!sameDevice?playConfiguredSound(name,stream,false,requestPermission,waitUntilEnded,volume):Promise.resolve(true);
  const [played]=await Promise.all([broadcasterPlay,streamPlay]);
  return played;
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
  if(soundPollBusy)return;
  soundPollBusy=true;
  try{
    if(!soundRuntimeConfig){
      const all=await api("/api/settings");soundRuntimeConfig=all.general?.sound||{};
      applyColorScheme(all.ui?.color_scheme||"system",all.ui?.custom_colors||null);
      const devices=await audioOutputDevices();
      soundRuntimeConfig.output_device=resolveSavedDeviceId(devices,soundRuntimeConfig.output_device,soundRuntimeConfig.output_device_label);
      soundRuntimeConfig.stream_output_device=resolveSavedDeviceId(devices,soundRuntimeConfig.stream_output_device,soundRuntimeConfig.stream_output_device_label);
    }
    const out=await api("/api/messages");
    const messages=Array.isArray(out.messages)?out.messages:[];
    if(!soundBaselineReady){messages.forEach(item=>soundSeen.add(soundMessageKey(item)));soundBaselineReady=true;return;}
    for(const item of messages){
      const key=soundMessageKey(item);if(soundSeen.has(key))continue;soundSeen.add(key);
      const type=String(item.message_type||item.type||"chat").toLowerCase();
      // Chat audio is triggered exclusively by the native desktop window once
      // the new row is rendered. This poller remains responsible for alerts.
      if(["chat","message","comment"].includes(type))continue;
      const name=configuredSoundForMessage(item,soundRuntimeConfig);
      const isAlert=!["chat","message","comment"].includes(type);
      if(name)enqueueIncomingSound(name,isAlert,soundRuntimeConfig);
    }
    if(soundSeen.size>600)soundSeen=new Set(messages.map(soundMessageKey));
  }catch(_){}finally{soundPollBusy=false;}
}
async function pollVisibleChatSounds(){
  if(visibleChatSoundPollBusy)return;
  visibleChatSoundPollBusy=true;
  try{
    const out=await api("/api/desktop-chat/sound-events");
    const events=Array.isArray(out.events)?out.events:[];
    if(!events.length)return;
    if(!soundRuntimeConfig){
      const all=await api("/api/settings");soundRuntimeConfig=all.general?.sound||{};
      const devices=await audioOutputDevices();
      soundRuntimeConfig.output_device=resolveSavedDeviceId(devices,soundRuntimeConfig.output_device,soundRuntimeConfig.output_device_label);
    }
    for(const item of events){
      const name=configuredSoundForMessage(item,soundRuntimeConfig);
      if(name)enqueueIncomingSound(name,false,soundRuntimeConfig);
    }
  }catch(_){}finally{visibleChatSoundPollBusy=false;}
}
async function bootPage(){
  try{
    await (({dashboard:renderDashboard,platforms:renderPlatforms,chat:renderChat,obs_meld:renderObsMeld,spotify:renderSpotify,easyslider:renderEasyslider,endstream:renderEndstream,overlays:renderOverlays,tutorials:renderTutorials,plugins:renderPlugins,settings:renderSettings,chattim3r:renderChattim3r,commands:()=>renderDedicatedPlugin("commands","commands",L("Eigene Chat-Commands, Antworten und OBS/Meld-Aktionen verwalten.","Manage custom chat commands, replies and OBS/Meld actions.")),modalot:()=>renderDedicatedPlugin("modalot","Modalot",L("Moderation und Regeln zentral verwalten.","Manage moderation and rules centrally.")),info3ditor:()=>renderDedicatedPlugin("info3ditor","Info3ditor",L("Streaminformationen und Vorlagen verwalten.","Manage stream information and presets.")),gam3pick3r:()=>renderDedicatedPlugin("gam3pick3r","gam3pick3r",L("Spielauswahl, Voting und Picker verwalten.","Manage game selection, voting and picker.")),dev:renderDev}[page]||renderDashboard)());
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
pollVisibleChatSounds();
setInterval(pollIncomingSounds,1000);
setInterval(pollVisibleChatSounds,100);
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
