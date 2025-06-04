import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster, HeatMap
from sklearn.cluster import KMeans
from geopy.distance import geodesic
import os
import json
import requests
from collections import defaultdict

def main():
    # 1. Load and prepare data
    # 1. Load and prepare data
    try:
        # Load trips data
        trips_df = pd.read_csv("trips.csv")
        trips_df['ScheduledDtm'] = pd.to_datetime(trips_df['ScheduledDtm'])
        
        # Load phlebotomist locations
        phleb_df = pd.read_csv("unique_phleb_locations.csv")
        print("✅ Data loaded successfully.")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return
    
    # 2. Get phlebotomist selection
    phleb_ids = trips_df["PhlebotomistID.1"].unique()
    phleb_id = get_user_selection(
        prompt=f"Enter Phleb ID from available options {list(phleb_ids)}: ",
        options=list(map(str, phleb_ids)),
        error_msg=f"⚠ Invalid Phleb ID! Choose from {list(phleb_ids)}."
    )
    
    # 3. Filter data for selected phlebotomist
    phleb_data = trips_df[trips_df["PhlebotomistID.1"] == phleb_id]
    if phleb_data.empty:
        print(f"❌ No data found for Phlebotomist ID {phleb_id}")
        return

    # 4. Get date selection
    years = sorted(phleb_data['ScheduledDtm'].dt.year.unique())
    year = get_user_selection(
        prompt=f"Select a year from {years}: ",
        options=years,
        error_msg=f"⚠ Invalid year! Choose from {years}.",
        convert_type=int
    )
    
    year_data = phleb_data[phleb_data['ScheduledDtm'].dt.year == year]
    
    months = sorted(year_data['ScheduledDtm'].dt.month.unique())
    month = get_user_selection(
        prompt=f"Select a month from {months}: ",
        options=months,
        error_msg=f"⚠ Invalid month! Choose from {months}.",
        convert_type=int
    )
    
    month_data = year_data[year_data['ScheduledDtm'].dt.month == month]
    
    days = sorted(month_data['ScheduledDtm'].dt.day.unique())
    day = get_user_selection(
        prompt=f"Select a day from {days}: ",
        options=days,
        error_msg=f"⚠ Invalid day! Choose from {days}.",
        convert_type=int
    )

    # 5. Filter data for selected date
    selected_date = pd.Timestamp(year, month, day).date()
    trip_data = month_data[month_data['ScheduledDtm'].dt.date == selected_date]
    trip_data = trip_data.sort_values(by='ScheduledDtm')
    
    if trip_data.empty:
        print(f"❌ No trips found for {selected_date}")
        return
    
    print(f"📊 Found {len(trip_data)} trips for {selected_date}")

    # 6. Get API key for routing
    ors_api_key = load_api_key()
    
    # 7. Create enhanced journey map - passing the full trips_df
    create_enhanced_journey_map(trip_data, phleb_df, phleb_id, selected_date, ors_api_key,trips_df)  # Added trips_df here
    
    print(f"📊 Found {len(trip_data)} trips for {selected_date}")

    # 6. Get API key for routing
    ors_api_key = load_api_key()
    
    # 7. Create enhanced journey map

def get_user_selection(prompt, options, error_msg, convert_type=str):
    """Helper function to get valid user input"""
    while True:
        try:
            user_input = input(prompt).strip()
            if convert_type != str:
                user_input = convert_type(user_input)
            
            if user_input in options:
                return user_input
            else:
                print(error_msg)
        except ValueError:
            print("⚠ Invalid input! Please enter a valid value.")

def load_api_key():
    """Load OpenRouteService API key from file"""
    try:
        if os.path.exists("key.json"):
            with open("key.json", "r") as file:
                return json.load(file)["key"]
        else:
            print("⚠ API key file not found. Routes will be shown as straight lines.")
            return None
    except Exception as e:
        print(f"⚠ Failed to load ORS API key: {e}")
        return None

def get_route(start, end, api_key):
    """Get route between two points using OpenRouteService API"""
    if api_key is None:
        return []

    try:
        # ORS expects coordinates as [longitude, latitude]
        start_coords = [float(start[1]), float(start[0])]
        end_coords = [float(end[1]), float(end[0])]
        
        headers = {
            'Accept': 'application/json, application/geo+json',
            'Authorization': api_key,
            'Content-Type': 'application/json'
        }
        
        body = {"coordinates": [start_coords, end_coords]}
        
        response = requests.post(
            'https://api.openrouteservice.org/v2/directions/driving-car/geojson',
            json=body,
            headers=headers
        )
        
        if response.status_code == 200:
            route_data = response.json()
            if "features" in route_data and route_data["features"]:
                return route_data["features"][0]["geometry"]["coordinates"]
            else:
                print(f"⚠ No route found between {start} and {end}")
                return []
        else:
            print(f"⚠ API request failed: {response.status_code} {response.reason}")
            return []
    except Exception as e:
        print(f"⚠ Error fetching route: {e}")
        return []

