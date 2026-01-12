# CONTROL INTELIGENTE DE CONSUMO – GRUPO BCA
# Versión FINAL v11 – DESVIO visible + fecha última carga + export Excel
# --------------------------------------------------

import re
import os
import numpy as np
import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# ==========================
# CONFIG
# ==========================
st.set_page_config(page_title="Control de Consumo BCA", layout="wide")

TOLERANCIA_PCT = 0.03  # 4%

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(BASE_DIR, "base.xlsx")
NOMINA_PATH = os.path.join(BASE_DIR, "Nomina_consumo_camion.xlsx")

LOGO_PATHS = [
    os.path.join(BASE_DIR, "logo_bca.png"),
    os.path.join(BASE_DIR, "logo_bca.jpg"),
    os.path.join(BASE_DIR, "logo_bca.jpeg"),
]

COLOR_PRINCIPAL = "#006778"
COLOR_SECUNDARIO = "#009999"

# ==========================
# AUTENTICACIÓN SOLO POR EMAIL (SIN CÓDIGO)
# ==========================
USUARIOS_PERMITIDOS = {
    "ycarriego@grupobca.com.ar",
    "aescobar@grupobca.com.ar",
    "oscarsaavedra01@gmail.com",
    "mcarmona@grupobca.com.ar",
    "mmaxit@grupobca.com.ar",
    "jptermite@grupobca.com.ar",
    "mcabo@grupobca.com.ar",
    "jbassi@grupobca.com.ar",
    "mmanresa@grupobca.com.ar",
    "dloillet@grupobca.com.ar",
}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown(
        """
        <h2 style="text-align:center; margin-bottom:0;">
            Acceso al Panel de Consumo BCA
        </h2>
        <p style="text-align:center; margin-top:4px; color:gray;">
            Ingrese su correo corporativo autorizado.
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_login1, col_login2, col_login3 = st.columns([1, 2, 1])
    with col_login2:
        email = st.text_input("Correo corporativo:", key="login_email")

        if st.button("Ingresar", type="primary"):
            email_norm = email.strip().lower()
            if email_norm in {c.lower() for c in USUARIOS_PERMITIDOS}:
                st.session_state["autenticado"] = True
                st.session_state["usuario"] = email_norm
                st.success("Acceso concedido. Bienvenido.")
                st.rerun()
            else:
                st.error("Correo no autorizado. Verifique e intente nuevamente.")

    st.stop()

# ==========================
# CSS
# ==========================
st.markdown(
    """
<style>
html, body, [class*="css"] { font-size: 18px; }
.card {
    background: white;
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 6px 14px rgba(0,0,0,0.12);
    text-align: center;
}
</style>
""",
    unsafe_allow_html=True,
)

# ==========================
# HELPERS
# ==========================
def es_patente_valida(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return False
    return bool(
        re.match(r"^[A-Z]{3}[0-9]{3}$|^[A-Z]{2}[0-9]{3}[A-Z]{2}$", str(p).upper())
    )

def to_num_col(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")

def normalizar_base(df):
    df = df.copy()
    rename = {}
    for c in df.columns:
        cu = str(c).upper().strip()
        if "PAT" in cu:
            rename[c] = "PATENTE"
        elif "FECHA" in cu:
            rename[c] = "FECHA"
        elif "ODOM" in cu or "ODÓMETRO" in cu or "KM" in cu or "KILOM" in cu:
            rename[c] = "KM"
        elif "LIT" in cu or "PRODUCTO" in cu:
            rename[c] = "LITROS"

    df = df.rename(columns=rename)

    for r in ["PATENTE", "FECHA", "KM", "LITROS"]:
        if r not in df.columns:
            raise ValueError(f"Falta columna obligatoria en base.xlsx: {r}")

    df["PATENTE"] = df["PATENTE"].astype(str).str.upper().str.strip()
    df["KM"] = to_num_col(df["KM"])
    df["LITROS"] = to_num_col(df["LITROS"])
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce", dayfirst=True)

    df = df[df["PATENTE"].apply(es_patente_valida)]
    df = df.dropna(subset=["FECHA"])
    return df

def normalizar_nomina(df):
    df = df.copy()
    df.columns = [c.upper().strip() for c in df.columns]

    # PATENTE
    if "PATENTE" not in df.columns:
        for c in df.columns:
            if "PAT" in c:
                df = df.rename(columns={c: "PATENTE"})
                break

    # MODELO
    if "MODELO" not in df.columns:
        for c in df.columns:
            if "MODE" in c:
                df = df.rename(columns={c: "MODELO"})
                break

    # Consumo teórico (columna razonable)
    col_consumo = None
    for c in df.columns:
        cu = c.upper()
        if ("LIT" in cu or "CONSUM" in cu) and ("100" in cu or "KM" in cu):
            col_consumo = c
            break

    if col_consumo:
        df = df.rename(columns={col_consumo: "LITROS_100KM"})
        df["LITROS_100KM"] = to_num_col(df["LITROS_100KM"])
    else:
        df["LITROS_100KM"] = np.nan

    if "MODELO" not in df.columns:
        df["MODELO"] = np.nan

    df["PATENTE"] = df["PATENTE"].astype(str).str.upper().str.strip()
    df = df[df["PATENTE"].apply(es_patente_valida)]

    return df[["PATENTE", "MODELO", "LITROS_100KM"]]

def calcular_eventos(df):
    df = df.sort_values(["PATENTE", "FECHA", "KM"]).copy()

    df["KM_ANT"] = df.groupby("PATENTE")["KM"].shift(1)
    df["KM_DELTA"] = df["KM"] - df["KM_ANT"]

    df["ESTADO_DATOS"] = "OK"
    df.loc[df["KM_ANT"].isna(), "ESTADO_DATOS"] = "PRIMERA_CARGA"
    df.loc[df["KM_DELTA"] <= 0, "ESTADO_DATOS"] = "ERROR DATOS"
    df.loc[df["LITROS"] <= 0, "ESTADO_DATOS"] = "ERROR DATOS"

    # Regla continuidad
    df["ERROR_ANT"] = (
        df.groupby("PATENTE")["ESTADO_DATOS"]
          .shift(1)
          .eq("ERROR DATOS")
    )

    df["TRAMO_VALIDO"] = (
        (df["ESTADO_DATOS"] == "OK") &
        (~df["ERROR_ANT"]) &
        (df["KM_DELTA"] > 0)
    )

    return df

def clasificar_estado(cons_real, cons_teor, errores):
    if errores > 0:
        return "ERROR DATOS"
    if pd.isna(cons_real) or pd.isna(cons_teor):
        return "SIN DATOS"

    min_ok = cons_teor * (1 - TOLERANCIA_PCT)
    max_ok = cons_teor * (1 + TOLERANCIA_PCT)

    if cons_real < min_ok or cons_real > max_ok:
        return "A AUDITAR"
    return "CORRECTO"

def motivo_sin_datos(row):
    # Si hay errores en eventos -> km invalido (auditoría)
    if row.get("ERRORES", 0) > 0:
        return "KM_INVALIDO"
    km = row.get("KM_RECORRIDOS", np.nan)
    if pd.isna(km) or km <= 0:
        return "PRIMERA_CARGA"
    if pd.isna(row.get("LITROS_100KM", np.nan)):
        return "NOMINA_FALTANTE"
    return None

def icono_estado(row):
    if row["ESTADO"] == "CORRECTO":
        return "🟢"
    if row["ESTADO"] == "A AUDITAR":
        return "🟡"
    if row["ESTADO"] == "ERROR DATOS":
        return "🔴"
    # SIN DATOS
    if row["MOTIVO_SIN_DATOS"] == "PRIMERA_CARGA":
        return "🟡"
    if row["MOTIVO_SIN_DATOS"] in ("KM_INVALIDO", "NOMINA_FALTANTE"):
        return "🔴"
    return "⚪"

def exportar_excel(df_export: pd.DataFrame) -> BytesIO:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="Consumo", index=False)
    buf.seek(0)
    return buf

# ==========================
# HEADER
# ==========================
c_logo, c_title = st.columns([1, 6])
with c_logo:
    for lp in LOGO_PATHS:
        if os.path.exists(lp):
            st.image(lp, width=130)
            break

with c_title:
    st.markdown(
        f"""
    <div style="background:linear-gradient(90deg,{COLOR_PRINCIPAL},{COLOR_SECUNDARIO});
                padding:22px 28px;
                border-radius:20px;
                color:white;">
        <div style="font-size:30px;font-weight:800;">
            Control Inteligente de Consumo
        </div>
        <div style="font-size:17px;opacity:0.9;">
            Estados + auditoría · Grupo BCA
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ==========================
# DATA
# ==========================
df_base = normalizar_base(pd.read_excel(BASE_PATH))
df_nom = normalizar_nomina(pd.read_excel(NOMINA_PATH))

# ==========================
# FILTROS
# ==========================
st.sidebar.header("Filtros")

fmin, fmax = df_base["FECHA"].min().date(), df_base["FECHA"].max().date()
fecha_ini, fecha_fin = st.sidebar.date_input("Rango fechas", [fmin, fmax])

patentes = sorted(df_base["PATENTE"].unique())
pat_sel = st.sidebar.multiselect("Patentes", patentes)

modelos = sorted(df_nom["MODELO"].dropna().unique())
mod_sel = st.sidebar.multiselect("Modelo", modelos)

estados_disponibles = ["CORRECTO", "A AUDITAR", "SIN DATOS", "ERROR DATOS"]
estado_sel = st.sidebar.multiselect("Estado", estados_disponibles, default=estados_disponibles)

df_f = df_base[
    (df_base["FECHA"].dt.date >= fecha_ini) &
    (df_base["FECHA"].dt.date <= fecha_fin)
]
if pat_sel:
    df_f = df_f[df_f["PATENTE"].isin(pat_sel)]

# ==========================
# CÁLCULO
# ==========================
ev = calcular_eventos(df_f)

# Última carga evaluada por patente (de todo el set filtrado)
ultima_fecha = (
    ev.groupby("PATENTE")["FECHA"]
      .max()
      .reset_index(name="FECHA_ULTIMA_CARGA")
)

ok = ev[
    (ev["ESTADO_DATOS"] == "OK") &
    (ev["TRAMO_VALIDO"]) &
    (ev["KM_DELTA"] > 0)
]

# Litros total (auditoría) (incluye todo)
agg_litros_total = ev.groupby("PATENTE", as_index=False).agg(
    LITROS_TOTALES=("LITROS", "sum")
)

# Tramos OK: litros + km (para consumo)
agg_ok = ok.groupby("PATENTE", as_index=False).agg(
    LITROS_OK=("LITROS", "sum"),
    KM_RECORRIDOS=("KM_DELTA", "sum"),
)

# Errores
err = (
    ev.groupby("PATENTE")["ESTADO_DATOS"]
      .apply(lambda s: (s == "ERROR DATOS").sum())
      .reset_index(name="ERRORES")
)

df = (
    agg_litros_total
    .merge(agg_ok, on="PATENTE", how="left")
    .merge(err, on="PATENTE", how="left")
    .merge(df_nom, on="PATENTE", how="left")
    .merge(ultima_fecha, on="PATENTE", how="left")
)

df["LITROS_OK"] = df["LITROS_OK"].fillna(0.0)
df["ERRORES"] = df["ERRORES"].fillna(0).astype(int)

df["CONSUMO_REAL_L_100KM"] = np.where(
    df["KM_RECORRIDOS"] > 0,
    (df["LITROS_OK"] / df["KM_RECORRIDOS"]) * 100,
    np.nan
)

df["DESVIO_PCT"] = np.where(
    df["LITROS_100KM"].notna() & (df["LITROS_100KM"] > 0),
    (df["CONSUMO_REAL_L_100KM"] - df["LITROS_100KM"]) / df["LITROS_100KM"] * 100,
    np.nan
)

# Redondeo (visual)
df["CONSUMO_REAL_L_100KM"] = df["CONSUMO_REAL_L_100KM"].round(2)
df["DESVIO_PCT"] = df["DESVIO_PCT"].round(2)

# Fecha estética
df["FECHA_ULTIMA_CARGA"] = pd.to_datetime(df["FECHA_ULTIMA_CARGA"], errors="coerce")
df["FECHA_ULTIMA_CARGA_STR"] = df["FECHA_ULTIMA_CARGA"].dt.strftime("%d/%m/%Y")

# Estado / motivo / semáforo
df["ESTADO"] = df.apply(
    lambda r: clasificar_estado(r["CONSUMO_REAL_L_100KM"], r["LITROS_100KM"], r["ERRORES"]),
    axis=1
)

df["MOTIVO_SIN_DATOS"] = df.apply(
    lambda r: motivo_sin_datos(r) if r["ESTADO"] == "SIN DATOS" else None,
    axis=1
)

df["SEMAFORO"] = df.apply(icono_estado, axis=1)

# Filtros post-cálculo
if mod_sel:
    df = df[df["MODELO"].isin(mod_sel)]
if estado_sel:
    df = df[df["ESTADO"].isin(estado_sel)]

# ==========================
# EXPORT + TABLA (UN SOLO df_export, NO SE PISA)
# ==========================
df_export = df[
    [
        "SEMAFORO", "ESTADO", "MOTIVO_SIN_DATOS",
        "PATENTE", "MODELO",
        "FECHA_ULTIMA_CARGA_STR",
        "KM_RECORRIDOS",
        "LITROS_TOTALES", "LITROS_OK",
        "CONSUMO_REAL_L_100KM", "LITROS_100KM",
        "DESVIO_PCT",
    ]
].rename(columns={
    "FECHA_ULTIMA_CARGA_STR": "FECHA_ULTIMA_CARGA",
    "DESVIO_PCT": "DESVIO_%"
}).sort_values("PATENTE")

# Asegurar que se vea como % (string) sin perder valor numérico en Excel:
# - En pantalla: mostramos DESVIO_% con % bonito
# - En Excel: dejamos también una columna numérica DESVIO_NUM (opcional)
df_export["DESVIO_%"] = df_export["DESVIO_%"].apply(
    lambda x: (f"{x:.2f}%" if pd.notna(x) else "")
)

# ==========================
# EXPORTACIÓN (1 click)
# ==========================
st.sidebar.markdown("---")
nombre_archivo = f"consumo_bca_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

st.sidebar.download_button(
    label="📤 Descargar Excel",
    data=exportar_excel(df_export),
    file_name=nombre_archivo,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# ==========================
# KPIs
# ==========================
st.subheader("Resumen general")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f'<div class="card">🟢 CORRECTO<br><h2>{(df["ESTADO"]=="CORRECTO").sum()}</h2></div>',
        unsafe_allow_html=True
    )
with c2:
    st.markdown(
        f'<div class="card">🟡 A AUDITAR<br><h2>{(df["ESTADO"]=="A AUDITAR").sum()}</h2></div>',
        unsafe_allow_html=True
    )
with c3:
    st.markdown(
        f'<div class="card">🟡 SIN DATOS<br><h2>{(df["ESTADO"]=="SIN DATOS").sum()}</h2></div>',
        unsafe_allow_html=True
    )
with c4:
    st.markdown(
        f'<div class="card">🔴 ERROR DATOS<br><h2>{(df["ESTADO"]=="ERROR DATOS").sum()}</h2></div>',
        unsafe_allow_html=True
    )

# Última fecha global del filtro (estética)
fecha_global = ev["FECHA"].max()
if pd.notna(fecha_global):
    st.caption(f"📌 Última carga evaluada en el rango seleccionado: **{fecha_global.strftime('%d/%m/%Y %H:%M')}**")

# ==========================
# TABLA
# ==========================
st.subheader("Detalle por patente")

st.dataframe(
    df_export,
    use_container_width=True,
    key="tabla_principal"
)

with st.expander("Eventos por carga (auditoría)"):
    st.dataframe(
        ev.sort_values(["PATENTE", "FECHA"]),
        use_container_width=True,
        key="tabla_eventos"
    )

st.caption("Control de Consumo – Grupo BCA")
