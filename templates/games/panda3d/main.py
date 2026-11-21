"""AURA Turbo 3D: circuito arcade local con geometría original procedural."""
import math
import os
import json
import random
from pathlib import Path
from panda3d.core import (loadPrcFileData, GeomVertexFormat, GeomVertexData,
    GeomVertexWriter, GeomTriangles, Geom, GeomNode, NodePath, AmbientLight,
    DirectionalLight, Fog, Vec3, PNMImage, Texture, TextNode, Filename, ClockObject)
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.DirectGui import DirectFrame

loadPrcFileData('', 'window-title AURA Turbo 3D\nwin-size 1100 700\nsync-video true\naudio-library-name null\ntextures-power-2 none\nshow-frame-rate-meter false')
if os.environ.get('AURA_3D_SCREENSHOT'):
    loadPrcFileData('', 'window-type offscreen')


def center(s):
    return math.sin(s/105)*17 + math.sin(s/245)*30


def heading(s):
    return -math.degrees(math.atan2(center(s+.5)-center(s-.5),1))


def mesh(name, vertices, faces):
    data=GeomVertexData(name,GeomVertexFormat.getV3n3t2(),Geom.UHStatic)
    v=GeomVertexWriter(data,'vertex');n=GeomVertexWriter(data,'normal');uv=GeomVertexWriter(data,'texcoord')
    tri=GeomTriangles(Geom.UHStatic)
    for face in faces:
        a,b,c=[Vec3(*vertices[i]) for i in face[:3]];normal=(b-a).cross(c-a).normalized()
        start=v.getWriteRow()
        for j,index in enumerate(face):
            v.addData3(*vertices[index]);n.addData3(normal);uv.addData2(*[(0,0),(1,0),(1,1),(0,1)][j%4])
        for j in range(1,len(face)-1):tri.addVertices(start,start+j,start+j+1)
    g=Geom(data);g.addPrimitive(tri);node=GeomNode(name);node.addGeom(g)
    result=NodePath(node);result.setTwoSided(True);return result


def cube():
    return mesh('box',[(-.5,-.5,-.5),(.5,-.5,-.5),(.5,.5,-.5),(-.5,.5,-.5),(-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5)],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])


def cone():
    points=[(math.cos(i*math.tau/10),math.sin(i*math.tau/10),0) for i in range(10)]+[(0,0,1)]
    return mesh('pine',points,[(i,(i+1)%10,10) for i in range(10)]+[tuple(reversed(range(10)))])


