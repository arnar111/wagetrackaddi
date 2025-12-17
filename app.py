import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

st.title("🔍 Debugging Google Sheets")

# 1. Connect
try:
    if "google_credentials_json" in st.secrets:
        secrets = json.loads(st.secrets["google_credentials_json"])
    elif "gcp_service_account" in st.secrets:
        secrets = dict(st.secrets["gcp_service_account"])
        if "private_key" in secrets:
            secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")
            
    creds = Credentials.from_service_account_info(secrets, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    
    # 2. Open Sheet
    SHEET_NAME = "Launa_DB" # Make sure this matches exactly
    sheet = client.open(SHEET_NAME)
    
    # 3. List all tabs
    worksheets = sheet.worksheets()
    st.write(f"✅ Connected to: **{SHEET_NAME}**")
    st.write("📂 Tabs found:")
    
    found_users = False
    for ws in worksheets:
        st.write(f"- `{ws.title}`")
        if ws.title == "Users":
            found_users = True
            
    if found_users:
        st.success("🎉 I CAN see the 'Users' tab!")
        # Try to read it
        data = sheet.worksheet("Users").get_all_records()
        st.write("Data inside Users:")
        st.write(data)
    else:
        st.error("❌ I CANNOT see 'Users'.")
        st.info("Try renaming the tab to something else (e.g. 'Staff') and back to 'Users' in Google Sheets.")

except Exception as e:
    st.error(f"Error: {e}")