def calculate_distance(route_coords=None, start=None, end=None):
    """Calculate distance between points"""
    if route_coords and len(route_coords) > 1:
        # Calculate distance along the route
        distance = 0
        for i in range(len(route_coords) - 1):
            point1 = (route_coords[i][1], route_coords[i][0])  # Convert [lon,lat] to [lat,lon]
            point2 = (route_coords[i+1][1], route_coords[i+1][0])
            distance += geodesic(point1, point2).kilometers
        return distance
    elif start and end:
        # Calculate straight-line distance
        return geodesic(start, end).kilometers
    return 0

def find_optimal_service_point(patient_locations):
    """
    Find the optimal service point using K-means clustering
    
    Args:
        patient_locations: List of (latitude, longitude) tuples for patient locations
        
    Returns:
        Tuple of (latitude, longitude) for the optimal service point
    """
    print("🔍 Finding optimal service point...")
    
    # Convert to numpy array for K-means
    locations_array = np.array(patient_locations)
    
    # Use K-means to find the optimal center
    # We use 1 cluster since we want one optimal point
    kmeans = KMeans(n_clusters=1, random_state=42, n_init=10)
    kmeans.fit(locations_array)
    
    # Get the optimal service point (center of the cluster)
    optimal_point = tuple(kmeans.cluster_centers_[0])
    
    print(f"✅ Optimal service point found: {optimal_point}")
    return optimal_point

def find_nearest_phlebotomist(optimal_point, phleb_df, current_phleb_id, selected_date, trips_df):
    """
    Find the nearest available phlebotomist to the optimal service point with enhanced selection logic
    
    Returns:
        Tuple of (phlebotomist_id, location, distance, has_conflicts, selection_report)
    """
    MAX_DISTANCE = 50  # Maximum acceptable distance in kilometers
    
    # Store detailed information about each phlebotomist
    phleb_analysis = []
    
    # Get the time slots needed for the new appointments
    needed_time_slots = set(pd.to_datetime(trips_df[
        trips_df['PhlebotomistID.1'] == current_phleb_id
    ]['ScheduledDtm']).dt.strftime('%H:%M').tolist())
    
    for _, row in phleb_df.iterrows():
        phleb_id = str(row['PhlebotomistID.1'])
        location = (row['PhlebotomistLatitude'], row['PhlebotomistLongitude'])
        
        # Calculate distance to optimal point
        distance = geodesic(optimal_point, location).kilometers
        
        # Initialize analysis dictionary for this phlebotomist
        analysis = {
            'phleb_id': phleb_id,
            'location': location,
            'distance': distance,
            'status': 'Considered',
            'reasons': [],
            'conflicts': [],
            'workload': 0
        }
        
        # Check distance constraint
        if distance > MAX_DISTANCE:
            analysis['status'] = 'Rejected'
            analysis['reasons'].append(f"Too far from optimal point ({distance:.2f} km > {MAX_DISTANCE} km)")
            phleb_analysis.append(analysis)
            continue
        
        # Get existing schedule for the selected date
        existing_schedule = trips_df[
            (trips_df['PhlebotomistID.1'] == phleb_id) & 
            (pd.to_datetime(trips_df['ScheduledDtm']).dt.date == selected_date)
        ]
        
        # Analyze schedule conflicts
        if not existing_schedule.empty:
            existing_times = set(existing_schedule['ScheduledDtm'].dt.strftime('%H:%M'))
            conflicting_times = needed_time_slots.intersection(existing_times)
            
            if conflicting_times:
                analysis['status'] = 'Conflicts'
                analysis['conflicts'] = sorted(list(conflicting_times))
                analysis['reasons'].append(f"Schedule conflicts at: {', '.join(analysis['conflicts'])}")
        
        # Calculate current workload
        analysis['workload'] = len(existing_schedule)
        if analysis['workload'] > 10:  # Example threshold
            analysis['reasons'].append(f"High workload ({analysis['workload']} appointments)")
        
        phleb_analysis.append(analysis)
    
    # Sort phlebotomists by priority: no conflicts first, then by distance
    phleb_analysis.sort(key=lambda x: (
        x['status'] != 'Considered',  # Considered first
        len(x['conflicts']),          # Fewer conflicts better
        x['distance']                 # Shorter distance better
    ))
    
    # Generate detailed selection report
    selection_report = "🔍 Phlebotomist Selection Analysis:\n"
    selection_report += f"Found {len(phleb_analysis)} phlebotomists within search radius\n\n"
    
    # Add selected phlebotomist details
    if phleb_analysis:
        selected = phleb_analysis[0]
        selection_report += f"Selected Phlebotomist (ID {selected['phleb_id']}):\n"
        selection_report += f"- Distance from optimal point: {selected['distance']:.2f} km\n"
        selection_report += f"- Current workload: {selected['workload']} appointments\n"
        if selected['conflicts']:
            selection_report += f"- Schedule conflicts: {', '.join(selected['conflicts'])}\n"
        
        # Add alternatives analysis
        selection_report += "\nAlternative Options:\n"
        for phleb in phleb_analysis[1:4]:  # Show next 3 alternatives
            selection_report += f"\nPhlebotomist ID {phleb['phleb_id']}:\n"
            selection_report += f"- Distance: {phleb['distance']:.2f} km\n"
            selection_report += f"- Status: {phleb['status']}\n"
            if phleb['reasons']:
                selection_report += f"- Issues: {'; '.join(phleb['reasons'])}\n"
        
        return (
            selected['phleb_id'],
            selected['location'],
            selected['distance'],
            bool(selected['conflicts']),
            selection_report
        )
    
    return None, None, None, None, "No suitable phlebotomists found within maximum distance"
    
