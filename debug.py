import pandas as pd

# Load your local sheets
songs = pd.read_csv("Master Songs and Venues - Songs w metadata.csv")
venues = pd.read_csv("Master Songs and Venues - Venues w metadata.csv")

# 1. Print totals
print(f"Total songs in CSV: {len(songs)}")
print(f"Active songs: {len(songs[songs['STATUS'].str.strip() == 'ACTIVE'])}")

# 2. Check the selected venue parameters
venue_name = "THE PUB TIFTON"
venue_profile = venues[venues['NAME'] == venue_name].iloc[0]
print(f"\nVenue: {venue_name}")
print(f"Max Energy Allowed: {venue_profile['MAX ENERGY']}")
print(f"Family Friendly? {venue_profile['FAMILY FRIENDLY?']}")

# 3. Simulate the filter step-by-step
pool = songs[songs['STATUS'].str.strip() == 'ACTIVE'].copy()

# Filter Energy
pool_energy = pool[pool['ENERGY'] <= int(venue_profile['MAX ENERGY'])]
print(f"Songs remaining after Energy filter: {len(pool_energy)}")

# Filter Standard Tuning
pool_st = pool_energy[pool_energy['BASE TUNING'].str.upper().str.contains('STANDARD', na=False)]
print(f"Standard tuning songs remaining: {len(pool_st)}")

# Filter Flat Tuning
pool_fl = pool_energy[pool_energy['BASE TUNING'].str.upper().str.contains('FLAT', na=False)]
print(f"Flat tuning songs remaining: {len(pool_fl)}")