'use strict';

const $ = (id) => document.getElementById(id);
const state = { csrf: '', aliases: [], messages: [], stats: {}, config: {}, selected: null,
  aliasId: null, unread: false, search: '', hasMore: false, loading: false };
let toastTimer;
let searchTimer;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function tell(message, error=false) {
  const t = $('toast'); t.textContent = message; t.className = `toast show${error?' error':''}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.className='toast'; }, 4400);
}
async function api(path, options={}) {
  const headers = { 'Accept': 'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}), ...options.headers };
  if (state.csrf && options.method && !['GET','HEAD'].includes(options.method)) headers['X-CSRF-Token'] = state.csrf;
  let response;
  try { response = await fetch('/api' + path, { credentials:'same-origin', cache:'no-store', ...options, headers }); }
  catch { throw new Error('Keine Verbindung zum Server. Bitte Netzwerk prüfen.'); }
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    if (response.status === 401 && path !== '/login' && path !== '/me') showLogin();
    throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
  }
  return data;
}
function showLogin() { state.csrf=''; $('login-screen').hidden=false; $('app-shell').hidden=true; $('login-password').value=''; }
function showApp() { $('login-screen').hidden=true; $('app-shell').hidden=false; }
function fmtDate(unix) {
  return new Date(unix*1000).toLocaleDateString('de-DE', { day:'2-digit',month:'short',year:'numeric' });
}
function fmtShort(unix) {
  const d = new Date(unix*1000), n = new Date();
  if (d.toDateString() === n.toDateString()) return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'});
}
function initials(name) { const clean = name.replace(/<[^>]*>/g,'').trim(); return (clean[0] || '?').toUpperCase(); }
async function clipboard(text) {
  try { await navigator.clipboard.writeText(text); tell('E-Mail-Adresse kopiert'); }
  catch { window.prompt('Adresse kopieren:', text); }
}
async function fetchAll() {
  const [a, s] = await Promise.all([api('/aliases'), api('/stats')]);
  state.aliases=a.aliases; state.stats=s;
  renderStats(); renderAliases(); await fetchMessages(false);
}
async function fetchMessages(more=false) {
  if (state.loading) return;
  state.loading=true;
  $('load-more').disabled=true;
  try {
    const qp = new URLSearchParams();
    if (state.aliasId !== null) qp.set('alias_id', state.aliasId);
    if (state.unread) qp.set('unread_only', 'true');
    if (state.search) qp.set('q',state.search);
    if (more && state.messages.length) qp.set('before_id', state.messages[state.messages.length-1].id);
    const data = await api('/messages?' + qp);
    state.messages = more ? state.messages.concat(data.messages) : data.messages;
    state.hasMore=data.has_more;
    renderMessages();
  } finally { state.loading=false; $('load-more').disabled=false; }
}
function renderStats() {
  $('stat-active').textContent=state.stats.active_aliases ?? 0;
  $('stat-messages').textContent=state.stats.message_count ?? 0;
  $('stat-unread').textContent=state.stats.unread_count ?? 0;
  $('nav-all-count').textContent=state.stats.message_count ?? 0;
  $('nav-unread-count').textContent=state.stats.unread_count ?? 0;
}
function selectView(type, aliasId=null) {
  state.aliasId=aliasId; state.unread=type==='unread'; state.selected=null;
  $('nav-inbox').classList.toggle('active',type==='all'); $('nav-unread').classList.toggle('active',type==='unread');
  const local=state.aliases.find(a=>a.id===aliasId);
  const title= local ? local.local_part+'@'+state.config.alias_domain : type==='unread' ? 'Ungelesene E-Mails' : 'Dein Posteingang';
  $('page-title').textContent=title; $('page-title').append(el('span','period','.'));
  $('breadcrumb-page').textContent=local?'ADRESSE':type==='unread'?'UNGELESEN':'POSTEINGANG';
  $('filter-desc').textContent=local?'Nachrichten an diese Adresse':state.unread?'Nur ungelesene Nachrichten':'Alle eingegangenen E-Mails';
  renderAliases(); clearDetail(); fetchMessages(false).catch(e=>tell(e.message,true));
}
function renderAliases() {
  const panel=$('alias-nav'); panel.replaceChildren();
  if (!state.aliases.length) panel.append(el('div','alias-item','Noch keine Adressen'));
  for (const a of state.aliases) {
    const btn=el('button','alias-item'+(state.aliasId===a.id?' selected':'')); btn.type='button';
    btn.title=a.address;
    btn.append(el('span','alias-bullet'+(a.active?'':' off')),el('span','alias-name',a.local_part),el('span','alias-count',a.unread_count?`● ${a.unread_count}`:''));
    btn.addEventListener('click',()=>selectView('alias',a.id)); panel.append(btn);
  }
  renderManage();
}
function renderMessages() {
  const panel=$('message-list'); panel.replaceChildren();
  $('list-count').textContent=state.messages.length+(state.hasMore?'+':'');
  $('load-more').hidden=!state.hasMore;
  if (!state.messages.length) {
    const empty=el('div','empty-list');
    empty.append(el('div','empty-illustration','✉'),el('strong','Hier ist es noch ruhig.'),el('p','Neue Nachrichten erscheinen automatisch nach der nächsten Aktualisierung.'));
    panel.append(empty); return;
  }
  for (const msg of state.messages) {
    const btn=el('button','message-row'+(msg.is_read?'':' unread')+(state.selected===msg.id?' selected':'')); btn.type='button';
    const bubble=el('span','sender-avatar',initials(msg.sender));
    const content=el('span','message-core');
    const meta=el('span','message-meta');meta.append(el('span','message-sender',msg.sender),el('span','message-date',fmtShort(msg.received_at)));
    content.append(meta,el('div','message-subject',msg.subject),el('div','message-preview',msg.preview),el('span','message-tag',msg.local_part+'@'+state.config.alias_domain));
    btn.append(bubble,content); btn.addEventListener('click',()=>openMessage(msg.id)); panel.append(btn);
  }
}
function clearDetail() {
  const root=$('message-detail'); root.replaceChildren();
  const e=el('div','detail-empty');e.append(el('div','empty-icon','✉'),el('strong','Ein ruhiger Posteingang.'),el('span','','Wähle eine Nachricht aus, um sie hier zu lesen.'));
  root.append(e);
}
async function openMessage(id) {
  state.selected=id; renderMessages();
  try {
    const msg=await api('/messages/'+id);
    const root=$('message-detail'); root.replaceChildren();
    const article=el('article','open-message');const actions=el('div','detail-actions');
    const del=el('button','delete-button','Löschen');del.type='button';del.addEventListener('click',async()=>{
      if(!window.confirm('Nachricht wirklich dauerhaft löschen?')) return;
      try { await api('/messages/'+id,{method:'DELETE'});state.selected=null;clearDetail();await fetchAll();tell('Nachricht gelöscht'); }
      catch(e){tell(e.message,true);}
    });
    actions.append(el('span','detail-label','NACHRICHT'),del);
    const sender=el('div','detail-sender');const avatar=el('span','sender-avatar',initials(msg.sender));
    const info=el('div','detail-sender-info');info.append(el('strong','',msg.sender),el('small','',`An: ${msg.local_part}@${state.config.alias_domain}`));
    sender.append(avatar,info,el('span','detail-date',fmtDate(msg.received_at)));
    article.append(actions,el('h2','detail-subject',msg.subject),sender,el('div','detail-body',msg.body));root.append(article);
    if(!msg.is_read){await api('/messages/'+id+'/read',{method:'POST'}); const found=state.messages.find(m=>m.id===id);if(found)found.is_read=true;
      const [a,s]=await Promise.all([api('/aliases'),api('/stats')]);state.aliases=a.aliases;state.stats=s;renderStats();renderAliases();renderMessages(); }
  } catch(e){tell(e.message,true);}
}
function renderManage() {
  const root=$('manage-list'); root.replaceChildren();
  if(!state.aliases.length){root.append(el('p','','Noch keine Adressen vorhanden.'));return;}
  for(const a of state.aliases) {
    const row=el('div','manage-row');const b=el('span','alias-bullet'+(a.active?'':' off')); const info=el('div','manage-row-info');
    info.append(el('strong','',a.address),el('small','',`${a.message_count} Nachrichten · ${a.active?'Aktiv':'Deaktiviert'}`));
    const copy=el('button','','Kopieren');copy.type='button';copy.addEventListener('click',()=>clipboard(a.address));
    const toggle=el('button','',a.active?'Pausieren':'Aktivieren');toggle.type='button';toggle.addEventListener('click',async()=>{
      try {await api('/aliases/'+a.id,{method:'PATCH',body:JSON.stringify({active:!a.active})});await fetchAll();tell(a.active?'Adresse pausiert':'Adresse aktiviert');}
      catch(e){tell(e.message,true);}
    });
    const del=el('button','danger-link','Löschen');del.type='button';del.addEventListener('click',async()=>{
      if(!window.confirm(`Adresse ${a.address} und alle zugehörigen Nachrichten dauerhaft löschen?`))return;
      try {await api('/aliases/'+a.id,{method:'DELETE'});if(state.aliasId===a.id)state.aliasId=null;await fetchAll();tell('Adresse gelöscht');}
      catch(e){tell(e.message,true);}
    });
    row.append(b,info,copy,toggle,del);root.append(row);
  }
}
function openCreate(){ $('alias-local').value=''; $('create-dialog').showModal();$('alias-local').focus(); }
async function submitCreate(event){event.preventDefault();const local=$('alias-local').value.trim();
  try {const created=await api('/aliases',{method:'POST',body:JSON.stringify({local_part:local||null})});$('create-dialog').close();
    await fetchAll();tell('Adresse erstellt: '+created.address);await clipboard(created.address);}
  catch(e){tell(e.message,true);}
}
async function boot() {
  try {state.config=await api('/config');$('domain-suffix').textContent='@'+state.config.alias_domain;
    $('retention-label').textContent=state.config.retention_days;
    const me=await api('/me');state.csrf=me.csrf;$('profile-name').textContent=me.username;showApp();await fetchAll(); }
  catch(e){showLogin();if(!/angemeldet|abgelaufen/i.test(e.message))tell(e.message,true);}
}
$('login-form').addEventListener('submit',async(event)=>{event.preventDefault();$('login-error').hidden=true;
  try {await api('/login',{method:'POST',body:JSON.stringify({username:$('login-user').value,password:$('login-password').value})});await boot();}
  catch(e){$('login-error').textContent=e.message;$('login-error').hidden=false;}
});
$('logout-button').addEventListener('click',async()=>{try{await api('/logout',{method:'POST'});showLogin();tell('Du wurdest abgemeldet.');}catch(e){tell(e.message,true);}});
$('nav-inbox').addEventListener('click',()=>selectView('all'));
$('nav-unread').addEventListener('click',()=>selectView('unread'));
$('refresh-button').addEventListener('click',()=>fetchAll().then(()=>tell('Posteingang aktualisiert')).catch(e=>tell(e.message,true)));
$('create-button').addEventListener('click',openCreate);
$('sidebar-create').addEventListener('click',openCreate);
$('close-create').addEventListener('click',()=>$('create-dialog').close());
$('cancel-create').addEventListener('click',()=>$('create-dialog').close());
$('create-form').addEventListener('submit',submitCreate);
$('manage-aliases').addEventListener('click',()=>$('manage-dialog').showModal());
$('close-manage').addEventListener('click',()=>$('manage-dialog').close());
$('done-manage').addEventListener('click',()=>$('manage-dialog').close());
$('manage-create').addEventListener('click',()=>{$('manage-dialog').close();openCreate();});
$('mail-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.search=$('mail-search').value.trim();fetchMessages(false).catch(e=>tell(e.message,true));},300);});
$('load-more').addEventListener('click',()=>fetchMessages(true).catch(e=>tell(e.message,true)));
boot();

// Refresh quietly while the dashboard is visible; never poll hidden mobile tabs.
setInterval(() => { if (!$('app-shell').hidden && document.visibilityState === 'visible' && !state.loading) { fetchAll().catch(() => {}); } }, 30000);
