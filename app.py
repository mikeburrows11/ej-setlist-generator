import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import streamlit.components.v1 as components
import os

# --- LIGHTWEIGHT CRON PING CATCHER ---
# If cron-job.org hits the app, it stops here
if st.query_params.get("ping") == "true":
    st.text("Pong! Engine is awake.")
    st.stop()

# Import your existing engine modules
from setlist_engine import SetlistEngine, compile_gemini_prompt, compile_audit_prompt
from llm_service import call_gemini_engine

# Set up page configurations optimized for mobile screens
st.set_page_config(
    page_title="Electric Junkyard Setlist Engine",
    page_icon="🎸",
    layout="centered"
)

# Initialize Session State variables to prevent reruns from wiping out generated work
if "generated_setlist" not in st.session_state:
    st.session_state["generated_setlist"] = None
if "final_display_text" not in st.session_state:
    st.session_state["final_display_text"] = ""
if "parsed_history_rows" not in st.session_state:
    st.session_state["parsed_history_rows"] = []
if "extracted_commentary" not in st.session_state:
    st.session_state["extracted_commentary"] = ""
if "prompt_debugger_payload" not in st.session_state:
    st.session_state["prompt_debugger_payload"] = {"pass1": "", "pass2": ""}

# 1. Cached Data Layer (avoids hammering Google Sheets on every UI click)
@st.cache_data(show_spinner=False)
def load_all_data_cached(sheet_name="Master Songs and Venues"):
    """Connects to Google Sheets and caches the resulting DataFrames."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    #creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    creds = Credentials.from_service_account_info(st.secrets["gspread_credentials"], scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open(sheet_name)
    
    songs_df = pd.DataFrame(spreadsheet.worksheet("Songs w metadata").get_all_records())
    venues_df = pd.DataFrame(spreadsheet.worksheet("Venues w metadata").get_all_records())
    history_df = pd.DataFrame(spreadsheet.worksheet("Gig history").get_all_records())
    
    return songs_df, venues_df, history_df

def append_gig_history_to_sheet(rows, sheet_name="Master Songs and Venues"):
    """Writes the parsed performance tracks directly back to the Google Sheet tab."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open(sheet_name)
    worksheet = spreadsheet.worksheet("Gig history")
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

# App Title
logo_filename = "EJ_LogoFinal_3_smaller.png"

if os.path.exists(logo_filename):
    # Renders the logo centered and fluidly scales down on mobile viewports
    st.image(logo_filename, use_container_width=True)
else:
    # Safe fallback just in case the filename changes or is missing in production
    st.title("⚡🎸 Electric Junkyard")

st.markdown("## Setlist Engine")
st.caption("Data-driven live show optimization orchestrated by Gemini")
st.markdown("---")

# Initialize data layer
try:
    with st.spinner("Fetching latest sheets data..."):
        df_songs, df_venues, df_history = load_all_data_cached()
    st.sidebar.success(f"Loaded: {len(df_songs)} Songs | {len(df_venues)} Venues")
except Exception as e:
    st.error(f"❌ Failed to connect to Google Sheets: {e}")
    st.stop()

# Instantiate the engine
engine = SetlistEngine(df_songs, df_venues, df_history)

# 2. Sidebar Configuration Controls
st.sidebar.header("🎛️ Gig Parameters")

# Venue Select (Updated to lookup the correct "NAME" column key)
venue_list = df_venues["NAME"].unique().tolist() if "NAME" in df_venues.columns else ["HARVEST MOON"]
selected_venue = st.sidebar.selectbox("Select Venue", venue_list)

# Date Selector Parameter (Kept locally, insulated from prompt compilation)
selected_date = st.sidebar.date_input("Gig Date", datetime.date.today())
formatted_date_str = selected_date.strftime("%m/%d/%Y")

# Explicit Layout Target Configurations List
gig_types = [
    "3-set typical",
    "3-set w. extended standard",
    "3-set w. acoustic block in set 2",
    "3-set w. acoustic first",
    "2-set typical",
    "2-set w. acoustic first, standard second",
    "2-set w. acoustic first, flat second",
    "2-set acoustic only",
    "1-set mixed",
    "1-set standard only",
    "1-set flat only",
    "1-set acoustic only"
]
selected_gig_type = st.sidebar.selectbox("Gig Layout Type", gig_types)

banned_funblock_gig_types = [
            "1-set standard only",
            "1-set acoustic only",
            "2-set acoustic only",
            "2-set w. acoustic first, standard second",
            "3-set w. acoustic first"
        ]

# Determine medley compatibility dynamically
#is_medley_banned = "1-set" in selected_gig_type.lower() or "acoustic only" in selected_gig_type.lower()
is_medley_banned = selected_gig_type in banned_funblock_gig_types

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Active Set Modifiers")

