import os
import json
import requests
import folium
from folium.plugins import LocateControl
from geopy.distance import geodesic
from datetime import datetime
import googlemaps
import os
import time
from dotenv import load_dotenv
import openrouteservice
load_dotenv()
MAPSAPI = os.getenv("MAP")
ORSKEY = os.getenv("KEY")
gmaps = googlemaps.Client(key=MAPSAPI)

GEOJSON_FILE = "routes.geojson"
TRIAL_MAPS_DIR = "trial_maps"
os.makedirs(TRIAL_MAPS_DIR, exist_ok=True)
ors_client = openrouteservice.Client(key=ORSKEY)

def load_geojson():
    """Load existing GeoJSON data or initialize a new structure."""
    if os.path.exists(GEOJSON_FILE):
        try:
            with open(GEOJSON_FILE, "r") as file:
                data = json.load(file)
                if "features" not in data:
                    return {"type": "FeatureCollection", "features": []}
                return data
        except json.JSONDecodeError:
            print("⚠ Invalid JSON detected. Resetting to default structure.")
    return {"type": "FeatureCollection", "features": []}

def save_geojson(data):
    """Save GeoJSON data to file."""
    with open(GEOJSON_FILE, "w") as file:
        json.dump(data, file, indent=4)
        
def generate_route_id(start, end, use_scheduled_time=True):
    """Generate a unique identifier for a route between two points."""
    # Sort coordinates to ensure consistency regardless of direction
    coords = sorted([start, end])
    
    # Base route ID from coordinates
    base_id = f"{coords[0][0]:.5f}_{coords[0][1]:.5f}_{coords[1][0]:.5f}_{coords[1][1]:.5f}"
    
    # Add suffix based on routing preference
    suffix = "-st" if use_scheduled_time else "-px"
    
    return base_id + suffix

def find_route_in_geojson(route_id, geojson_data):
    """Check if the route already exists in the GeoJSON file by route_id."""
    for feature in geojson_data["features"]:
        if feature["properties"]["route_id"] == route_id:
            return feature["geometry"]["coordinates"]
    
    return None

def get_route(start, end, api_key, use_scheduled_time=True):
    """Get route between two points, checking GeoJSON first before using ORS API."""
    import json
    import requests
    
    geojson_data = load_geojson()
    
    # Generate route_id
    route_id = generate_route_id(start, end, use_scheduled_time)
    
    # Check if route exists in GeoJSON
    existing_route = find_route_in_geojson(route_id, geojson_data)
    if existing_route:
        print(f"✅ Route found in local GeoJSON: {route_id}")
        return existing_route

    # If route not found, fetch from OpenRouteService
    print(f"🔍 Route not found in GeoJSON. Fetching from OpenRouteService...")

    if api_key is None:
        print("⚠ API key is missing!")
        return []

    try:
        start_coords = [float(start[1]), float(start[0])]
        end_coords = [float(end[1]), float(end[0])]

        # Step 1: Get Distance using ORS Distance Matrix API
        matrix_url = "https://api.openrouteservice.org/v2/matrix/driving-car"
        matrix_body = {
            "locations": [start_coords, end_coords],
            "metrics": ["distance"],  # Requesting only distance
            "units": "m"
        }
        
        matrix_headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }

        matrix_response = requests.post(matrix_url, json=matrix_body, headers=matrix_headers)

        if matrix_response.status_code != 200:
            print(f"⚠ Distance Matrix API request failed: {matrix_response.status_code} {matrix_response.reason}")
            print(f"Response content: {matrix_response.text[:500]}...")
            return []

        matrix_data = matrix_response.json()
        
        # Debug matrix response if needed
        # print(f"Matrix response: {json.dumps(matrix_data, indent=2)}")
        
        # More robust handling of distance extraction
        route_distance_m = 0
        if "distances" in matrix_data and len(matrix_data["distances"]) > 0:
            route_distance_m = matrix_data["distances"][0][1]  # Distance in meters
        else:
            print(f"⚠ Could not find distances in matrix response: {json.dumps(matrix_data, indent=2)[:300]}...")
            # Try alternative ways to extract distance
            if "durations" in matrix_data and len(matrix_data["durations"]) > 0:
                print("Using estimated distance based on durations")
                # Estimate distance based on duration (assuming average speed of 50 km/h)
                route_distance_m = matrix_data["durations"][0][1] * (50 * 1000 / 3600)  # meters
            else:
                print("⚠ No distance information available. Using fallback straight-line distance.")
                from geopy.distance import geodesic
                route_distance_m = geodesic(
                    (start[0], start[1]), 
                    (end[0], end[1])
                ).meters
        
        route_distance_miles = route_distance_m * 0.000621371  # Convert meters to miles

        # Step 2: Get Route using ORS Directions API
        directions_url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        directions_body = {"coordinates": [start_coords, end_coords]}

        directions_headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }

        response = requests.post(directions_url, json=directions_body, headers=directions_headers)

        if response.status_code == 200:
            route_data = response.json()
            
            # Debug directions response if needed
            # print(f"Directions response: {json.dumps(route_data, indent=2)[:500]}...")
            
            # More robust handling of route extraction
            if "features" in route_data and route_data["features"]:
                feature = route_data["features"][0]
                
                if "geometry" in feature and "coordinates" in feature["geometry"]:
                    route_coords = feature["geometry"]["coordinates"]
                    
                    # Check if coordinates are valid
                    if not route_coords or len(route_coords) < 2:
                        print(f"⚠ Invalid or empty route coordinates: {route_coords}")
                        # Fall back to straight line coordinates
                        route_coords = [start_coords, end_coords]
                    
                    # Store new route in GeoJSON with distance
                    new_feature = {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": route_coords},
                        "properties": {
                            "route_id": route_id,
                            "start": start,
                            "end": end,
                            "distance_miles": round(route_distance_miles, 2)  # Store rounded distance
                        }
                    }
                    geojson_data["features"].append(new_feature)
                    save_geojson(geojson_data)
                    
                    print(f"✅ Route successfully created with {len(route_coords)} points and {round(route_distance_miles, 2)} miles")
                    return route_coords
                else:
                    print(f"⚠ Could not find coordinates in route response")
                    print(f"Feature structure: {json.dumps(feature, indent=2)[:300]}...")
            else:
                print(f"⚠ No features found in route response")
                print(f"Response structure: {json.dumps(route_data, indent=2)[:300]}...")
        else:
            print(f"⚠ Directions API request failed: {response.status_code} {response.reason}")
            print(f"Response content: {response.text[:500]}...")

    except Exception as e:
        import traceback
        print(f"⚠ Error fetching route: {e}")
        print(f"Traceback: {traceback.format_exc()}")

    # If we get here, something went wrong - return an empty route
    print("⚠ Returning empty route due to errors")
    return []

