"""Lámina técnica longitudinal de colectores (matplotlib, datos de ResultadoRed).

El dibujo mantiene a escala las ABSCISAS y COTAS de la entrada, pero los anchos
visuales de pozos y diámetros de cruces no son dimensiones constructivas en X.
Las coberturas acotadas se calculan respecto al LOMO EXTERIOR (no a la batea).
"""
from __future__ import annotations

from pathlib import Path
import math
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Patch, Polygon, Rectangle
from matplotlib.lines import Line2D
from matplotlib.gridspec import GridSpec

from app.modelo import etiqueta_abscisa

CAPAS = (
    ("ASFALTO", "asfalto_m", "#495768", "////"),
    ("BASE GRANULAR", "base_m", "#F2D88D", ".."),
    ("SUBBASE", "subbase_m", "#EEAE75", "xx"),
    ("RAJÓN", "rajon_m", "#B8C9D4", ""),
)
CRUCES = {
    "AGUA POTABLE": "#1178BC", "GAS": "#E1A01C", "TELEFONIA": "#9552B6",
    "TELEFONÍA": "#9552B6", "ELECTRICA": "#BE5151", "ELÉCTRICA": "#BE5151",
}


def _s(v: float, n: int = 2) -> str:
    return f"{v:.{n}f}".replace('.', ',')


def cobertura_tuberia(tramo: dict, fraccion: float) -> float:
    """Distancia vertical exacta de rasante a lomo exterior interpolado."""
    t = tramo["tramo"]
    r = (1-fraccion)*t.inicio.cota_rasante_m + fraccion*t.fin.cota_rasante_m
    l = (1-fraccion)*t.inicio.cota_lomo_exterior_m + fraccion*t.fin.cota_lomo_exterior_m
    return float(r-l)


def cobertura_cruce(resultado, cruce: dict) -> float:
    """Distancia rasante -> cota superior EXTERIOR del servicio intersectante."""
    t = resultado.tramos[cruce["tramo"]-1]["tramo"]
    f = (cruce["abscisa_m"]-t.inicio.abscisa_m)/(t.fin.abscisa_m-t.inicio.abscisa_m)
    rasante = t.inicio.cota_rasante_m + f*(t.fin.cota_rasante_m-t.inicio.cota_rasante_m)
    return float(rasante-cruce["cota_superior_m"])


def _cota(ax, x, z_arriba, z_abajo, texto, col="#21344A", etiqueta_lado=1):
    """Acotación vertical con flechas y extensiones legibles."""
    ax.annotate("", (x,z_arriba), (x,z_abajo),
                arrowprops={"arrowstyle":"<->", "color":col, "lw":1.25,
                            "shrinkA":0,"shrinkB":0}, zorder=17)
    ax.plot([x-.4,x+.4], [z_arriba,z_arriba],color=col,lw=.75,zorder=17)
    ax.plot([x-.4,x+.4], [z_abajo,z_abajo],color=col,lw=.75,zorder=17)
    ax.annotate(texto, (x,(z_arriba+z_abajo)/2),
                xytext=(8*etiqueta_lado,0),textcoords="offset points",
                ha="left" if etiqueta_lado>=0 else "right", va="center",
                fontsize=7.2, color=col,fontweight="bold",
                bbox={"facecolor":"white","edgecolor":"#CCD5DC","pad":1.6,"alpha":.96},
                zorder=20)


