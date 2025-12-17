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
    [data-testid="stMetricValue"] {font-size: 26px; color: #00C853; font-weight: 600;}
    .big-card {
        background-color: white; padding: 20px; border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION ---
SHEET_ID = "1BUiNj316whIeXoSvuHmpUfYgBHb4HbPkO4cZu_PEPI8" # YOUR SHEET ID

# WAGE CONSTANTS
RATE_DAY = 2797.0
RATE_EVE = 3768.47
DEDUCTION_RATE = 636.0
OFFSET_HOURS = 1.0
MONTH_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Maí", 6: "Jún", 7: "Júl", 8: "Ágú", 9: "Sep", 10: "Okt", 11: "Nóv", 12: "Des"}

# TAX CONSTANTS (Standard Icelandic Defaults - You can change these)
PENSION_RATE = 0.04        # 4% Lífeyrissjóður
UNION_RATE = 0.007         # 0.7% Stéttarfélag
TAX_RATE_1 = 0.3145        # 31.45% Skattþrep 1
PERSONAL_ALLOWANCE = 64926 # Persónuafsláttur (approx monthly)

# --- AUTH & CONNECTION ---
@st.cache_resource
def get_gsheet_client():
    try:
        if "google_credentials_json" in st.secrets:
            secrets = json.loads(st.secrets["google_credentials_json"])
        elif "gcp_service_account" in st.secrets:
            secrets = dict(st.secrets["gcp_service_account"])
            if "private_key" in secrets:
                secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")
        else:
            return None
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(secrets, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

# Adding TTL (Time To Live) to cache ensures it refreshes automatically every 10 seconds
# This fixes the issue of the dashboard not updating
@st.cache_data(ttl=10)
def get_data(worksheet_name):
    client = get_gsheet_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def append_row(worksheet_name, row_data):
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)
        # CLEAR CACHE IMMEDIATELY AFTER SAVE
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

# --- LOGIC FUNCTIONS ---
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

def calculate_net_salary(gross_salary, personal_allowance_usage=1.0):
    """
    Standard Icelandic Salary Calculation.
    gross_salary: Heildarlaun
    personal_allowance_usage: 1.0 = 100% usage, 0.5 = 50% usage
    """
    # 1. Deduct Pension and Union
    pension = gross_salary * PENSION_RATE
    union = gross_salary * UNION_RATE
    tax_base = gross_salary - pension - union
    
    # 2. Calculate Income Tax
    # Simplified Tier 1 calculation (covers wages up to ~446k ISK)
    # If you earn more, we would need Tier 2 logic, but this is a good estimator.
    income_tax = tax_base * TAX_RATE_1
    
    # 3. Apply Personal Allowance
    allowance = PERSONAL_ALLOWANCE * personal_allowance_usage
    final_tax = max(0, income_tax - allowance)
    
    # 4. Net Salary
    net_salary = tax_base - final_tax
    
    return {
        "gross": gross_salary,
        "pension": pension,
        "union": union,
        "tax_base": tax_base,
        "income_tax_calc": income_tax,
        "allowance": allowance,
        "final_tax": final_tax,
        "net_salary": net_salary
    }

# --- LOGIN SYSTEM ---
def check_login(staff_code):
    df_users = get_data("Users")
    if df_users.empty:
        st.error("⚠️ Villa: Gat ekki lesið 'Users' flipann.")
        return None
    
    df_users['StaffCode'] = df_users['StaffCode'].astype(str).str.strip()
    clean_code = str(staff_code).strip()
    user_row = df_users[df_users['StaffCode'] == clean_code]
    
    if not user_row.empty:
        return user_row.iloc[0]['Name']
    return None

# Session State
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_code = ""

# --- LOGIN SCREEN ---
if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br><br><h1 style='text-align: center;'>🔐</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Launa CRM Innskráning</h3>", unsafe_allow_html=True)
        with st.form("login_form"):
            input_code = st.text_input("Starfsmannanúmer", type="password")
            if st.form_submit_button("Skrá inn"):
                st.cache_data.clear()
                name = check_login(input_code)
                if name:
                    st.session_state.logged_in = True
                    st.session_state.user_code = str(input_code).strip()
                    st.session_state.user_name = name
                    st.rerun()
                else:
                    st.error("🚫 Rangt númer.")
    st.stop() 

# =========================================================
# === MAIN APP ===
# =========================================================

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    st.caption(f"ID: {st.session_state.user_code}")
    menu = st.radio("Valmynd", ["🔥 Dagurinn í dag", "📊 Mælaborð", "💰 Launaseðill", "💾 Gagnagrunnur"])
    st.markdown("---")
    daily_goal = st.number_input("Dagsmarkmið:", value=150000, step=10000)
    monthly_goal = st.number_input("Mánaðarmarkmið:", value=600000, step=50000)
    st.markdown("---")
    if st.button("🚪 Útskráning"):
        st.session_state.logged_in = False
        st.session_state.user_code = ""
        st.rerun()

def get_my_data(tab_name):
    df = get_data(tab_name)
    if df.empty: return df
    if 'StaffCode' in df.columns:
        df['StaffCode'] = df['StaffCode'].astype(str).str.strip()
        return df[df['StaffCode'] == st.session_state.user_code]
    return df

# --- 1. LIVE DAY & END SHIFT (MERGED) ---
if menu == "🔥 Dagurinn í dag":
    st.header(f"📅 Vaktin í dag: {datetime.now().strftime('%d. %B')}")
    
    # --- A. LIVE DASHBOARD ---
    df_sales = get_my_data("Sales")
    today_sales = pd.DataFrame()
    if not df_sales.empty and 'Timestamp' in df_sales.columns:
        df_sales['Timestamp'] = pd.to_datetime(df_sales['Timestamp'])
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_sales = df_sales[df_sales['Timestamp'].dt.strftime("%Y-%m-%d") == today_str].copy()

    cur_sales = today_sales['Amount'].sum() if not today_sales.empty else 0
    sale_count = len(today_sales)
    avg_sale = cur_sales / sale_count if sale_count > 0 else 0
    
    # Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Sala í dag", f"{cur_sales:,.0f}", help="Heildarsala safnað í dag")
    m2.metric("📦 Fjöldi sala", sale_count)
    m3.metric("📈 Meðalsala", f"{avg_sale:,.0f} kr")
    
    prog = min(1.0, cur_sales/daily_goal) if daily_goal > 0 else 0
    m4.metric("🎯 Markmið", f"{prog*100:.0f}%")
    st.progress(prog)
    
    st.markdown("---")
    
    # --- B. SALES ENTRY ---
    c_left, c_right = st.columns([1, 1])
    
    with c_left:
        st.subheader("➕ Skrá sölu")
        with st.form("add_sale_form", clear_on_submit=True): # clear_on_submit makes it ready for next sale
            c1, c2 = st.columns([2,1])
            amt = c1.number_input("Upphæð (kr)", step=1000, min_value=0)
            note = c2.text_input("Skýring (valfrjálst)")
            
            if st.form_submit_button("💾 Vista Sölu", type="primary"):
                if amt > 0:
                    now = datetime.now()
                    row = [st.session_state.user_code, str(now), now.strftime("%H:%M"), amt, note]
                    append_row("Sales", row)
                    st.toast(f"Sala skráð: {amt:,.0f} kr", icon="✅")
                    time.sleep(1) # Give API a moment
                    st.rerun()    # Force refresh dashboard
    
    with c_right:
        st.subheader("📝 Nýlegar færslur")
        if not today_sales.empty:
            st.dataframe(today_sales[['Time', 'Amount', 'Note']].sort_values('Time', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Engar sölur skráðar í dag.")

    st.markdown("---")

    # --- C. END SHIFT SECTION ---
    st.header("🏁 Loka Vakt (End Shift)")
    st.markdown("Þegar vaktinni er lokið, fylltu út tímana hér að neðan. Heildarsalan fyllist út sjálfkrafa.")
    
    with st.container():
        with st.form("end_shift_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                date_in = st.date_input("Dagsetning", value=datetime.now())
                # Auto-fill sales from the live dashboard
                final_sales = st.number_input("Heildarsala (Sjálfvirkt)", value=int(cur_sales), step=1000)
            with col_b:
                d_hrs = st.number_input("Dagvinna (klst)", step=0.5, min_value=0.0)
                e_hrs = st.number_input("Kvöldvinna (klst)", step=0.5, min_value=0.0)
            
            # Preview Calculation
            if d_hrs > 0 or e_hrs > 0:
                p_w, p_b, p_t = calculate_pay(d_hrs, e_hrs, final_sales)
                st.caption(f"💰 Áætluð laun fyrir vaktina: **{p_t:,.0f} kr**")
            
            if st.form_submit_button("💾 Loka Vakt & Vista Laun"):
                w, b, t = calculate_pay(d_hrs, e_hrs, final_sales)
                mon = get_wage_month(date_in)
                row = [st.session_state.user_code, str(date_in), d_hrs, e_hrs, final_sales, w, b, t, mon]
                append_row("Wages", row)
                st.balloons()
                st.success(f"Vakt vistuð! Þú þénaðir {t:,.0f} kr í dag.")
                time.sleep(2)
                st.rerun()

# --- 2. STATS ---
elif menu == "📊 Mælaborð":
    st.header("📈 Mælaborð")
    df_wages = get_my_data("Wages")
    if not df_wages.empty and 'WageMonth' in df_wages.columns:
        months = sorted(df_wages['WageMonth'].unique().tolist(), reverse=True)
        sel_m = st.selectbox("Veldu Mánuð", months) if months else None
        
        if sel_m:
            m_data = df_wages[df_wages['WageMonth'] == sel_m]
            if not m_data.empty:
                tot_pay = m_data['Total'].sum()
                tot_bonus = m_data['Bonus'].sum()
                tot_hours = m_data['DayHrs'].sum() + m_data['EveHrs'].sum()
                avg_hr = tot_pay / tot_hours if tot_hours > 0 else 0
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Heildarlaun", f"{tot_pay:,.0f}")
                c2.metric("Bónusar", f"{tot_bonus:,.0f}")
                c3.metric("Unnir tímar", f"{tot_hours:.1f}")
                c4.metric("Meðaltímakaup", f"{avg_hr:,.0f} kr")
                
                st.progress(min(1.0, tot_pay/monthly_goal))
                
                # Chart
                if 'Date' in m_data.columns:
                    m_data['DateObj'] = pd.to_datetime(m_data['Date'])
                    m_data = m_data.sort_values('DateObj')
                    fig = px.bar(m_data, x='Date', y=['Wage', 'Bonus'], title="Dagleg laun", color_discrete_map={'Wage': '#29B6F6', 'Bonus': '#66BB6A'})
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Engin gögn fyrir þennan mánuð.")
    else:
        st.info("Engin launagögn fundust.")

# --- 3. PAYSLIP (LAUNASEÐILL) ---
elif menu == "💰 Launaseðill":
    st.header("🧾 Reiknivél: Áætluð Útborgun")
    st.markdown("Hér getur þú séð áætluð útborguð laun eftir skatt.")
    
    df_wages = get_my_data("Wages")
    
    if not df_wages.empty and 'WageMonth' in df_wages.columns:
        months = sorted(df_wages['WageMonth'].unique().tolist(), reverse=True)
        sel_m = st.selectbox("Veldu Launatímabil", months)
        
        if sel_m:
            m_data = df_wages[df_wages['WageMonth'] == sel_m]
            total_gross = m_data['Total'].sum()
            
            # Allow user to toggle Personal Allowance
            use_allowance = st.toggle("Nota Persónuafslátt? (100%)", value=True)
            usage_ratio = 1.0 if use_allowance else 0.0
            
            # Calculate
            pay_details = calculate_net_salary(total_gross, usage_ratio)
            
            # DISPLAY RECEIPT STYLE
            col_L, col_R = st.columns([1, 1])
            
            with col_L:
                st.subheader("Laun")
                st.markdown(f"**Heildarlaun:** {pay_details['gross']:,.0f} kr")
                st.markdown("---")
                st.write(f"Lífeyrissjóður ({PENSION_RATE*100}%): -{pay_details['pension']:,.0f} kr")
                st.write(f"Stéttarfélag ({UNION_RATE*100}%): -{pay_details['union']:,.0f} kr")
                st.markdown(f"**Skattstofn:** {pay_details['tax_base']:,.0f} kr")
                
            with col_R:
                st.subheader("Skattar")
                st.write(f"Reiknaður skattur: {pay_details['income_tax_calc']:,.0f} kr")
                st.write(f"Persónuafsláttur: -{pay_details['allowance']:,.0f} kr")
                st.markdown(f"**Skattur til greiðslu:** {pay_details['final_tax']:,.0f} kr")
                
            st.divider()
            st.metric("💵 ÚTBORGAÐ (Netto)", f"{pay_details['net_salary']:,.0f} kr")
            st.caption("*Ath: Þetta er áætlun. Endanlegur launaseðill gæti verið örlítið frábrugðinn.*")
            
    else:
        st.info("Engin gögn til að reikna.")

# --- 4. DB ---
elif menu == "💾 Gagnagrunnur":
    st.header("🗄️ Mín Gögn")
    tab1, tab2 = st.tabs(["Laun", "Sala"])
    with tab1: st.dataframe(get_my_data("Wages"), use_container_width=True)
    with tab2: st.dataframe(get_my_data("Sales"), use_container_width=True)
