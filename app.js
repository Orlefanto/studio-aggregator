// === ССЫЛКИ НА ОФИЦИАЛЬНЫЕ КАЛЕНДАРИ ===
// Если у студии один общий календарь на все залы (как у «Свободы») — заполняй "studio", а "halls" оставь пустым {}.
// Если у каждого зала свой отдельный календарь — заполняй "halls" по точному названию зала.
const CALENDAR_LINKS = {
  "Ламер": {
    studio: "https://calendar.google.com/calendar/u/0/embed?src=ekaterinakolpasikova65@gmail.com&ctz=UTC",
    halls: {
      "Ленина, 95А": "https://calendar.google.com/calendar/u/0/embed?src=ekaterinakolpasikova65@gmail.com&ctz=UTC"
    }
  },
  "ЯнаФОТО": {
    studio: "https://calendar.google.com/calendar/u/0/embed?src=yanafoto2025@gmail.com&ctz=Europe/Moscow",
    halls: {
      "АЛЕКСАНДР (ТЦ Европейский, 2 эт)": "https://calendar.google.com/calendar/u/0/embed?src=yanafoto2025@gmail.com&ctz=Europe/Moscow",
      "МЕТАЛЛ (ТЦ Европейский, 2 эт)": "https://calendar.google.com/calendar/u/0/embed?src=eurometall01.08.2024@gmail.com&ctz=Europe/Moscow",
      "ПЕРВЫЙ ЗАЛ (ул. Щорса)": "https://calendar.google.com/calendar/u/0/embed?src=h36qi6c1hb2rc270t912cen41g@group.calendar.google.com&ctz=Europe/Moscow"
    }
  },
  "Свобода": {
    studio: "https://appevent.ru/w/18285",
    halls: {}
  }
};

const D = window.DATA;
const MONTHS = ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
const WD = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];
const state = { view:"agg", hall:{}, month:{y:+D.today.slice(0,4), m:+D.today.slice(5,7)-1},
  mode:"busy", aggMode:"free", aggDate:D.today, aggMonth:{y:+D.today.slice(0,4), m:+D.today.slice(5,7)-1},
  minDur:60, modal:null, mmode:"busy", modalMinH:0 };

const fmt = m => String(Math.floor(m/60)%24).padStart(2,"0")+":"+String(m%60).padStart(2,"0");
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const iso = d => d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const plural = (n,a,b,c)=>{n=Math.abs(n)%100;const d=n%10;if(n>10&&n<20)return c;if(d>1&&d<5)return b;if(d===1)return a;return c;};
function dur(m){
  if(m<60) return m+" "+plural(m,"минута","минуты","минут");
  if(m%60===0){const h=m/60;return h+" "+plural(h,"час","часа","часов");}
  return String(Math.round(m/60*100)/100).replace(".",",")+" часа";
}
const studio = id => D.studios.find(s=>s.id===id);
const dayOf = (s,h,ds) => (s.halls[h]&&s.halls[h].days[ds])||null;
const evName = e => (e.t && !/^(busy|занято)$/i.test(String(e.t).trim())) ? e.t : "";
const busyLabel = e => (e.s===0&&e.e===1440) ? "весь день занято" : fmt(e.s)+" занято (на "+dur(e.e-e.s)+")";
const busyTip = e => fmt(e.s)+"-"+fmt(e.e)+(evName(e)?" · "+evName(e):"");
const hallTip = x => "Не удалось обновить: "+x.error+(x.updated?" (актуальные данные на "+x.updated+")":"");

function studioAggLink(s){
  const cfg = CALENDAR_LINKS[s.name] || {};
  const hasHallLinks = cfg.halls && Object.values(cfg.halls).some(Boolean);
  if(hasHallLinks) return "";
  return cfg.studio || s.url || "";
}
function hallAggLink(s, hallName){
  const cfg = CALENDAR_LINKS[s.name] || {};
  return (cfg.halls && cfg.halls[hallName]) || "";
}
function studioPageLink(s, hallName){
  const cfg = CALENDAR_LINKS[s.name] || {};
  return (cfg.halls && cfg.halls[hallName]) || cfg.studio || s.url || "";
}