def _rocas(ax, contorno, x0, x1, z_superior0,z_superior1,espesor, seed):
    """Traza fragmentos pétreos irregulares dentro del rajón, recortados por capa."""
    if espesor <= 0:
        return
    rng = np.random.default_rng(seed)
    L = x1-x0
    # La escala en X es diferente a la de Y: las piezas son símbolos, no granulometría.
    pasos = int(np.clip(L / max(espesor*14, .85), 7, 65))
    for fila in (0,1):
        for i in range(pasos):
            frac = (i + (.5 if fila else .1) + rng.uniform(-.12,.12))/pasos
            frac = max(.03,min(.97,frac))
            xx=x0+frac*L
            zz=(1-frac)*z_superior0+frac*z_superior1
            yy=zz-espesor*(.26 if fila == 0 else .72)+rng.uniform(-.045,.045)*espesor
            # Guijarros irregulares: polígonos cerrados con bordes pétreos.
            # La variación se aplica por eje sin rotación de coordenadas.
            ww=L/pasos*rng.uniform(.62,1.0)
            hh=espesor*rng.uniform(.34,.55)
            thetas=np.linspace(0,2*np.pi,9)[:-1]
            radios=rng.uniform(.79,1.05,8)
            vertices=[(xx+ww*.5*math.cos(a)*radios[vi],
                       yy+hh*.5*math.sin(a)*radios[vi])
                      for vi,a in enumerate(thetas)]
            piedra=Polygon(vertices,closed=True,
                           facecolor="#D3DBE0", edgecolor="#586D79",
                           lw=.7, alpha=.95, zorder=2.6)
            piedra.set_clip_path(contorno)
            ax.add_patch(piedra)


def _pozos(resultado, indices):
    pozos = {}
    for ix in indices:
        tr=resultado.tramos[ix]["tramo"]
        for p in (tr.inicio,tr.fin):
            key = (p.nombre, p.abscisa_m)
            z = pozos.setdefault(key, {"pozo":p,"bateas":[],"conexiones":[]})
            z["bateas"].append(p.cota_batea_exterior_m)
            z["conexiones"].append((p.conexion.lower(),p.cota_lomo_exterior_m))
    return list(sorted(pozos.values(),key=lambda x:x["pozo"].abscisa_m))


def _leyenda(ax, resultado, n_pozos):
    ax.set_axis_off();ax.set_xlim(0,1);ax.set_ylim(0,1)
    ax.add_patch(Rectangle((0,.02),1,.95,facecolor="#FFFFFF",edgecolor="#657B8F",lw=1))
    ax.add_patch(Rectangle((0,.83),1,.14,facecolor="#DCE9F2",edgecolor="#657B8F",lw=1))
    ax.text(.5,.90,"LEYENDA · MATERIALES Y SÍMBOLOS",ha="center",va="center",fontsize=12.5,fontweight="bold")
    items=[]
    for nombre, campo, color, trama in CAPAS:
        espesor=getattr(resultado.parametros,campo)
        if espesor>0: items.append((nombre+f" · e = {_s(espesor)} m",color,trama,"capa"))
    items.extend([
        ("Terreno natural", "#F8EEDD", "//", "capa"),
        ("Pozo de inspección (mampostería)","#F1A66C","--","capa"),
        ("Tubería PVC","#F3F8FF","","capa"),
        ("Tubería de concreto","#929BA5","","capa"),
        ("Cruce agua potable",CRUCES["AGUA POTABLE"],"","cruce"),
        ("Cruce gas",CRUCES["GAS"],"","cruce"),
        ("Cruce telefonía",CRUCES["TELEFONIA"],"","cruce"),
        ("Sentido de flujo","#26394C","","flecha"),
    ])
    mitad=int(math.ceil(len(items)/2))
    for j,(label,color,hatch,tipo) in enumerate(items):
        col=j//mitad; fila=j%mitad
        x = .045+.51*col
        y = .747 - fila * (.69/max(mitad-1,1))
        if tipo == "cruce":
            ax.plot(x+.025,y,marker='o',markersize=11,
                    markerfacecolor=color,markeredgecolor="#26394C",markeredgewidth=1.2)
        elif tipo == "flecha":
            ax.annotate('',(x+.08,y),(x,y),arrowprops={'arrowstyle':'-|>','lw':2,'color':color})
        else:
            ax.add_patch(Rectangle((x,y-.025),.09,.055,facecolor=color,
                                   edgecolor="#596A79",hatch=hatch,lw=.9))
            if label.startswith('RAJÓN'):
                for delta,dy in ((.012,-.003),(.034,.01),(.059,-.012),(.076,.014)):
                    piedra=Polygon([(x+delta-.01,y+dy),(x+delta-.004,y+dy+.015),
                                     (x+delta+.009,y+dy+.012),(x+delta+.013,y+dy-.006),
                                     (x+delta,y+dy-.013)],closed=True,
                                    facecolor='#DCE5E9',edgecolor='#586D79',lw=.6)
                    ax.add_patch(piedra)
        ax.text(x+.113,y,label,va="center",fontsize=8.5)


