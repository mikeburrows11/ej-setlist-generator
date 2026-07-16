import pandas as pd
import numpy as np
from datetime import datetime

class SetlistEngine:
    def __init__(self, songs_df, venues_df, history_df):
        self.songs_df = songs_df.copy()
        self.venues_df = venues_df.copy()
        self.history_df = history_df.copy()
        
        self.songs_df['SONG'] = self.songs_df['SONG'].str.strip()
        #self.songs_df['ARTIST'] = self.songs_df['ARTIST'].str.strip()
        self.history_df['DATE'] = pd.to_datetime(self.history_df['DATE'])
        
    def calculate_recency_scores(self, current_date):
        last_played = self.history_df.groupby('SONG')['DATE'].max().to_dict()
        recency_scores = {}
        for _, row in self.songs_df.iterrows():
            song = row['SONG']
            if song in last_played:
                days_since = (current_date - last_played[song]).days
                score = min(100, int((days_since / 90.0) * 100))
            else:
                score = 100
            recency_scores[song] = score
        return recency_scores

    def generate_setlist(self, venue_name, format_selection, modifiers, current_date=None):
        if current_date is None:
            current_date = datetime.now()
            
        venue_profile = self.venues_df[self.venues_df['NAME'] == venue_name].iloc[0]
        max_energy = int(venue_profile['MAX ENERGY'])
        is_family_friendly = (venue_profile['FAMILY FRIENDLY?'] == 'Y') or modifiers.get('force_family_friendly', False)
        
        # Start with active pool
        pool = self.songs_df[self.songs_df['STATUS'] == 'ACTIVE'].copy()
        
        # Strict Exclusions
        if is_family_friendly:
            pool = pool[pool['EXPLICIT'] != 'Y']
        pool = pool[pool['ENERGY'] <= max_energy]
        
        if pd.notna(venue_profile['BANNED SONGS']):
            banned = [s.strip().upper() for s in venue_profile['BANNED SONGS'].split(',')]
            pool = pool[~pool['SONG'].str.upper().isin(banned)]
            
        # CRITICAL: Birthday song safety lock
        if venue_name.upper() != "BIRTHDAY":
            pool = pool[pool['SONG'].str.upper() != "BIRTHDAY"]
            
        # Scoring
        recency_scores = self.calculate_recency_scores(current_date)
        scores = []
        for idx, row in pool.iterrows():
            song = row['SONG']
            score = 0
            if row['IS CORE'] == 'Y': score += 1000
            if modifiers.get('classic_rock_heavy') and '70s' in row['DECADE']: score += 200
            if modifiers.get('nineties_heavy') and '90s' in row['DECADE']: score += 200
            if modifiers.get('high_energy_dancy') and row['DANCY?'] == 'Y': score += 150
            score += int(recency_scores.get(song, 100) * 0.5)
            scores.append((song, score))
            
        pool['FINAL_SCORE'] = [s[1] for s in scores]
        used_songs = set()

        # Helper to safely pull a tracked pair/chain together
        def get_song_and_chain(song_row):
            chain = [song_row.to_dict()]
            if pd.notna(song_row['ALWAYS FOLLOWED BY']):
                target = song_row['ALWAYS FOLLOWED BY'].strip()
                match = pool[pool['SONG'].str.upper() == target.upper()]
                if not match.empty:
                    chain.append(match.iloc[0].to_dict())
            return chain

        # 1. FIXED BLOCK: BUILD THE FUN BLOCK MEDLEY
        fun_block_final = []
        if modifiers.get('include_fun_block'):
            fb_pool = pool[pool['FUN BLOCK?'].notna()]
            beg = fb_pool[fb_pool['FUN BLOCK?'] == 'BEGINNING']
            end = fb_pool[fb_pool['FUN BLOCK?'] == 'END']
            middles = fb_pool[fb_pool['FUN BLOCK?'] == 'MIDDLE'].sort_values(by='FINAL_SCORE', ascending=False)
            
            if not beg.empty:
                # This naturally chains Electric Worry -> Hard to Handle if updated in sheet
                fun_block_final.extend(get_song_and_chain(beg.iloc[0]))
                
            num_middles = 6 if modifiers.get('long_fun_block') else 3
            added_middles = 0
            for _, mid_row in middles.iterrows():
                if added_middles >= num_middles: break
                if mid_row['SONG'] not in [s['SONG'] for s in fun_block_final]:
                    fun_block_final.extend(get_song_and_chain(mid_row))
                    added_middles += 1
                    
            if not end.empty and end.iloc[0]['SONG'] not in [s['SONG'] for s in fun_block_final]:
                fun_block_final.append(end.iloc[0].to_dict())
                
            used_songs.update([s['SONG'] for s in fun_block_final])

        # 2. FIXED BLOCK: BUILD THE EVEN FLOW + SHINE PAIR FOR SET 3
        set3_tail_block = []
        ef_match = pool[pool['SONG'].str.upper() == "EVEN FLOW"]
        if not ef_match.empty and "EVEN FLOW" not in used_songs:
            set3_tail_block.extend(get_song_and_chain(ef_match.iloc[0]))
            used_songs.update([s['SONG'] for s in set3_tail_block])

        # Separate remaining tunings
        # We separate them by tuning so the LLM can easily group them visually,
        # but we pass the FULL available catalog so it has ultimate creative choice.
        sets_output = {}
        
        standard_pool = pool[pool['BASE TUNING'].str.contains('STANDARD', na=False)].sort_values(by='FINAL_SCORE', ascending=False)
        flat_pool = pool[pool['BASE TUNING'].str.contains('FLAT', na=False)].sort_values(by='FINAL_SCORE', ascending=False)
        
        # Grab the top tier candidates as the core suggestions (plenty of options for a standard gig)
        sets_output['Set 1 Suggestions'] = standard_pool.head(15).to_dict('records')
        sets_output['Set 2 & 3 Suggestions'] = flat_pool.head(25).to_dict('records')
        
        # Gather all songs that were NOT handed over in the primary suggestions
        suggested_song_names = set(
            [s['SONG'] for s in sets_output['Set 1 Suggestions']] + 
            [s['SONG'] for s in sets_output['Set 2 & 3 Suggestions']]
        )
        
        # The remaining vetted active songs become your Alternates Bench (guaranteed to be populated!)
        sets_output['Alternates Pool'] = pool[~pool['SONG'].isin(suggested_song_names)].sort_values(by='FINAL_SCORE', ascending=False).to_dict('records')
        
        # Pull your special blocks if toggled
        if modifiers.get('include_fun_block'):
            sets_output['Fun Block'] = pool[pool['FUN BLOCK?'].notna()].to_dict('records')
        if modifiers.get('add_acoustic_block'):
            sets_output['Acoustic Block'] = pool[pool['ACOUSTIC?'] == 'BOTH'].to_dict('records')
            
        return sets_output
    
