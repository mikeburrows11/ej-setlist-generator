# main.py
import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from setlist_engine import SetlistEngine, generate_llm_prompt

load_dotenv()

def load_catalog_from_sheets(sheet_name, worksheet_name):
    # Define the scope of what the service account can access
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Authenticate using the credentials file
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    
    # Open the spreadsheet and pull the raw data
    spreadsheet = client.open(sheet_name)
    worksheet = spreadsheet.worksheet(worksheet_name)
    
    # Pull all records as a list of dictionaries, then convert to a DataFrame
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    
    return df

def generate_ai_setlist():
    # 1. Quick environment check to ensure the key is present
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ Error: GEMINI_API_KEY environment variable not set in .env file.")
        return

    print("--- 📂 Loading Master Sheet Data Tiers ---")
    # Load dataframes from your local files
    songs_df = load_catalog_from_sheets("Master Songs and Venues", "Songs w metadata")
    venues_df = load_catalog_from_sheets("Master Songs and Venues", "Venues w metadata")
    history_df = load_catalog_from_sheets("Master Songs and Venues", "Gig history")
    
    # Initialize your updated logic engine
    engine = SetlistEngine(songs_df, venues_df, history_df)
    
    # 2. Configure our target gig settings
    #venue_name = "THE PUB TIFTON"
    venue_name = "HARVEST MOON"
    show_format = "3-Set Show: Standard (Default)"
    
    modifiers = {
        'classic_rock_heavy': False,
        'nineties_heavy': True,        # Focus on 90s alternative
        'high_energy_dancy': True,     # Keep the bar moving
        'include_fun_block': True,     # Enable the Clutch -> Sublime medley
        'long_fun_block': False,       # 5 songs total (1 Beg + 3 Mid + 1 End)
        'add_acoustic_block': True,    # Give the drummer's wrist a short break
        'force_family_friendly': False  # Standard adult bar show rules apply
    }
    
    # Simulate human typing custom notes into a web UI context box
    user_comments = ""
    #user_comments = (
    #    "Our drummer's wrist is bothering him tonight, so make sure to spread out "
    #    "the hyper-fast songs like Green Day or Offspring. Put the Acoustic block "
    #    "right in the middle of Set 2 so he can fully rest for 10-12 minutes."
    #)
    
    # 3. Process the backend scoring and filtering
    print(f"--- ⚙️ Running Python Filtering & Scoring for '{venue_name}' ---")
    draft_data = engine.generate_setlist(venue_name, show_format, modifiers, datetime(2026, 7, 25))
    venue_profile = engine.venues_df[engine.venues_df['NAME'] == venue_name].iloc[0].to_dict()
    
    # Compile the rich tiered prompt payload
    full_prompt = generate_llm_prompt(draft_data, venue_profile, user_comments, show_format)

    print(full_prompt)
    
    # 4. Initialize the Gemini Client and stream the response
    print("--- 🚀 Transmitting Safe Song Pools to Gemini API ---")
    client = genai.Client()
    
    response = client.models.generate_content(
        #model='gemini-3.5-flash',
        #model='gemini-2.5-flash-lite',
        model='gemini-flash-latest',
        #model='gemini-2.5-flash',
        contents=full_prompt,
    )
    
    print("\n=======================================================")
    print("      🎸 FINAL AI-ALIGNED SETLIST FOR ELECTRIC JUNKYARD   ")
    print("=======================================================\n")
    print(response.text)

if __name__ == "__main__":
    generate_ai_setlist()