# import redis
# import pandas as pd
# from openrouteservice import client
# import time

# def initialize_redis(host='localhost', port=6379, db=0):
#     """Initialize Redis connection."""
#     return redis.Redis(host=host, port=port, db=db, decode_responses=True)

# def load_phlebotomists_to_redis(redis_conn, phleb_df):
#     """
#     Load phlebotomists data into Redis geospatial index.
    
#     Args:
#         redis_conn: Redis connection
#         phleb_df: DataFrame with phlebotomist information
#     """
#     # Clear existing geospatial data
#     redis_conn.delete('phlebotomists')
    
#     # Add phlebotomists to geospatial index
#     for _, phleb in phleb_df.iterrows():
#         phleb_id = str(phleb["PhlebotomistID.1"])
#         lat = phleb["PhlebotomistLatitude"]
#         lon = phleb["PhlebotomistLongitude"]
        
#         # Store phlebotomist location in geospatial index
#         redis_conn.geoadd('phlebotomists', (lon, lat, phleb_id))
        
#         # Store phlebotomist data as hash
#         phleb_data = {
#             'id': phleb_id,
#             'name': phleb.get('Name', ''),
#             'city': phleb.get('City', ''),
#             'latitude': str(lat),
#             'longitude': str(lon)
#         }
#         redis_conn.hset(f'phleb:{phleb_id}', mapping=phleb_data)

# def get_nearby_phlebotomists(redis_conn, lat, lon, radius_miles=30):
#     """
#     Get phlebotomists within radius_miles of the given coordinates.
    
#     Args:
#         redis_conn: Redis connection
#         lat: Latitude of target location
#         lon: Longitude of target location
#         radius_miles: Search radius in miles
        
#     Returns:
#         List of phlebotomist IDs within the radius
#     """
#     # Redis uses meters, so convert miles to meters (1 mile ≈ 1609.34 meters)
#     radius_meters = radius_miles * 1609.34
    
#     # Get phlebotomists within radius with distances
#     nearby_phlebs = redis_conn.georadius(
#         'phlebotomists', 
#         lon, 
#         lat, 
#         radius_meters, 
#         unit='m', 
#         withdist=True,
#         withcoord=True
#     )
    
#     # Return as list of (id, distance_miles, [lon, lat])
#     return [(phleb_id, dist/1609.34, coords) for phleb_id, dist, coords in nearby_phlebs]

# # def calculate_route_distance(ors_client, start_coords, end_coords):
# #     """
# #     Calculate the driving distance between two points using OpenRouteService.
    
# #     Args:
# #         ors_client: OpenRouteService client
# #         start_coords: (latitude, longitude) of starting point
# #         end_coords: (latitude, longitude) of ending point
        
# #     Returns:
# #         Distance in miles
# #     """
# #     import json
    
# #     try:
# #         # ORS expects coordinates as [longitude, latitude]
# #         coords = [[start_coords[1], start_coords[0]], [end_coords[1], end_coords[0]]]
        
# #         # Get route
# #         route = ors_client.directions(
# #             coordinates=coords,
# #             profile='driving-car',
# #             format='geojson',
# #             units='mi',
# #             instructions=False
# #         )
        
# #         # Extract distance from response (in miles)
# #         if 'features' in route and len(route['features']) > 0:
# #             feature = route['features'][0]
            
# #             # Try multiple possible locations for the distance value
# #             if 'properties' in feature:
# #                 props = feature['properties']
                
# #                 # Option 1: Check segments array
# #                 if 'segments' in props and len(props['segments']) > 0:
# #                     if 'distance' in props['segments'][0]:
# #                         return props['segments'][0]['distance']
                
# #                 # Option 2: Check summary object
# #                 if 'summary' in props and 'distance' in props['summary']:
# #                     return props['summary']['distance']
                
# #                 # Option 3: Check direct distance property
# #                 if 'distance' in props:
# #                     return props['distance']
            
