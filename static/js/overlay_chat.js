
async function load(){
 const r=await fetch('/api/messages',{cache:'no-store'}); const d=await r.json();
 const el=document.getElementById('chatOverlay');
 el.innerHTML=(d.messages||[]).slice(-12).map(m=>`<div class="oMsg"><span class="p">${m.platform}</span><b>${m.user}</b>: ${String(m.text||'').replace(/[&<>"']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[s]))}</div>`).join('');
}
load(); setInterval(load,1500);
