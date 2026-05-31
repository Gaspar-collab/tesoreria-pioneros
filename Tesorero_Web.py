import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import os
import io
import unicodedata
import pandas as pd

# ==========================================
# 1. CONFIGURACIÓN DE IDENTIDAD (DINÁMICA)
# ==========================================
# Sacamos la identidad de la unidad de los secretos
NOM_UNIDAD = st.secrets["config"].get("nombre_unidad", "Manada")

# 🐾 PROCESAMIENTO DEL EMOJI: Soporta Emojis de texto y Base64 personalizado
emoji_raw = st.secrets["config"].get("emoji", "🔥")

if emoji_raw.startswith("data:image"):
    EMOJI_UNIDAD = f"<img src='{emoji_raw}' width='26' style='vertical-align: middle; margin-right: 6px;'>"
else:
    EMOJI_UNIDAD = emoji_raw

# 🎭 FILTRO DE TEXTO: ¿Niños o Jóvenes? Depende de la unidad
if NOM_UNIDAD.lower() == "manada":
    TEXTO_INDIVIDUAL = "niño"
    TEXTO_PLURAL = "niños"
else:
    TEXTO_INDIVIDUAL = "joven"
    TEXTO_PLURAL = "jóvenes"

# 🚨 CONFIGURACIÓN DE PÁGINA AL INICIO 
# Nota: page_icon no soporta HTML, por lo que le pasamos un emoji de respaldo si es Base64
icono_pestana = "🔥" if emoji_raw.startswith("data:image") else emoji_raw
st.set_page_config(page_title=f"Tesorería {NOM_UNIDAD}", page_icon=icono_pestana, layout="centered")

