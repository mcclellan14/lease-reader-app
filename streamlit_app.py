
import streamlit as st
import fitz  # PyMuPDF
import tempfile
import os
import openai
import ast
import re
import gspread
import json
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Lease Reader", layout="centered")
st.title("📄 Lease Reader")
st.markdown("Upload one or more lease PDFs and extract key lease data to Google Sheets.")

api_key = st.sidebar.text_input("🔑 Enter your OpenAI API key", type="password")
if not api_key:
    st.warning("Please enter your OpenAI API key in the sidebar.")
    st.stop()
openai.api_key = api_key

json_path = "/mount/lease-reader-service-account.json"
if not os.path.exists(json_path):
    st.error("Google Sheets credentials file not found.")
    st.stop()

with open(json_path) as f:
    key_data = json.load(f)

creds = Credentials.from_service_account_info(key_data, scopes=[
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])
gc = gspread.authorize(creds)
sheet_url = "https://docs.google.com/spreadsheets/d/1eySt6Xk3PP7WBHvGMt-yEhagbxsnJnW2pKj8iBZ62kw"
worksheet = gc.worksheet("Lease extraction")

prompt_template = (
    "Extract the following lease information from the text below:\n"
    "- Effective Date\n"
    "- Landlord\n"
    "- Tenant\n"
    "- Leased Premises (unit numbers, e.g., 13, 14)\n"
    "- Leased Premises Address\n"
    "- Square Footage (sum if more than one unit, numbers only, no labels like 'sq. ft.')\n"
    "- Security Deposit\n"
    "- Possession Date\n"
    "- Commencement Date\n"
    "- Term (Years)\n"
    "- Minimum Rent Year 1 to Year 10 (in $/sf, calculated from total square footage)\n"
    "- Renewal Option\n"
    "- Permitted Use\n"
    "- Insurance Requirement\n"
    "- Fixturing Period\n"
    "- Signage Rent\n"
    "- Parking Rent\n"
    "- Right of First Refusal\n\n"
    "Return exactly one row as a Python list. Each field must be wrapped in double quotes to prevent commas from splitting fields.\n\n"
    "Use consistent formatting:\n"
    "- All dates must be written as 'Month D, YYYY' (e.g., June 1, 2025)\n"
    "- Minimum Rent values must be formatted as dollar amounts, e.g., $19.00\n"
    "- Lease terms must be expressed as numbers (e.g., 5 not 'FIVE')\n"
    "- Leased Premises must be described by unit name/number, not just a count\n\n"
    "If the lease is shorter than 10 years, leave the remaining minimum rent year fields as empty strings ("").\n"
    "Do not include any explanation before or after the list.\n\n"
    "Order: Effective Date, Landlord, Tenant, Leased Premises, Leased Premises Address, Square Footage, Security Deposit, "
    "Possession Date, Commencement Date, Term (Years), Minimum Rent Year 1 ($/sf), Minimum Rent Year 2 ($/sf), "
    "Minimum Rent Year 3 ($/sf), Minimum Rent Year 4 ($/sf), Minimum Rent Year 5 ($/sf), Minimum Rent Year 6 ($/sf), "
    "Minimum Rent Year 7 ($/sf), Minimum Rent Year 8 ($/sf), Minimum Rent Year 9 ($/sf), Minimum Rent Year 10 ($/sf), "
    "Renewal Option, Permitted Use, Insurance Requirement, Fixturing Period, Signage Rent, Parking Rent, Right of First Refusal\n\n"
    "TEXT:\n\"\"\"\n{lease_text}\n\"\"\""
)

uploaded_files = st.file_uploader("📤 Upload lease PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files and api_key:
    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        text = ""
        with fitz.open(tmp_path) as doc:
            for page in doc:
                text += page.get_text("text")

        prompt = prompt_template.format(lease_text=text)

        try:
            response = openai.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                st.error(f"❌ No valid list found in GPT response for {uploaded_file.name}")
                continue
            parsed = ast.literal_eval(match.group(0))
            worksheet.append_row(parsed, value_input_option="USER_ENTERED")
            st.success(f"✅ {uploaded_file.name} processed and added to Google Sheet.")
        except Exception as e:
            st.error(f"❌ Error processing {uploaded_file.name}: {e}")
