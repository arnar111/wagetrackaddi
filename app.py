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
SHEET_ID = "1BUiNj316whIeXoSvuHmpUfYgBHb4HbPkO4cZu_PEPI8" 

# WAGE CONSTANTS
RATE_DAY = 2797.0
RATE_EVE = 3768.47
DEDUCTION_RATE = 636.0
OFFSET_HOURS = 1.0
MONTH_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Maí", 6: "Jún", 7: "Júl", 8: "Ágú", 9: "Sep", 10: "Okt", 11: "Nóv", 12: "Des"}

# TAX CONSTANTS
PENSION_RATE = 0.04        
UNION_RATE = 0.007         
TAX_RATE_1 = 0.3145        
PERSONAL_ALLOWANCE = 64926 

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

# --- DATA HANDLING WITH ROW TRACKING ---
@st.cache_data(ttl=0)
def get_data_with_index(worksheet_name):
    """
    Fetches data but preserves the Row Number so we can edit it later.
    """
    client = get_gsheet_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        # get_all_values returns a list of lists (Raw Data)
        data = ws.get_all_values()
        
        if not data: return pd.DataFrame()
        
        headers = data[0]
        rows = data[1:]
        
        # Create DF
        df = pd.DataFrame(rows, columns=headers)
        
        # Add a hidden column "_row_id" (Index + 2 because Google Sheets starts at 1 and has headers)
        df['_row_id'] = range(2, len(rows) + 2)
        
        return df
    except:
        return pd.DataFrame()

def append_row(worksheet_name, row_data):
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False

def update_row(worksheet_name, row_id, new_values):
    """Updates a specific row in Google Sheets"""
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        
        # Identify range (e.g., A5:H5) based on length of data
        # 'Wages' has 9 columns (A to I)
        # 'Sales' has 5 columns (A to E)
        col_count = len(new_values)
        
        # Convert list to simple types (int/float/str) to avoid JSON errors
        clean_values = []
        for v in new_values:
            if isinstance(v, (int, float)):
                clean_values.append(v)
            else:
                clean_values.append(str(v))

        # Update the row
        # gspread uses (row, col) coordinates. Col 1 is A.
        for i, val in enumerate(clean_values):
            ws.update_cell(row_id, i+1, val)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Update Error: {e}")
        return False

def delete_row(worksheet_name, row_id):
    """Deletes a specific row"""
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        ws.delete_rows(row_id)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Delete Error: {e}")
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
    pension = gross_salary * PENSION_RATE
    union = gross_salary * UNION_RATE
    tax_base = gross_salary - pension - union
    income_tax = tax_base * TAX_RATE_1
    allowance = PERSONAL_ALLOWANCE * personal_allowance_usage
    final_tax = max(0, income_tax - allowance)
    net_salary = tax_base - final_tax
    return {
        "gross": gross_salary, "pension": pension, "union": union,
        "tax_base": tax_base, "income_tax_calc": income_tax,
        "allowance": allowance, "final_tax": final_tax, "net_salary": net_salary
    }

# --- LOGIN ---
def check_login(staff_code):
    # Use get_data_with_index but ignore index for login
    df_users = get_data_with_index("Users")
    if df_users.empty: return None
    df_users['StaffCode'] = df_users['StaffCode'].astype(str).str.strip()
    clean_code = str(staff_code).strip()
    user_row = df_users[df_users['StaffCode'] == clean_code]
    return user_row.iloc[0]['Name'] if not user_row.empty else None

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_code = ""

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center;'>🔐</h1>", unsafe_allow_html=True)
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
                    st.error("Rangt númer.")
    st.stop() 

# --- MAIN APP ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    st.caption(f"ID: {st.session_state.user_code}")
    menu = st.radio("Valmynd", ["🔥 Dagurinn í dag", "📊 Mælaborð", "💰 Launaseðill", "💾 Gagnagrunnur"])
    st.markdown("---")
    daily_goal = st.number_input("Dagsmarkmið:", value=150000, step=10000)
    monthly_goal = st.number_input("Mánaðarmarkmið:", value=600000, step=50000)
    st.markdown("---")
    if st.button("🚪 Útskráning"):
        st.session_state.logged_in = False; st.rerun()

# Helper to filter data for current user
def get_my_data(tab_name):
    df = get_data_with_index(tab_name)
    if df.empty: return df
    
    # Ensure correct types
    if 'StaffCode' in df.columns:
        df['StaffCode'] = df['StaffCode'].astype(str).str.strip()
        # Convert numeric columns to numbers safely
        if tab_name == "Wages":
            cols_to_num = ['DayHrs', 'EveHrs', 'Sales', 'Wage', 'Bonus', 'Total']
            for c in cols_to_num:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        elif tab_name == "Sales":
             if 'Amount' in df.columns: df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)

        return df[df['StaffCode'] == st.session_state.user_code]
    return df

