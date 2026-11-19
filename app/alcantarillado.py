"""Geometría de tramos independientes de alcantarillado entre pozos.

Cotas lomo/batea = caras EXTERIORES de tubería, nunca cotas interiores.
El diámetro calculado es EXTERIOR en metros/pulgadas, sin redondearlo a
nominal comercial. Es una cartera geométrica preliminar, no un diseño hidráulico.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import math
import numpy as np

from app.modelo import etiqueta_abscisa


@dataclass(frozen=True)
class Pozo:
    nombre: str
    abscisa_m: float
    cota_rasante_m: float
    cota_lomo_exterior_m: float
    cota_batea_exterior_m: float
    conexion: str  # entrada o salida


@dataclass(frozen=True)
class Tramo:
    inicio: Pozo
    fin: Pozo
    material: str = "PVC"
    red: str = "PLUVIAL"


@dataclass(frozen=True)
class Interferencia:
    tramo: int  # número de tramo (empieza en 1)
    abscisa_m: float
    servicio: str
    cota_superior_m: float
    cota_inferior_m: float


@dataclass(frozen=True)
class ParametrosZanja:
    sobreancho_total_m: float = 0.60
    cama_triturado_m: float = 0.10
    longitud_efectiva_tubo_m: float = 5.85
    base_m: float = 0.80
    asfalto_m: float = 0.08
    subbase_m: float = 0.0
    incremento_suministro_pct: float = 0.0
    rajon_m: float = 0.0

    def validar(self):
        valores = (self.sobreancho_total_m, self.cama_triturado_m, self.longitud_efectiva_tubo_m,
                   self.base_m, self.asfalto_m, self.subbase_m, self.incremento_suministro_pct, self.rajon_m)
        if not all(math.isfinite(v) for v in valores):
            raise ValueError("Todos los parámetros deben ser finitos.")
        if self.sobreancho_total_m < 0 or self.cama_triturado_m < 0 or self.longitud_efectiva_tubo_m <= 0:
            raise ValueError("Sobreancho/cama deben ser no negativos y longitud de tubo positiva.")
        if min(self.base_m, self.asfalto_m, self.subbase_m, self.rajon_m) < 0:
            raise ValueError("Los espesores no pueden ser negativos.")
        if not 0 <= self.incremento_suministro_pct <= 100:
            raise ValueError("Incremento de suministro fuera del intervalo 0–100 %.")


@dataclass
class ResultadoRed:
    parametros: ParametrosZanja
    tramos: list[dict]
    interferencias: list[dict]
    cantidades: dict[str, float]
    advertencias: list[str]


def calcular_red(tramos: list[Tramo], parametros: ParametrosZanja,
                 interferencias: list[Interferencia] | None = None) -> ResultadoRed:
    parametros.validar()
    if not tramos:
        raise ValueError("Debe existir al menos un tramo entre dos pozos.")
    if len(tramos) > 200:
        raise ValueError("Máximo 200 tramos por ejecución.")
    resultados, avisos = [], []
    for indice, tramo in enumerate(tramos, 1):
        i, f = tramo.inicio, tramo.fin
        if not i.nombre.strip() or not f.nombre.strip():
            raise ValueError(f"Tramo {indice}: ambos pozos necesitan un nombre.")
        if tramo.material.upper() not in {"PVC", "CONCRETO"}:
            raise ValueError(f"Tramo {indice}: material debe ser PVC o CONCRETO.")
        if tramo.red.upper() not in {"PLUVIAL", "RESIDUAL"}:
            raise ValueError(f"Tramo {indice}: red debe ser PLUVIAL o RESIDUAL.")
        if i.conexion.lower() != "salida" or f.conexion.lower() != "entrada":
            raise ValueError(f"Tramo {indice}: primer pozo debe tener SALIDA y segundo ENTRADA.")
        valores = [i.abscisa_m, f.abscisa_m, i.cota_rasante_m, f.cota_rasante_m,
                   i.cota_lomo_exterior_m, f.cota_lomo_exterior_m,
                   i.cota_batea_exterior_m, f.cota_batea_exterior_m]
        if not all(math.isfinite(v) for v in valores):
            raise ValueError(f"Tramo {indice}: cotas/abscisas deben ser finitas.")
        l = f.abscisa_m - i.abscisa_m
        if l <= 0:
            raise ValueError(f"Tramo {indice}: la abscisa de FIN debe ser mayor que INICIO.")
        d1 = i.cota_lomo_exterior_m - i.cota_batea_exterior_m
        d2 = f.cota_lomo_exterior_m - f.cota_batea_exterior_m
        if d1 <= 0 or d2 <= 0:
            raise ValueError(f"Tramo {indice}: lomo exterior debe superar la batea exterior.")
        # Mismo tubo: diferencias grandes de diámetro indican inconsistencia de campo.
        if abs(d1-d2) > 0.005:
            raise ValueError(f"Tramo {indice}: diámetros exteriores en extremos difieren más de 5 mm. Verifica cotas.")
        d = (d1+d2)/2.0
        ancho = d + parametros.sobreancho_total_m
        prof_i = i.cota_rasante_m-i.cota_batea_exterior_m+parametros.cama_triturado_m
        prof_f = f.cota_rasante_m-f.cota_batea_exterior_m+parametros.cama_triturado_m
        if min(prof_i, prof_f) <= 0:
            raise ValueError(f"Tramo {indice}: fondo de excavación por encima de la rasante.")
        pendiente = 100*(i.cota_batea_exterior_m-f.cota_batea_exterior_m)/l
        if pendiente <= 0:
            avisos.append(f"Tramo {indice}: batea de salida NO baja hacia la llegada (pendiente {pendiente:.3f} %).")
        if min(i.cota_rasante_m-i.cota_lomo_exterior_m,
               f.cota_rasante_m-f.cota_lomo_exterior_m) < parametros.asfalto_m+parametros.base_m+parametros.subbase_m+parametros.rajon_m:
            avisos.append(f"Tramo {indice}: cubierta sobre lomo menor que la suma de capas indicadas en algún extremo.")
        num = int(math.ceil(l/parametros.longitud_efectiva_tubo_m))
        ultimo = l-(num-1)*parametros.longitud_efectiva_tubo_m
        excavacion = ancho*l*(prof_i+prof_f)/2.0
        cama = ancho*l*parametros.cama_triturado_m
        asfalto = ancho*l*parametros.asfalto_m
        base = ancho*l*parametros.base_m
        subbase = ancho*l*parametros.subbase_m
        rajon = ancho*l*parametros.rajon_m
        ocupacion_exterior = math.pi*d*d/4.0*l
        relleno = excavacion-cama-asfalto-base-subbase-rajon-ocupacion_exterior
        if relleno < -1e-8:
            avisos.append(f"Tramo {indice}: cantidades incompatibles; relleno residual negativo. Revisar espesores y cotas.")
        resultados.append({
            "numero": indice, "tramo": tramo, "longitud_m": l, "diametro_exterior_m": d,
            "diametro_exterior_pulg": d/0.0254, "ancho_zanja_m": ancho,
            "pendiente_batea_pct": pendiente, "profundidad_ini_m": prof_i,
            "profundidad_fin_m": prof_f, "tubos_completos_o_cortados": num,
            "ultimo_tubo_m": ultimo,
            "excavacion_m3": excavacion, "cama_triturado_m3": cama,
            "base_m3": base, "subbase_m3": subbase, "asfalto_m3": asfalto, "rajon_m3": rajon,
            "ocupacion_tuberia_exterior_m3": ocupacion_exterior,
            "relleno_restante_estimado_m3": max(relleno, 0.0),
        })

    cruces = []
    for cruce in interferencias or []:
        if cruce.tramo < 1 or cruce.tramo > len(tramos):
            raise ValueError(f"Interferencia {cruce.servicio}: número de tramo no existente.")
        r = resultados[cruce.tramo - 1]
        t = r["tramo"]
        if not all(math.isfinite(v) for v in (cruce.abscisa_m, cruce.cota_superior_m, cruce.cota_inferior_m)):
            raise ValueError(f"Interferencia {cruce.servicio}: valores no finitos.")
        if not cruce.servicio.strip() or cruce.cota_inferior_m > cruce.cota_superior_m:
            raise ValueError(f"Interferencia {cruce.tramo}: servicio o cotas no válidas.")
        if not t.inicio.abscisa_m <= cruce.abscisa_m <= t.fin.abscisa_m:
            raise ValueError(f"Interferencia {cruce.servicio} fuera del tramo {cruce.tramo}.")
        f = (cruce.abscisa_m-t.inicio.abscisa_m)/r["longitud_m"]
        batea = (1-f)*t.inicio.cota_batea_exterior_m+f*t.fin.cota_batea_exterior_m
        lomo = (1-f)*t.inicio.cota_lomo_exterior_m+f*t.fin.cota_lomo_exterior_m
        if cruce.cota_inferior_m > lomo:
            espacio = cruce.cota_inferior_m-lomo
            posicion = "Interferencia encima de la tubería"
        elif cruce.cota_superior_m < batea:
            espacio = batea-cruce.cota_superior_m
            posicion = "Interferencia debajo de la tubería"
        else:
            espacio = -(min(cruce.cota_superior_m, lomo)-max(cruce.cota_inferior_m, batea))
            posicion = "Superposición vertical"
            avisos.append(f"Interferencia {cruce.servicio} en tramo {cruce.tramo}: solapamiento vertical. No implica cruce físico sin planta.")
        cruces.append({"tramo": cruce.tramo, "abscisa_m": cruce.abscisa_m,
                      "servicio": cruce.servicio, "cota_superior_m": cruce.cota_superior_m,
                      "cota_inferior_m": cruce.cota_inferior_m,
                      "diametro_exterior_pulg": (cruce.cota_superior_m-cruce.cota_inferior_m)/0.0254,
                      "batea_tuberia_m": batea, "lomo_tuberia_m": lomo,
                      "holgura_vertical_con_signo_m": espacio, "observacion": posicion})
    keys = ["longitud_m", "excavacion_m3", "cama_triturado_m3", "base_m3", "subbase_m3",
            "asfalto_m3", "rajon_m3", "ocupacion_tuberia_exterior_m3", "relleno_restante_estimado_m3"]
    cantidades = {k: float(sum(r[k] for r in resultados)) for k in keys}
    cantidades["numero_tubos_por_tramos"] = int(sum(r["tubos_completos_o_cortados"] for r in resultados))
    cantidades["pozos_declarados_nombres_unicos"] = len({p.nombre.strip().upper() for t in tramos for p in (t.inicio, t.fin)})
    factor = 1+parametros.incremento_suministro_pct/100
    for key in ["cama_triturado_m3", "base_m3", "subbase_m3", "rajon_m3", "asfalto_m3", "relleno_restante_estimado_m3"]:
        cantidades["suministro_estimado_"+key] = cantidades[key]*factor
    return ResultadoRed(parametros, resultados, cruces, cantidades, avisos)


def guardar_red_tramos(r: ResultadoRed, destino: str | Path) -> Path:
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f)
        w.writerow(['Tramo','Pozo_salida','Pozo_entrada','Red','Material',
                    'Abscisa_inicio_m','Abscisa_fin_m','Cota_rasante_inicio_m','Cota_rasante_fin_m',
                    'Lomo_ext_inicio_m','Batea_ext_inicio_m','Lomo_ext_fin_m','Batea_ext_fin_m',
                    'Diametro_exterior_m','Diametro_exterior_pulg_NO_nominal',
                    'Longitud_m','Pendiente_batea_pct','Ancho_zanja_m','Prof_excav_ini_m',
                    'Prof_excav_fin_m','Numero_tubos','Longitud_ultimo_tubo_m'])
        for z in r.tramos:
            t=z['tramo']; i=t.inicio; f=t.fin
            w.writerow([z['numero'],i.nombre,f.nombre,t.red,t.material,
                f'{i.abscisa_m:.3f}',f'{f.abscisa_m:.3f}',
                f'{i.cota_rasante_m:.4f}',f'{f.cota_rasante_m:.4f}',
                f'{i.cota_lomo_exterior_m:.4f}',f'{i.cota_batea_exterior_m:.4f}',
                f'{f.cota_lomo_exterior_m:.4f}',f'{f.cota_batea_exterior_m:.4f}',
                f'{z["diametro_exterior_m"]:.4f}',f'{z["diametro_exterior_pulg"]:.3f}',
                f'{z["longitud_m"]:.3f}',f'{z["pendiente_batea_pct"]:.4f}',
                f'{z["ancho_zanja_m"]:.3f}', f'{z["profundidad_ini_m"]:.3f}',
                f'{z["profundidad_fin_m"]:.3f}',z['tubos_completos_o_cortados'],f'{z["ultimo_tubo_m"]:.3f}'])
    return destino


def guardar_red_cartera(r: ResultadoRed, destino: str | Path) -> Path:
    """Cartera de replanteo TEÓRICO por tubo, con cotas por ambos extremos.

    Referencias geométricas:
    - lomo exterior: introducido en cada conexión del pozo e interpolado;
    - batea exterior: lomo menos diámetro EXTERIOR;
    - triturado (referencia superior): nivel de contacto con la batea exterior;
    - triturado inferior y fondo de excavación: batea menos cama de triturado;
    - profundidad de excavación: rasante menos fondo de excavación.

    Las cotas realmente instaladas y las lecturas de campo quedan en blanco.
    Este modelo considera una cama teórica uniforme, no un detalle constructivo
    de apoyo ni una especificación geotécnica.
    """
    destino=Path(destino)
    destino.parent.mkdir(parents=True,exist_ok=True)
    encabezados = [
        'TRAMO','TUBO No.','ABSCISA INICIO','ABSCISA FINAL',
        'LONGITUD INSTALACIÓN (m)','Longitud_efectiva_m','MATERIAL','TIPO RED',
        'DIÁMETRO EXTERIOR (pulg)','PENDIENTE TUBERÍA (%)',
        'COTA TERRENO / RASANTE inicio (m)','COTA TERRENO / RASANTE final (m)',
        'COTA LOMO EXTERIOR teórica inicio (m)',
        'COTA LOMO EXTERIOR teórica final (m)',
        'COTA BATEA EXTERIOR teórica inicio (m)',
        'COTA BATEA EXTERIOR teórica final (m)',
        'COTA SUPERIOR TRITURADO teórica inicio (m)',
        'COTA SUPERIOR TRITURADO teórica final (m)',
        'COTA INFERIOR TRITURADO teórica inicio (m)',
        'COTA INFERIOR TRITURADO teórica final (m)',
        'ESPESOR TRITURADO (m)',
        'COTA FONDO EXCAVACIÓN teórica inicio (m)',
        'COTA FONDO EXCAVACIÓN teórica final (m)',
        'PROFUNDIDAD EXCAVACIÓN teórica inicio (m)',
        'PROFUNDIDAD EXCAVACIÓN teórica final (m)',
        'ANCHO EXCAVACIÓN (m)','BASE (m)','SUBBASE (m)','RAJÓN (m)','ASFALTO (m)',
        'COTA LOMO INSTALADO medida (m)','FECHA INSTALACIÓN',
        'LECTURAS DE CAMPO / OBSERVACIONES','ORIGEN'
    ]
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f)
        w.writerow(encabezados)
        for z in r.tramos:
            t=z['tramo']
            longitud=z['longitud_m']
            paso=r.parametros.longitud_efectiva_tubo_m
            cama=r.parametros.cama_triturado_m

            def interpolar(nombre,fraccion):
                return ((1-fraccion)*getattr(t.inicio,nombre)
                        + fraccion*getattr(t.fin,nombre))

            for numero in range(1,z['tubos_completos_o_cortados']+1):
                inicio=(numero-1)*paso
                fin=min(numero*paso,longitud)
                fracciones=(inicio/longitud,fin/longitud)
                rasantes=[interpolar('cota_rasante_m',fr) for fr in fracciones]
                lomos=[interpolar('cota_lomo_exterior_m',fr) for fr in fracciones]
                bateas=[interpolar('cota_batea_exterior_m',fr) for fr in fracciones]
                fondos=[valor-cama for valor in bateas]
                profundidades=[rasante-fondo for rasante,fondo in zip(rasantes,fondos)]
                w.writerow([
                    f'{t.inicio.nombre} - {t.fin.nombre}',numero,
                    etiqueta_abscisa(t.inicio.abscisa_m+inicio),
                    etiqueta_abscisa(t.inicio.abscisa_m+fin),
                    f'{fin-inicio:.3f}',f'{fin-inicio:.3f}',
                    t.material,t.red,f'{z["diametro_exterior_pulg"]:.3f}',
                    f'{z["pendiente_batea_pct"]:.4f}',
                    *(f'{valor:.4f}' for valor in rasantes),
                    *(f'{valor:.4f}' for valor in lomos),
                    *(f'{valor:.4f}' for valor in bateas),
                    *(f'{valor:.4f}' for valor in bateas),  # nivel superior nominal de cama
                    *(f'{valor:.4f}' for valor in fondos),  # nivel inferior de cama
                    f'{cama:.3f}',
                    *(f'{valor:.4f}' for valor in fondos),  # fondo de excavación
                    *(f'{valor:.4f}' for valor in profundidades),
                    f'{z["ancho_zanja_m"]:.3f}',
                    f'{r.parametros.base_m:.3f}',
                    f'{r.parametros.subbase_m:.3f}',
                    f'{r.parametros.rajon_m:.3f}',
                    f'{r.parametros.asfalto_m:.3f}',
                    '', '', '',
                    'INTERPOLACIÓN TEÓRICA: completar datos de campo'
                ])
    return destino


def guardar_red_cantidades(r: ResultadoRed, destino: str | Path) -> Path:
    destino=Path(destino); destino.parent.mkdir(parents=True,exist_ok=True)
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['Concepto','Cantidad','Unidad','Alcance'])
        for clave,valor in r.cantidades.items():
            unidad='und' if 'numero_tubos' in clave or 'pozos_declarados' in clave else 'm' if clave=='longitud_m' else 'm3'
            w.writerow([clave,f'{valor:.4f}',unidad,'Estimación geométrica, no presupuesto normativo'])
    return destino


def guardar_interferencias(r: ResultadoRed, destino: str | Path) -> Path:
    destino=Path(destino); destino.parent.mkdir(parents=True,exist_ok=True)
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f)
        keys=['tramo','abscisa_m','servicio','cota_superior_m','cota_inferior_m',
              'lomo_tuberia_m','batea_tuberia_m','holgura_vertical_con_signo_m','observacion']
        w.writerow(keys)
        for s in r.interferencias:
            w.writerow([s[k] for k in keys])
    return destino


def guardar_red_png(r: ResultadoRed, destino: str | Path, indice: int=0) -> Path:
    """Lámina por tramo, con mismo diseño que el perfil general."""
    from app.lamina_alcantarillado import guardar_lamina_red
    return guardar_lamina_red(r, destino, indices=[indice])


def guardar_red_resumen(r: ResultadoRed, destino: str | Path) -> Path:
    destino=Path(destino);destino.parent.mkdir(parents=True,exist_ok=True)
    lines=['PERFIL VIAL | REDES DE ALCANTARILLADO - ANÁLISIS GEOMÉTRICO PRELIMINAR',
           'Entrada: LOMO exterior y DIÁMETRO EXTERIOR (pulg) de cada tramo.',
           'Batea exterior CALCULADA = lomo exterior - diámetro exterior × 0.0254.',
           'No confundir diámetro nominal/comercial con diámetro exterior real.',
           f'Ancho de zanja = diámetro exterior + {r.parametros.sobreancho_total_m:.3f} m',
           f'Cama de triturado = {r.parametros.cama_triturado_m:.3f} m BAJO la batea exterior.',
           f'Longitud efectiva por tubo = {r.parametros.longitud_efectiva_tubo_m:.3f} m',
           f'Asfalto = {r.parametros.asfalto_m:.3f} m; Base = {r.parametros.base_m:.3f} m; Subbase = {r.parametros.subbase_m:.3f} m; Rajón = {r.parametros.rajon_m:.3f} m.',
           f'Incremento de suministro = {r.parametros.incremento_suministro_pct:.2f} % (no es densidad Proctor).',
           'Los tubos se contabilizan por tramo, sin considerar uniones/desperdicio de corte.',
           'Cubicación prismática de zanja: no incluye estructuras de pozos, sostenimiento, sobreexcavación,',
           'bombeo, transportes, recubrimiento lateral especializado ni tolerancias de obra.',
           'Las interferencias se evalúan SOLO en altura, sin verificar cruce real en planta.',
           'Se necesita diseño hidráulico y verificación reglamentaria aparte.', '', 'CANTIDADES']
    lines += [f'{k}: {v:.4f}' for k,v in r.cantidades.items()]
    lines += ['', 'ADVERTENCIAS']
    lines += r.advertencias or ['Sin advertencias geométricas en este modelo limitado.']
    destino.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return destino


def guardar_red_perfil_general(r: ResultadoRed, destino: str | Path) -> Path:
    """Lámina completa con pozos, acotaciones verticales, tabla y leyenda."""
    from app.lamina_alcantarillado import guardar_lamina_red
    return guardar_lamina_red(r, destino)
