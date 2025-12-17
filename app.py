import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import json
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Launa CRM", 
    page_icon="💎", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE ---
st.markdown("""
<style>
    div.stButton > button {width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold;}
    [data-testid="stMetricValue"] {font-size: 32px; color: #00C853; font-weight: 600;}
    /* Login Box Styling */
    .login-box {
        padding: 50px;
        border-radius: 10px;
        background-color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
RATE_DAY = 2797.0
RATE_EVE = 3768.47
DEDUCTION_RATE = 636.0
OFFSET_HOURS = 1.0
SHEET_NAME = "Launa_DB"
MONTH_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Maí", 6: "Jún", 7: "Júl", 8: "Ágú", 9: "Sep", 10: "Okt", 11: "Nóv", 12: "Des"}

# --- AUTH & CONNECTION (FIXED SCOPES) ---
@st.cache_resource
def get_gsheet_client():
    try:
        # Check for "Foolproof" JSON string first
        if "google_credentials_json" in st.secrets:
            secrets = json.loads(st.secrets["google_credentials_json"])
        # Fallback to standard TOML
        elif "gcp_service_account" in st.secrets:
            secrets = dict(st.secrets["gcp_service_account"])
            if "private_key" in secrets:
                secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")
        else:
            return None
        
        # --- THE FIX IS HERE: Added 'drive' scope ---
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds = Credentials.from_service_account_info(secrets, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

def get_data(worksheet_name):
    client = get_gsheet_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open(SHEET_NAME)
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        # Fail silently or log error if needed
        # st.error(f"Error loading {worksheet_name}: {e}")
        return pd.DataFrame()

def append_row(worksheet_name, row_data):
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open(SHEET_NAME)
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

# --- LOGIC ---
def calculate_pay(day_h, eve_h, sales):
    wages = (day_h * RATE_DAY) + (eve_h * RATE_EVE)
    total_h = day_h + eve_h
    threshold = max(0, (total_h - OFFSET_HOURS) * DEDUCTION_RATE)
    bonus = max(0, sales - threshold)
    return wages, bonus, (wages + bonus)

def get_wage_month(date_obj):
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
        except: return "Unknown"
    if date_obj.day >= 26:
        next_month = date_obj.replace(day=1) + timedelta(days=32)
        return f"{next_month.year}-{next_month.month:02d} ({MONTH_MAP[next_month.month]})"
    return f"{date_obj.year}-{date_obj.month:02d} ({MONTH_MAP[date_obj.month]})"

# --- LOGIN SYSTEM ---
def check_login(staff_code):
    df_users = get_data("Users")
    
    if df_users.empty:
        st.error("⚠️ Villa: Gat ekki lesið 'Users' flipann. Athugaðu nafnið.")
        return None
    
    # Robust string cleaning
    df_users['StaffCode'] = df_users['StaffCode'].astype(str).str.strip()
    clean_code = str(staff_code).strip()
    
    user_row = df_users[df_users['StaffCode'] == clean_code]
    
    if not user_row.empty:
        return user_row.iloc[0]['Name']
    
    return None

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_code = ""

# --- LOGIN SCREEN ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>🔐</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>Innskráning</h2>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            input_code = st.text_input("Starfsmannanúmer", type="password")
            submitted = st.form_submit_button("Skrá inn")
            
            if submitted:
                # Clear cache to force refresh of Users tab
                st.cache_resource.clear()
                
                name = check_login(input_code)
                if name:
                    st.session_state.logged_in = True
                    st.session_state.user_code = str(input_code).strip()
                    st.session_state.user_name = name
                    st.rerun()
                else:
                    st.error("🚫 Rangt númer eða notandi fannst ekki.")
    st.stop() 

# =========================================================
# === MAIN APP (Logged In) ===
# =========================================================

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👋 Hæ, {st.session_state.user_name}")
    st.caption(f"Starfsmaður: {st.session_state.user_code}")
    
    menu = st.radio("Valmynd", ["🔥 Dagurinn í dag", "📊 Mælaborð", "📝 Skrá Vakt", "💾 Gagnagrunnur"])
    
    st.markdown("---")
    daily_goal = st.number_input("Dagsmarkmið:", value=150000, step=10000)
    monthly_goal = st.number_input("Mánaðarmarkmið:", value=600000, step=50000)
    
    st.markdown("---")
    if st.button("🚪 Útskráning"):
        st.session_state.logged_in = False
        st.session_state.user_code = ""
        st.rerun()

# --- FILTER FUNCTION ---
def get_my_data(tab_name):
    df = get_data(tab_name)
    if df.empty: return df
    
    if 'StaffCode' in df.columns:
        df['StaffCode'] = df['StaffCode'].astype(str).str.strip()
        return df[df['StaffCode'] == st.session_state.user_code]
    return df

# --- 1. LIVE DAY ---
if menu == "🔥 Dagurinn í dag":
    st.header(f"📅 Sala í dag ({datetime.now().strftime('%d. %b')})")
    
    df_sales = get_my_data("Sales")
    
    today_sales = pd.DataFrame()
    if not df_sales.empty and 'Timestamp' in df_sales.columns:
        df_sales['Timestamp'] = pd.to_datetime(df_sales['Timestamp'])
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_sales = df_sales[df_sales['Timestamp'].dt.strftime("%Y-%m-%d") == today_str].copy()

    cur_sales = today_sales['Amount'].sum() if not today_sales.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Sala í dag", f"{cur_sales:,.0f} kr")
    c2.metric("📦 Fjöldi sala", len(today_sales))
    prog = min(1.0, cur_sales/daily_goal) if daily_goal>0 else 0
    c3.metric("🎯 Markmið", f"{prog*100:.0f}%")
    st.progress(prog)
    
    st.markdown("### ➕ Skrá nýja sölu")
    with st.container():
        with st.form("add_sale"):
            c1, c2 = st.columns([2,1])
            with c1:
                amt = st.number_input("Upphæð", step=1000)
            with c2:
                note = st.text_input("Skýring")
            
            if st.form_submit_button("Vista"):
                now = datetime.now()
                # Row: StaffCode, Timestamp, Time, Amount, Note
                row = [st.session_state.user_code, str(now), now.strftime("%H:%M"), amt, note]
                append_row("Sales", row)
                st.success("Skráð!")
                st.rerun()
            
    if not today_sales.empty:
        st.dataframe(today_sales[['Time', 'Amount', 'Note']].sort_values('Time', ascending=False), use_container_width=True, hide_index=True)

# --- 2. STATS ---
elif menu == "📊 Mælaborð":
    st.header("📈 Mælaborð")
    df_wages = get_my_data("Wages")
    
    if not df_wages.empty and 'WageMonth' in df_wages.columns:
        months = sorted(df_wages['WageMonth'].unique().tolist(), reverse=True)
        if months:
            sel_m = st.selectbox("Mánuður", months)
            m_data = df_wages[df_wages['WageMonth'] == sel_m]
            
            if not m_data.empty:
                tot_pay = m_data['Total'].sum()
                tot_bonus = m_data['Bonus'].sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Heildarlaun", f"{tot_pay:,.0f}")
                c2.metric("Bónusar", f"{tot_bonus:,.0f}")
                c3.metric("Vaktir", len(m_data))
                
                st.progress(min(1.0, tot_pay/monthly_goal))
                
                if 'Date' in m_data.columns:
                    m_data['DateObj'] = pd.to_datetime(m_data['Date'])
                    m_data = m_data.sort_values('DateObj')
                    fig = px.bar(m_data, x='Date', y=['Wage', 'Bonus'], title="Launaþróun", color_discrete_map={'Wage': '#29B6F6', 'Bonus': '#66BB6A'})
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Engin gögn fundust.")
    else:
        st.info("Engin gögn fundust.")

# --- 3. END SHIFT ---
elif menu == "📝 Skrá Vakt":
    st.header("🏁 Loka Vakt")
    
    df_sales = get_my_data("Sales")
    auto_sales = 0
    if not df_sales.empty:
        df_sales['Timestamp'] = pd.to_datetime(df_sales['Timestamp'])
        today_str = datetime.now().strftime("%Y-%m-%d")
        auto_sales = df_sales[df_sales['Timestamp'].dt.strftime("%Y-%m-%d") == today_str]['Amount'].sum()

    with st.form("end_shift"):
        date_in = st.date_input("Dagsetning", value=datetime.now())
        sales_in = st.number_input("Heildarsala", value=int(auto_sales))
        c1, c2 = st.columns(2)
        d_h = c1.number_input("Dagvinna", step=0.5)
        e_h = c2.number_input("Kvöldvinna", step=0.5)
        
        if st.form_submit_button("Vista"):
            w, b, t = calculate_pay(d_h, e_h, sales_in)
            mon = get_wage_month(date_in)
            row = [st.session_state.user_code, str(date_in), d_h, e_h, sales_in, w, b, t, mon]
            append_row("Wages", row)
            st.balloons()
            st.success(f"Vakt vistuð! {t:,.0f} kr.")

# --- 4. DB ---
elif menu == "💾 Gagnagrunnur":
    st.header("🗄️ Mín Gögn")
    tab1, tab2 = st.tabs(["Laun", "Sala"])
    with tab1:
        st.dataframe(get_my_data("Wages"), use_container_width=True)
    with tab2:
        st.dataframe(get_my_data("Sales"), use_container_width=True)
