import json
import folium

def create_assignment_map(assigned_phlebs, assigned_patients, target_date, target_city, 
                     api_key=None, return_distances=False, use_scheduled_time=True, ors_client=None):
    """
    Create a map visualization of phlebotomist assignments with proper ordering of patients and dropoffs.

    Args:
        assigned_phlebs: DataFrame with assigned phlebotomists
        assigned_patients: DataFrame with assigned patients
        target_date: Date to analyze
        target_city: City to analyze
        api_key: OpenRouteService API key (optional)
        return_distances: Whether to return route distances
        use_scheduled_time: Whether to use scheduled time for routing
        ors_client: Pre-initialized OpenRouteService client (optional)

    Returns:
        Map visualization and optionally a dictionary of route distances
    """
    import folium
    from folium.plugins import MarkerCluster
    import pandas as pd
    from geopy.distance import geodesic
    import time
    import json
    from collections import defaultdict

    # Debug the input data
    print("\n" + "="*50)
    print("INPUT DATA FOR MAP CREATION")
    print("="*50)
    print(f"Number of phlebotomists: {len(assigned_phlebs)}")
    print(f"Number of patients: {len(assigned_patients)}")
    print("Sample patient columns:", assigned_patients.columns.tolist())
    print("TripOrderInDay values:", assigned_patients['TripOrderInDay'].unique())
    if 'DropOffSequence' in assigned_patients.columns:
        seq_values = assigned_patients['DropOffSequence'].dropna().unique()
        print(f"DropOffSequence values: {seq_values}")
        print(f"Number of patients with dropoff sequences: {assigned_patients['DropOffSequence'].notna().sum()}")
    print("="*50)
    
    # Get dropoff locations data
    try:
        # Check if dropoffs is already defined
        dropoffs
    except NameError:
        # Load dropoffs data if not already loaded
        try:
            dropoffs = pd.read_csv("All_Dropoffs.csv")
            print("Loaded dropoffs data successfully")
        except Exception as e:
            print(f"Error loading dropoffs data: {e}")
            # Create an empty DataFrame as fallback
            dropoffs = pd.DataFrame(columns=['LabID', 'Address'])

    # If API key is provided but client isn't, initialize it
    if api_key and not ors_client:
        from redis_utils import initialize_ors_client
        ors_client = initialize_ors_client(api_key)
        if ors_client:
            print("ORS Client initialized for creating map")
        else:
            print("ORS Client initialization FAILED for creating map")

    # Create a map centered at the mean coordinates of patients
    mean_lat = assigned_patients['PatientLatitude'].mean()
    mean_lon = assigned_patients['PatientLongitude'].mean()
    m = folium.Map(location=[mean_lat, mean_lon], zoom_start=12)
    
    # Save the use_scheduled_time parameter in the map for legend reference
    m.get_root().script.add_child(folium.Element(f"var use_scheduled_time = {str(use_scheduled_time).lower()};"))

    # Create marker clusters for patients, phlebotomists, and dropoff locations
    patient_cluster = MarkerCluster(name="Patients").add_to(m)
    phleb_cluster = MarkerCluster(name="Phlebotomists").add_to(m)
    dropoff_cluster = MarkerCluster(name="Dropoff Locations").add_to(m)

    # Create color map for phlebotomists
    phleb_colors = {}
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightblue', 
              'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'pink', 'lightgreen']

    for i, phleb_id in enumerate(assigned_patients['AssignedPhlebID'].unique()):
        phleb_colors[phleb_id] = colors[i % len(colors)]

    # Store route information by phlebotomist
    phleb_routes = {}
    
    # Dictionary to store trip details for each phlebotomist
    trip_details = {}

    # Process dropoff information before building routes
    dropoff_map = {}  # Maps patient index to dropoff info
    
    for idx, patient in assigned_patients.iterrows():
        if pd.notna(patient.get('DropOffClinicLoc')) and patient['DropOffClinicLoc'] is not None:
            # Parse the DropOffClinicLoc which could be in various formats
            try:
                if isinstance(patient['DropOffClinicLoc'], str):
                    dropoff_lat, dropoff_lon = map(float, patient['DropOffClinicLoc'].split(","))
                elif isinstance(patient['DropOffClinicLoc'], (tuple, list)):
                    dropoff_lat, dropoff_lon = patient['DropOffClinicLoc']
                else:
                    continue
                
                # Store in dropoff map
                dropoff_map[idx] = {
                    'location': (dropoff_lat, dropoff_lon),
                    'lab_id': patient.get('DropOffLabID', 'Unknown'),
                    'clinic_name': patient.get('DropOffClinicName', 'Unknown'),
                    'sequence': patient.get('DropOffSequence', float('inf'))  # Use infinity if no sequence
                }
            except (ValueError, TypeError) as e:
                print(f"Warning: Error parsing dropoff location for patient {idx}: {e}")

    # Helper function to create consistent popups
    def create_popup(title, content_lines, width=250, height=150):
        """Creates a consistent popup with title and content lines"""
        
        # Start with popup title in bold
        html = f"""
        <div style="font-family: Arial, sans-serif; margin: 0; padding: 0;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; border-bottom: 1px solid #e0e0e0; padding-bottom: 5px;">
                {title}
            </div>
            <div style="font-size: 13px;">
        """
        
        # Add each content line
        for line in content_lines:
            if line[0] and line[1]:  # Both label and value exist
                html += f"""
                <div style="margin-bottom: 4px;">
                    <span style="font-weight: 500;">{line[0]}:</span> {line[1]}
                </div>
                """
        
        # Close the HTML
        html += """
            </div>
        </div>
        """
        
        # Create the popup with iframe
        iframe = folium.IFrame(html=html, width=width, height=height)
        return folium.Popup(iframe, max_width=300)

    # Add phlebotomists to the map
    for _, phleb in assigned_phlebs.iterrows():
        phleb_id = phleb['PhlebotomistID.1']
        phleb_name = phleb.get('Name', f'Phlebotomist {phleb_id}')
        if 'PhlebotomistName' in phleb:
            phleb_name = phleb['PhlebotomistName']
        phleb_lat = phleb['PhlebotomistLatitude']
        phleb_lon = phleb['PhlebotomistLongitude']
        phleb_color = phleb_colors.get(phleb_id, 'gray')

        # Create popup content
        popup_content = [
            ["Name", phleb_name],
            ["ID", phleb_id],
            ["City", phleb.get("City", "Unknown")]
        ]
        
        # Add phlebotomist marker with consistent popup
        folium.Marker(
            [phleb_lat, phleb_lon],
            popup=create_popup("Phlebotomist", popup_content),
            icon=folium.Icon(color=phleb_color, icon='home', prefix='fa')
        ).add_to(phleb_cluster)

        # Initialize route feature group for this phlebotomist
        route_feature_group = folium.FeatureGroup(name=f"Route: {phleb_name}").add_to(m)

        # Get patients assigned to this phlebotomist
        phleb_patients = assigned_patients[assigned_patients['AssignedPhlebID'] == phleb_id].copy()
        
        # Initialize route info
        phleb_routes[phleb_id] = {
            "color": phleb_color,
            "distance": 0,
            "patients": len(phleb_patients),
            "workload": phleb_patients['WorkloadPoints'].sum() if 'WorkloadPoints' in phleb_patients.columns else len(phleb_patients),
            "name": phleb_name
        }
        
        # Initialize trip details for this phlebotomist
        trip_details[phleb_id] = {
            "name": phleb_name,
            "color": phleb_color,
            "stops": [{
                "type": "start",
                "name": f"{phleb_name} Starting Point",
                "address": phleb.get("Address", "Home Base"),
                "lat": phleb_lat,
                "lon": phleb_lon,
                "order": 0,
                "distance": 0,
                "cumulative_distance": 0,
                "time": "Start"
            }]
        }

        # Skip if no patients assigned
        if phleb_patients.empty:
            continue

        # Create a list of all stops (patients and dropoffs) based on the optimization results
        all_stops = []
        
        # Start with phlebotomist home location
        all_stops.append({
            'type': 'start',
            'location': (phleb_lat, phleb_lon),
            'label': f"Start: {phleb_name}",
            'order': 0
        })
        
        # Add patients based on their TripOrderInDay
        for idx, patient in phleb_patients.sort_values('TripOrderInDay').iterrows():
            patient_id = patient.get('UserReqID', idx)
            patient_order = patient['TripOrderInDay']
            patient_location = (patient['PatientLatitude'], patient['PatientLongitude'])
            scheduled_time = patient['ScheduledDtm'].strftime('%H:%M') if pd.notna(patient['ScheduledDtm']) else 'Unknown'
            
            # Add patient to stops
            all_stops.append({
                'type': 'patient',
                'location': patient_location,
                'label': f"Patient {patient_id}",
                'order': patient_order,
                'patient_idx': idx,
                'patient_id': patient_id,
                'time': scheduled_time,
                'address': patient.get('PatientAddress', 'Unknown Address')
            })
            
            # Add to trip details
            trip_details[phleb_id]["stops"].append({
                "type": "patient",
                "name": f"Patient {patient_id}",
                "address": patient.get("PatientAddress", "Patient Address"),
                "lat": patient_location[0],
                "lon": patient_location[1],
                "order": patient_order,
                "distance": 0,  # Will be updated later
                "cumulative_distance": 0,  # Will be updated later
                "time": scheduled_time
            })
        
        # Now add dropoffs based on DropOffSequence if available
        if 'DropOffSequence' in assigned_patients.columns:
            # Group patients by dropoff sequence
            dropoff_groups = defaultdict(list)
            for idx, patient in phleb_patients.iterrows():
                if pd.notna(patient.get('DropOffSequence')):
                    dropoff_groups[patient['DropOffSequence']].append(idx)
            
            # Add dropoffs in sequence order
            for seq in sorted(dropoff_groups.keys()):
                # Get the first patient in this group to get the dropoff info
                patient_idx = dropoff_groups[seq][0]
                if patient_idx in dropoff_map:
                    dropoff_info = dropoff_map[patient_idx]
                    
                    # Get the patient IDs in this group
                    patient_ids = [phleb_patients.loc[idx].get('PatientID', idx) for idx in dropoff_groups[seq]]
                    patients_str = ", ".join(str(pid) for pid in patient_ids)
                    
                    # Add dropoff to stops
                    all_stops.append({
                        'type': 'dropoff',
                        'location': dropoff_info['location'],
                        'label': f"Dropoff: {dropoff_info['clinic_name']}",
                        'order': float(seq) + 0.5,  # Place after patient but keep sequence order
                        'patients': patients_str,
                        'lab_id': dropoff_info['lab_id'],
                        'clinic_name': dropoff_info['clinic_name']
                    })
                    
                    # Get address from dropoffs DataFrame if available
                    dropoff_address = "Unknown Address"
                    if dropoff_info['lab_id'] != 'Unknown':
                        matching_dropoffs = dropoffs[dropoffs['LabID'] == dropoff_info['lab_id']]
                        if not matching_dropoffs.empty:
                            dropoff_address = matching_dropoffs.iloc[0]['Address']
                    
                    # Add to trip details
                    trip_details[phleb_id]["stops"].append({
                        "type": "dropoff",
                        "name": f"Dropoff: {dropoff_info['clinic_name']}",
                        "address": dropoff_address,
                        "lat": dropoff_info['location'][0],
                        "lon": dropoff_info['location'][1],
                        "order": float(seq) + 0.5,
                        "distance": 0,  # Will be updated later
                        "cumulative_distance": 0,  # Will be updated later
                        "for_patients": patients_str,
                        "lab_id": dropoff_info['lab_id'],
                        "time": ""
                    })
        
        # Sort all stops by order
        all_stops.sort(key=lambda x: x['order'])
        
        # Calculate routes between stops
        total_distance = 0
        current_location = (phleb_lat, phleb_lon)
        
        for i in range(1, len(all_stops)):
            start = all_stops[i-1]['location']
            end = all_stops[i]['location']
            start_label = all_stops[i-1]['label']
            end_label = all_stops[i]['label']
            
            # Calculate distance using ORS if available, otherwise use geodesic
            if ors_client:
                try:
                    # Format for ORS API: [lon, lat]
                    coords_for_ors = [[start[1], start[0]], [end[1], end[0]]]
                    
                    # Get route from ORS
                    route = ors_client.directions(
                        coordinates=coords_for_ors,
                        profile='driving-car',
                        format='geojson',
                        units='mi',
                        instructions=False
                    )
                    
                    # Extract route geometry and distance
                    if 'features' in route and len(route['features']) > 0:
                        route_geom = route['features'][0]['geometry']['coordinates']
                        
                        # Extract distance
                        segment_distance = None
                        if 'properties' in route['features'][0]:
                            props = route['features'][0]['properties']
                            
                            if 'segments' in props and len(props['segments']) > 0:
                                segment_distance = props['segments'][0].get('distance', 0)
                            elif 'summary' in props:
                                segment_distance = props['summary'].get('distance', 0)
                            elif 'distance' in props:
                                segment_distance = props['distance']
                        
                        if segment_distance is None:
                            if 'summary' in route and 'distance' in route['summary']:
                                segment_distance = route['summary']['distance']
                            else:
                                # Fall back to geodesic as last resort
                                segment_distance = geodesic(start, end).miles
                        
                        # Convert coordinates for Folium
                        route_points = [[coord[1], coord[0]] for coord in route_geom]
                        
                        # Add route line to map
                        folium.PolyLine(
                            route_points,
                            color=phleb_color,
                            weight=3,
                            opacity=0.8,
                            tooltip=f'{start_label} to {end_label}: {segment_distance:.2f} miles'
                        ).add_to(route_feature_group)
                        
                        # Add sequence label
                        if len(route_points) > 0:
                            midpoint_idx = len(route_points) // 2
                            midpoint = route_points[midpoint_idx]
                            add_sequence_label(route_feature_group, midpoint, i, phleb_color)
                    else:
                        raise Exception("No features found in route response")
                    
                    # Rate limiting
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"Error calculating ORS route: {e}")
                    
                    # Fallback to geodesic
                    segment_distance = geodesic(start, end).miles
                    
                    # Add simple line
                    folium.PolyLine(
                        [start, end],
                        color=phleb_color,
                        weight=3,
                        opacity=0.5,
                        tooltip=f'{start_label} to {end_label}: {segment_distance:.2f} miles (geodesic)'
                    ).add_to(route_feature_group)
                    
                    # Calculate midpoint for sequence label
                    midpoint = [(start[0] + end[0])/2, (start[1] + end[1])/2]
                    # Add sequence label
                    add_sequence_label(route_feature_group, midpoint, i, phleb_color)
            else:
                # Use geodesic distance
                segment_distance = geodesic(start, end).miles
                
                # Add line to map
                folium.PolyLine(
                    [start, end],
                    color=phleb_color,
                    weight=3, 
                    opacity=0.5,
                    tooltip=f'{start_label} to {end_label}: {segment_distance:.2f} miles (geodesic)'
                ).add_to(route_feature_group)
                
                # Calculate midpoint for sequence label
                midpoint = [(start[0] + end[0])/2, (start[1] + end[1])/2]
                # Add sequence label
                add_sequence_label(route_feature_group, midpoint, i, phleb_color)
            
            # Update distances in trip details
            if i < len(trip_details[phleb_id]['stops']):
                trip_details[phleb_id]['stops'][i]['distance'] = segment_distance
            
            # Add to total distance
            total_distance += segment_distance
            current_location = end
        
        # Store total distance
        phleb_routes[phleb_id]["distance"] = total_distance
        
        # Calculate cumulative distances for trip details
        cumulative_distance = 0
        for i in range(len(trip_details[phleb_id]['stops'])):
            if i > 0:
                cumulative_distance += trip_details[phleb_id]['stops'][i]['distance']
            trip_details[phleb_id]['stops'][i]['cumulative_distance'] = cumulative_distance

    # Add patient markers
    for idx, patient in assigned_patients.iterrows():
        patient_id = patient.get('UserReqID', idx)
        phleb_id = patient['AssignedPhlebID']
        trip_order = patient['TripOrderInDay']
        patient_lat = patient['PatientLatitude']
        patient_lon = patient['PatientLongitude']
        workload = patient.get('WorkloadPoints', 'N/A')
        patient_name = patient.get("PatientFirstName", '') + patient.get("PatientLastName", '')
        
        # Get color from assigned phlebotomist
        patient_color = phleb_colors.get(phleb_id, 'gray')
        
        # Format scheduled time
        scheduled_time = patient['ScheduledDtm'].strftime('%H:%M') if 'ScheduledDtm' in patient and pd.notna(patient['ScheduledDtm']) else 'Unknown'
        
        # Create popup content
        popup_content = [
            ["ID", patient_id],
            ["Name", patient_name],
            ["Phlebotomist", phleb_id],
            ["Order", trip_order],
            ["Time", scheduled_time],
            ["Workload", workload]
        ]
        
        # Add patient marker with consistent popup
        folium.Marker(
            [patient_lat, patient_lon],
            popup=create_popup("Patient", popup_content),
            icon=folium.Icon(color=patient_color, icon='user', prefix='fa')
        ).add_to(patient_cluster)
    
    # Add dropoff markers
    for idx, info in dropoff_map.items():
        if idx in assigned_patients.index:
            patient = assigned_patients.loc[idx]
            phleb_id = patient['AssignedPhlebID']
            patient_id = patient.get('PatientID', idx)
            
            # Get color from assigned phlebotomist
            patient_color = phleb_colors.get(phleb_id, 'gray')
            
            # Get dropoff info
            dropoff_lat, dropoff_lon = info['location']
            dropoff_lab_id = info['lab_id'] 
            dropoff_clinic_name = info['clinic_name']
            
            # Get address from dropoffs DataFrame if available
            dropoff_address = "Unknown Address"
            if dropoff_lab_id != 'Unknown':
                matching_dropoffs = dropoffs[dropoffs['LabID'] == dropoff_lab_id]
                if not matching_dropoffs.empty:
                    dropoff_address = matching_dropoffs.iloc[0]['Address']
            
            # Create popup content
            popup_content = [
                ["Lab ID", dropoff_lab_id],
                ["Clinic", dropoff_clinic_name],
                ["Address", dropoff_address],
                ["For Patient", patient_id],
                ["Sequence", info['sequence'] if pd.notna(info['sequence']) else 'Unknown'],
                ["Phlebotomist", phleb_id]
            ]
            
            # Add dropoff marker with consistent popup
            folium.Marker(
                [dropoff_lat, dropoff_lon],
                popup=create_popup("Dropoff Location", popup_content),
                icon=folium.Icon(color=patient_color, icon='flask', prefix='fa')
            ).add_to(dropoff_cluster)
    
    # Add layer control and trip panel
    folium.LayerControl().add_to(m)
    create_trip_panel(m, trip_details)
    create_assignment_legend(m, phleb_routes, target_date, target_city)
    
    # Print route summary
    print("\n" + "="*50)
    print("ROUTE SUMMARY")
    print("="*50)
    for phleb_id, route in phleb_routes.items():
        print(f"Phlebotomist {route['name']} (ID: {phleb_id}):")
        print(f"  - Total distance: {route['distance']:.2f} miles")
        print(f"  - Patients: {route['patients']}")
        print(f"  - Workload: {route['workload']:.1f}")
        print("-"*30)
    print("="*50)
    
    if return_distances:
        return m, {phleb_id: route["distance"] for phleb_id, route in phleb_routes.items()}
    else:
        return m

