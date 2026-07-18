import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from setlist_engine import SetlistEngine, compile_gemini_prompt
# Import the pass-through function from your new module
from llm_service import call_gemini_engine

def get_gspread_client(credentials_file="credentials.json"):
    """Handles authentication and returns an authorized gspread client."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    return gspread.authorize(creds)

def load_all_data(sheet_name="Master Songs and Venues"):
    """
    Connects to the master Google Sheet and reads all three required tabs
    into individual Pandas DataFrames.
    """
    print(f"Connecting to Google Sheets: '{sheet_name}'...")
    client = get_gspread_client()
    spreadsheet = client.open(sheet_name)
    
    # Extract tabs as distinct DataFrames
    print("Loading data tabs...")
    songs_df = pd.DataFrame(spreadsheet.worksheet("Songs w metadata").get_all_records())
    venues_df = pd.DataFrame(spreadsheet.worksheet("Venues w metadata").get_all_records())
    history_df = pd.DataFrame(spreadsheet.worksheet("Gig history").get_all_records())
    
    print(f"Successfully loaded {len(songs_df)} songs, {len(venues_df)} venues, and {len(history_df)} history rows.")
    return songs_df, venues_df, history_df

def main():
    # 1. Initialize data layer (only load from Sheets once)
    try:
        df_songs, df_venues, df_history = load_all_data()
    except Exception as e:
        print(f"\n[ERROR] Failed to fetch data from Google Sheets: {e}")
        print("Ensure 'credentials.json' exists and has access to the spreadsheet.")
        return

    # 2. Instantiate the execution engine
    engine = SetlistEngine(df_songs, df_venues, df_history)

    # 3. Define test scenarios for automated pipeline debugging
    SCENARIOS = [
        {
            "name": "Standard 3-Set Rock Show (Tuning Progression Test)",
            "venue": "HARVEST MOON",
            "gig_type": "3-set typical",
            "modifiers": {"FAMILY_FRIENDLY": False, "CLASSIC": True, "90s": True, "DANCY": True, "FUNBLOCK": True},
            "fun_block_size": 6
        },
        {
            "name": "Family Friendly Single Set (Medley Banned Intercept Test)",
            "venue": "HARVEST MOON",
            "gig_type": "1-set flat only",
            "modifiers": {"FAMILY_FRIENDLY": True, "CLASSIC": True, "90s": False, "DANCY": True, "FUNBLOCK": True},
            "fun_block_size": 6
        }
    ]

    # --- Start Scenario Testing Pipeline Loop ---
    for scenario in SCENARIOS:
        # Extract scenario-specific variables to feed the engine layers
        current_venue = scenario["venue"]
        current_gig_type = scenario["gig_type"]
        current_modifiers = scenario["modifiers"].copy() # shallow copy to protect the definition dictionary
        current_funblock_size = scenario["fun_block_size"]

        print(f"\n======================================================================")
        print(f"🏃 RUNNING SCENARIO: {scenario['name']}")
        print(f"======================================================================")

        # --- Gig Type & Modifier Compatibility Intercept ---
        banned_funblock_gig_types = [
            "1-set standard only",
            "1-set acoustic only",
            "2-set acoustic only",
            "2-set w. acoustic first, standard second",
            "3-set w. acoustic first"
        ]

        # Force override the modifier if an incompatible gig type is active
        if current_gig_type.lower().strip() in banned_funblock_gig_types:
            if current_modifiers.get('FUNBLOCK'):
                print(f"[Pipeline Notice] Overriding 'FUNBLOCK' to False. Medleys are disabled for gig type: '{current_gig_type}'.")
                current_modifiers['FUNBLOCK'] = False
                current_funblock_size = 0

        print(f"\n--- Running Pipeline Debugger ---")
        print(f"Venue: {current_venue}")
        print(f"Gig Type: {current_gig_type}")
        print(f"Modifiers: { {k: v for k, v in current_modifiers.items() if v} }")
        print(f"Fun Block Size: {current_funblock_size if current_modifiers['FUNBLOCK'] else 'N/A'}")
        print("---------------------------------\n")

        # 4. Run Tier 1: Hard Filters
        print("[Engine] Executing Tier 1: Global Filters...")
        filtered_pool = engine.apply_tier1_filters(current_venue, current_gig_type, current_modifiers)
        print(f"-> Remaining eligible songs: {len(filtered_pool)}")

        # 5 & 6. Run Tier 3 (which now loops Tier 2 dynamic context internally)
        print("[Engine] Executing Tier 3: Contextual Scoring & Structural Bucketing...")
        set_menus, set_lengths = engine.build_set_pools(
            filtered_pool, 
            current_venue,
            current_gig_type, 
            current_modifiers, 
            fun_block_size=current_funblock_size
        )

        # 7. Compile Prompt Payload
        print("[Engine] Building prompt compiler markup payload...")
        final_prompt = compile_gemini_prompt(set_menus, set_lengths, current_gig_type, current_modifiers)

        # 8. Print Output to Terminal
        print("\n======================= COMPILED GEMINI PROMPT =======================")
        print(final_prompt)
        print("======================================================================\n")

        # 9. Live API Handshake
        print("📡 Sending engine-generated payload to Gemini API...")
        try:
            system_rules = "You are the live music director for the rock band Electric Junkyard. Adhere strictly to the structural formatting rules provided."
            
            generated_setlist = call_gemini_engine(system_rules, final_prompt)
            
            print("\n⚡🎸 === GEMINI GENERATED SETLIST LIVE OUTPUT === 🎸⚡")
            print(generated_setlist)
            print("=========================================================\n")
            
        except Exception as e:
            print(f"\n❌ API Call failed for scenario '{scenario['name']}': {e}")
            print("Ensure your .env file is loaded and contains GEMINI_API_KEY.")
            
        print(f"🏁 Finished Scenario: {scenario['name']}\n")

if __name__ == "__main__":
    main()