# #             # Option 4: Check at features level
# #             if 'distance' in feature:
# #                 return feature['distance']
            
# #             # Option 5: Check summary at the root level
# #             if 'summary' in route and 'distance' in route['summary']:
# #                 return route['summary']['distance']
            
# #             # Debug the structure if we still can't find the distance
# #             print(f"Warning: Could not find distance in route response structure. Using fallback.")
# #             print(f"Response structure: {json.dumps(route, indent=2)[:500]}...")
# #         else:
# #             print("Warning: No features found in route response. Using fallback.")
        
# #         # If we can't find the distance in the response, fall back to geodesic
# #         from geopy.distance import geodesic
# #         geodesic_distance = geodesic(start_coords, end_coords).miles
# #         print(f"Using geodesic distance fallback: {geodesic_distance:.2f} miles")
# #         return geodesic_distance
        
# #     except Exception as e:
# #         print(f"Error calculating route distance: {e}")
        
# #         # More detailed error information
# #         import traceback
# #         print(f"Traceback: {traceback.format_exc()}")
        
# #         # Fall back to geodesic distance if route calculation fails
# #         from geopy.distance import geodesic
# #         geodesic_distance = geodesic(start_coords, end_coords).miles
# #         print(f"Using geodesic distance fallback: {geodesic_distance:.2f} miles")
# #         return geodesic_distance

# def calculate_route_distance(ors_client, start_coords, end_coords, use_scheduled_time=True):
#     """
#     Calculate the driving distance between two points using OpenRouteService.
#     Checks GeoJSON cache first, then calls API if not found.
    
#     Args:
#         ors_client: OpenRouteService client
#         start_coords: (latitude, longitude) of starting point
#         end_coords: (latitude, longitude) of ending point
#         use_scheduled_time: Whether to use scheduled time in route ID generation
        
#     Returns:
#         Distance in miles
#     """
#     import json
#     from route_utils import (
#         load_geojson, 
#         generate_route_id, 
#         find_route_in_geojson, 
#         save_geojson
#     )
    
#     try:
#         # Load GeoJSON data
#         geojson_data = load_geojson()
        
#         # Generate route_id using the same format as route_utils
#         route_id = generate_route_id(start_coords, end_coords, use_scheduled_time)
        
#         # Check if route exists in GeoJSON cache
#         existing_route = find_route_in_geojson(route_id, geojson_data)
#         if existing_route:
#             print(f"✅ Route found in local GeoJSON cache: {route_id}")
            
#             # Extract distance from cached route
#             if (existing_route.get('properties', {}).get('distance_miles') is not None):
#                 cached_distance = existing_route['properties']['distance_miles']
#                 print(f"✅ Using cached distance: {cached_distance} miles")
#                 return cached_distance
#             else:
#                 print("⚠ Cached route found but no distance stored. Calculating from coordinates...")
#                 # If no distance stored, calculate from cached coordinates
#                 if 'geometry' in existing_route and 'coordinates' in existing_route['geometry']:
#                     coords = existing_route['geometry']['coordinates']
#                     if len(coords) >= 2:
#                         # Use first and last coordinates to estimate distance
#                         start_cached = [coords[0][1], coords[0][0]]  # Convert lon,lat to lat,lon
#                         end_cached = [coords[-1][1], coords[-1][0]]
#                         from geopy.distance import geodesic
#                         estimated_distance = geodesic(start_cached, end_cached).miles
#                         print(f"✅ Estimated distance from cached route: {estimated_distance:.2f} miles")
#                         return estimated_distance

#         # Route not found in cache, fetch from OpenRouteService
#         print(f"🔍 Route not found in GeoJSON cache. Fetching from OpenRouteService...")
        
#         # ORS expects coordinates as [longitude, latitude]
#         coords = [[start_coords[1], start_coords[0]], [end_coords[1], end_coords[0]]]
        
