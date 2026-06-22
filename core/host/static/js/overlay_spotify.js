let overlayState=null, fonts=[], selected='background', nowPlaying={};
let nowPlayingLoading=false, nowPlayingLoaded=false, nowPlayingFailures=0;
let overlaySaveTimer=null, overlaySaveQueue=Promise.resolve();
let overlayStateSyncing=false;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const uid=()=> 'x'+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
function clamp(v,min,max){v=Number(v); if(Number.isNaN(v)) return min; return Math.max(min,Math.min(max,v));}

async function loadState(){
 try{
  const [r,f]=await Promise.all([fetch('/api/spotis3mptify/overlay-state',{cache:'no-store'}), fetch('/api/system-fonts',{cache:'no-store'}).catch(()=>null)]);
  if(!r.ok)throw new Error(`API Error: ${r.status}`);
  overlayState=await r.json();
  fonts=f?((await f.json()).fonts||[]):['Segoe UI','Arial','Verdana','Tahoma','Consolas','Impact'];
  renderExtras();
  applyState();
  buildSelect();
  fillEditor();
  initDrag();
 }catch(e){
  console.error('LoadState Error:',e);
  showStatus('Fehler beim Laden: '+e.message, 'error');
 }
}

// A browser source is a separate page from the editor. Meld can keep that
// page alive for hours, so it must observe saved layout changes itself instead
// of depending on a browser-source reload.
async function syncOverlayState(){
 if(overlayStateSyncing||!overlayState||document.body.classList.contains('editing'))return;
 overlayStateSyncing=true;
 try{
  const r=await fetch('/api/spotis3mptify/overlay-state?_='+Date.now(),{cache:'no-store'});
  if(!r.ok)return;
  const next=await r.json();
  // Reapply even when the serialized config looks identical. Some embedded
  // Chromium views retain inline paint state after a source resize/reload.
  // This makes the saved state authoritative for every running browser source.
  overlayState=next;
  renderExtras();
  applyState();
 }catch(_){
  // Keep rendering the last valid state while the local server restarts.
 }finally{
  overlayStateSyncing=false;
 }
}

function elCfg(id){
 if(id.startsWith('extra:'))return overlayState.extras.find(x=>x.id===id.slice(6));
 return overlayState[id];
}

function domFor(id){
 if(id==='background')return $('#bgEl');
 if(id==='cover')return $('#coverEl');
 if(id==='title')return $('#titleEl');
 if(id==='artist')return $('#artistEl');
 if(id.startsWith('extra:'))return document.querySelector(`[data-extra-id="${CSS.escape(id.slice(6))}"]`);
}

function setBox(dom,c){
 if(!dom||!c)return;
 dom.style.display=c.enabled===false?'none':'block';
 dom.style.left=(c.x||0)+'px';
 dom.style.top=(c.y||0)+'px';
 dom.style.width=(c.w||80)+'px';
 dom.style.height=(c.h||30)+'px';
}

function applyState(){
 const s=overlayState;
 setBox($('#bgEl'),s.background);
 $('#bgEl').style.borderRadius=(s.background.radius||0)+'px';
 $('#bgEl').style.background=hexToRgba(s.background.color||'#4a4d56', s.background.opacity??.72);

 setBox($('#coverEl'),s.cover);
 $('#coverEl').style.borderRadius=s.cover.shape==='circle'?'50%':((s.cover.radius||0)+'px');
 $('#coverEl').classList.toggle('rotating',!!s.cover.rotate);

 setText('title', nowPlaying.title||'Kein Song aktiv');
 setText('artist', nowPlaying.artist||'');

 ['title','artist'].forEach(k=>{
  const c=s[k], d=domFor(k);
  setBox(d,c);
  d.style.fontSize=(c.fontSize||20)+'px';
  d.style.fontFamily=c.fontFamily||'Segoe UI';
  d.style.color=c.color||'#fff';
  d.style.textTransform=c.uppercase?'uppercase':'none';
  refreshMarquee(k);
 });

 renderExtras();
 document.querySelectorAll('.ovEl').forEach(x=>x.classList.remove('selected'));
 const sd=domFor(selected);
 if(sd)sd.classList.add('selected');
}

