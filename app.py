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
    /* Bonus Meter Styling */
    .stProgress > div > div > div > div {
        background-color: #00C853;
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

# --- DATA HANDLING ---
@st.cache_data(ttl=0)
def get_data_with_index(worksheet_name):
    client = get_gsheet_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_values()
        if not data: return pd.DataFrame()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
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
    client = get_gsheet_client()
    if not client: return False
    try:
        sheet = client.open_by_key(SHEET_ID)
        ws = sheet.worksheet(worksheet_name)
        clean_values = []
        for v in new_values:
            if isinstance(v, (int, float)): clean_values.append(v)
            else: clean_values.append(str(v))
        for i, val in enumerate(clean_values):
            ws.update_cell(row_id, i+1, val)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Update Error: {e}")
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

# --- HELPER: GET DATA ---
def get_my_data(tab_name):
    df = get_data_with_index(tab_name)
    if df.empty: return df
    if 'StaffCode' in df.columns:
        df['StaffCode'] = df['StaffCode'].astype(str).str.strip()
        if tab_name == "Wages":
            cols_to_num = ['DayHrs', 'EveHrs', 'Sales', 'Wage', 'Bonus', 'Total']
            for c in cols_to_num:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        elif tab_name == "Sales":
             if 'Amount' in df.columns: df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        return df[df['StaffCode'] == st.session_state.user_code]
    return df

# --- SIDEBAR (With Gamification) ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    st.caption(f"ID: {st.session_state.user_code}")
    
    # 🏆 FEATURE 4: PERSONAL BEST (Gamification)
    # We calculate this once on load
    df_all_wages = ge