#         # Get route from ORS
#         route = ors_client.directions(
#             coordinates=coords,
#             profile='driving-car',
#             format='geojson',
#             units='mi',
#             instructions=False
#         )
        
#         route_distance_miles = None
#         route_coords = None
        
#         # Extract distance and coordinates from response
#         if 'features' in route and len(route['features']) > 0:
#             feature = route['features'][0]
            
#             # Extract coordinates
#             if 'geometry' in feature and 'coordinates' in feature['geometry']:
#                 route_coords = feature['geometry']['coordinates']
            
#             # Try multiple possible locations for the distance value
#             if 'properties' in feature:
#                 props = feature['properties']
                
#                 # Option 1: Check segments array
#                 if 'segments' in props and len(props['segments']) > 0:
#                     if 'distance' in props['segments'][0]:
#                         route_distance_miles = props['segments'][0]['distance']
                
#                 # Option 2: Check summary object
#                 if route_distance_miles is None and 'summary' in props and 'distance' in props['summary']:
#                     route_distance_miles = props['summary']['distance']
                
#                 # Option 3: Check direct distance property
#                 if route_distance_miles is None and 'distance' in props:
#                     route_distance_miles = props['distance']
            
#             # Option 4: Check at features level
#             if route_distance_miles is None and 'distance' in feature:
#                 route_distance_miles = feature['distance']
            
#             # Option 5: Check summary at the root level
#             if route_distance_miles is None and 'summary' in route and 'distance' in route['summary']:
#                 route_distance_miles = route['summary']['distance']
        
#         # If we still don't have distance, use geodesic fallback
#         if route_distance_miles is None:
#             print(f"Warning: Could not find distance in route response. Using geodesic fallback.")
#             from geopy.distance import geodesic
#             route_distance_miles = geodesic(start_coords, end_coords).miles
        
#         # If we don't have route coordinates, create a simple line
#         if route_coords is None or len(route_coords) < 2:
#             print("Warning: No valid route coordinates found. Using straight line.")
#             route_coords = [coords[0], coords[1]]  # [start_coords, end_coords] in lon,lat format
        
#         # Save the new route to GeoJSON cache
#         new_feature = {
#             "type": "Feature",
#             "geometry": {"type": "LineString", "coordinates": route_coords},
#             "properties": {
#                 "route_id": route_id,
#                 "start": start_coords,
#                 "end": end_coords,
#                 "distance_miles": round(route_distance_miles, 2)
#             }
#         }
        
#         geojson_data["features"].append(new_feature)
#         save_geojson(geojson_data)
        
#         print(f"✅ Route cached with {len(route_coords)} points and {round(route_distance_miles, 2)} miles")
#         return route_distance_miles
        
#     except Exception as e:
#         print(f"Error calculating route distance: {e}")
        
#         # More detailed error information
#         import traceback
#         print(f"Traceback: {traceback.format_exc()}")
        
#         # Fall back to geodesic distance if route calculation fails
#         from geopy.distance import geodesic
#         geodesic_distance = geodesic(start_coords, end_coords).miles
#         print(f"Using geodesic distance fallback: {geodesic_distance:.2f} miles")
#         return geodesic_distance

# def initialize_ors_client(api_key):
#     """Initialize OpenRouteService client."""
#     return client.Client(key=api_key)
import redis
import pandas as pd
from openrouteservice import client
import time
import json
import traceback
from datetime import datetime