function collectErrors(){
  const errs = [];
  for(const s of D.studios){
    const bad = s.halls.filter(x=>x.error);
    if(s.error && !s.halls.length){
      errs.push(`${s.name}: не удалось обновить (нет сохранённых данных)`);
    } else if(bad.length && bad.length === s.halls.length){
      const dt = (bad.find(x=>x.updated)||{}).updated || s.updated;
      errs.push(`${s.name}: не удалось обновить`+(dt?`, в календаре данные на ${dt}`:", нет сохранённых данных"));
    } else {
      for(const x of bad){
        errs.push(`${s.name} (${x.name}): не удалось обновить`+(x.updated?`, в календаре данные на ${x.updated}`:", нет сохранённых данных"));
      }
    }
  }
  return errs;
}

function renderSidebar(){
  let h = `<div class="side-logo"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="M12 3v5.5M21 12h-5.5M12 21v-5.5M3 12h5.5"/></svg>Фотостудии</div>
  <div class="side-sec">Обзор</div>
  <div class="nav-item ${state.view==="agg"?"active":""}" data-action="agg">
    <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></svg>Агрегатор</div>
  <div class="side-sec">Фотостудии</div>`;
  for(const s of D.studios){
    const hi = state.hall[s.id]||0;
    h += `<div class="studio-item ${state.view===s.id?"active":""}" data-action="studio" data-id="${s.id}">
      <div class="studio-top"><div class="studio-av" style="background:${s.color}1a;color:${s.color}">${esc(s.name[0])}</div>
      <div><div class="studio-name">${esc(s.name)}</div><div class="studio-addr">${esc(s.address)}</div></div>
      ${s.error&&!s.halls.length?`<span class="hall-err" title="${esc("Не удалось обновить: "+s.error)}">!</span>`:""}</div>
      <div class="hall-list">${s.halls.map((x,i)=>`<div class="hall-link ${state.view===s.id&&hi===i?"active":""}" data-action="hall" data-id="${s.id}" data-h="${i}">
        <span class="hall-name">${esc(x.name)}</span>
        ${x.error?`<span class="hall-err" title="${esc(hallTip(x))}">!</span>`:""}
      </div>`).join("")}</div></div>`;
  }
  const errs = collectErrors();
  h += `<div class="side-foot ${errs.length?"has-err":""}">
    <div class="sf-main">
      <span class="dot ${errs.length?"err":""}"></span>
      <div><b>Актуальные данные на:</b><span>${esc(D.generated)} · каждые ~10 мин</span></div>
    </div>
    ${errs.length?`<div class="side-service">${errs.map(e=>`<div>⚠ ${esc(e)}</div>`).join("")}</div>`:""}
  </div>`;
  document.getElementById("sidebar").innerHTML = h;
}

function gridHTML(s, hi){
  const {y,m} = state.month;
  const first = new Date(y,m,1), lead=(first.getDay()+6)%7;
  const dim = new Date(y,m+1,0).getDate(), weeks=Math.ceil((lead+dim)/7);
  const start = new Date(y,m,1-lead);
  let h = `<table class="grid"><thead><tr>${WD.map(w=>`<th>${w}</th>`).join("")}</tr></thead><tbody>`;
  for(let w=0;w<weeks;w++){
    h += "<tr>"; let prevM = null;
    for(let k=0;k<7;k++){
      const d = new Date(start.getFullYear(),start.getMonth(),start.getDate()+w*7+k);
      const ds = iso(d), day = dayOf(s,hi,ds);
      const items = day ? (state.mode==="busy"?day.busy:day.free) : [];
      const show = items.length>5 ? items.slice(0,4) : items;
      let cell = show.map(e=> state.mode==="busy"
        ? `<div class="ev busy" title="${esc(busyTip(e))}">${esc(busyLabel(e))}</div>`
        : `<div class="ev free" title="свободно ${dur(e.e-e.s)}">${fmt(e.s)}-${fmt(e.e)}</div>`).join("");
      if(items.length>5) cell += `<div class="more" data-action="more" data-id="${s.id}" data-h="${hi}" data-d="${ds}">ЕЩЕ ${items.length-4}</div>`;
      const sep = (k>0 && prevM!==null && d.getMonth()!==prevM) ? ` mstart" data-m="${MONTHS[d.getMonth()].toUpperCase()}` : "";
      const head = ds===D.today
        ? `<div class="drow"><div class="dnum">${d.getDate()}</div><span class="ttag">СЕГОДНЯ</span></div>`
        : `<div class="dnum">${d.getDate()}</div>`;
      h += `<td class="${d.getMonth()!==m?"out":""} ${ds===D.today?"today":""}${sep}">${head}${cell}</td>`;
      prevM = d.getMonth();
    }
    h += "</tr>";
  }
  return h+"</tbody></table>";
}

