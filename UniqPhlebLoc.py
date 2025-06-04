import pandas as pd

# Load the trips.csv
df = pd.read_csv("trips.csv")

# Clean column names
df.columns = df.columns.str.strip()

# Ensure datetime format
df['ScheduledDtm'] = pd.to_datetime(df['ScheduledDtm'])

# Check correct column name
phleb_id_col = "PhlebotomistID.1" if "PhlebotomistID.1" in df.columns else "PhlebotomistID"

# Get unique phlebotomists with their first recorded location
unique_phlebs = df.groupby(phleb_id_col).first().reset_index()

# Include city information so downstream applications have full context
unique_phleb_locations = unique_phlebs[
    [
        phleb_id_col,
        "PhlebotomistName",
        "PhlebotomistLatitude",
        "PhlebotomistLongitude",
        "City",
    ]
]

# Save as CSV using the expected filename
unique_phleb_locations.to_csv("phlebotomists_with_city.csv", index=False)
print("✅ Unique phlebotomist locations saved as phlebotomists_with_city.csv")