def initialize_redis(host='localhost', port=6379, db=0):
    """Initialize Redis connection."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing Redis connection to {host}:{port}")
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)

def load_phlebotomists_to_redis(redis_conn, phleb_df):
    """
    Load phlebotomists data into Redis geospatial index.
    
    Args:
        redis_conn: Redis connection
        phleb_df: DataFrame with phlebotomist information
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading {len(phleb_df)} phlebotomists to Redis...")
    
    # Clear existing geospatial data
    redis_conn.delete('phlebotomists')
    
    # Add phlebotomists to geospatial index
    for idx, phleb in phleb_df.iterrows():
        phleb_id = str(phleb["PhlebotomistID.1"])
        lat = phleb["PhlebotomistLatitude"]
        lon = phleb["PhlebotomistLongitude"]
        
        # Store phlebotomist location in geospatial index
        redis_conn.geoadd('phlebotomists', (lon, lat, phleb_id))
        
        # Store phlebotomist data as hash
        phleb_data = {
            'id': phleb_id,
            'name': phleb.get('Name', ''),
            'city': phleb.get('City', ''),
            'latitude': str(lat),
            'longitude': str(lon)
        }
        redis_conn.hset(f'phleb:{phleb_id}', mapping=phleb_data)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Successfully loaded phlebotomists to Redis")