def calculate_route_distance(route_coords):
    """Calculate the total distance of a route based on its coordinates."""
    total_distance = 0
    if len(route_coords) < 2:
        return 0
    for i in range(len(route_coords) - 1):
        point1 = (route_coords[i][1], route_coords[i][0])
        point2 = (route_coords[i+1][1], route_coords[i+1][0])
        total_distance += geodesic(point1, point2).miles
    return total_distance

# def calculate_distance(point1, point2):
#     """Calculate the distance between two geo points in miles."""
#     coords = [point1[::-1], point2[::-1]]
#     result=ors_client.distance_matrix(
#         locations=[[point1[1],point1[0]], [point2[1],point2[0]]],
#         profile='driving-car',
#         metrics=['distance'],
#         units='mi'
#     )
#     # if result:
#     #     route = result[0]
#     distance_miles = result['distances'][0][1] # Convert meters to miles
#         # duration = route["legs"][0]["duration"]["value"] / 60  #  minutes
#     time.sleep(3)
#     print(distance_miles)
#         # logger.info(f"Distance: {distance_miles:.2f} miles")
#     return distance_miles
#     # return geodesic(point1, point2).miles

# def calculate_distance(point1, point2):
#     """Calculate the distance between two geo points in miles."""
#     return geodesic(point1, point2).miles

def calculate_distance(point1, point2, ors_client=None):
    """
    Calculate the distance between two geographic points.
    Uses OpenRouteService for driving distance if available, 
    otherwise falls back to geodesic distance.

    Args:
        point1: (latitude, longitude) of first point
        point2: (latitude, longitude) of second point
        ors_client: OpenRouteService client object

    Returns:
        Distance in miles
    """
    # Fall back to geodesic distance if no client
    if not ors_client:
        from geopy.distance import geodesic
        return geodesic(point1, point2).miles
    
    try:
        print("Trying ORS for distance calculation...")
        # ORS expects coordinates as [longitude, latitude]
        coords = [[float(point1[1]), float(point1[0])], [float(point2[1]), float(point2[0])]]
        
        # Use matrix service for more accurate distance calculation
        matrix_response = ors_client.distance_matrix(
            locations=coords,
            metrics=['distance'],
            units='m'
        )
        
        # Primary path to extract distance
        if "distances" in matrix_response and len(matrix_response["distances"]) > 0:
            route_distance_m = matrix_response["distances"][0][1]  # Distance in meters
            return route_distance_m * 0.000621371  # Convert meters to miles
        
        # First fallback - try to estimate from durations
        elif "durations" in matrix_response and len(matrix_response["durations"]) > 0:
            print("Using estimated distance based on durations")
            # Estimate distance based on duration (assuming average speed of 50 km/h)
            route_distance_m = matrix_response["durations"][0][1] * (50 * 1000 / 3600)
            return route_distance_m * 0.000621371  # Convert meters to miles
            
    except Exception as e:
        print(f"Error calculating route distance with ORS: {e}")
    
    # Final fallback to geodesic distance
    print("Falling back to straight-line distance calculation")
    from geopy.distance import geodesic
    return geodesic(point1, point2).miles

def plot_routes_on_map(routes, stops):
    """Plot multiple routes on a Folium map with a legend and checkboxes."""
    m = folium.Map(location=stops[0], zoom_start=10)
    colors = ['blue', 'green', 'red', 'purple', 'orange']
    layers = []
    for idx, (route, start, end) in enumerate(routes):
        layer = folium.FeatureGroup(name=f"Route {idx + 1}: {start} → {end}")
        folium.PolyLine(
            locations=[(lat, lon) for lon, lat in route],
            color=colors[idx % len(colors)],
            weight=5,
            opacity=0.7,
            tooltip=f"Route {idx + 1}: {start} → {end}"
        ).add_to(layer)
        layers.append(layer)
    for layer in layers:
        layer.add_to(m)
    folium.LayerControl().add_to(m)
    LocateControl().add_to(m)
    map_filename = f"multi_stop_route_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    map_path = os.path.join(TRIAL_MAPS_DIR, map_filename)
    m.save(map_path)
    print(f"Map saved at {map_path}")