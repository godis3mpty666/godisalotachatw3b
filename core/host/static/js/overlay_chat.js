
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const mark={twitch:"Twitch",tiktok:"TikTok",youtube:"YouTube",kick:"Kick"};
function userColor(platform,user){let h=2166136261;for(const c of `${platform}:${user}`){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `hsl(${Math.abs(h)%360} 78% 68%)`;}
async function load(){
 const r=await fetch('/api/chat-state',{cache:'no-store'}); const d=await r.json();
 const el=document.getElementById('chatOverlay');
 el.innerHTML=(d.messages||[]).filter(m=>m.message_type==="chat").slice(-12).map(m=>`<div class="oMsg"><span class="p ${esc(m.platform)}"><img src="/platform-icon/${esc(m.platform)}" alt="">${esc(mark[m.platform]||m.platform)}</span><b style="color:${userColor(m.platform,m.user)}">${esc(m.user)}</b>: ${m.html||esc(m.text)}</div>`).join('');
}
load(); setInterval(load,1500);
