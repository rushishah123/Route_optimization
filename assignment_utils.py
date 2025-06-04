import pandas as pd
import logging
import os
import streamlit as st
import numpy as np
from geopy.geocoders import Nominatim
from datetime import timedelta, datetime
from copy import deepcopy

from route_utils import calculate_distance
from workload_utils import phlebs_required_asper_workload
from map_utils import create_assignment_map
from final_utils_upd import calculate_route_distance
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_available_phlebotomists(phleb_df, target_city, num_phlebs_needed, redis_conn=None, ors_api_key=None):
    """
    Get available phlebotomists in the target city.
    If no phlebotomist is found in the target city, returns the nearest ones.
    
    Args:
        phleb_df: DataFrame with phlebotomist information
        target_city: City to analyze
        num_phlebs_needed: Number of phlebotomists needed
        redis_conn: Redis connection (optional)
        ors_api_key: OpenRouteService API key (optional)
        
    Returns:
        DataFrame with available phlebotomists
    """
    from geopy.geocoders import Nominatim
    import pandas as pd
    
    # Import Redis and ORS utility functions if Redis connection is provided
    if redis_conn is not None:
        from redis_utils import load_phlebotomists_to_redis, get_nearby_phlebotomists, initialize_ors_client
    
    # Geocode the target city
    geolocator = Nominatim(user_agent="phleb_locator")
    location = geolocator.geocode(target_city)
    
    if location is None:
        st.error(f"Could not find coordinates for {target_city}.")
        return pd.DataFrame()  # Return empty DataFrame if city is not found
    
    target_coords = (location.latitude, location.longitude)
    print(f"Target Coords --> {target_coords}")
    
    # If Redis connection is provided, use geospatial indexing
    if redis_conn is not None:
        # Load phlebotomists data into Redis if not already loaded
        load_phlebotomists_to_redis(redis_conn, phleb_df)
        
        # Find nearby phlebotomists using Redis geospatial index
        # Start with a reasonable radius (30 miles)
        search_radius = 30  # miles
        nearby_phlebs = get_nearby_phlebotomists(redis_conn, location.latitude, location.longitude, search_radius)
        
        # If not enough phlebotomists found, increase radius
        while len(nearby_phlebs) < num_phlebs_needed and search_radius < 100:
            search_radius += 20
            nearby_phlebs = get_nearby_phlebotomists(redis_conn, location.latitude, location.longitude, search_radius)
        
        # Extract phlebotomist IDs and create a new DataFrame
        nearby_phleb_ids = [phleb_id for phleb_id, _, _ in nearby_phlebs]
        
        if not nearby_phleb_ids:
            # st.warning(f"No phlebotomists found within {search_radius} miles of {target_city}. Using all available phlebotomists.")
            available_phlebs = phleb_df.copy()
        else:
            # Filter the original DataFrame to include only nearby phlebotomists
            available_phlebs = phleb_df[phleb_df["PhlebotomistID.1"].astype(str).isin(nearby_phleb_ids)].copy()
            
            # Add distance information
            distance_map = {phleb_id: dist for phleb_id, dist, _ in nearby_phlebs}
            available_phlebs["distance_to_target"] = available_phlebs["PhlebotomistID.1"].astype(str).map(distance_map)
            
            # Sort by distance
            available_phlebs = available_phlebs.sort_values(by="distance_to_target")
            
        # Check if any phlebotomists are in the target city
        city_phlebs = available_phlebs[available_phlebs['City'] == target_city]
        
        if not city_phlebs.empty:
            # If phlebotomists are available in the target city, prioritize them
            available_phlebs = city_phlebs.copy()
        
    else:
        # Fall back to original method if Redis is not available
        # Compute distances for all phlebotomists using geodesic
        from geopy.distance import geodesic
        
        print(f"Finding distance to target from target : ({target_coords})")
        phleb_df["distance_to_target"] = phleb_df.apply(
            lambda x: geodesic(target_coords, (x["PhlebotomistLatitude"], x["PhlebotomistLongitude"])).miles,
            axis=1
        )
        
        # Sort by distance to target city
        phleb_df = phleb_df.sort_values(by="distance_to_target")
        
        # Select phlebotomists in the target city
        available_phlebs = phleb_df[phleb_df['City'] == target_city].copy()
        
        if available_phlebs.empty:
            st.warning(f"No phlebotomists found in {target_city}. Returning nearby phlebotomists.")
            available_phlebs = phleb_df.copy()
    
    # Initialize workload tracking columns
    available_phlebs["current_workload"] = 0
    available_phlebs["assigned_patients"] = [[] for _ in range(len(available_phlebs))]
    available_phlebs["total_distance"] = 0
    available_phlebs["current_location"] = list(zip(
        available_phlebs["PhlebotomistLatitude"], 
        available_phlebs["PhlebotomistLongitude"]
    ))
    
    print("Returning available phlebs")
    print(available_phlebs)
    
    return available_phlebs

def estimate_travel_time(distance_miles):
    """
    Estimate travel time based on distance.
    
    Args:
        distance_miles: Distance in miles
        
    Returns:
        Estimated travel time in minutes
    """
    # Assume average speed of 30 mph in urban areas
    # Convert to minutes (60 minutes / 30 miles = 2 minutes per mile)
    return distance_miles * 2

def estimate_draw_time(workload_points):
    """
    Estimate time needed for blood draw based on workload points.
    
    Args:
        workload_points: Workload points for the patient
        
    Returns:
        Estimated draw time in minutes
    """
    # Base time for any draw (patient interaction, preparation, etc.)
    base_time = 30
    
    # Additional time based on workload points (adjust as needed)
    # Assuming 1 workload point is roughly 1 minute of work
    additional_time = workload_points
    
    return base_time + additional_time

