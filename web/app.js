'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  book:'<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H4z"/><path d="M13 7a3 3 0 0 1 3-3h5v14h-4a4 4 0 0 0-4 3"/>',
  spark:'<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4z"/><path d="m20 2 .7 2.3L23 5l-2.3.7L20 8l-.7-2.3L17 5l2.3-.7z"/>',
  cards:'<rect x="7" y="7" width="14" height="14" rx="2"/><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2M11 12h6M11 16h4"/>',
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  arrowup:'<path d="M6 18 18 6M6 6h12v12"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  upload:'<path d="M12 16V3m-4 4 4-4 4 4M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  file:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  edit:'<path d="m16 3 5 5-12 12-6 1 1-6zM13 6l5 5"/>',
  send:'<path d="m3 11 18-8-8 18-2-8zM11 13 21 3"/>',
  folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  link:'<path d="m10 13 4-4M8 15l-2 2a3.5 3.5 0 0 1-5-5l4-4a3.5 3.5 0 0 1 5 0m4 1 2-2a3.5 3.5 0 0 1 5 5l-4 4a3.5 3.5 0 0 1-5 0"/>',
  leaf:'<path d="M20 3C9 2 3 6 4 13c1 7 13 10 16-10ZM4 21c2-7 5-10 10-13"/>',
  back:'<path d="M19 12H5m5-5-5 5 5 5"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M5 16a8 8 0 0 0 13 2"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const state = {page:'overview',status:null,aiSettings:null,aiSettingsError:'',aiBusy:false,aiTests:{},aiModels:{},notes:[],cards:[],due:[],history:[],note:null,editing:false,search:'',category:'全部',chatBusy:false,chatQuestion:'',chatSource:null,review:null,flipped:false,reviewed:0,modal:null,generated:null,error:null,loadToken:0};