def _tabla(ax, resultado, indices):
    ax.set_axis_off()
    ax.add_patch(Rectangle((0,.02),1,.95, transform=ax.transAxes,
                           facecolor="white",edgecolor="#657B8F",lw=1,zorder=-2))
    ax.add_patch(Rectangle((0,.83),1,.14,transform=ax.transAxes,
                           facecolor="#DCE9F2",edgecolor="#657B8F",lw=1,zorder=-1))
    ax.text(.5,.90,"RESUMEN DE TRAMOS DE TUBERÍA",transform=ax.transAxes,
            ha="center",va="center",fontsize=12.5,fontweight="bold")
    encabezados=["TRAMO", "DE → A", "LONGITUD (m)", "MATERIAL", "Ø EXT. (pulg)", "PENDIENTE (%)"]
    datos=[]
    for j in indices:
        tdata=resultado.tramos[j];t=tdata['tramo']
        datos.append([f"T-{tdata['numero']:02d}", f"{t.inicio.nombre} → {t.fin.nombre}",
                      _s(tdata['longitud_m']),t.material.upper(),
                      _s(tdata['diametro_exterior_pulg']),
                      _s(tdata['pendiente_batea_pct'])])
    tab=ax.table(cellText=datos,colLabels=encabezados,loc="center",
                 cellLoc="center",colWidths=[.09,.29,.16,.15,.15,.16],
                 bbox=[.026,.12,.948,.64])
    tab.set_zorder(5)
    tab.auto_set_font_size(False)
    tam=min(9.5, max(5.2,11.0-(len(indices)-2)*.37))
    for (fila,col),celda in tab.get_celld().items():
        celda.set_edgecolor("#8399AA")
        celda.set_linewidth(.65)
        celda.set_facecolor("#E6F0F7" if fila==0 else ("#FFFFFF" if fila%2 else "#F2F7FB"))
        celda.get_text().set_fontsize(tam)
        if fila == 0:celda.get_text().set_fontweight("bold")
    if len(indices)>10:
        ax.text(.5,.055,"Lámina extensa: consulta la cartera CSV para detalles de cada tubo.",
                transform=ax.transAxes,ha="center",fontsize=7.0,color="#52657B")


