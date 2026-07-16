import streamlit as st
import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from google import genai
# Import your dynamic sheet loader and your engine functions
from setlist_engine import SetlistEngine, generate_llm_prompt
from main import load_catalog_from_sheets

load_dotenv()

st.set_page_config(page_title="Electric Junkyard Setlist AI", layout="wide", page_icon="🎸")
st.title("🎸 Electric Junkyard Setlist Engine")

# Cache the Google Sheets data fetch so it doesn't slam your API quota on every button click
@st.cache_data(ttl=300) # Caches data for 5 minutes, then refreshes
def fetch_live_data():
    try:
        # Load your sheets using the gspread auth function we created
        songs_df = load_catalog_from_sheets(sheet_name="Master Songs and Venues", worksheet_name="Songs w metadata")
        venues_df = load_catalog_from_sheets(sheet_name="Master Songs and Venues", worksheet_name="Venues w metadata")
        history_df = load_catalog_from_sheets(sheet_name="Master Songs and Venues", worksheet_name="Gig history")
        return SetlistEngine(songs_df, venues_df, history_df)
    except Exception as e:
        st.error(f"Failed to securely sync with Google Drive: {e}")
        return None

# Initialize the backend engine with the live sheets
engine = fetch_live_data()

if engine is not None:
    # Sidebar or Left Column: Control Board Configuration
    col1, col2 = st.columns([1, 2])

    with col1:
        st.header("🎛️ Gig Settings")
        
        # Pull the live list of venues directly from your spreadsheet column
        venue_list = engine.venues_df['NAME'].tolist()
        selected_venue = st.selectbox("Select Venue Target", options=venue_list)
        
        show_format = st.selectbox(
            "Show Format Structure",
            options=[
                "3-Set Show: Standard (Default)",
                "1-Set Show: Fast Gig",
                "2-Set Show: Medium Gig"
            ]
        )
        
        st.divider()
        st.subheader("⚡ Style Modifiers")
        c_rock = st.checkbox("Classic Rock Heavy (70s Boost)")
        nineties = st.checkbox("90s Alternative Heavy")
        dancy = st.checkbox("Super Dancy / High Energy Focus")
        f_friendly = st.checkbox("Force Family-Friendly Override")
        acoustic = st.checkbox("Add Acoustic Block (Pull 'YES' & 'BOTH' Tracks)")
        
        st.divider()
        st.subheader("🔥 Medley Controls")
        fun = st.checkbox("Include 'Fun Block' Medley", value=True)
        long_fun = st.checkbox("Long Fun Block (Include Extra Middles)", disabled=not fun)
        
        st.divider()
        user_comments = st.text_area(
            "Live Human Directives for Tonight", 
            placeholder="e.g., 'Drummer's wrist is sore, ease up on fast tempos' or 'Put a birthday toast in Set 2'"
        )
        
        generate_btn = st.button("🚀 Generate AI Setlist", type="primary")

    with col2:
        st.header("📋 Live Stage Layout Output")
        
        if generate_btn:
            if not os.environ.get("GEMINI_API_KEY"):
                st.error("Missing GEMINI_API_KEY in your local environment setup.")
            else:
                # Compile parameters into modifiers dictionary
                modifiers = {
                    'classic_rock_heavy': c_rock,
                    'nineties_heavy': nineties,
                    'high_energy_dancy': dancy,
                    'force_family_friendly': f_friendly,
                    'add_acoustic_block': acoustic,
                    'include_fun_block': fun,
                    'long_fun_block': long_fun
                }
                
                # Run the backend gatekeeper filtering & scoring
                # (Assumes your function signature matches what we built previously)
                with st.spinner("Python filtering your catalog & streaming parameters to Gemini..."):
                    draft_data = engine.generate_setlist(selected_venue, show_format, modifiers, datetime.now())
                    venue_profile = engine.venues_df[engine.venues_df['NAME'] == selected_venue].iloc[0].to_dict()
                    
                    # Generate the rich structural prompt payload
                    full_prompt = generate_llm_prompt(draft_data, venue_profile, user_comments, show_format)
                    
                    try:
                        # Initialize Google GenAI client and stream the content
                        client = genai.Client()
                        response = client.models.generate_content(
                            model='gemini-3.1-flash-lite',
                            #model='gemini-2.5-flash',
                            #model='gemini-3.5-flash',
                            contents=full_prompt,
                        )
                        
                        st.success(f"Show order generated successfully for {selected_venue}!")
                        
                        # Display the raw Markdown response natively in the UI
                        st.markdown(response.text)
                        
                        st.divider()
                        # Add a quick structural wrapper for easy copying
                        st.subheader("📥 Export Setlist Options")
                        st.text_area("Click inside to copy raw text layout:", value=response.text, height=250)
                        
                    except Exception as api_err:
                        st.error(f"Gemini API returned an operational error. Server might be under load (503). Specifics: {api_err}")
else:
    st.info("Awaiting structural synchronization with Google Drive...")