function setText(k,t){
 const sp=k==='title'?$('#spTitle'):$('#spArtist');
 if(!sp)return;
 const value=t||'';
 const clone=sp.closest('.textTrack')?.querySelector('.textClone');
 if(sp.textContent===value&&(!clone||clone.textContent===value))return;
 sp.textContent=value;
 if(clone)clone.textContent=value;
 refreshMarquee(k);
}

function refreshMarquee(k){
 requestAnimationFrame(()=>{
  const d=domFor(k), c=overlayState?.[k];
  if(!d||!c)return;
  const track=d.querySelector('.textTrack');
  const text=track?.querySelector('span:not(.textClone)');
  if(!track||!text)return;
  const mode=c.marqueeMode||'off';
  const gap=clamp(c.marqueeGap??60,0,1000);
  const textWidth=text.getBoundingClientRect().width;
  const fieldWidth=d.clientWidth;
  const overflow=Math.max(0,textWidth-fieldWidth);
  const speed=clamp(c.marqueeSpeed??45,5,500);
  const marqueeKey=[text.textContent,mode,gap,speed,Math.round(textWidth),fieldWidth].join('|');
  if(d.dataset.marqueeKey===marqueeKey)return;
  d.dataset.marqueeKey=marqueeKey;
  d.classList.remove('marqueeActive','marqueeBounce','marqueeLoopRtl','marqueeLoopLtr');
  track.style.removeProperty('--marquee-distance');
  track.style.removeProperty('--marquee-duration');
  track.style.setProperty('--marquee-gap',`${gap}px`);
  if(mode==='off'||overflow<1)return;
  const looping=mode==='loop-rtl'||mode==='loop-ltr';
  const distance=looping?textWidth+gap:overflow;
  track.style.setProperty('--marquee-distance',`${distance}px`);
  track.style.setProperty('--marquee-duration',`${Math.max(.2,distance/speed)}s`);
  d.classList.add('marqueeActive');
  d.classList.add(mode==='bounce'?'marqueeBounce':mode==='loop-ltr'?'marqueeLoopLtr':'marqueeLoopRtl');
 });
}