def get_nearby_phlebotomists(redis_conn, lat, lon, radius_miles=30):
    """
    Get phlebotomists within radius_miles of the given coordinates.
    
    Args:
        redis_conn: Redis connection
        lat: Latitude of target location
        lon: Longitude of target location
        radius_miles: Search radius in miles
        
    Returns:
        List of phlebotomist IDs within the radius
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Searching for phlebotomists within {radius_miles} miles of ({lat:.4f}, {lon:.4f})")
    
    # Redis uses meters, so convert miles to meters (1 mile ≈ 1609.34 meters)
    radius_meters = radius_miles * 1609.34
    
    # Get phlebotomists within radius with distances
    nearby_phlebs = redis_conn.georadius(
        'phlebotomists', 
        lon, 
        lat, 
        radius_meters, 
        unit='m', 
        withdist=True,
        withcoord=True
    )
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(nearby_phlebs)} phlebotomists within radius")
    
    # Return as list of (id, distance_miles, [lon, lat])
    return [(phleb_id, dist/1609.34, coords) for phleb_id, dist, coords in nearby_phlebs]

def calculate_route_distance(ors_client, start_coords, end_coords, use_scheduled_time=True):
    """
    Calculate the driving distance between two points using OpenRouteService.
    Uses the same caching logic as route_utils.py
    
    Args:
        ors_client: OpenRouteService client (can be None to use ORS API key from env)
        start_coords: (latitude, longitude) of starting point
        end_coords: (latitude, longitude) of ending point
        use_scheduled_time: Whether to use scheduled time in route ID generation
        
    Returns:
        Distance in miles
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === Calculating route distance ===")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Start: {start_coords}, End: {end_coords}")
    
    from route_utils import (
        load_geojson, 
        generate_route_id, 
        find_route_in_geojson,
        save_geojson,
        ORSKEY
    )
    
    try:
        # Load GeoJSON data
        geojson_data = load_geojson()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loaded GeoJSON with {len(geojson_data['features'])} existing routes")
        
        # Generate route_id using the same format as route_utils
        route_id = generate_route_id(start_coords, end_coords, use_scheduled_time)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Generated route_id: {route_id}")
        
        # Check if route exists in GeoJSON cache
        existing_route_coords = find_route_in_geojson(route_id, geojson_data)
        
        if existing_route_coords:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Route found in local GeoJSON cache!")
            
            # Find the feature to get the distance
            for feature in geojson_data["features"]:
                if feature["properties"]["route_id"] == route_id:
                    if "distance_miles" in feature["properties"]:
                        cached_distance = feature["properties"]["distance_miles"]
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Using cached distance: {cached_distance} miles")
                        return cached_distance
                    else:
                        # Calculate distance from coordinates if not stored
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  No distance in cache, calculating from coordinates...")
                        from geopy.distance import geodesic
                        total_distance = 0
                        for i in range(len(existing_route_coords) - 1):
                            point1 = (existing_route_coords[i][1], existing_route_coords[i][0])
                            point2 = (existing_route_coords[i+1][1], existing_route_coords[i+1][0])
                            total_distance += geodesic(point1, point2).miles
                        
                        # Update the feature with calculated distance
                        feature["properties"]["distance_miles"] = round(total_distance, 2)
                        save_geojson(geojson_data)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 Updated cache with calculated distance: {round(total_distance, 2)} miles")
                        return total_distance

        # Route not found in cache, fetch from OpenRouteService
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Route not found in GeoJSON cache. Fetching from OpenRouteService...")
        
        # Use the same logic as route_utils.py get_route function
        api_key = ORSKEY if ors_client is None else ors_client.key
        
        if api_key is None:
            print("⚠ API key is missing!")
            return 0
        
        # Convert to ORS format [longitude, latitude]
        start_coords_ors = [float(start_coords[1]), float(start_coords[0])]
        end_coords_ors = [float(end_coords[1]), float(end_coords[0])]
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Calling ORS Distance Matrix API...")
        
        # Step 1: Get Distance using ORS Distance Matrix API (same as route_utils.py)
        import requests
        matrix_url = "https://api.openrouteservice.org/v2/matrix/driving-car"
        matrix_body = {
            "locations": [start_coords_ors, end_coords_ors],
            "metrics": ["distance"],
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
            # Fallback to geodesic
            from geopy.distance import geodesic
            return geodesic(start_coords, end_coords).miles

        matrix_data = matrix_response.json()
        
        # Extract distance (same logic as route_utils.py)
        route_distance_m = 0
        if "distances" in matrix_data and len(matrix_data["distances"]) > 0:
            route_distance_m = matrix_data["distances"][0][1]
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Got distance from matrix API: {route_distance_m} meters")
        else:
            print(f"⚠ Could not find distances in matrix response")
            from geopy.distance import geodesic
            route_distance_m = geodesic(start_coords, end_coords).meters
        
        route_distance_miles = route_distance_m * 0.000621371
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Calling ORS Directions API...")
        
        # Step 2: Get Route using ORS Directions API (same as route_utils.py)
        directions_url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        directions_body = {"coordinates": [start_coords_ors, end_coords_ors]}

        directions_headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }

        response = requests.post(directions_url, json=directions_body, headers=directions_headers)

        if response.status_code == 200:
            route_data = response.json()
            
            if "features" in route_data and route_data["features"]:
                feature = route_data["features"][0]
                
                if "geometry" in feature and "coordinates" in feature["geometry"]:
                    route_coords = feature["geometry"]["coordinates"]
                    
                    if not route_coords or len(route_coords) < 2:
                        print(f"⚠ Invalid or empty route coordinates")
                        route_coords = [start_coords_ors, end_coords_ors]
                    
                    # Store new route in GeoJSON with distance (same as route_utils.py)
                    new_feature = {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": route_coords},
                        "properties": {
                            "route_id": route_id,
                            "start": start_coords,
                            "end": end_coords,
                            "distance_miles": round(route_distance_miles, 2)
                        }
                    }
                    geojson_data["features"].append(new_feature)
                    save_geojson(geojson_data)
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Route cached with {len(route_coords)} points and {round(route_distance_miles, 2)} miles")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 Total routes in cache: {len(geojson_data['features'])}")
                    
                    return route_distance_miles
                else:
                    print(f"⚠ Could not find coordinates in route response")
            else:
                print(f"⚠ No features found in route response")
        else:
            print(f"⚠ Directions API request failed: {response.status_code}")
        
        # If we get here, return the distance we calculated from matrix API
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Using distance from matrix API: {round(route_distance_miles, 2)} miles")
        return route_distance_miles
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error calculating route distance: {e}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Traceback: {traceback.format_exc()}")
        
        # Fall back to geodesic distance if route calculation fails
        from geopy.distance import geodesic
        geodesic_distance = geodesic(start_coords, end_coords).miles
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📏 Using geodesic distance fallback: {geodesic_distance:.2f} miles")
        return geodesic_distance

def initialize_ors_client(api_key):
    """Initialize OpenRouteService client."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing OpenRouteService client")
    return client.Client(key=api_key)