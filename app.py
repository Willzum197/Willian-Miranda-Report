# -*- coding: utf-8 -*-
# Gestor de Morbilidad - Willian Almenar
# SISPRO / EPI12 / EPI15  +  Motor SIS-03/PRO (tabulador diario) + Foto->IA
import streamlit as st
import pandas as pd
import numpy as np
import re, calendar, base64
from datetime import datetime, timedelta
from io import BytesIO

st.set_page_config(page_title="Gestor de Morbilidad - Willian Almenar", layout="wide")

# ============ ESTILOS ============
st.markdown("""
    <style>
    .main-header {background-color:#1E3A5F;padding:1rem;border-radius:10px;color:white;text-align:center;}
    .success-box {background-color:#d4edda;padding:1rem;border-radius:5px;border-left:5px solid #28a745;}
    .warning-box {background-color:#fff3cd;padding:1rem;border-radius:5px;border-left:5px solid #ffc107;}
    .danger-box {background-color:#f8d7da;padding:1rem;border-radius:5px;border-left:5px solid #dc3545;}
    .info-box {background-color:#d1ecf1;padding:1rem;border-radius:5px;border-left:5px solid #17a2b8;}
    .match-box {background-color:#e8f5e9;padding:1rem;border-radius:10px;border-left:5px solid #2e7d32;margin-bottom:1rem;}
    .discrepancy-box {background-color:#fff3e0;padding:1rem;border-radius:10px;border-left:5px solid #ff9800;margin-bottom:1rem;}
    .total-box {background-color:#e8f5e9;padding:1rem;border-radius:10px;border-left:5px solid #2e7d32;margin:1rem 0;}
    .mes-box {background-color:#fff3e0;padding:1rem;border-radius:10px;margin:0.5rem 0;border:2px solid #ff9800;}
    .semana-box {background-color:#f3e5f5;padding:0.8rem;border-radius:8px;margin:0.5rem 0;border-left:4px solid #7b1fa2;}
    .grupo-box {background-color:#e3f2fd;padding:0.5rem 1rem;border-radius:5px;margin:0.2rem 0;border-left:3px solid #1976d2;}
    .reporte-box {background-color:#fce4ec;padding:1rem;border-radius:10px;border-left:5px solid #c62828;margin:1rem 0;}
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>Gestor de Morbilidad - Validación de Reportes</h1><p>Willian Almenar</p></div>', unsafe_allow_html=True)
st.markdown("---")

# ============ DICCIONARIOS Y FUNCIONES BASE (ORIGINAL) ============
EXPECTED_COLUMNS = {
    "SISPRO": ["CODIGO_EPS","NOMBRE_EPS","TIPO_DOCUMENTO","NUMERO_DOCUMENTO","NOMBRE_PACIENTE","APELLIDO_PACIENTE",
               "FECHA_ATENCION","CODIGO_DIAGNOSTICO","DESCRIPCION_DIAGNOSTICO","CODIGO_CIE10","SEXO","EDAD","MUNICIPIO","DEPARTAMENTO"],
    "EPI12": ["CODIGO_EPS","NOMBRE_EPS","TIPO_DOCUMENTO","NUMERO_DOCUMENTO","NOMBRE_PACIENTE","APELLIDO_PACIENTE",
              "FECHA_ATENCION","CODIGO_DIAGNOSTICO","DESCRIPCION_DIAGNOSTICO","CODIGO_CIE10","PROCEDIMIENTO",
              "DESCRIPCION_PROCEDIMIENTO","SEXO","EDAD","ATENCION_AMBULATORIA","EMERGENCIA"],
    "EPI15": ["CODIGO_EPS","NOMBRE_EPS","TIPO_DOCUMENTO","NUMERO_DOCUMENTO","NOMBRE_PACIENTE","APELLIDO_PACIENTE",
              "FECHA_ATENCION","CODIGO_DIAGNOSTICO","DESCRIPCION_DIAGNOSTICO","CODIGO_CIE10","SERVICIO","SEXO","EDAD","MUNICIPIO","CAUSA_CONSULTA"]
}

GRUPOS_SISPRO = {
    'Total Lactantes y Pre-escolares': (0, 5),
    'Total Escolares': (6, 11),
    'Total Adolescentes de 12 a Menores de 19 Años': (12, 18),
    'Total Adultos': (19, 59),
    'Total de la Tercera Edad': (60, 150)
}

GRUPOS_ETARIOS = {
    '0-4 anos': (0,4),'5-9 anos': (5,9),'10-14 anos': (10,14),'15-19 anos': (15,19),'20-24 anos': (20,24),
    '25-29 anos': (25,29),'30-34 anos': (30,34),'35-39 anos': (35,39),'40-44 anos': (40,44),'45-49 anos': (45,49),
    '50-54 anos': (50,54),'55-59 anos': (55,59),'60-64 anos': (60,64),'65+ anos': (65,150)
}

def obtener_semana_mes(fecha):
    if pd.isna(fecha): return 0
    dia = fecha.day
    if dia <= 7: return 1
    elif dia <= 14: return 2
    elif dia <= 21: return 3
    elif dia <= 28: return 4
    return 5

def asignar_grupo_etario(edad):
    if pd.isna(edad): return 'Sin dato'
    try:
        edad = float(edad)
        for grupo,(mn,mx) in GRUPOS_ETARIOS.items():
            if mn <= edad <= mx: return grupo
        return 'Sin dato'
    except: return 'Sin dato'

def asignar_grupo_sispro(edad):
    if pd.isna(edad): return 'Sin dato'
    try:
        edad = float(edad)
        for grupo,(mn,mx) in GRUPOS_SISPRO.items():
            if mn <= edad <= mx: return grupo
        return 'Sin dato'
    except: return 'Sin dato'

def normalizar_identificacion(df):
    if 'NUMERO_DOCUMENTO' in df.columns: df['IDENTIFICACION'] = df['NUMERO_DOCUMENTO'].astype(str).str.strip()
    elif 'DOCUMENTO' in df.columns: df['IDENTIFICACION'] = df['DOCUMENTO'].astype(str).str.strip()
    else: df['IDENTIFICACION'] = df.index.astype(str)
    return df

def detectar_columna_fecha(df):
    posibles = ['FECHA_ATENCION','FECHA ATENCION','FECHADEATENCION','FECHA_CONSULTA','FECHA CONSULTA','FECHACONSULTA',
                'FECHA_DE_ATENCION','FECHA_DE_CONSULTA','FECHA_REGISTRO','FECHA REGISTRO','FECHAREGISTRO','FECHA','FECH','DATE','FECHA_DIA']
    for col in df.columns:
        cu = col.upper().strip()
        for f in posibles:
            if cu == f or cu == f.replace(' ','_') or cu == f.replace(' ',''): return col
    for col in df.columns:
        if 'FECHA' in col.upper() or 'DATE' in col.upper(): return col
    return None

def convertir_fechas(df, columna_fecha):
    if columna_fecha is None: return None, "No se encontró columna de fecha"
    try:
        if pd.api.types.is_numeric_dtype(df[columna_fecha]):
            fechas = pd.to_datetime(df[columna_fecha], unit='D', origin='1899-12-30', errors='coerce')
            if fechas.notna().sum() > 0: return fechas, "Formato Excel (fecha serial)"
    except: pass
    formatos = ['%d/%m/%Y','%m/%d/%Y','%Y-%m-%d','%d-%m-%Y','%d.%m.%Y','%Y/%m/%d','%d/%m/%y','%m/%d/%y',
                '%Y-%m-%d %H:%M:%S','%d/%m/%Y %H:%M:%S']
    for formato in formatos:
        try:
            fechas = pd.to_datetime(df[columna_fecha], format=formato, errors='coerce')
            if fechas.notna().sum() > 0: return fechas, f"Formato detectado: {formato}"
        except: continue
    try:
        fechas = pd.to_datetime(df[columna_fecha], errors='coerce')
        if fechas.notna().sum() > 0: return fechas, "Conversion automatica"
    except: pass
    return None, "No se pudieron convertir las fechas"

def analizar_archivo(file, tipo_archivo, columna_fecha_seleccionada=None):
    if file is None: return None, "No se ha subido ningun archivo"
    try:
        if file.name.endswith('.xls'): df = pd.read_excel(file, engine='xlrd', header=0)
        else: df = pd.read_excel(file, engine='openpyxl', header=0)
        df.columns = df.columns.str.strip().str.upper()
        info = {"filas": df.shape[0], "columnas": df.shape[1], "nombres_columnas": list(df.columns),
                "fecha_carga": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        df = normalizar_identificacion(df)
        if 'EDAD' in df.columns:
            df['GRUPO_ETARIO'] = df['EDAD'].apply(asignar_grupo_etario)
            df['GRUPO_SISPRO'] = df['EDAD'].apply(asignar_grupo_sispro)
        columna_fecha = columna_fecha_seleccionada if columna_fecha_seleccionada else detectar_columna_fecha(df)
        info["columna_fecha_detectada"] = columna_fecha
        if columna_fecha:
            fechas, mensaje = convertir_fechas(df, columna_fecha)
            if fechas is not None:
                df['FECHA_ATENCION'] = fechas
                df['ANO'] = df['FECHA_ATENCION'].dt.year
                df['MES'] = df['FECHA_ATENCION'].dt.month
                df['SEMANA_ANUAL'] = df['FECHA_ATENCION'].dt.isocalendar().week
                df['SEMANA'] = df['FECHA_ATENCION'].apply(obtener_semana_mes)
                info["fechas_ok"] = True; info["fechas_validas"] = fechas.notna().sum(); info["mensaje_fechas"] = mensaje
                if fechas.notna().sum() > 0:
                    info["fecha_min"] = fechas.min(); info["fecha_max"] = fechas.max()
            else:
                info["fechas_ok"] = False; info["error_fechas"] = mensaje
        else:
            info["fechas_ok"] = False; info["error_fechas"] = "No se encontró columna de fecha"
        info["estadisticas"] = {"total_registros": len(df),
                                "pacientes_unicos": df['IDENTIFICACION'].nunique() if 'IDENTIFICACION' in df.columns else 0}
        return df, info
    except Exception as e:
        return None, f"Error al procesar el archivo: {str(e)}"

def validar_mes_completo(df_sispro, df_epi12, df_epi15, ano, mes):
    mask_sispro = (df_sispro['ANO'] == ano) & (df_sispro['MES'] == mes)
    mask_epi12  = (df_epi12['ANO'] == ano) & (df_epi12['MES'] == mes)
    mask_epi15  = (df_epi15['ANO'] == ano) & (df_epi15['MES'] == mes)
    df_sispro_mes = df_sispro[mask_sispro].copy()
    df_epi12_mes  = df_epi12[mask_epi12].copy()
    df_epi15_mes  = df_epi15[mask_epi15].copy()
    if len(df_sispro_mes)==0 and len(df_epi12_mes)==0 and len(df_epi15_mes)==0:
        return None, f"No hay datos para {mes:02d}/{ano}"
    grupos_sispro, total_sispro = {}, 0
    for grupo in GRUPOS_SISPRO.keys():
        if 'GRUPO_SISPRO' in df_sispro_mes.columns:
            count = df_sispro_mes[df_sispro_mes['GRUPO_SISPRO']==grupo]['IDENTIFICACION'].nunique()
        else: count = 0
        grupos_sispro[grupo] = count; total_sispro += count
    totales_semanales_epi12, total_epi12 = {}, 0
    if len(df_epi12_mes) > 0:
        col_amb = next((c for c in df_epi12_mes.columns if 'AMBULATORIA' in c or 'AMB' in c), None)
        col_emerg = next((c for c in df_epi12_mes.columns if 'EMERGENCIA' in c or 'EMER' in c), None)
        for sem in range(1, 53):
            df_sem = df_epi12_mes[df_epi12_mes['SEMANA_ANUAL'] == sem]
            if len(df_sem) > 0:
                amb_val = df_sem[col_amb].sum() if col_amb else len(df_sem)
                emerg_val = df_sem[col_emerg].sum() if col_emerg else 0
                tot_sem = amb_val + emerg_val
                totales_semanales_epi12[f"Semana {sem}"] = tot_sem
                total_epi12 += tot_sem
        if not totales_semanales_epi12: total_epi12 = df_epi12_mes['IDENTIFICACION'].nunique()
    total_epi15 = len(df_epi15_mes) if len(df_epi15_mes) > 0 else 0
    diff12 = total_epi12 - total_sispro; diff15 = total_epi15 - total_sispro
    errores = []
    if diff12 != 0: errores.append({'tipo':'EPI12','descripcion':f"EPI12 difiere de SISPRO en {abs(diff12)} registros."})
    if diff15 != 0: errores.append({'tipo':'EPI15','descripcion':f"EPI15 difiere de SISPRO en {abs(diff15)} causas."})
    return {'mes': f"{mes:02d}/{ano}", 'ano': ano, 'mes_num': mes,
            'sispro': {'grupos': grupos_sispro, 'total': total_sispro},
            'epi12': {'totales_semanales': totales_semanales_epi12, 'total': total_epi12},
            'epi15': {'total': total_epi15},
            'diferencias': {'sispro_epi12': diff12, 'sispro_epi15': diff15},
            'errores': errores, 'todos_coinciden': (diff12==0 and diff15==0)}, None

def validar_periodo(df_sispro, df_epi12, df_epi15, ano_inicio, mes_inicio, ano_fin, mes_fin):
    resultados = []
    fecha_actual = datetime(ano_inicio, mes_inicio, 1); fecha_fin = datetime(ano_fin, mes_fin, 1)
    while fecha_actual <= fecha_fin:
        ano, mes = fecha_actual.year, fecha_actual.month
        resultado, _ = validar_mes_completo(df_sispro, df_epi12, df_epi15, ano, mes)
        if resultado: resultados.append(resultado)
        fecha_actual = datetime(ano+1,1,1) if mes==12 else datetime(ano,mes+1,1)
    return resultados

# ==================================================================
# ============ MOTOR SIS-03/PRO (TABULADOR DIARIO) =================
# ==================================================================
MESES = ['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE']
DIAS_MES = [31,28,31,30,31,30,31,31,30,31,30,31]

def norm_code(v):
    if not isinstance(v,str): return None
    m = re.match(r'^\s*(\d{2}(?:\.\d{2})*)[\.\s]*$', v)
    return m.group(1) if m else None

def num(v):
    if isinstance(v,bool): return np.nan
    if isinstance(v,(int,float)): return float(v)
    if isinstance(v,str):
        t = v.strip().replace(',','.')
        if re.fullmatch(r'-?\d+(\.\d+)?', t): return float(t)
    return np.nan

def leer_libro(a):
    nombre = getattr(a,'name',str(a))
    if hasattr(a,'read'):
        try: a.seek(0)
        except Exception: pass
        data = a.read()
    else:
        data = open(a,'rb').read()
    hojas = []
    if nombre.lower().endswith('.xls'):
        import xlrd
        bk = xlrd.open_workbook(file_contents=data)
        for sh in bk.sheets():
            hojas.append((sh.name, [[sh.cell_value(r,c) for c in range(sh.ncols)] for r in range(sh.nrows)]))
    else:
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(data), data_only=True, read_only=True)
        for ws in wb.worksheets:
            hojas.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    return hojas

def es_tabulador(hojas):
    for n,m in hojas[:3]:
        for r in range(min(30,len(m))):
            f = [str(x).strip().lower() for x in m[r] if x is not None]
            if any(x in ('código','codigo') for x in f) and any('actividad' in x for x in f): return True
    return False

def detectar_layout(matriz):
    hdr, cc, cl = None, 0, 1
    for r in range(min(40,len(matriz))):
        for c,v in enumerate(matriz[r]):
            if isinstance(v,str) and v.strip().lower() in ('código','codigo'):
                hdr, cc = r, c; break
        if hdr is not None: break
    if hdr is None: return None
    fila = matriz[hdr]
    for c,v in enumerate(fila):
        if isinstance(v,str) and 'actividad' in v.strip().lower(): cl = c
    dias, ct = {}, None
    for c,v in enumerate(fila):
        n = num(v)
        if n is not None and not np.isnan(n) and float(n).is_integer() and 1 <= n <= 31 and c > cl: dias[int(n)] = c
        if isinstance(v,str) and 'TOTAL' in v.upper(): ct = c
    if len(dias) < 28: dias = {d: cl+d for d in range(1,32)}
    if ct is None: ct = max(dias.values())+1
    return {'header_row':hdr,'col_code':cc,'col_label':cl,'dias':dias,'col_total':ct}

MAPA_META = {'entidad':'entidad','municipio':'municipio','establecimiento':'establecimiento',
             'nombre del medico':'medico','mes':'mes','año':'anio','ano':'anio'}

def extraer_meta(matriz, hdr):
    meta = {k:'' for k in ['entidad','municipio','establecimiento','medico','mes','anio','profesional','enfermera','ams']}
    for r in range(hdr):
        fila = matriz[r]
        for c,v in enumerate(fila):
            if not isinstance(v,str): continue
            t = v.strip(); low = t.lower()
            for campo,clave in MAPA_META.items():
                if low.startswith(campo+':'):
                    resto = t.split(':',1)[1].strip()
                    if not resto:
                        for k in range(c+1,len(fila)):
                            w = fila[k]
                            if isinstance(w,str) and w.strip():
                                wt = w.strip()
                                if wt.endswith(':') or any(wt.lower().startswith(x+':') for x in MAPA_META): break
                                resto = wt; break
                            nw = num(w)
                            if nw is not None and not np.isnan(nw): resto = str(int(nw)); break
                    if resto and not meta[clave]: meta[clave] = resto
            if 'NOMBRE MEDICO O PROFESIONAL' in t.upper():
                for ln in t.split('\n'):
                    l = ln.strip(); u = l.upper()
                    if u.startswith('NOMBRE MEDICO O PROFESIONAL:'): meta['profesional'] = l.split(':',1)[1].strip()
                    elif u.startswith('NOMBRE ENFERMERA O AUXILIAR:'): meta['enfermera'] = l.split(':',1)[1].strip()
                    elif u.startswith('NOMBRE AMS/ACAPS:'): meta['ams'] = l.split(':',1)[1].strip()
    if not meta['anio']:
        for r in range(hdr):
            fila = matriz[r]
            if any(isinstance(v,str) and v.strip().lower().startswith('mes:') for v in fila):
                for v in fila:
                    n = num(v)
                    if n is not None and not np.isnan(n) and 1900 <= n <= 2100: meta['anio'] = str(int(n)); break
            if meta['anio']: break
    return meta

def parse_hoja(nombre, matriz):
    lay = detectar_layout(matriz)
    if lay is None: return None
    hdr = lay['header_row']; mx = max(lay['col_total'], max(lay['dias'].values())); recs = []
    for r in range(hdr+1, len(matriz)):
        fila = matriz[r]
        if lay['col_code'] >= len(fila): continue
        code = norm_code(fila[lay['col_code']])
        if not code: continue
        lab = fila[lay['col_label']] if lay['col_label'] < len(fila) else ''
        lab = str(lab).strip() if lab is not None else ''
        daily = [num(fila[lay['dias'][d]]) if d in lay['dias'] and lay['dias'][d] < len(fila) else np.nan for d in range(1,32)]
        tot = num(fila[lay['col_total']]) if lay['col_total'] < len(fila) else np.nan
        recs.append({'fila':r+1,'codigo':code,'actividad':lab,'nivel':code.count('.')+1,'dias':daily,'total':tot,
                     'suma':float(np.nansum(daily)),
                     'celdas':int(sum(1 for v in daily if not np.isnan(v) and v>0)),'raw':fila[:mx+1]})
    if not recs: return None
    df = pd.DataFrame(recs); codes = set(df.codigo)
    df['es_padre'] = [any(o!=c and o.startswith(c+'.') for o in codes) for c in df.codigo]
    return {'nombre':nombre,'df':df,'meta':extraer_meta(matriz,hdr),'header_row':hdr+1,'layout':lay,'nrows':len(matriz)}

GRUPOS_SIS03 = [
 {'nombre':'Lactantes y preescolares (0 a <7 a)','corto':'Lact/Preesc','total':'01.01.01','m':'01.01.01.01','f':'01.01.01.02',
  'primeras':['01.01.02.01','01.01.02.02','01.01.02.03','01.01.03.01','01.01.03.02'],'sucesivas':['01.01.02.04','01.01.03.03'],
  'enfermeria':['01.01.02.05','01.01.03.04'],'consultas':['01.01.02','01.01.03'],'dx':'01.01.11',
  'sanos':['01.01.11.01','01.01.11.03'],'enfermos':['01.01.11.02','01.01.11.04'],
  'nut':'01.01.04','ta':'01.01.07','riesgo':'01.01.08','ref':'01.01.12'},
 {'nombre':'Escolares (7 a <12 a)','corto':'Escolar','total':'01.02.01','m':'01.02.01.01','f':'01.02.01.02',
  'primeras':['01.02.02.01','01.02.02.02','01.02.02.03','01.02.02.06'],'sucesivas':['01.02.02.04'],'enfermeria':['01.02.02.05'],
  'consultas':['01.02.02'],'dx':'01.02.13','sanos':['01.02.13.01'],'enfermos':['01.02.13.02'],
  'nut':'01.02.07','ta':'01.02.09','riesgo':'01.02.10','ref':'01.02.14'},
 {'nombre':'Adolescentes (12 a <19 a)','corto':'Adolescente','total':'01.05.01','m':'01.05.01.01','f':'01.05.01.02',
  'primeras':['01.05.02.01'],'sucesivas':['01.05.02.02'],'enfermeria':['01.05.02.03'],'consultas':['01.05.02'],
  'dx':'01.05.03','sanos':['01.05.03.01'],'enfermos':['01.05.03.02'],
  'nut':'01.05.04','ta':'01.05.06','riesgo':'01.05.07','ref':'01.05.10'},
 {'nombre':'Adultos (19 a <60 a)','corto':'Adulto','total':'02.00.01','m':'02.00.01.01','f':'02.00.01.02',
  'primeras':['02.00.02.01'],'sucesivas':['02.00.02.02'],'enfermeria':['02.00.02.03'],'consultas':['02.00.02'],
  'dx':'02.00.03','sanos':['02.00.03.01'],'enfermos':['02.00.03.02'],
  'nut':'02.00.04','ta':'02.00.06','riesgo':'02.00.07','ref':'02.00.10'},
 {'nombre':'Tercera edad (60 a y mas)','corto':'Tercera edad','total':'03.00.01','m':'03.00.01.01','f':'03.00.01.02',
  'primeras':['03.00.02.01'],'sucesivas':['03.00.02.02'],'enfermeria':['03.00.02.03'],'consultas':['03.00.02'],
  'dx':'03.00.03','sanos':['03.00.03.01'],'enfermos':['03.00.03.02'],
  'nut':'03.00.04','ta':'03.00.06','riesgo':'03.00.07','ref':'03.00.10'}]

NUT_CATS = ['Exceso','Normal','Zona Critica','Leve','Moderada','Grave','Bajo Peso']
TA_CATS  = ['Normal','Hipertenso','Hipotenso']
PROGRAMAS = [('01.03','CED / Diarreicas'),('01.04','IRA'),('04.01','Diabetes'),('04.02','Cardiovascular / HTA'),
 ('06.01','Tuberculosis'),('06.02','Asma'),('07','Salud reproductiva'),('08','Cancer cervico-uterino'),
 ('09','ITS / VIH'),('17','Salud mental'),('11','Nivel terciario'),('12','Otras actividades'),
 ('13','Educacion sanitaria'),('14','Visitas')]
MORB_CANON = [('Infecciosas y parasitarias',r'infeccios'),('Neoplasias',r'neoplasia'),
 ('Sangre y organos hematopoyeticos',r'sangre'),('Endocrina, nutricional y metabolica',r'endocrin'),
 ('Trastorno mental y comportamiento',r'mental y comp'),('Sistema nervioso',r'nervioso'),('Ojo y sus anexos',r'ojo'),
 ('Oido y apofisis mastoides',r'o[ií]do'),('Sistema circulatorio',r'circulatorio'),('Sistema respiratorio',r'respiratorio'),
 ('Sistema digestivo',r'digestivo'),('Piel y tejido conjuntivo',r'piel'),('Genital y urinaria',r'genital|urinar'),
 ('Parto y puerperio',r'parto y puerper'),('Traumatismos y envenenamientos',r'traumatism'),
 ('Anomalias congenitas',r'anomal'),('Control pre-natal',r'control pre-?natal'),('Parto distocico',r'parto dist'),
 ('Cianosis perinatal',r'cianosis'),('Ictericia neonatal',r'ictericia'),('Medicamentos en el embarazo',r'medicament'),
 ('Embarazo con tabaco',r'tabaco'),('Embarazo con alcohol',r'alcohol'),('Embarazo con cocaina',r'coca[ií]na'),
 ('Embarazo con pre-eclampsia',r'eclampsia')]

def canon_morb(l):
    t = l.lower()
    for n,p in MORB_CANON:
        if re.search(p,t): return n
    return l.strip()

def canon_ref(l):
    t = re.sub(r'\s+',' ', l.strip())
    for a,b in [('Traum. y Ortopedia','Traumatologia y Ortopedia'),('Traumatología  y Ortopedia','Traumatologia y Ortopedia'),
                ('Traumatología y Ortopedia','Traumatologia y Ortopedia'),('Médicos de Familia','Medico de Familia'),
                ('Medicos de Familia','Medico de Familia'),('Médico de Familia','Medico de Familia'),
                ('Atención Psiquiátrica de Ambulatoria','Atencion Psiquiatrica Ambulatoria'),
                ('Atención Psiquiátrica Ambulatoria','Atencion Psiquiatrica Ambulatoria'),
                ('Hospitalización Psiquiática de Agudos','Hospitalizacion Psiquiatrica de Agudos'),
                ('Hospitalización Psiquiátrica de Agudos','Hospitalizacion Psiquiatrica de Agudos')]:
        t = t.replace(a,b)
    return re.sub(r'\(Ministerio de (Educación|Sanidad)\)','(Ministerio)', t)

def idx_hoja(h): return {r.codigo: r for r in h['df'].itertuples(index=False)}
def val(ix,c,campo='suma'):
    r = ix.get(c)
    if r is None: return 0.0
    if campo=='suma': return float(r.suma)
    t = r.total; return 0.0 if (t is None or np.isnan(t)) else float(t)
def act_de(ix,c):
    r = ix.get(c); return r.actividad if r is not None else '-'
def fila_de(ix,c):
    r = ix.get(c); return int(r.fila) if r is not None else None
def dias_de(ix,c):
    r = ix.get(c); return list(r.dias) if r is not None else [np.nan]*31
def suma_lista(ix,cs,campo='suma'): return float(sum(val(ix,c,campo) for c in cs))
def hijos(ix,p):
    n = p.count('.')+1
    return [c for c in ix if c.startswith(p+'.') and c.count('.')==n]

def analizar_hoja(hoja, modo='dias'):
    """modo='dias': suma C:AG (produccion real). modo='ah': columna TOTAL SIS O4."""
    campo = 'total' if modo=='ah' else 'suma'
    df = hoja['df']; ix = idx_hoja(hoja)
    V  = lambda c: val(ix,c,campo)
    S  = lambda cs: suma_lista(ix,cs,campo)
    VF = lambda c: (val(ix,c,'suma') or val(ix,c,'total'))
    out = {'nombre':hoja['nombre'],'meta':hoja['meta'],'header_row':hoja['header_row'],'modo':modo}
    us = {}
    for r in df.itertuples(index=False):
        for i,v in enumerate(r.dias):
            if not np.isnan(v) and v>0: us[i+1] = us.get(i+1,0)+v
    out['dias_con_carga'] = sorted(us); out['carga_por_dia'] = us
    filas = []
    for g in GRUPOS_SIS03:
        T = V(g['total'])
        d = {'grupo':g['nombre'],'corto':g['corto'],'codigo':g['total'],'fila':fila_de(ix,g['total']),'total':T,
             'total_ah':val(ix,g['total'],'total'),'m':V(g['m']),'f':V(g['f']),
             'primeras':S(g['primeras']),'sucesivas':S(g['sucesivas']),'enfermeria':S(g['enfermeria']),
             'sanos':S(g['sanos']),'enfermos':S(g['enfermos']),'dx_declarado':V(g['dx']),'dx_fila':fila_de(ix,g['dx']),
             'nut':{c:V(g['nut']+'.%02d'%(i+1)) for i,c in enumerate(NUT_CATS)},'nut_total':V(g['nut']),'nut_fila':fila_de(ix,g['nut']),
             'ta':{c:V(g['ta']+'.%02d'%(i+1)) for i,c in enumerate(TA_CATS)},'ta_total':V(g['ta']),'ta_fila':fila_de(ix,g['ta']),
             'riesgo_total':V(g['riesgo']),'riesgo_fila':fila_de(ix,g['riesgo']),
             'ref_total':V(g['ref']),'ref_fila':fila_de(ix,g['ref'])}
        d['no_espec'] = max(0.0, T-d['m']-d['f'])
        d['clasificados'] = d['sanos']+d['enfermos']
        d['sin_clasificar'] = T-d['clasificados']
        d['consultas_declarado'] = S(g['consultas'])
        filas.append(d)
    out['grupos'] = filas
    for k in ['total','m','f','sanos','enfermos','primeras','sucesivas','enfermeria']:
        out[k] = float(sum(x[k] for x in filas))
    out['clasificados'] = out['sanos']+out['enfermos']
    out['sin_clasificar'] = out['total']-out['clasificados']
    morb, mg = {}, {}
    for g in GRUPOS_SIS03:
        tg = 0.0
        for c in hijos(ix,g['riesgo']):
            v = V(c)
            if v == 0: continue
            k = canon_morb(ix[c].actividad); morb[k] = morb.get(k,0)+v; tg += v
        mg[g['corto']] = tg
    out['morbilidad'] = dict(sorted(morb.items(), key=lambda x:-x[1]))
    out['morbilidad_grupo'] = mg; out['morbilidad_total'] = float(sum(morb.values()))
    refs = {}
    for g in GRUPOS_SIS03:
        for c in hijos(ix,g['ref']):
            v = V(c)
            if v == 0: continue
            k = canon_ref(ix[c].actividad); refs[k] = refs.get(k,0)+v
    out['referencias'] = dict(sorted(refs.items(), key=lambda x:-x[1]))
    out['referencias_total'] = float(sum(refs.values()))
    out['nutricion'] = {c: float(sum(x['nut'][c] for x in filas)) for c in NUT_CATS}
    out['tension']  = {c: float(sum(x['ta'][c] for x in filas)) for c in TA_CATS}
    prog = []
    for pref,nombre in PROGRAMAS:
        sub = df[[c==pref or c.startswith(pref+'.') for c in df.codigo]]
        hs = sub[~sub.es_padre]
        tot = float(hs.suma.sum()) if campo=='suma' else float(hs.total.fillna(0).sum())
        dec = float(sub[[c==pref for c in sub.codigo]].total.fillna(0).sum())
        prog.append({'programa':nombre,'prefijo':pref,'total':tot,'declarado':dec})
    out['programas'] = prog
    out['sub_0_6'] = {k:VF(c) for k,c in [('lt23','01.01.02'),('a2_6','01.01.03'),('lt1m','01.01.02.01'),
                                          ('m1_11','01.01.02.02'),('m12_23','01.01.02.03'),
                                          ('a2_3','01.01.03.01'),('a4_6','01.01.03.02')]}
    leaf = df[~df.es_padre]
    out['filas_hoja_con_dato'] = int((leaf.suma>0).sum())
    out['celdas_dia_con_dato'] = int(leaf.celdas.sum())
    out['carga_planilla'] = float(leaf.suma.sum())
    return out

def _fmt(x):
    if x is None or (isinstance(x,float) and np.isnan(x)): return 'Dato faltante'
    if isinstance(x,float) and float(x).is_integer(): return str(int(x))
    return str(x)

def auditar_hoja(hoja, mes_num=None, anio=None, es_cons=False):
    df = hoja['df']; ix = idx_hoja(hoja); H = []; lay = hoja['layout']
    def add(fila,cod,act,tipo,esp,reg,sev='Media'):
        e = None if (isinstance(esp,float) and np.isnan(esp)) else esp
        r = None if (isinstance(reg,float) and np.isnan(reg)) else reg
        dif = (r-e) if (isinstance(e,(int,float)) and isinstance(r,(int,float))) else None
        H.append({'Hoja':hoja['nombre'],'Fila':fila,'Codigo':cod,'Actividad':str(act)[:60],'Hallazgo':tipo,
                  'Esperado':_fmt(e),'Registrado':_fmt(r),
                  'Diferencia':'' if dif is None else ('%+d'%dif if float(dif).is_integer() else '%+.2f'%dif),
                  'Severidad':sev})
    lim = None
    if mes_num:
        lim = DIAS_MES[mes_num-1]
        if mes_num==2 and anio and str(anio).isdigit() and calendar.isleap(int(anio)): lim = 29
    for r in df.itertuples(index=False):
        tiene = (r.suma>0) or (not np.isnan(r.total) and r.total>0)
        if not es_cons:
            if not np.isnan(r.total) and r.suma!=r.total and tiene:
                add(r.fila,r.codigo,r.actividad,'TOTAL AH distinto de la suma de dias',r.suma,r.total)
            if not np.isnan(r.total) and r.total>0 and r.suma==0:
                add(r.fila,r.codigo,r.actividad,'Valor fantasma: total sin soporte diario',0,r.total,'Alta')
            if np.isnan(r.total) and r.suma>0:
                add(r.fila,r.codigo,r.actividad,'TOTAL AH vacio con dias cargados',r.suma,np.nan)
        if r.nivel<=2 and r.suma>0:
            add(r.fila,r.codigo,r.actividad,'Fila de seccion con dias cargados',0,r.suma)
        for i,v in enumerate(r.dias):
            if np.isnan(v): continue
            if v<0: add(r.fila,r.codigo,r.actividad,'Valor negativo en dia %d'%(i+1),'>=0',v,'Alta')
            elif not float(v).is_integer(): add(r.fila,r.codigo,r.actividad,'Valor decimal en dia %d'%(i+1),'entero',v)
            if lim and (i+1)>lim and v>0:
                add(r.fila,r.codigo,r.actividad,'Dia %d fuera de rango del mes (%d dias)'%(i+1,lim),0,v,'Alta')
        for d,c in lay['dias'].items():
            if c < len(r.raw):
                w = r.raw[c]
                if isinstance(w,str) and w.strip() and num(w) is None:
                    add(r.fila,r.codigo,r.actividad,'Texto en columna del dia %d'%d,'numero',w.strip()[:20],'Alta')
    for g in GRUPOS_SIS03:
        T = val(ix,g['total'])
        if T==0 and val(ix,g['total'],'total')==0: continue
        m,f = val(ix,g['m']), val(ix,g['f'])
        if m+f != T:
            add(fila_de(ix,g['m']),g['m'],act_de(ix,g['m']),'Masculino + Femenino vs total '+g['corto'],T,m+f,'Alta')
        for clave,cod,etq in [('dx',g['dx'],'Diagnosticos'),('nut',g['nut'],'Estado nutricional'),
                              ('ta',g['ta'],'Tension arterial'),('riesgo',g['riesgo'],'Riesgo biologico'),
                              ('ref',g['ref'],'Referencias')]:
            v = (suma_lista(ix,g['sanos'])+suma_lista(ix,g['enfermos'])) if clave=='dx' else val(ix,cod)
            if v != T: add(fila_de(ix,cod),cod,act_de(ix,cod),etq+' vs total '+g['corto'],T,v)
        cons = suma_lista(ix,g['primeras'])+suma_lista(ix,g['sucesivas'])
        if cons != T:
            add(fila_de(ix,g['consultas'][0]),g['consultas'][0],act_de(ix,g['consultas'][0]),
                'Primeras+sucesivas vs total '+g['corto'],T,cons)
        dt = dias_de(ix,g['total'])
        for cod,etq in [(g['dx'],'Diagnosticos'),(g['nut'],'Nutricion'),(g['ta'],'TA'),
                        (g['riesgo'],'Riesgo biologico'),(g['ref'],'Referencias')] + [(c,'Consultas') for c in g['consultas']]:
            dv = dias_de(ix,cod)
            for i in range(31):
                a = 0 if np.isnan(dv[i]) else dv[i]
                b = 0 if np.isnan(dt[i]) else dt[i]
                if a > b:
                    add(fila_de(ix,cod),cod,act_de(ix,cod),
                        '%s: dia %d excede total del grupo (%s)'%(etq,i+1,g['corto']),b,a,'Alta')
    ls = val(ix,'01.01.11.01'); c23 = val(ix,'01.01.02')
    if ls > c23:
        add(fila_de(ix,'01.01.11.01'),'01.01.11.01',act_de(ix,'01.01.11.01'),'Lactantes sanos > consultas <23 meses',c23,ls)
    for par,tot in [('01.03.02','01.03.01'),('01.03.05','01.03.04')]:
        if val(ix,par)>0 and val(ix,tot)==0:
            add(fila_de(ix,tot),tot,act_de(ix,tot),'Casos CED sin denominador de atenciones',val(ix,par),0)
    for k,etq in [('entidad','Entidad'),('municipio','Municipio'),('establecimiento','Establecimiento'),
                  ('medico','Nombre del medico'),('mes','Mes'),('anio','Anio')]:
        if not hoja['meta'].get(k):
            add(hoja['header_row'],'-','Encabezado','Metadato faltante: '+etq,'texto',None,'Baja')
    return H

def auditar_libro(hp, md, cons_name=None):
    H = []
    for n,h in hp.items():
        H += auditar_hoja(h, md.get(n), h['meta'].get('anio') or None, es_cons=(n==cons_name))
    return pd.DataFrame(H)

def cruzar_consolidado(hp, nc='CONSOLIDADO', incluir_dias=False):
    if not nc or nc not in hp: return pd.DataFrame()
    cons = hp[nc]['df'].set_index('codigo'); meses = [h for n,h in hp.items() if n!=nc]; filas = []
    for cod in cons.index:
        ac = cons.loc[cod,'total']; ac = 0.0 if np.isnan(ac) else float(ac)
        am = sm = 0.0
        for h in meses:
            r = h['df'][h['df'].codigo==cod]
            if len(r):
                t = r.iloc[0].total
                am += 0.0 if np.isnan(t) else float(t)
                sm += float(r.iloc[0].suma)
        sc = float(cons.loc[cod,'suma']); act = str(cons.loc[cod,'actividad'])[:60]
        if ac != am:
            filas.append({'Codigo':cod,'Actividad':act,'Chequeo':'AH consolidado vs suma AH mensuales',
                          'Consolidado':ac,'Meses':am,'Diferencia':ac-am})
        if incluir_dias and sc != sm:
            filas.append({'Codigo':cod,'Actividad':act,'Chequeo':'Dias consolidado vs suma dias mensuales',
                          'Consolidado':sc,'Meses':sm,'Diferencia':sc-sm})
    return pd.DataFrame(filas)

# ============ TABLAS / INFORMES / EXPORTACION ============
def df_grupos(a):
    rows = []
    for g in a['grupos']:
        rows.append({'Grupo etario':g['grupo'],'Codigo':g['codigo'],'Fila':g['fila'],'Total':int(g['total']),
                     'Masculino':int(g['m']),'Femenino':int(g['f']),'Sexo no espec.':int(g['no_espec']),
                     '1eras consultas':int(g['primeras']),'Sucesivas':int(g['sucesivas']),
                     'Enfermeria (aparte)':int(g['enfermeria']),'Sanos':int(g['sanos']),
                     'Enfermos':int(g['enfermos']),'Sin clasificar':int(g['sin_clasificar'])})
    d = pd.DataFrame(rows)
    tot = {'Grupo etario':'TOTAL','Codigo':'-','Fila':None,'Total':int(a['total']),'Masculino':int(a['m']),
           'Femenino':int(a['f']),'Sexo no espec.':int(a['total']-a['m']-a['f']),
           '1eras consultas':int(a['primeras']),'Sucesivas':int(a['sucesivas']),
           'Enfermeria (aparte)':int(a['enfermeria']),'Sanos':int(a['sanos']),
           'Enfermos':int(a['enfermos']),'Sin clasificar':int(a['sin_clasificar'])}
    return pd.concat([d, pd.DataFrame([tot])], ignore_index=True)

def df_dict(d, c1='Categoria', c2='Total'):
    return pd.DataFrame([{c1:k, c2:int(v)} for k,v in d.items()])

def df_perfil(a):
    rows = []
    for g in a['grupos']:
        rows.append({'Grupo':g['corto'],'Total':int(g['total']),'Nutricion normal':int(g['nut']['Normal']),
                     'Nutricion alterada':int(g['nut_total']-g['nut']['Normal']),'TA normal':int(g['ta']['Normal']),
                     'Hipertenso':int(g['ta']['Hipertenso']),'Hipotenso':int(g['ta']['Hipotenso']),
                     'Sanos':int(g['sanos']),'Enfermos':int(g['enfermos']),'Sin clasificar':int(g['sin_clasificar']),
                     'Riesgo biologico':int(g['riesgo_total']),'Referencias':int(g['ref_total'])})
    return pd.DataFrame(rows)

def md_tabla(df):
    cols = list(df.columns)
    out = ['| '+' | '.join(map(str,cols))+' |', '|'+'|'.join(['---']*len(cols))+'|']
    for _,r in df.iterrows():
        out.append('| '+' | '.join('' if pd.isna(r[c]) else str(r[c]) for c in cols)+' |')
    return '\n'.join(out)

def informe_mes_md(a, aud_mes, nombre_mes, anio):
    m = a['meta']; L = []
    L.append(f"# SIS-03/PRO - Informe de {nombre_mes} {anio or m.get('anio','(anio no declarado)')}")
    L.append(f"**Entidad:** {m.get('entidad') or 'Dato faltante'} | **Municipio:** {m.get('municipio') or 'Dato faltante'}")
    L.append(f"**Establecimiento:** {m.get('establecimiento') or 'Dato faltante'}")
    L.append(f"**Medico:** {m.get('medico') or m.get('profesional') or 'Dato faltante'} | **Enfermeria:** {m.get('enfermera') or 'Dato faltante'}")
    dias = a['dias_con_carga']
    L.append(f"**Dias con carga:** {', '.join(map(str,dias)) if dias else 'ninguno'} ({len(dias)} dias)")
    if a['total'] == 0:
        L.append("\n## Hoja en blanco\nNo hay registros en el mes. No es posible calcular produccion ni morbilidad.")
        return '\n'.join(L)
    L.append("\n## 1. Produccion por grupo etario y sexo\n"+md_tabla(df_grupos(a)))
    s = a['sub_0_6']
    L.append(f"\nDesglose 0 a <7 anos: <23 meses {int(s['lt23'])} (<1m {int(s['lt1m'])}, 1-11m {int(s['m1_11'])}, 12-23m {int(s['m12_23'])}); "
             f"2-6 anos {int(s['a2_6'])} (2-3a {int(s['a2_3'])}, 4-6a {int(s['a4_6'])}).")
    L.append("\n## 2. Perfil clinico\n"+md_tabla(df_perfil(a)))
    L.append("\n## 3. Morbilidad (riesgo biologico homologado)\n"+(md_tabla(df_dict(a['morbilidad'],'Grupo de enfermedad','Casos')) if a['morbilidad'] else 'Sin registros.'))
    L.append(f"\nTotal eventos de riesgo biologico: {int(a['morbilidad_total'])}")
    L.append("\n## 4. Referencias\n"+(md_tabla(df_dict(a['referencias'],'Servicio','Referencias')) if a['referencias'] else 'Sin referencias.'))
    L.append(f"\nTotal referencias: {int(a['referencias_total'])}")
    cero = [p['programa'] for p in a['programas'] if p['total']==0]
    L.append("\n## 5. Programas\nCon actividad: "+(', '.join(f"{p['programa']}={int(p['total'])}" for p in a['programas'] if p['total']>0) or 'ninguno'))
    L.append("\nEn cero: "+', '.join(cero))
    L.append("\n## 6. Auditoria del mes\n")
    if aud_mes is None or len(aud_mes)==0: L.append('Sin hallazgos.')
    else: L.append(md_tabla(aud_mes[['Fila','Codigo','Hallazgo','Esperado','Registrado','Diferencia','Severidad']]))
    L.append("\n## 7. Lectura del mes")
    L.append(f"- Se registraron {int(a['total'])} atenciones en {len(dias)} dias; promedio {a['total']/max(1,len(dias)):.1f} por dia con carga.")
    L.append(f"- {int(a['f'])} mujeres ({a['f']/a['total']*100:.1f}%) y {int(a['m'])} hombres ({a['m']/a['total']*100:.1f}%).")
    if a['sin_clasificar']>0: L.append(f"- {int(a['sin_clasificar'])} atenciones sin clasificacion sano/enfermo: limita el calculo de morbilidad.")
    if a['primeras']>0 and a['sucesivas']==0: L.append("- Todas las consultas figuran como primeras: no hay seguimiento registrado.")
    L.append("- Los eventos de riesgo biologico son diagnosticos, no pacientes: no deben sumarse a las atenciones.")
    return '\n'.join(L)

def informe_anual_md(C, resumen, cruces):
    L = ["# SIS-03/PRO - Consolidado anual","## 1. Resumen mensual", md_tabla(resumen)]
    L.append(f"\n**Gran total de atenciones:** {int(C['total'])}")
    L.append("\n## 2. Grupo etario y sexo\n"+md_tabla(df_grupos(C)))
    L.append("\n## 3. Diagnostico general\n"+md_tabla(df_perfil(C)))
    L.append("\n## 4. Morbilidad homologada del ano\n"+md_tabla(df_dict(C['morbilidad'],'Grupo de enfermedad','Casos')))
    L.append(f"\nTotal eventos: {int(C['morbilidad_total'])} para {int(C['total'])} atenciones.")
    L.append("\n## 5. Estado nutricional\n"+md_tabla(df_dict(C['nutricion'],'Categoria','Personas')))
    L.append("\n## 6. Tension arterial\n"+md_tabla(df_dict(C['tension'],'Categoria','Personas')))
    L.append("\n## 7. Referencias\n"+md_tabla(df_dict(C['referencias'],'Servicio','Referencias')))
    L.append("\n## 8. Programas\n"+md_tabla(pd.DataFrame(C['programas'])))
    if cruces is not None and len(cruces):
        L.append("\n## 9. Diferencias consolidado vs meses\n"+md_tabla(cruces.head(60)))
    return '\n'.join(L)

def construir_excel(resumen, grupos, perfil, morb, refs, nut, ta, prog, aud, cruces):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as w:
        resumen.to_excel(w,'Resumen mensual',index=False)
        grupos.to_excel(w,'Grupo etario y sexo',index=False)
        perfil.to_excel(w,'Perfil clinico',index=False)
        morb.to_excel(w,'Morbilidad',index=False)
        refs.to_excel(w,'Referencias',index=False)
        nut.to_excel(w,'Nutricion',index=False)
        ta.to_excel(w,'Tension arterial',index=False)
        prog.to_excel(w,'Programas',index=False)
        if aud is not None and len(aud): aud.to_excel(w,'Auditoria',index=False)
        if cruces is not None and len(cruces): cruces.to_excel(w,'Consolidado vs meses',index=False)
    return bio.getvalue()

# ============ FOTO -> JSON -> VALIDACION ============
PROMPT_SIS03 = """Eres un transcriptor y auditor de instrumentos SIS-03/PRO (Tabulador Diario de Actividades de Programas de Salud, Medicina General y Familiar).
Trabajas sobre la FOTO de una planilla mensual. No inventes datos.

REGLAS DE LECTURA
1. Identifica el encabezado: Entidad, Municipio, Establecimiento, Nombre del Medico, Mes, Ano y el bloque NOMBRE MEDICO O PROFESIONAL / ENFERMERA / AMS-ACAPS. Si esta vacio escribe null.
2. La tabla tiene: columna A = Codigo, columna B = Actividad, columnas C..AG = dias 1..31, columna AH = TOTAL SIS O4.
3. Recorre TODAS las filas con codigo jerarquico (01., 01.01., 01.01.01., ...). Respeta el codigo exacto.
4. Celda vacia = null. Cero escrito = 0. No confundas vacio con cero.
5. Si un valor es ilegible, escribe null y agrega el codigo a "ilegibles".
6. No completes totales: transcribe AH tal como aparece, aunque no cuadre con los dias.

SALIDA: unicamente JSON valido con esta forma
{"meta":{"entidad":...,"municipio":...,"establecimiento":...,"medico":...,"mes":...,"anio":...},
 "filas":[{"fila":123,"codigo":"02.00.01","actividad":"Total Adultos","dias":[null,...31 valores...],"total":34}],
 "ilegibles":["..."],"observaciones":"..."}
No agregues comentarios fuera del JSON."""

def llamar_vision(base_url, model, api_key, imagenes_b64, instruccion, timeout=180):
    import requests
    contenido = [{"type":"text","text":instruccion}]
    for b in imagenes_b64:
        contenido.append({"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}})
    payload = {"model":model,"temperature":0,
               "messages":[{"role":"system","content":PROMPT_SIS03},{"role":"user","content":contenido}]}
    r = requests.post(base_url.rstrip('/')+"/chat/completions",
                      headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},
                      json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def extraer_json(texto):
    import json as _json
    t = texto.strip()
    t = re.sub(r'^```(json)?','',t).strip(); t = re.sub(r'```$','',t).strip()
    i,j = t.find('{'), t.rfind('}')
    if i>=0 and j>i: t = t[i:j+1]
    return _json.loads(t)

def json_a_hoja(datos, nombre='FOTO'):
    filas = []
    for k,f in enumerate(datos.get('filas',[])):
        cod = norm_code(str(f.get('codigo',''))) or str(f.get('codigo','')).strip()
        if not cod: continue
        ds = [num(x) for x in (f.get('dias') or [])][:31]
        ds = ds + [np.nan]*(31-len(ds))
        tot = num(f.get('total'))
        filas.append({'fila':int(f.get('fila') or k+1),'codigo':cod,'actividad':str(f.get('actividad','')),
                      'nivel':cod.count('.')+1,'dias':ds,'total':tot,'suma':float(np.nansum(ds)),
                      'celdas':int(sum(1 for v in ds if not np.isnan(v) and v>0)),
                      'raw':[cod,str(f.get('actividad',''))]+ds+[tot]})
    if not filas: return None
    df = pd.DataFrame(filas); codes = set(df.codigo)
    df['es_padre'] = [any(o!=c and o.startswith(c+'.') for o in codes) for c in df.codigo]
    meta = {k:(v if v else '') for k,v in (datos.get('meta') or {}).items()}
    for k in ['entidad','municipio','establecimiento','medico','mes','anio','profesional','enfermera','ams']:
        meta.setdefault(k,'')
    return {'nombre':nombre,'df':df,'meta':meta,'header_row':10,
            'layout':{'header_row':9,'col_code':0,'col_label':1,'dias':{d:d+1 for d in range(1,32)},'col_total':33},
            'nrows':len(df)+10}

# ============ HELPERS DE CARGA SIS-03 ============
def consolidar_meses(lista):
    if not lista: return None
    import copy
    C = copy.deepcopy(lista[0]); C['nombre'] = 'CONSOLIDADO (suma de meses)'; C['modo'] = 'dias'
    C['meta'] = {'entidad':lista[0]['meta'].get('entidad',''),'municipio':lista[0]['meta'].get('municipio',''),
                 'establecimiento':lista[0]['meta'].get('establecimiento',''),'medico':'','mes':'ANUAL',
                 'anio':lista[0]['meta'].get('anio','')}
    claves = ['total','m','f','sanos','enfermos','primeras','sucesivas','enfermeria','clasificados','sin_clasificar',
              'morbilidad_total','referencias_total','filas_hoja_con_dato','celdas_dia_con_dato','carga_planilla']
    for k in claves: C[k] = float(sum(a.get(k,0) for a in lista))
    for i,g in enumerate(C['grupos']):
        for k in ['total','total_ah','m','f','primeras','sucesivas','enfermeria','sanos','enfermos','dx_declarado',
                  'nut_total','ta_total','riesgo_total','ref_total','no_espec','clasificados','sin_clasificar','consultas_declarado']:
            g[k] = float(sum(a['grupos'][i].get(k,0) for a in lista))
        for cat in NUT_CATS: g['nut'][cat] = float(sum(a['grupos'][i]['nut'][cat] for a in lista))
        for cat in TA_CATS:  g['ta'][cat]  = float(sum(a['grupos'][i]['ta'][cat] for a in lista))
    for clave in ['morbilidad','referencias','nutricion','tension','sub_0_6','morbilidad_grupo']:
        agg = {}
        for a in lista:
            for k,v in a.get(clave,{}).items(): agg[k] = agg.get(k,0)+v
        C[clave] = dict(sorted(agg.items(), key=lambda x:-x[1])) if clave in ('morbilidad','referencias') else agg
    for i,p in enumerate(C['programas']):
        p['total'] = float(sum(a['programas'][i]['total'] for a in lista))
        p['declarado'] = float(sum(a['programas'][i]['declarado'] for a in lista))
    C['dias_con_carga'] = sorted({d for a in lista for d in a['dias_con_carga']})
    return C

def cargar_sis03(file):
    hojas = leer_libro(file)
    if not es_tabulador(hojas):
        return None,'El archivo no tiene la estructura SIS-03/PRO (Codigo / Actividad / dias 1-31 / TOTAL SIS O4).'
    H = {}
    for n,m in hojas:
        p = parse_hoja(n,m)
        if p is not None: H[n] = p
    if not H: return None,'No se encontraron filas con codigo SIS-03/PRO.'
    md = {}
    for n,p in H.items():
        t = (p['meta'].get('mes') or '').strip().upper()
        if t in MESES: md[n] = MESES.index(t)+1
        elif n.strip().upper() in MESES: md[n] = MESES.index(n.strip().upper())+1
    cons = next((n for n in H if 'CONSOL' in n.upper()), None)
    A = {n: analizar_hoja(p) for n,p in H.items()}
    orden = sorted([n for n in H if n in md], key=lambda n: md[n])
    C = analizar_hoja(H[cons], modo='ah') if cons else consolidar_meses([A[n] for n in orden])
    aud = auditar_libro(H, md, cons)
    cruces = cruzar_consolidado(H, cons) if cons else pd.DataFrame()
    return {'hojas':H,'analisis':A,'meses':md,'orden':orden,'cons':C,'cons_name':cons,
            'aud':aud,'cruces':cruces},'OK'

def tabla_resumen_mensual(pack):
    rows = []
    for n in pack['orden']:
        a = pack['analisis'][n]
        rows.append({'Mes':n,'Dias con carga':len(a['dias_con_carga']),'Atenciones':int(a['total']),
                     'Masculino':int(a['m']),'Femenino':int(a['f']),'Sanos':int(a['sanos']),
                     'Enfermos':int(a['enfermos']),'Sin clasificar':int(a['sin_clasificar']),
                     'Riesgo biologico':int(a['morbilidad_total']),'Referencias':int(a['referencias_total']),
                     'Estado':'Sin datos' if a['total']==0 else ('Revisar' if a['sin_clasificar']>0 else 'Consistente')})
    d = pd.DataFrame(rows)
    if len(d):
        tot = {'Mes':'TOTAL ANO','Dias con carga':int(d['Dias con carga'].sum())}
        for c in d.columns[2:-1]: tot[c] = int(d[c].sum())
        tot['Estado'] = ''
        d = pd.concat([d, pd.DataFrame([tot])], ignore_index=True)
    return d

def _secret(k, d=''):
    try: return st.secrets.get(k, d)
    except Exception: return d

def hay_tres():
    return all(k in st.session_state.dataframes and st.session_state.dataframes[k] is not None
               for k in ['SISPRO','EPI12','EPI15'])

# ============ INTERFAZ ============
if 'dataframes' not in st.session_state: st.session_state.dataframes = {}
if 'infos' not in st.session_state: st.session_state.infos = {}

with st.sidebar:
    st.markdown("### Dos formatos SISPRO")
    st.markdown("**Paciente a paciente** (columnas EDAD, FECHA_ATENCION, NUMERO_DOCUMENTO): pestañas 1 a 3.")
    st.markdown("**Tabulador SIS-03/PRO** (Codigo / Actividad / dias 1-31 / TOTAL SIS O4): pestañas 4 a 8.")
    st.markdown("---")
    st.caption("Los totales del tabulador se calculan sumando los dias; la columna AH se contrasta, no se copia.")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Carga de Archivos","Validación por Mes","Validación por Periodo",
    "SIS-03 mes a mes","Consolidado anual SIS-03","Auditoría","Foto → Informe (IA)","Exportar"])

with tab1:
    st.header("Carga de Archivos SISPRO, EPI12 y EPI15")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("SISPRO")
        file_sispro = st.file_uploader("Subir archivo SISPRO", type=['xls','xlsx'], key="sispro")
        if file_sispro:
            df, info = analizar_archivo(file_sispro, "SISPRO")
            if df is None: st.error(info)
            else:
                st.session_state.dataframes['SISPRO'] = df; st.session_state.infos['SISPRO'] = info
                st.success(f"SISPRO cargado: {info['filas']} filas")
                if 'EDAD' not in df.columns and any('ACTIVIDAD' in c for c in df.columns):
                    st.warning("Este archivo parece un tabulador SIS-03/PRO. Use la pestaña 'SIS-03 mes a mes'.")
    with col2:
        st.subheader("EPI12")
        file_epi12 = st.file_uploader("Subir archivo EPI12", type=['xls','xlsx'], key="epi12")
        if file_epi12:
            df, info = analizar_archivo(file_epi12, "EPI12")
            if df is None: st.error(info)
            else:
                st.session_state.dataframes['EPI12'] = df; st.session_state.infos['EPI12'] = info
                st.success(f"EPI12 cargado: {info['filas']} filas")
    with col3:
        st.subheader("EPI15")
        file_epi15 = st.file_uploader("Subir archivo EPI15", type=['xls','xlsx'], key="epi15")
        if file_epi15:
            df, info = analizar_archivo(file_epi15, "EPI15")
            if df is None: st.error(info)
            else:
                st.session_state.dataframes['EPI15'] = df; st.session_state.infos['EPI15'] = info
                st.success(f"EPI15 cargado: {info['filas']} filas")

with tab2:
    st.header("Validación por Mes")
    if hay_tres():
        meses_nombres = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        col_m1, col_m2 = st.columns(2)
        with col_m1: mes_sel = st.selectbox("Seleccione el Mes", meses_nombres)
        with col_m2: ano_sel = st.number_input("Año", min_value=2020, max_value=2030, value=2026)
        mes_idx = meses_nombres.index(mes_sel)+1
        res, err = validar_mes_completo(st.session_state.dataframes['SISPRO'],
                                        st.session_state.dataframes['EPI12'],
                                        st.session_state.dataframes['EPI15'], ano_sel, mes_idx)
        if res:
            st.subheader(f"Resultados para {mes_sel} {ano_sel}")
            st.markdown("### 1. SISPRO (Grupos Etarios)")
            st.dataframe(pd.DataFrame(list(res['sispro']['grupos'].items()), columns=['Categoría','Total']), use_container_width=True)
            st.write(f"**Total SISPRO del Mes:** {res['sispro']['total']:,}")
            st.markdown("### 2. EPI12 (Pacientes Atendidos por Semanas)")
            if res['epi12']['totales_semanales']:
                st.dataframe(pd.DataFrame(list(res['epi12']['totales_semanales'].items()), columns=['Semana','Total Pacientes']), use_container_width=True)
            st.write(f"**Total EPI12 del Mes:** {res['epi12']['total']:,}")
            st.markdown("### 3. EPI15 (Total Causas de Consulta)")
            st.info(f"**Total Causas de Consulta en el Mes:** {res['epi15']['total']:,}")
            if res['todos_coinciden']:
                st.markdown('<div class="match-box"><b>¡Coincidencia perfecta entre los reportes!</b></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="discrepancy-box"><b>Se detectaron discrepancias que requieren revisión de errores.</b></div>', unsafe_allow_html=True)
                for e in res['errores']: st.warning(e['descripcion'])
        else:
            st.warning(err or "No hay datos para este mes.")
    else:
        st.info("Cargue los tres archivos (SISPRO, EPI12 y EPI15) en la pestaña 'Carga de Archivos'.")

with tab3:
    st.header("Validación por Periodo y Total General Anual")
    if hay_tres():
        resultados_periodo = validar_periodo(st.session_state.dataframes['SISPRO'],
                                             st.session_state.dataframes['EPI12'],
                                             st.session_state.dataframes['EPI15'], 2026,1,2026,12)
        if resultados_periodo:
            resumen_Anual = [{'Mes':r['mes'],'Total SISPRO':r['sispro']['total'],'Total EPI12':r['epi12']['total'],
                              'Total EPI15':r['epi15']['total'],'Estado':'OK' if r['todos_coinciden'] else 'Revisar Error'}
                             for r in resultados_periodo]
            st.dataframe(pd.DataFrame(resumen_Anual), use_container_width=True)
            g_sispro = sum(r['sispro']['total'] for r in resultados_periodo)
            g_epi12  = sum(r['epi12']['total'] for r in resultados_periodo)
            g_epi15  = sum(r['epi15']['total'] for r in resultados_periodo)
            st.markdown("---"); st.subheader("Total General Anual (Enero a Diciembre)")
            ca, cb, cc = st.columns(3)
            ca.metric("Gran Total SISPRO", f"{g_sispro:,}")
            cb.metric("Gran Total EPI12", f"{g_epi12:,}", delta=f"{g_epi12-g_sispro:+,}")
            cc.metric("Gran Total EPI15", f"{g_epi15:,}", delta=f"{g_epi15-g_sispro:+,}")
        else:
            st.warning("No se encontraron registros suficientes para procesar el periodo anual.")
    else:
        st.info("Cargue los archivos en la primera pestaña para visualizar la consolidación anual.")

with tab4:
    st.header("SIS-03/PRO - Informe mes a mes (tabulador diario)")
    st.caption("Cargue el libro SIS PRO AÑO 2026 (12 meses + consolidado). Se suman los dias 1-31 y se contrasta con TOTAL SIS O4.")
    f03 = st.file_uploader("Libro SIS-03/PRO (.xls / .xlsx)", type=['xls','xlsx'], key='sis03')
    if f03 is not None:
        with st.spinner("Procesando tabulador..."):
            pack, msg = cargar_sis03(f03)
        if pack is None: st.error(msg)
        else:
            st.session_state['sis03'] = pack
            st.success(f"{len(pack['hojas'])} hojas leidas | {len(pack['orden'])} meses detectados | consolidado: {pack['cons_name'] or 'calculado por suma'}")
    pack = st.session_state.get('sis03')
    if pack:
        nombre = st.selectbox("Mes a informar", pack['orden'] if pack['orden'] else list(pack['hojas'].keys()))
        a = pack['analisis'][nombre]; m = a['meta']
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Atenciones del mes", int(a['total']))
        c2.metric("Masculino", int(a['m'])); c3.metric("Femenino", int(a['f']))
        c4.metric("Dias con carga", len(a['dias_con_carga']))
        st.markdown(f"**Entidad:** {m.get('entidad') or 'Dato faltante'} | **Municipio:** {m.get('municipio') or 'Dato faltante'} | "
                    f"**Establecimiento:** {m.get('establecimiento') or 'Dato faltante'} | "
                    f"**Medico:** {m.get('medico') or m.get('profesional') or 'Dato faltante'}")
        st.write("**Dias con carga:**", ', '.join(map(str,a['dias_con_carga'])) or 'ninguno')
        if a['total'] == 0:
            st.markdown('<div class="warning-box"><b>Hoja en blanco:</b> no hay produccion registrada en el mes.</div>', unsafe_allow_html=True)
        else:
            st.markdown("### 1. Grupo etario, sexo y tipo de consulta")
            st.dataframe(df_grupos(a), use_container_width=True)
            s = a['sub_0_6']
            st.caption(f"0 a <7 anos: <23 meses {int(s['lt23'])} | 2-6 anos {int(s['a2_6'])} "
                       f"(<1m {int(s['lt1m'])}, 1-11m {int(s['m1_11'])}, 12-23m {int(s['m12_23'])}, 2-3a {int(s['a2_3'])}, 4-6a {int(s['a4_6'])})")
            st.markdown("### 2. Perfil clinico"); st.dataframe(df_perfil(a), use_container_width=True)
            st.markdown("### 3. Morbilidad (riesgo biologico homologado)")
            if a['morbilidad']:
                dm = df_dict(a['morbilidad'],'Grupo de enfermedad','Casos')
                st.dataframe(dm, use_container_width=True); st.bar_chart(dm.set_index('Grupo de enfermedad'))
            st.markdown("### 4. Referencias")
            if a['referencias']: st.dataframe(df_dict(a['referencias'],'Servicio','Referencias'), use_container_width=True)
            st.markdown("### 5. Programas"); st.dataframe(pd.DataFrame(a['programas']), use_container_width=True)
        aud = pack['aud']; am = aud[aud.Hoja==nombre] if len(aud) else aud
        st.markdown("### 6. Auditoria del mes")
        if len(am): st.dataframe(am[['Fila','Codigo','Actividad','Hallazgo','Esperado','Registrado','Diferencia','Severidad']], use_container_width=True)
        else: st.success("Sin hallazgos en el mes.")
        md_txt = informe_mes_md(a, am, nombre, m.get('anio'))
        with st.expander("Ver informe redactado (Markdown)"): st.markdown(md_txt)
        st.download_button("Descargar informe del mes (.md)", md_txt.encode('utf-8'),
                           file_name=f"SIS03_{nombre}.md", mime='text/markdown')

with tab5:
    st.header("Consolidado anual SIS-03/PRO")
    pack = st.session_state.get('sis03')
    if not pack: st.info("Cargue el tabulador en la pestaña 'SIS-03 mes a mes'.")
    else:
        C = pack['cons']; resumen = tabla_resumen_mensual(pack)
        st.markdown("### Resumen mensual"); st.dataframe(resumen, use_container_width=True)
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Gran total", int(C['total'])); c2.metric("Masculino", int(C['m'])); c3.metric("Femenino", int(C['f']))
        c4.metric("Sanos", int(C['sanos'])); c5.metric("Enfermos", int(C['enfermos']))
        st.metric("Atenciones sin clasificacion sano/enfermo", int(C['sin_clasificar']),
                  delta=(f"{C['sin_clasificar']/C['total']*100:.1f}% del total" if C['total'] else None), delta_color="inverse")
        st.markdown("### Grupo etario y sexo (ano)"); st.dataframe(df_grupos(C), use_container_width=True)
        st.markdown("### Diagnostico general del ano"); st.dataframe(df_perfil(C), use_container_width=True)
        st.markdown("### Morbilidad homologada del ano")
        dmo = df_dict(C['morbilidad'],'Grupo de enfermedad','Casos')
        st.dataframe(dmo, use_container_width=True)
        if len(dmo): st.bar_chart(dmo.set_index('Grupo de enfermedad'))
        ca, cb = st.columns(2)
        with ca:
            st.markdown("### Estado nutricional"); st.dataframe(df_dict(C['nutricion'],'Categoria','Personas'), use_container_width=True)
        with cb:
            st.markdown("### Tension arterial"); st.dataframe(df_dict(C['tension'],'Categoria','Personas'), use_container_width=True)
        st.markdown("### Referencias del ano"); st.dataframe(df_dict(C['referencias'],'Servicio','Referencias'), use_container_width=True)
        st.markdown("### Programas"); st.dataframe(pd.DataFrame(C['programas']), use_container_width=True)
        if len(pack['cruces']):
            st.markdown("### Diferencias: hoja CONSOLIDADO vs suma de meses")
            st.dataframe(pack['cruces'], use_container_width=True)
        md_anual = informe_anual_md(C, resumen, pack['cruces'])
        with st.expander("Ver informe anual (Markdown)"): st.markdown(md_anual)
        st.download_button("Descargar informe anual (.md)", md_anual.encode('utf-8'),
                           file_name="SIS03_informe_anual.md", mime='text/markdown')
        st.session_state['export'] = {'resumen':resumen,'grupos':df_grupos(C),'perfil':df_perfil(C),'morb':dmo,
                                      'refs':df_dict(C['referencias'],'Servicio','Referencias'),
                                      'nut':df_dict(C['nutricion'],'Categoria','Personas'),
                                      'ta':df_dict(C['tension'],'Categoria','Personas'),
                                      'prog':pd.DataFrame(C['programas']),'aud':pack['aud'],'cruces':pack['cruces']}

with tab6:
    st.header("Auditoria de calidad del tabulador")
    pack = st.session_state.get('sis03')
    if not pack: st.info("Cargue el tabulador en la pestaña 'SIS-03 mes a mes'.")
    else:
        aud = pack['aud']
        if not len(aud): st.success("Sin hallazgos.")
        else:
            c1,c2 = st.columns(2)
            h = c1.selectbox("Hoja", ['(todas)']+sorted(aud.Hoja.unique().tolist()))
            s = c2.selectbox("Severidad", ['(todas)','Alta','Media','Baja'])
            f = aud.copy()
            if h != '(todas)': f = f[f.Hoja==h]
            if s != '(todas)': f = f[f.Severidad==s]
            st.write(f"{len(f)} hallazgos")
            st.dataframe(f, use_container_width=True, height=460)
            st.download_button("Descargar auditoria (.csv)", f.to_csv(index=False).encode('utf-8'),
                               file_name="auditoria_sis03.csv", mime='text/csv')
            st.markdown("### Resumen por tipo de hallazgo")
            st.dataframe(aud.Hallazgo.str.replace(r'\d+','N',regex=True).value_counts()
                         .rename_axis('Tipo').reset_index(name='Casos'), use_container_width=True)

with tab7:
    st.header("Foto de la planilla → informe (IA + validacion en Python)")
    st.caption("Paso 1: el modelo de vision transcribe la foto a JSON. Paso 2: Python valida y calcula. Paso 3: se redacta el informe con datos verificados.")
    with st.expander("Configuracion del modelo de vision"):
        base  = st.text_input("Base URL (compatible OpenAI)", value="https://api.openai.com/v1")
        model = st.text_input("Modelo con vision", value="gpt-4o-mini")
        key   = st.text_input("API Key", type="password", value=_secret("OPENAI_API_KEY",""))
        st.caption("La clave se usa solo en esta sesion; no se guarda en el archivo.")
    imgs = st.file_uploader("Fotos de la planilla (una o varias)", type=['png','jpg','jpeg','webp'], accept_multiple_files=True)
    if imgs and st.button("Transcribir foto a JSON"):
        if not key: st.error("Falta la API Key.")
        else:
            b64 = [base64.b64encode(i.getvalue()).decode() for i in imgs]
            try:
                with st.spinner("Leyendo la planilla..."):
                    txt = llamar_vision(base, model, key, b64,
                                        "Transcribe la planilla completa de las imagenes adjuntas siguiendo las reglas del sistema.")
                st.session_state['json_foto'] = txt
                st.success("Transcripcion recibida.")
            except Exception as e:
                st.error(f"Fallo la llamada al modelo: {e}")
    st.markdown("#### JSON transcrito (editable / pegable)")
    editor = st.text_area("Pegue o edite aqui el JSON", value=st.session_state.get('json_foto',''), height=260)
    if st.button("Validar JSON y generar informe"):
        try:
            datos = extraer_json(editor); hoja = json_a_hoja(datos)
            if hoja is None: st.error("El JSON no contiene filas con codigo valido.")
            else:
                mes_txt = (hoja['meta'].get('mes') or '').strip().upper()
                mes_num = MESES.index(mes_txt)+1 if mes_txt in MESES else None
                a = analizar_hoja(hoja)
                h = auditar_hoja(hoja, mes_num, hoja['meta'].get('anio'))
                st.dataframe(df_grupos(a), use_container_width=True)
                st.dataframe(df_perfil(a), use_container_width=True)
                if h: st.dataframe(pd.DataFrame(h), use_container_width=True)
                inf = informe_mes_md(a, pd.DataFrame(h), mes_txt or 'MES', hoja['meta'].get('anio'))
                st.markdown(inf)
                st.download_button("Descargar informe (.md)", inf.encode('utf-8'),
                                   file_name="informe_foto.md", mime='text/markdown')
        except Exception as e:
            st.error(f"No se pudo validar: {e}")
    with st.expander("Ver prompt de sistema usado"): st.code(PROMPT_SIS03, language='text')

with tab8:
    st.header("Exportar resultados")
    ex = st.session_state.get('export')
    if not ex: st.info("Genere primero el consolidado anual (pestaña 'Consolidado anual SIS-03').")
    else:
        data = construir_excel(ex['resumen'], ex['grupos'], ex['perfil'], ex['morb'], ex['refs'],
                               ex['nut'], ex['ta'], ex['prog'], ex['aud'], ex['cruces'])
        st.download_button("Descargar libro Excel consolidado", data, file_name="SIS03_consolidado_anual.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.markdown('<div class="info-box">El Excel incluye: resumen mensual, grupo etario y sexo, perfil clinico, morbilidad, referencias, nutricion, tension arterial, programas, auditoria y cruces consolidado vs meses.</div>', unsafe_allow_html=True)