function hexToRgba(hex,op){
 hex=String(hex||'#000').replace('#','');
 if(hex.length===3)hex=hex.split('').map(x=>x+x).join('');
 const n=parseInt(hex,16);
 return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${op})`;
}

function renderExtras(){
 const layer=$('#extrasLayer');
 layer.innerHTML=(overlayState.extras||[]).map(x=>{
  if(x.type==='text')return `<div class="ovEl textEl extraText" data-el="extra:${esc(x.id)}" data-extra-id="${esc(x.id)}"><span>${esc(x.text||'Text')}</span></div>`;
  if(x.type==='rect')return `<div class="ovEl extraRect" data-el="extra:${esc(x.id)}" data-extra-id="${esc(x.id)}"></div>`;
  if(x.type==='circle')return `<div class="ovEl extraCircle" data-el="extra:${esc(x.id)}" data-extra-id="${esc(x.id)}"></div>`;
  return '';
 }).join('');

 (overlayState.extras||[]).forEach(x=>{
  const d=domFor('extra:'+x.id);
  if(!d)return;
  setBox(d,x);
  if(x.type==='text'){
   d.style.fontSize=(x.fontSize||24)+'px';
   d.style.fontFamily=x.fontFamily||'Segoe UI';
   d.style.color=x.color||'#fff';
   d.style.textTransform=x.uppercase?'uppercase':'none';
  }
  if(x.type==='rect'){
   d.style.background=hexToRgba(x.color||'#865cff', x.opacity??.5);
   d.style.borderRadius=(x.radius||0)+'px';
  }
  if(x.type==='circle'){
   d.style.background=hexToRgba(x.color||'#5fd7ff', x.opacity??.5);
   d.style.borderRadius='50%';
  }
 });
}

function buildSelect(){
 const options=[
  ['background','Hintergrund'],
  ['cover','Cover'],
  ['title','Titel'],
  ['artist','Artist'],
  ...(overlayState.extras||[]).map(x=>{
   const label=x.type==='text'?'Text: '+(x.text||'Text'):x.type==='rect'?'Rechteck':'Kreis';
   return ['extra:'+x.id, label];
  })
 ];
 $('#selectedElement').innerHTML=options.map(o=>`<option value="${esc(o[0])}" ${selected===o[0]?'selected':''}>${esc(o[1])}</option>`).join('');
 $('#selectedElement').onchange=e=>{selected=e.target.value; fillEditor(); applyState();};
}

function fontOptions(cur){
 return fonts.map(f=>`<option value="${esc(f)}" ${f===cur?'selected':''}>${esc(f)}</option>`).join('');
}

function baseFields(c){
 return `<label><span>Sichtbar</span><input data-k="enabled" type="checkbox" ${c.enabled!==false?'checked':''}></label>
  <label><span>X</span><input data-k="x" type="number" value="${c.x||0}"></label>
  <label><span>Y</span><input data-k="y" type="number" value="${c.y||0}"></label>
  <label><span>Breite</span><input data-k="w" type="number" value="${c.w||80}"></label>
  <label><span>Höhe</span><input data-k="h" type="number" value="${c.h||30}"></label>`;
}

function fillEditor(){
 const c=elCfg(selected);
 if(!c)return;
 let html='<div class="gridEdit">'+baseFields(c);

 if(selected==='background'){
  html+=`<label><span>Radius</span><input data-k="radius" type="number" value="${c.radius||0}"></label>
   <label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#4a4d56'}"></label>
   <label><span>Deckkraft</span><input data-k="opacity" type="number" min="0" max="1" step="0.05" value="${c.opacity??.72}"></label>`;
 }

 if(selected==='cover'){
  html+=`<label><span>Form</span><select data-k="shape">
   <option value="rounded" ${c.shape!=='circle'?'selected':''}>Ecken / Radius</option>
   <option value="circle" ${c.shape==='circle'?'selected':''}>Kreis</option>
   </select></label>
   <label><span>Radius</span><input data-k="radius" type="number" value="${c.radius||0}"></label>
   <label><span>Rotieren</span><input data-k="rotate" type="checkbox" ${c.rotate?'checked':''}></label>`;
 }

 if(['title','artist'].includes(selected)){
  html+=`<label><span>Text</span><input data-k="text" type="text" value="${esc(c.text||'')}" disabled></label>
   <label><span>Font</span><select data-k="fontFamily">${fontOptions(c.fontFamily||'Segoe UI')}</select></label>
   <label><span>Größe</span><input data-k="fontSize" type="number" value="${c.fontSize||24}"></label>
   <label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#ffffff'}"></label>
   <label><span>Uppercase</span><input data-k="uppercase" type="checkbox" ${c.uppercase?'checked':''}></label>
   <label><span>Scrollen</span><select data-k="marqueeMode">
    <option value="off" ${!c.marqueeMode||c.marqueeMode==='off'?'selected':''}>Aus</option>
    <option value="bounce" ${c.marqueeMode==='bounce'?'selected':''}>Hin und her</option>
    <option value="loop-rtl" ${c.marqueeMode==='loop-rtl'?'selected':''}>Loop rechts nach links</option>
    <option value="loop-ltr" ${c.marqueeMode==='loop-ltr'?'selected':''}>Loop links nach rechts</option>
   </select></label>
   <label><span>Tempo px/s</span><input data-k="marqueeSpeed" type="number" min="5" max="500" value="${c.marqueeSpeed??45}"></label>
   <label><span>Loop-Lücke px</span><input data-k="marqueeGap" type="number" min="0" max="1000" value="${c.marqueeGap??60}"></label>`;
 }

 if(selected.startsWith('extra:')){
  const extra=c;
  if(extra.type==='text'){
   html+=`<label><span>Text</span><input data-k="text" type="text" value="${esc(c.text||'')}"></label>
    <label><span>Font</span><select data-k="fontFamily">${fontOptions(c.fontFamily||'Segoe UI')}</select></label>
    <label><span>Größe</span><input data-k="fontSize" type="number" value="${c.fontSize||24}"></label>
    <label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#ffffff'}"></label>
    <label><span>Deckkraft</span><input data-k="opacity" type="number" min="0" max="1" step="0.05" value="${c.opacity??1}"></label>
    <label><span>Uppercase</span><input data-k="uppercase" type="checkbox" ${c.uppercase?'checked':''}></label>`;
  }
  if(extra.type==='rect'){
   html+=`<label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#865cff'}"></label>
    <label><span>Deckkraft</span><input data-k="opacity" type="number" min="0" max="1" step="0.05" value="${c.opacity??.5}"></label>
    <label><span>Radius</span><input data-k="radius" type="number" value="${c.radius||0}"></label>`;
  }
  if(extra.type==='circle'){
   html+=`<label><span>Farbe</span><input data-k="color" type="color" value="${c.color||'#5fd7ff'}"></label>
    <label><span>Deckkraft</span><input data-k="opacity" type="number" min="0" max="1" step="0.05" value="${c.opacity??.5}"></label>`;
  }
  html+='</div><div class="editBtns"><button class="danger" id="deleteExtra">Element löschen</button></div>';
 } else {
  html+='</div>';
 }

 $('#elementEditor').innerHTML=html;
 $('#elementEditor').querySelectorAll('[data-k]').forEach(i=>i.addEventListener('input',()=>{
  const key=i.dataset.k;
  if(i.type==='checkbox') c[key]=i.checked;
  else if(i.type==='number') c[key]=Number(i.value);
  else c[key]=i.value;
  if(key==='text') buildSelect();
  applyState();
  scheduleOverlaySave();
 }));
 const del=$('#deleteExtra');
 if(del)del.onclick=()=>{
  overlayState.extras=overlayState.extras.filter(x=>'extra:'+x.id!==selected);
  selected='background';
  buildSelect();
  fillEditor();
  applyState();
  scheduleOverlaySave();
 };
}

async function loadNowPlaying(){
 if(document.body.classList.contains('editing'))return;
 if(nowPlayingLoading)return;
 nowPlayingLoading=true;
 try{
  const r=await fetch('/api/nowplaying?_='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw new Error(`API Error: ${r.status}`);
  const d=(await r.json())||{};
  nowPlaying=d;
  nowPlayingLoaded=true;
  nowPlayingFailures=0;
  setText('title',d.title||'Kein Song aktiv');
  setText('artist',d.artist||'');
  const img=$('#spCover'), disc=$('#spDisc');
  if(d.cover){
   img.src=d.cover;
   img.style.display='block';
   disc.style.display='none';
  }else{
   img.removeAttribute('src');
   img.style.display='none';
   disc.style.display='block';
  }
 }catch(e){
  nowPlayingFailures++;
  console.error('LoadNowPlaying Error:',e);
  if(!nowPlayingLoaded&&nowPlayingFailures>=3){
   setText('title','Spotify Fehler');
   setText('artist','Verbindung fehlgeschlagen');
  }
 }finally{
  nowPlayingLoading=false;
 }
}

function showStatus(msg, type='success'){
 const el=$('#saveStatus');
 el.textContent=msg;
 el.style.background=type==='error'?'rgba(255,85,119,.2)':'rgba(46,233,135,.2)';
 el.style.color=type==='error'?'#ff5577':'#2ee987';
 el.style.display='block';
 setTimeout(()=>{el.style.display='none';}, 3000);
}

function persistOverlayState(notify=false){
 if(!overlayState)return Promise.resolve(false);
 if(overlaySaveTimer){
  clearTimeout(overlaySaveTimer);
  overlaySaveTimer=null;
 }
 const snapshot=JSON.stringify(overlayState);
 overlaySaveQueue=overlaySaveQueue.catch(()=>false).then(async()=>{
  const r=await fetch('/api/spotis3mptify/overlay-state',{
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:snapshot
  });
  if(!r.ok)throw new Error(`Save Error: ${r.status}`);
  await r.json();
  if(notify)showStatus('Erfolgreich gespeichert!', 'success');
  return true;
 }).catch(e=>{
  console.error('Save Error:',e);
  showStatus('Fehler beim Speichern: '+e.message, 'error');
  return false;
 });
 return overlaySaveQueue;
}

function scheduleOverlaySave(){
 if(overlaySaveTimer)clearTimeout(overlaySaveTimer);
 overlaySaveTimer=setTimeout(()=>persistOverlayState(false),500);
}

function initEdit(){
 $('#editOverlayBtn').onclick=async()=>{
  if(document.body.classList.contains('editing')){
   await persistOverlayState(false);
   document.body.classList.remove('editing');
   loadNowPlaying();
  }else{
   document.body.classList.add('editing');
  }
 };
 $('#closeOverlayEdit').onclick=async()=>{
  await persistOverlayState(false);
  document.body.classList.remove('editing');
  loadNowPlaying();
 };

 $('#addTextEl').onclick=()=>{
  const id=uid();
  overlayState.extras.push({id,type:'text',text:'Neues Element',enabled:true,x:50,y:150,w:260,h:40,fontSize:24,fontFamily:'Segoe UI',color:'#ffffff',opacity:1});
  selected='extra:'+id;
  renderExtras();
  buildSelect();
  fillEditor();
  initDrag();
  applyState();
  scheduleOverlaySave();
 };

 $('#addRectEl').onclick=()=>{
  const id=uid();
  overlayState.extras.push({id,type:'rect',enabled:true,x:50,y:200,w:200,h:100,color:'#865cff',opacity:.5,radius:8});
  selected='extra:'+id;
  renderExtras();
  buildSelect();
  fillEditor();
  initDrag();
  applyState();
  scheduleOverlaySave();
 };

 $('#addCircleEl').onclick=()=>{
  const id=uid();
  overlayState.extras.push({id,type:'circle',enabled:true,x:50,y:250,w:80,h:80,color:'#5fd7ff',opacity:.5});
  selected='extra:'+id;
  renderExtras();
  buildSelect();
  fillEditor();
  initDrag();
  applyState();
  scheduleOverlaySave();
 };

 $('#saveOverlay').onclick=async()=>{
  if(await persistOverlayState(true)){
   document.body.classList.remove('editing');
   loadNowPlaying();
  }
 };
}

function initDrag(){
 const stage=$('#spotifyStage');
 if(stage.dataset.dragReady==='true')return;
 stage.dataset.dragReady='true';

 stage.addEventListener('pointerdown',e=>{
  if(!document.body.classList.contains('editing')||e.button!==0)return;
  const el=e.target.closest('.ovEl');
  if(!el||!stage.contains(el))return;

  e.preventDefault();
  selected=el.dataset.el;
  const c=elCfg(selected);
  if(!c)return;
  const rect=el.getBoundingClientRect();
  const resizing=e.clientX>=rect.right-16&&e.clientY>=rect.bottom-16;

  buildSelect();
  fillEditor();
  applyState();

  const sx=e.clientX, sy=e.clientY, ox=c.x||0, oy=c.y||0, ow=c.w||rect.width, oh=c.h||rect.height;

  const move=ev=>{
   if(resizing){
    c.w=Math.max(8,Math.round(ow+ev.clientX-sx));
    c.h=Math.max(8,Math.round(oh+ev.clientY-sy));
   }else{
    c.x=Math.round(ox+ev.clientX-sx);
    c.y=Math.round(oy+ev.clientY-sy);
   }
   applyState();
   fillEditor();
  };
  const stop=()=>{
   document.removeEventListener('pointermove',move);
   document.removeEventListener('pointerup',stop);
   document.removeEventListener('pointercancel',stop);
   scheduleOverlaySave();
  };
  document.addEventListener('pointermove',move);
  document.addEventListener('pointerup',stop);
  document.addEventListener('pointercancel',stop);
 });
}

loadState();
loadNowPlaying();
initEdit();
setInterval(loadNowPlaying,2500);
setInterval(syncOverlayState,1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncOverlayState();});
window.addEventListener('beforeunload',()=>{
 // A passive Meld/OBS browser source must never write its possibly stale
 // in-memory layout back during a reload. Only the active editor is allowed
 // to flush a last pending change on close.
 if(!overlayState||!document.body.classList.contains('editing'))return;
 navigator.sendBeacon('/api/spotis3mptify/overlay-state',new Blob([JSON.stringify(overlayState)],{type:'application/json'}));
});