def assign_patients_to_phlebotomists(patient_df, phleb_df, workload_df, target_date, target_city, 
                             api_key=None, redis_conn=None):
    """
    Assign patients to phlebotomists while optimizing workload, distance, and dropoff locations.
    
    Args:
        patient_df: DataFrame with patient orders
        phleb_df: DataFrame with phlebotomist information
        workload_df: DataFrame with city workload information
        target_date: Date to analyze
        target_city: City to analyze
        api_key: OpenRouteService API key (optional)
        redis_conn: Redis connection (optional)
        
    Returns:
        Tuple of (assigned_phlebs_df, assigned_patients_df)
    """
    import pandas as pd
    from collections import defaultdict
    
    # Import ORS utilities if API key is provided
    if api_key:
        from redis_utils import initialize_ors_client, calculate_route_distance
        ors_client = initialize_ors_client(api_key)
    
    # Convert target_date to datetime.date
    target_date = pd.to_datetime(target_date).date()
    
    # Filter patients for target city and date
    filtered_patients = patient_df[
        (patient_df["City"] == target_city) &
        (patient_df["ScheduledDtm"].dt.date == target_date)
    ].copy()
    
    # If no patients, return empty DataFrames
    if filtered_patients.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Calculate number of phlebotomists needed
    num_phlebs_needed = phlebs_required_asper_workload(workload_df, patient_df, target_date, target_city)
    if not num_phlebs_needed:
        st.error(f"Could not determine phlebotomists needed for {target_city} on {target_date}")
        return pd.DataFrame(), pd.DataFrame()
    
    # Get available phlebotomists using Redis geospatial if available
    available_phlebs = get_available_phlebotomists(phleb_df, target_city, num_phlebs_needed, 
                                                  redis_conn=redis_conn, ors_api_key=api_key)
    
    print("*"*50)
    print("got avail phlebs")
    print(available_phlebs)
    
    if available_phlebs.empty:
        st.error(f"No phlebotomists available in {target_city}")
        return pd.DataFrame(), pd.DataFrame()
    
    # Get the average workload per phlebotomist for the city
    if target_city in workload_df["City"].tolist():
        avg_workload_per_phleb = workload_df.loc[
            workload_df["City"] == target_city,
            "Avg_Workload_Points_per_Phleb"
        ].values[0]
    else:
        print(f"Could not find {target_city} avg workload. Setting Default of 1000")
        avg_workload_per_phleb = 1000
    
    # Sort patients by scheduled time
    filtered_patients = filtered_patients.sort_values(by="ScheduledDtm", ascending=True)
    
    print("-"*50)
    print(filtered_patients)
    
    # Add assignment columns to patients DataFrame
    filtered_patients["AssignedPhlebID"] = None
    filtered_patients["TripOrderInDay"] = None
    filtered_patients["PreferredTime"] = filtered_patients["ScheduledDtm"].copy()  # Initialize with scheduled time
    
    # Define distance calculation function based on available APIs
    def get_distance(point1, point2, use_ors = False):
        """Calculate distance between two points using ORS or fallback to geodesic."""
        if api_key and ors_client and use_ors:
            # Use ORS for routing distance
            return calculate_route_distance(ors_client, point1, point2)
        else:
            # Fallback to geodesic distance
            from geopy.distance import geodesic
            return geodesic(point1, point2).miles
    
    # Cache for route distances to avoid redundant API calls
    distance_cache = {}
    
    # IMPROVED: Pre-process patients to identify dropoff locations and group by clinic
    # Load dropoff locations
    try:
        dropoffs = pd.read_csv("All_Dropoffs.csv")
        has_dropoff_data = True
    except:
        print("Warning: All_Dropoffs.csv not found, skipping dropoff optimization")
        has_dropoff_data = False
    
    # Create mapping of dropoff locations to patients
    dropoff_patient_map = defaultdict(list)
    patient_dropoff_map = {}
    
    if has_dropoff_data:
        print("Pre-processing patients to determine dropoff locations...")
        
        for idx, patient in filtered_patients.iterrows():
            if isinstance(patient["DropOffLocation"], str):
                patient_location = (patient["PatientLatitude"], patient["PatientLongitude"])
                clinic = patient["DropOffLocation"].lower()
                
                # Filter dropoffs by clinic and state
                filtered_dropoffs = dropoffs[dropoffs['Clinic'].str.lower() == clinic]
                
                if len(filtered_dropoffs) > 0:
                    # Further filter by state
                    state_dropoffs = filtered_dropoffs[filtered_dropoffs['State'].str.lower() == patient['PatientState'].lower()]
                    if not state_dropoffs.empty:
                        filtered_dropoffs = state_dropoffs
                    
                    # Try to filter by zipcode if possible
                    zipcode_dropoffs = filtered_dropoffs[filtered_dropoffs['Zipcode'] == patient['PatientZip']]
                    if not zipcode_dropoffs.empty:
                        filtered_dropoffs = zipcode_dropoffs
                    
                    if not filtered_dropoffs.empty:
                        # Find nearest dropoff
                        nearest_dropoff = None
                        min_distance = float('inf')
                        
                        for _, dropoff in filtered_dropoffs.iterrows():
                            dropoff_location = (dropoff["Latitude"], dropoff["Longitude"])
                            
                            # Check cache for distance
                            location_pair = (str(patient_location), str(dropoff_location))
                            if location_pair in distance_cache:
                                dist_to_dropoff = distance_cache[location_pair]
                            else:
                                # Calculate distance
                                dist_to_dropoff = get_distance(patient_location, dropoff_location)
                                distance_cache[location_pair] = dist_to_dropoff
                            
                            if dist_to_dropoff < min_distance:
                                min_distance = dist_to_dropoff
                                nearest_dropoff = dropoff
                        
                        if nearest_dropoff is not None:
                            # Create a unique key for this dropoff location
                            dropoff_key = f"{nearest_dropoff['LabID']}_{nearest_dropoff['Clinic']}"
                            
                            # Add to mapping
                            dropoff_patient_map[dropoff_key].append(idx)
                            patient_dropoff_map[idx] = {
                                'key': dropoff_key,
                                'location': (nearest_dropoff["Latitude"], nearest_dropoff["Longitude"]),
                                'lab_id': nearest_dropoff["LabID"],
                                'clinic_name': nearest_dropoff["Clinic"]
                            }
                            
                            print(f"Patient {idx} mapped to dropoff {dropoff_key}")
    
    # IMPROVED: Patient assignment strategy
    # First sort dropoff groups by size (descending) to prioritize larger groups
    sorted_dropoff_groups = sorted(
        dropoff_patient_map.items(), 
        key=lambda x: len(x[1]), 
        reverse=True
    ) if has_dropoff_data else []
    
    # Process patients in dropoff groups first
    processed_patients = set()
    
    for dropoff_key, patient_indices in sorted_dropoff_groups:
        # Skip small groups (only 1 patient) for the first pass
        if len(patient_indices) <= 1:
            continue
            
        # Get patients in this dropoff group
        group_patients = [idx for idx in patient_indices if idx not in processed_patients]
        
        if not group_patients:
            continue
            
        print(f"Processing dropoff group {dropoff_key} with {len(group_patients)} patients")
        
        # Calculate total workload for this group
        group_workload = sum(filtered_patients.loc[idx, "WorkloadPoints"] for idx in group_patients)
        
        # Find the best phlebotomist for this group
        best_phleb_idx = None
        min_total_distance = float('inf')
        
        for phleb_idx, phleb in available_phlebs.iterrows():
            current_location = phleb["current_location"]
            current_workload = phleb["current_workload"]
            
            # Skip if workload would exceed limit
            if current_workload + group_workload > avg_workload_per_phleb * 4:  # Allow 4x average
                continue
                
            # Calculate total distance from phlebotomist to all patients in this group
            total_distance = 0
            
            for patient_idx in group_patients:
                patient_location = (
                    filtered_patients.loc[patient_idx, "PatientLatitude"],
                    filtered_patients.loc[patient_idx, "PatientLongitude"]
                )
                
                # Check cache for distance
                location_pair = (str(current_location), str(patient_location))
                if location_pair in distance_cache:
                    distance = distance_cache[location_pair]
                else:
                    distance = get_distance(current_location, patient_location)
                    distance_cache[location_pair] = distance
                    
                total_distance += distance
                
            # Factor in the benefit of keeping patients with the same dropoff together
            # by giving a discount to the total distance
            adjusted_distance = total_distance * 0.8  # 20% discount for shared dropoff
                
            # If this is the best phlebotomist so far, update
            if adjusted_distance < min_total_distance:
                min_total_distance = adjusted_distance
                best_phleb_idx = phleb_idx
        
        # If found a suitable phlebotomist, assign all patients in this group
        if best_phleb_idx is not None:
            phleb_id = available_phlebs.loc[best_phleb_idx, "PhlebotomistID.1"]
            
            print(f"Assigned dropoff group {dropoff_key} to phlebotomist {phleb_id}")
            
            # Sort patients by scheduled time for this phlebotomist
            group_patients.sort(key=lambda idx: filtered_patients.loc[idx, "ScheduledDtm"])
            
            # Update each patient in the group
            for i, patient_idx in enumerate(group_patients, start=1):
                # Add to the phlebotomist's assigned patients in order
                trip_order = len(available_phlebs.loc[best_phleb_idx, "assigned_patients"]) + i
                
                # Update the patient record
                filtered_patients.at[patient_idx, "AssignedPhlebID"] = phleb_id
                filtered_patients.at[patient_idx, "TripOrderInDay"] = trip_order
                
                # Add to processed set
                processed_patients.add(patient_idx)
                
                # Add to phlebotomist's assigned patients list
                available_phlebs.at[best_phleb_idx, "assigned_patients"].append(patient_idx)
                
                # Update phlebotomist workload
                available_phlebs.at[best_phleb_idx, "current_workload"] += filtered_patients.loc[patient_idx, "WorkloadPoints"]
            
            # Update phlebotomist location to the last patient in the group
            last_patient_idx = group_patients[-1]
            last_patient_location = (
                filtered_patients.loc[last_patient_idx, "PatientLatitude"],
                filtered_patients.loc[last_patient_idx, "PatientLongitude"]
            )
            available_phlebs.at[best_phleb_idx, "current_location"] = last_patient_location
            
            # Update total distance (approximate)
            available_phlebs.at[best_phleb_idx, "total_distance"] += min_total_distance
    
    # Now process remaining patients (ungrouped or from small groups)
    remaining_patients = [idx for idx in filtered_patients.index if idx not in processed_patients]
    
    print("Remaining Patients")
    print(remaining_patients)
    
    # Prioritize patients with dropoff locations (but were in small groups)
    remaining_with_dropoff = [idx for idx in remaining_patients if idx in patient_dropoff_map]
    remaining_without_dropoff = [idx for idx in remaining_patients if idx not in patient_dropoff_map]
    
    print("Remaining with dropoff")
    print(remaining_with_dropoff)
    
    print("Remaining without dropoff")
    print(remaining_without_dropoff)
    
    # Process remaining patients with dropoffs first, trying to assign to phlebotomists
    # who already handle that dropoff location if possible
    for patient_idx in remaining_with_dropoff:
        dropoff_info = patient_dropoff_map[patient_idx]
        dropoff_key = dropoff_info['key']
        patient_location = (
            filtered_patients.loc[patient_idx, "PatientLatitude"],
            filtered_patients.loc[patient_idx, "PatientLongitude"]
        )
        patient_workload = filtered_patients.loc[patient_idx, "WorkloadPoints"]
        
        # Find phlebotomists who already handle this dropoff location
        matching_phlebs = []
        
        for phleb_idx, phleb in available_phlebs.iterrows():
            assigned_patients = phleb["assigned_patients"]
            if any(idx in patient_dropoff_map and patient_dropoff_map[idx]['key'] == dropoff_key 
                  for idx in assigned_patients):
                matching_phlebs.append(phleb_idx)
        
        best_phleb_idx = None
        min_distance = float('inf')
        
        # First try phlebotomists who already handle this dropoff
        for phleb_idx in matching_phlebs:
            phleb = available_phlebs.loc[phleb_idx]
            current_location = phleb["current_location"]
            current_workload = phleb["current_workload"]
            
            # Skip if workload would exceed limit
            if current_workload + patient_workload > avg_workload_per_phleb * 4:
                continue
                
            # Check cache for distance
            location_pair = (str(current_location), str(patient_location))
            if location_pair in distance_cache:
                distance = distance_cache[location_pair]
            else:
                distance = get_distance(current_location, patient_location)
                distance_cache[location_pair] = distance
                
            # Give preference to phlebotomists with this dropoff (20% discount)
            adjusted_distance = distance * 0.8
                
            if adjusted_distance < min_distance:
                min_distance = adjusted_distance
                best_phleb_idx = phleb_idx
        
        # If no matching phlebotomist found, try any available phlebotomist
        if best_phleb_idx is None:
            for phleb_idx, phleb in available_phlebs.iterrows():
                current_location = phleb["current_location"]
                current_workload = phleb["current_workload"]
                
                # Skip if workload would exceed limit
                if current_workload + patient_workload > avg_workload_per_phleb * 4:
                    continue
                    
                # Check cache for distance
                location_pair = (str(current_location), str(patient_location))
                if location_pair in distance_cache:
                    distance = distance_cache[location_pair]
                else:
                    distance = get_distance(current_location, patient_location)
                    distance_cache[location_pair] = distance
                    
                if distance < min_distance:
                    min_distance = distance
                    best_phleb_idx = phleb_idx
        
        # If still no phlebotomist has capacity, assign to the one with the least workload
        if best_phleb_idx is None:
            best_phleb_idx = available_phlebs["current_workload"].idxmin()
            
            # Get the distance
            pheb_location = available_phlebs.loc[best_phleb_idx, "current_location"]
            location_pair = (str(pheb_location), str(patient_location))
            
            if location_pair in distance_cache:
                min_distance = distance_cache[location_pair]
            else:
                min_distance = get_distance(pheb_location, patient_location)
                distance_cache[location_pair] = min_distance
        
        # Assign the patient to the selected phlebotomist
        phleb_id = available_phlebs.loc[best_phleb_idx, "PhlebotomistID.1"]
        
        # Update the patient with the assigned phlebotomist
        filtered_patients.at[patient_idx, "AssignedPhlebID"] = phleb_id
        filtered_patients.at[patient_idx, "TripOrderInDay"] = len(available_phlebs.loc[best_phleb_idx, "assigned_patients"]) + 1
        
        # Update the phlebotomist's workload and location
        available_phlebs.at[best_phleb_idx, "current_workload"] += patient_workload
        available_phlebs.at[best_phleb_idx, "total_distance"] += min_distance
        available_phlebs.at[best_phleb_idx, "current_location"] = patient_location
        available_phlebs.at[best_phleb_idx, "assigned_patients"].append(patient_idx)
        
        # Mark as processed
        processed_patients.add(patient_idx)
    
    # Finally, process remaining patients without dropoff locations (original approach)
    for patient_idx in remaining_without_dropoff:
        patient_location = (
            filtered_patients.loc[patient_idx, "PatientLatitude"],
            filtered_patients.loc[patient_idx, "PatientLongitude"]
        )
        patient_workload = filtered_patients.loc[patient_idx, "WorkloadPoints"]
        
        # Track best phlebotomist assignment
        best_phleb_idx = None
        min_distance = float('inf')
        
        # Find the nearest phlebotomist with capacity
        for phleb_idx, phleb in available_phlebs.iterrows():
            current_location = phleb["current_location"]
            current_workload = phleb["current_workload"]
            
            # Skip if workload would exceed limit
            if current_workload + patient_workload > avg_workload_per_phleb * 4:
                continue
                
            # Check cache for distance
            location_pair = (str(current_location), str(patient_location))
            if location_pair in distance_cache:
                distance = distance_cache[location_pair]
            else:
                distance = get_distance(current_location, patient_location)
                distance_cache[location_pair] = distance
                
            if distance < min_distance:
                min_distance = distance
                best_phleb_idx = phleb_idx
        
        # If no phlebotomist has capacity, assign to the one with the least workload
        if best_phleb_idx is None:
            best_phleb_idx = available_phlebs["current_workload"].idxmin()
            
            # Get the distance
            pheb_location = available_phlebs.loc[best_phleb_idx, "current_location"]
            location_pair = (str(pheb_location), str(patient_location))
            
            if location_pair in distance_cache:
                min_distance = distance_cache[location_pair]
            else:
                min_distance = get_distance(pheb_location, patient_location)
                distance_cache[location_pair] = min_distance
        
        # Assign the patient to the selected phlebotomist
        phleb_id = available_phlebs.loc[best_phleb_idx, "PhlebotomistID.1"]
        
        # Update the patient with the assigned phlebotomist
        filtered_patients.at[patient_idx, "AssignedPhlebID"] = phleb_id
        filtered_patients.at[patient_idx, "TripOrderInDay"] = len(available_phlebs.loc[best_phleb_idx, "assigned_patients"]) + 1
        
        # Update the phlebotomist's workload and location
        available_phlebs.at[best_phleb_idx, "current_workload"] += patient_workload
        available_phlebs.at[best_phleb_idx, "total_distance"] += min_distance
        available_phlebs.at[best_phleb_idx, "current_location"] = patient_location
        available_phlebs.at[best_phleb_idx, "assigned_patients"].append(patient_idx)
    
    # Filter to only phlebotomists with assigned patients
    available_phlebs = available_phlebs[available_phlebs['assigned_patients'].map(lambda x: len(x) > 0)]
    
    print(f"Completed patient assignment with dropoff optimization, {len(processed_patients)} patients assigned")
    
    return available_phlebs, filtered_patients


