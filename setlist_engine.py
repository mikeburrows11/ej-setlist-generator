import pandas as pd
import numpy as np
from datetime import datetime

class SetlistEngine:
    def __init__(self, songs_path, venues_path, history_path):
        # Load datasets
        self.songs_df = pd.read_csv(songs_path)
        self.venues_df = pd.read_csv(venues_path)
        self.history_df = pd.read_csv(history_path)
        
        # Clean string inputs
        self.songs_df['SONG'] = self.songs_df['SONG'].str.strip()
        self.songs_df['ARTIST'] = self.songs_df['ARTIST'].str.strip()
        
        # Standardize history dates
        self.history_df['DATE'] = pd.to_datetime(self.history_df['DATE'])
        
    def calculate_recency_scores(self, current_date):
        """
        Calculates days since each song was last played based on Gig History.
        Returns a dictionary mapping song titles to their recency score (0 to 100).
        """
        # Get the most recent gig date for each song
        last_played = self.history_df.groupby('SONG')['DATE'].max().to_dict()
        
        recency_scores = {}
        for _, row in self.songs_df.iterrows():
            song = row['SONG']
            if song in last_played:
                days_since = (current_date - last_played[song]).days
                # Score curve: scale between 0 (just played) and 100 (not played in 90+ days)
                score = min(100, int((days_since / 90.0) * 100))
            else:
                # Never played or not in recent history gets max freshness score
                score = 100
            recency_scores[song] = score
            
        return recency_scores

    def generate_setlist(self, venue_name, format_selection, modifiers, current_date=None):
        """
        Main engine to filter and score songs based on venue rules and user modifiers.
        """
        if current_date is None:
            current_date = datetime.now()
            
        # 1. FETCH VENUE PROFILE
        venue_profile = self.venues_df[self.venues_df['NAME'] == venue_name].iloc[0]
        max_energy = int(venue_profile['MAX ENERGY'])
        is_family_friendly = venue_profile['FAMILY FRIENDLY?'] == 'Y'
        
        # Start with all active songs
        pool = self.songs_df[self.songs_df['STATUS'] == 'ACTIVE'].copy()
        
        # 2. HARD FILTERS (Venue Constraints)
        # Filter by Family-Friendliness
        if is_family_friendly:
            # Exclude strict explicit songs ('Y'). Keep 'N' and 'MAYBE'
            pool = pool[pool['EXPLICIT'] != 'Y']
        
        # Filter by Max Energy allowed at venue
        pool = pool[pool['ENERGY'] <= max_energy]
        
        # Remove Banned Songs if any exist for the venue
        if pd.notna(venue_profile['BANNED SONGS']):
            banned = [s.strip().upper() for s in venue_profile['BANNED SONGS'].split(',')]
            pool = pool[~pool['SONG'].str.upper().isin(banned)]
            
        # 3. SCORING THE REMAINING POOL
        recency_scores = self.calculate_recency_scores(current_date)
        scores = []
        
        for idx, row in pool.iterrows():
            song = row['SONG']
            score = 0
            
            # Rule A: Core Songs get massive boost
            if row['IS CORE'] == 'Y':
                score += 1000
                
            # Rule B: Venue Preferred Genres
            if pd.notna(venue_profile['PREFERRED GENRE']):
                pref_genres = [g.strip().upper() for g in venue_profile['PREFERRED GENRE'].split(',')]
                song_genres = [g.strip().upper() for g in row['GENRE'].split(',')]
                # If there's an overlap, give a boost
                if any(g in pref_genres for g in song_genres):
                    score += 150
                    
            # Rule C: Match Modifiers (e.g. "90s Heavy" or "Dancy")
            if modifiers.get('classic_rock_heavy') and '70s' in row['DECADE']:
                score += 200
            if modifiers.get('nineties_heavy') and '90s' in row['DECADE']:
                score += 200
            if modifiers.get('high_energy_dancy') and row['DANCY?'] == 'Y':
                score += 150
                
            # Rule D: Recency component (Weighted tie-breaker)
            score += int(recency_scores.get(song, 100) * 0.5) # Scale factor of 0.5 so max weight is 50 points
            
            scores.append((song, score))
            
        # Map scores back to dataframe
        pool['FINAL_SCORE'] = [s[1] for s in scores]
        
        # 4. SET DIVISION & TUNING RESTRICTIONS
        # Identify the tuning flow required based on the Format Selection
        sets = {'Set 1': [], 'Set 2': [], 'Set 3': []}
        
        # Example: Default 3-Set Show
        # Set 1 = STANDARD, Set 2 & 3 = FLAT
        if format_selection == "3-Set Show: Standard (Default)":
            set_1_pool = pool[pool['BASE TUNING'].str.contains('STANDARD', na=False)]
            set_2_pool = pool[pool['BASE TUNING'].str.contains('FLAT', na=False)]
            set_3_pool = pool[pool['BASE TUNING'].str.contains('FLAT', na=False)]
        
        elif format_selection == "Extended E-Standard":
            # Set 1 = STANDARD, Set 2 = half STANDARD half FLAT, Set 3 = FLAT
            set_1_pool = pool[pool['BASE TUNING'].str.contains('STANDARD', na=False)]
            set_2_pool = pool # Can take either, we will split this logic later
            set_3_pool = pool[pool['BASE TUNING'].str.contains('FLAT', na=False)]
        else:
            # Fallback (can define rules for all formatting options in UI)
            set_1_pool, set_2_pool, set_3_pool = pool, pool, pool

        # 5. CONSTRUCT THE FUN BLOCK (If requested in UI)
        fun_block = []
        if modifiers.get('include_fun_block'):
            fun_block_pool = pool[pool['FUN BLOCK?'].notna()].copy()
            
            # Start with the BEGINNING song (e.g., Clutch - Electric Worry)
            beg = fun_block_pool[fun_block_pool['FUN BLOCK?'] == 'BEGINNING']
            # End with the END song (e.g., Sublime - Santeria)
            end = fun_block_pool[fun_block_pool['FUN BLOCK?'] == 'END']
            # Middle pool
            middles = fun_block_pool[fun_block_pool['FUN BLOCK?'] == 'MIDDLE'].sort_values(by='FINAL_SCORE', ascending=False)
            
            # Determine block length
            num_middles = 5 if modifiers.get('long_fun_block') else 3
            
            fun_block.append(beg.iloc[0]['SONG'] if not beg.empty else None)
            fun_block.extend(middles.head(num_middles)['SONG'].tolist())
            fun_block.append(end.iloc[0]['SONG'] if not end.empty else None)
            fun_block = [s for s in fun_block if s is not None]
            
            # Remove chosen fun block songs from main pools so they aren't duplicated
            pool = pool[~pool['SONG'].isin(fun_block)]
            set_1_pool = set_1_pool[~set_1_pool['SONG'].isin(fun_block)]
            set_2_pool = set_2_pool[~set_2_pool['SONG'].isin(fun_block)]
            set_3_pool = set_3_pool[~set_3_pool['SONG'].isin(fun_block)]

        # 6. FILLING THE SETS (Greedy Selector)
        # Select Set 1 (Target: 12 songs)
        set_1_chosen = set_1_pool.sort_values(by='FINAL_SCORE', ascending=False).head(12)
        used_songs = set(set_1_chosen['SONG'])
        
        # Select Set 2 (Target: 12 songs, excluding already used)
        set_2_eligible = set_2_pool[~set_2_pool['SONG'].isin(used_songs)]
        set_2_chosen = set_2_eligible.sort_values(by='FINAL_SCORE', ascending=False).head(12)
        used_songs.update(set_2_chosen['SONG'])
        
        # Select Set 3 (Target: 12 songs, excluding already used)
        set_3_eligible = set_3_pool[~set_3_pool['SONG'].isin(used_songs)]
        set_3_chosen = set_3_eligible.sort_values(by='FINAL_SCORE', ascending=False).head(12)
        
        # 7. ADD CHAINED SONGS
        # Helper to force "Always Followed By" rules within sets
        def apply_chaining(chosen_df):
            list_songs = chosen_df.to_dict('records')
            final_list = []
            for item in list_songs:
                final_list.append(item)
                if pd.notna(item['ALWAYS FOLLOWED BY']):
                    target_song = item['ALWAYS FOLLOWED BY']
                    # Fetch from original pool if it exists
                    match = pool[pool['SONG'] == target_song]
                    if not match.empty:
                        final_list.append(match.iloc[0].to_dict())
            return pd.DataFrame(final_list).drop_duplicates(subset=['SONG']).tolist()

        # Compile draft setlists
        sets['Set 1'] = apply_chaining(set_1_chosen)
        sets['Set 2'] = apply_chaining(set_2_chosen)
        sets['Set 3'] = apply_chaining(set_3_chosen)
        
        # Inject Fun Block (Typically sits at the end of Set 2 or start of Set 3)
        if fun_block:
            sets['Fun Block'] = [pool[pool['SONG'] == s].iloc[0].to_dict() for s in fun_block if not pool[pool['SONG'] == s].empty]

        return sets