# Lease Reader Streamlit App
# Upload lease PDFs → extract summary with GPT-4 Turbo → push to Google Sheet

import streamlit as st
import fitz  # PyMuPDF
import gspread
import json
from google.oauth2.service_account import Credentials
from openai import OpenAI
import ast
import re
import time
import tempfile
import os

# --- SETUP ---
st.set_page_config(page_title="Lease Reader", layout="centered")
st.title("📄 Lease Reader")
st.caption("Upload commercial lease PDFs and extract key terms to Google Sheets")

# --- GOOGLE SHEETS SETUP ---
st.sidebar.header("🔐 Connect to Google Sheets")
with st.sidebar:
    uploaded_json = st.file_uploader("Upload Service Account JSON", type="json")
    sheet_url = st.text_input("Google Sheet URL", placeholder="Paste your Google Sheet URL here")

# --- OPENAI API SETUP ---
openai_key = st.sidebar.text_input("OpenAI API Key", type="password")

# --- FILE UPLOAD ---
pdf_files = st.file_uploader("Upload Lease PDF(s)", type="pdf", accept_multiple_files=True)
process_button = st.button("🔍 Extract Lease Data")

# --- PROMPT TEMPLATE ---
prompt_template = '''Extract the following lease information from the text below:
- Effective Date
- Landlord
- Tenant
- Leased Premises (unit numbers, e.g., 13, 14)
- Leased Premises Address
- Square Footage (sum if more than one unit)
- Security Deposit
- Possession Date
- Commencement Date
- Term (Years)
- Minimum Rent Year 1 to Year 10 (in $/sf, calculated from total square footage)
- Renewal Option
- Permitted Use
- Insurance Requirement
- Fixturing Period
- Signage Rent
- Parking Rent
- Right of First Refusal

Return exactly one row as a Python list. Each field must be wrapped in double quotes to prevent commas from splitting fields.

Use consistent formatting:
- All dates must be written as 'Month D, YYYY' (e.g., June 1, 2025)
- Minimum Rent values must be formatted as dollar amounts, e.g., $19.00
- Lease terms must be expressed as numbers (e.g., 5 not "FIVE")
- Leased Premises must be described by unit name/number, not just a count

If the lease is shorter than 10 years, leave the remaining minimum rent year fields as empty strings (""). 
Do not include any explanation before or after the list.

Order: Effective Date, Landlord, Tenant, Leased Premises, Leased Premises Address, Square Footage, Security Deposit, Possession Date, Commencement Date, Term (Years), Minimum Rent Year 1 ($/sf), Minimum Rent Year 2 ($/sf), Minimum Rent Year 3 ($/sf), Minimum Rent Year 4 ($/sf), Minimum Rent Year 5 ($/sf), Minimum Rent Year 6 ($/sf), Minimum Rent Year 7 ($/sf), Minimum Rent Year 8 ($/sf), Minimum Rent Year 9 ($/sf), Minimum Rent Year 10 ($/sf), Renewal Option, Permitted Use, Insurance Requirement, Fixturing Period, Signage Rent, Parking Rent, Right of First Refusal

TEXT:
"""
{lease_text}
"""
'''

# --- MAIN PROCESS ---
if process_button:
    if not uploaded_json or not sheet_url or not openai_key:
        st.warning("Please upload your service account, enter your Google Sheet URL, and API key.")
    elif not pdf_files:
        st.warning("Please upload at least one lease PDF.")
    else:
        key_data = json.load(uploaded_json)
        creds = Credentials.from_service_account_info(key_data, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        gc = gspread.authorize(creds)
        worksheet = gc.open_by_url(sheet_url).worksheet("Lease extraction")

        client = OpenAI(api_key=openai_key)

        for file in pdf_files:
            st.markdown(f"**Processing:** `{file.name}`")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            lease_text = ""
            with fitz.open(tmp_path) as doc:
                for page in doc:
                    lease_text += page.get_text("text")
            os.remove(tmp_path)

            prompt = prompt_template.format(lease_text=lease_text)
            try:
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048
                )
                content = response.choices[0].message.content.strip()
                match = re.search(r"\[.*\]", content, re.DOTALL)
                if not match:
                    st.error(f"❌ GPT failed to return a list for `{file.name}`")
                    continue
                row = ast.literal_eval(match.group(0))
                worksheet.append_row(row, value_input_option="USER_ENTERED")
                st.success(f"✅ Added to Google Sheet: `{file.name}`")
                time.sleep(6)
            except Exception as e:
                st.error(f"❌ Error processing `{file.name}`: {e}")