def parse_coordinates(coord_str):
    """Parse a comma-separated string of coordinates back into a tuple"""
    if not coord_str or pd.isna(coord_str):
        return None
    lat, lng = coord_str.split(',')
    return (float(lat), float(lng))


def process_city_assignments(patient_df, phleb_df, workload_df, target_date, target_city, 
                        api_key=None, use_scheduled_time=True, redis_host='localhost', redis_port=6379):
    """
    Main function to process patient assignments for a city and date.

    Args:
        patient_df: DataFrame with patient orders
        phleb_df: DataFrame with phlebotomist information
        workload_df: DataFrame with city workload information
        target_date: Date to analyze
        target_city: City to analyze
        api_key: OpenRouteService API key (optional)
        use_scheduled_time: Whether to use scheduled time for routing (True) or optimize by proximity (False)
        redis_host: Redis host (default: localhost)
        redis_port: Redis port (default: 6379)

    Returns:
        Tuple of (map, assigned_phlebs_df, assigned_patients_df)
    """
    # Initialize Redis connection if possible
    try:
        from redis_utils import initialize_redis, initialize_ors_client
        redis_conn = initialize_redis(host=redis_host, port=redis_port)

        # Test Redis connection
        redis_conn.ping()
        print("Successfully connected to Redis")
    except Exception as e:
        print(f"Warning: Redis connection failed - {e}. Using fallback method.")
        redis_conn = None

    # Initialize ORS client if API key is provided
    ors_client = None
    if api_key:
        try:
            from redis_utils import initialize_ors_client
            ors_client = initialize_ors_client(api_key)
            print("Successfully initialized OpenRouteService client")
        except Exception as e:
            print(f"Warning: OpenRouteService initialization failed - {e}. Using fallback method.")

    # Step 1: Assign patients to phlebotomists
    assigned_phlebs, assigned_patients = assign_patients_to_phlebotomists(
        patient_df, phleb_df, workload_df, target_date, target_city, 
        api_key=api_key, redis_conn=redis_conn
    )
    print("="*30)
    print("Assigned Phlebs:")
    print(assigned_phlebs)

    if assigned_phlebs.empty or assigned_patients.empty:
        return None, pd.DataFrame(), pd.DataFrame()

    # Step 2: Optimize routes based on the selected approach
    optimized_patients = optimize_routes(
        assigned_phlebs, 
        assigned_patients, 
        use_scheduled_time=use_scheduled_time,
        ors_client=ors_client
    )
    
    print("Optimized Patients : ")
    print(optimized_patients)

    # Step 3: Re-order the trip order based on preferred time
    for phleb_id in optimized_patients["AssignedPhlebID"].unique():
        phleb_patients = optimized_patients[optimized_patients["AssignedPhlebID"] == phleb_id].copy()
        # Sort by PreferredTime
        phleb_patients = phleb_patients.sort_values("PreferredTime")
        # Reassign TripOrderInDay based on PreferredTime order
        for trip_order, patient_idx in enumerate(phleb_patients.index, 1):
            optimized_patients.at[patient_idx, "TripOrderInDay"] = trip_order

    # Step 4: Create the assignment map with OpenRouteService for routing if available
    assignment_map, route_distances = create_assignment_map(
        assigned_phlebs, optimized_patients, target_date, target_city, 
        api_key=api_key, return_distances=True, use_scheduled_time=use_scheduled_time,
        ors_client=ors_client  # Pass the ORS client if available
    )

    # Update phlebotomist distances based on the actual routes
    for phleb_id, distance in route_distances.items():
        # Find the index of this phlebotomist in the DataFrame
        phleb_indices = assigned_phlebs.index[assigned_phlebs["PhlebotomistID.1"] == phleb_id].tolist()
        if phleb_indices:
            assigned_phlebs.at[phleb_indices[0], "total_distance"] = distance

    # Reset indices for return
    assigned_phlebs = assigned_phlebs.reset_index()
    optimized_patients = optimized_patients.reset_index()

    return assignment_map, assigned_phlebs, optimized_patients


# def optimize_routes(assigned_phlebs, assigned_patients, use_scheduled_time=True, ors_client=None):
#     """
#     Optimize routes for each phlebotomist using either scheduled time or nearest neighbor algorithm,
#     with improved patient clustering and smarter specimen drop-off logic.
    
#     Uses LabID from dropoffs.csv as the key identifier for dropoff locations.

