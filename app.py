import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Launa CRM",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM STYLING (CSS) ---
# This injects CSS to give it that "Sleek CRM" card look
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 24px;
        color: #00CC96;
    }
    div.stButton > button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #4CAF50; 
        color: white;
    }
    .main {
        background-color: #f5f5f5;
    }
    /* Card styling for containers */
    div.css-1r6slb0 {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION & CONSTANTS ---
RATE_DAY = 2797.0
RATE_EVE = 3768.47
DEDUCTION_RATE = 636.0
OFFSET_HOURS = 1.0
DATA_FILE = 'wage_data.csv'

MONTH_MAP = {
    1: "Janúar", 2: "Febrúar", 3: "Mars", 4: "Apríl", 5: "Maí", 6: "Júní",
    7: "Júlí", 8: "Ágúst", 9: "September", 10: "Október", 11: "Nóvember", 12: "Desember"
}

# --- LOGIC FUNCTIONS ---
def get_wage_month(date_obj):
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

def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=['Date', 'DayHrs', 'EveHrs', 'Sales', 'Wage', 'Bonus', 'Total', 'WageMonth'])
    return pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("📊 Launa CRM")
    st.markdown("---")
    menu = st.radio("Valmynd", ["Mælaborð (Dashboard)", "Skrá nýja vakt", "Gagnagrunnur"])
    st.markdown("---")
    
    # Monthly Goal Setting
    st.subheader("🎯 Mánaðarlegt Markmið")
    monthly_goal = st.number_input("Launamarkmið (kr)", value=500000, step=10000)

# --- MAIN APP LOGIC ---
df = load_data()

# 1. DASHBOARD PAGE
if menu == "Mælaborð (Dashboard)":
    st.header("📈 Yfirlit & Tölfræði")
    
    if df.empty:
        st.info("Engin gögn fundust. Byrjaðu á að skrá vakt í valmyndinni.")
    else:
        # Filter by Month
        all_months = sorted(df['WageMonth'].unique().tolist(), reverse=True)
        selected_month = st.selectbox("Veldu Launatímabil:", all_months)
        
        # Filter Data
        month_data = df[df['WageMonth'] == selected_month]
        
        if not month_data.empty:
            # CALCULATIONS
            total_pay = month_data['Total'].sum()
            total_bonus = month_data['Bonus'].sum()
            total_hours = month_data['DayHrs'].sum() + month_data['EveHrs'].sum()
            avg_hourly = total_pay / total_hours if total_hours > 0 else 0
            
            # --- TOP METRICS ROW ---
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Heildarlaun", f"{total_pay:,.0f} kr", delta=f"{total_pay/monthly_goal*100:.1f}% af markmiði")
            col2.metric("Bónusar", f"{total_bonus:,.0f} kr", delta_color="off")
            col3.metric("Unnir tímar", f"{total_hours:.1f} klst")
            col4.metric("Meðallaun/klst", f"{avg_hourly:,.0f} kr")
            
            # --- PROGRESS BAR ---
            st.write(f"Markmið: {monthly_goal:,.0f} kr")
            progress = min(1.0, total_pay / monthly_goal)
            st.progress(progress)
            
            # --- CHARTS ROW ---
            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.subheader("Launa Samsetning")
                # Prepare data for stacked bar
                chart_data = month_data.copy()
                chart_data['Date'] = pd.to_datetime(chart_data['Date'])
                chart_data = chart_data.sort_values('Date')
                
                fig = px.bar(chart_data, x='Date', y=['Wage', 'Bonus'], 
                             title="Dagleg laun (Grunnlaun vs Bónus)",
                             labels={'value': 'Krónur', 'variable': 'Tegund'},
                             color_discrete_map={'Wage': '#2E86C1', 'Bonus': '#28B463'})
                st.plotly_chart(fig, use_container_width=True)
                
            with c2:
                st.subheader("Hlutfall Bónusa")
                wage_share = month_data['Wage'].sum()
                bonus_share = month_data['Bonus'].sum()
                
                fig_pie = px.donut(values=[wage_share, bonus_share], names=['Grunnlaun', 'Bónus'], 
                                   color_discrete_sequence=['#2E86C1', '#28B463'], hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

# 2. ENTRY PAGE
elif menu == "Skrá nýja vakt":
    st.header("📝 Skráning Vaktar")
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.form("entry_form"):
            date_input = st.date_input("Dagsetning")
            day_hrs = st.number_input("Dagvinna (klst)", min_value=0.0, step=0.5)
            eve_hrs = st.number_input("Kvöldvinna (klst)", min_value=0.0, step=0.5)
            sales = st.number_input("Sala (kr)", min_value=0, step=1000)
            
            submitted = st.form_submit_button("💾 Vista Vakt")
            
            if submitted:
                # Calc
                w, b, t = calculate_pay(day_hrs, eve_hrs, sales)
                w_month = get_wage_month(date_input)
                
                new_row = {
                    'Date': date_input,
                    'DayHrs': day_hrs, 
                    'EveHrs': eve_hrs, 
                    'Sales': sales,
                    'Wage': w, 
                    'Bonus': b, 
                    'Total': t,
                    'WageMonth': w_month
                }
                
                # Update DF
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df)
                st.success(f"Vakt skráð! Heildarlaun: {t:,.0f} kr")
                
    with col2:
        # Live Calculator Preview
        st.info("💡 Reiknivél (Preview)")
        calc_w, calc_b, calc_t = calculate_pay(day_hrs, eve_hrs, sales)
        st.markdown(f"""
        **Áætluð laun fyrir þessa vakt:**
        * Grunnlaun: {calc_w:,.0f} kr
        * Bónus: {calc_b:,.0f} kr
        * **Samtals: {calc_t:,.0f} kr**
        """)

# 3. DATABASE PAGE
elif menu == "Gagnagrunnur":
    st.header("📋 Öll Gögn")
    
    # Download Button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Sækja Excel/CSV", data=csv, file_name="laun_gogn.csv", mime="text/csv")
    
    # Editable Dataframe
    st.markdown("Hér getur þú breytt eða eytt færslum (hakaðu við til að eyða).")
    
    # Show data with latest first
    edited_df = st.data_editor(
        df.sort_index(ascending=False), 
        num_rows="dynamic",
        use_container_width=True
    )
    
    # Save changes logic (if edited)
    if not edited_df.equals(df.sort_index(ascending=False)):
        # Re-sort to original before saving to maintain order logic if needed
        # But usually we just overwrite
        save_data(edited_df.sort_index())
        st.toast("Breytingar vistaðar!", icon="✅")