def guardar_lamina_red(resultado, destino: str | Path, indices=None) -> Path:
    """Genera el perfil listo para mostrar/guardar en el visor de Flet.

    Cada valor de cota, material, diámetro y pendiente procede del resultado
    calculado. En ausencia de cruces NO se dibujan ni se inventan cruces.
    """
    ruta=Path(destino);ruta.parent.mkdir(parents=True,exist_ok=True)
    ids=list(range(len(resultado.tramos))) if indices is None else list(indices)
    if not ids or any(j<0 or j>=len(resultado.tramos) for j in ids):
        raise ValueError("Selecciona al menos un tramo válido.")
    datos=[resultado.tramos[j] for j in ids]
    pozos=_pozos(resultado,ids)
    x_inicio=datos[0]['tramo'].inicio.abscisa_m
    x_final=datos[-1]['tramo'].fin.abscisa_m
    largo=x_final-x_inicio
    # La escala X conserva las abscisas reales; las cotas Y se muestran en metros.
    margen=.10*largo
    x_l=x_inicio-margen
    x_r=x_final+.29*largo  # banda para dimensionar capas a la derecha
    cotas=[p['pozo'].cota_rasante_m for p in pozos]
    bateas=[v for p in pozos for v in p['bateas']]
    cruces=[cr for cr in resultado.interferencias if (cr['tramo']-1) in ids]
    total_esp=sum(getattr(resultado.parametros,campo) for _,campo,_,_ in CAPAS)
    abajo=min(bateas+[cr['cota_inferior_m'] for cr in cruces] or bateas)-.52
    cima=max(cotas)+max(.8,.27*(max(cotas)-min(bateas)))
    if cima-abajo < 2.4:cima=abajo+2.4
    nfilas=len(ids)
    # Escala suficiente para que incluso 8+ filas de tabla sean legibles.
    alto=11.8+max(0,nfilas-4)*.24
    ancho=19.2+max(0,nfilas-7)*.13
    fig=plt.figure(figsize=(ancho,alto),facecolor="white")
    grilla=GridSpec(2,2,figure=fig,height_ratios=[3.15,max(1.2,1+.12*(nfilas-2))],
                    width_ratios=[1.14,1],hspace=.055,wspace=.065,
                    left=.025,right=.98,top=.91,bottom=.075)
    ax=fig.add_subplot(grilla[0,:]); tab=fig.add_subplot(grilla[1,0]); leg=fig.add_subplot(grilla[1,1])
    fig.text(.5,.974,f"PERFIL LONGITUDINAL DE ALCANTARILLADO · {len(pozos)} POZOS",
             ha='center',va='top',fontsize=22,fontweight='bold',color='#172737')
    fig.text(.5,.935,"LÁMINA DE PREDISEÑO · COTAS EXTERIORES · POZOS/CRUCES CON ANCHO SIMBÓLICO",
             ha='center',va='center',fontsize=10.5,color='#456075',
             bbox={'boxstyle':'square,pad=.4','ec':'#A7B4C0','fc':'#F8FAFC'})
    ax.set_xlim(x_l,x_r);ax.set_ylim(abajo,cima)
    ax.set_facecolor('white')
    # Suelo natural debajo de las capas, representado como una superficie simbólica.
    for k,z in enumerate(datos):
        t=z['tramo'];x0=t.inicio.abscisa_m;x1=t.fin.abscisa_m
        R=np.array([t.inicio.cota_rasante_m,t.fin.cota_rasante_m])
        ax.fill_between([x0,x1], abajo+.05, R-total_esp,
                        color='#FAEEDF',edgecolor='#DBC4A4',hatch='//',alpha=.85,zorder=.5)
        cima_capa=R.copy()
        for j,(nombre, campo, color, trama) in enumerate(CAPAS):
            e=getattr(resultado.parametros,campo)
            if e<=0: continue
            piso=cima_capa-e
            parche=Polygon([[x0,cima_capa[0]],[x1,cima_capa[1]],[x1,piso[1]],[x0,piso[0]]],
                            facecolor=color,edgecolor='#566B7E',lw=.65,hatch=trama,zorder=2)
            ax.add_patch(parche)
            if campo=='rajon_m':
                _rocas(ax,parche,x0,x1,cima_capa[0],cima_capa[1],e,seed=203+j*97+k*17)
            cima_capa=piso
        ax.plot([x0,x1],R,color='#213248',lw=2.2,zorder=4)
        l0,l1=t.inicio.cota_lomo_exterior_m,t.fin.cota_lomo_exterior_m
        b0,b1=t.inicio.cota_batea_exterior_m,t.fin.cota_batea_exterior_m
        pvc=(t.material.upper()=='PVC')
        color='#F2F8FF' if pvc else '#A1A8B2'
        pol=Polygon([[x0,l0],[x1,l1],[x1,b1],[x0,b0]],closed=True,
                    facecolor=color,edgecolor='#164A8E' if pvc else '#27394A',lw=2.2,zorder=6)
        ax.add_patch(pol)
        # Línea interior no corresponde al diámetro interior; se usa como distintivo gráfico.
        f=.40
        ax.plot([x0,x1],[(1-f)*l0+f*b0,(1-f)*l1+f*b1],
                color='#2169D0' if pvc else '#E8EDF2',lw=1.15,zorder=7)
        # Material + diámetro + pendiente sobre cada tubo.
        # Alejar las etiquetas de cruces cercanos al centro de los tramos.
        cr_fractions=[(cr['abscisa_m']-x0)/(x1-x0) for cr in cruces
                      if cr['tramo']==z['numero']]
        opciones=[.52,.70,.32]
        frac_etiqueta=max(opciones,key=lambda v:
                          min([abs(v-crf) for crf in cr_fractions] or [1.])-
                          .12*abs(v-.5))
        xm=x0+frac_etiqueta*(x1-x0)
        zt=l0+frac_etiqueta*(l1-l0)
        zr=R[0]+frac_etiqueta*(R[1]-R[0])
        y_label=zt+(zr-zt)*.42
        ax.text(xm,y_label,
                f'{t.material.upper()} · Ø EXTERIOR {_s(z["diametro_exterior_pulg"])}"\n'
                f'PENDIENTE {_s(z["pendiente_batea_pct"])} %',
                ha='center',va='center',fontsize=9.4,fontweight='bold',color='#153044',
                bbox={'facecolor':'white','edgecolor':'#718697','pad':5,'alpha':.96},zorder=14)
        ax.annotate('',(xm+(x1-x0)*.14, zt-.05),(xm-(x1-x0)*.14,zt+.05),
                    arrowprops={'arrowstyle':'-|>','lw':2,'color':'#152D40'},zorder=13)
        # Distancia desde superficie de asfalto hasta corona exterior, por tramo.
        fr=.13 if k%2==0 else .87
        xdim=x0+fr*(x1-x0)
        ylim_s=float(R[0]+fr*(R[1]-R[0]))
        ylim_l=float(l0+fr*(l1-l0))
        _cota(ax,xdim,ylim_s,ylim_l,
              f'RASANTE → LOMO\n{_s(cobertura_tuberia(z,fr))} m',
              col='#244E74',etiqueta_lado=-1 if k%2 else 1)
    # Leyenda de la rasante en el propio dibujo, como en la lámina de referencia.
    primer=datos[0]['tramo']
    x_ref=primer.inicio.abscisa_m+.10*(primer.fin.abscisa_m-primer.inicio.abscisa_m)
    f_ref=(x_ref-primer.inicio.abscisa_m)/(primer.fin.abscisa_m-primer.inicio.abscisa_m)
    y_ref=(1-f_ref)*primer.inicio.cota_rasante_m+f_ref*primer.fin.cota_rasante_m
    ax.annotate('RASANTE ASFÁLTICA\n(PENDIENTE LONGITUDINAL)',
                (x_ref,y_ref),xytext=(x_ref+.065*largo,max(cotas)+.10),
                textcoords='data',ha='left',va='bottom',fontsize=8.6,fontweight='bold',
                color='#263D50',
                arrowprops={'arrowstyle':'-|>','lw':.9,'color':'#263D50'},
                bbox={'facecolor':'white','edgecolor':'none','alpha':.88,'pad':1.0},zorder=16)
    # Construcción de los pozos sobre las capas ya trazadas.
    ancho_pozo=min(largo*.035,max(.5,largo*.065))
    for p in pozos:
        pozo=p['pozo'];xc=pozo.abscisa_m
        z_base=min(p['bateas'])-.18;z_top=pozo.cota_rasante_m
        ancho_p=ancho_pozo
        esp_pared=ancho_p*.18
        # Hueco blanco, paredes naranjas achuradas en ladrillo, tapa y placa.
        ax.add_patch(Rectangle((xc-ancho_p/2,z_base),ancho_p,z_top-z_base,
                      facecolor='#F9FCFF',edgecolor='#343F48',lw=1.25,zorder=9))
        for paredx in (xc-ancho_p/2,xc+ancho_p/2-esp_pared):
            ax.add_patch(Rectangle((paredx,z_base),esp_pared,z_top-z_base,
                          facecolor='#EF9962',edgecolor='#4F392F',hatch='--',lw=1.0,zorder=10))
        ax.add_patch(Rectangle((xc-ancho_p*.68,z_base-.09),ancho_p*1.36,.1,
                      facecolor='#D6D5D3',edgecolor='#364451',hatch='..',lw=1,zorder=11))
        ax.add_patch(Rectangle((xc-ancho_p*.6,z_top-.035),ancho_p*1.2,.06,
                      facecolor='#DDE4EA',edgecolor='#34485A',lw=1.5,zorder=11))
        ax.vlines(xc, z_top+.08,cima-.08,linestyle='--',color='#66788A',alpha=.6,lw=.9)
        # Cotas topográficas JUNTO A SUS PUNTOS: tapa en rasante, lomo en
        # cada conexión física. En pozos intermedios puede haber dos lomos.
        # Líneas guía apuntan a la cota exacta en la representación.
        ax.annotate(f'Cota rasante/tapa: {_s(z_top,3)} m',
                    xy=(xc,z_top),xycoords='data',
                    xytext=(10,12),textcoords='offset points',
                    ha='left',va='bottom',fontsize=7.25,color='#21384A',
                    bbox={'facecolor':'white','edgecolor':'#B4C5D2','pad':2,'alpha':.97},
                    arrowprops={'arrowstyle':'->','lw':.8,'color':'#647B8E'},zorder=19)
        for conexion,lomo in p['conexiones']:
            # La conexión de entrada llega por la izquierda y la de salida
            # se dirige hacia la derecha. Cotas distintas se rotulan aparte.
            sentido=-1 if conexion=='entrada' else 1
            # La referencia pertenece al extremo de la tubería; su abscisa
            # no cambia la cota interpolada del pozo.
            ax.annotate(f'Lomo {conexion}: {_s(lomo,3)} m',
                        xy=(xc+sentido*ancho_p*.50,lomo),xycoords='data',
                        xytext=(-8 if sentido<0 else 8,
                                -13 if sentido<0 else 13),
                        textcoords='offset points',
                        ha='right' if sentido<0 else 'left',
                        va='top' if sentido<0 else 'bottom',fontsize=7.25,
                        color='#173E65',fontweight='bold',
                        bbox={'facecolor':'white','edgecolor':'#A8C2D6','pad':2,'alpha':.96},
                        arrowprops={'arrowstyle':'->','lw':.8,'color':'#32638D'},zorder=19)
        ax.text(xc,cima-.12,pozo.nombre,ha='center',va='top',fontweight='bold',fontsize=10.0,
                bbox={'boxstyle':'square,pad=.3','facecolor':'white','edgecolor':'#42586D','linewidth':1.0},zorder=23)
        ax.text(xc,abajo+.10,etiqueta_abscisa(xc),ha='center',va='bottom',fontsize=9.4,
                fontweight='bold',color='#172737',zorder=20)
    # Longitudes horizontales de tramo, con flecha de doble punta.
    altura_dim=max(cotas)+min(.43,(cima-max(cotas))*.36)
    for z in datos:
        t=z['tramo'];xi=t.inicio.abscisa_m;xf=t.fin.abscisa_m
        ax.annotate('',(xf,altura_dim),(xi,altura_dim),
                    arrowprops={'arrowstyle':'<->','color':'#273F51','lw':1.35},zorder=19)
        ax.text((xi+xf)/2,altura_dim+.06,f'L = {_s(z["longitud_m"])} m',
                ha='center',va='bottom',fontsize=9.8,fontweight='bold',
                bbox={'facecolor':'white','edgecolor':'none','pad':2},zorder=20)
    # Cruces declarados: sección circular y cota explícita rasante→lomo de cruce.
    for k,cr in enumerate(cruces):
        index=cr['tramo']-1;t=resultado.tramos[index]['tramo']
        f=(cr['abscisa_m']-t.inicio.abscisa_m)/(t.fin.abscisa_m-t.inicio.abscisa_m)
        surface=t.inicio.cota_rasante_m+f*(t.fin.cota_rasante_m-t.inicio.cota_rasante_m)
        z_sup=cr['cota_superior_m'];z_inf=cr['cota_inferior_m']
        zs=(z_sup+z_inf)/2;x=cr['abscisa_m']
        color=CRUCES.get(cr['servicio'].upper(),'#389582')
        ax.scatter([x],[zs],s=350,marker='o',c=[color],edgecolors='#243444',
                   linewidths=1.5,zorder=21)
        ax.plot(x,zs,marker='o',markersize=3, color='white',zorder=23)
        ax.annotate(f'CRUCE {cr["servicio"].upper()}\nØ EXT. {_s(cr["diametro_exterior_pulg"])}"',
                    (x,zs),xytext=(12,12 if k%2==0 else -22),textcoords='offset points',
                    fontsize=8,ha='left',va='bottom' if k%2==0 else 'top',fontweight='bold',
                    bbox={'facecolor':'white','edgecolor':color,'alpha':.97,'pad':3},
                    arrowprops={'arrowstyle':'-','color':color,'lw':.8},zorder=24)
        xd=x+min(.04*largo,max(.3,.12*(t.fin.abscisa_m-t.inicio.abscisa_m)))
        _cota(ax,xd,surface,z_sup,
              f'RASANTE → CRUCE\n{_s(cobertura_cruce(resultado,cr))} m',
              col=color,etiqueta_lado=1 if k%2 else -1)
    # Acotaciones de cada capa a la derecha (cotas verticales de espesor).
    xpos=x_final+.04*largo
    superficie=float(datos[-1]['tramo'].fin.cota_rasante_m)
    acumulado=0
    for nombre,campo,color,trama in CAPAS:
        esp=getattr(resultado.parametros,campo)
        if esp<=0:continue
        ya=superficie-acumulado;yb=ya-esp
        # Flechas en la cota vertical real, textos fuera de las capas para ser legibles.
        ax.annotate('',(xpos,ya),(xpos,yb),arrowprops={'arrowstyle':'<->','lw':1.1,'color':'#1A2D3B'},zorder=19)
        ax.plot([x_final,xpos+.012*largo],[ya,ya],color='#526779',lw=.7,zorder=18)
        ax.text(xpos+.023*largo,(ya+yb)/2,f'{nombre} · e = {_s(esp)} m',
                ha='left',va='center',fontsize=8.2,fontweight='bold',
                color='#162D40',bbox={'facecolor':'white','edgecolor':'#B8C5CF','alpha':.95,'pad':2},zorder=21)
        acumulado+=esp
    ax.set_yticks([]);ax.set_xticks([])
    for lado in ax.spines.values(): lado.set_edgecolor('#667D8D');lado.set_linewidth(.95)
    _tabla(tab,resultado,ids)
    _leyenda(leg,resultado,len(pozos))
    fig.text(.5,.029,
             'Cotas y pendientes proceden de los datos introducidos. Recubrimiento = rasante - lomo EXTERIOR. '
             'Interferencias: cruce perpendicular declarado, sin comprobación en planta. '
             'Pozos y cruces: anchos gráficos no constructivos.',
             ha='center',va='bottom',fontsize=8,color='#516477')
    fig.savefig(ruta,dpi=165,facecolor='white')
    plt.close(fig)
    return ruta