#     Args:
#         assigned_phlebs (pd.DataFrame): DataFrame with assigned phlebotomists
#         assigned_patients (pd.DataFrame): DataFrame with assigned patients
#         use_scheduled_time (bool): Whether to sort by scheduled time or use nearest neighbor
#         ors_client: OpenRouteService client (optional)

#     Returns:
#         pd.DataFrame: Updated patient DataFrame with optimized route information
#     """
#     import pandas as pd
#     from datetime import timedelta, datetime
#     import numpy as np
#     from collections import defaultdict
#     from geopy.distance import geodesic

#     # Create a copy of the patients DataFrame to modify
#     updated_patients = assigned_patients.copy()

#     # Initialize dropoff information columns if they don't exist
#     if 'DropOffSequence' not in updated_patients.columns:
#         updated_patients['DropOffSequence'] = None  # To track when specimen is dropped off

#     # Load dropoff locations from CSV
#     try:
#         dropoffs_df = pd.read_csv("All_Dropoffs.csv")
#         print(f"Loaded dropoffs data: {len(dropoffs_df)} locations")
        
#         # Print a sample to verify structure
#         if not dropoffs_df.empty:
#             print("Dropoffs columns:", dropoffs_df.columns.tolist())
#             print("First dropoff record:", dropoffs_df.iloc[0].to_dict())
#     except Exception as e:
#         print(f"Error loading dropoffs: {e}")
#         dropoffs_df = pd.DataFrame(columns=["LabID", "Clinic", "Address", "City", "State", "Zipcode", "Latitude", "Longitude"])

#     def estimate_travel_time(distance_miles):
#         """Estimate travel time in minutes based on average speed (e.g., 30 mph)."""
#         return max(5, round(distance_miles * 60 / 30))  # Minimum 5 mins per stop

#     def estimate_draw_time(workload_points):
#         """Estimate draw time in minutes based on workload points."""
#         return max(5, int(workload_points * 10))  # Example: 10 mins per point

#     def calculate_distance(point1, point2, ors=None, use_ors = False):
#         """Calculate distance between two points using ORS or geodesic."""
#         if not use_ors:
#             return geodesic(point1, point2).miles
        
#         # Try ORS if use_ors is True
#         if ors is not None:
#             try:
#                 # Format for ORS API: [lon, lat]
#                 coords_for_ors = [[point1[1], point1[0]], [point2[1], point2[0]]]
#                 route = ors.directions(
#                     coordinates=coords_for_ors,
#                     profile='driving-car',
#                     format='geojson',
#                     units='mi',
#                     instructions=False
#                 )
                
#                 # Extract distance from the response
#                 if 'features' in route and len(route['features']) > 0:
#                     props = route['features'][0]['properties']
#                     if 'segments' in props and len(props['segments']) > 0:
#                         return props['segments'][0].get('distance', 0)
#                     elif 'summary' in props:
#                         return props['summary'].get('distance', 0)
#                     elif 'distance' in props:
#                         return props['distance']
#             except Exception as e:
#                 print(f"Error calculating ORS distance: {e}, falling back to geodesic")
        
#         # Fallback to geodesic distance

#     # Debug patient data
#     print("*" * 50)
#     print("PATIENT DATA FOR ROUTE OPTIMIZATION:")
#     print(f"Total patients: {len(updated_patients)}")
#     print("Unique phlebotomists:", updated_patients['AssignedPhlebID'].unique())
#     if 'DropOffLocation' in updated_patients.columns:
#         print("DropOffLocation values:", updated_patients['DropOffLocation'].unique())
#     print("*" * 50)

#     # Process each phlebotomist
#     for idx, phleb in assigned_phlebs.iterrows():
#         phleb_id = phleb["PhlebotomistID.1"]
#         phleb_name = phleb.get('PhlebotomistName', f'Phlebotomist {phleb_id}')
#         phleb_location = (phleb["PhlebotomistLatitude"], phleb["PhlebotomistLongitude"])
#         phleb_patients = updated_patients[updated_patients["AssignedPhlebID"] == phleb_id].copy()
        
#         print(f"Processing routes for {phleb_name} with {len(phleb_patients)} patients")
        
#         if phleb_patients.empty:
#             continue

#         # Process dropoff locations using LabID from DropOffLocation field
#         dropoff_dict = {}  # Map LabID to dropoff info
#         patient_to_dropoff = {}  # Map patient index to LabID
        
#         # First, map patients to dropoff locations using DropOffLocation field
#         for pat_idx, patient in phleb_patients.iterrows():
#             if 'DropOffLocation' in patient and pd.notna(patient['DropOffLocation']):
#                 # Get patient location
#                 patient_location = (patient["PatientLatitude"], patient["PatientLongitude"])
                
#                 # Find matching dropoff in dropoffs_df
#                 clinic_name = patient['DropOffLocation']
#                 matching_dropoffs = dropoffs_df[dropoffs_df['Clinic'].str.lower() == clinic_name.lower()]
                
#                 # Further filter by state if available
#                 if 'PatientState' in patient and pd.notna(patient['PatientState']) and not matching_dropoffs.empty:
#                     state_dropoffs = matching_dropoffs[matching_dropoffs['State'] == patient['PatientState']]
#                     if not state_dropoffs.empty:
#                         matching_dropoffs = state_dropoffs
                
#                 # Further filter by city if available
#                 if 'City' in patient and pd.notna(patient['City']) and not matching_dropoffs.empty:
#                     city_dropoffs = matching_dropoffs[matching_dropoffs['City'] == patient['City']]
#                     if not city_dropoffs.empty:
#                         matching_dropoffs = city_dropoffs
                
#                 # Further filter by zipcode if available
#                 if 'PatientZip' in patient and pd.notna(patient['PatientZip']) and not matching_dropoffs.empty:
#                     try:
#                         zip_dropoffs = matching_dropoffs[matching_dropoffs['Zipcode'] == int(patient['PatientZip'])]
#                         if not zip_dropoffs.empty:
#                             matching_dropoffs = zip_dropoffs
#                     except (ValueError, TypeError):
#                         # Handle case where PatientZip isn't convertible to int
#                         pass
                
#                 # Find nearest dropoff if multiple matches
#                 if not matching_dropoffs.empty:
#                     if len(matching_dropoffs) > 1:
#                         # Find the closest dropoff location
#                         min_distance = float('inf')
#                         nearest_dropoff = None
                        
#                         print(f"Checking {len(matching_dropoffs)} dropoffs")
#                         print(matching_dropoffs)
                        
                        
#                         for _, dropoff in matching_dropoffs.iterrows():
#                             dropoff_location = (dropoff['Latitude'], dropoff['Longitude'])
#                             dist = calculate_distance(patient_location, dropoff_location, ors_client, use_ors=False)
#                             if dist < min_distance:
#                                 min_distance = dist
#                                 nearest_dropoff = dropoff
                        
#                         if nearest_dropoff is not None:
#                             dropoff = nearest_dropoff
#                             print(f"Multiple dropoffs found for patient {pat_idx}. Selected nearest: {dropoff['LabID']} at {min_distance:.2f} miles")
#                         else:
#                             # If calculation fails, just use the first one
#                             dropoff = matching_dropoffs.iloc[0]
#                     else:
#                         # Only one match found
#                         dropoff = matching_dropoffs.iloc[0]
                    
#                     # Get key fields
#                     lab_id = dropoff['LabID']
#                     lat = dropoff['Latitude']
#                     lon = dropoff['Longitude']
                    
#                     # Store in dropoff dict if not already there
#                     if lab_id not in dropoff_dict:
#                         dropoff_dict[lab_id] = {
#                             'location': (lat, lon),
#                             'lab_id': lab_id,
#                             'clinic_name': dropoff['Clinic'],
#                             'address': dropoff['Address'],
#                             'city': dropoff.get('City', ''),
#                             'state': dropoff.get('State', ''),
#                             'zipcode': dropoff.get('Zipcode', ''),
#                             'patients': []
#                         }
                    
#                     # Map this patient to this dropoff
#                     dropoff_dict[lab_id]['patients'].append(pat_idx)
#                     patient_to_dropoff[pat_idx] = lab_id
                    
#                     # Update patient record with dropoff information
#                     updated_patients.at[pat_idx, 'DropOffClinicLoc'] = f"{lat},{lon}"
#                     updated_patients.at[pat_idx, 'DropOffLabID'] = lab_id
#                     updated_patients.at[pat_idx, 'DropOffClinicName'] = dropoff['Clinic']
                    
#                     # Print diagnostic info
#                     patient_id = patient.get('PatientSysID', pat_idx)
#                     print(f"Patient {patient_id} mapped to dropoff {lab_id}_{dropoff['Clinic']}")
#                 else:
#                     print(f"Warning: No matching dropoff found for patient {pat_idx} with clinic {clinic_name}")
        
#         # Log dropoff locations found
#         print(f"Found {len(dropoff_dict)} unique dropoff locations")
#         for lab_id, info in dropoff_dict.items():
#             patient_ids = [str(idx) for idx in info['patients']]
#             print(f"  - Dropoff {info['clinic_name']} (LabID: {lab_id}): Patients {', '.join(patient_ids)}")
#             print(f"    Location: {info['location'][0]}, {info['location'][1]}")
#             if 'city' in info and 'state' in info:
#                 print(f"    Address: {info.get('address', 'Unknown')}, {info.get('city', '')}, {info.get('state', '')} {info.get('zipcode', '')}")

