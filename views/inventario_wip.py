"""
views/inventario_wip.py
Módulo de Inventario Físico de Tarimas WIP — SIGRAMA
• Una tarima (T-WIP-XXXXX) puede tener piezas de MÚLTIPLES nidos/OFs
• Se imprime UNA ETIQUETA POR PIEZA (no por tarima completa)
• Sin código QR
• El INT es el id interno de la pieza en la tabla piezas
"""
import streamlit as st
import pandas as pd
from utils.database import get_connection, get_local_now, save_db_to_excel


# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_tables():
    """Crea las tablas necesarias si no existen."""
    conn = get_connection()
    # Tabla de tarimas WIP (registro de qué piezas están en cada T-WIP)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarimas_wip (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            twip_id     TEXT NOT NULL,
            of_number   TEXT NOT NULL,
            nido        TEXT NOT NULL,
            no_pieza    TEXT NOT NULL,
            int_id      INTEGER,
            cantidad    INTEGER,
            timestamp   TEXT
        )
    """)
    # Tabla de inventarios físicos registrados
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventario_wip (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT NOT NULL,
            twip_id           TEXT,
            of_number         TEXT NOT NULL,
            nido              TEXT NOT NULL,
            no_pieza          TEXT NOT NULL,
            int_id            INTEGER,
            auditor           TEXT NOT NULL,
            cantidad_sistema  INTEGER NOT NULL,
            cantidad_fisica   INTEGER NOT NULL,
            desviacion        INTEGER NOT NULL,
            observaciones     TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_next_twip_id() -> str:
    conn = get_connection()
    row = conn.execute("SELECT MAX(id) FROM tarimas_wip").fetchone()
    conn.close()
    next_num = (row[0] or 0) + 1
    return f"T-WIP-{next_num:05d}"


def get_all_ofs():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT of_number FROM ordenes ORDER BY of_number").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_nidos_of(of_number):
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT nido FROM piezas WHERE of_number=? ORDER BY nido", (of_number,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_piezas_nido(of_number, nido):
    conn = get_connection()
    df_hojas = pd.read_sql_query(
        "SELECT hojas FROM nidos WHERE of_number=? AND nido=?", conn, params=(of_number, nido)
    )
    df_piezas = pd.read_sql_query(
        "SELECT id, no_pieza, nombre_pieza, cantidad FROM piezas WHERE of_number=? AND nido=? ORDER BY no_pieza",
        conn, params=(of_number, nido)
    )
    conn.close()
    if df_piezas.empty:
        return pd.DataFrame()
    hojas = int(df_hojas.iloc[0]['hojas']) if not df_hojas.empty else 1
    df_piezas['cantidad_sistema'] = df_piezas['cantidad'] * hojas
    df_piezas['hojas'] = hojas
    return df_piezas[['id', 'no_pieza', 'nombre_pieza', 'cantidad_sistema', 'hojas']]


def get_historial_inventario(of_filter=None, twip_filter=None, limit=300):
    ensure_tables()
    conn = get_connection()
    conds = []
    params = []
    if of_filter:
        conds.append("of_number = ?")
        params.append(of_filter)
    if twip_filter:
        conds.append("twip_id = ?")
        params.append(twip_filter)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    df = pd.read_sql_query(f"""
        SELECT timestamp as Fecha, twip_id as "T-WIP", of_number as OF, nido as Nido,
               no_pieza as "No. Pieza", int_id as INT, auditor as Auditor,
               cantidad_sistema as "Qty Sistema", cantidad_fisica as "Qty Física",
               desviacion as "Desviación", observaciones as Observaciones
        FROM inventario_wip
        {where}
        ORDER BY timestamp DESC LIMIT {limit}
    """, conn, params=params if params else None)
    conn.close()
    return df


def registrar_inventario_db(twip_id, of_number, nido, auditor, registros, obs_gen):
    ensure_tables()
    conn = get_connection()
    now = get_local_now().strftime("%Y-%m-%d %H:%M:%S")
    for r in registros:
        desviacion = int(r['cantidad_fisica']) - int(r['cantidad_sistema'])
        obs = str(r.get('obs', '') or obs_gen or '')
        conn.execute("""
            INSERT INTO inventario_wip
              (timestamp, twip_id, of_number, nido, no_pieza, int_id, auditor,
               cantidad_sistema, cantidad_fisica, desviacion, observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (now, twip_id, of_number, nido, r['no_pieza'], r.get('int_id', 0),
              auditor, int(r['cantidad_sistema']), int(r['cantidad_fisica']), desviacion, obs))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# VISTA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def view_inventario_wip():
    ensure_tables()

    st.markdown("## 🔍 Inventario Físico de Tarimas WIP")
    st.caption(
        "**T-WIP-XXXXX** · Una tarima puede tener piezas de múltiples OFs/Nidos. "
        "Se genera **una etiqueta por pieza**."
    )

    tab_etiqueta, tab_inventario, tab_historial = st.tabs([
        "🖨️ Etiqueta de Tarima (por pieza)",
        "📋 Registrar Inventario Físico",
        "📜 Historial de Auditorías",
    ])

    # ── TAB 1: ETIQUETA ──────────────────────────────────────────────────────
    with tab_etiqueta:
        st.markdown("### 🏷️ Generador de Etiquetas T-WIP")
        st.info(
            "**Una etiqueta por pieza.** Si una tarima tiene 2 tipos de pieza → "
            "genera 2 etiquetas con el MISMO T-WIP ID. El PDF descargado tendrá una página por pieza."
        )

        all_ofs = get_all_ofs()
        if not all_ofs:
            st.warning("No hay OFs registradas.")
            return

        # ID de tarima: nuevo o reutilizar
        col_tw1, col_tw2 = st.columns([2, 3])
        with col_tw1:
            modo_id = st.radio("ID de Tarima", ["Generar nuevo T-WIP", "Usar ID existente"], horizontal=True, key="twip_modo")
        with col_tw2:
            if modo_id == "Generar nuevo T-WIP":
                twip_propuesto = get_next_twip_id()
                st.markdown(f"**ID propuesto:** `{twip_propuesto}`")
                twip_id_uso = twip_propuesto
            else:
                twip_id_uso = st.text_input("Escribe el T-WIP existente (ej: T-WIP-00003)", key="twip_existente",
                                             placeholder="T-WIP-00003")

        st.markdown("---")
        st.markdown("#### Piezas en esta tarima")
        st.caption("Selecciona cada pieza que está en la tarima. Puedes agregar piezas de distintos nidos/OFs.")

        # Session state para lista de piezas acumuladas
        if "twip_piezas" not in st.session_state:
            st.session_state.twip_piezas = []

        col_a, col_b, col_c = st.columns([2, 2, 2])
        with col_a:
            of_add = st.selectbox("OF", all_ofs, key="twip_add_of")
        with col_b:
            nidos_add = get_nidos_of(of_add)
            nido_add = st.selectbox("Nido", nidos_add, key="twip_add_nido") if nidos_add else None
        with col_c:
            if nido_add:
                df_pzs = get_piezas_nido(of_add, nido_add)
                opciones_pzs = df_pzs['no_pieza'].tolist() if not df_pzs.empty else []
                pieza_add = st.selectbox("Pieza", opciones_pzs, key="twip_add_pieza")
            else:
                pieza_add = None

        if st.button("➕ Agregar pieza a la tarima", disabled=(pieza_add is None), key="twip_btn_add"):
            entrada = {"of_number": of_add, "nido": nido_add, "no_pieza": pieza_add}
            if entrada not in st.session_state.twip_piezas:
                st.session_state.twip_piezas.append(entrada)
                st.rerun()
            else:
                st.warning("Esa pieza ya está en la lista.")

        # Mostrar lista acumulada
        if st.session_state.twip_piezas:
            st.markdown(f"**{len(st.session_state.twip_piezas)} pieza(s) en esta tarima `{twip_id_uso}`:**")
            df_lista = pd.DataFrame(st.session_state.twip_piezas)
            df_lista.columns = ["OF", "Nido", "No. Pieza"]

            # Agregar INT y cantidad sistema para información
            rows_preview = []
            for p in st.session_state.twip_piezas:
                df_p = get_piezas_nido(p['of_number'], p['nido'])
                if not df_p.empty:
                    row_p = df_p[df_p['no_pieza'] == p['no_pieza']]
                    if not row_p.empty:
                        rows_preview.append({
                            "T-WIP": twip_id_uso,
                            "OF": p['of_number'],
                            "Nido": p['nido'],
                            "No. Pieza": p['no_pieza'],
                            "INT": f"INT {int(row_p.iloc[0]['id']):03d}",
                            "Qty Sistema": int(row_p.iloc[0]['cantidad_sistema']),
                        })

            if rows_preview:
                st.dataframe(pd.DataFrame(rows_preview), use_container_width=True, hide_index=True)

            col_gen, col_clear = st.columns([3, 1])
            with col_gen:
                if st.button("🖨️ Generar PDF (una página por pieza)", type="primary", use_container_width=True, key="twip_gen_pdf"):
                    try:
                        from utils.etiqueta_tarima import generar_multiples_etiquetas_stream
                        pdf_buf = generar_multiples_etiquetas_stream(
                            st.session_state.twip_piezas,
                            twip_id=twip_id_uso
                        )
                        fname = f"{twip_id_uso}_{get_local_now().strftime('%Y%m%d_%H%M')}.pdf"
                        st.download_button(
                            label=f"📥 Descargar Etiquetas PDF — {twip_id_uso}",
                            data=pdf_buf,
                            file_name=fname,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="twip_dl"
                        )
                        st.success(f"✅ PDF generado con {len(st.session_state.twip_piezas)} etiqueta(s). Imprime cada página para cada pieza.")
                        st.info("💡 Imprime en tamaño **Carta** · En el visor PDF usa `Ctrl+P`")
                    except Exception as e:
                        st.error(f"❌ Error al generar PDF: {e}")
            with col_clear:
                if st.button("🗑️ Limpiar lista", use_container_width=True, key="twip_clear"):
                    st.session_state.twip_piezas = []
                    st.rerun()
        else:
            st.info("☝️ Agrega al menos una pieza con el botón de arriba.")

    # ── TAB 2: REGISTRAR INVENTARIO ──────────────────────────────────────────
    with tab_inventario:
        st.markdown("### 📋 Registrar Conteo Físico de Inventario")
        st.caption("Captura lo que físicamente encontraste en la tarima. Se compara con el dato del sistema y detecta desviaciones.")

        all_ofs2 = get_all_ofs()

        col_i1, col_i2, col_i3 = st.columns([2, 2, 3])
        with col_i1:
            of_inv = st.selectbox("OF", all_ofs2, key="inv_of2")
        with col_i2:
            nidos_inv = get_nidos_of(of_inv)
            nido_inv = st.selectbox("Nido / Tarima", nidos_inv, key="inv_nido2") if nidos_inv else None
        with col_i3:
            twip_inv = st.text_input("T-WIP ID de la tarima (opcional)",
                                      placeholder="T-WIP-00001",
                                      key="inv_twip_id")

        # Auditor
        conn_p = get_connection()
        df_pers = pd.read_sql_query(
            "SELECT DISTINCT operador_nombre FROM personal_areas ORDER BY operador_nombre", conn_p
        )
        conn_p.close()
        personal = df_pers['operador_nombre'].tolist() if not df_pers.empty else []

        col_aud1, col_aud2 = st.columns([3, 3])
        with col_aud1:
            auditor = st.selectbox("👷 Quién hizo el inventario", ["— Selecciona —"] + personal, key="inv_auditor2")
        with col_aud2:
            obs_gen = st.text_input("Observaciones generales", placeholder="Ubicación, estado, etc.", key="inv_obs2")

        if nido_inv:
            df_piezas_inv = get_piezas_nido(of_inv, nido_inv)

            if df_piezas_inv.empty:
                st.info(f"No hay piezas para OF `{of_inv}` / Nido `{nido_inv}`.")
            else:
                st.markdown("---")
                st.markdown(f"#### Conteo físico — OF `{of_inv}` · Nido `{nido_inv}`")

                df_edit = df_piezas_inv.rename(columns={
                    'id': 'INT',
                    'no_pieza': 'No. Pieza',
                    'nombre_pieza': 'Descripción',
                    'cantidad_sistema': 'Qty Sistema',
                    'hojas': 'Hojas'
                })
                df_edit['INT'] = df_edit['INT'].apply(lambda x: f"INT {x:03d}")
                df_edit['Qty Física'] = df_edit['Qty Sistema']
                df_edit['Observación'] = ''
                df_edit = df_edit[['INT', 'No. Pieza', 'Descripción', 'Qty Sistema', 'Qty Física', 'Observación']]

                edited = st.data_editor(
                    df_edit, use_container_width=True, hide_index=True, key="inv_editor2",
                    column_config={
                        "INT": st.column_config.TextColumn("INT", width="small", disabled=True),
                        "No. Pieza": st.column_config.TextColumn("No. Pieza", width="medium", disabled=True),
                        "Descripción": st.column_config.TextColumn("Descripción", width="large", disabled=True),
                        "Qty Sistema": st.column_config.NumberColumn("📊 Sistema", width="small", disabled=True),
                        "Qty Física": st.column_config.NumberColumn("✏️ Físico", width="small", min_value=0, step=1),
                        "Observación": st.column_config.TextColumn("Observación", width="medium"),
                    },
                    num_rows="fixed",
                )

                edited['Desviación'] = edited['Qty Física'] - edited['Qty Sistema']
                desviaciones = edited[edited['Desviación'] != 0]

                if not desviaciones.empty:
                    for _, row in desviaciones.iterrows():
                        diff = int(row['Desviación'])
                        icon = "🔴" if abs(diff) > 3 else "🟡"
                        signo = "+" if diff > 0 else ""
                        st.warning(f"{icon} **{row['No. Pieza']}** — Sistema: {int(row['Qty Sistema'])} | Físico: {int(row['Qty Física'])} | **Diferencia: {signo}{diff}**")
                else:
                    st.success("✅ Sin desviaciones — todos los conteos coinciden con el sistema.")

                can_save = auditor != "— Selecciona —"
                if not can_save:
                    st.warning("⚠️ Selecciona el auditor antes de guardar.")

                if st.button("✅ Guardar Inventario", type="primary", use_container_width=True, disabled=not can_save, key="inv_save2"):
                    registros = []
                    for _, row in edited.iterrows():
                        int_str = str(row['INT']).replace("INT ", "").strip()
                        try:
                            int_id = int(int_str)
                        except:
                            int_id = 0
                        registros.append({
                            'no_pieza': row['No. Pieza'],
                            'int_id': int_id,
                            'cantidad_sistema': int(row['Qty Sistema']),
                            'cantidad_fisica': int(row['Qty Física']),
                            'obs': str(row['Observación']),
                        })
                    twip_usar = twip_inv.strip() or get_next_twip_id()
                    registrar_inventario_db(twip_usar, of_inv, nido_inv, auditor, registros, obs_gen)
                    save_db_to_excel()
                    n_desv = len(desviaciones)
                    if n_desv > 0:
                        st.error(f"🔴 Inventario guardado con **{n_desv} desviación(es)**. Revisa el historial.")
                    else:
                        st.success(f"✅ Inventario registrado — T-WIP: `{twip_usar}` · Auditor: **{auditor}**")
                    st.balloons()

    # ── TAB 3: HISTORIAL ─────────────────────────────────────────────────────
    with tab_historial:
        st.markdown("### 📜 Historial de Inventarios WIP")

        col_hf1, col_hf2 = st.columns([2, 2])
        with col_hf1:
            of_hf = st.selectbox("Filtrar por OF", ["Todas"] + get_all_ofs(), key="hist_of2")
        with col_hf2:
            twip_hf = st.text_input("Filtrar por T-WIP ID (opcional)", placeholder="T-WIP-00001", key="hist_twip")

        df_hist = get_historial_inventario(
            of_filter=of_hf if of_hf != "Todas" else None,
            twip_filter=twip_hf.strip() if twip_hf.strip() else None,
        )

        if df_hist.empty:
            st.info("No hay inventarios registrados todavía.")
        else:
            total = len(df_hist)
            con_desv = int((df_hist['Desviación'] != 0).sum())
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Registros", total)
            c2.metric("Con Desviación 🔴", con_desv)
            c3.metric("Sin Desviación ✅", total - con_desv)

            def color_desv(val):
                if isinstance(val, (int, float)):
                    if val < 0: return "background:#ffcccc;color:#c00;"
                    if val > 0: return "background:#fff3cc;color:#a60;"
                return ""

            st.dataframe(
                df_hist.style.applymap(color_desv, subset=["Desviación"]),
                use_container_width=True, hide_index=True, height=420,
            )

            import io
            buf = io.BytesIO()
            df_hist.to_excel(buf, index=False, sheet_name="Inventario WIP")
            buf.seek(0)
            st.download_button(
                "📥 Descargar Excel",
                data=buf,
                file_name=f"inventario_wip_{get_local_now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="hist_dl"
            )
