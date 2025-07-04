import streamlit as st
import fitz  # PyMuPDF
import gspread
import ast
import time
import re
from openai import OpenAI
from google.oauth2.service_account import Credentials
from transformers import GPT2TokenizerFast

# TITLE
st.title("📄 Lease Reader")

# Upload lease PDFs
uploaded_files = st.file_uploader("Upload one or more lease PDFs", type=["pdf"], accept_multiple_files=True)

# Load credentials from Streamlit secrets
key_data = st.secrets["GOOGLE_CREDENTIALS"]
creds = Credentials.from_service_account_info(
    key_data,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)

# Connect to Google Sheets
gc = gspread.authorize(creds)
sheet_url = "https://docs.google.com/spreadsheets/d/1eySt6Xk3PP7WBHvGMt-yEhagbxsnJnW2pKj8iBZ62kw"
worksheet = gc.open_by_url(sheet_url).worksheet("Lease extraction")

# Initialize OpenAI
openai_api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=openai_api_key)

# Tokenizer for estimating token length
tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

# Prompt template
prompt_template = '''Extract the following lease information from the text below:
- Effective Date
- Landlord
- Tenant
- Leased Premises (unit numbers, e.g., 13, 14)
- Leased Premises Address
- Square Footage (sum if more than one unit, just show number, e.g., 1,234)
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
- Square Footage must be a number with commas, e.g., 6,540 (no 'sq. ft.' text)

If the lease is shorter than 10 years, leave the remaining minimum rent year fields as empty strings (""). 
Do not include any explanation before or after the list.

Order: Effective Date, Landlord, Tenant, Leased Premises, Leased Premises Address, Square Footage, Security Deposit, Possession Date, Commencement Date, Term (Years), Minimum Rent Year 1 ($/sf), Minimum Rent Year 2 ($/sf), Minimum Rent Year 3 ($/sf), Minimum Rent Year 4 ($/sf), Minimum Rent Year 5 ($/sf), Minimum Rent Year 6 ($/sf), Minimum Rent Year 7 ($/sf), Minimum Rent Year 8 ($/sf), Minimum Rent Year 9 ($/sf), Minimum Rent Year 10 ($/sf), Renewal Option, Permitted Use, Insurance Requirement, Fixturing Period, Signage Rent, Parking Rent, Right of First Refusal

TEXT:
"""
{lease_text}
"""
'''

def extract_text_from_pdf(file):
    text = ""
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text")
    return text

if uploaded_files:
    for uploaded_file in uploaded_files:
        st.write(f"📄 Processing: {uploaded_file.name}")
        lease_text = extract_text_from_pdf(uploaded_file)

        # Token check
        num_tokens = len(tokenizer.encode(lease_text))
        st.write(f"🔢 Token count: {num_tokens}")
        if num_tokens > 12000:
            st.warning(f"⚠️ Skipping {uploaded_file.name}: too large for GPT-4.")
            continue

        # Fill in prompt
        prompt = prompt_template.format(lease_text=lease_text)

        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048
            )
            list_line = response.choices[0].message.content.strip()

            # Extract the list safely
            match = re.search(r"\[.*\]", list_line, re.DOTALL)
            if not match:
                st.error(f"❌ Could not find list format in GPT response.")
                continue
            cleaned_output = match.group(0)

            try:
                row = ast.literal_eval(cleaned_output)
                worksheet.append_row(row, value_input_option="USER_ENTERED")
                st.success("✅ Lease data added to Google Sheet.")
            except Exception as parse_error:
                st.error(f"⚠️ Failed to parse GPT output: {parse_error}")
                continue

            time.sleep(6)  # for OpenAI rate limits

        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.info("🎉 All leases processed.")
    