#         # Sort patients by scheduled time or optimize by proximity
#         if use_scheduled_time:
#             # Sort by scheduled time, then assign trip order
#             sorted_patients = phleb_patients.sort_values("ScheduledDtm")
#             for trip_order, (idx, _) in enumerate(sorted_patients.iterrows(), 1):
#                 updated_patients.at[idx, "TripOrderInDay"] = trip_order
#                 updated_patients.at[idx, "PreferredTime"] = sorted_patients.at[idx, "ScheduledDtm"]
#         else:
#             # Use nearest neighbor algorithm
#             current_location = phleb_location
#             unvisited = list(phleb_patients.index)
#             trip_order = 1
            
#             while unvisited:
#                 # Find closest patient
#                 next_patient_idx = min(
#                     unvisited,
#                     key=lambda idx: calculate_distance(
#                         current_location,
#                         (phleb_patients.at[idx, "PatientLatitude"], phleb_patients.at[idx, "PatientLongitude"]),
#                         ors_client
#                     )
#                 )
                
#                 # Assign order
#                 updated_patients.at[next_patient_idx, "TripOrderInDay"] = trip_order
#                 trip_order += 1
                
#                 # Update location
#                 current_location = (
#                     phleb_patients.at[next_patient_idx, "PatientLatitude"],
#                     phleb_patients.at[next_patient_idx, "PatientLongitude"]
#                 )
                
#                 # Remove from unvisited
#                 unvisited.remove(next_patient_idx)
        
#         # CRITICAL CHANGE: Now add dropoffs after all patients
#         # This is a simplification that guarantees dropoffs appear after patients
#         drop_sequence = max(updated_patients.loc[phleb_patients.index, "TripOrderInDay"].max() + 1, 1)
        
#         # Handle each unique dropoff location
#         for lab_id, dropoff_info in dropoff_dict.items():
#             # Assign the same sequence number to all patients that share this dropoff
#             for patient_idx in dropoff_info['patients']:
#                 updated_patients.at[patient_idx, 'DropOffSequence'] = drop_sequence
            
#             print(f"Assigned dropoff sequence {drop_sequence} to {len(dropoff_info['patients'])} patients for {dropoff_info['clinic_name']} (LabID: {lab_id})")
#             drop_sequence += 1

#     # Add detailed logging of the final routes
#     print("\n" + "="*80)
#     print("FINAL ROUTE OPTIMIZATION RESULTS")
#     print("="*80)
    
#     # Process each phlebotomist's route for logging
#     for idx, phleb in assigned_phlebs.iterrows():
#         phleb_id = phleb["PhlebotomistID.1"]
#         phleb_name = phleb.get('PhlebotomistName', f'Phlebotomist {phleb_id}')
#         phleb_location = (phleb["PhlebotomistLatitude"], phleb["PhlebotomistLongitude"])
        
#         print(f"\nROUTE FOR {phleb_name} (ID: {phleb_id}):")
#         print("-"*50)
        
#         # Get patients for this phlebotomist
#         phleb_patients = updated_patients[updated_patients["AssignedPhlebID"] == phleb_id].copy()
        
#         if phleb_patients.empty:
#             print(f"  No patients assigned to {phleb_name}")
#             continue
        
#         # Start from phlebotomist location
#         print(f"  1. START: Phlebotomist Base ({phleb_location[0]:.6f}, {phleb_location[1]:.6f})")
        
#         # Create a complete list of all stops
#         stops = []
        
#         # Add phlebotomist as first stop
#         current_location = phleb_location
#         total_distance = 0
        
#         # Add all patients based on trip order
#         for idx, patient in phleb_patients.sort_values("TripOrderInDay").iterrows():
#             patient_loc = (patient["PatientLatitude"], patient["PatientLongitude"])
#             patient_time = patient["PreferredTime"].strftime('%H:%M') if pd.notna(patient["PreferredTime"]) else "Unknown"
            
#             # Safely get patient ID
#             if 'PatientID' in patient and pd.notna(patient['PatientID']):
#                 patient_id = patient['PatientID']
#             elif 'PatientSysID' in patient and pd.notna(patient['PatientSysID']):
#                 patient_id = patient['PatientSysID']
#             else:
#                 patient_id = idx if isinstance(idx, (int, str)) else str(idx)
            
#             stops.append({
#                 'type': 'patient',
#                 'location': patient_loc,
#                 'id': patient_id,
#                 'time': patient_time,
#                 'idx': idx
#             })
        
#         # Add dropoffs after patients
#         processed_dropoffs = set()
        
#         for idx, patient in phleb_patients.sort_values("DropOffSequence").iterrows():
#             if pd.notna(patient['DropOffSequence']) and pd.notna(patient['DropOffLabID']):
#                 lab_id = patient['DropOffLabID']
                
#                 # Only add each unique dropoff once
#                 if lab_id not in processed_dropoffs:
#                     processed_dropoffs.add(lab_id)
                    
#                     # Get dropoff info
#                     dropoff_lat, dropoff_lon = None, None
                    
#                     # Try to get coordinates from DropOffClinicLoc
#                     if pd.notna(patient['DropOffClinicLoc']):
#                         try:
#                             if isinstance(patient['DropOffClinicLoc'], str):
#                                 dropoff_lat, dropoff_lon = map(float, patient['DropOffClinicLoc'].split(","))
#                             elif isinstance(patient['DropOffClinicLoc'], (tuple, list)):
#                                 dropoff_lat, dropoff_lon = patient['DropOffClinicLoc']
#                         except Exception as e:
#                             print(f"Error parsing DropOffClinicLoc: {e}")
                    
#                     # If not found, look up in dropoffs_df
#                     if dropoff_lat is None or dropoff_lon is None:
#                         matching_dropoffs = dropoffs_df[dropoffs_df['LabID'] == lab_id]
#                         if not matching_dropoffs.empty:
#                             dropoff_lat = matching_dropoffs.iloc[0]['Latitude']
#                             dropoff_lon = matching_dropoffs.iloc[0]['Longitude']
#                             print(f"Using coordinates from dropoffs.csv for {lab_id}: {dropoff_lat}, {dropoff_lon}")
#                         else:
#                             print(f"Warning: Could not find coordinates for dropoff {lab_id}")
                    
#                     if dropoff_lat is not None and dropoff_lon is not None:
#                         dropoff_loc = (dropoff_lat, dropoff_lon)
                        
#                         # Find all patients that share this dropoff
#                         patients_for_dropoff = []
#                         for p_idx, p in phleb_patients.iterrows():
#                             if pd.notna(p['DropOffLabID']) and p['DropOffLabID'] == lab_id:
#                                 # Safely get patient ID
#                                 if 'PatientID' in p and pd.notna(p['PatientID']):
#                                     p_id = p['PatientID']
#                                 elif 'PatientSysID' in p and pd.notna(p['PatientSysID']):
#                                     p_id = p['PatientSysID']
#                                 else:
#                                     p_id = p_idx if isinstance(p_idx, (int, str)) else str(p_idx)
                                
#                                 patients_for_dropoff.append(p_id)
                        
#                         # Get clinic name
#                         clinic_name = patient.get('DropOffClinicName', 'Unknown')
#                         if clinic_name == 'Unknown':
#                             matching_dropoffs = dropoffs_df[dropoffs_df['LabID'] == lab_id]
#                             if not matching_dropoffs.empty:
#                                 clinic_name = matching_dropoffs.iloc[0]['Clinic']
                        
#                         stops.append({
#                             'type': 'dropoff',
#                             'location': dropoff_loc,
#                             'id': lab_id,
#                             'clinic': clinic_name,
#                             'for_patients': ', '.join(map(str, patients_for_dropoff)),
#                             'idx': idx,
#                             'sequence': patient['DropOffSequence']
#                         })
        
#         # Sort stops - patients by trip order, then dropoffs
#         # This ensures we visit all patients first, then do dropoffs
#         stops.sort(key=lambda x: float('inf') if x['type'] == 'dropoff' else phleb_patients.at[x['idx'], 'TripOrderInDay'])
        
#         # Now print the route
#         for i, stop in enumerate(stops, start=2):  # Start at 2 (after phlebotomist base)
#             # Calculate distance from previous location
#             distance = calculate_distance(current_location, stop['location'], ors_client)
#             total_distance += distance
            
#             if stop['type'] == 'patient':
#                 print(f"  {i}. PATIENT: {stop['id']} at ({stop['location'][0]:.6f}, {stop['location'][1]:.6f})")
#                 print(f"     Time: {stop['time']}, Distance from previous: {distance:.2f} miles")
#             else:  # dropoff
#                 print(f"  {i}. DROPOFF: Lab {stop['id']} - {stop['clinic']} at ({stop['location'][0]:.6f}, {stop['location'][1]:.6f})")
#                 print(f"     For Patients: {stop['for_patients']}, Distance from previous: {distance:.2f} miles")
            
#             current_location = stop['location']
        
#         print(f"  TOTAL ROUTE DISTANCE: {total_distance:.2f} miles")
        
#         # Print patient-dropoff relationships
#         print("\n  Patient-Dropoff Summary:")
#         dropoff_map = {}
#         for idx, patient in phleb_patients.iterrows():
#             if pd.notna(patient['DropOffLabID']) and pd.notna(patient['DropOffSequence']):
#                 dropoff_id = patient['DropOffLabID']
                