class Race(ShowBase):
    def __init__(self):
        super().__init__();self.disableMouse();self.setBackgroundColor(.40,.68,.88)
        self.camLens.setFov(72);self.camLens.setNearFar(.2,350)
        self.box=cube();self.pine=cone();self.rng=random.Random(24)
        ambient=AmbientLight('ambient');ambient.setColor((.65,.68,.73,1));self.render.setLight(self.render.attachNewNode(ambient))
        sun=DirectionalLight('sun');sun.setColor((.95,.88,.73,1));light=self.render.attachNewNode(sun);light.setHpr(-35,-55,0);self.render.setLight(light)
        fog=Fog('distance');fog.setColor(.40,.68,.88);fog.setExpDensity(.006);self.render.setFog(fog)
        self.quality='Ligera';self.fog=fog;self.keys={};self.state='menu';self.best=0
        self.record=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AURA_Turbo'/'record-3d.json'
        try:self.best=int(json.loads(self.record.read_text())['record'])
        except (OSError,ValueError,KeyError,TypeError):pass
        for key in ('arrow_left','arrow_right','a','d','space'):
            self.accept(key,self.key,[key,True]);self.accept(key+'-up',self.key,[key,False])
        self.accept('enter',self.start);self.accept('escape',self.pause);self.accept('p',self.pause);self.accept('f1',self.quality_toggle)
        self.accept('window-event',self.window_event)
        self.world=self.render.attachNewNode('circuit')
        self.build_world();self.player=self.car((.03,.76,.93,1));self.traffic=[]
        for i in range(8):self.traffic.append([self.car(self.rng.choice([(.96,.3,.3,1),(1,.69,.17,1),(.55,.36,.88,1)])),50+i*30,self.rng.choice([-4.5,-1.5,1.5,4.5])])
        DirectFrame(frameColor=(.025,.06,.11,.92),frameSize=(-1.57,1.57,.76,1),parent=self.aspect2d)
        self.hud=OnscreenText(text='',pos=(-1.48,.90),scale=.045,align=TextNode.ALeft,fg=(.9,.96,1,1),mayChange=True)
        self.note=OnscreenText(text='',pos=(0,.25),scale=.075,align=TextNode.ACenter,fg=(.2,.93,1,1),mayChange=True)
        self.help=OnscreenText(text='Flechas / A D: conducir   ESPACIO: turbo   P: pausa   F1: calidad',pos=(0,-.93),scale=.038,fg=(1,1,1,1))
        self.reset();self.taskMgr.add(self.update,'race')
        if os.environ.get('AURA_3D_PREVIEW'):
            self.state='play';self.distance=float(os.environ['AURA_3D_PREVIEW'])

    def key(self,key,value):self.keys[key]=value

    def part(self,parent,pos,scale,color,model=None):
        node=(model or self.box).copyTo(parent);node.setPos(*pos);node.setScale(*scale);node.setColor(*color);return node

    def car(self,color):
        root=self.render.attachNewNode('car')
        self.part(root,(0,0,.65),(1.6,3.4,.65),color)
        self.part(root,(0,-.2,1.16),(1.3,1.6,.55),(.10,.22,.30,1))
        self.part(root,(0,-.25,1.48),(1.25,.9,.12),color)
        for side in (-1,1):
            for y in (-1.05,1.05):self.part(root,(side*.83,y,.43),(.23,.72,.64),(.035,.04,.055,1))
            self.part(root,(side*.5,1.72,.72),(.38,.06,.18),(1,1,.8,1))
            self.part(root,(side*.5,-1.72,.72),(.38,.06,.18),(1,.12,.15,1))
        self.part(root,(0,0,.09),(2,3.7,.03),(.08,.12,.13,1))
        root.flattenStrong();return root

    def build_world(self):
        image=PNMImage(64,64)
        for x in range(64):
            for y in range(64):
                tone=self.rng.uniform(.72,1);image.setXel(x,y,tone,tone,tone)
        asphalt=Texture('asphalt');asphalt.load(image)
        for s in range(-40,3900,8):
            segment=self.world.attachNewNode('road');segment.setPos(center(s),s,0);segment.setH(heading(s))
            self.part(segment,(0,0,-.13),(14,8.3,.25),(.22,.25,.29,1)).setTexture(asphalt)
            self.part(segment,(0,0,-.39),(190,8.4,.3),(.20+(s%24)*.001,.43,.24,1))
            for side in (-1,1):
                self.part(segment,(side*7,0,.02),(.32,8,.12),(1,.92,.8,1) if s%16 else (.85,.23,.22,1))
            for lane in (-3.5,0,3.5):self.part(segment,(lane,0,.015),(.10,3.7,.035),(.90,.92,.83,1))
        # Árboles fijos en el mundo: pasan junto a la cámara, sin reciclarse a la vista.
        for s in range(-15,3850,12):
            for side in (-1,1):
                if 610<s%1100<810:continue
                x=center(s)+side*self.rng.uniform(11,24);height=self.rng.uniform(4,9)
                self.part(self.world,(x,s,height*.22),(.45,.45,height*.5),(.31,.20,.12,1))
                for z,scale in [(.3,1),(.52,.8),(.72,.58)]:
                    self.part(self.world,(x,s,height*z),(height*.32*scale,height*.32*scale,height*.55),(.10,.31+self.rng.random()*.12,.20,1),self.pine)
        for s in range(0,3900,110):
            for side in (-1,1):
                self.part(self.world,(center(s)+side*90,s,-1),(48,65,self.rng.uniform(30,70)),(.34,.46,.49,1),self.pine)
            cloud=self.world.attachNewNode('cloud');cloud.setPos(center(s)-35,s,36)
            for i in range(4):self.part(cloud,(i*5,0,(i%2)*2),(10,5,3),(.93,.96,.98,1))
        for start in (610,1710,2810):
            for s in range(start,start+200,8):
                tunnel=self.world.attachNewNode('tunnel');tunnel.setPos(center(s),s,0);tunnel.setH(heading(s))
                for side in (-1,1):
                    self.part(tunnel,(side*8,0,3),(1,8.4,6),(.31,.35,.40,1))
                    self.part(tunnel,(side*7.4,0,4.8),(.10,1,.24),(1,.83,.38,1))
                self.part(tunnel,(0,0,6.4),(17,8.4,.8),(.35,.39,.43,1))
        self.world.flattenStrong()
        self.sun=self.part(self.render,(110,230,90),(13,13,13),(1,.88,.44,1),self.pine);self.sun.setLightOff();self.sun.setFogOff()

    def reset(self):
        self.distance=0.;self.offset=0.;self.energy=100.;self.lives=3;self.invulnerable=0.;self.steer=0.;self.speed=0.
        self.camera.setPos(center(0),-12,6)
        for i,item in enumerate(self.traffic):item[1]=50+i*30

    def start(self):
        if self.state in ('menu','over','win'):self.reset();self.state='play'

    def pause(self):
        if self.state in ('play','pause'):self.state='pause' if self.state=='play' else 'play'

    def window_event(self,window):
        if window and not window.getProperties().getForeground() and self.state=='play' and not os.environ.get('AURA_3D_SCREENSHOT'):
            self.state='pause';self.keys.clear()

    def quality_toggle(self):
        self.quality='Amplia' if self.quality=='Ligera' else 'Ligera'
        self.camLens.setFar(500 if self.quality=='Amplia' else 350)
        self.fog.setExpDensity(.004 if self.quality=='Amplia' else .006)

    def finish(self,state):
        self.state=state;score=int(self.distance*10)
        if score>self.best:
            self.best=score
            if not os.environ.get('AURA_3D_SCREENSHOT'):
                try:self.record.parent.mkdir(parents=True,exist_ok=True);self.record.write_text(json.dumps({'record':self.best}))
                except OSError:pass

    def update(self,task):
        dt=min(ClockObject.getGlobalClock().getDt(),.05)
        level=min(10,1+int(self.distance//360));turn=int(self.keys.get('arrow_right',False) or self.keys.get('d',False))-int(self.keys.get('arrow_left',False) or self.keys.get('a',False))
        if self.state=='play':
            turbo=self.keys.get('space',False) and self.energy>1
            self.energy=max(0,self.energy-dt*28) if turbo else min(100,self.energy+dt*14)
            self.speed=25+level*1.4+(15 if turbo else 0)
            self.distance+=self.speed*dt;self.offset=max(-6,min(6,self.offset+turn*dt*8))
            self.invulnerable=max(0,self.invulnerable-dt)
            for rival in self.traffic:
                rival[1]+=dt*(14+level*.6)
                if rival[1]<self.distance-18:rival[1]=self.distance+210+self.rng.random()*65;rival[2]=self.rng.choice([-4.5,-1.5,1.5,4.5])
                if abs(rival[1]-self.distance)<2.7 and abs(rival[2]-self.offset)<1.5 and self.invulnerable==0:
                    self.lives-=1;self.invulnerable=2
                    if self.lives==0:self.finish('over')
            if self.distance>=3600:self.finish('win')
        self.steer+=(turn*8-self.steer)*min(1,dt*9)
        self.player.setPos(center(self.distance)+self.offset,self.distance,0)
        self.player.setHpr(heading(self.distance)-self.steer,0,-self.steer*.40)
        self.player.setColorScale(1,1,1,.35 if self.invulnerable and int(task.time*10)%2 else 1)
        for node,s,lane in self.traffic:node.setPos(center(s)+lane,s,0);node.setH(heading(s))
        target=Vec3(center(self.distance-12)+self.offset*.45,self.distance-12,6)
        self.camera.setPos(self.camera.getPos()+(target-self.camera.getPos())*min(1,dt*7))
        self.camera.lookAt(center(self.distance+22)+self.offset*.2,self.distance+22,1.4)
        self.sun.setY(self.distance+230)
        self.hud.setText(f'AURA TURBO 3D     NIVEL {level}/10     {int(self.speed*3.6):03} km/h     VIDAS {self.lives}     TURBO {int(self.energy)}%\nPUNTOS {int(self.distance*10):06}     RECORD {self.best:06}     CALIDAD: {self.quality}')
        self.note.setText({'menu':'AURA TURBO 3D\n\nENTER para correr','pause':'PAUSA\nP para continuar','over':'FIN DE CARRERA\nENTER para volver','win':'CAMPEON\nDiez niveles completados\nENTER para volver'}.get(self.state,''))
        if os.environ.get('AURA_3D_SCREENSHOT') and task.time>.6:
            self.graphicsEngine.renderFrame();self.win.saveScreenshot(Filename.fromOsSpecific(os.environ['AURA_3D_SCREENSHOT']));self.userExit()
        return task.cont


if __name__=='__main__':Race().run()
