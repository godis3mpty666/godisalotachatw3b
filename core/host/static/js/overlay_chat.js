
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const mark={twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"};
function userColor(platform,user){let h=2166136261;for(const c of `${platform}:${user}`){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `hsl(${Math.abs(h)%360} 78% 68%)`;}
function inlineMessage(m){return String(m.html||esc(m.text)).replace(/<br\s*\/?\s*>/gi," ").replace(/<(?:div|p)\b[^>]*>/gi,"<span>").replace(/<\/(?:div|p)>/gi,"</span>");}
function chatBadges(m){return (Array.isArray(m?.badges)?m.badges:[]).map(b=>{const url=String(b.url||"").trim();if(!url)return "";const title=esc(b.title||b.kind||"Badge");return `<span class="chatRoleBadge" title="${title}"><img src="${esc(url)}" alt="${title}"></span>`;}).join("");}
async function load(){
 const r=await fetch('/api/chat-state',{cache:'no-store'}); const d=await r.json();
 const el=document.getElementById('chatOverlay');
 el.innerHTML=(d.messages||[]).filter(m=>m.message_type==="chat").slice(-12).map(m=>`<div class="oMsg"><span class="p"><img src="/platform-icon/${esc(m.platform)}" alt="${esc(mark[m.platform]||m.platform)}"></span>${chatBadges(m)}<b style="color:${userColor(m.platform,m.user)}">${esc(m.user)}</b>: <span class="chatText">${inlineMessage(m)}</span></div>`).join('');
}
load(); setInterval(load,1500);