def add_sequence_label(feature_group, midpoint, sequence_num, color):
    """Add a circular marker with sequence number at the given point"""
    # Create custom HTML for the circular label
    circle_html = f'''
        <div style="
            background-color: {color};
            color: white;
            border-radius: 50%;
            width: 24px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
            border: 2px solid white;
            box-shadow: 0 0 4px rgba(0,0,0,0.5);
        ">
            {sequence_num}
        </div>
    '''
    
    # Add the custom HTML marker
    folium.Marker(
        location=midpoint,
        icon=folium.DivIcon(
            html=circle_html,
            icon_size=(20, 20),
            icon_anchor=(10, 10)
        ),
        tooltip=f"Route #{sequence_num}"
    ).add_to(feature_group)
    
def create_assignment_legend(m, phleb_routes, target_date, target_city):
    """Create a legend for the assignment map with dropoff information"""
    total_distance = sum(route["distance"] for route in phleb_routes.values())
    total_patients = sum(route["patients"] for route in phleb_routes.values())
    
    # Determine if we're using scheduled time or optimized routing
    try:
        # Safely check if the attribute exists
        script_elem = m.get_root().script
        script_dict = getattr(script_elem, '_children', {})
        first_item = next(iter(script_dict.values()), {}) if script_dict else {}
        routing_mode = "Using scheduled appointment times" if first_item.get('use_scheduled_time', False) else "Using optimized routing (±2 hour window)"
    except (AttributeError, IndexError, KeyError):
        # Default value if we can't determine the routing mode
        routing_mode = "Using optimized routing (±2 hour window)"
    
    legend_html = f'''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 320px;
                border:1px solid #ddd; z-index:999; font-size:12px;
                background-color:white; padding: 10px;
                border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1);
                font-family: Arial, sans-serif;">
        <div style="margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #eee;">
            <div style="font-weight: bold; font-size: 14px; color: #202124; margin-bottom: 5px;">Assignment Summary</div>
            <div style="display: grid; grid-template-columns: auto 1fr; grid-gap: 5px;">
                <div>Date:</div><div style="font-weight: 500;">{target_date}</div>
                <div>City:</div><div style="font-weight: 500;">{target_city}</div>
                <div>Patients:</div><div style="font-weight: 500;">{total_patients}</div>
                <div>Phlebotomists:</div><div style="font-weight: 500;">{len(phleb_routes)}</div>
                <div>Total Distance:</div><div style="font-weight: 500;">{total_distance:.2f} miles</div>
                <div>Routing:</div><div style="font-weight: 500;">{routing_mode}</div>
            </div>
        </div>
        
        <div style="margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #eee;">
            <div style="font-weight: bold; margin-bottom: 5px;">Phlebotomist Details</div>
    '''
    
    # Add details for each phlebotomist
    for phleb_id, route in sorted(phleb_routes.items()):
        phleb_name = route.get('name', f'Phleb {phleb_id}')
        legend_html += f'''
        <div style="margin: 5px 0; display: flex; align-items: center;">
            <div style="width: 16px; height: 12px; background-color:{route['color']}; margin-right: 5px; border-radius: 2px;"></div>
            <div style="flex-grow: 1;">
                <span style="font-weight: 500;">{phleb_name}</span>
                <div style="font-size: 11px; color: #5f6368;">
                    {route['patients']} patients, {route['workload']:.1f} workload, {route['distance']:.2f} miles
                </div>
            </div>
        </div>
        '''
    
    legend_html += '''
        </div>
        
        <div style="margin-bottom: 10px;">
            <div style="font-weight: bold; margin-bottom: 5px;">Map Legend</div>
            <div style="display: grid; grid-template-columns: 20px 1fr; grid-gap: 5px; align-items: center;">
                <div style="text-align: center;"><i class="fa fa-home"></i></div>
                <div>Phlebotomist Starting Point</div>
                
                <div style="text-align: center;"><i class="fa fa-user"></i></div>
                <div>Patient Location</div>
                
                <div style="text-align: center;"><i class="fa fa-flask"></i></div>
                <div>Specimen Dropoff Location</div>
                
                <div style="text-align: center;"><div style="height: 2px; background-color: #3388ff; width: 100%;"></div></div>
                <div>Travel Routes</div>
                
                <div style="text-align: center;"><div style="width: 16px; height: 16px; background-color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 3px rgba(0,0,0,0.3);"><span style="font-size: 10px; font-weight: bold;">1</span></div></div>
                <div>Sequence Number</div>
            </div>
        </div>
        
        <div style="font-size: 11px; color: #5f6368; text-align: center; margin-top: 5px;">
            Toggle layers using the control panel. View trip details in the right panel.
        </div>
    </div>
    '''
    
    m.get_root().html.add_child(folium.Element(legend_html))

