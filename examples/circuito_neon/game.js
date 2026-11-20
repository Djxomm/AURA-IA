'use strict';
(() => {
 const canvas=document.getElementById('game'),ctx=canvas.getContext('2d');
 const ui=Object.fromEntries(['level','lives','distance','boost','status','progress','start','pause'].map(id=>[id,document.getElementById(id)]));
 const keys=new Set(),colors=['#32d9da','#80c6ff','#af9eff','#ffb672','#ff7f9e','#ffe078','#7ee5a4','#e59cff','#92e9ff','#fff0b6'];
 let state='ready',player={x:278,y:565,w:44,h:78},cars=[],distance=0,level=1,lives=3,energy=100,spawn=0,invulnerable=0,road=0,last=0,note=0;
 function reset(){state='running';player.x=278;cars=[];distance=0;level=1;lives=3;energy=100;spawn=.7;invulnerable=0;road=0;note=2;keys.clear();ui.start.textContent='Reiniciar carrera';ui.status.textContent='¡Vamos! Mantente dentro de la pista.';updateUI();}
 function pause(){if(state==='running'){state='paused';keys.clear();ui.status.textContent='En pausa.';}else if(state==='paused'){state='running';ui.status.textContent='¡Sigue la carrera!';}}
 function updateUI(){ui.level.textContent=level+' / 10';ui.lives.textContent=lives;ui.distance.textContent=Math.floor(distance)+' m';ui.boost.textContent=Math.floor(energy)+'%';ui.progress.value=(distance%350)/3.5;}
 function car(x,y,w,h,color){ctx.fillStyle='#080e1b';ctx.fillRect(x-5,y+12,8,18);ctx.fillRect(x+w-3,y+12,8,18);ctx.fillRect(x-5,y+h-30,8,18);ctx.fillRect(x+w-3,y+h-30,8,18);ctx.fillStyle=color;ctx.fillRect(x,y,w,h);ctx.fillStyle='#142d45';ctx.fillRect(x+6,y+14,w-12,20);ctx.fillRect(x+7,y+h-24,w-14,13);ctx.fillStyle='#f6f9da';ctx.fillRect(x+4,y+3,9,5);ctx.fillRect(x+w-13,y+3,9,5);}
 function overlaps(a,b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
 function tick(dt){
  if(state!=='running')return;
  const turbo=keys.has(' ')&&energy>0;energy=Math.max(0,Math.min(100,energy+(turbo?-32:17)*dt));
  const speed=(225+level*22)*(turbo?1.65:1);road=(road+speed*dt)%100;distance+=speed*dt*.10;
  if(distance>=3500){state='won';ui.progress.value=100;ui.status.textContent='¡Ganaste las diez etapas!';keys.clear();updateUI();ui.progress.value=100;return;}
  const next=Math.min(10,1+Math.floor(distance/350));if(next!==level){level=next;note=2;ui.status.textContent='Nivel '+level+' · Más tráfico, más velocidad.';}
  player.x=Math.max(108,Math.min(448,player.x+((keys.has('ArrowRight')||keys.has('d')?1:0)-(keys.has('ArrowLeft')||keys.has('a')?1:0))*310*dt));
  invulnerable=Math.max(0,invulnerable-dt);spawn-=dt;note=Math.max(0,note-dt);
  if(spawn<=0){const lane=Math.floor(Math.random()*3);cars.push({x:130+lane*125,y:-100,w:44,h:78,color:colors[Math.floor(Math.random()*colors.length)]});spawn=Math.max(.62,1.65-level*.075);}
  for(const enemy of cars){enemy.y+=speed*dt;if(invulnerable===0&&overlaps(player,enemy)){lives--;invulnerable=2;enemy.y=800;ui.status.textContent=lives?'¡Cuidado! Perdiste una vida.':'Carrera terminada. Pulsa Reiniciar.';if(lives<=0){state='lost';keys.clear();break;}}}
  cars=cars.filter(enemy=>enemy.y<830);updateUI();
 }
 function draw(){ctx.fillStyle='#0b2330';ctx.fillRect(0,0,600,720);ctx.fillStyle='#193b43';for(let y=-100;y<800;y+=100){ctx.fillRect(35,y+road,22,50);ctx.fillRect(543,y+road,22,50);}ctx.fillStyle='#1a2537';ctx.fillRect(100,0,400,720);ctx.fillStyle=colors[level-1];ctx.fillRect(96,0,5,720);ctx.fillRect(499,0,5,720);ctx.fillStyle='#c2d5df';for(let y=-100;y<800;y+=100){ctx.fillRect(232,y+road,4,48);ctx.fillRect(365,y+road,4,48);}for(const enemy of cars)car(enemy.x,enemy.y,enemy.w,enemy.h,enemy.color);if(invulnerable===0||Math.floor(invulnerable*8)%2)car(player.x,player.y,44,78,'#33f2e2');
  if(state!=='running'){ctx.fillStyle='#07101cdd';ctx.fillRect(0,0,600,720);ctx.textAlign='center';ctx.fillStyle='#f1f8ff';ctx.font='bold 38px system-ui';ctx.fillText({ready:'CIRCUITO NEÓN',paused:'PAUSA',lost:'FIN DE CARRERA',won:'¡META ALCANZADA!'}[state],300,320);ctx.font='20px system-ui';ctx.fillStyle='#76eeec';ctx.fillText(state==='won'?'10 / 10 niveles completados':state==='paused'?'Pulsa P para continuar':'Pulsa Iniciar / Reiniciar',300,365);}
  else if(note>0){ctx.textAlign='center';ctx.font='bold 27px system-ui';ctx.fillStyle='#fff';ctx.fillText('ETAPA '+level+' / 10',300,65);}
 }
 function frame(now){const dt=last?Math.min(.04,(now-last)/1000):0;last=now;tick(dt);draw();requestAnimationFrame(frame);}
 window.addEventListener('keydown',e=>{const key=e.key.length===1?e.key.toLowerCase():e.key;if(['ArrowLeft','ArrowRight',' ','p','r','a','d'].includes(key))e.preventDefault();if(!e.repeat&&key==='p')pause();if(!e.repeat&&key==='r')reset();keys.add(key);});
 window.addEventListener('keyup',e=>keys.delete(e.key.length===1?e.key.toLowerCase():e.key));
 window.addEventListener('blur',()=>{if(state==='running')pause();});
 ui.start.addEventListener('click',reset);ui.pause.addEventListener('click',pause);
 for(const [id,key] of [['left','ArrowLeft'],['right','ArrowRight'],['turbo',' ']]){const button=document.getElementById(id);button.addEventListener('pointerdown',e=>{e.preventDefault();button.setPointerCapture(e.pointerId);keys.add(key);});for(const event of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(event,()=>keys.delete(key));}
 requestAnimationFrame(frame);
})();