const titles = {overview:'学习概览',library:'知识库',chat:'AI 导师',cards:'复习卡片',settings:'学习设置'};
const categoryNames = {note:'知识笔记',template:'学习模板',mistake:'错题整理',inbox:'收集箱',plan:'学习计划',card:'复习卡片',review:'复习卡片',profile:'学习档案'};
const categoryLabel = category => categoryNames[category] || category || '知识笔记';
const classificationTypes=['note','mistake','plan','card','inbox','profile'];
const classificationSubjects=['数学','物理','化学','生物','计算机','英语','医学','经济管理','人文社科','综合'];
const classificationFolders={note:'01_知识笔记',mistake:'02_错题本',plan:'03_学习计划',card:'04_复习卡片',inbox:'00_收集箱',profile:'05_学习档案'};
const classificationLabel=n=>`${n.subject?`${n.subject} · `:''}${categoryLabel(n.category)}`;
const classificationFolder=c=>`${classificationFolders[c.category]||classificationFolders.note}/${c.category==='profile'?'':`${c.subject||'综合'}/`}`;
state.subject='全部';
let searchTimer = null, searchToken = 0, discardResolve = null;
function noteBody(content) { return String(content||'').replace(/^\uFEFF?---\s*\r?\n[\s\S]*?\r?\n---\s*(?:\r?\n|$)/,'').replace(/^\s*#\s+[^\n]*(?:\n|$)/,'').trim(); }
function hasUnsavedEdit() { return state.editing && $('#note-editor') && $('#note-editor').value !== state.note?.content; }
async function canLeaveEditor() {
  if(state.noteSaving){toast('正在分类并保存笔记，请稍候。');return false;}
  if(!hasUnsavedEdit())return true;
  return new Promise(resolve=>{discardResolve=resolve;showModal('这篇笔记还没有保存',
    '<p class="preview-notice">离开后，刚才的修改将不会保留。你可以继续编辑并保存，或放弃这次修改。</p>',
    secondary('继续编辑','keep-edit','edit')+primary('放弃修改','discard-edit','close'));});
}

async function api(path, data) {
  const response = await fetch(path, {method:data === undefined ? 'GET':'POST', headers:data === undefined ? undefined : {'Content-Type':'application/json'}, body:data === undefined ? undefined : JSON.stringify(data)});
  let result;
  try { result = await response.json(); } catch { throw new Error('服务暂时没有响应，请检查本地服务是否运行。'); }
  if (!response.ok || result.error) throw new Error(result.error || `请求失败（${response.status}）`);
  return result;
}
function toast(message, error = false) {
  const item = document.createElement('div'); item.className = `toast${error?' toast-error':''}`;
  item.innerHTML = icon(error?'close':'check') + `<span>${esc(message)}</span>`;
  $('#toasts').append(item); setTimeout(() => item.remove(), 5000);
}
function shortDate(value) { if (!value) return '刚刚'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? '' : date.toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'}); }
function relativeDate(value) { if (!value) return ''; const delta = Date.now()-new Date(value).valueOf(); if (delta<86400000) return '今天更新'; if(delta<172800000) return '昨天更新'; return `${shortDate(value)} 更新`; }
function noteTitle(path) { return String(path || '').split(/[\\/]/).pop().replace(/\.md$/i,''); }
function safeTitle(value) { return String(value || '未命名笔记').replace(/[<>:"/\\|?*\x00-\x1f]/g,'-').trim().slice(0,90) || '未命名笔记'; }
function timestamp() { return new Date().toISOString().replace(/[T:.]/g,'-').slice(0,19); }
function tagsHtml(tags = []) { return (Array.isArray(tags)?tags:[]).slice(0,4).map(t => `<span class="tag">${esc(String(t).replace(/^#/,''))}</span>`).join(''); }
function emptyState(title, text, action = '') { return `<div class="empty-state"><div class="empty-icon">${icon('leaf')}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`; }
function pageHeading(kicker, title, description, actions = '') { return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${description}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`; }
function primary(text, action, ico='plus', attrs='') { return `<button class="button button-primary" data-action="${action}" ${attrs}>${icon(ico)}${text}</button>`; }
function secondary(text, action, ico='upload', attrs='') { return `<button class="button button-secondary" data-action="${action}" ${attrs}>${icon(ico)}${text}</button>`; }

// Escape all source text before applying a limited Markdown grammar. Never allow raw HTML.
function markdown(source) {
  const blocks = [];
  let text = String(source || '').replace(/\r\n/g,'\n');
  text = text.replace(/```([^\n]*)\n([\s\S]*?)```/g, (_,lang,code) => `\n\u0000BLOCK${blocks.push(`<pre><span class="code-language">${esc(lang.trim())}</span><code>${esc(code.replace(/\n$/,''))}</code></pre>`)-1}\u0000\n`);
  text = text.replace(/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]/g, formula => `\n\u0000BLOCK${blocks.push(`<div class="math-block">${esc(formula)}</div>`)-1}\u0000\n`);
  const inline = input => {
    const tokens = [];
    const hold = html => `\u0001${tokens.push(html)-1}\u0001`;
    let result = String(input).replace(/`([^`]+)`/g, (_,code)=>hold(`<code>${esc(code)}</code>`));
    result = result.replace(/\\\([\s\S]*?\\\)|\$(?!\$)[^$\n]+\$/g, formula => hold(`<span class="math-inline">${esc(formula)}</span>`));
    result = result.replace(/\[\[([^\]]+)\]\]/g, (_,target) => { const [path, label] = target.split('|'); return hold(`<button class="wiki-link" data-action="wiki" data-path="${esc(path.trim())}">${esc(label || path)}</button>`); });
    result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_,label,url)=>{
      if (/^https?:\/\//i.test(url)) return hold(`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`);
      if (/^mailto:/i.test(url)) return hold(`<a href="${esc(url)}">${esc(label)}</a>`);
      if (!/^[a-z][a-z0-9+.-]*:/i.test(url) && !url.startsWith('//')) return hold(`<button class="wiki-link" data-action="wiki" data-path="${esc(url.replace(/\.md$/i,''))}">${esc(label)}</button>`);
      return hold(esc(label));
    });
    result = esc(result).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/__([^_]+)__/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>').replace(/~~([^~]+)~~/g,'<del>$1</del>');
    return result.replace(/\u0001(\d+)\u0001/g, (_,n) => tokens[Number(n)]);
  };
  let result = '', list = '', quote = false, paragraph = [];
  const flush = () => { if(paragraph.length) { result += `<p>${paragraph.map(inline).join('<br>')}</p>`; paragraph=[]; } };
  const closeList = () => { if(list) { result += `</${list}>`; list=''; } };
  const closeQuote = () => { if(quote) {result+='</blockquote>';quote=false;} };
  for (const line of text.split('\n')) {
    const block = line.match(/^\u0000BLOCK(\d+)\u0000$/);
    if(block) { flush();closeList();closeQuote();result+=blocks[Number(block[1])];continue; }
    if (!line.trim()) { flush();closeList();closeQuote();continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if(heading) { flush();closeList();closeQuote(); const level=Math.min(heading[1].length+1,6);result+=`<h${level}>${inline(heading[2])}</h${level}>`;continue; }
    if(/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { flush();closeList();closeQuote();result+='<hr>';continue; }
    const li = line.match(/^\s*(?:[-*+]\s+|\d+[.)]\s+)(.*)$/);
    if(li) { flush();closeQuote();const type=/^\s*\d/.test(line)?'ol':'ul';if(list!==type){closeList();result+=`<${type}>`;list=type;}result+=`<li>${inline(li[1]).replace(/^\[x\]\s*/i,'☑ ').replace(/^\[ \]\s*/,'☐ ')}</li>`;continue; }
    const q=line.match(/^>\s?(.*)$/);if(q){flush();closeList();if(!quote){result+='<blockquote>';quote=true;}result+=`<p>${inline(q[1])}</p>`;continue;}
    closeList();closeQuote();paragraph.push(line);
  }
  flush();closeList();closeQuote();return result;
}

async function refreshStatus() {
  state.status = await api('/api/status');
  const s=state.status;syncAIConnectionBadge();
  $('#nav-note-count').textContent=s.counts?.notes||'';
  $('#nav-due-count').textContent=s.counts?.due||'';
}
async function navigate() {
  if(!await canLeaveEditor()){history.replaceState(null,'',`#${state.page}`);return;}
  const page=location.hash.slice(1).split('?')[0] || 'overview';
  state.page=titles[page]?page:'overview';state.error=null;state.note=null;state.editing=false;
  const token=++state.loadToken;
  $('#page-name').textContent=titles[state.page];
  $$('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===state.page);if(el.dataset.nav===state.page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  document.title=`${titles[state.page]} · 拾知`;
  render();
  try {
    const work=[refreshStatus()];
    if(state.page==='library')work.push(api(`/api/notes?q=${encodeURIComponent(state.search)}`).then(r=>state.notes=r.notes||[]));
    if(state.page==='cards')work.push(api('/api/cards').then(r=>{state.cards=r.cards||[];state.due=r.due||[];}));
    if(state.page==='chat'&&!state.chatBusy)work.push(api('/api/history').then(r=>state.history=r.messages||[]));
    if(state.page==='settings')work.push(refreshAISettings());
    await Promise.all(work);if(token===state.loadToken)render();
  }catch(err){if(token===state.loadToken){state.error=err.message;render();}}
}
function render() {
  const main=$('#main');
  main.className=`page page-${state.page}`;
  if(state.error){main.innerHTML=`<div class="error-banner">${icon('close')}<span>${esc(state.error)}</span><button data-action="reload">重试</button></div>`;return;}
  main.innerHTML=({overview:renderOverview,library:renderLibrary,chat:renderChat,cards:renderCards,settings:renderSettings}[state.page])();
  if(state.page==='chat')requestAnimationFrame(()=>{const stream=$('#chat-stream');if(stream)stream.scrollTop=stream.scrollHeight;});
  renderMath();
}
function renderMath() {
  if(typeof window.renderMathInElement==='function') $$('.markdown-body').forEach(el=>{try{window.renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'$',right:'$',display:false},{left:'\\(',right:'\\)',display:false}],throwOnError:false,trust:false,output:'htmlAndMathml'});}catch{}});
}
function renderOverview() {
  const s=state.status||{},c=s.counts||{},recent=s.recent_notes||[],due=c.due||0;
  const hour=new Date().getHours(),greeting=hour<11?'上午好':hour<14?'中午好':hour<18?'下午好':'晚上好';
  return pageHeading('MAKE ROOM FOR WHAT YOU LEARN',`${greeting}，开始一点新的积累。`,'把零散的知识拾起来，让每一次学习都有回响。',secondary('导入资料','import')+primary('新建笔记','new-note'))+
    `<section class="welcome-card"><div class="welcome-copy"><div class="pill"><span class="tiny-dot"></span>今天，也向前一点</div><h2>学过的知识，<br>值得被<span>好好记住。</span></h2><p>${due?`你有 <strong>${due}</strong> 张卡片等待复习。从一次主动回忆开始，<br>让知识留得更久一点。`:'从一篇笔记、一个问题开始。<br>把今天的理解，留给未来的自己。'}</p><button class="button button-dark" data-action="${due?'start-review':'go-chat'}">${due?'开始今日复习':'和 AI 导师聊聊'}${icon('arrow')}</button><span class="hero-footnote">${due?'小步复习，积累长期记忆':'基于你的笔记，陪你梳理思路'}</span></div><div class="hero-art" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="art-star">✦</div><div class="art-dot"></div><div class="floating-note note-back"><span></span><span></span><span></span><i>思考</i></div><div class="floating-note note-front"><div class="drawn-leaf">${icon('leaf')}</div><span></span><span></span><small>每一天，都有所收获。</small></div><div class="art-caption">COLLECT. CONNECT. GROW.</div></div></section>
    <section class="stat-grid" aria-label="学习统计"><div class="stat-card"><div class="stat-icon sage">${icon('book')}</div><div><span>知识笔记</span><strong>${c.notes??'—'}<small>篇</small></strong></div><span class="stat-caption">属于你的知识积累</span></div><div class="stat-card"><div class="stat-icon peach">${icon('cards')}</div><div><span>待复习卡片</span><strong>${c.due??'—'}<small>张</small></strong></div><span class="stat-caption">${due?'趁记忆还温热，再想一遍':'把知识变成长期记忆'}</span></div><div class="stat-card"><div class="stat-icon lavender">${icon('spark')}</div><div><span>复习卡片总数</span><strong>${c.cards??'—'}<small>张</small></strong></div><span class="stat-caption">每一张，都是一个掌握点</span></div></section>
    <div class="overview-columns"><section class="panel recent-panel"><div class="section-heading"><div><span class="eyebrow">YOUR KNOWLEDGE</span><h2>最近的积累</h2></div><a class="text-link" href="#library">全部笔记${icon('arrow')}</a></div>${recent.length?`<div class="recent-list">${recent.slice(0,5).map((n,i)=>`<button class="recent-row" data-action="open-note" data-path="${esc(n.path)}"><span class="document-badge tone-${i%3}">${icon('file')}</span><span class="recent-info"><strong>${esc(n.title||noteTitle(n.path))}</strong><span>${esc(classificationLabel(n))}<i>·</i>${esc(relativeDate(n.modified))}</span></span>${icon('chevron')}</button>`).join('')}</div>`:emptyState('给知识一个落脚的地方','导入已有资料，或写下今天的第一个想法。',secondary('写第一篇笔记','new-note','plus'))}</section><section class="panel quick-panel"><div class="section-heading"><div><span class="eyebrow">A SMALL NEXT STEP</span><h2>下一步，轻松一点</h2></div><span class="little-flower">✳</span></div><button class="quick-action" data-action="go-chat">${icon('spark')}<span><strong>一个疑问，一起想明白</strong><small>让 AI 导师帮你串起知识点</small></span>${icon('arrowup')}</button><button class="quick-action" data-action="import">${icon('upload')}<span><strong>把散落的资料收进来</strong><small>笔记、文档，或一张手写照片</small></span>${icon('arrowup')}</button><button class="quick-action" data-action="new-card">${icon('cards')}<span><strong>为未来的自己留个问题</strong><small>用一张卡片检验真正的理解</small></span>${icon('arrowup')}</button><div class="thought-note"><span>学习小记</span><p>试着合上笔记，<br>用自己的话，再讲一遍。</p><div class="thought-line"></div></div></section></div>`;
}
function renderLibrary() {
  if(state.note)return renderNote();
  const categories=['全部',...new Set(state.notes.map(n=>n.category).filter(Boolean))];
  const subjects=['全部',...new Set(state.notes.map(n=>n.subject||'未分类'))];
  const notes=state.notes.filter(n=>(state.category==='全部'||n.category===state.category)&&(state.subject==='全部'||(n.subject||'未分类')===state.subject));
  return pageHeading('A PLACE FOR YOUR IDEAS','让知识，慢慢相连。','你的 Obsidian 笔记，就是这座知识库。',secondary('导入资料','import')+primary('新建笔记','new-note'))+
    `<div class="library-toolbar"><label class="search-field">${icon('search')}<input id="note-search" type="search" placeholder="搜索笔记、关键词或标签…" value="${esc(state.search)}" aria-label="搜索笔记"><kbd>/</kbd></label><span class="muted">共 ${state.notes.length} 篇笔记</span></div><div class="filter-row">${categories.map(c=>`<button class="filter-chip ${c===state.category?'selected':''}" data-action="filter" data-category="${esc(c)}">${esc(c==='全部'?c:categoryLabel(c))}</button>`).join('')}</div><div class="filter-row subject-filters" aria-label="按学科筛选"><span class="small-muted">学科</span>${subjects.map(c=>`<button class="filter-chip ${c===state.subject?'selected':''}" data-action="filter-subject" data-subject="${esc(c)}">${esc(c)}</button>`).join('')}</div><div id="note-results">${notes.length?`<div class="note-grid">${notes.map((n,i)=>`<button class="note-card" data-action="open-note" data-path="${esc(n.path)}"><div class="note-card-top"><span class="document-badge tone-${i%3}">${icon('file')}</span><span>${esc(classificationLabel(n))}</span>${icon('arrowup')}</div><h3>${esc(n.title||noteTitle(n.path))}</h3><p>${esc(n.preview||'打开这篇笔记，继续你的思考。')}</p><div class="note-card-bottom"><div class="tags">${tagsHtml(n.tags)}</div><span>${esc(shortDate(n.modified))}</span></div></button>`).join('')}</div>`:emptyState(state.search||state.notes.length?'还没有找到这篇笔记':'知识库，从一篇笔记开始',state.search||state.notes.length?'换个关键词，或者试试其他分类。':'写下你的理解，或把已有学习资料带进来。',state.search||state.notes.length?'':primary('新建笔记','new-note'))}</div>`;
}
function renderNote() {
  const n=state.note;
  return `<div class="note-topline"><button class="text-link" data-action="back-library">${icon('back')}返回知识库</button><div class="heading-actions">${state.editing?secondary('取消','cancel-edit','close')+primary('保存笔记','save-note','check'):secondary('编辑笔记','edit-note','edit')}</div></div><div class="note-reader-layout"><article class="panel note-reader"><div class="eyebrow">${esc(classificationLabel(n))}</div><h1>${esc(n.title||noteTitle(n.path))}</h1><div class="note-metadata"><span>${icon('clock')}${esc(relativeDate(n.modified))}</span><div class="tags">${tagsHtml(n.tags)}</div></div>${state.editing?`<label class="sr-only" for="note-editor">Markdown 笔记内容</label><textarea id="note-editor" class="note-editor" spellcheck="false">${esc(n.content)}</textarea><div class="editor-hint">支持 Markdown · Ctrl / ⌘ + Enter 保存</div><label class="classification-toggle"><input type="checkbox" id="editor-auto-classify" ${n.category==='template'?'':'checked'}><span>保存时自动分类<small>识别学科、类型与标签，保留笔记原路径。</small></span></label>`:`<div class="markdown-body">${markdown(noteBody(n.content))}</div>`}</article><aside class="note-context"><section class="panel context-panel"><span class="eyebrow">THINK A LITTLE DEEPER</span><h3>让这篇笔记更有用</h3><button class="context-action" data-action="classify-note" ${state.editing?'disabled':''}>${icon('spark')}自动分类${icon('arrow')}</button><button class="context-action" data-action="ask-note">${icon('spark')}和导师讨论${icon('arrow')}</button><button class="context-action" data-action="generate" data-kind="summary">${icon('file')}提炼知识摘要${icon('arrow')}</button><button class="context-action" data-action="generate" data-kind="cards">${icon('cards')}生成复习卡片${icon('arrow')}</button><button class="context-action" data-action="generate" data-kind="organize">${icon('book')}整理知识结构${icon('arrow')}</button><button class="context-action" data-action="generate" data-kind="plan">${icon('clock')}制定学习计划${icon('arrow')}</button></section><section class="panel context-panel"><div class="section-heading"><h3>知识之间的连接</h3>${icon('link')}</div><div class="link-label">这篇笔记提到</div>${(n.links||[]).length?n.links.map(link=>`<button class="backlink" data-action="wiki" data-path="${esc(link)}">${icon('file')}${esc(link)}</button>`).join(''):'<p class="small-muted">还没有双向链接。用 [[笔记名]] 建立关联。</p>'}<div class="link-label">提到这篇笔记</div>${(n.backlinks||[]).length?n.backlinks.map(link=>`<button class="backlink" data-action="open-note" data-path="${esc(link.path)}">${icon('file')}${esc(link.title||noteTitle(link.path))}</button>`).join(''):'<p class="small-muted">新的连接，会在这里出现。</p>'}</section><div class="file-location">${icon('folder')}<span>${esc(n.path)}</span></div></aside></div>`;
}
function renderChat() {
  const messages=state.history;
  return pageHeading('MAKE SENSE, TOGETHER','把问题，聊明白。','AI 导师会参考你的知识库，陪你解释、追问与联想。')+
    `<div class="chat-layout"><section class="panel chat-panel"><div class="chat-panel-header"><div class="mentor-avatar">${icon('spark')}</div><div><strong>拾知导师</strong><span>${state.chatBusy?'正在梳理你的问题…':'从你的知识出发，一起想深一点'}</span></div><span class="local-badge">基于知识库</span></div><div class="chat-stream" id="chat-stream">${messages.length?messages.map(renderMessage).join(''):`<div class="chat-welcome"><div class="mentor-orbit">${icon('spark')}</div><h2>每一个好问题，<br>都是理解的开始。</h2><p>哪里还没想通？把问题留在这里。<br>我们可以从你的笔记中找线索。</p><div class="suggestion-grid"><button data-action="suggest" data-question="请结合我的知识库，梳理最近学习内容的核心概念和它们的联系。">${icon('link')}帮我串起知识点${icon('arrowup')}</button><button data-action="suggest" data-question="根据我的笔记，请通过提问检验我对核心概念的理解，每次只问一个问题。">${icon('cards')}用提问检验我的理解${icon('arrowup')}</button><button data-action="suggest" data-question="请结合我的知识库，用通俗的例子解释一个值得深入理解的概念。">${icon('leaf')}换个角度理解概念${icon('arrowup')}</button><button data-action="suggest" data-question="根据我的知识库，给我一个具体、可执行的下一步学习建议。">${icon('clock')}找到下一步学习方向${icon('arrowup')}</button></div></div>`}${state.chatBusy?`<div class="message assistant"><span class="message-avatar">${icon('spark')}</span><div class="message-content"><div class="thinking"><span></span><span></span><span></span><small>正在阅读相关笔记，认真想一想</small></div></div></div>`:''}</div><form id="chat-form" class="chat-composer">${state.chatSource?`<div class="chat-selected-source">${icon('file')}<span>本次参考：${esc(state.chatSource.title||noteTitle(state.chatSource.path))}</span><button type="button" data-action="clear-chat-source" aria-label="取消指定笔记">${icon('close')}</button></div>`:''}<label class="sr-only" for="chat-input">你的问题</label><textarea id="chat-input" rows="2" placeholder="写下你的疑问，或者试着解释一个概念…" ${state.chatBusy?'disabled':''}>${esc(state.chatQuestion)}</textarea><div class="composer-bottom"><span>${icon('link')}相关笔记会作为参考发送给当前 AI 服务</span><button type="submit" class="send-button" aria-label="发送问题" ${state.chatBusy?'disabled':''}>${icon('send')}</button></div></form><div class="chat-footnote">Enter 发送 · Shift + Enter 换行 · AI 的回答也值得核对与思考</div></section><aside class="chat-side"><div class="panel context-panel"><span class="eyebrow">A BETTER QUESTION</span><h3>让提问更有收获</h3><div class="question-tip"><span>01</span><p><strong>带上你的理解</strong>“我认为是这样，但不确定…”</p></div><div class="question-tip"><span>02</span><p><strong>问清背后的原因</strong>“为什么这一步必须这样做？”</p></div><div class="question-tip"><span>03</span><p><strong>换一个具体例子</strong>“能用生活中的场景解释吗？”</p></div></div><div class="chat-side-note">理解不是记住答案，<br>是学会提出下一个问题。<span>✳</span></div></aside></div>`;
}
function renderMessage(m) {
  const uniqueSources=[...new Map((m.sources||[]).map(s=>[s.path,s])).values()];
  const user=m.role==='user';return `<div class="message ${user?'user':'assistant'}"><span class="message-avatar">${user?'我':icon('spark')}</span><div class="message-content"><span class="message-label">${user?'你':'拾知导师'}</span><div class="markdown-body">${markdown(m.content||m.answer)}</div>${!user&&m.sources?.length?`<div class="message-sources"><span>${icon('link')}参考笔记</span>${uniqueSources.map((s,i)=>`<button data-action="open-note" data-path="${esc(s.path)}" title="${esc(s.excerpt||'')}">${i+1}. ${esc(s.title||noteTitle(s.path))}${icon('arrowup')}</button>`).join('')}</div>`:''}</div></div>`;
}
function renderCards() {
  if(state.review)return renderReview();
  return pageHeading('REMEMBER WHAT MATTERS','回想一次，记得更久。','用主动回忆，把“好像懂了”变成真正掌握。',primary('新建卡片','new-card'))+
    `<div class="review-banner"><div><div class="eyebrow">YOUR NEXT RECALL</div><h2>${state.due.length?`今天，和 ${state.due.length} 个知识点重逢。`:'今天的复习，已经从容就绪。'}</h2><p>${state.due.length?'先回想，再翻面。根据真实掌握程度，安排下一次见面。':'到期的卡片会出现在这里。也可以随时新增想要记住的知识。'}</p></div><button class="button button-dark" data-action="start-review" ${state.due.length?'':'disabled'}>${icon('cards')}开始复习${state.due.length?`<span class="button-count">${state.due.length}</span>`:''}</button></div><div class="section-heading cards-list-heading"><h2>我的卡片<span class="heading-count">${state.cards.length}</span></h2><span class="muted">按计划，温故而知新</span></div>${state.cards.length?`<div class="card-list">${state.cards.map(c=>`<article class="panel study-card"><div class="study-card-info"><span class="card-topic">${esc(c.topic||'知识回顾')}</span><span class="due-label ${state.due.some(d=>d.id===c.id)?'is-due':''}">${state.due.some(d=>d.id===c.id)?'等待复习':`下次 ${esc(shortDate(c.due))}`}</span></div><h3>${esc(c.question)}</h3><details><summary>查看答案 ${icon('chevron')}</summary><div class="markdown-body">${markdown(c.answer)}</div></details>${c.source?`<button class="card-source" data-action="wiki" data-path="${esc(c.source)}">${icon('link')}${esc(noteTitle(c.source))}</button>`:''}</article>`).join('')}</div>`:emptyState('把值得记住的，变成一个问题','手动创建一张卡片，或在笔记里让 AI 帮你提炼。',secondary('去知识库挑一篇笔记','go-library','book'))}`;
}
function renderReview() {
  const c=state.review;
  return `<div class="note-topline"><button class="text-link" data-action="end-review">${icon('back')}返回卡片</button><span class="muted">本轮已复习 ${state.reviewed} 张 · 剩余 ${state.due.length} 张</span></div><div class="review-space"><div class="eyebrow">TAKE A MOMENT TO RECALL</div><h1>先想一想，再看答案。</h1><article class="flip-card"><span class="card-topic">${esc(c.topic||'知识回顾')}</span><span class="flip-label">问题 / QUESTION</span><div class="markdown-body card-question">${markdown(c.question)}</div>${state.flipped?`<div class="card-answer"><span class="flip-label">答案 / ANSWER</span><div class="markdown-body">${markdown(c.answer)}</div></div>`:`<div class="recall-hint">在心里组织好你的答案，或者试着说出来。</div><button class="button button-primary" data-action="flip-card">${icon('refresh')}翻开答案</button>`}</article>${state.flipped?`<div class="rating-prompt">这次回忆，感觉如何？</div><div class="rating-row"><button data-action="rate-card" data-rating="again"><span>还没记住</span><small>需要再学一遍</small></button><button data-action="rate-card" data-rating="hard"><span>有点困难</span><small>想了很久才记起</small></button><button data-action="rate-card" data-rating="good"><span>掌握得不错</span><small>顺利想起了答案</small></button><button data-action="rate-card" data-rating="easy"><span>轻松记住</span><small>已经很熟悉了</small></button></div>`:''}</div>`;
}
function renderSettings() {
  const s=state.status||{},c=s.codex||{},a=aiConnection(),settings=state.aiSettings,mode=settings?.mode||a.mode,active=settings?.profiles.find(p=>p.id===settings.active_profile_id),ready=c.available&&c.authenticated,busy=state.aiBusy?'disabled':'';
  const test=mode==='api'&&active?state.aiTests[active.id]:null;
  const statusText=mode==='api'?(active?(test?.status==='success'?'已通过连接测试':test?.status==='error'?'最近一次连接测试失败':'API 已配置，尚未验证连接'):'请添加并启用一个 API 供应商'):(ready?'Codex 已连接，可以开始学习':c.available?'Codex 已安装，等待登录':'尚未检测到 Codex');
  return pageHeading('YOUR SPACE, YOUR WAY','让学习空间，适合你。','管理 AI 供应商、API Key 和模型，随时切换适合自己的连接。')+`<div class="settings-grid">
    <section class="panel settings-panel"><div class="settings-title"><span class="stat-icon sage">${icon('folder')}</span><div><h2>我的知识库</h2><p>与你的 Obsidian 仓库保持连接</p></div></div><label class="field-label">当前仓库位置</label><div class="path-field">${icon('folder')}<code>${esc(s.vault_path||'正在读取…')}</code></div><div class="settings-description">你可以在 Obsidian 中继续编辑这些笔记。这里会读取最新的 Markdown 文件，双向链接也会保留。</div><div class="settings-meta"><span>${s.counts?.notes??0} 篇笔记</span><span>${s.counts?.cards??0} 张复习卡片</span></div><button class="button button-secondary" data-action="reload">${icon('refresh')}刷新知识库</button></section>
    <section class="panel settings-panel"><div class="settings-title"><span class="stat-icon peach">${icon('spark')}</span><div><h2>AI 连接</h2><p>选择账户登录或自己的 API Key</p></div></div><div class="ai-mode-switch" role="group" aria-label="AI 连接方式"><button data-action="ai-mode" data-mode="codex" aria-pressed="${mode==='codex'}" ${busy}>Codex 登录</button><button data-action="ai-mode" data-mode="api" aria-pressed="${mode==='api'}" ${busy||(!active?'disabled':'')}>API Key</button></div><div class="connection-status ${mode==='api'?test?.status==='success'?'ready':'':ready?'ready':''}"><span class="status-dot ${mode==='api'?test?.status==='success'?'connected':'':ready?'connected':''}"></span><strong>${statusText}</strong></div>
    ${mode==='api'?`<dl class="settings-details"><div><dt>当前供应商</dt><dd>${esc(active?.name||'未选择')}</dd></div><div><dt>当前模型</dt><dd>${esc(active?.model||'未选择')}</dd></div></dl><p class="small-muted">${esc(test?.detail||'保存配置后，点击「测试连接」验证密钥、地址和模型。配置完成不代表服务已验证。')}</p>`:`<p class="small-muted ai-detail">${esc(c.detail||'')}</p><dl class="settings-details"><div><dt>安装状态</dt><dd>${c.available?'已安装':'未检测到'}</dd></div><div><dt>登录状态</dt><dd>${c.authenticated?'已登录':'待登录'}</dd></div>${c.version?`<div><dt>版本</dt><dd>${esc(c.version)}</dd></div>`:''}</dl>${!ready?`<div class="setup-hint"><strong>${c.available?'在终端登录 Codex':'先安装并登录 Codex CLI'}</strong>${!c.available?'<code>npm install -g @openai/codex</code>':''}<code>codex login</code><p>按终端提示完成登录，然后刷新连接状态。</p></div>`:''}`}
    <button class="button button-secondary ai-refresh-button" data-action="ai-refresh" ${busy}>${icon('refresh')}刷新连接状态</button>${!active?'<p class="small-muted ai-detail">添加供应商并点击「启用」后，即可使用 API Key。</p>':''}</section>
    <section class="panel settings-panel ai-providers-panel"><div class="ai-section-heading"><div class="settings-title"><span class="stat-icon lavender">${icon('settings')}</span><div><h2>API 供应商 <span class="ai-profile-count">${settings?.profiles.length||0}</span></h2><p>保存多套连接，选择模型，一键启用</p></div></div>${primary('添加供应商','ai-add','plus',busy||(!settings?'disabled':''))}</div><p class="small-muted ai-provider-intro">支持 OpenAI 兼容接口、OpenAI Responses 和 Anthropic Messages。文字与图片能力取决于所选服务和模型。</p>
    ${state.aiSettingsError?`<div class="error-banner"><span>${esc(state.aiSettingsError)}</span><button data-action="ai-refresh" ${busy}>重试读取配置</button></div>`:!settings?'<div class="ai-loading"><span class="spinner"></span>正在读取 AI 配置…</div>':settings.profiles.length?`<div class="ai-profile-grid">${settings.profiles.map(renderAIProfile).join('')}</div>`:`<div class="ai-provider-empty">${icon('link')}<div><h3>连接你自己的 AI 服务</h3><p>填写 API 地址、密钥和模型。保存后选择「启用」，后续学习请求就会使用该连接。</p></div>${secondary('添加第一套 API 配置','ai-add','plus',busy)}</div>`}
    <p class="small-muted ai-test-notice">「测试连接」会向该供应商发送一条简短请求，消耗少量 API 额度；测试结果仅记录在本次页面会话中。</p><div class="ai-operation-status" role="status" aria-live="polite">${state.aiBusy?`<span class="spinner"></span>${state.aiBusy.startsWith('test:')?'正在验证 API 连接，请稍候…':'正在更新 AI 连接…'}`:''}</div></section>
    <section class="panel settings-panel privacy-panel"><span class="stat-icon lavender">${icon('book')}</span><div><h2>关于你的资料</h2><p>笔记、卡片和学习记录保存在本地。向 AI 提问时，问题和相关笔记片段会发送给当前启用的 AI 服务；识别图片或根据资料写笔记时，所选图片和文件内容也会发送给该服务。Codex 模式使用账户额度，API 模式使用供应商的 API 额度。</p><p class="small-muted">API Key 由本地服务保存，管理界面只显示是否已设置。生成内容会先展示草稿，由你决定是否保存。</p></div></section></div>`;
}

const aiProtocols={'openai-chat':'OpenAI 兼容 · Chat Completions','openai-responses':'OpenAI · Responses','anthropic':'Anthropic · Messages'};
const aiTemplates={custom:{name:'',protocol:'openai-chat',base_url:'',model:''},openai:{name:'OpenAI',protocol:'openai-responses',base_url:'https://api.openai.com/v1',model:''},anthropic:{name:'Anthropic',protocol:'anthropic',base_url:'https://api.anthropic.com/v1',model:''},deepseek:{name:'DeepSeek',protocol:'openai-chat',base_url:'https://api.deepseek.com/v1',model:''}};
function aiConnection(){const s=state.status||{};return s.ai||{mode:'codex',available:s.codex?.available,authenticated:s.codex?.authenticated,provider:'Codex',model:'',detail:s.codex?.detail};}
function syncAIConnectionBadge(){
  const a=aiConnection(),configured=a.available&&a.authenticated,tested=a.mode==='api'&&state.aiTests[state.aiSettings?.active_profile_id]?.status==='success';
  $('#connection-dot').classList.toggle('connected',!!(a.mode==='api'?tested:configured));
  $('#connection-label').textContent=configured?(a.mode==='api'?`${a.provider||'API'} · ${tested?'测试通过':'已配置'}`:'AI · Codex 已连接'):'本地知识库 · 已就绪';
}
async function refreshAISettings(){
  try{
    const result=await api('/api/ai/settings');
    // Only public metadata belongs in UI state. Keys stay in the password field until submitted.
    state.aiSettings={mode:result.mode,active_profile_id:result.active_profile_id,profiles:(result.profiles||[]).map(p=>({id:p.id,name:p.name,protocol:p.protocol,base_url:p.base_url,model:p.model,has_api_key:!!p.has_api_key}))};state.aiSettingsError='';return true;
  }catch(err){state.aiSettingsError=err.message;return false;}
}
function renderAIProfile(p){
  const selected=p.id===state.aiSettings.active_profile_id,active=selected&&state.aiSettings.mode==='api',test=state.aiTests[p.id],busy=state.aiBusy?'disabled':'';
  return `<article class="ai-profile-card ${active?'is-active':''}"><div class="ai-profile-heading"><span class="ai-provider-icon">${icon('spark')}</span><div><h3>${esc(p.name)}</h3><span>${esc(aiProtocols[p.protocol]||p.protocol)}</span></div>${active?'<span class="ai-profile-badge">正在使用</span>':selected?'<span class="ai-profile-badge ai-profile-saved">API 默认</span>':''}</div><dl class="ai-profile-details"><div><dt>模型</dt><dd>${esc(p.model)}</dd></div><div><dt>地址</dt><dd>${esc(p.base_url)}</dd></div><div><dt>API Key</dt><dd>${p.has_api_key?'已设置 · 密钥已隐藏':'未设置'}</dd></div></dl><div class="ai-profile-test ${test?.status==='error'?'is-error':''}" role="status">${test?`${icon(test.status==='success'?'check':test.status==='error'?'close':'clock')}<span>${esc(test.status==='testing'?'正在测试…':test.status==='success'?`测试通过：${test.detail}`:`测试失败：${test.detail}`)}</span>`:'<span>已保存配置 · 尚未测试</span>'}</div><div class="ai-profile-actions">${primary(active?'已启用':'启用','ai-select',active?'check':'arrow',`data-id="${esc(p.id)}" ${busy|| (active?'disabled':'')}`)}${secondary('测试连接','ai-test','link',`data-id="${esc(p.id)}" ${busy}`)}<button class="button button-secondary" data-action="ai-edit" data-id="${esc(p.id)}" ${busy}>${icon('edit')}编辑 / 模型</button><button class="ai-delete-button" data-action="ai-delete" data-id="${esc(p.id)}" ${busy} aria-label="删除供应商 ${esc(p.name)}">删除</button></div></article>`;
}
async function reloadAIConnection(){await Promise.all([refreshAISettings(),refreshStatus()]);if(state.page==='settings')render();}
async function updateAIConnection(data,message){
  if(state.aiBusy)return;state.aiBusy=data.action;if(state.page==='settings')render();
  try{await api('/api/ai/settings',data);await reloadAIConnection();toast(message);}
  finally{state.aiBusy=false;if(state.page==='settings')render();}
}
function showAIProfile(id=''){
  if(state.aiBusy)return;const p=state.aiSettings?.profiles.find(item=>item.id===id);if(id&&!p)return;
  const profile=p||{id:'',name:'',protocol:'openai-chat',base_url:'',model:'',has_api_key:false};
  state.modal={type:'ai-profile',profile:{...profile},busy:false,loadingModels:false};
  showModal(p?'编辑 API 供应商':'添加 API 供应商',`<form id="ai-profile-form" autocomplete="off"><p class="ai-form-intro">配置 API 服务和模型，保存后可在供应商列表中启用。</p><label class="field-label" for="ai-template">快速填写</label><select class="input" id="ai-template"><option value="custom">自定义 OpenAI 兼容服务</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="deepseek">DeepSeek</option></select><div class="form-row"><div><label class="field-label" for="ai-name">供应商名称</label><input class="input" id="ai-name" name="name" required maxlength="80" placeholder="例如：我的 API 服务" value="${esc(profile.name)}"></div><div><label class="field-label" for="ai-protocol">接口协议</label><select class="input" id="ai-protocol" name="protocol">${Object.entries(aiProtocols).map(([value,label])=>`<option value="${value}" ${profile.protocol===value?'selected':''}>${esc(label)}</option>`).join('')}</select></div></div><label class="field-label" for="ai-base-url">API Base URL</label><input class="input mono-input" id="ai-base-url" name="base_url" type="url" required maxlength="2000" placeholder="https://api.example.com/v1" value="${esc(profile.base_url)}" autocomplete="off" spellcheck="false"><p class="ai-field-help">填写接口根地址，可包含 /v1；程序会根据协议追加请求路径。</p><label class="field-label" for="ai-model">模型</label><div class="ai-model-field"><input class="input mono-input" id="ai-model" name="model" required maxlength="200" placeholder="选择已读取的模型，或手动输入模型 ID" value="${esc(profile.model)}" list="ai-model-options" autocomplete="off" spellcheck="false"><button type="button" class="button button-secondary" data-action="ai-load-models" ${profile.id?'':'disabled'}>${icon('refresh')}读取模型</button></div><datalist id="ai-model-options">${(state.aiModels[profile.id]||[]).map(m=>`<option value="${esc(m.id)}">${esc(m.name||m.id)}</option>`).join('')}</datalist><div id="ai-model-status" class="ai-field-help" role="status" aria-live="polite">${profile.id?'使用当前填写的 API 地址和密钥读取模型列表；不支持列表的服务可手动填写模型 ID。':'填写 API 地址和密钥后，即可读取可用模型；也可直接填写模型 ID。'}</div><label class="field-label" for="ai-api-key">API Key <span>${profile.has_api_key?'已设置，留空保留现有密钥':'必填'}</span></label><input class="input mono-input" id="ai-api-key" name="api_key" type="password" ${profile.has_api_key?'':'required'} placeholder="${profile.has_api_key?'留空保留现有密钥，填写可替换':'填写供应商提供的 API Key'}" autocomplete="new-password" spellcheck="false"><p class="ai-field-help">密钥由本地服务保存，浏览器不会回填已保存的密钥。图片识别需要所选模型支持图片输入。</p><div id="ai-form-status" class="ai-form-status" role="status" aria-live="polite"></div><div id="ai-close-confirm" class="ai-close-confirm" hidden><p>配置尚未保存。继续编辑，或放弃这次修改？</p><div>${secondary('继续编辑','ai-keep-profile','edit')}${secondary('放弃修改','ai-discard-profile','close')}</div></div></form>`,secondary('取消','close-modal','close')+`<button type="submit" form="ai-profile-form" class="button button-primary">${icon('check')}保存配置</button>`,true);
  $('#ai-template').value='custom';
  $$('#ai-close-confirm button').forEach(button=>button.type='button');
  $('#ai-model-options').insertAdjacentHTML('afterend','<label class="field-label" id="ai-model-choice-label" for="ai-model-choice" hidden>从模型列表选择</label><select id="ai-model-choice" class="input ai-model-choice" hidden></select>');
  populateAIModelChoices(state.aiModels[profile.id]||[]);
  updateAIModelLoadButton();
}
function populateAIModelChoices(models){
  const options=$('#ai-model-options'),choices=$('#ai-model-choice');if(!options||!choices)return;
  options.innerHTML=models.map(m=>`<option value="${esc(m.id)}">${esc(m.name||m.id)}</option>`).join('');
  choices.innerHTML='<option value="">选择一个模型，或继续手动输入</option>'+models.map(m=>`<option value="${esc(m.id)}">${esc(m.name&&m.name!==m.id?`${m.name} · ${m.id}`:m.id)}</option>`).join('');
  choices.value=models.some(m=>m.id===$('#ai-model').value)?$('#ai-model').value:'';
  choices.hidden=!models.length;$('#ai-model-choice-label').hidden=!models.length;
}
function aiProfileDirty(){
  if(state.modal?.type!=='ai-profile'||!$('#ai-profile-form'))return false;const original=state.modal.profile;
  return ['name','protocol','base_url','model'].some(name=>$('#ai-profile-form').elements.namedItem(name).value!==String(original[name]||''))||!!$('#ai-api-key').value;
}
function setAIFormBusy(busy){
  $$('input,select,button',$('#modal')).forEach(el=>el.disabled=busy);
  if(!busy)updateAIModelLoadButton();
}
function updateAIModelLoadButton(){
  const modal=state.modal,button=$('[data-action="ai-load-models"]');if(modal?.type!=='ai-profile'||!button)return;
  button.disabled=modal.busy||modal.loadingModels||!$('#ai-base-url').value.trim()||(!$('#ai-api-key').value.trim()&&!modal.profile.has_api_key);
}
async function saveAIProfile(){
  const modal=state.modal,form=$('#ai-profile-form');if(modal?.type!=='ai-profile'||modal.busy||!form?.reportValidity())return;
  if(modal.loadingModels){$('#ai-form-status').textContent='模型列表正在读取，完成后即可保存。';return;}
  const payload={action:'save',id:modal.profile.id,name:$('#ai-name').value.trim(),protocol:$('#ai-protocol').value,base_url:$('#ai-base-url').value.trim(),model:$('#ai-model').value.trim()};
  if($('#ai-api-key').value.trim())payload.api_key=$('#ai-api-key').value.trim();
  if(!payload.name||!payload.model){$('#ai-form-status').textContent='请填写供应商名称和模型 ID。';return;}
  modal.busy=true;setAIFormBusy(true);$('#ai-form-status').textContent='正在保存配置…';
  try{await api('/api/ai/settings',payload);delete state.aiTests[modal.profile.id];delete state.aiModels[modal.profile.id];closeModal(true);await reloadAIConnection();toast('API 配置已保存。点击「启用」选择该连接。');}
  catch(err){if(state.modal===modal){$('#ai-form-status').textContent=err.message;$('#ai-form-status').classList.add('is-error');}else toast(err.message,true);}
  finally{payload.api_key='';modal.busy=false;if(state.modal===modal)setAIFormBusy(false);}
}
async function loadAIModels(button){
  const modal=state.modal;if(modal?.type!=='ai-profile'||modal.loadingModels||modal.busy)return;
  const status=$('#ai-model-status'),urlInput=$('#ai-base-url'),keyInput=$('#ai-api-key');
  if(!urlInput.reportValidity()||(!modal.profile.has_api_key&&!keyInput.reportValidity()))return;
  const payload={protocol:$('#ai-protocol').value,base_url:urlInput.value.trim()};if(modal.profile.id)payload.id=modal.profile.id;if(keyInput.value.trim())payload.api_key=keyInput.value.trim();
  if(!payload.api_key&&!modal.profile.has_api_key){status.textContent='请填写 API Key 后读取模型。';return;}
  try{if(!['http:','https:'].includes(new URL(payload.base_url).protocol))throw new Error();}catch{status.textContent='请填写完整的 HTTP 或 HTTPS API 地址。';payload.api_key='';return;}
  const usesSaved=payload.id&&payload.protocol===modal.profile.protocol&&payload.base_url===modal.profile.base_url&&!payload.api_key;
  modal.loadingModels=true;button.disabled=true;status.textContent='正在使用当前填写的连接读取模型列表…';
  try{const job=await api('/api/ai/models',payload),result=await pollJob(job.job_id),models=[...new Map((result.models||[]).filter(m=>m&&typeof m.id==='string'&&m.id.trim()).map(m=>[m.id,{id:m.id,name:typeof m.name==='string'?m.name:m.id}])).values()];if(usesSaved)state.aiModels[modal.profile.id]=models;
    if(state.modal===modal){
      const changed=$('#ai-base-url').value.trim()!==payload.base_url||$('#ai-protocol').value!==payload.protocol||$('#ai-api-key').value.trim()!==(payload.api_key||'');
      if(changed){populateAIModelChoices([]);status.textContent='连接配置在读取期间发生了修改，请重新读取模型列表。';}
      else{populateAIModelChoices(models);status.textContent=models.length?`已读取 ${models.length} 个模型。可从下拉列表选择，也可以手动输入其他模型 ID。`:'服务没有返回可用模型；请手动填写供应商支持的模型 ID。';(models.length?$('#ai-model-choice'):$('#ai-model')).focus();}
    }
  }catch(err){if(state.modal===modal)status.textContent=`未能读取模型：${err.message} 仍可手动填写模型 ID。`;else toast(`未能读取模型：${err.message}`,true);}
  finally{payload.api_key='';modal.loadingModels=false;if(state.modal===modal)updateAIModelLoadButton();}
}
async function testAIProfile(id){
  if(state.aiBusy)return;state.aiBusy=`test:${id}`;state.aiTests[id]={status:'testing',detail:''};if(state.page==='settings')render();
  try{const job=await api('/api/ai/test',{id}),result=await pollJob(job.job_id);if(result.ok===false)throw new Error(result.detail||'服务没有通过连接测试。');state.aiTests[id]={status:'success',detail:result.detail||`${result.provider||'API'} / ${result.model||'所选模型'} 已响应`};toast('API 连接测试通过。');}
  catch(err){state.aiTests[id]={status:'error',detail:err.message};toast(err.message,true);}
  finally{state.aiBusy=false;syncAIConnectionBadge();if(state.page==='settings')render();}
}
function showDeleteAIProfile(id){
  if(state.aiBusy)return;const p=state.aiSettings?.profiles.find(item=>item.id===id);if(!p)return;
  const selected=id===state.aiSettings.active_profile_id;
  state.modal={type:'ai-delete',id,busy:false};showModal('删除 API 供应商',`<p class="preview-notice">将删除「${esc(p.name)}」及其 API Key。${selected?'这是当前选中的 API 配置，删除后会切回 Codex 登录模式。':'之后可以重新添加该供应商。'}</p><div id="ai-delete-status" class="ai-form-status" role="status"></div>`,secondary('保留配置','close-modal','close')+primary('删除供应商','ai-delete-confirm','close'));
}
async function deleteAIProfile(){
  const modal=state.modal;if(modal?.type!=='ai-delete'||modal.busy)return;modal.busy=true;$$('button',$('#modal')).forEach(b=>b.disabled=true);
  try{await api('/api/ai/settings',{action:'delete',id:modal.id});delete state.aiTests[modal.id];delete state.aiModels[modal.id];closeModal(true);await reloadAIConnection();toast('API 供应商已删除。');}
  catch(err){if(state.modal===modal){$('#ai-delete-status').textContent=err.message;$$('button',$('#modal')).forEach(b=>b.disabled=false);}else toast(err.message,true);}
  finally{modal.busy=false;}
}

async function openNote(path) {
  if(!await canLeaveEditor())return;
  try{const note=await api(`/api/note?path=${encodeURIComponent(path)}`);if(state.page!=='library'){state.page='library';history.replaceState(null,'','#library');$('#page-name').textContent=titles.library;$$('[data-nav]').forEach(el=>el.classList.toggle('active',el.dataset.nav==='library'));}document.title=`${note.title||noteTitle(note.path)} · 拾知`;state.note=note;state.editing=false;render();window.scrollTo({top:0,behavior:'smooth'});}catch(err){toast(err.message,true);}
}
async function resolveWiki(path) {
  const normalized=decodeURIComponent(String(path).split('#')[0]).replace(/\\/g,'/').replace(/\.md$/i,'');
  try{const r=await api('/api/notes');state.notes=r.notes||[];const note=state.notes.find(n=>n.path.replace(/\.md$/i,'')===normalized)||state.notes.find(n=>noteTitle(n.path)===noteTitle(normalized)||n.title===normalized);if(note)await openNote(note.path);else toast(`知识库中还没有「${normalized}」这篇笔记。`,true);}catch(err){toast(err.message,true);}
}
function showModal(title, body, footer='', wide=false) {
  const modal=$('#modal');modal.hidden=false;modal.innerHTML=`<section class="modal-dialog ${wide?'modal-wide':''}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-header"><div><span class="eyebrow">STUDY SPACE</span><h2 id="modal-title">${esc(title)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="关闭">${icon('close')}</button></div><div class="modal-body">${body}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}</section>`;document.body.classList.add('modal-open');requestAnimationFrame(()=>{$('input:not([type=hidden]),textarea,button',modal)?.focus();});
}
function closeModal(force=false){
  if(!force&&['ai-profile','ai-delete'].includes(state.modal?.type)&&state.modal.busy){toast('正在保存 AI 配置，请稍候。');return false;}
  if(!force&&aiProfileDirty()){const confirm=$('#ai-close-confirm');confirm.hidden=false;$('[data-action="ai-keep-profile"]',confirm)?.focus();return false;}
  const key=$('#ai-api-key');if(key)key.value='';
  captureNoteDraft();if(discardResolve){const resolve=discardResolve;discardResolve=null;resolve(false);} $('#modal').hidden=true;$('#modal').innerHTML='';document.body.classList.remove('modal-open');state.modal=null;return true;
}
function showNewNote(content='', title='', filename='') {
  if(arguments.length||!state.noteDraft)state.noteDraft={content,title,path:filename||'01_知识笔记/',instructions:'',files:[],busy:false,message:'',error:'',warnings:[],autoClassify:true,pathManual:false,classification:null,classifiedContent:null,classifiedTitle:null,manualClassification:false};
  state.modal={type:'new-note',draft:state.noteDraft};renderNoteDraft();
}
function captureNoteDraft() {
  const draft=state.modal?.type==='new-note'&&state.modal.draft;
  if(!draft||!$('#new-content'))return;
  for(const [key,id] of [['title','new-title'],['content','new-content'],['path','new-path'],['instructions','draft-instructions']])draft[key]=$(`#${id}`).value;
  if($('#draft-auto-classify'))draft.autoClassify=$('#draft-auto-classify').checked;
  if(draft.classification&&$('#draft-classification-category')){
    const c=readClassificationFields('draft-classification',draft.classification);
    if(JSON.stringify([c.category,c.subject,c.tags])!==JSON.stringify([draft.classification.category,draft.classification.subject,draft.classification.tags])){
      draft.classification=c;draft.manualClassification=true;draft.classifiedContent=draft.content;draft.classifiedTitle=draft.title;
      if(draft.autoClassify&&!draft.pathManual){draft.path=c.folder;$('#new-path').value=draft.path;}
    }
  }
}
function formatFileSize(size){return size<1048576?`${Math.max(1,Math.round(size/1024))} KB`:`${(size/1048576).toFixed(1)} MB`;}
function classificationFields(c,prefix,disabled=false) {
  const attrs=disabled?'disabled':'';
  return `<div class="classification-fields"><div><label class="field-label" for="${prefix}-category">笔记类型</label><select class="input" id="${prefix}-category" ${attrs}>${classificationTypes.map(k=>`<option value="${k}" ${k===c.category?'selected':''}>${categoryLabel(k)}</option>`).join('')}</select></div><div><label class="field-label" for="${prefix}-subject">学科</label><select class="input" id="${prefix}-subject" ${attrs}>${classificationSubjects.map(k=>`<option ${k===c.subject?'selected':''}>${k}</option>`).join('')}</select></div></div><label class="field-label" for="${prefix}-tags">标签 <span>最多 5 个，用逗号分隔</span></label><input class="input" id="${prefix}-tags" value="${esc((c.tags||[]).join('，'))}" ${attrs}><p class="classification-reason">${esc(c.reason||'可以调整识别结果，再保存分类。')}</p>`;
}
function readClassificationFields(prefix,base) {
  if(!$(`#${prefix}-category`))return base;
  const c={category:$(`#${prefix}-category`).value,subject:$(`#${prefix}-subject`).value,tags:$(`#${prefix}-tags`).value.split(/[,，]/).map(t=>t.trim().replace(/^#+/,'')).filter(Boolean).slice(0,5),reason:base?.reason||''};
  c.folder=classificationFolder(c);return c;
}
function draftClassificationHtml(d) {
  const current=d.classification&&(d.manualClassification||(d.classifiedContent===d.content&&d.classifiedTitle===d.title));
  return `<section class="draft-classification"><div class="classification-heading"><label class="classification-toggle"><input type="checkbox" id="draft-auto-classify" ${d.autoClassify?'checked':''} ${d.busy?'disabled':''}><span>保存时自动分类<small>自动识别学科、笔记类型和标签，建议保存目录。</small></span></label>${secondary('识别笔记分类','draft-classify','spark',d.busy||!d.content.trim()?'disabled':'')}</div>${d.classification?`${!current?'<p class="small-muted">正文或标题已变化，保存时会重新识别分类。</p>':''}${classificationFields(d.classification,'draft-classification',d.busy||!d.autoClassify)}`:'<p class="small-muted">生成笔记时会同时分类；手写笔记可在保存时自动识别。</p>'}</section>`;
}
function applyDraftClassification(d,c) {
  d.classification=c;d.classifiedContent=d.content;d.classifiedTitle=d.title;d.manualClassification=false;
  if(d.autoClassify&&!d.pathManual)d.path=classificationFolder(c);
}
async function fetchClassification(content,title='',path='') {
  const job=await api('/api/classify-note',{content,title,path});const result=await pollJob(job.job_id);
  if(!result.classification)throw new Error('暂未识别到有效分类，请稍后重试。');return result;
}
async function classifyDraft() {
  const d=state.modal?.type==='new-note'&&state.modal.draft;if(!d||d.busy)return;captureNoteDraft();
  if(!d.content.trim())return toast('先生成笔记，或填写笔记正文，再识别分类。',true);
  d.busy=true;d.busyLabel='正在识别学科、笔记类型和标签…';d.error='';renderNoteDraft();
  try{const result=await fetchClassification(d.content,d.title);applyDraftClassification(d,result.classification);d.warnings=[...new Set([...d.warnings,...(result.warnings||[])])];d.message='分类已识别。你可以调整类型、学科和标签，保存时会写入笔记。';}
  catch(err){d.error=err.message;}
  finally{d.busy=false;if(state.modal?.draft===d)renderNoteDraft();else toast(d.error||'笔记分类已识别，点击「新建笔记」查看。',!!d.error);}
}
async function classifyExistingNote() {
  if(!state.note||state.editing)return;
  const note={...state.note};
  if(state.classificationPreview?.note.path===note.path&&state.classificationPreview.note.mtime===note.mtime){showExistingClassification();return;}
  const modal={type:'classify-existing'};state.modal=modal;
  showModal('正在为笔记分类',`<div class="generation-loading"><span class="spinner"></span><h3>识别这篇笔记的归属</h3><p>正在阅读《${esc(note.title)}》，识别学科、笔记类型和标签。<br>分类结果可调整；保存分类会保留原路径。</p></div>`,secondary('暂时关闭','close-modal','close'));
  try{const result=await fetchClassification(note.content,note.title,note.path);state.classificationPreview={note,classification:result.classification,warnings:result.warnings||[]};if(state.modal===modal)showExistingClassification();else toast('笔记分类已识别。打开这篇笔记并点击「自动分类」查看。');}
  catch(err){if(state.modal===modal)closeModal();toast(err.message,true);}
}
function showExistingClassification() {
  const p=state.classificationPreview;if(!p)return;state.modal={type:'classification-preview'};
  showModal('笔记自动分类',`<p class="preview-notice">《${esc(p.note.title)}》的分类结果。可以修改后保存，笔记正文和双向链接会保留。</p>${classificationFields(p.classification,'existing-classification')}${p.warnings.length?`<p class="preview-warning">${p.warnings.map(esc).join('<br>')}</p>`:''}<label class="field-label">当前保存位置</label><p class="classification-path">${esc(p.note.path)}</p><p class="small-muted">已有笔记只更新分类信息，保持原路径。</p>`,secondary('暂时关闭','close-modal','close')+primary('保存分类','save-classification','check'),true);
}
async function saveExistingClassification(button) {
  const p=state.classificationPreview;if(!p)return;const classification=readClassificationFields('existing-classification',p.classification);button.disabled=true;
  try{const note=await api('/api/note',{path:p.note.path,content:p.note.content,mtime:p.note.mtime,classification});closeModal();state.classificationPreview=null;if(state.note?.path===note.path){state.note=note;render();}await refreshStatus();toast(`分类已保存：${classificationLabel(note)}。`);}
  catch(err){button.disabled=false;toast(err.message,true);}
}
function renderNoteDraft() {
  const d=state.modal?.draft;if(!d)return;const disabled=d.busy?'disabled':'';
  showModal('新建学习笔记',`<p class="draft-intro">带上课堂照片、讲义或已有资料，让 AI 帮你整理成自己的笔记。</p><section class="draft-materials" aria-label="学习资料"><input type="file" id="draft-files" accept=".md,.txt,.pdf,.png,.jpg,.jpeg,.webp" multiple hidden><button class="draft-upload" data-action="draft-upload" ${disabled}>${icon('upload')}<span><strong>上传学习资料</strong><small>图片、PDF、Markdown 或 TXT · 最多 6 份，共 12 MB</small></span>${icon('plus')}</button><div class="draft-file-list">${d.files.map((f,i)=>`<div class="draft-file">${icon('file')}<span><strong>${esc(f.name)}</strong><small>${formatFileSize(f.size)}</small></span><button class="icon-button" data-action="draft-remove" data-index="${i}" aria-label="移除 ${esc(f.name)}" ${disabled}>${icon('close')}</button></div>`).join('')}</div><label class="field-label" for="draft-instructions">整理要求 <span>选填</span></label><textarea id="draft-instructions" class="input draft-instructions" rows="2" placeholder="例如：整理核心概念、公式和例题，标出易错点，最后给我 3 个自测问题。" ${disabled}>${esc(d.instructions)}</textarea><div class="draft-generate-row">${primary(d.busy?'正在整理资料…':'根据资料生成笔记','draft-generate','spark',disabled||(!d.files.length&&!d.content.trim()?'disabled':''))}<span>生成时，所选资料会发送给当前 AI 服务。</span></div><div class="draft-status ${d.error?'draft-error':''}" role="status" aria-live="polite">${d.busy?`<span class="spinner"></span>${esc(d.busyLabel||'正在阅读资料并写笔记，请稍候。')}`:esc(d.error||d.message)}</div>${d.warnings.length?`<p class="preview-warning">${d.warnings.map(esc).join('<br>')}</p>`:''}</section><label class="field-label" for="new-title">笔记标题</label><input class="input" id="new-title" placeholder="可先填写，也可以让 AI 拟一个标题" value="${esc(d.title)}" ${disabled}><label class="field-label" for="new-content">笔记内容 <span>AI 草稿可直接编辑 · 支持 Markdown</span></label><textarea class="input draft-textarea" id="new-content" placeholder="上传资料生成笔记，也可以在这里直接写下你的理解…" ${disabled}>${esc(d.content)}</textarea>${draftClassificationHtml(d)}<label class="field-label" for="new-path">保存位置</label><input class="input mono-input" id="new-path" value="${esc(d.path)}" placeholder="01_知识笔记/笔记标题.md" ${disabled}><p class="small-muted">核对识别内容、公式和答案后保存。笔记会写入你的 Obsidian 知识库。</p>`,secondary('暂时关闭','close-modal','close')+primary('保存到知识库','create-note','check',disabled),true);
}
function addDraftFiles(files) {
  const d=state.modal?.type==='new-note'&&state.modal.draft;if(!d||d.busy)return;captureNoteDraft();
  for(const file of files){
    if(!/\.(png|jpe?g|webp|pdf|md|txt)$/i.test(file.name)){toast(`「${file.name}」暂不支持，请选择图片、PDF、MD 或 TXT。`,true);continue;}
    if(d.files.some(f=>f.name===file.name&&f.size===file.size&&f.lastModified===file.lastModified))continue;
    if(d.files.length>=6){toast('一次最多上传 6 份资料。',true);break;}
    if(!file.size){toast(`「${file.name}」是空文件，请选择有内容的资料。`,true);continue;}
    if(/\.(md|txt)$/i.test(file.name)&&file.size>2*1024*1024){toast('每份文字资料不能超过 2 MB。',true);continue;}
    if(d.files.reduce((sum,f)=>sum+f.size,0)+file.size>12*1024*1024){toast('资料总大小不能超过 12 MB，请分批整理。',true);continue;}
    d.files.push(file);
  }
  d.error='';renderNoteDraft();
}
function readDraftFile(file) {
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({filename:file.name,data:String(reader.result).split(',')[1]});reader.onerror=()=>reject(new Error(`无法读取「${file.name}」，请重新选择。`));reader.readAsDataURL(file);});
}
async function generateNoteDraft() {
  const d=state.modal?.type==='new-note'&&state.modal.draft;if(!d||d.busy)return;captureNoteDraft();
  if(!d.files.length&&!d.content.trim())return toast('先上传学习资料，或填写要整理的内容。',true);
  d.busy=true;d.busyLabel='正在阅读资料并写笔记，请稍候。';d.error='';d.message='';d.warnings=[];renderNoteDraft();
  try{
    const files=await Promise.all(d.files.map(readDraftFile));
    const job=await api('/api/draft-note',{files,instructions:d.instructions,title:d.title,draft:d.content});
    const result=await pollJob(job.job_id);
    if(!String(result.text||'').trim())throw new Error('这次没有生成笔记，请保留资料后重试。');
    d.content=result.text;
    if(!d.title.trim())d.title=result.title||String(result.text).match(/^#\s+(.+)$/m)?.[1]?.trim()||d.files[0]?.name.replace(/\.[^.]+$/,'')||'学习笔记';
    d.warnings=result.warnings||(result.warning?[result.warning]:[]);
    if(result.classification)applyDraftClassification(d,result.classification);
    d.message='笔记草稿已生成。你可以修改内容，核对后保存到知识库。';
  }catch(err){d.error=err.message;}
  finally{
    d.busy=false;
    if(state.modal?.type==='new-note'&&state.modal.draft===d)renderNoteDraft();
    else toast(d.error||'笔记草稿已生成，点击「新建笔记」继续编辑。',!!d.error);
  }
}
function showNewCard() {
  state.modal={type:'new-card'};
  showModal('给未来的自己留个问题',`<label class="field-label" for="card-question">问题</label><textarea class="input" rows="3" id="card-question" placeholder="一个清晰、具体的问题，最适合回忆练习。"></textarea><label class="field-label" for="card-answer">答案</label><textarea class="input" rows="5" id="card-answer" placeholder="用自己的话，写下你理解的答案。"></textarea><div class="form-row"><div><label class="field-label" for="card-topic">主题 <span>选填</span></label><input class="input" id="card-topic" placeholder="例如：线性代数"></div><div><label class="field-label" for="card-source">来源笔记 <span>选填</span></label><input class="input" id="card-source" placeholder="笔记路径或名称" value="${esc(state.note?.path||'')}"></div></div>`,secondary('取消','close-modal','close')+primary('创建卡片','create-card','check'));
}
async function createNote(button) {
  captureNoteDraft();const d=state.modal?.draft;if(!d||d.busy)return;
  const title=d.title.trim(),content=d.content;
  if(!title||!content.trim())return toast('请填写笔记标题和内容。',true);
  d.busy=true;d.busyLabel=d.autoClassify?'正在分类并保存笔记…':'正在保存笔记…';d.error='';renderNoteDraft();
  try{
    let classification;
    if(d.autoClassify){
      if(!d.classification||(!d.manualClassification&&(d.classifiedContent!==content||d.classifiedTitle!==d.title))){const result=await fetchClassification(content,title);applyDraftClassification(d,result.classification);d.warnings=[...new Set([...d.warnings,...(result.warnings||[])])];}
      classification=d.classification;
    }
    let path=d.path.trim()||'01_知识笔记/';if(path.endsWith('/'))path+=`${safeTitle(title)}.md`;if(!/\.md$/i.test(path))path+='.md';
    const note=await api('/api/note',{path,content:/^#\s/m.test(content)?content:`# ${title}\n\n${content}`,classification});
    if(state.modal?.draft===d)closeModal();if(state.noteDraft===d)state.noteDraft=null;toast(`笔记已保存${classification?`：${classificationLabel(classification)}`:'，新的积累留下了'}。`);await refreshStatus();await openNote(note.path||path);
  }catch(err){d.error=err.message;toast(err.message,true);}
  finally{d.busy=false;if(state.modal?.draft===d)renderNoteDraft();}
}
async function saveNote(button) {
  if(state.noteSaving)return;const editor=$('#note-editor');if(!editor)return;const content=editor.value,note={...state.note},auto=$('#editor-auto-classify')?.checked;
  state.noteSaving=true;button.disabled=true;editor.disabled=true;const toggle=$('#editor-auto-classify');if(toggle)toggle.disabled=true;
  try{const result=auto?await fetchClassification(content,note.title,note.path):null;state.note=await api('/api/note',{path:note.path,content,mtime:note.mtime,classification:result?.classification});state.editing=false;toast('笔记已保存。');render();refreshStatus().catch(()=>{});}
  catch(err){toast(err.message,true);button.disabled=false;editor.disabled=false;if(toggle)toggle.disabled=false;}
  finally{state.noteSaving=false;}
}
async function createCard(button) {
  const question=$('#card-question').value.trim(),answer=$('#card-answer').value.trim();if(!question||!answer)return toast('问题和答案都需要填写。',true);button.disabled=true;
  try{await api('/api/cards',{question,answer,topic:$('#card-topic').value.trim(),source:$('#card-source').value.trim()});closeModal();toast('新卡片已加入复习计划。');await refreshStatus();if(state.page==='cards'){const r=await api('/api/cards');state.cards=r.cards;state.due=r.due;render();}}catch(err){toast(err.message,true);button.disabled=false;}
}
async function pollJob(id) {
  for(;;){const job=await api(`/api/jobs?id=${encodeURIComponent(id)}`);if(job.status==='completed')return job.result;if(job.status==='failed')throw new Error(job.error||'这次 AI 请求没有完成，请稍后再试。');await new Promise(resolve=>setTimeout(resolve,1500));}
}
async function sendChat(question) {
  question=question.trim();if(!question||state.chatBusy)return;
  state.chatBusy=true;state.chatQuestion='';const prior=state.history.slice(-12).map(m=>({role:m.role,content:m.content}));state.history.push({role:'user',content:question});render();
  try{const job=await api('/api/chat',{question,history:prior,path:state.chatSource?.path||''});const result=await pollJob(job.job_id);state.history.push({role:'assistant',content:result.answer||result.text||'',sources:result.sources||[]});}
  catch(err){toast(err.message,true);state.history.push({role:'assistant',content:`这次没有完成回答：${err.message}\n\n你可以在学习设置中检查当前 AI 连接，然后重新发送问题。`});}
  finally{state.chatBusy=false;if(state.page==='chat')render();}
}
async function generate(kind) {
  const names={summary:'知识摘要',cards:'复习卡片',plan:'学习计划',organize:'知识结构'},path=state.note?.path;
  state.modal={type:'generation',busy:true};showModal(`正在整理${names[kind]}`,`<div class="generation-loading"><span class="spinner"></span><h3>给理解一点时间</h3><p>正在阅读这篇笔记，提炼值得保留的内容。<br>生成结果会先展示给你确认。</p></div>`,secondary('在后台继续','close-modal','close'));
  try{const job=await api('/api/generate',{kind,path});const result=await pollJob(job.job_id);state.generated={...result,kind,source:path,savedCards:new Set()};showGenerated();}
  catch(err){closeModal();toast(err.message,true);}
}
function showGenerated() {
  const g=state.generated;if(!g)return;const names={summary:'知识摘要',cards:'复习卡片',plan:'学习计划',organize:'知识结构'};
  const cards=Array.isArray(g.cards)?g.cards:[];
  const body=`${g.warning?`<p class="preview-warning">${esc(g.warning)}</p>`:''}<p class="preview-notice">这是 AI 生成的草稿。检查内容后，再把有用的部分留下来。</p>${cards.length?`<div class="generated-cards">${cards.map((c,i)=>`<article class="generated-card"><span class="card-topic">${esc(c.topic||'知识回顾')}</span><h3>${esc(c.question)}</h3><div class="markdown-body">${markdown(c.answer)}</div><button class="button button-secondary button-small" data-action="save-generated-card" data-index="${i}" ${g.savedCards.has(i)?'disabled':''}>${icon(g.savedCards.has(i)?'check':'plus')}${g.savedCards.has(i)?'已加入复习':'加入复习'}</button></article>`).join('')}</div>`:`<div class="markdown-body generated-text">${markdown(g.text||'暂未生成内容。')}</div>`}`;
  showModal(`${names[g.kind]} · 预览`,body,secondary('暂时关闭','close-modal','close')+(cards.length?primary('全部加入复习','save-all-cards','cards'):primary('保存到知识库','save-generated','check')),true);renderMath();
}
async function saveGeneratedCard(index,button) {
  const g=state.generated,c=g.cards[index];if(g.savedCards.has(index))return;if(button)button.disabled=true;
  try{await api('/api/cards',{question:c.question,answer:c.answer,topic:c.topic||'',source:c.source||g.source||''});g.savedCards.add(index);if(button){button.innerHTML=icon('check')+'已加入复习';}await refreshStatus();}
  catch(err){if(button)button.disabled=false;throw err;}
}
async function saveGenerated(button) {
  const g=state.generated,names={summary:'知识摘要',cards:'复习卡片',plan:'学习计划',organize:'知识结构'};button.disabled=true;
  button.innerHTML=icon('spark')+'正在分类并保存…';
  try{const title=`${names[g.kind]}-${safeTitle(noteTitle(g.source)||'学习记录')}-${timestamp()}`;const result=await fetchClassification(g.text||'',title);const note=await api('/api/note',{path:`${classificationFolder(result.classification)}${title}.md`,content:g.text||'',classification:result.classification});closeModal();toast(`已保存到知识库：${classificationLabel(note)}。`);await refreshStatus();await openNote(note.path);}catch(err){toast(err.message,true);button.disabled=false;button.innerHTML=icon('check')+'保存到知识库';}
}
async function startReview() {
  try{const r=await api('/api/cards');state.cards=r.cards||[];state.due=r.due||[];if(!state.due.length){toast('目前没有到期卡片，稍后再来看看。');return;}state.review=state.due[0];state.reviewed=0;state.flipped=false;if(state.page!=='cards'){location.hash='cards';}else render();}catch(err){toast(err.message,true);}
}
async function rateCard(rating,button) {
  $$('.rating-row button').forEach(b=>b.disabled=true);
  try{await api('/api/review',{id:state.review.id,rating});state.reviewed++;state.due=state.due.filter(c=>c.id!==state.review.id);state.flipped=false;state.review=state.due[0]||null;if(!state.review){const count=state.reviewed;const r=await api('/api/cards');state.cards=r.cards||[];state.due=r.due||[];toast(`这一轮完成了 ${count} 张卡片。给认真回想的自己一点肯定。`);}await refreshStatus();render();}catch(err){toast(err.message,true);$$('.rating-row button').forEach(b=>b.disabled=false);}
}
async function importFile(file) {
  if(!file)return;const ext=file.name.split('.').pop().toLowerCase();
  if(!['md','txt','pdf','png','jpg','jpeg','webp'].includes(ext))return toast('支持 Markdown、TXT、PDF 和 PNG / JPG / WebP 图片。',true);
  if(['md','txt'].includes(ext)&&file.size>2*1024*1024)return toast('文本文件不能超过 2 MB，请按章节分开导入。',true);
  if(file.size>12*1024*1024)return toast('文件过大，请选择 12 MB 以内的文件。',true);
  if(['md','txt'].includes(ext)){
    try{const content=await file.text();showNewNote(content,file.name.replace(/\.[^.]+$/,''),'00_收集箱/');}catch(err){toast(err.message,true);}return;
  }
  const isImage=ext!=='pdf';
  if(isImage){state.modal={type:'image-import',file};showModal('把照片里的知识留下来',`<div class="import-explanation"><span class="large-icon">${icon('file')}</span><h3>${esc(file.name)}</h3><p>识别时，这张图片会发送给当前 AI 服务。<br>识别结果可以编辑，确认后再保存为笔记。</p></div>`,secondary('取消','close-modal','close')+primary('识别图片文字','transcribe','spark'));return;}
  await extractFile(file,false);
}
async function extractFile(file,isImage) {
  showModal(isImage?'正在识别图片':'正在读取 PDF',`<div class="generation-loading"><span class="spinner"></span><h3>${isImage?'把画面转成可以整理的文字':'正在提取文档中的文字'}</h3><p>完成后可以检查、编辑，再保存为笔记。</p></div>`);
  try{const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('无法读取文件，请重新选择。'));reader.readAsDataURL(file);});let result;if(isImage){const job=await api('/api/transcribe',{filename:file.name,data});result=await pollJob(job.job_id);}else{result=await api('/api/import-pdf',{filename:file.name,data});}showNewNote(result.text||'',file.name.replace(/\.[^.]+$/,''),'00_收集箱/');if(result.warnings?.length)toast(result.warnings.join('；'));}
  catch(err){closeModal();toast(err.message,true);}
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;const action=button.dataset.action;
  try{
    switch(action){
      case 'reload':await navigate();toast('学习空间已更新。');break;
      case 'ai-refresh':if(!state.aiBusy){await reloadAIConnection();if(!state.aiSettingsError)toast('AI 连接状态已更新。');}break;
      case 'ai-mode':await updateAIConnection({action:'mode',mode:button.dataset.mode},button.dataset.mode==='api'?'已切换到 API Key 连接。':'已切换到 Codex 登录。');break;
      case 'ai-select':await updateAIConnection({action:'select',id:button.dataset.id},'该 API 供应商已启用。');break;
      case 'ai-add':showAIProfile();break;
      case 'ai-edit':showAIProfile(button.dataset.id);break;
      case 'ai-test':await testAIProfile(button.dataset.id);break;
      case 'ai-load-models':await loadAIModels(button);break;
      case 'ai-delete':showDeleteAIProfile(button.dataset.id);break;
      case 'ai-delete-confirm':await deleteAIProfile();break;
      case 'ai-keep-profile':$('#ai-close-confirm').hidden=true;$('#ai-name')?.focus();break;
      case 'ai-discard-profile':closeModal(true);break;
      case 'go-chat':location.hash='chat';break;
      case 'go-library':location.hash='library';break;
      case 'global-search':location.hash='library';setTimeout(()=>$('#note-search')?.focus(),100);break;
      case 'new-note':showNewNote();break;
      case 'draft-upload':$('#draft-files')?.click();break;
      case 'draft-remove':{captureNoteDraft();const d=state.modal?.draft;if(d&&!d.busy){d.files.splice(Number(button.dataset.index),1);renderNoteDraft();}break;}
      case 'draft-generate':await generateNoteDraft();break;
      case 'draft-classify':await classifyDraft();break;
      case 'classify-note':await classifyExistingNote();break;
      case 'save-classification':await saveExistingClassification(button);break;
      case 'new-card':showNewCard();break;
      case 'close-modal':closeModal();break;
      case 'keep-edit':closeModal();break;
      case 'discard-edit':{const resolve=discardResolve;discardResolve=null;closeModal();resolve?.(true);break;}
      case 'create-note':await createNote(button);break;
      case 'create-card':await createCard(button);break;
      case 'open-note':await openNote(button.dataset.path);break;
      case 'wiki':await resolveWiki(button.dataset.path);break;
      case 'filter':state.category=button.dataset.category;render();break;
      case 'filter-subject':state.subject=button.dataset.subject;render();break;
      case 'back-library':if(!await canLeaveEditor())break;state.note=null;state.editing=false;await navigate();break;
      case 'edit-note':state.editing=true;render();$('#note-editor')?.focus();break;
      case 'cancel-edit':if(!await canLeaveEditor())break;state.editing=false;render();break;
      case 'save-note':await saveNote(button);break;
      case 'import':$('#import-file').click();break;
      case 'transcribe':{const file=state.modal.file;await extractFile(file,true);break;}
      case 'suggest':await sendChat(button.dataset.question);break;
      case 'clear-chat-source':state.chatSource=null;render();break;
      case 'ask-note':if(!await canLeaveEditor())break;state.editing=false;state.chatSource={path:state.note.path,title:state.note.title};state.chatQuestion=`请结合《${state.note.title||noteTitle(state.note.path)}》这篇笔记（${state.note.path}），帮我梳理核心概念，并指出值得进一步思考的问题。`;location.hash='chat';break;
      case 'generate':await generate(button.dataset.kind);break;
      case 'save-generated':await saveGenerated(button);break;
      case 'save-generated-card':await saveGeneratedCard(Number(button.dataset.index),button);toast('已加入复习计划。');break;
      case 'save-all-cards':button.disabled=true;for(let i=0;i<state.generated.cards.length;i++)await saveGeneratedCard(i);toast('生成的卡片已加入复习计划。');showGenerated();break;
      case 'start-review':await startReview();break;
      case 'end-review':state.review=null;render();break;
      case 'flip-card':state.flipped=true;render();break;
      case 'rate-card':await rateCard(button.dataset.rating,button);break;
    }
  }catch(err){toast(err.message,true);button.disabled=false;}
});
document.addEventListener('input',event=>{
  if(['new-title','new-content','new-path','draft-instructions'].includes(event.target.id)&&state.modal?.type==='new-note'){
    captureNoteDraft();const d=state.modal.draft;if(event.target.id==='new-path')d.pathManual=true;const button=$('[data-action="draft-generate"]');if(button)button.disabled=d.busy||(!d.files.length&&!d.content.trim());const classifyButton=$('[data-action="draft-classify"]');if(classifyButton)classifyButton.disabled=d.busy||!d.content.trim();
  }
  if(event.target.id==='note-search'){
    state.search=event.target.value;state.category='全部';state.subject='全部';clearTimeout(searchTimer);
    const token=++searchToken,query=state.search;
    searchTimer=setTimeout(async()=>{try{
      const result=await api(`/api/notes?q=${encodeURIComponent(query)}`);
      if(token!==searchToken||state.page!=='library'||state.note)return;
      const focused=document.activeElement?.id==='note-search',cursor=$('#note-search')?.selectionStart;
      state.notes=result.notes||[];render();
      if(focused){const input=$('#note-search');input?.focus();try{input?.setSelectionRange(cursor,cursor);}catch{}}
    }catch(err){toast(err.message,true);}},220);
  }
  if(event.target.id==='chat-input')state.chatQuestion=event.target.value;
  if(state.modal?.type==='ai-profile'&&['ai-base-url','ai-api-key'].includes(event.target.id))updateAIModelLoadButton();
});
document.addEventListener('submit',event=>{if(event.target.id==='chat-form'){event.preventDefault();sendChat($('#chat-input').value);}else if(event.target.id==='ai-profile-form'){event.preventDefault();saveAIProfile();}});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&!$('#modal').hidden){closeModal();return;}
  if(event.target.id==='chat-input'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();sendChat(event.target.value);}
  if(event.target.id==='note-editor'&&event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();saveNote($('[data-action="save-note"]'));}
  if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){event.preventDefault();location.hash='library';setTimeout(()=>$('#note-search')?.focus(),100);}
  if(event.key==='Tab'&&!$('#modal').hidden){const items=$$('button,a[href],input,textarea,select,[tabindex="0"]',$('#modal')).filter(el=>!el.disabled&&el.getClientRects().length),first=items[0],last=items[items.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
});
$('#modal').addEventListener('click',event=>{if(event.target===$('#modal'))closeModal();});
$('#modal').addEventListener('change',event=>{if(event.target.id==='draft-files'){const files=[...event.target.files];event.target.value='';addDraftFiles(files);}});
$('#modal').addEventListener('change',event=>{
  if(state.modal?.type!=='ai-profile'||state.modal.busy)return;
  if(event.target.id==='ai-template'){
    const template=aiTemplates[event.target.value];if(!template)return;
    for(const name of ['name','protocol','base_url'])$('#ai-profile-form').elements.namedItem(name).value=template[name];
    populateAIModelChoices([]);$('#ai-model-status').textContent='已填写接口模板。填写 API Key 后可读取模型，也可手动填写模型 ID。';updateAIModelLoadButton();
  }
  else if(event.target.id==='ai-model-choice'&&event.target.value)$('#ai-model').value=event.target.value;
});
$('#modal').addEventListener('change',event=>{
  if(state.modal?.type!=='new-note')return;
  if(event.target.id==='draft-auto-classify'){captureNoteDraft();const d=state.modal.draft;if(d.autoClassify&&d.classification&&!d.pathManual)d.path=classificationFolder(d.classification);renderNoteDraft();}
  else if(event.target.id.startsWith('draft-classification-'))captureNoteDraft();
});
$('#import-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';importFile(file);});
window.addEventListener('beforeunload',event=>{if(hasUnsavedEdit()||aiProfileDirty()){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',navigate);
$$('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
$('#today-date').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
navigate();
