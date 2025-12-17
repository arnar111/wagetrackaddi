import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Launa CRM Pro", 
    page_icon="💎", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM STYLING (CSS) ---
st.markdown("""
<style>
    div.stButton > button {
        width: 100%; 
        border-radius: 8px; 
        height: 3.5em; 
        font-weight: bold;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .big-font {font-size:20px !important;}
    [data-testid="stMetricValue"] {
        font-size: 32px; 
        color: #00C853; 
        font-weight: 600;
    }
    /* Card-like containers for cleaner look */
    div.stDataFrame {
        border: 1px solid #f0f2f6;
        border-radius: 8px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
RATE_DAY = 2797.0
RATE_EVE = 3768.47
DEDUCTION_RATE = 636.0
OFFSET_HOURS = 1.0
SHEET_NAME = "Launa_DB"  # Must match your Google Sheet name exactly
MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Maí", 6: "Jún", 
    7: "Júl", 8: "Ágú", 9: "Sep", 10: "Okt", 11: "Nóv", 12: "Des"
}

# --- GOOGLE SHEETS CONNECTION (FIXED) ---
@st.cache_resource
def get_gsheet_client():
    # 1. Load secrets as a standard dictionary
    secrets = dict(st.secrets["gcp_service_account"])
    
    # 2. THE FIX: Manually replace escaped newlines with actual newlines
    # This repairs the private_key string if TOML formatted it incorrectly
    if "private_key" in secrets:
        secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")

    # 3. Authenticate
    creds = Credentials.from_service_account_info(
        secrets,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)

def get_data(worksheet_name):
    """Fetch all data from a specific worksheet."""
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME)
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Villa við að sækja gögn: {e}")
        return pd.DataFrame()

def append_row(worksheet_name, row_data):
    """Append a list of values as a new row."""
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME)
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"Villa við vistun: {e}")
        return False

# --- BUSINESS LOGIC ---
def get_wage_month(date_obj):
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
        except:
            return "Unknown"
            
    # If 26th or later, it's the NEXT month
    if date_obj.day >= 26:
        next_month = date_obj.replace(day=1) + timedelta(days=32)
        return f"{next_month.year}-{next_month.month:02d} ({MONTH_MAP[next_month.month]})"
    return f"{date_obj.year}-{date_obj.month:02d} ({MONTH_MAP[date_obj.month]})"

def calculate_pay(day_h, eve_h, sales):
    wages = (day_h * RATE_DAY) + (eve_h * RATE_EVE)
    total_h = day_h + eve_h
    threshold = max(0, (total_h - OFFSET_HOURS) * DEDUCTION_RATE)
    bonus = max(0, sales - threshold)
    return wages, bonus, (wages + bonus)

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("💎 Launa CRM")
    st.caption("v2.0 - Google Sheets Edition")
    
    menu = st.radio("Valmynd", [
        "🔥 Dagurinn í dag (Live)", 
        "📊 Mælaborð (Stats)", 
        "📝 Skrá Vakt (End Shift)", 
        "💾 Gagnagrunnur"
    ])
    
    st.markdown("---")
    st.subheader("🎯 Markmið")
    daily_goal = st.number_input("Daglegt Sölumarkmið:", value=150000, step=10000)
    monthly_goal = st.number_input("Mánaðarlegt Launamarkmið:", value=600000, step=50000)

# --- 1. LIVE DAY DASHBOARD ---
if menu == "🔥 Dagurinn í dag (Live)":
    st.header(f"📅 Dagurinn í dag: {datetime.now().strftime('%d. %B')}")
    
    # 1. Fetch Sales for Today
    df_sales = get_data("Sales")
    if not df_sales.empty:
        df_sales['Timestamp'] = pd.to_datetime(df_sales['Timestamp'])
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_sales = df_sales[df_sales['Timestamp'].dt.strftime("%Y-%m-%d") == today_str].copy()
    else:
        today_sales = pd.DataFrame()

    # 2. Metrics
    current_sales = today_sales['Amount'].sum() if not today_sales.empty else 0
    sales_count = len(today_sales)
    
    # Progress towards daily goal
    prog = min(1.0, current_sales / daily_goal) if daily_goal > 0 else 0
    remaining = max(0, daily_goal - current_sales)
    
    # Layout Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Sala í dag", f"{current_sales:,.0f} kr", f"{remaining:,.0f} kr eftir")
    col2.metric("📦 Fjöldi sala", sales_count)
    col3.metric("🎯 Dagsskilvirkni", f"{prog*100:.0f}%")
    
    st.progress(prog)

    # 3. Add New Sale Form
    st.markdown("### ➕ Skrá nýja sölu")
    with st.container():
        with st.form("add_sale"):
            c1, c2 = st.columns([2, 1])
            with c1:
                sale_amount = st.number_input("Upphæð (kr)", min_value=0, step=1000, value=0)
            with c2:
                sale_note = st.text_input("Skýring (Valfrjálst)")
            
            if st.form_submit_button("Staðfesta Sölu"):
                if sale_amount > 0:
                    now = datetime.now()
                    # Append to Google Sheet "Sales" tab
                    # Columns: Timestamp, Time, Amount, Note
                    row = [str(now), now.strftime("%H:%M"), sale_amount, sale_note]
                    if append_row("Sales", row):
                        st.success(f"✅ Sala skráð: {sale_amount} kr")
                        st.rerun() # Refresh to update numbers immediately
                else:
                    st.warning("Upphæð verður að vera hærri en 0.")

    # 4. Recent Transactions Table
    if not today_sales.empty:
        st.markdown("### 🕒 Sölusaga í dag")
        st.dataframe(
            today_sales[['Time', 'Amount', 'Note']].sort_values('Time', ascending=False),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Engar sölur skráðar í dag.")

# --- 2. MAIN STATS DASHBOARD ---
elif menu == "📊 Mælaborð (Stats)":
    st.header("📈 Yfirlit Launa")
    df_wages = get_data("Wages")
    
    if df_wages.empty:
        st.info("Engin launagögn skráð ennþá. Farðu í 'Skrá Vakt' til að byrja.")
    else:
        # Month Filter
        if 'WageMonth' in df_wages.columns:
            all_months = sorted(df_wages['WageMonth'].unique().tolist(), reverse=True)
            sel_month = st.selectbox("Veldu Tímabil:", all_months)
            m_data = df_wages[df_wages['WageMonth'] == sel_month].copy()
        else:
            st.error("Dálkurinn 'WageMonth' fannst ekki í gögnunum.")
            m_data = pd.DataFrame()
        
        if not m_data.empty:
            tot_pay = m_data['Total'].sum()
            tot_bonus = m_data['Bonus'].sum()
            tot_sales = m_data['Sales'].sum()
            tot_wage = m_data['Wage'].sum()
            
            # Big Cards
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Heildarlaun", f"{tot_pay:,.0f}", help="Grunnlaun + Bónus")
            c2.metric("Bónusar", f"{tot_bonus:,.0f}", delta=f"{tot_bonus/tot_pay*100:.0f}% af heild")
            c3.metric("Heildarsala", f"{tot_sales:,.0f}")
            c4.metric("Vaktir", len(m_data))
            
            st.write(f"Mánaðarmarkmið: {monthly_goal:,.0f} kr")
            st.progress(min(1.0, tot_pay/monthly_goal))
            
            st.divider()

            # Charts
            col_chart1, col_chart2 = st.columns([2,1])
            with col_chart1:
                # Wages over time area chart
                m_data['DateObj'] = pd.to_datetime(m_data['Date'])
                m_data = m_data.sort_values('DateObj')
                fig = px.bar(m_data, x='Date', y=['Wage', 'Bonus'], title="Samsetning Launa",
                              labels={'value': 'Krónur', 'variable': 'Tegund'},
                              color_discrete_map={'Wage': '#29B6F6', 'Bonus': '#66BB6A'})
                st.plotly_chart(fig, use_container_width=True)
            
            with col_chart2:
                # Donut Chart
                fig_pie = px.donut(
                    values=[tot_wage, tot_bonus], 
                    names=['Grunnlaun', 'Bónus'], 
                    title="Hlutfall Bónusa",
                    color_discrete_sequence=['#29B6F6', '#66BB6A'],
                    hole=0.4
                )
                st.plotly_chart(fig_pie, use_container_width=True)

# --- 3. END SHIFT (WAGE ENTRY) ---
elif menu == "📝 Skrá Vakt (End Shift)":
    st.header("🏁 Loka Vakt & Reikna Laun")
    
    # Auto-fetch today's sales
    df_sales = get_data("Sales")
    today_str = datetime.now().strftime("%Y-%m-%d")
    auto_sales = 0
    
    if not df_sales.empty:
        df_sales['Timestamp'] = pd.to_datetime(df_sales['Timestamp'])
        # Filter sales that happened today
        mask = df_sales['Timestamp'].dt.strftime("%Y-%m-%d") == today_str
        auto_sales = df_sales[mask]['Amount'].sum()
        
    with st.form("shift_form"):
        st.subheader("Upplýsingar um vaktina")
        col1, col2 = st.columns(2)
        with col1:
            date_in = st.date_input("Dagsetning", value=datetime.now())
            sales_in = st.number_input(
                "Heildarsala (kr)", 
                value=int(auto_sales), 
                step=1000, 
                help="Sækir sjálfkrafa sölu dagsins úr Live kerfinu ef hún er til"
            )
        with col2:
            d_hrs = st.number_input("Dagvinna (klst)", step=0.5, value=0.0)
            e_hrs = st.number_input("Kvöldvinna (klst)", step=0.5, value=0.0)
            
        submit = st.form_submit_button("💾 Vista Vakt í Grunn")
        
        if submit:
            # Calculate
            w, b, t = calculate_pay(d_hrs, e_hrs, sales_in)
            w_month = get_wage_month(date_in)
            
            # Prepare row: Date, DayHrs, EveHrs, Sales, Wage, Bonus, Total, WageMonth
            row_data = [
                str(date_in), 
                d_hrs, 
                e_hrs, 
                sales_in, 
                w, 
                b, 
                t, 
                w_month
            ]
            
            if append_row("Wages", row_data):
                st.balloons()
                st.success(f"Vakt vistuð! Þú þénaðir {t:,.0f} kr í dag (Mánuður: {w_month}).")
            
    # Live Preview
    st.info("💡 Sláðu inn tölur til að sjá útreikning hér að neðan áður en þú vistar.")
    prev_w, prev_b, prev_t = calculate_pay(d_hrs, e_hrs, sales_in)
    c1, c2, c3 = st.columns(3)
    c1.metric("Grunnlaun", f"{prev_w:,.0f}")
    c2.metric("Bónus", f"{prev_b:,.0f}")
    c3.metric("SAMTALS", f"{prev_t:,.0f}")

# --- 4. DATABASE (Fancy View) ---
elif menu == "💾 Gagnagrunnur":
    st.header("🗄️ Gagnagrunnur (Google Sheets)")
    
    tab1, tab2 = st.tabs(["💰 Launaskrá (Wages)", "🧾 Söluyfirlit (Sales)"])
    
    with tab1:
        df_w = get_data("Wages")
        if not df_w.empty:
            # Sort by Date descending
            if 'Date' in df_w.columns:
                df_w = df_w.sort_values('Date', ascending=False)
                
            st.data_editor(
                df_w,
                column_config={
                    "Total": st.column_config.NumberColumn("Heildarlaun", format="%d kr"),
                    "Bonus": st.column_config.NumberColumn("Bónus", format="%d kr"),
                    "Sales": st.column_config.ProgressColumn(
                        "Sala", 
                        format="%f", 
                        min_value=0, 
                        max_value=int(df_w['Sales'].max()) if df_w['Sales'].max() > 0 else 100000
                    ),
                },
                use_container_width=True,
                num_rows="dynamic",
                key="wages_editor"
            )
            st.caption("Ath: Breytingar hér vistast ekki sjálfkrafa í Google Sheets í þessari útgáfu (Read-only view).")
        else:
            st.warning("Engin gögn í 'Wages' flipanum.")

    with tab2:
        df_s = get_data("Sales")
        if not df_s.empty:
            st.dataframe(
                df_s.sort_values("Timestamp", ascending=False), 
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("Engin gögn í 'Sales' flipanum.")