# --- 1. LIVE DAY ---
if menu == "🔥 Dagurinn í dag":
    st.header(f"📅 Vaktin í dag: {datetime.now().strftime('%d. %B')}")
    
    # FETCH DATA
    df_sales = get_my_data("Sales")
    today_sales = pd.DataFrame()
    
    if not df_sales.empty and 'Timestamp' in df_sales.columns:
        df_sales['TimestampObj'] = pd.to_datetime(df_sales['Timestamp'], errors='coerce')
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_sales = df_sales[df_sales['TimestampObj'].dt.strftime("%Y-%m-%d") == today_str].copy()

    # METRICS
    cur_sales = today_sales['Amount'].sum() if not today_sales.empty else 0
    sale_count = len(today_sales)
    avg_sale = cur_sales / sale_count if sale_count > 0 else 0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Sala í dag", f"{cur_sales:,.0f}")
    m2.metric("📦 Fjöldi sala", sale_count)
    m3.metric("📈 Meðalsala", f"{avg_sale:,.0f} kr")
    
    prog = min(1.0, cur_sales/daily_goal) if daily_goal > 0 else 0
    m4.metric("🎯 Markmið", f"{prog*100:.0f}%")
    st.progress(prog)
    st.markdown("---")
    
    # SALES ENTRY
    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.subheader("➕ Skrá sölu")
        with st.form("add_sale_form", clear_on_submit=True):
            c1, c2 = st.columns([2,1])
            amt = c1.number_input("Upphæð (kr)", step=1000, min_value=0)
            note = c2.text_input("Skýring")
            if st.form_submit_button("💾 Vista Sölu", type="primary"):
                if amt > 0:
                    now = datetime.now()
                    # Row: StaffCode, Timestamp, Time, Amount, Note
                    row = [st.session_state.user_code, str(now), now.strftime("%H:%M"), amt, note]
                    append_row("Sales", row)
                    st.toast(f"Sala skráð: {amt:,.0f} kr", icon="✅")
                    time.sleep(1); st.rerun()
    
    with c_right:
        st.subheader("📝 Nýlegar færslur")
        if not today_sales.empty:
            st.dataframe(today_sales[['Time', 'Amount', 'Note']].sort_values('Time', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Engar sölur skráðar í dag.")

    st.markdown("---")
    st.header("🏁 Loka Vakt")
    with st.container():
        with st.form("end_shift_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                date_in = st.date_input("Dagsetning", value=datetime.now())
                final_sales = st.number_input("Heildarsala (Sjálfvirkt)", value=int(cur_sales), step=1000)
            with col_b:
                d_hrs = st.number_input("Dagvinna (klst)", step=0.5, min_value=0.0)
                e_hrs = st.number_input("Kvöldvinna (klst)", step=0.5, min_value=0.0)
            
            if st.form_submit_button("💾 Loka Vakt & Vista Laun"):
                w, b, t = calculate_pay(d_hrs, e_hrs, final_sales)
                mon = get_wage_month(date_in)
                # Row: StaffCode, Date, DayHrs, EveHrs, Sales, Wage, Bonus, Total, WageMonth
                row = [st.session_state.user_code, str(date_in), d_hrs, e_hrs, final_sales, w, b, t, mon]
                append_row("Wages", row)
                st.balloons(); st.success(f"Vakt vistuð! {t:,.0f} kr."); time.sleep(2); st.rerun()

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
                tot_pay = m_data['Total'].sum(); tot_bonus = m_data['Bonus'].sum()
                tot_hours = m_data['DayHrs'].sum() + m_data['EveHrs'].sum()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Heildarlaun", f"{tot_pay:,.0f}"); c2.metric("Bónusar", f"{tot_bonus:,.0f}")
                c3.metric("Unnir tímar", f"{tot_hours:.1f}"); c4.metric("Vaktir", len(m_data))
                st.progress(min(1.0, tot_pay/monthly_goal))
                if 'Date' in m_data.columns:
                    m_data['DateObj'] = pd.to_datetime(m_data['Date'])
                    m_data = m_data.sort_values('DateObj')
                    fig = px.bar(m_data, x='Date', y=['Wage', 'Bonus'], title="Dagleg laun", color_discrete_map={'Wage': '#29B6F6', 'Bonus': '#66BB6A'})
                    st.plotly_chart(fig, use_container_width=True)
            else: st.info("Engin gögn.")
    else: st.info("Engin launagögn fundust.")

# --- 3. PAYSLIP ---
elif menu == "💰 Launaseðill":
    st.header("🧾 Reiknivél")
    df_wages = get_my_data("Wages")
    if not df_wages.empty and 'WageMonth' in df_wages.columns:
        months = sorted(df_wages['WageMonth'].unique().tolist(), reverse=True)
        sel_m = st.selectbox("Veldu Launatímabil", months)
        if sel_m:
            m_data = df_wages[df_wages['WageMonth'] == sel_m]
            total_gross = m_data['Total'].sum()
            use_allowance = st.toggle("Nota Persónuafslátt? (100%)", value=True)
            pd_tax = calculate_net_salary(total_gross, 1.0 if use_allowance else 0.0)
            
            cL, cR = st.columns(2)
            with cL:
                st.subheader("Laun")
                st.write(f"Heildarlaun: **{pd_tax['gross']:,.0f} kr**")
                st.write(f"Lífeyrissjóður: -{pd_tax['pension']:,.0f} kr")
                st.write(f"Stéttarfélag: -{pd_tax['union']:,.0f} kr")
                st.write(f"Skattstofn: {pd_tax['tax_base']:,.0f} kr")
            with cR:
                st.subheader("Skattar")
                st.write(f"Reiknaður skattur: {pd_tax['income_tax_calc']:,.0f} kr")
                st.write(f"Persónuafsláttur: -{pd_tax['allowance']:,.0f} kr")
                st.write(f"Skattur til greiðslu: {pd_tax['final_tax']:,.0f} kr")
            st.divider()
            st.metric("💵 ÚTBORGAÐ", f"{pd_tax['net_salary']:,.0f} kr")
    else: st.info("Engin gögn.")

# --- 4. DB (EDITABLE) ---
elif menu == "💾 Gagnagrunnur":
    st.header("🗄️ Breyta Gögnum")
    st.info("Hér getur þú breytt tölum eða eytt línum. Laun uppfærast sjálfkrafa við vistun.")

    tab1, tab2 = st.tabs(["Laun (Wages)", "Sala (Sales)"])
    
    # --- WAGES EDITOR ---
    with tab1:
        df_w = get_my_data("Wages")
        
        if not df_w.empty:
            # Configure columns for the editor
            # We hide calculated columns from editing to prevent bad math
            col_config = {
                "_row_id": None, # Hide ID
                "StaffCode": None, # Hide User ID
                "Wage": st.column_config.NumberColumn(disabled=True),
                "Bonus": st.column_config.NumberColumn(disabled=True),
                "Total": st.column_config.NumberColumn(disabled=True),
                "WageMonth": st.column_config.TextColumn(disabled=True),
            }
            
            # Show Editor
            edited_df = st.data_editor(
                df_w, 
                key="wages_editor", 
                num_rows="dynamic", # Allows adding/deleting rows
                column_config=col_config,
                use_container_width=True
            )
            
            if st.button("💾 Vista Breytingar á Launum", type="primary"):
                # Logic: Compare old vs new, or just process updates
                # Since Streamlit editor handles the state, we just iterate the edited_df
                
                with st.status("Vist breytingar...", expanded=True) as status:
                    # 1. Handle Deletions: Find rows in original missing in edited
                    # (Simplified: We just check updates for now. Deletions in GSheets via ID is tricky with dynamic editors)
                    # robust way: If the user used the trashcan icon, Streamlit returns a smaller DF.
                    
                    # For updates:
                    changes_count = 0
                    
                    # We iterate through the EDITED dataframe
                    for index, row in edited_df.iterrows():
                        # Get original ID
                        row_id = row['_row_id']
                        
                        # Recalculate Logic
                        d_hrs = float(row['DayHrs'])
                        e_hrs = float(row['EveHrs'])
                        sales = int(row['Sales'])
                        date_val = str(row['Date'])
                        
                        # Math
                        w, b, t = calculate_pay(d_hrs, e_hrs, sales)
                        w_mon = get_wage_month(date_val)
                        
                        # Prepare List for GSheets (Order matches Columns A-I)
                        # StaffCode, Date, DayHrs, EveHrs, Sales, Wage, Bonus, Total, WageMonth
                        update_list = [
                            st.session_state.user_code,
                            date_val,
                            d_hrs,
                            e_hrs,
                            sales,
                            w,
                            b,
                            t,
                            w_mon
                        ]
                        
                        # Update GSheets row
                        # Only update if valid row_id exists
                        if row_id > 0:
                            update_row("Wages", row_id, update_list)
                            changes_count += 1
                    
                    status.update(label=f"Uppfærði {changes_count} línur!", state="complete")
                    time.sleep(1)
                    st.rerun()
        else:
            st.warning("Engin launagögn til að breyta.")

    # --- SALES EDITOR ---
    with tab2:
        df_s = get_my_data("Sales")
        if not df_s.empty:
            col_config_s = {
                "_row_id": None, 
                "StaffCode": None
            }
            edited_sales = st.data_editor(df_s, key="sales_editor", column_config=col_config_s, num_rows="dynamic", use_container_width=True)
            
            if st.button("💾 Vista Breytingar á Sölu"):
                for index, row in edited_sales.iterrows():
                    row_id = row['_row_id']
                    # StaffCode, Timestamp, Time, Amount, Note
                    upd = [
                        st.session_state.user_code,
                        str(row['Timestamp']),
                        str(row['Time']),
                        int(row['Amount']),
                        str(row['Note'])
                    ]
                    if row_id > 0:
                        update_row("Sales", row_id, upd)
                st.success("Sölur uppfærðar!")
                time.sleep(1)
                st.rerun()
        else:
            st.info("Engar sölur til að breyta.")