function renderStudio(s){
  const hi = state.hall[s.id]||0, {y,m} = state.month;
  const cur = y+"-"+String(m+1).padStart(2,"0");
  const hall = s.halls[hi];
  const calUrl = studioPageLink(s, hall && hall.name);
  const errMsg = (hall && hall.error) || s.error;
  const staleDt = (hall && hall.updated) || s.updated;
  const errBanner = errMsg
    ? `<div class="cal-err" title="${esc(errMsg)}">Внимание, последний раз данные обновить не удалось${staleDt?", показаны актуальные на "+esc(staleDt):""}</div>`
    : "";
  return `<div class="card"><div class="cal-head">
    <div class="cal-id"><h1 class="cal-h1">${esc(s.name)}</h1><span class="cal-addr">${esc(s.address)}</span>${calUrl?`<a class="cal-link" href="${esc(calUrl)}" target="_blank" rel="noopener noreferrer">Календарь</a>`:""}</div>
    <div class="tabs">
      <button class="tab t-red ${state.mode==="busy"?"active":""}" data-action="mode" data-v="busy">Занятое время</button>
      <button class="tab t-green ${state.mode==="free"?"active":""}" data-action="mode" data-v="free">Свободное время</button></div>
    ${errBanner}
    <div class="cal-tools">
      <button class="btn btn-icon" data-action="prev" ${cur<=D.range.from.slice(0,7)?"disabled":""}>&lt;-</button>
      <button class="btn" data-action="today" title="Вернуться к текущему месяцу">${MONTHS[m]} ${y}</button>
      <button class="btn btn-icon" data-action="next" ${cur>=D.range.to.slice(0,7)?"disabled":""}>-&gt;</button>
      ${s.halls.length>1?`<select class="select" data-action="hallsel" data-id="${s.id}">${s.halls.map((x,i)=>`<option value="${i}" ${i===hi?"selected":""}>${esc(x.name)}</option>`).join("")}</select>`:""}
    </div></div>
    ${s.halls.length?gridHTML(s,hi):`<p style="padding:0 16px 16px;color:var(--red)">Не удалось получить данные: ${esc(s.error||"нет данных")}</p>`}
  </div>`;
}

