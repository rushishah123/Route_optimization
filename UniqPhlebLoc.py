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

# Select relevant columns
unique_phleb_locations = unique_phlebs[[phleb_id_col, "PhlebotomistName", "PhlebotomistLatitude", "PhlebotomistLongitude"]]

# Save as CSV
unique_phleb_locations.to_csv("unique_phleb_locations.csv", index=False)
print("✅ Unique phlebotomist locations saved as unique_phleb_locations.csv")
