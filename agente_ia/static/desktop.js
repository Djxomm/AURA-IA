const byId = id => document.getElementById(id);
byId('btn-terminal').onclick = async () => {
  const s = await (await fetch('/api/settings')).json();
  byId('terminal-workspace').textContent = 'Carpeta: ' + s.workspace_path;
  byId('terminal-dialog').showModal();
};
byId('terminal-close').onclick = () => byId('terminal-dialog').close();
byId('terminal-form').onsubmit = async event => {
  event.preventDefault();
  const command = byId('terminal-command').value.trim();
  if (!command || !confirm('¿Autorizas ejecutar este comando en tu PC?\n\n' + command)) return;
  const btn = byId('terminal-run'); btn.disabled = true;
  byId('terminal-output').textContent = 'Ejecutando… tiempo máximo: 120 segundos.';
  try {
    const response = await fetch('/api/terminal/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command, confirmed:true})});
    const result = await response.json();
    if(!response.ok) throw new Error(JSON.stringify(result.detail));
    byId('terminal-output').textContent = result.output + '\nCódigo de salida: ' + result.exit_code + (result.timed_out ? '\nDetenido por tiempo máximo.' : '') + (result.truncated ? '\nSalida recortada.' : '');
  } catch(e) {byId('terminal-output').textContent = e.message;} finally {btn.disabled = false;}
};
byId('btn-online-search').onclick = () => {
  const query = prompt('Buscar en Internet. Solo se enviará el texto que escribas al buscador:');
  if(query?.trim()) window.open('https://www.bing.com/search?q='+encodeURIComponent(query.trim()), '_blank', 'noopener,noreferrer');
};
async function refreshSkills(){
 const response=await fetch('/api/skills');const data=await response.json();const list=byId('skills-list');list.replaceChildren();
 for(const skill of data.skills){
  const row=document.createElement('section');row.style.cssText='padding:12px 0;border-bottom:1px solid var(--border)';
  const label=document.createElement('label');const check=document.createElement('input');check.type='checkbox';check.checked=skill.enabled;
  label.append(check,document.createTextNode(' '+skill.name));row.append(label);
  const info=document.createElement('p');info.textContent=skill.description+' · '+Math.ceil(skill.bytes/1024)+' KB en disco';row.append(info);
  check.onchange=async()=>{try{const r=await fetch('/api/skills/'+skill.id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:check.checked})});if(!r.ok)throw new Error((await r.json()).detail);byId('skills-notice').textContent='Cambio guardado para el siguiente mensaje.';}catch(e){check.checked=!check.checked;byId('skills-notice').textContent=e.message;}};
  const remove=document.createElement('button');remove.type='button';remove.className='ghost-btn';remove.textContent='Eliminar';remove.onclick=async()=>{if(confirm('¿Eliminar esta habilidad del catálogo?')){await fetch('/api/skills/'+skill.id,{method:'DELETE'});await refreshSkills();}};row.append(remove);list.append(row);
 }
 if(!data.skills.length)list.textContent='No hay habilidades. Importa un archivo SKILL.md para comenzar.';
}
byId('btn-skills').onclick=async()=>{byId('skills-notice').textContent='';await refreshSkills();byId('skills-dialog').showModal();};
byId('skills-close').onclick=()=>byId('skills-dialog').close();
byId('skills-upload').onchange=async event=>{
 let count=0;
 try{for(const file of event.target.files){if(file.size>524288)throw new Error(file.name+': supera 512 KB.');const content=await file.text();const r=await fetch('/api/skills',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});if(!r.ok)throw new Error((await r.json()).detail);count++;}byId('skills-notice').textContent=count+' habilidades importadas. Activa las que necesitas.';}catch(e){byId('skills-notice').textContent=e.message;}finally{event.target.value='';await refreshSkills();}
};
const header=document.querySelector('.topbar');
if(header && typeof ResizeObserver!=='undefined') new ResizeObserver(()=>document.documentElement.style.setProperty('--topbar-height',header.offsetHeight+'px')).observe(header);