def create_enhanced_journey_map(trip_data, phleb_df, current_phleb_id, selected_date, api_key, full_trips_df):
    """
    Create and save the enhanced journey map with detailed phlebotomist selection analysis
    """
    # Get phlebotomist's starting location
    current_phleb_location = (
        trip_data.iloc[0]['PhlebotomistLatitude'], 
        trip_data.iloc[0]['PhlebotomistLongitude']
    )
    
    # Extract patient locations
    patient_locations = [
        (row['PatientLatitude'], row['PatientLongitude']) 
        for _, row in trip_data.iterrows()
    ]
    
    # Find optimal service point
    optimal_point = find_optimal_service_point(patient_locations)
    
    # Find nearest phlebotomist with enhanced selection logic
    nearest_phleb_id, nearest_phleb_location, nearest_distance, has_conflicts, selection_report = find_nearest_phlebotomist(
        optimal_point, phleb_df, current_phleb_id, selected_date, full_trips_df
    )
    
    # Print detailed selection report
    print(f"\n{selection_report}")
    
    # Create map centered at the optimal service point
    m = folium.Map(location=optimal_point, zoom_start=12)
    
    # Add a heat map layer of patient density
    heat_data = [[lat, lon] for lat, lon in patient_locations]
    HeatMap(heat_data, radius=15, blur=10).add_to(m)
    
    # Draw service area circles around the optimal point
    for radius in [1, 3, 5]:
        folium.Circle(
            location=optimal_point,
            radius=radius * 1000,  # Convert km to meters
            color='purple',
            fill=True,
            fill_opacity=0.1,
            popup=f"{radius} km radius"
        ).add_to(m)
    
    # Mark the optimal service point
    folium.Marker(
        optimal_point,
        popup="Optimal Service Point",
        icon=folium.Icon(color="purple", icon="star", prefix='fa')
    ).add_to(m)
    
    # Add marker for current phlebotomist's starting point
    folium.Marker(
        current_phleb_location,
        popup=f"Current Phlebotomist {current_phleb_id} Starting Point",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(m)
    
    # Calculate and display original route
    original_route_distance = plot_original_route(m, current_phleb_location, patient_locations, api_key)
    
    # If a different phlebotomist is suggested, plot their suggested route
    suggested_route_distance = 0
    if nearest_phleb_id != current_phleb_id:
        # Mark the suggested phlebotomist
        folium.Marker(
            nearest_phleb_location,
            popup=f"Suggested Phlebotomist {nearest_phleb_id}",
            icon=folium.Icon(color="orange", icon="user", prefix='fa')
        ).add_to(m)
        
        # Plot suggested route
        suggested_route_distance = plot_suggested_route(m, nearest_phleb_location, 
                                                        patient_locations, api_key)
    
    # Create marker cluster for all phlebotomists in the area
    marker_cluster = MarkerCluster().add_to(m)
    for _, row in phleb_df.iterrows():
        phleb_id = str(row['PhlebotomistID.1'])
        if phleb_id not in [current_phleb_id, nearest_phleb_id]:
            folium.Marker(
                [row['PhlebotomistLatitude'], row['PhlebotomistLongitude']],
                popup=f"Phlebotomist {phleb_id}",
                icon=folium.Icon(color="gray", icon="user", prefix='fa')
            ).add_to(marker_cluster)
    
    # Add markers for each patient
    for i, (lat, lon) in enumerate(patient_locations):
        order_time = trip_data.iloc[i]['ScheduledDtm'].strftime('%H:%M')
        folium.Marker(
            [lat, lon],
            popup=f"Patient {i+1}: {order_time}",
            icon=folium.Icon(color="green", icon="plus", prefix='fa')
        ).add_to(m)
    
    # Add enhanced legend with route comparison and selection reason
    create_enhanced_legend(m, current_phleb_id, nearest_phleb_id, 
                            original_route_distance, suggested_route_distance,
                            patient_locations, selected_date, optimal_point,
                            has_conflicts, selection_report)
    
    # Save map to file
    output_file = f"enhanced_phleb_journey_{current_phleb_id}_{selected_date}_new_new.html"
    m.save(output_file)
    print(f"✅ Enhanced map saved as {output_file}")

def plot_original_route(m, start_location, patient_locations, api_key):
    """Plot the original route for the current phlebotomist"""
    print("🗺️ Plotting original route...")
    total_distance = 0
    
    # Plot route from phlebotomist to first patient
    if patient_locations:
        route_coords = get_route(start_location, patient_locations[0], api_key)
        
        # Calculate distance
        distance = 0
        if route_coords:
            distance = calculate_distance(route_coords=route_coords)
        else:
            distance = calculate_distance(start=start_location, end=patient_locations[0])
        
        total_distance += distance
        
        # Add route line to map
        folium.PolyLine(
            [(lat, lon) for lon, lat in route_coords] if route_coords else [start_location, patient_locations[0]],
            color="blue",
            weight=3,
            opacity=0.8,
            popup=f"Distance: {distance:.2f} km"
        ).add_to(m)
    
    # Plot routes between patients
    for i in range(len(patient_locations) - 1):
        start_point = patient_locations[i]
        end_point = patient_locations[i + 1]
        
        route_coords = get_route(start_point, end_point, api_key)
        
        # Calculate distance
        distance = 0
        if route_coords:
            distance = calculate_distance(route_coords=route_coords)
        else:
            distance = calculate_distance(start=start_point, end=end_point)
        
        total_distance += distance
        
        # Add route line to map
        folium.PolyLine(
            [(lat, lon) for lon, lat in route_coords] if route_coords else [start_point, end_point],
            color="blue",
            weight=3,
            opacity=0.8,
            popup=f"Distance: {distance:.2f} km"
        ).add_to(m)
    
    print(f"📏 Original route total distance: {total_distance:.2f} km")
    return total_distance

def plot_suggested_route(m, start_location, patient_locations, api_key):
    """Plot the suggested route for the alternative phlebotomist"""
    print("🗺️ Plotting suggested route...")
    total_distance = 0
    
    # Optimize the order of patient visits for the suggested route
    optimized_patient_order = optimize_patient_order(start_location, patient_locations)
    
    # Plot route from phlebotomist to first patient
    if optimized_patient_order:
        first_patient = optimized_patient_order[0]
        route_coords = get_route(start_location, first_patient, api_key)
        
        # Calculate distance
        distance = 0
        if route_coords:
            distance = calculate_distance(route_coords=route_coords)
        else:
            distance = calculate_distance(start=start_location, end=first_patient)
        
        total_distance += distance
        
        # Add route line to map
        folium.PolyLine(
            [(lat, lon) for lon, lat in route_coords] if route_coords else [start_location, first_patient],
            color="orange",
            weight=3,
            opacity=0.8,
            popup=f"Distance: {distance:.2f} km",
            dash_array="5, 10"
        ).add_to(m)
    
    # Plot routes between patients
    for i in range(len(optimized_patient_order) - 1):
        start_point = optimized_patient_order[i]
        end_point = optimized_patient_order[i + 1]
        
        route_coords = get_route(start_point, end_point, api_key)
        
        # Calculate distance
        distance = 0
        if route_coords:
            distance = calculate_distance(route_coords=route_coords)
        else:
            distance = calculate_distance(start=start_point, end=end_point)
        
        total_distance += distance
        
        # Add route line to map
        folium.PolyLine(
            [(lat, lon) for lon, lat in route_coords] if route_coords else [start_point, end_point],
            color="orange",
            weight=3,
            opacity=0.8,
            popup=f"Distance: {distance:.2f} km",
            dash_array="5, 10"
        ).add_to(m)
    
    print(f"📏 Suggested route total distance: {total_distance:.2f} km")
    return total_distance

def optimize_patient_order(start_location, patient_locations):
    """
    Implements a simple greedy algorithm to optimize the order of patient visits
    Always selects the nearest unvisited patient
    """
    remaining = patient_locations.copy()
    current_location = start_location
    optimized_order = []
    
    while remaining:
        # Find nearest patient to current location
        nearest_idx = -1
        min_distance = float('inf')
        
        for i, patient in enumerate(remaining):
            dist = geodesic(current_location, patient).kilometers
            if dist < min_distance:
                min_distance = dist
                nearest_idx = i
        
        # Add the nearest patient to the optimized order
        if nearest_idx >= 0:
            nearest_patient = remaining.pop(nearest_idx)
            optimized_order.append(nearest_patient)
            current_location = nearest_patient
    
    return optimized_order

def create_enhanced_legend(m, current_phleb_id, nearest_phleb_id, 
                         original_distance, suggested_distance,
                         patient_locations, selected_date, optimal_point,
                         has_conflicts, selection_report):
    """Create an enhanced legend with route comparison and scheduling information"""
    
    distance_diff = suggested_distance - original_distance
    percent_diff = (distance_diff / original_distance * 100) if original_distance > 0 else 0
    
    if nearest_phleb_id == current_phleb_id:
        route_comparison = "Current phlebotomist is optimal for this service area"
    elif distance_diff < 0:
        route_comparison = f"Suggested route is {abs(distance_diff):.2f} km shorter ({abs(percent_diff):.1f}% reduction)"
    else:
        route_comparison = f"Suggested route is {distance_diff:.2f} km longer ({percent_diff:.1f}% increase)"
    
    # Add scheduling conflict warning if applicable
    conflict_warning = ""
    if has_conflicts:
        conflict_warning = f"""
        <div style="color: red; margin-top: 5px;">
            ⚠️ Warning: Suggested phlebotomist has existing draws scheduled for {selected_date}
        </div>
        """
        
        
    selection_analysis_html = f'''
    <div style="margin-top: 10px;">
        <b>Selection Analysis</b><br>
        <div style="max-height: 150px; overflow-y: auto; margin-top: 5px;">
            {selection_report.replace('\n', '<br>')}
        </div>
    </div>
    '''
    legend_html = f'''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 300px; 
                border:2px solid grey; z-index:9999; font-size:12px;
                background-color:white; padding: 10px;
                border-radius: 5px;">
        <b style="font-size:14px;">Enhanced Journey Analysis</b><br>
        <hr>
        <b>Optimal Service Point:</b> {optimal_point[0]:.5f}, {optimal_point[1]:.5f}<br>
        <b>Date:</b> {selected_date}<br>
        <b>Patients Visited:</b> {len(patient_locations)}<br>
        <hr>
        <b style="color:red;">Current Phlebotomist (ID {current_phleb_id})</b><br>
        <i class="fa fa-minus" style="color:blue"></i> Current Route: {original_distance:.2f} km<br>
        <br>
        
        {f"""<b style="color:orange;">Suggested Phlebotomist (ID {nearest_phleb_id})</b><br>
        <i class="fa fa-minus" style="color:orange"></i> Suggested Route: {suggested_distance:.2f} km<br>
        <b>Route Comparison:</b> {route_comparison}<br>
        {conflict_warning}""" if nearest_phleb_id != current_phleb_id else ""}
        <hr>
        <b>Map Legend</b><br>
        <i class="fa fa-star" style="color:purple"></i> Optimal Service Point<br>
        <i class="fa fa-circle" style="color:purple;opacity:0.5;"></i> Service Area Radius<br>
        <i class="fa fa-home" style="color:red"></i> Current Phlebotomist Start<br>
        <i class="fa fa-plus" style="color:green"></i> Patient Locations<br>
        <i class="fa fa-user" style="color:gray"></i> Other Phlebotomists<br>
        {f'<i class="fa fa-user" style="color:orange"></i> Suggested Phlebotomist<br>' if nearest_phleb_id != current_phleb_id else ""}
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

if __name__ == "__main__":
    main()