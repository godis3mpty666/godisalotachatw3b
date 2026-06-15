let overlayState=null, fonts=[], selected='background', selectedExtra=null, nowPlaying={};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const uid=()=> 'x'+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
function clamp(v,min,max){v=Number(v); if(Number.isNaN(v)) return min; return Math.max(min,Math.min(max,v));}
async function loadState(){
 const [r,f]=await Promise.all([fetch('/api/spotis3mptify/overlay-state',{cache:'no-store'}), fetch('/api/system-fonts',{cache:'no-store'}).catch(()=>null)]);
 overlayState=await r.json(); fonts=f?((await f.json()).fonts||[]):['Segoe UI','Arial','Verdana','Tahoma','Consolas','Impact'];
 renderExtras(); applyState(); buildSelect(); fillEditor(); initDrag();
}
function elCfg(id){ if(id.startsWith('extra:')) return overlayState.extras.find(x=>x.id===id.slice(6)); return overlayState[id]; }
function domFor(id){ if(id==='background')return $('#bgEl'); if(id==='cover')return $('#coverEl'); if(id==='title')return $('#titleEl'); if(id==='artist')return $('#artistEl'); if(id.startsWith('extra:'))return document.querySelector(`[data-extra-id="${CSS.escape(id.slice(6))}"]`); }
function setBox(dom,c){ if(!dom||!c)return; dom.style.display=c.enabled===false?'none':'block'; dom.style.left=(c.x||0)+'px'; dom.style.top=(c.y||0)+'px'; dom.style.width=(c.w||80)+'px'; dom.style.height=(c.h||30)+'px'; }
function applyState(){
 const s=overlayState;
 setBox($('#bgEl'),s.background); $('#bgEl').style.borderRadius=(s.background.radius||0)+'px'; $('#bgEl').style.background=hexToRgba(s.background.color||'#4a4d56', s.background.opacity??.72);
 setBox($('#coverEl'),s.cover); $('#coverEl').style.borderRadius=s.cover.shape==='circle'?'50%':((s.cover.radius||0)+'px'); $('#coverEl').classList.toggle('rotating',!!s.cover.rotate);
 setText('title', nowPlaying.title||'Kein Song aktiv'); setText('artist', nowPlaying.artist||'');
 ['title','artist'].forEach(k=>{const c=s[k], d=domFor(k); setBox(d,c); d.style.fontSize=(c.fontSize||20)+'px'; d.style.fontFamily=c.fontFamily||'Segoe UI'; d.style.color=c.color||'#fff'; d.style.textTransform=c.uppercase?'uppercase':'none';});
 renderExtras();
 document.querySelectorAll('.ovEl').forEach(x=>x.classList.remove('selected')); const sd=domFor(selected); if(sd)sd.classList.add('selected');
}
function setText(k,t){ const sp=k==='title'?$('#spTitle'):$('#spArtist'); if(!sp)return; sp.textContent=t||''; }
function hexToRgba(hex,op){ hex=String(hex||'#000').replace('#',''); if(hex.length===3)hex=hex.split('').map(x=>x+x).join(''); const n=parseInt(hex,16); return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${op})`; }
function renderExtras(){
 const layer=$('#extrasLayer'); layer.innerHTML=(overlayState.extras||[]).map(x=>`<div class="ovEl textEl extraText" data-el="extra:${esc(x.id)}" data-extra-id="${esc(x.id)}"><span>${esc(x.text||'Text')}</span></div>`).join('');
 (overlayState.extras||[]).forEach(x=>{ const d=domFor('extra:'+x.id); setBox(d,x); d.style.fontSize=(x.fontSize||24)+'px'; d.style.fontFamily=x.fontFamily||'Segoe UI'; d.style.color=x.color||'#fff'; });
}
function buildSelect(){
 const options=[['background','Hintergrund'],['cover','Cover'],['title','Titel'],['artist','Artist'],...(overlayState.extras||[]).map(x=>['extra:'+x.id, 'Text: '+(x.text||'Text')])];
 $('#selectedElement').innerHTML=options.map(o=>`<option value="${esc(o[0])}" ${selected===o[0]?'selected':''}>${esc(o[1])}</option>`).join('');
 $('#selectedElement').onchange=e=>{selected=e.target.value; fillEditor(); applyState();};
}
function fontOptions(cur){return fonts.map(f=>`<option value="${esc(f)}" ${f===cur?'selected':''}>${esc(f)}</option>`).join('');}
function baseFields(c){return `<label><span>Sichtbar</span><input data-k="enabled" type="checkbox" ${c.enabled!==false?'checked':''}></label><label><span>X</span><input data-k="x" type="number" value="${c.x||0}"></label><label><span>Y</span><input data-k="y" type="number" value="${c.y||0}"></label><label><span>Breite</span><input data-k="w" type="number" value="${c.w||80}"></label><label><span>Höhe</span><input data-k="h" type="number" value="${c.h||30}"></label>`;}
function fillEditor(){
 const c=elCfg(selected); if(!c)return; let html='<div class="gridEdit">'+baseFields(c);
 if(selected==='background') html+=`<label><span>Radius</span><input data-k="radius" type="number" value="${c.radius||0}"></label><label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#4a4d56'}"></label><label><span>Deckkraft</span><input data-k="opacity" type="number" min="0" max="1" step="0.05" value="${c.opacity??.72}"></label>`;
 if(selected==='cover') html+=`<label><span>Form</span><select data-k="shape"><option value="rounded" ${c.shape!=='circle'?'selected':''}>Ecken / Radius</option><option value="circle" ${c.shape==='circle'?'selected':''}>Kreis</option></select></label><label><span>Radius</span><input data-k="radius" type="number" value="${c.radius||0}"></label><label><span>Rotieren</span><input data-k="rotate" type="checkbox" ${c.rotate?'checked':''}></label>`;
 if(['title','artist'].includes(selected)||selected.startsWith('extra:')) html+=`<label><span>Text</span><input data-k="text" type="text" value="${esc(c.text||'')}" ${selected.startsWith('extra:')?'':'disabled'}></label><label><span>Font</span><select data-k="fontFamily">${fontOptions(c.fontFamily||'Segoe UI')}</select></label><label><span>Größe</span><input data-k="fontSize" type="number" value="${c.fontSize||24}"></label><label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#ffffff'}"></label><label><span>Uppercase</span><input data-k="uppercase" type="checkbox" ${c.uppercase?'checked':''} ${selected.startsWith('extra:')?'disabled':''}></label>`;
 html+='</div>'+(selected.startsWith('extra:')?'<div class="editBtns"><button class="danger" id="deleteExtra">Element löschen</button></div>':'');
 $('#elementEditor').innerHTML=html;
 $('#elementEditor').querySelectorAll('[data-k]').forEach(i=>i.addEventListener('input',()=>{ const key=i.dataset.k; if(i.type==='checkbox') c[key]=i.checked; else if(i.type==='number') c[key]=Number(i.value); else c[key]=i.value; if(key==='text') buildSelect(); applyState(); }));
 const del=$('#deleteExtra'); if(del)del.onclick=()=>{ overlayState.extras=overlayState.extras.filter(x=>'extra:'+x.id!==selected); selected='background'; buildSelect(); fillEditor(); applyState(); };
}
async function loadNowPlaying(){
 try{ const r=await fetch('/api/nowplaying?_='+Date.now(),{cache:'no-store'}); const d=await r.json(); nowPlaying=d||{};
  setText('title',d.title||'Kein Song aktiv'); setText('artist',d.artist||'');
  const img=$('#spCover'), disc=$('#spDisc');
  if(d.cover){ img.src=d.cover; img.style.display='block'; disc.style.display='none'; } else { img.removeAttribute('src'); img.style.display='none'; disc.style.display='block'; }
 }catch(e){ setText('title','Spotify Fehler'); setText('artist',String(e)); }
}
function initEdit(){
 $('#editOverlayBtn').onclick=()=>document.body.classList.toggle('editing'); $('#closeOverlayEdit').onclick=()=>document.body.classList.remove('editing');
 $('#addTextEl').onclick=()=>{const id=uid(); overlayState.extras.push({id,text:'Neues Element',enabled:true,x:50,y:150,w:260,h:40,fontSize:24,fontFamily:'Segoe UI',color:'#ffffff'}); selected='extra:'+id; renderExtras(); buildSelect(); fillEditor(); initDrag(); applyState();};
 $('#saveOverlay').onclick=async()=>{await fetch('/api/spotis3mptify/overlay-state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(overlayState)}); document.body.classList.remove('editing');};
}
function initDrag(){
 document.querySelectorAll('.ovEl').forEach(el=>{
  el.onmousedown=e=>{ if(!document.body.classList.contains('editing'))return; e.preventDefault(); selected=el.dataset.el; buildSelect(); fillEditor(); applyState(); const c=elCfg(selected); const rect=el.getBoundingClientRect(); const resizing=e.offsetX>rect.width-16&&e.offsetY>rect.height-16; const sx=e.clientX, sy=e.clientY, ox=c.x||0, oy=c.y||0, ow=c.w||rect.width, oh=c.h||rect.height;
   document.onmousemove=ev=>{ if(resizing){c.w=Math.max(8,Math.round(ow+ev.clientX-sx)); c.h=Math.max(8,Math.round(oh+ev.clientY-sy));} else {c.x=Math.round(ox+ev.clientX-sx); c.y=Math.round(oy+ev.clientY-sy);} applyState(); fillEditor(); };
   document.onmouseup=()=>{document.onmousemove=null;document.onmouseup=null;};
  };
 });
}
loadState(); loadNowPlaying(); initEdit(); setInterval(loadNowPlaying,2500);