# Sacamos ambos IDs directamente de los secretos
SPREADSHEET_ID = st.secrets["config"]["spreadsheet_id"]
CARPETA_COMPROBANTES_ID = st.secrets["config"]["carpeta_comprobantes_id"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ========================================================
# 🔐 ESCUDO DE SEGURIDAD (LOGIN PARA DIRIGENTES)
# ========================================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    # Usamos unsafe_allow_html aquí también por si el título lleva el emoji en Base64
    st.markdown(f"## {EMOJI_UNIDAD} Acceso Restringido - Tesorería", unsafe_allow_html=True)
    st.write(f"Ingresa la contraseña de la {NOM_UNIDAD} para registrar movimientos.")

    clave_maestra = st.secrets["credenciales"]["clave_compartida"]
    pass_input = st.text_input("Contraseña de acceso", type="password")

    if st.button("Ingresar al Sistema"):
        if pass_input == clave_maestra:
            st.session_state["autenticado"] = True
            st.success(f"¡Bienvenido! Cargando panel de la {NOM_UNIDAD}...")
            st.rerun()
        else:
            st.error("❌ Contraseña incorrecta. ¡Inténtalo de nuevo!")
            
    st.stop()

# ==========================================
# 2. AUTENTICACIÓN DE GOOGLE 
# ==========================================
def autenticar():
    from google.oauth2.credentials import Credentials as OAuthCredentials
    
    creds = OAuthCredentials.from_authorized_user_info(st.secrets["token_json"], scopes=SCOPES)
    cliente_sheets = gspread.authorize(creds)
    servicio_drive = build('drive', 'v3', credentials=creds)
    
    return cliente_sheets, servicio_drive

def quitar_tildes(texto):
    texto = str(texto).lower().strip()
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')

@st.cache_data(ttl=600)
def cargar_lista_lobatos():
    try:
        cliente_sheets, _ = autenticar()
        sheet = cliente_sheets.open_by_key(SPREADSHEET_ID)
        hoja_principal = sheet.worksheet("Mensualidades")
        registros = hoja_principal.get_all_values()
        nombres = [fila[1] for fila in registros[1:] if len(fila) > 1 and fila[1].strip()]
        return nombres, registros
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return [], []

@st.cache_data(ttl=600)
def obtener_datos_busqueda():
    cliente_sheets, _ = autenticar()
    sheet = cliente_sheets.open_by_key(SPREADSHEET_ID)
    meses_map = ['Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    data_total = []
    
    for mes in meses_map:
        try:
            hoja = sheet.worksheet(mes)
            rows = hoja.get_all_values()
            for row in rows[1:]:
                if len(row) > 1:
                    row_data = row + [mes] 
                    data_total.append(row_data)
        except: continue
    return data_total

# ==========================================
# 3. CREACIÓN DE PESTAÑAS (TABS)
# ==========================================
# Renderizamos el título principal admitiendo HTML para el emoji personalizado
st.markdown(f"# {EMOJI_UNIDAD} Tesorería de la {NOM_UNIDAD}", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 Registrar Transacción", "📊 Estadísticas y Buscador"])

# ==========================================
# PESTAÑA 1: REGISTRAR TRANSACCIÓN
# ==========================================
with tab1:
    st.write("Registra ingresos y egresos de forma rápida para el Excel.")

    if 'form_id' not in st.session_state:
        st.session_state.form_id = 0

    if 'ultimo_registro' in st.session_state:
        # st.success no interpreta HTML directo de forma nativa en textos complejos, 
        # así que usamos markdown para mostrar el último registro con su emoji impecable.
        st.markdown(f"✅ **Último registro:** {st.session_state['ultimo_registro']}", unsafe_allow_html=True)
        if st.session_state.get('mostrar_globos', False):
            st.balloons()
            st.session_state['mostrar_globos'] = False

    lista_nombres_lobatos, todos_los_registros = cargar_lista_lobatos()

    col1, col2 = st.columns(2)
    with col1:
        lista_meses = ["Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre"]
        meses_espanol = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        mes_actual_nombre = meses_espanol[datetime.today().month]
        default_index = lista_meses.index(mes_actual_nombre) if mes_actual_nombre in lista_meses else 0

        mes_seleccionado = st.selectbox("📅 Mes del registro:", lista_meses, index=default_index, key=f'mes_sel_{st.session_state.form_id}')
    with col2:
        tipo_movimiento = st.radio("💰 Tipo de movimiento:", ["Ingreso", "Egreso"], horizontal=True, key=f'tipo_mov_{st.session_state.form_id}')

    tipo_transaccion = st.selectbox("📌 Tipo de Transacción:", [
        "Cuota", "Inscripción", "Cuota e Inscripción", 
        "Transferencia", "Devolución", "Compra", "Depósito", "Donación"
    ], key=f'tipo_trans_{st.session_state.form_id}')

    motivo_especifico = ""
    objeto_comprado = ""
    evento_compra = ""
    quien_transfiere = ""
    quien_recibe = ""

    if tipo_transaccion == "Transferencia":
        col_tf1, col_tf2 = st.columns(2)
        with col_tf1:
            quien_transfiere = st.text_input("👤 ¿Quién hace la transferencia? (Origen):", placeholder="Ej: Apoderado Juan Pérez o Unidad", key=f'q_transfiere_{st.session_state.form_id}')
        with col_tf2:
            quien_recibe = st.text_input("👤 ¿Quién recibe la transferencia? (Destino):", placeholder="Ej: Caja Chica o Proveedor", key=f'q_recibe_{st.session_state.form_id}')
        motivo_especifico = st.text_input("🎯 Motivo específico (Ej: Cuota Rifa, Materiales Campamento):", key=f'mot_esp_tf_{st.session_state.form_id}')
        
    elif tipo_transaccion == "Devolución":
        motivo_especifico = st.text_input("🎯 Motivo específico (Ej: Compra campamento de verano):", key=f'mot_esp_dev_{st.session_state.form_id}')
        
    elif tipo_transaccion == "Compra":
        col_compra1, col_compra2 = st.columns(2)
        with col_compra1:
            objeto_comprado = st.text_input("📦 Qué se compró (Ej: Cartulinas y plumones):", key=f'obj_comp_{st.session_state.form_id}')
        with col_compra2:
            evento_compra = st.text_input("📅 Día o Evento (Ej: Consejo de Sábado):", key=f'evt_comp_{st.session_state.form_id}')

    es_pago_lobato = tipo_transaccion in ["Cuota", "Inscripción", "Cuota e Inscripción"]
    nombre_final = ""
    tiene_hermanos = False
    ya_pago_inscripcion = False

    if es_pago_lobato:
        nombre_final = st.selectbox(f"👦 Selecciona al {TEXTO_INDIVIDUAL} de la {NOM_UNIDAD}:", ["-- Selecciona una opción --"] + lista_nombres_lobatos, key=f'nom_lobato_{st.session_state.form_id}')
        if nombre_final != "-- Selecciona una opción --":
            nombre_input_limpio = quitar_tildes(nombre_final)
            headers = todos_los_registros[0]
            for fila in todos_los_registros:
                if len(fila) > 1 and quitar_tildes(fila[1]) == nombre_input_limpio:
                    if len(fila) > 3 and str(fila[3]).strip() not in ['0', '', '0%']:
                        tiene_hermanos = True
                    if 'Inscr.' in headers:
                        idx_inscr = headers.index('Inscr.')
                        if idx_inscr < len(fila) and fila[idx_inscr].strip().upper() in ["TRUE", "1"]:
                            ya_pago_inscripcion = True
                    break
    elif tipo_transaccion == "Transferencia":
        nombre_final = f"{quien_transfiere} a {quien_recibe}"
    else:
        nombre_final = st.text_input("🏢 Nombre de la persona o entidad (Ej: Librería Central u Olave):", key=f'nom_entidad_{st.session_state.form_id}')

    monto = st.number_input("💵 Monto ($):", min_value=0, step=500, format="%d", key=f'monto_val_{st.session_state.form_id}')

    cuotas_calculadas = 0
    num_cuotas_final = 0
    detalles_extra = ""
    minimo_requerido = 0
    monto_base_esperado = 0

    if es_pago_lobato and nombre_final != "-- Selecciona una opción --":
        valor_cuota = 11000 if tiene_hermanos else 12000
        
        if tipo_transaccion == "Cuota":
            minimo_requerido = valor_cuota
        elif tipo_transaccion == "Inscripción":
            minimo_requerido = 21000
        elif tipo_transaccion == "Cuota e Inscripción":
            minimo_requerido = 21000 + valor_cuota

        if tipo_transaccion in ["Inscripción", "Cuota e Inscripción"] and ya_pago_inscripcion:
            st.error(f"❌ **¡Paren las prensas!** Este {TEXTO_INDIVIDUAL} ya tiene registrada su inscripción como pagada en el sistema. No dupliques el registro.")

        if monto > 0 and monto < minimo_requerido:
            st.error(f"❌ **Monto insuficiente:** El valor ingresado (${monto:,}) ni siquiera llega al valor mínimo requerido para esta transacción (${minimo_requerido:,}).")
        else:
            if tipo_transaccion in ["Cuota", "Cuota e Inscripción"] and monto >= minimo_requerido:
                monto_restante_calc = monto
                if tipo_transaccion == "Cuota e Inscripción":
                    monto_restante_calc -= 21000
                    
                cuotas_calculadas = max(0, monto_restante_calc // valor_cuota)
                st.info(f"✨ **Cálculo Automático:** El programa detecta que este monto equivale a **{cuotas_calculadas} cuotas** en base a las condiciones del {TEXTO_INDIVIDUAL}.")
                num_cuotas_final = st.number_input("⚙️ Número de cuotas final (Modifica aquí si el cálculo es incorrecto):", value=int(cuotas_calculadas), min_value=0, step=1, key=f'num_cuotas_{st.session_state.form_id}')

            elif tipo_transaccion == "Inscripción" and monto >= minimo_requerido:
                st.info("✨ **Cálculo Automático:** Inscripción detectada ($21,000).")
                num_cuotas_final = 0

            if monto > monto_base_esperado and monto > 0:
                st.warning("⚠️ El monto ingresado supera el valor de lo cubierto por cuotas/inscripción.")
                detalles_extra = st.text_input("🔍 Detalla qué más transfirieron (Ej: los curantos, rifa):", placeholder="Ej: los curantos", key=f'detalles_extra_{st.session_state.form_id}')

    fecha = st.date_input("📆 Fecha de la transacción:", datetime.today(), key=f'fecha_val_{st.session_state.form_id}')

    texto_persona = nombre_final if (nombre_final and nombre_final != "-- Selecciona una opción --") else "[Nombre]"
    texto_motivo = motivo_especifico if motivo_especifico.strip() else "[Motivo]"
    texto_objeto = objeto_comprado if objeto_comprado.strip() else "[Objeto]"
    texto_evento = evento_compra if evento_compra.strip() else "[Día/Evento]"

    predeterminado_final = ""

    if tipo_transaccion == "Devolución":
        predeterminado_final = f"Devolución de dinero por parte de la unidad a {texto_persona} por {texto_motivo}"
        st.info(f"💡 **Comentario:** Si lo dejas en blanco se escribirá:\n\n*{predeterminado_final}*")
        
    elif tipo_transaccion == "Transferencia":
        texto_transfiere = quien_transfiere if quien_transfiere.strip() else "[Quién envía]"
        texto_recibe = quien_recibe if quien_recibe.strip() else "[Quién recibe]"
        predeterminado_final = f"Transferencia por concepto de {texto_motivo} realizada por {texto_transfiere} a {texto_recibe}"
        st.info(f"💡 **Comentario:** Si lo dejas en blanco se escribirá:\n\n*{predeterminado_final}*")
        
    elif tipo_transaccion == "Donación":
        predeterminado_final = f"Donación por parte de {texto_persona}"
        st.info(f"💡 **Comentario:** Si lo dejas en blanco se escribirá:\n\n*{predeterminado_final}*")
        
    elif tipo_transaccion == "Compra":
        sug_objeto = f"Pago por parte de la unidad para comprar {texto_objeto}"
        sug_evento = f"Pago por parte de la unidad para compras de {texto_evento}"
        
        st.write("📋 **Selecciona el comentario predeterminado para usar si dejas el campo vacío:**")
        seleccion_sugerida = st.radio("Opciones disponibles:", [sug_objeto, sug_evento], key=f'radio_compra_{st.session_state.form_id}')
        predeterminado_final = seleccion_sugerida
    elif es_pago_lobato:
        if detalles_extra.strip():
            if tipo_transaccion == "Cuota e Inscripción":
                predeterminado_final = f"Pago de cuota, inscripción y {detalles_extra.strip()} por parte del apoderado/a de {texto_persona}"
            elif tipo_transaccion == "Inscripción":
                predeterminado_final = f"Pago de inscripción y {detalles_extra.strip()} por parte del apoderado/a de {texto_persona}"
            else:
                predeterminado_final = f"Pago de cuota y {detalles_extra.strip()} por parte del apoderado/a de {texto_persona}"
        else:
            predeterminado_final = f"Pago de {tipo_transaccion.lower()} por parte del apoderado/a de {texto_persona}"
            
        st.info(f"💡 **Comentario:** Si lo dejas en blanco se escribirá:\n\n*{predeterminado_final}*")
    else:
        predeterminado_final = f"Pago por parte de {texto_persona} para {tipo_transaccion.lower()}"
        st.info(f"💡 **Comentario:** Si lo dejas en blanco se escribirá:\n\n*{predeterminado_final}*")

    comentario_usuario = st.text_input("📝 Escribe un comentario personalizado si deseas cambiar el predeterminado:", key=f'com_user_{st.session_state.form_id}')

    st.write("---")
    st.subheader("📸 Comprobantes de Pago")
    archivos_comprobantes = st.file_uploader(
        "Toma una foto, sube un pantallazo o un PDF (Puedes seleccionar varios archivos a la vez):", 
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
        key=f"comprobantes_{st.session_state.form_id}"
    )

    st.write("---")
    if st.button("🚀 REGISTRAR TRANSACCIÓN", use_container_width=True):
        if es_pago_lobato and nombre_final == "-- Selecciona una opción --":
            st.error(f"❌ Por favor, selecciona un {TEXTO_INDIVIDUAL} válido de la lista.")
        elif es_pago_lobato and tipo_transaccion in ["Inscripción", "Cuota e Inscripción"] and ya_pago_inscripcion:
            st.error(f"❌ Operación rechazada: La inscripción de este {TEXTO_INDIVIDUAL} ya figura como pagada.")
        elif es_pago_lobato and monto < minimo_requerido:
            st.error(f"❌ Error en el monto: Debe ingresar al menos el valor mínimo requerido (${minimo_requerido:,}).")
        elif tipo_transaccion == "Transferencia" and (not quien_transfiere.strip() or not quien_recibe.strip()):
            st.error("❌ Por favor, rellena quién realiza y quién recibe la transferencia.")
        elif not es_pago_lobato and tipo_transaccion != "Transferencia" and not nombre_final.strip():
            st.error("❌ Por favor, escribe el nombre de la entidad o persona.")
        elif tipo_transaccion in ["Devolución", "Transferencia"] and not motivo_especifico.strip():
            st.error(f"❌ Por favor, ingresa el motivo específico de la {tipo_transaccion.lower()}.")
        elif tipo_transaccion == "Compra" and not objeto_comprado.strip() and not evento_compra.strip():
            st.error("❌ Por favor, ingresa qué se compró o para qué evento se realizó la compra.")
        elif monto <= 0:
            st.error("❌ El monto debe ser mayor a $0.")
        elif es_pago_lobato and monto > monto_base_esperado and not detalles_extra.strip():
            st.error("❌ Detectamos dinero extra. Por favor, detalla qué más están pagando en la casilla correspondiente.")
        elif not archivos_comprobantes:
            st.error("❌ Debes adjuntar o tomarle una foto al menos a un comprobante desde tu dispositivo para validar.")
        else:
            with st.spinner("Procesando... Subiendo archivos a Drive y actualizando planilla... ⏳"):
                try:
                    cliente_sheets, servicio_drive = autenticar()
                    sheet = cliente_sheets.open_by_key(SPREADSHEET_ID)
                    
                    meses_map = {'Abril': 'Abr', 'Mayo': 'May', 'Junio': 'Jun', 'Julio': 'Jul',
                                 'Agosto': 'Ago', 'Septiembre': 'Sep', 'Octubre': 'Oct'}
                    hoja_mes_nombre = meses_map[mes_seleccionado]
                    
                    fecha_str = fecha.strftime("%d/%m/%Y")
                    
                    motivo_limpio = quitar_tildes(tipo_transaccion).replace(' ', '_').title()
                    persona_limpia = quitar_tildes(nombre_final).replace(' ', '_').title()
                    fecha_limpia = fecha_str.replace('/', '-')
                    
                    links_comprobantes = []
                    for index, archivo in enumerate(archivos_comprobantes):
                        sufijo = f"_{index + 1}" if len(archivos_comprobantes) > 1 else ""
                        nombre_archivo_drive = f"Comprobante_{motivo_limpio}_{persona_limpia}_{fecha_limpia}{sufijo}"
                        
                        file_metadata = {'name': nombre_archivo_drive, 'parents': [CARPETA_COMPROBANTES_ID]}
                        
                        archivo_bytes = archivo.getvalue()
                        fh = io.BytesIO(archivo_bytes)
                        media = MediaIoBaseUpload(fh, mimetype=archivo.type, resumable=True)
                        
                        archivo_drive = servicio_drive.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
                        servicio_drive.permissions().create(fileId=archivo_drive.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
                        
                        links_comprobantes.append(archivo_drive.get('webViewLink'))
                    
                    links_comprobantes_final = "\n".join(links_comprobantes)

                    if not comentario_usuario.strip():
                        comentario_final = predeterminado_final
                    else:
                        comentario_final = comentario_usuario.strip()

                    hoja_mes = sheet.worksheet(hoja_mes_nombre)
                    ingreso = monto if tipo_movimiento == "Ingreso" else 0
                    egreso = monto if tipo_movimiento == "Egreso" else 0
                    
                    nueva_fila = [fecha_str, tipo_transaccion, ingreso, egreso, "", links_comprobantes_final, comentario_final]
                    
                    todas_las_filas = hoja_mes.get_all_values()
                    index_a_insertar = len(todas_las_filas) + 1 
                    
                    for i, fila in enumerate(todas_las_filas[1:]):
                        try:
                            fecha_fila_dt = datetime.strptime(fila[0], "%d/%m/%Y")
                            if fecha < fecha_fila_dt.date():
                                index_a_insertar = i + 2
                                break
                        except (ValueError, IndexError):
                            continue
                    
                    hoja_mes.insert_row(nueva_fila, index=index_a_insertar, value_input_option='USER_ENTERED')

                    if es_pago_lobato and todos_los_registros:
                        hoja_principal = sheet.worksheet("Mensualidades")
                        headers = todos_los_registros[0]
                        
                        fila_lobato = None
                        datos_lobato = []
                        nombre_input_limpio = quitar_tildes(nombre_final)
                        
                        for i, fila in enumerate(todos_los_registros):
                            if len(fila) > 1 and quitar_tildes(fila[1]) == nombre_input_limpio:
                                fila_lobato = i + 1
                                datos_lobato = fila
                                break
                        
                        if fila_lobato:
                            paga_inscripcion = tipo_transaccion in ["Inscripción", "Cuota e Inscripción"]
                            if paga_inscripcion: 
                                if 'Inscr.' in headers:
                                    idx_inscr = headers.index('Inscr.') + 1
                                    hoja_principal.update_cell(fila_lobato, idx_inscr, "TRUE")
                            
                            if num_cuotas_final > 0:
                                meses_orden = ['Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic', 'ene']
                                cuotas_assigned = 0
                                for m_abrev in meses_orden:
                                    if cuotas_assigned >= num_cuotas_final: 
                                        break
                                    try:
                                        idx_mes = headers.index(m_abrev)
                                        valor_actual = datos_lobato[idx_mes].strip() if idx_mes < len(datos_lobato) else ""
                                        if valor_actual in ["", "0", "$0", "-", "FALSE"]:
                                            hoja_principal.update_cell(fila_lobato, idx_mes + 1, "TRUE")
                                            cuotas_assigned += 1
                                    except ValueError:
                                        continue
                    
                    st.session_state['ultimo_registro'] = comentario_final
                    st.session_state['mostrar_globos'] = True
                    st.session_state.form_id += 1
                    
                    st.cache_data.clear() 
                    st.rerun()
                    
                except Exception as err:
                    st.error(f"❌ Ocurrió un error al guardar los datos: {err}")

# ==========================================
# PESTAÑA 2: ESTADÍSTICAS Y BUSCADOR
# ==========================================
with tab2:
    st.header("📊 Panel de Consultas y Estadísticas")
    st.write("Sapea los datos acumulados y encuentra información al toque.")

    if not todos_los_registros:
        st.warning("No hay datos disponibles para mostrar estadísticas. Revisa la conexión.")
    else:
        headers_m = todos_los_registros[0]
        
        metodo_busqueda = st.selectbox("🔍 Selecciona el método de búsqueda:", [
            "Buscar Miembro", 
            "Buscar Tipo de Transacción",
            "Buscar por Motivo/Comentario"
        ], key="metodo_busqueda_key")

        # --- OPCIÓN A: BUSCAR MIEMBRO ---
        if metodo_busqueda == "Buscar Miembro":
            lobato_seleccionado = st.selectbox(f"👦 Elige un {TEXTO_INDIVIDUAL} de la {NOM_UNIDAD}:", ["-- Selecciona una opción --"] + lista_nombres_lobatos, key="busqueda_lobato_stats")
            
            if lobato_seleccionado != "-- Selecciona una opción --":
                st.subheader(f"📋 Estado de Cuenta: {lobato_seleccionado}")
                
                fila_n = None
                nombre_clean = quitar_tildes(lobato_seleccionado)
                for fila in todos_los_registros:
                    if len(fila) > 1 and quitar_tildes(fila[1]) == nombre_clean:
                        fila_n = fila
                        break
                
                if fila_n:
                    if 'Inscr.' in headers_m:
                        idx_i = headers_m.index('Inscr.')
                        status_inscr = fila_n[idx_i].strip().upper() if idx_i < len(fila_n) else ""
                        if status_inscr in ["TRUE", "1"]:
                            st.markdown("**Inscripción Inicial:** 🟢 Registrada / Al día")
                        else:
                            st.markdown("**Inscripción Inicial:** 🔴 Pendiente / No Registrada")
                    
                    st.write("#### Visualización de Cuotas:")
                    meses_a_mostrar = ['Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic', 'ene']
                    cols_meses = st.columns(5)
                    
                    for idx_m, m_abrev in enumerate(meses_a_mostrar):
                        col_target = cols_meses[idx_m % 5]
                        with col_target:
                            nombre_visible = "Ene" if m_abrev == "ene" else m_abrev
                            st.write(f"**{nombre_visible}**")
                            if m_abrev in headers_m:
                                idx_cell = headers_m.index(m_abrev)
                                idx_monto = idx_cell + 1
                                val_monto = fila_n[idx_monto].strip() if idx_monto < len(fila_n) else ""
                                if val_monto and val_monto not in ["", "0", "$0", "-", "$ -"]:
                                    st.markdown("🟢 Al día")
                                else:
                                    st.markdown("🔴 Pendiente")
                            else:
                                st.markdown("🔴 No Disp.")

        # --- OPCIÓN B: BUSCAR TIPO DE TRANSACCIÓN ---
        elif metodo_busqueda == "Buscar Tipo de Transacción":
            tipo_sel = st.selectbox("💰 Selecciona el tipo de transacción:", 
                                    ["Cuota", "Transferencia", "Devolución", "Compra", "Depósito", "Donación"], 
                                    key="tipo_trans_stats")
            
            if tipo_sel == "Cuota":
                st.subheader(f"🗓️ Cuotas de la {NOM_UNIDAD} por Mes")
                meses_a_contar = ['Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic', 'ene']
                total_lobatos = len(todos_los_registros) - 1
                for m_abrev in meses_a_contar:
                    nombre_visible = "Ene" if m_abrev == "ene" else m_abrev
                    if m_abrev in headers_m:
                        idx_mes = headers_m.index(m_abrev)
                        idx_monto = idx_mes + 1
                        contador_al_dia = sum(1 for fila in todos_los_registros[1:] 
                                             if idx_monto < len(fila) and fila[idx_monto].strip() and fila[idx_monto].strip() not in ["", "0", "$0", "-", "$ -"])
                        st.write(f"🔹 **{nombre_visible}**: {contador_al_dia} de {total_lobatos} {TEXTO_PLURAL} al día.")
            
            else:
                st.subheader(f"📋 Listado de: {tipo_sel}")
                registros_encontrados = []
                cliente_sheets, _ = autenticar()
                sheet = cliente_sheets.open_by_key(SPREADSHEET_ID)
                meses_map = ['Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct']
                
                for mes in meses_map:
                    try:
                        hoja = sheet.worksheet(mes)
                        data = hoja.get_all_values()
                        for fila in data[1:]:
                            if fila[1] == tipo_sel:
                                registros_encontrados.append({"Mes": mes, "Fecha": fila[0], "Ingreso": fila[2], "Egreso": fila[3], "Comentario": fila[6]})
                    except: continue
                
                if registros_encontrados:
                    st.table(pd.DataFrame(registros_encontrados))
                else:
                    st.info("No se encontraron registros de este tipo.")

        # --- OPCIÓN C: BUSCAR POR MOTIVO O COMENTARIO ---
        elif metodo_busqueda == "Buscar por Motivo/Comentario":
            keyword = st.text_input("📝 Escribe la palabra a buscar (ej: curanto):").strip().lower()
            
            if keyword:
                st.subheader(f"🔎 Resultados para: '{keyword}'")
                
                todos_los_datos = obtener_datos_busqueda()
                resultados_busqueda = []
                
                for fila in todos_los_datos:
                    comentario_fila = str(fila[6]).lower() if len(fila) > 6 else ""
                    
                    if keyword in comentario_fila:
                        resultados_busqueda.append({
                            "Mes": fila[7], 
                            "Fecha": fila[0],
                            "Tipo": fila[1],
                            "Ingreso": fila[2],
                            "Egreso": fila[3],
                            "Comentario": fila[6]
                        })
                
                if len(resultados_busqueda) > 0:
                    st.table(pd.DataFrame(resultados_busqueda))
                else:
                    st.info("No se encontraron registros que contengan esa palabra.")