ui_modifiers = {
    "FAMILY_FRIENDLY": st.sidebar.checkbox("Family Friendly Filter", value=False),
    "CLASSIC": st.sidebar.checkbox("Classic Rock Heavy", value=False),
    "90s": st.sidebar.checkbox("90s Alternative Heavy", value=False),
    "DANCY": st.sidebar.checkbox("Dancy / Groovy", value=False)
}

# Automatically uncheck and grey out medley configuration rules for restricted layouts
if is_medley_banned:
    st.sidebar.checkbox("Include Fun Block Medley", value=False, disabled=True, help="Medleys are disabled for single-set or pure acoustic layouts.")
    active_funblock = False
    active_funblock_size = 0
else:
    active_funblock = st.sidebar.checkbox("Include Fun Block Medley", value=True)
    active_funblock_size = st.sidebar.slider("Fun Block Medley Track Count", min_value=4, max_value=8, value=6, disabled=not active_funblock)

active_modifiers = ui_modifiers.copy()
active_modifiers["FUNBLOCK"] = active_funblock

st.sidebar.markdown("---")
if st.sidebar.button("Clear App Cache"):
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()

# 3. Main Interface Strategy Metadata Blocks
st.subheader("📋 Show Pipeline Strategy")
with st.container(border=True):
    st.markdown(f"**📍 Venue:** {selected_venue}")
    st.markdown(f"**📅 Date:** {formatted_date_str}")
    st.markdown(f"**🎸 Layout Type:** {selected_gig_type}")
    st.markdown(f"**🔀 Medley Status:** {f'Enabled ({active_funblock_size} tracks)' if active_funblock else 'Disabled'}")

st.markdown("")

# Custom Gig Notes passed directly into the first-pass LLM prompt
additional_context = st.text_area(
    "📝 Additional Gig Instructions (Optional)", 
    placeholder="e.g., Make Set 3 extra high energy, or emphasize grunge rock tracks..."
)

# 4. Action Engine Execution
if st.button("🚀 Sequence and Generate Setlist", type="primary", use_container_width=True):
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        status_text.markdown("ℹ️ *Running Tier 1: Executing hard filters...*")
        progress_bar.progress(25)
        filtered_pool = engine.apply_tier1_filters(selected_venue, selected_gig_type, active_modifiers)
        
        status_text.markdown("ℹ️ *Running Tier 3: Calculating structural boundaries...*")
        progress_bar.progress(50)
        set_menus, set_lengths = engine.build_set_pools(
            filtered_pool, 
            selected_venue,
            selected_gig_type, 
            active_modifiers, 
            fun_block_size=active_funblock_size
        )
        
        status_text.markdown("ℹ️ *Compiling prompt payload...*")
        progress_bar.progress(55)
        final_prompt = compile_gemini_prompt(set_menus, set_lengths, selected_gig_type, active_modifiers, additional_context)
        # Store Pass 1 raw prompt structure for the hidden box
        st.session_state["prompt_debugger_payload"]["pass1"] = final_prompt
        
        # --- PASS 1 INITIAL RUN ---
        status_text.markdown("📡 *Transmitting payload to Gemini API (Pass 1: Creation)...*")
        progress_bar.progress(75)
        
        p1_system_rules = "You are the live music director for the rock band Electric Junkyard. Output ONLY uppercase song names grouped under uppercase SET headers, and add a short commentary block at the end (starting with ###), detailing the actions you took."
        raw_llm_response = call_gemini_engine(p1_system_rules, final_prompt)
        
        # --- PASS 2 CRITIC RUN ---
        status_text.markdown("🕵️‍♂️ *Executing Pass 2: Rigorous constraint validation audit...*")
        progress_bar.progress(90)
        
        p2_audit_prompt = compile_audit_prompt(raw_llm_response, df_songs)
        # Store Pass 2 raw prompt structure for the hidden box
        st.session_state["prompt_debugger_payload"]["pass2"] = p2_audit_prompt
        
        p2_system_rules = "You are a technical setlist sorting engine. Output the final formatted uppercase text block matching the formatting laws and add a short commentary block at the end (starting with ###), detailing any actions you took."
        final_audited_output = call_gemini_engine(p2_system_rules, p2_audit_prompt)

        # Clear progress tracking states
        progress_bar.empty()
        status_text.empty()
        
        # --- PARSE & SPLIT PERFORMANCE DATA FROM COMMENTARY ---
        p1_commentary = ""
        p2_commentary = ""
        clean_setlist_block = ""
        
        # Extract Pass 1 commentary
        if "###" in raw_llm_response:
            parts_p1 = raw_llm_response.split("###")
            p1_commentary = parts_p1[1].strip()
            
        # Extract Pass 2 list and commentary
        if "###" in final_audited_output:
            parts_p2 = final_audited_output.split("###")
            clean_setlist_block = parts_p2[0].strip()
            p2_commentary = parts_p2[1].strip()
        else:
            clean_setlist_block = final_audited_output.strip()
            
        # Format the combined commentary output block
        combined_commentary_text = ""
        if p1_commentary:
            combined_commentary_text += f"💬 **Pass 1 Director Insights:**\n{p1_commentary}\n\n"
        if p2_commentary:
            combined_commentary_text += f"🛡️ **Pass 2 Auditor Corrections:**\n{p2_commentary}"
            
        st.session_state["extracted_commentary"] = combined_commentary_text
        
        # Pre-pend structural header metadata to the clean setlist
        header_prefix = f"{selected_venue.upper()}: {formatted_date_str}\n\n"
        st.session_state["generated_setlist"] = clean_setlist_block
        st.session_state["final_display_text"] = header_prefix + clean_setlist_block
        
        # 5. Parse output rows into structured array to prepare sheet recording schema
        parsed_history = []
        current_set_context = "1"
        
        for line in clean_setlist_block.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            if "SET " in line_clean.upper():
                parts = line_clean.upper().split("SET ")
                if len(parts) > 1:
                    current_set_context = parts[1].strip()
                continue
            
            parsed_history.append([line_clean.upper(), current_set_context, selected_venue.upper(), formatted_date_str])
            
        st.session_state["parsed_history_rows"] = parsed_history
        st.success("🎉 Setlist optimized successfully!")
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Critical Pipeline Failure: {e}")