function anyFree(ds){ return D.studios.some(s=>s.halls.some((_,h)=>(dayOf(s,h,ds)||{free:[]}).free.length>0)); }
function anyBusy(ds){ return D.studios.some(s=>s.halls.some((_,h)=>{const d=dayOf(s,h,ds);return d&&d.busy.length>0;})); }
function miniCal(){
  const {y,m}=state.aggMonth;
  const first=new Date(y,m,1), lead=(first.getDay()+6)%7;
  const dim=new Date(y,m+1,0).getDate(), weeks=Math.ceil((lead+dim)/7);
  const start=new Date(y,m,1-lead);
  const cur=y+"-"+String(m+1).padStart(2,"0");
  const busyDots = state.aggMode==="busy";
  let h=`<div class="card"><div class="mini-head"><b>${MONTHS[m]} ${y}</b>
    <span><button class="btn btn-icon" data-action="aprev" ${cur<=D.range.from.slice(0,7)?"disabled":""}>&lt;-</button>
    <button class="btn btn-icon" data-action="anext" ${cur>=D.range.to.slice(0,7)?"disabled":""}>-&gt;</button></span></div>
    <div class="mini-grid">${WD.map(w=>`<div class="wd">${w[0]}</div>`).join("")}`;
  for(let w=0;w<weeks;w++)for(let k=0;k<7;k++){
    const d=new Date(start.getFullYear(),start.getMonth(),start.getDate()+w*7+k), ds=iso(d);
    const has = busyDots?anyBusy(ds):anyFree(ds);
    h+=`<button class="mini-d ${d.getMonth()!==m?"out":""} ${ds===state.aggDate?"sel":""}" data-action="pick" data-d="${ds}">${d.getDate()}${has?`<span class="fd${busyDots?" b":""}"></span>`:""}</button>`;
  }
  return h+"</div></div>";
}
function renderAgg(){
  const ds=state.aggDate, d=new Date(ds+"T12:00");
  const freeMode = state.aggMode==="free";
  let total=0,hallsHit=0,cards="";
  for(const s of D.studios){
    let rows="";
    s.halls.forEach((hall,h)=>{
      const day=dayOf(s,h,ds);
      const errBadge = hall.error ? `<span class="hall-err" title="${esc(hallTip(hall))}">!</span>` : "";
      const hUrl = hallAggLink(s, hall.name);
      const hnHTML = `<div class="hn"><div class="hn-top"><span>${esc(hall.name)}</span>${errBadge}</div>${hUrl?`<a class="cal-link" href="${esc(hUrl)}" target="_blank" rel="noopener noreferrer">Официальный календарь</a>`:""}</div>`;
      if(!day){ rows+=`<div class="hall-row">${hnHTML}<span class="empty mut">нет данных</span></div>`; return; }
      if(freeMode){
        const fr=day.free.filter(f=>f.e-f.s>=state.minDur);
        if(fr.length){ hallsHit++; total+=fr.length;
          rows+=`<div class="hall-row">${hnHTML}<div class="chips">${fr.map(f=>`<span class="chip" title="свободно ${dur(f.e-f.s)}">${fmt(f.s)}-${fmt(f.e)}<i>${dur(f.e-f.s)}</i></span>`).join("")}</div></div>`;
        } else rows+=`<div class="hall-row">${hnHTML}<span class="empty">всё занято</span></div>`;
      } else {
        const bu=day.busy;
        if(bu.length){ hallsHit++; total+=bu.length;
          rows+=`<div class="hall-row">${hnHTML}<div class="chips">${bu.map(e=>`<span class="chip busy" title="${esc(busyTip(e))}">${fmt(e.s)}-${fmt(e.e)}<i>${dur(e.e-e.s)}</i></span>`).join("")}</div></div>`;
        } else rows+=`<div class="hall-row">${hnHTML}<span class="empty mut">нет броней</span></div>`;
      }
    });
    const stUrl = studioAggLink(s);
    cards+=`<div class="card res-card"><div class="res-head">
      <div class="studio-av" style="background:${s.color}1a;color:${s.color}">${esc(s.name[0])}</div>
      <div><b>${esc(s.name)}</b><span>${esc(s.address)}</span></div>
      <span class="res-badge">${s.halls.length} ${plural(s.halls.length,"зал","зала","залов")}</span>${stUrl?`<a class="cal-link" href="${esc(stUrl)}" target="_blank" rel="noopener noreferrer">Официальный календарь</a>`:""}</div>
      ${rows}</div>`;
  }
  const sum = freeMode
    ? `${total} ${plural(total,"окно","окна","окон")} · ${hallsHit} ${plural(hallsHit,"зал","зала","залов")} со свободным временем`
    : `${total} ${plural(total,"бронь","брони","броней")} · ${hallsHit} ${plural(hallsHit,"зал","зала","залов")} с занятостью`;
  return `<div class="card"><div class="cal-head">
    <div class="cal-id"><h1 class="cal-h1">Агрегатор</h1></div>
    <div class="tabs">
      <button class="tab t-red ${!freeMode?"active":""}" data-action="amode" data-v="busy">Занятое время</button>
      <button class="tab t-green ${freeMode?"active":""}" data-action="amode" data-v="free">Свободное время</button></div>
    </div></div>
  <div class="agg-layout">${miniCal()}
    <div><div class="agg-tools">
      <b style="color:var(--ink);font-size:15px">${d.toLocaleDateString("ru-RU",{weekday:"long",day:"numeric",month:"long"})}</b>
      <span class="agg-sum">${sum}</span>
      ${freeMode?`<select class="select" data-action="mindur" style="margin-left:auto">
        ${[0,30,60,90,120].map(v=>`<option value="${v}" ${v===state.minDur?"selected":""}>${v===0?"Любая длительность":"от "+dur(v)}</option>`).join("")}
      </select>`:""}
    </div>
    ${cards||`<div class="card res-card"><span class="empty mut">${freeMode?"На эту дату свободного времени нет":"На эту дату броней нет"}</span></div>`}</div>
  </div>`;
}

