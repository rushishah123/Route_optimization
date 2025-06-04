import pandas as pd
from geopy.distance import geodesic

def create_trips_csv(input_file, output_file):
    # Load the dataset
    df = pd.read_csv(input_file)
    
    # Selecting essential columns for the trip
    trips_df = df[[ 
        'PhlebotomistID.1', 'PhlebotomistName', 'PhlebotomistLatitude', 'PhlebotomistLongitude',
        'PatientSysID', 'PatientFirstName', 'PAtientLastName', 'PatientLatitude', 'PatientLongitude',
        'ScheduledDtm', 'CollectedDtm', 'City', 'ServiceAreaCode', 'NumOfTests', 'WorkloadPoints'
    ]].copy()
    
    # Drop rows with missing coordinates (essential for distance calculations)
    trips_df = trips_df.dropna(subset=['PhlebotomistLatitude', 'PhlebotomistLongitude', 'PatientLatitude', 'PatientLongitude'])
    
    # Convert ScheduledDtm to datetime
    trips_df['ScheduledDtm'] = pd.to_datetime(trips_df['ScheduledDtm'])

    # Extract date only (ignoring time)
    trips_df['TripDate'] = trips_df['ScheduledDtm'].dt.date  

    # Calculate distance in miles
    def calculate_distance(row):
        phleb_location = (row['PhlebotomistLatitude'], row['PhlebotomistLongitude'])
        patient_location = (row['PatientLatitude'], row['PatientLongitude'])
        return round(geodesic(phleb_location, patient_location).miles, 2)

    trips_df['DistanceMiles'] = trips_df.apply(calculate_distance, axis=1)

    # Sort by PhlebotomistID, Date, and ScheduledDtm
    trips_df = trips_df.sort_values(by=['PhlebotomistID.1', 'TripDate', 'ScheduledDtm'])

    # Assign trip order per phlebotomist per day
    trips_df['TripOrderInDay'] = trips_df.groupby(['PhlebotomistID.1', 'TripDate'])['ScheduledDtm'].rank(method='first').astype(int)

    # Save the cleaned data to trips.csv
    trips_df.to_csv(output_file, index=False)
    
    print(f"Trips data saved to {output_file}")

# Example usage
create_trips_csv('Req.csv', 'trips.csv')