# 5. Output Management Console Area
if st.session_state["generated_setlist"]:
    st.subheader("🎸 Performance Setlist Output")
    
    # Render interactive code block displaying custom prepended layout tracking line
    st.code(st.session_state["final_display_text"], language="text")
    
    # Native browser cross-platform "Copy to Clipboard" implementation component
    js_copy_script = f"""
    <script>
    function copyText() {{
        const textToCopy = `{st.session_state["final_display_text"].replace('`', '\\`').replace('$', '\\$')}`;
        navigator.clipboard.writeText(textToCopy).then(() => {{
            parent.postMessage({{type: 'streamlit:success', message: 'Copied!'}}, '*');
        }}).catch(err => {{
            console.error('Could not copy text: ', err);
        }});
    }}
    </script>
    <button onclick="copyText()" style="
        width: 100%; 
        background-color: #f0f2f6; 
        color: #31333F; 
        border: 1px solid rgba(49, 51, 63, 0.2); 
        padding: 0.5rem 1rem; 
        border-radius: 4px; 
        cursor: pointer; 
        font-weight: 500;
        margin-bottom: 15px;
    ">📋 Copy Entire Setlist to Clipboard</button>
    """
    components.html(js_copy_script, height=50)
    
    st.markdown("---")
    st.subheader("💾 Data Synchronization")
    
    # Record database change transaction confirmation block button
    if st.button("✅ Confirm and Update Gig History", type="secondary", use_container_width=True):
        if st.session_state["parsed_history_rows"]:
            with st.spinner("Writing records back to Google Sheets..."):
                try:
                    append_gig_history_to_sheet(st.session_state["parsed_history_rows"])
                    st.toast("⚡ Google Sheets database successfully updated!", icon="💾")
                    st.success(f"Successfully tracked {len(st.session_state['parsed_history_rows'])} performance rows to the 'Gig history' tab!")
                    
                    # Clear out cache targets to force calculation loops refresh on subsequent updates
                    st.cache_data.clear()
                except Exception as write_err:
                    st.error(f"Failed writing data package to Google Sheet: {write_err}")
        else:
            st.warning("No parsed performance tracks discovered in execution memory to record.")
    
    # --- COMBINED ISOLATED COMMENTARY DISPLAYS ---
    if st.session_state["extracted_commentary"]:
        st.markdown("---")
        st.subheader("📝 Director & Auditor Commentary")
        with st.container(border=True):
            st.markdown(st.session_state["extracted_commentary"])
            
    # --- COLLAPSIBLE PROMPT DEBUGGER BLOCK ---
    if st.session_state["prompt_debugger_payload"]["pass1"]:
        st.markdown("")
        with st.expander("🛠️ View Compiled Prompt Payload Context (Hidden Options)"):
            st.subheader("Pass 1: Master Generation Prompt")
            st.text_area("Pass 1 Prompt Details", st.session_state["prompt_debugger_payload"]["pass1"], height=200, key="p1_debug_view")
            st.subheader("Pass 2: Zero-Tolerance Audit Prompt")
            st.text_area("Pass 2 Prompt Details", st.session_state["prompt_debugger_payload"]["pass2"], height=200, key="p2_debug_view")