function render(){
  renderSidebar();
  const s = state.view==="agg"?null:studio(state.view);
  document.getElementById("content").innerHTML = s?renderStudio(s):renderAgg();
}
function openModal(html){ document.getElementById("mbody").innerHTML=html; document.getElementById("overlay").style.display="flex"; }
function closeModal(){ document.getElementById("overlay").style.display="none"; }
function modalRows(mode){
  const {id,h,ds}=state.modal, day=dayOf(studio(id),h,ds);
  const items=day?(mode==="busy"?day.busy:day.free):[];
  return items.map(e=>mode==="busy"
    ?`<div class="ev busy">${fmt(e.s)}-${fmt(e.e)} · занято (на ${dur(e.e-e.s)})${evName(e)?" · "+esc(evName(e)):""}</div>`
    :`<div class="ev free">${fmt(e.s)}-${fmt(e.e)} · ${dur(e.e-e.s)}</div>`).join("")||'<div class="msub">-</div>';
}
function modalBody(){
  const {id,h,ds}=state.modal, s=studio(id);
  const d=new Date(ds+"T12:00");
  return `<h3>${d.toLocaleDateString("ru-RU",{weekday:"long",day:"numeric",month:"long"})}</h3>
    <div class="msub">${esc(s.name)} · ${esc(s.halls[h].name)}</div>
    <div class="tabs">
      <button class="tab t-red ${state.mmode==="busy"?"active":""}" data-action="mmode" data-v="busy">Занято</button>
      <button class="tab t-green ${state.mmode==="free"?"active":""}" data-action="mmode" data-v="free">Свободно</button></div>
    <div class="mlist" id="mlist" style="min-height:${state.modalMinH||0}px">${modalRows(state.mmode)}</div>`;
}
function measureModal(){
  const mb=document.getElementById("mbody");
  const m=document.createElement("div"); m.className="mmeasure"; mb.appendChild(m);
  let max=0;
  for(const mode of ["busy","free"]){
    m.innerHTML=`<div class="mlist">${modalRows(mode)}</div>`;
    max=Math.max(max, m.firstChild.offsetHeight);
  }
  m.remove(); state.modalMinH=max;
  const l=document.getElementById("mlist"); if(l) l.style.minHeight=max+"px";
}
function dayModal(id,h,ds){ state.modal={id,h,ds}; state.mmode=state.mode; state.modalMinH=0; openModal(modalBody()); measureModal(); }
document.addEventListener("click", e=>{
  const a=e.target.closest("[data-action]"); if(!a)return;
  const act=a.dataset.action, id=+a.dataset.id;
  if(act==="agg"){state.view="agg";render();}
  else if(act==="studio"){state.view=id;render();}
  else if(act==="hall"){e.stopPropagation();state.view=id;state.hall[id]=+a.dataset.h;render();}
  else if(act==="mode"){state.mode=a.dataset.v;render();}
  else if(act==="amode"){state.aggMode=a.dataset.v;render();}
  else if(act==="mmode"){state.mmode=a.dataset.v;document.getElementById("mbody").innerHTML=modalBody();}
  else if(act==="prev"||act==="next"){let m=state.month.m+(act==="prev"?-1:1),y=state.month.y;if(m<0){m=11;y--;}if(m>11){m=0;y++;}state.month={y,m};render();}
  else if(act==="today"){state.month={y:+D.today.slice(0,4),m:+D.today.slice(5,7)-1};render();}
  else if(act==="aprev"||act==="anext"){let m=state.aggMonth.m+(act==="aprev"?-1:1),y=state.aggMonth.y;if(m<0){m=11;y--;}if(m>11){m=0;y++;}state.aggMonth={y,m};render();}
  else if(act==="pick"){state.aggDate=a.dataset.d;state.aggMonth={y:+a.dataset.d.slice(0,4),m:+a.dataset.d.slice(5,7)-1};render();}
  else if(act==="more"){dayModal(id,+a.dataset.h,a.dataset.d);}
});
document.addEventListener("change", e=>{
  const a=e.target.closest("[data-action]"); if(!a)return;
  if(a.dataset.action==="hallsel"){state.hall[+a.dataset.id]=+a.value;render();}
  if(a.dataset.action==="mindur"){state.minDur=+a.value;render();}
});
document.getElementById("mclose").onclick=closeModal;
document.getElementById("overlay").onclick=e=>{if(e.target.id==="overlay")closeModal();};
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});
render();