def generate_llm_prompt(draft_data, venue_profile, user_comments, show_format):
    """
    Generates a constraint-based creative prompt for Gemini.
    Python only acts as the menu filter; the LLM handles all sequencing, 
    tuning grouping, and flow logic based on data and rules.
    """
    
    # 1. DYNAMIC MACRO CONSTRAINTS BASED ON FORMAT
    if "1-Set" in show_format:
        target_len = "11-13 songs total"
        set_structure_instruction = "Arrange all chosen songs into a single, cohesive, uninterrupted live set list block."
    elif "2-Set" in show_format:
        target_len = "24-26 songs total"
        set_structure_instruction = "Divide the selected songs evenly into SET 1 and SET 2 (roughly 12-13 songs per set)."
    else: # 3-Set Shows (Default)
        target_len = "35-38 songs total"
        set_structure_instruction = (
            "Divide the selected songs cleanly into SET 1, SET 2, and SET 3 (roughly 12 songs per set).\n"
            "* Place the 'Fun Block Medley' suite directly in the middle of SET 2."
        )

    # 2. THE MASTER RULES HIERARCHY FOR THE LLM
    prompt = f"""
        CRITICAL: You are an anchor-based generator. 
        You are STRICTLY forbidden from using any song name that does not appear in the candidate pools below. 
        If a pool is empty, do not make up songs; only use songs from the Alternates pool.
        
        You are the veteran music director and live stage arranger for our rock cover band, "Electric Junkyard".
        Your job is to take the vetted raw pool of songs provided below and sequence the ultimate live show setlist. 

        Follow this strict Rules Hierarchy to arrange the tracks. Treat these rules as absolute operational laws:

        =======================================================
        RULES HIERARCHY (Ranked by Order of Importance)
        =======================================================
        1. TUNING LOCK: You must group all songs strictly by their BASE TUNING block. Never bounce back-and-forth between E-Standard and E-Flat within a set. Maximize continuous blocks.
        2. DROP-D TAILS: Within any tuning block, songs marked [DropD: Y] or noted as Drop-D must be clustered together at the absolute END of that specific tuning section.
        3. PAIRING CHAINS: You must read individual 'SONG NOTES'and 'MEDLEY_ROLE' tags. If a note states a track 'must always be followed by X', you must snap them back-to-back chronologically. Never separate them. In addition:
            * If a song is marked [MEDLEY_ROLE: BEGINNING], it MUST be the absolute first song of the Fun Block medley.
            * If a song is marked [MEDLEY_ROLE: END], it MUST be the absolute final song closing out the Fun Block medley.
            * All other chosen medley songs must stay locked back-to-back between them as an uninterrupted block inside SET 2.
        4. SET CLOSERS: The final song of every single set block must be an epic, high-energy closer track (indicated by SlotPref: CLOSER or noted as such).
        5. SET STRUCTURE & LEN: 
        * {set_structure_instruction}
        * Target a total show length of {target_len}.
        6. STAGE FLOW: Build an energy arc within sets. Start fast, settle into mid-tempo, and build to an intense, heavy rock finish.

        =======================================================
        CRITICAL MEDLEY LAWS (THE FUN BLOCK)
        =======================================================
        When assembling the Fun Block medley, you must follow this exact linear sequence:
        1. START: You must open the medley with "ELECTRIC WORRY", which is always followed by "HARD TO HANDLE".
        2. MIDDLES: Insert 3 to 5 middle tier medley tracks (e.g., Toxic, Blister in the Sun, etc.) back-to-back with zero non-medley songs separating them.
            *If "MY OWN WORST ENEMY" is included, it is always followed immediately by "ALL THE SMALL THINGS".
        3. END: You must close the medley with "SANTERIA" unless it was already previously filtered out (e.g., due to its explicit nature not being suitable for the venue). 
        * Total Violation Check: If "ELECTRIC WORRY" is missing in a set list that is defined to have a "Fun Block", the setlist is invalid.

        =======================================================
        GIG PARAMETERS & LIVE DIRECTIVES
        =======================================================
        * Venue Name: {venue_profile['NAME']}
        * Venue-Specific Constraints: "{venue_profile['VENUE NOTES']}"
        * Live Human Directives for Tonight: "{user_comments}"

        =======================================================
        VETTED SONG SELECTION POOL (THE MENU)
        =======================================================
        Select your roster and alternates strictly from this pool. Pay close attention to the row-level 'Notes' fields to honor chains, slot requirements, and exclusions:

        """

    # 3. APPEND THE FILTERED RAW POOLS WITH DATA TAGS
    all_eligible_pools = [
        ("E-Standard Candidates Pool", draft_data.get('Set 1 Suggestions', [])),
        ("E-Flat Candidates Pool", draft_data.get('Set 2 & 3 Suggestions', [])),
        ("Alternates & Bench Pool", draft_data.get('Alternates Pool', []))
    ]
    
    # Include blocks if active in the data payload
    if 'Fun Block' in draft_data:
        all_eligible_pools.append(("Fun Block Suite", draft_data['Fun Block']))
    if 'Acoustic Block' in draft_data:
        all_eligible_pools.append(("Acoustic Breather Suite", draft_data['Acoustic Block']))

    for pool_name, song_list in all_eligible_pools:
        prompt += f"\n--- {pool_name} ---\n"
        if not song_list:
            prompt += "* [No tracks available in this tier]\n"
            continue
        for s in song_list:
            # Check if this song has a strict medley role assigned in the sheet
            role_tag = f"[MEDLEY_ROLE: {s['FUN BLOCK?']}] " if pd.notna(s.get('FUN BLOCK?')) else ""
            
            prompt += (
                f"* {role_tag}{s['SONG']} "
                f"[Tuning: {s['BASE TUNING']}] "
                f"[DropD: {s['DROP D?']}] "
                f"[Energy: {s['ENERGY']}] "
                f"[SlotPref: {s.get('SLOT PREF', 'Normal')}] "
                f"[Notes: {s.get('SONG NOTES', 'None')}]\n"
            )

    # 4. ENFORCE RAW TEXT OUTPUT FORMAT
    prompt += """
        =======================================================
        REQUIRED OUTPUT FORMAT Blueprint
        =======================================================
        Your output must be strictly limited to the finalized lists matching this template exactly. No generic conversational text, greetings, or fluff.
        Do not add place numbers before the song.

        SET 1
        [Song Name]
        [Song Name]
        ...

        SET 2
        [Song Name]
        ...

        SET 3
        [Song Name]
        ...

        BRIEF STAGE DIRECTOR LOGISTICS NOTES:
        * [Include 2-3 short, bulleted notes max explaining critical transition choices or border-line pacing decisions at the absolute bottom.]
        """
    return prompt