def create_trip_panel(m, trip_details):
    """Create a Google Maps-like trip panel showing the sequence of stops"""
    
    # Create the trip panel HTML
    trip_panel_html = '''
    <div id="trip-panel" style="
        position: fixed; 
        top: 75px; 
        right: 10px; 
        width: 350px;
        max-height: 80vh;
        overflow-y: auto;
        background-color: white;
        border-radius: 8px;
        box-shadow: 0 0 10px rgba(0,0,0,0.2);
        z-index: 1000;
        font-family: Arial, sans-serif;
        padding: 0;
        display: flex;
        flex-direction: column;
    ">
        <div style="padding: 15px; border-bottom: 1px solid #e0e0e0; background-color: #f8f9fa;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; font-size: 16px; color: #202124;">Trip Routes</h3>
                <select id="phleb-selector" style="padding: 6px; border-radius: 4px; border: 1px solid #ddd;">
                    <option value="">Select Phlebotomist</option>
    '''
    
    # Add phlebotomist options
    for phleb_id, details in trip_details.items():
        trip_panel_html += f'<option value="{phleb_id}">{details["name"]}</option>'
    
    trip_panel_html += '''
                </select>
            </div>
        </div>
        <div id="trip-details" style="padding: 10px; flex-grow: 1; overflow-y: auto;">
            <div style="text-align: center; color: #5f6368; margin-top: 50px;">
                Select a phlebotomist to view their trip details
            </div>
        </div>
    </div>
    '''
    
    # Create JS to handle phlebotomist selection and show trip details
    trip_panel_js = '''
    <script>
    document.getElementById('phleb-selector').addEventListener('change', function() {
        var phlebId = this.value;
        var tripDetails = document.getElementById('trip-details');
        
        if (!phlebId) {
            tripDetails.innerHTML = '<div style="text-align: center; color: #5f6368; margin-top: 50px;">Select a phlebotomist to view their trip details</div>';
            return;
        }
        
        // Get trip data
        var tripData = ''' + json.dumps(trip_details, default=pandas_serializer) + ''';
        var phleb = tripData[phlebId];
        
        if (!phleb) {
            tripDetails.innerHTML = '<div style="text-align: center; color: #5f6368;">No trip details available</div>';
            return;
        }
        
        // Sort stops by order
        var stops = phleb.stops.sort((a, b) => a.order - b.order);
        
        // Build trip details HTML
        var html = `
            <div style="border-bottom: 3px solid ${phleb.color}; padding-bottom: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0 0 5px 0; color: ${phleb.color};">${phleb.name}</h3>
                <div style="font-size: 13px; color: #5f6368;">
                    ${stops.length} stops | 
                    ${stops[stops.length-1].cumulative_distance.toFixed(2)} miles total
                </div>
            </div>
        `;
        
        // Add each stop
        stops.forEach((stop, index) => {
            // Define icon based on stop type
            let icon = 'home';
            if (stop.type === 'patient') icon = 'user';
            else if (stop.type === 'dropoff') icon = 'flask';
            
            // Get time or estimate
            let timeText = '';
            if (stop.time && stop.time !== 'Unknown' && stop.time !== '') {
                timeText = `<div style="font-size: 13px; font-weight: bold;">${stop.time}</div>`;
            }
            
            // Format additional info based on stop type
            let additionalInfo = '';
            if (stop.type === 'dropoff' && stop.for_patients) {
                additionalInfo = `<div style="font-size: 12px; color: #5f6368;">For patients: ${stop.for_patients}</div>`;
            }
            
            html += `
                <div style="display: flex; margin-bottom: ${index === stops.length - 1 ? '0' : '15px'};">
                    <!-- Left column with icon and connector line -->
                    <div style="width: 35px; display: flex; flex-direction: column; align-items: center;">
                        <div style="
                            width: 26px;
                            height: 26px;
                            background-color: ${phleb.color};
                            color: white;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        ">
                            <i class="fa fa-${icon}" aria-hidden="true" style="font-size: 12px;"></i>
                        </div>
                        ${index < stops.length - 1 ? `
                        <div style="
                            width: 2px;
                            flex-grow: 1;
                            background-color: #e0e0e0;
                            margin-top: 4px;
                        "></div>
                        ` : ''}
                    </div>
                    
                    <!-- Right column with stop details -->
                    <div style="flex-grow: 1; padding-left: 10px;">
                        <div style="font-weight: ${stop.type === 'patient' ? 'bold' : 'normal'}; font-size: 14px;">
                            ${stop.name}
                        </div>
                        <div style="font-size: 12px; color: #5f6368;">
                            ${stop.address}
                        </div>
                        ${timeText}
                        ${additionalInfo}
                        ${index > 0 ? `
                        <div style="font-size: 12px; color: #5f6368; margin-top: 2px;">
                            ${stop.distance.toFixed(2)} miles from previous stop
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        
        tripDetails.innerHTML = html;
    });
    </script>
    '''
    
    m.get_root().html.add_child(folium.Element(trip_panel_html + trip_panel_js))

def pandas_serializer(obj):
    """Helper function to serialize pandas objects for JSON"""
    import pandas as pd
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')