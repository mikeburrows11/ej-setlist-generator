import pandas as pd
import numpy as np
from datetime import datetime

# ---------------------------------------------------------
# GLOBAL ENGINE CONFIGURATIONS
# ---------------------------------------------------------
GIG_TYPES = {
    "3-set typical": {
        "set_length": 12,
        "set1": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"},
        "set2": {"tuning": "FLAT", "exclude_energy": 5, "acoustic": "N"},
        "set3": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "3-set w. extended standard": {
        "set_length": 12,
        "set1": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"},
        "set2": {"split": True, "partA": {"slots": 6, "tuning": "STANDARD", "exclude_energy": 5}, "partB": {"slots": 6, "tuning": "FLAT", "exclude_energy": 5}},
        "set3": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "3-set w. acoustic block in set 2": {
        "set_length": 12,
        "set1": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"},
        "set2": {"split": True, "partA": {"slots": 5, "acoustic": "ONLY"}, "partB": {"slots": 7, "tuning": "FLAT", "exclude_energy": 5}},
        "set3": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "3-set w. acoustic first": {
        "set_length": 12,
        "set1": {"acoustic": "ONLY"},
        "set2": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"},
        "set3": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "2-set typical": {
        "set_length": 15,
        "set1": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"},
        "set2": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "2-set w. acoustic first, standard second": {
        "set_length": 15,
        "set1": {"acoustic": "ONLY"},
        "set2": {"tuning": "STANDARD", "exclude_energy": None, "acoustic": "N"}
    },
    "2-set w. acoustic first, flat second": {
        "set_length": 15,
        "set1": {"acoustic": "ONLY"},
        "set2": {"tuning": "FLAT", "exclude_energy": None, "acoustic": "N"}
    },
    "2-set acoustic only": {
        "set_length": 15,
        "set1": {"tuning": "STANDARD", "acoustic": "ONLY"},
        "set2": {"tuning": "FLAT", "acoustic": "ONLY"}
    },
    "1-set mixed": {
        "set_length": 15,
        "set1": {"split": True, "partA": {"slots": 7, "tuning": "STANDARD"}, "partB": {"slots": 8, "tuning": "FLAT"}}
    },
    "1-set standard only": {
        "set_length": 15,
        "set1": {"tuning": "STANDARD"}
    },
    "1-set flat only": {
        "set_length": 15,
        "set1": {"tuning": "FLAT"}
    },
    "1-set acoustic only": {
        "set_length": 15,
        "set1": {"acoustic": "ONLY"}
    }
}


class SetlistEngine:
    def __init__(self, df_songs, df_venues, df_history):
        self.df_songs = df_songs.copy()
        self.df_venues = df_venues.copy()
        self.df_history = df_history.copy()
        self._prepare_data()

    def _prepare_data(self):
        self.df_songs['SONG_UPPER'] = self.df_songs['SONG'].str.strip().str.upper()
        self.df_history['SONG_UPPER'] = self.df_history['SONG'].str.strip().str.upper()
        self.df_history['DATE_DT'] = pd.to_datetime(self.df_history['DATE'], errors='coerce')
        self.df_songs['ENERGY'] = pd.to_numeric(self.df_songs['ENERGY'], errors='coerce').fillna(3)

    # ---------------------------------------------------------
    # TIER 1: GLOBAL FILTERS
    # ---------------------------------------------------------
    def apply_tier1_filters(self, venue_name, gig_type, modifiers):
        venue_info = self.df_venues[self.df_venues['NAME'] == venue_name]
        if venue_info.empty:
            raise ValueError(f"Venue '{venue_name}' not found.")
        
        venue = venue_info.iloc[0]
        pool = self.df_songs.copy()
        
        if (venue.get('FAMILY FRIENDLY?') == 'Y') or (modifiers.get('FAMILY_FRIENDLY') is True):
            pool = pool[pool['EXPLICIT'].str.upper() != 'Y']
            
        banned_songs_str = str(venue.get('BANNED SONGS', ''))
        banned_songs_list = [s.strip().upper() for s in banned_songs_str.split(',') if s.strip()]
        if banned_songs_list:
            pool = pool[~pool['SONG_UPPER'].isin(banned_songs_list)]
            
        max_energy = pd.to_numeric(venue.get('MAX ENERGY'), errors='coerce')
        if not np.isnan(max_energy):
            pool = pool[pool['ENERGY'] <= max_energy]
            
        if "acoustic" not in gig_type.lower():
            pool = pool[pool['ACOUSTIC?'].str.upper() != 'Y']
            
        return pool

    # ---------------------------------------------------------
    # TIER 2: DYNAMIC CONTEXTUAL SCORING
    # ---------------------------------------------------------
    def calculate_dynamic_scores(self, pool, venue_name, modifiers, current_set_num=None):
        venue = self.df_venues[self.df_venues['NAME'] == venue_name].iloc[0]
        pool = pool.copy()
        pool['SCORE'] = 100.0
        
        latest_plays = self.df_history.groupby('SONG_UPPER')['DATE_DT'].max().to_dict()
        current_date = datetime.now()
        
        for idx, row in pool.iterrows():
            song_name = row['SONG_UPPER']
            if song_name in latest_plays and pd.notnull(latest_plays[song_name]):
                days_since_played = (current_date - latest_plays[song_name]).days
                if days_since_played <= 7:
                    pool.at[idx, 'SCORE'] -= 50
                elif days_since_played <= 30:
                    pool.at[idx, 'SCORE'] -= 25
                elif days_since_played <= 60:
                    pool.at[idx, 'SCORE'] -= 10

        for idx, row in pool.iterrows():
            genre = str(row.get('GENRE', ''))
            decade = str(row.get('DECADE', ''))
            dancy = str(row.get('DANCY?', ''))
            usual_set = str(row.get('USUAL SET', ''))
            
            if modifiers.get('CLASSIC') and 'Classic' in genre:
                pool.at[idx, 'SCORE'] += 50
            if modifiers.get('90s') and '90s' in decade:
                pool.at[idx, 'SCORE'] += 50
            if modifiers.get('DANCY') and dancy == 'Y':
                pool.at[idx, 'SCORE'] += 50
                
            pref_genre = venue.get('PREFERRED GENRE', 'ALL')
            if pref_genre != 'ALL' and any(g.strip() in genre for g in pref_genre.split(',')):
                pool.at[idx, 'SCORE'] += 50
                
            if current_set_num and str(current_set_num) in usual_set:
                pool.at[idx, 'SCORE'] += 40
                
        return pool.sort_values(by='SCORE', ascending=False)

    # ---------------------------------------------------------
    # TIER 3: STRUCTURAL BUCKETING
    # ---------------------------------------------------------
    def build_set_pools(self, global_filtered_pool, venue_name, gig_type, modifiers, fun_block_size=5):
        blueprint = GIG_TYPES.get(gig_type)
        if not blueprint:
            raise ValueError(f"Gig blueprint '{gig_type}' is unrecognized.")
            
        set_menus = {}
        set_lengths = {}
        
        sets_to_build = [k for k in blueprint.keys() if k.startswith('set') and k != 'set_length']
        
        for set_key in sets_to_build:
            set_rule = blueprint[set_key]
            target_len = blueprint.get('set_length', 12)
            
            set_num = ''.join(filter(str.isdigit, set_key))
            set_num = int(set_num) if set_num else None
            
            scored_pool = self.calculate_dynamic_scores(global_filtered_pool, venue_name, modifiers, current_set_num=set_num)
            
            fun_block_tracks = []
            if set_key == 'set2' and modifiers.get('FUNBLOCK'):
                scored_pool, fun_block_tracks = self._generate_fun_block(scored_pool, fun_block_size)
                target_len = max(0, target_len - len(fun_block_tracks))
            
            if isinstance(set_rule, dict) and set_rule.get('split'):
                partA_rule = set_rule['partA']
                partB_rule = set_rule['partB']
                
                pool_A = self._filter_pool_by_rule(scored_pool, partA_rule).head(15)
                pool_B = self._filter_pool_by_rule(scored_pool, partB_rule).head(15)
                
                set_menus[set_key] = {"partA": pool_A, "partB": pool_B}
                set_lengths[set_key] = {"partA": partA_rule['slots'], "partB": partB_rule['slots']}
            else:
                filtered_pool = self._filter_pool_by_rule(scored_pool, set_rule)
                set_menus[set_key] = filtered_pool.head(30)
                set_lengths[set_key] = target_len
                
            if fun_block_tracks:
                set_menus[f"{set_key}_funblock"] = fun_block_tracks

        return set_menus, set_lengths

    def _filter_pool_by_rule(self, pool, rule):
        p = pool.copy()
        if 'tuning' in rule:
            p = p[p['BASE TUNING'].str.upper() == rule['tuning'].upper()]
        if rule.get('exclude_energy') is not None:
            p = p[p['ENERGY'] != rule['exclude_energy']]
            
        acoustic_rule = rule.get('acoustic', 'BOTH')
        if acoustic_rule == 'ONLY':
            p = p[p['ACOUSTIC?'].str.upper().isin(['Y', 'BOTH'])]
        elif acoustic_rule == 'N':
            p = p[p['ACOUSTIC?'].str.upper() != 'Y']
        return p

    def _generate_fun_block(self, pool, X):
        # FIX: Explicitly restrict candidates to rows where FUN BLOCK? column is populated
        fb_pool = pool[
            (pool['FUN BLOCK?'].notna()) & (pool['FUN BLOCK?'].astype(str).str.strip() != '') |
            (pool['SONG_UPPER'].isin(['ELECTRIC WORRY', 'HARD TO HANDLE', 'SANTERIA']))
        ].copy()
        
        medley = [None] * X
        
        def pull_song(title):
            match = fb_pool[fb_pool['SONG_UPPER'] == title.upper()]
            return match.iloc[0] if not match.empty else None

        medley[0] = pull_song('ELECTRIC WORRY')
        medley[1] = pull_song('HARD TO HANDLE')
        
        santeria = pull_song('SANTERIA')
        if santeria is not None:
            medley[-1] = santeria
        else:
            # FIX: Ensure fillers strictly pull from non-blank FUN BLOCK rows
            remaining_fb = fb_pool[
                (~fb_pool['SONG_UPPER'].isin(['ELECTRIC WORRY', 'HARD TO HANDLE'])) & 
                (fb_pool['FUN BLOCK?'].notna()) & (fb_pool['FUN BLOCK?'].astype(str).str.strip() != '')
            ]
            if not remaining_fb.empty:
                medley[-1] = remaining_fb.iloc[0]

        assigned_names = [s['SONG_UPPER'] for s in medley if s is not None]
        fillers_needed = X - len(assigned_names)
        
        if fillers_needed > 0:
            # FIX: Pull only genuine remaining, explicitly designated fun block items
            available_fillers = fb_pool[
                (~fb_pool['SONG_UPPER'].isin(assigned_names)) &
                (fb_pool['FUN BLOCK?'].notna()) & (fb_pool['FUN BLOCK?'].astype(str).str.strip() != '')
            ].sort_values(by='SCORE', ascending=False)
            
            filler_idx = 0
            for i in range(2, X - 1):
                if filler_idx < len(available_fillers):
                    medley[i] = available_fillers.iloc[filler_idx]
                    filler_idx += 1

        final_medley = [s for s in medley if s is not None]
        final_medley_names = [s['SONG_UPPER'] for s in final_medley]
        remaining_pool = pool[~pool['SONG_UPPER'].isin(final_medley_names)]
        
        return remaining_pool, final_medley


# ---------------------------------------------------------
# PROMPT COMPILER
# ---------------------------------------------------------
def compile_gemini_prompt(set_menus, set_lengths, gig_type, modifiers, additional_context):
    prompt = f"""
You are the Creative Director and Setlist Maestro for the rock band 'Electric Junkyard'.
Your job is to sequence an optimal live performance setlist using ONLY the provided filtered song menus below.

GIG TYPE CONFIGURATION: {gig_type}
MODIFIERS ACTIVE: {', '.join([k for k, v in modifiers.items() if v]) or 'None'}

---
CRITICAL EXECUTION LAWS:
1. ABSOLUTE BOUNDARY LAW: Choose songs strictly from the matching Set Menu. Never cross-contaminate sets or invent songs.
2. QUANTITY MATCH LAW: You must pick exactly the target capacity specified for each set layout. If a set contains a mandatory medley block (like the Fun Block), your chosen standard tracks PLUS the medley tracks must equal the traditional total set capacity (e.g., 12 songs total for a standard set).
3. NO DUPLICATION LAW: A song can NEVER be repeated anywhere in the entire gig layout. If a song appears as an option in multiple set menus, once you choose it for a set, it becomes completely locked out and unavailable for any subsequent sets.
4. TUNING PROGRESSION LAW: Within any set containing both Standard and Flat tunings, songs must flow strictly from Standard to Flat. Never alternate back and forth.
    Data Ground Truth: Trust the provided table columns implicitly. Never assume a song's base tuning or Drop-D status based on real-world knowledge; rely solely on the explicit BASE TUNING and DROP D? = Y markings in the menu rows.
5. DROP-D PLACEMENT LAW: All Drop-D songs must be grouped together and positioned at the absolute end of their respective set.
    Pairing Intercept: If a standard song is hard-bound to a Drop-D song (e.g., My Hero to Everlong), sequence that entire paired unit right at the boundary where the Drop-D block begins. 
    Drop-D positioning laws permanently override any standard mid-set pairing positions.
6. OPENER & CLOSER ALIGNMENT LAW: You must strictly structure the structural anchor positions of every individual set using the 'SLOT PREF' data:
   6a. SET OPENERS: The very first song of ANY set (or sub-set part) MUST be a track designated as 'OPENER' in the SLOT PREF column.
   6b. SET CLOSERS: The very last song of ANY set (or sub-set part) MUST be a track explicitly designated as 'CLOSER' in the SLOT PREF column. 
    CRITICAL: You are strictly forbidden from identifying a song as a CLOSER in your output unless that exact song carries a 'CLOSER' designation in the provided menu table. 
        If the absolute end of a set features a Drop-D block, the final song of that block must be chosen from the available tracks marked 'CLOSER' and 'Y' for Drop-D (e.g., Slither, Black Hole Sun, or Shine).
   6c. MID-SET FLEXIBILITY: Tracks marked as 'OPENER' or 'CLOSER' are perfectly eligible to be played in the middle of a set as well, provided they fit the tuning progression and other laws. Non-designated tracks can play anywhere *except* the absolute first or last slot.
7. ACOUSTIC CONTINUITY LAW: If Gig Type calls for an acoustic component, group Standard Acoustic tracks together first, followed by Flat Acoustic. Maintain clean transitions.
   7a. If Gig Type does not explicitly contain the word "acoustic" then there is no acoustic component. In this case, never pick a song where ACOUSTIC? = Y ("BOTH" is OK).
8. TEMPO & PAIRING: Keep stage momentum high. If a song lists a rule in the 'ALWAYS FOLLOWED BY' column, you must sequence its partner directly behind it.
9. NOTES COMPLIANCE: Review the 'SONG NOTES' column for performance restrictions or dependencies and adhere to them fully.
10. MEDLEY INTEGRATION & EXCLUSION: If a Set 2 Fun Block Medley array is provided, it must be inserted as an uninterrupted sequence in the exact order generated. CRITICAL: Any song explicitly named inside the Fun Block Medley is considered ALREADY CHOSEN. 
    You must never select these songs as standalone tracks in Set 2 or Set 3, even if they appear in those menus.
11. OUTPUT FORMAT MANDATE: You must return the final setlist using the exact text schema below. Do not include numbers, bullet points, track tuning notes, or slot tags in the set lists.
    Add a short commentary block at the end (starting with ###), detailing the actions you took.
    Output only the uppercase song names under each set header. E.g.:
    SET 1
    SONG NAME 1
    SONG NAME 2

    SET 2
    SONG NAME 1
    SONG NAME 2

    SET 3
    SONG NAME 1
    SONG NAME 2

    etc.
    ###
    [COMMENTARY ABOUT THE ACTIONS YOU TOOK]
---
AVAILABLE SET MENUS:
"""

    def format_df_to_text_table(df):
        cols = ['SONG', 'BASE TUNING', 'DROP D?', 'ACOUSTIC?', 'SLOT PREF', 'ENERGY', 'ALWAYS FOLLOWED BY', 'SONG NOTES']
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        
        table_str = " | ".join(cols) + "\n"
        table_str += "-" * len(table_str) + "\n"
        for _, row in df.iterrows():
            row_str = " | ".join([str(row[c]).replace('\n', ' ').strip() for c in cols])
            table_str += row_str + "\n"
        return table_str

    has_funblock = "set2_funblock" in set_menus
    funblock_count = len(set_menus["set2_funblock"]) if has_funblock else 0

    for set_name, data in set_menus.items():
        if "funblock" in set_name:
            prompt += f"\n### {set_name.upper()} (MANDATORY MEDLEY - MUST BE KEPT AS AN UNINTERRUPTED BLOCK):\n"
            for s in data:
                slot_pref = s.get('SLOT PREF', '') if pd.notna(s.get('SLOT PREF')) else ''
                prompt += f"- {s['SONG']} (Tuning: {s['BASE TUNING']}, Drop-D: {s['DROP D?']}, Slot Pref: {slot_pref})\n"
        elif isinstance(data, dict):
            for part, df_part in data.items():
                prompt += f"\n### {set_name.upper()} - {part.upper()} (Target: {set_lengths[set_name][part]} songs):\n"
                prompt += format_df_to_text_table(df_part) + "\n"
        else:
            if set_name == "set2" and has_funblock:
                total_target = set_lengths[set_name] + funblock_count
                header_target_msg = f"{set_lengths[set_name]} songs (Note: The other {funblock_count} slots are filled by the mandatory SET2_FUNBLOCK medley below, making {total_target} songs total for Set 2)"
            else:
                header_target_msg = f"{set_lengths[set_name]} songs"

            prompt += f"\n### {set_name.upper()} (Target: {header_target_msg}):\n"
            prompt += format_df_to_text_table(data) + "\n"
            
    # New Clean Finish: Inject user text and explicitly enforce zero commentary
    if additional_context.strip():
        prompt += f"\n\nUSER-SPECIFIED GIG INSTRUCTIONS (ADHERE TO THESE FULLY):\n- {additional_context.strip()}\n"

    prompt += "\nFormat your final response cleanly with headers for each set. Output ONLY uppercase song names and uppercase set headers. Do not include any summary notes, explanations, or creative commentary."
    return prompt


def compile_audit_prompt(pass1_text: str, df_songs: pd.DataFrame) -> str:
    """
    Takes the raw string output from the first LLM pass, extracts the selected songs,
    cross-references them with the master song DataFrame to inject ground-truth metadata,
    and compiles the strict optimization prompt for the Pass 2 Auditor.
    """
    audit_metadata_payload = ""
    current_set = "UNKNOWN SET"
    
    # Process line-by-line to map selected tracks to their true metadata
    for line in pass1_text.splitlines():
        line_clean = line.strip().upper()
        if not line_clean:
            continue
        
        # Track which set boundary we are crossing
        if "SET " in line_clean:
            current_set = line_clean
            audit_metadata_payload += f"\n{current_set} VERIFIED METADATA:\n"
            continue
            
        # Skip creative commentary markers if they accidentally leaked into Pass 1
        if line_clean.startswith("###"):
            continue
            
        # Look up the song in the master song DataFrame (case-insensitive match)
        matched_song = df_songs[df_songs['SONG'].str.upper() == line_clean]
        
        if not matched_song.empty:
            # Safely grab tuning details directly from your Sheet's columns
            tuning = matched_song.iloc[0].get('BASE TUNING', 'STANDARD')
            drop_d = matched_song.iloc[0].get('DROP D?', 'N')
            followed_by = matched_song.iloc[0].get('ALWAYS FOLLOWED BY', '')
            
            audit_metadata_payload += (
                f"- {line_clean} [Tuning: {tuning} | Drop-D: {drop_d} | Followed By: {followed_by}]\n"
            )
        else:
            # Fallback if a song name was hallucinated or misspelled by Pass 1
            audit_metadata_payload += f"- {line_clean} [WARNING: Track metadata missing from Master Sheet]\n"

    # Assemble the final zero-tolerance audit prompt
    audit_prompt = f"""
You are a meticulous, zero-tolerance Setlist Auditor for the rock band 'Electric Junkyard'.
Your sole assignment is to take the DRAFT SETLIST from Pass 1, cross-reference it with the verified SONG METADATA provided below, and repair any structural law violations.

DRAFT SETLIST AND COMMENTARY FROM PASS 1:
---
{pass1_text}
---

VERIFIED SONG METADATA (GROUND TRUTH):
---
{audit_metadata_payload}
---

CRITICAL EXECUTION LAWS TO ENFORCE:
1. TUNING PROGRESSION LAW: Within any single set containing both Standard and Flat tunings, songs must flow strictly from STANDARD to FLAT. They can never alternate back and forth.
2. DROP-D PLACEMENT LAW: All Drop-D tracks (marked Drop-D: Y) must be grouped together and positioned at the absolute end of their respective sets.
3. TEMPO & PAIRINGS: Ensure the following, IF APPLICABLE (i.e., if they are present in a set): 
    If JOHNNY B GOODE is present, it is followed immediately by ROCK & ROLL. Add ROCK & ROLL if necessary to satisfy this requirement.
    If SIMPLE MAN is present, it should be in set 2, and placed BEFORE any Drop-D songs (if they exist). Move it if present and necessary, otherwise do nothing.
    If EVEN FLOW is present, it is followed immediately by SHINE. Add SHINE if necessary to satisfy this requirement.
    If MY OWN WORST ENEMY is present, it is followed immediately by ALL THE SMALL THINGS. Add ALL THE SMALL THINGS if necessary to satisfy this requirement.
    If THE BOYS ARE BACK IN TOWN is present, it should be in set 2. Remove or move it if necessary to satisfy this requirement, while respecting other rules.
4. ABSOLUTE OUTPUT FORMAT MANDATE: You must output ONLY the final clean text block. Do not include bullet points, numbering, or track metadata tags. Do not output any conversational text or creative commentary. Only return the uppercase 'SET X' headers and the uppercase song names.

Examine the draft carefully. If any songs violate the tuning progression or drop-d positioning laws, re-sort that specific set's order silently to perfectly comply before outputting.
After outputting the list, add a short commentary (1-2 paragraphs) detailing any actions that you took.
Output should look like:
    SET 1
    SONG NAME 1
    SONG NAME 2

    SET 2
    SONG NAME 1
    SONG NAME 2

    SET 3
    SONG NAME 1
    SONG NAME 2

    etc.
    ###
    [COMMENTARY ABOUT THE ACTIONS YOU TOOK]
"""
    return audit_prompt