#                 # Safely get patient ID
#                 if 'PatientID' in patient and pd.notna(patient['PatientID']):
#                     patient_id = patient['PatientID']
#                 elif 'PatientSysID' in patient and pd.notna(patient['PatientSysID']):
#                     patient_id = patient['PatientSysID']
#                 else:
#                     patient_id = idx if isinstance(idx, (int, str)) else str(idx)
                
#                 if dropoff_id not in dropoff_map:
#                     dropoff_map[dropoff_id] = []
#                 dropoff_map[dropoff_id].append(patient_id)
        
#         if dropoff_map:
#             for dropoff_id, patient_ids in dropoff_map.items():
#                 patients_str = ", ".join(str(pid) for pid in patient_ids)
#                 print(f"  - Dropoff {dropoff_id}: Specimens from Patients {patients_str}")
#         else:
#             print("  - No dropoffs assigned")
    
#     print("\n" + "="*80)
    
#     return updated_patients


def optimize_routes(assigned_phlebs, assigned_patients, use_scheduled_time=True, ors_client=None):
    """
    Optimize routes for each phlebotomist using either scheduled time or nearest neighbor algorithm,
    with improved patient clustering and smarter specimen drop-off logic.
    
    Uses LabID from dropoffs.csv as the key identifier for dropoff locations with special handling for
    same-clinic dropoffs to optimize route efficiency.

    Args:
        assigned_phlebs (pd.DataFrame): DataFrame with assigned phlebotomists
        assigned_patients (pd.DataFrame): DataFrame with assigned patients
        use_scheduled_time (bool): Whether to sort by scheduled time or use nearest neighbor
        ors_client: OpenRouteService client (optional)

    Returns:
        pd.DataFrame: Updated patient DataFrame with optimized route information
    """
    import pandas as pd
    from datetime import timedelta, datetime
    import numpy as np
    from collections import defaultdict
    from geopy.distance import geodesic

    # Create a copy of the patients DataFrame to modify
    updated_patients = assigned_patients.copy()

    # Initialize dropoff information columns if they don't exist
    if 'DropOffSequence' not in updated_patients.columns:
        updated_patients['DropOffSequence'] = None  # To track when specimen is dropped off

    # Load dropoff locations from CSV
    try:
        dropoffs_df = pd.read_csv("All_Dropoffs.csv")
        print(f"Loaded dropoffs data: {len(dropoffs_df)} locations")
        
        # Print a sample to verify structure
        if not dropoffs_df.empty:
            print("Dropoffs columns:", dropoffs_df.columns.tolist())
            print("First dropoff record:", dropoffs_df.iloc[0].to_dict())
    except Exception as e:
        print(f"Error loading dropoffs: {e}")
        dropoffs_df = pd.DataFrame(columns=["LabID", "Clinic", "Address", "City", "State", "Zipcode", "Latitude", "Longitude"])

    def estimate_travel_time(distance_miles):
        """Estimate travel time in minutes based on average speed (e.g., 30 mph)."""
        return max(5, round(distance_miles * 60 / 30))  # Minimum 5 mins per stop

    def estimate_draw_time(workload_points):
        """Estimate draw time in minutes based on workload points."""
        return max(5, int(workload_points * 10))  # Example: 10 mins per point

    def calculate_distance(point1, point2, ors=None, use_ors=False):
        """Calculate distance between two points using ORS or geodesic."""
        if not use_ors:
            return geodesic(point1, point2).miles
        
        # Try ORS if use_ors is True
        if ors is not None:
            try:
                # Format for ORS API: [lon, lat]
                coords_for_ors = [[point1[1], point1[0]], [point2[1], point2[0]]]
                route = ors.directions(
                    coordinates=coords_for_ors,
                    profile='driving-car',
                    format='geojson',
                    units='mi',
                    instructions=False
                )
                
                # Extract distance from the response
                if 'features' in route and len(route['features']) > 0:
                    props = route['features'][0]['properties']
                    if 'segments' in props and len(props['segments']) > 0:
                        return props['segments'][0].get('distance', 0)
                    elif 'summary' in props:
                        return props['summary'].get('distance', 0)
                    elif 'distance' in props:
                        return props['distance']
            except Exception as e:
                print(f"Error calculating ORS distance: {e}, falling back to geodesic")
        
        # Fallback to geodesic distance
        return geodesic(point1, point2).miles

    # Debug patient data
    print("*" * 50)
    print("PATIENT DATA FOR ROUTE OPTIMIZATION:")
    print(f"Total patients: {len(updated_patients)}")
    print("Unique phlebotomists:", updated_patients['AssignedPhlebID'].unique())
    if 'DropOffLocation' in updated_patients.columns:
        print("DropOffLocation values:", updated_patients['DropOffLocation'].unique())
    print("*" * 50)

    # Process each phlebotomist
    for idx, phleb in assigned_phlebs.iterrows():
        phleb_id = phleb["PhlebotomistID.1"]
        phleb_name = phleb.get('PhlebotomistName', f'Phlebotomist {phleb_id}')
        phleb_location = (phleb["PhlebotomistLatitude"], phleb["PhlebotomistLongitude"])
        phleb_patients = updated_patients[updated_patients["AssignedPhlebID"] == phleb_id].copy()
        
        print(f"Processing routes for {phleb_name} with {len(phleb_patients)} patients")
        
        if phleb_patients.empty:
            continue

        # Process dropoff locations using LabID from DropOffLocation field
        dropoff_dict = {}  # Map LabID to dropoff info
        patient_to_dropoff = {}  # Map patient index to LabID
        clinic_to_dropoffs = defaultdict(list)  # Map clinic name to list of dropoff IDs
        
        # First, map patients to dropoff locations using DropOffLocation field
        for pat_idx, patient in phleb_patients.iterrows():
            if 'DropOffLocation' in patient and pd.notna(patient['DropOffLocation']):
                # Get patient location
                patient_location = (patient["PatientLatitude"], patient["PatientLongitude"])
                
                # Find matching dropoff in dropoffs_df
                clinic_name = patient['DropOffLocation']
                matching_dropoffs = dropoffs_df[dropoffs_df['Clinic'].str.lower() == clinic_name.lower()]
                
                # Further filter by state if available
                if 'PatientState' in patient and pd.notna(patient['PatientState']) and not matching_dropoffs.empty:
                    state_dropoffs = matching_dropoffs[matching_dropoffs['State'] == patient['PatientState']]
                    if not state_dropoffs.empty:
                        matching_dropoffs = state_dropoffs
                
                # Further filter by city if available
                if 'City' in patient and pd.notna(patient['City']) and not matching_dropoffs.empty:
                    city_dropoffs = matching_dropoffs[matching_dropoffs['City'] == patient['City']]
                    if not city_dropoffs.empty:
                        matching_dropoffs = city_dropoffs
                
                # Further filter by zipcode if available
                if 'PatientZip' in patient and pd.notna(patient['PatientZip']) and not matching_dropoffs.empty:
                    try:
                        zip_dropoffs = matching_dropoffs[matching_dropoffs['Zipcode'] == int(patient['PatientZip'])]
                        if not zip_dropoffs.empty:
                            matching_dropoffs = zip_dropoffs
                    except (ValueError, TypeError):
                        # Handle case where PatientZip isn't convertible to int
                        pass
                
                # Find nearest dropoff if multiple matches
                if not matching_dropoffs.empty:
                    if len(matching_dropoffs) > 1:
                        # Find the closest dropoff location
                        min_distance = float('inf')
                        nearest_dropoff = None
                        
                        print(f"Checking {len(matching_dropoffs)} dropoffs")
                        print(matching_dropoffs[['LabID', 'Clinic', 'Address', 'City', 'State', 'Zipcode', 'Latitude', 'Longitude']])
                        
                        for _, dropoff in matching_dropoffs.iterrows():
                            dropoff_location = (dropoff['Latitude'], dropoff['Longitude'])
                            dist = calculate_distance(patient_location, dropoff_location, ors_client, use_ors=False)
                            if dist < min_distance:
                                min_distance = dist
                                nearest_dropoff = dropoff
                        
                        if nearest_dropoff is not None:
                            dropoff = nearest_dropoff
                            print(f"Multiple dropoffs found for patient {pat_idx}. Selected nearest: {dropoff['LabID']} at {min_distance:.2f} miles")
                        else:
                            # If calculation fails, just use the first one
                            dropoff = matching_dropoffs.iloc[0]
                    else:
                        # Only one match found
                        dropoff = matching_dropoffs.iloc[0]
                    
                    # Get key fields
                    lab_id = dropoff['LabID']
                    lat = dropoff['Latitude']
                    lon = dropoff['Longitude']
                    
                    # Store in dropoff dict if not already there
                    if lab_id not in dropoff_dict:
                        dropoff_dict[lab_id] = {
                            'location': (lat, lon),
                            'lab_id': lab_id,
                            'clinic_name': dropoff['Clinic'],
                            'address': dropoff['Address'],
                            'city': dropoff.get('City', ''),
                            'state': dropoff.get('State', ''),
                            'zipcode': dropoff.get('Zipcode', ''),
                            'patients': []
                        }
                        # Add to clinic-to-dropoffs mapping
                        clinic_to_dropoffs[dropoff['Clinic']].append(lab_id)
                    
                    # Map this patient to this dropoff
                    dropoff_dict[lab_id]['patients'].append(pat_idx)
                    patient_to_dropoff[pat_idx] = lab_id
                    
                    # Update patient record with dropoff information
                    updated_patients.at[pat_idx, 'DropOffClinicLoc'] = f"{lat},{lon}"
                    updated_patients.at[pat_idx, 'DropOffLabID'] = lab_id
                    updated_patients.at[pat_idx, 'DropOffClinicName'] = dropoff['Clinic']
                    
                    # Print diagnostic info
                    patient_id = patient.get('PatientSysID', pat_idx)
                    print(f"Patient {patient_id} mapped to dropoff {lab_id}_{dropoff['Clinic']}")
                else:
                    print(f"Warning: No matching dropoff found for patient {pat_idx} with clinic {clinic_name}")
        
        # Log dropoff locations found
        print(f"Found {len(dropoff_dict)} unique dropoff locations")
        for lab_id, info in dropoff_dict.items():
            patient_ids = [str(idx) for idx in info['patients']]
            print(f"  - Dropoff {info['clinic_name']} (LabID: {lab_id}): Patients {', '.join(patient_ids)}")
            print(f"    Location: {info['location'][0]}, {info['location'][1]}")
            if 'city' in info and 'state' in info:
                print(f"    Address: {info.get('address', 'Unknown')}, {info.get('city', '')}, {info.get('state', '')} {info.get('zipcode', '')}")

        # Sort patients by scheduled time or optimize by proximity
        if use_scheduled_time:
            # Sort by scheduled time, then assign trip order
            sorted_patients = phleb_patients.sort_values("ScheduledDtm")
            for trip_order, (idx, _) in enumerate(sorted_patients.iterrows(), 1):
                updated_patients.at[idx, "TripOrderInDay"] = trip_order
                updated_patients.at[idx, "PreferredTime"] = sorted_patients.at[idx, "ScheduledDtm"]
        else:
            # Use nearest neighbor algorithm
            current_location = phleb_location
            unvisited = list(phleb_patients.index)
            trip_order = 1
            
            while unvisited:
                # Find closest patient
                next_patient_idx = min(
                    unvisited,
                    key=lambda idx: calculate_distance(
                        current_location,
                        (phleb_patients.at[idx, "PatientLatitude"], phleb_patients.at[idx, "PatientLongitude"]),
                        ors_client
                    )
                )
                
                # Assign order
                updated_patients.at[next_patient_idx, "TripOrderInDay"] = trip_order
                trip_order += 1
                
                # Update location
                current_location = (
                    phleb_patients.at[next_patient_idx, "PatientLatitude"],
                    phleb_patients.at[next_patient_idx, "PatientLongitude"]
                )
                
                # Remove from unvisited
                unvisited.remove(next_patient_idx)
        
        # CRITICAL CHANGE: Now add dropoffs after all patients
        # First, consolidate dropoffs for the same clinic if applicable
        consolidated_dropoffs = {}  # Will store the best dropoff for each clinic
        
        # Go through all clinics with multiple dropoffs
        for clinic_name, lab_ids in clinic_to_dropoffs.items():
            if len(lab_ids) > 1:
                print(f"DROPOFF CONSOLIDATION: Found {len(lab_ids)} dropoffs for clinic '{clinic_name}'")
                print(f"  Options: {', '.join(lab_ids)}")
                
                # Calculate the last patient location (after all patients are visited)
                last_patient_idx = updated_patients.loc[phleb_patients.index, "TripOrderInDay"].idxmax()
                if pd.isna(last_patient_idx):
                    # If no valid TripOrderInDay, use phlebotomist location as reference
                    last_location = phleb_location
                else:
                    last_location = (
                        phleb_patients.at[last_patient_idx, "PatientLatitude"],
                        phleb_patients.at[last_patient_idx, "PatientLongitude"]
                    )
                
                # Find the best (closest) dropoff location for this clinic
                best_lab_id = None
                min_distance = float('inf')
                distances = {}
                
                # Calculate all distances first for comparison
                for lab_id in lab_ids:
                    dropoff_location = dropoff_dict[lab_id]['location']
                    distance = calculate_distance(last_location, dropoff_location, ors_client, use_ors=False)
                    distances[lab_id] = distance
                    if distance < min_distance:
                        min_distance = distance
                        best_lab_id = lab_id
                
                # Log the calculations
                print(f"  Calculating distances from last patient location {last_location}:")
                for lab_id, distance in distances.items():
                    print(f"    - {lab_id}: {distance:.2f} miles {' (SELECTED as closest)' if lab_id == best_lab_id else ''}")
                
                # Now we have the best dropoff for this clinic
                consolidated_dropoffs[clinic_name] = best_lab_id
                
                # Reassign all patients to this best dropoff
                all_patients_for_clinic = []
                for lab_id in lab_ids:
                    if lab_id != best_lab_id:  # Skip the best one as it's already correctly assigned
                        # Move patients from other dropoffs to the best one
                        patients_to_move = dropoff_dict[lab_id]['patients']
                        for pat_idx in patients_to_move:
                            print(f"  Reassigning patient {pat_idx} from dropoff {lab_id} to {best_lab_id}")
                            
                            # Update patient's dropoff information
                            best_dropoff = dropoff_dict[best_lab_id]
                            updated_patients.at[pat_idx, 'DropOffClinicLoc'] = f"{best_dropoff['location'][0]},{best_dropoff['location'][1]}"
                            updated_patients.at[pat_idx, 'DropOffLabID'] = best_lab_id
                            
                            # Add to the best dropoff's patient list
                            dropoff_dict[best_lab_id]['patients'].append(pat_idx)
                            
                            # Update patient_to_dropoff mapping
                            patient_to_dropoff[pat_idx] = best_lab_id
                            
                            all_patients_for_clinic.append(pat_idx)
                        
                        # Remove patients from original dropoff
                        dropoff_dict[lab_id]['patients'] = []
                    else:
                        # Add patients from best dropoff to the list
                        all_patients_for_clinic.extend(dropoff_dict[lab_id]['patients'])
                
                print(f"  CONSOLIDATED: All {len(all_patients_for_clinic)} patients for {clinic_name} will use dropoff {best_lab_id}")
            
            else:
                # Only one dropoff for this clinic, no consolidation needed
                consolidated_dropoffs[clinic_name] = lab_ids[0]
        
        # Remove empty dropoffs after consolidation
        dropoff_dict = {lab_id: info for lab_id, info in dropoff_dict.items() if info['patients']}
        
        # Now assign dropoff sequences after consolidation
        drop_sequence = max(updated_patients.loc[phleb_patients.index, "TripOrderInDay"].max() + 1, 1)
        
        # Handle each unique dropoff location
        for lab_id, dropoff_info in dropoff_dict.items():
            # Assign the same sequence number to all patients that share this dropoff
            for patient_idx in dropoff_info['patients']:
                updated_patients.at[patient_idx, 'DropOffSequence'] = drop_sequence
            
            print(f"Assigned dropoff sequence {drop_sequence} to {len(dropoff_info['patients'])} patients for {dropoff_info['clinic_name']} (LabID: {lab_id})")
            drop_sequence += 1

    # Add detailed logging of the final routes
    print("\n" + "="*80)
    print("FINAL ROUTE OPTIMIZATION RESULTS")
    print("="*80)
    
    # Process each phlebotomist's route for logging
    for idx, phleb in assigned_phlebs.iterrows():
        phleb_id = phleb["PhlebotomistID.1"]
        phleb_name = phleb.get('PhlebotomistName', f'Phlebotomist {phleb_id}')
        phleb_location = (phleb["PhlebotomistLatitude"], phleb["PhlebotomistLongitude"])
        
        print(f"\nROUTE FOR {phleb_name} (ID: {phleb_id}):")
        print("-"*50)
        
        # Get patients for this phlebotomist
        phleb_patients = updated_patients[updated_patients["AssignedPhlebID"] == phleb_id].copy()
        
        if phleb_patients.empty:
            print(f"  No patients assigned to {phleb_name}")
            continue
        
        # Start from phlebotomist location
        print(f"  1. START: Phlebotomist Base ({phleb_location[0]:.6f}, {phleb_location[1]:.6f})")
        
        # Create a complete list of all stops
        stops = []
        
        # Add phlebotomist as first stop
        current_location = phleb_location
        total_distance = 0
        
        # Add all patients based on trip order
        for idx, patient in phleb_patients.sort_values("TripOrderInDay").iterrows():
            patient_loc = (patient["PatientLatitude"], patient["PatientLongitude"])
            patient_time = patient["PreferredTime"].strftime('%H:%M') if pd.notna(patient["PreferredTime"]) else "Unknown"
            
            # Safely get patient ID
            if 'PatientID' in patient and pd.notna(patient['PatientID']):
                patient_id = patient['PatientID']
            elif 'PatientSysID' in patient and pd.notna(patient['PatientSysID']):
                patient_id = patient['PatientSysID']
            else:
                patient_id = idx if isinstance(idx, (int, str)) else str(idx)
            
            stops.append({
                'type': 'patient',
                'location': patient_loc,
                'id': patient_id,
                'time': patient_time,
                'idx': idx
            })
        
        # Add dropoffs after patients
        processed_dropoffs = set()
        
        for idx, patient in phleb_patients.sort_values("DropOffSequence").iterrows():
            if pd.notna(patient['DropOffSequence']) and pd.notna(patient['DropOffLabID']):
                lab_id = patient['DropOffLabID']
                
                # Only add each unique dropoff once
                if lab_id not in processed_dropoffs:
                    processed_dropoffs.add(lab_id)
                    
                    # Get dropoff info
                    dropoff_lat, dropoff_lon = None, None
                    
                    # Try to get coordinates from DropOffClinicLoc
                    if pd.notna(patient['DropOffClinicLoc']):
                        try:
                            if isinstance(patient['DropOffClinicLoc'], str):
                                dropoff_lat, dropoff_lon = map(float, patient['DropOffClinicLoc'].split(","))
                            elif isinstance(patient['DropOffClinicLoc'], (tuple, list)):
                                dropoff_lat, dropoff_lon = patient['DropOffClinicLoc']
                        except Exception as e:
                            print(f"Error parsing DropOffClinicLoc: {e}")
                    
                    # If not found, look up in dropoffs_df
                    if dropoff_lat is None or dropoff_lon is None:
                        matching_dropoffs = dropoffs_df[dropoffs_df['LabID'] == lab_id]
                        if not matching_dropoffs.empty:
                            dropoff_lat = matching_dropoffs.iloc[0]['Latitude']
                            dropoff_lon = matching_dropoffs.iloc[0]['Longitude']
                            print(f"Using coordinates from dropoffs.csv for {lab_id}: {dropoff_lat}, {dropoff_lon}")
                        else:
                            print(f"Warning: Could not find coordinates for dropoff {lab_id}")
                    
                    if dropoff_lat is not None and dropoff_lon is not None:
                        dropoff_loc = (dropoff_lat, dropoff_lon)
                        
                        # Find all patients that share this dropoff
                        patients_for_dropoff = []
                        for p_idx, p in phleb_patients.iterrows():
                            if pd.notna(p['DropOffLabID']) and p['DropOffLabID'] == lab_id:
                                # Safely get patient ID
                                if 'PatientID' in p and pd.notna(p['PatientID']):
                                    p_id = p['PatientID']
                                elif 'PatientSysID' in p and pd.notna(p['PatientSysID']):
                                    p_id = p['PatientSysID']
                                else:
                                    p_id = p_idx if isinstance(p_idx, (int, str)) else str(p_idx)
                                
                                patients_for_dropoff.append(p_id)
                        
                        # Get clinic name
                        clinic_name = patient.get('DropOffClinicName', 'Unknown')
                        if clinic_name == 'Unknown':
                            matching_dropoffs = dropoffs_df[dropoffs_df['LabID'] == lab_id]
                            if not matching_dropoffs.empty:
                                clinic_name = matching_dropoffs.iloc[0]['Clinic']
                        
                        stops.append({
                            'type': 'dropoff',
                            'location': dropoff_loc,
                            'id': lab_id,
                            'clinic': clinic_name,
                            'for_patients': ', '.join(map(str, patients_for_dropoff)),
                            'idx': idx,
                            'sequence': patient['DropOffSequence']
                        })
        
        # Sort stops - patients by trip order, then dropoffs
        # This ensures we visit all patients first, then do dropoffs
        stops.sort(key=lambda x: float('inf') if x['type'] == 'dropoff' else phleb_patients.at[x['idx'], 'TripOrderInDay'])
        
        # Now print the route
        for i, stop in enumerate(stops, start=2):  # Start at 2 (after phlebotomist base)
            # Calculate distance from previous location
            distance = calculate_distance(current_location, stop['location'], ors_client, use_ors=False)
            total_distance += distance
            
            if stop['type'] == 'patient':
                print(f"  {i}. PATIENT: {stop['id']} at ({stop['location'][0]:.6f}, {stop['location'][1]:.6f})")
                print(f"     Time: {stop['time']}, Distance from previous: {distance:.2f} miles")
            else:  # dropoff
                print(f"  {i}. DROPOFF: Lab {stop['id']} - {stop['clinic']} at ({stop['location'][0]:.6f}, {stop['location'][1]:.6f})")
                print(f"     For Patients: {stop['for_patients']}, Distance from previous: {distance:.2f} miles")
            
            current_location = stop['location']
        
        print(f"  TOTAL ROUTE DISTANCE: {total_distance:.2f} miles")
        
        # Print patient-dropoff relationships
        print("\n  Patient-Dropoff Summary:")
        dropoff_map = {}
        for idx, patient in phleb_patients.iterrows():
            if 'DropOffLabID' in phleb_patients.columns and pd.notna(patient['DropOffLabID']) and pd.notna(patient['DropOffSequence']):
                dropoff_id = patient['DropOffLabID']
                
                # Safely get patient ID
                if 'PatientID' in patient and pd.notna(patient['PatientID']):
                    patient_id = patient['PatientID']
                elif 'PatientSysID' in patient and pd.notna(patient['PatientSysID']):
                    patient_id = patient['PatientSysID']
                else:
                    patient_id = idx if isinstance(idx, (int, str)) else str(idx)
                
                if dropoff_id not in dropoff_map:
                    dropoff_map[dropoff_id] = []
                dropoff_map[dropoff_id].append(patient_id)
        
        if dropoff_map:
            for dropoff_id, patient_ids in dropoff_map.items():
                patients_str = ", ".join(str(pid) for pid in patient_ids)
                print(f"  - Dropoff {dropoff_id}: Specimens from Patients {patients_str}")
        else:
            print("  - No dropoffs assigned")
    
    print("\n" + "="*80)
    
    return updated_patients


def save_assignment_results(assignment_map, assigned_phlebs, assigned_patients, target_date, target_city, use_scheduled_time=True):
    """
    Save the assignment results to files.
    Args:
        assignment_map: Folium map object
        assigned_phlebs: DataFrame with assigned phlebotomists
        assigned_patients: DataFrame with assigned patients
        target_date: Date of assignments
        target_city: City of assignments
        use_scheduled_time: Whether scheduled time was used for routing
    Returns:
        Dict with paths to saved files (relative to 'myproject')
    """
    logger = logging.getLogger(__name__)

    # Define output directory
    output_dir = os.path.join("GeneratedFiles")
    os.makedirs(output_dir, exist_ok=True)

    logger.info("🗂️ Output directory checked/created")

    # Format date for filenames
    date_str = pd.to_datetime(target_date).strftime("%Y-%m-%d")
    city_str = target_city.replace(" ", "")
    routing_method = "scheduled" if use_scheduled_time else "optimized"
    base_filename = f"{city_str}{date_str}{routing_method}"

    # Define file paths (absolute)
    map_path_abs = os.path.join(output_dir, f"{base_filename}_map.html")
    phleb_path_abs = os.path.join(output_dir, f"{base_filename}_phlebs.csv")
    patients_path_abs = os.path.join(output_dir, f"{base_filename}_patients.csv")
    
    # Convert absolute paths to relative paths from 'myproject', ensuring single slashes
    def to_relative_path(abs_path):
        # return os.path.relpath(abs_path, settings.BASE_DIR).replace("\\", "/")
         return os.path.relpath(abs_path).replace("\\", "/")

    map_path_rel = to_relative_path(map_path_abs)
    phleb_path_rel = to_relative_path(phleb_path_abs)
    patients_path_rel = to_relative_path(patients_path_abs)

    logger.info(f"📝 Saving assignments for {city_str} on {date_str} using {routing_method} routing")

    # Save map
    assignment_map.save(map_path_abs)
    logger.info(f"🗺️ Assignment map saved to {map_path_rel}")

    # Save phlebotomist assignments
    try:
        if not isinstance(assigned_phlebs, pd.DataFrame):
            assigned_phlebs = pd.DataFrame(assigned_phlebs)

        if 'assigned_patients' in assigned_phlebs.columns:
              assigned_phlebs['assigned_patients'] = assigned_phlebs['assigned_patients'].apply(
                  lambda x: x if isinstance(x, list) else [x]
              )

        assigned_phlebs.to_csv(phleb_path_abs, index=False)
        logger.info(f"👨‍⚕️ Phlebotomist assignments saved to {phleb_path_rel} with {len(assigned_phlebs)} phlebotomists")

    except Exception as e:
        logger.error(f"❌ Error processing phlebotomist assignments: {e}")
        raise

    # Save patient assignments
    try:
        if not isinstance(assigned_patients, pd.DataFrame):
            assigned_patients = pd.DataFrame(assigned_patients)

        for col in assigned_patients.columns:
            assigned_patients[col] = assigned_patients[col].apply(
                lambda x: ','.join(map(str, x)) if isinstance(x, (list, pd.Series)) else str(x)
            )

        assigned_patients.to_csv(patients_path_abs, index=False)
        logger.info(f"🏥 Patient assignments saved to {patients_path_rel} with {len(assigned_patients)} patients")

    except Exception as e:
        logger.error(f"❌ Error processing patient assignments: {e}")
        raise

    logger.info(f"✅ Assignment files successfully generated for {city_str} on {date_str}")

    return {
        "map": map_path_rel,
        "phlebs": phleb_path_rel,
        "patients": patients_path_rel
    }
