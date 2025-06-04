import streamlit as st
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv
import folium
from streamlit_folium import st_folium
from LogHandler import setup_logger
import final_utils_upd as utils
from redis_utils import initialize_redis, initialize_ors_client
import json
import pickle
import base64
import uuid

load_dotenv()

es_config = {
    "es_host": "localhost",
    "es_port": 9200,
    "index": "dynamic-service-app-logs"
}

# Only set up the logger once at app initialization
if 'logger' not in st.session_state:
    st.session_state.logger = setup_logger(
        log_file_prefix="dsal",
        es_config=es_config
    )
    st.session_state.logger.info("Application started")

logger = st.session_state.logger

# Set page config
st.set_page_config(
    page_title="Phlebotomist Route Optimizer",
    page_icon="🩸",
    layout="wide"
)

def clear_cache():
    """Clear Redis cache for this application"""
    if 'redis_conn' in st.session_state and st.session_state.redis_conn is not None:
        try:
            # Get all keys with the prefix 'history:'
            history_keys = st.session_state.redis_conn.keys('history:*')
            if history_keys:
                # Delete all history keys
                st.session_state.redis_conn.delete(*history_keys)
                logger.info(f"Cleared {len(history_keys)} history entries from Redis cache")
            else:
                logger.info("No history entries found to clear in Redis cache")
                
            # Clear session state history list
            st.session_state.history_items = []
            
            return True
        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
            return False
    return False

def get_history_items():
    """Get all history items from Redis"""
    if 'redis_conn' in st.session_state and st.session_state.redis_conn is not None:
        try:
            # Get all keys with the prefix 'history:'
            history_keys = st.session_state.redis_conn.keys('history:*')
            
            # Extract date-city pairs from keys
            history_items = []
            for key in history_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                # Format: history:<date>:<city>
                parts = key_str.split(':', 2)
                if len(parts) == 3:
                    history_items.append({
                        'date': parts[1],
                        'city': parts[2],
                        'key': key_str
                    })
            
            return history_items
        except Exception as e:
            logger.error(f"Failed to get history items from Redis: {e}")
    return []

def save_to_cache(date, city, assignment_map, assigned_phlebs, assigned_patients, use_scheduled_time):
    """Save assignment results to Redis cache"""
    if 'redis_conn' in st.session_state and st.session_state.redis_conn is not None:
        try:
            date_str = date.strftime('%Y-%m-%d')
            key = f"history:{date_str}:{city}"
            
            # Convert folium map to HTML string
            map_html = assignment_map.get_root().render()
            
            # Create a cache object
            cache_data = {
                'date': date_str,
                'city': city,
                'map_html': map_html,
                'assigned_phlebs': base64.b64encode(pickle.dumps(assigned_phlebs)).decode('utf-8'),
                'assigned_patients': base64.b64encode(pickle.dumps(assigned_patients)).decode('utf-8'),
                'use_scheduled_time': use_scheduled_time,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save to Redis
            st.session_state.redis_conn.set(key, json.dumps(cache_data, default=str), ex=86400)  # expire in 24 hours
            
            # Update history items in session state
            if 'history_items' not in st.session_state:
                st.session_state.history_items = []
            
            # Log current history items BEFORE adding
            logger.info(f"History items before update: {st.session_state.history_items}")
            
            # Check if this item already exists
            existing_item = next((item for item in st.session_state.history_items 
                                if item['date'] == date_str and item['city'] == city), None)
            
            if not existing_item:
                # Add to history items
                st.session_state.history_items.append({
                    'date': date_str,
                    'city': city,
                    'key': key
                })
                
                # Log updated history items AFTER adding
                logger.info(f"History items after update: {st.session_state.history_items}")
            
            logger.info(f"Saved assignment results to Redis cache: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to save assignment results to Redis cache: {e}")
    return False


def initialize_session_state():
    """Initialize session state variables"""
    # Reset cache on page reload/refresh if client session ID changed
    if 'client_session_id' not in st.session_state:
        st.session_state.client_session_id = str(uuid.uuid4())
        # Clear cache on first load or page refresh
        logger.info("New session detected - clearing Redis cache")
        clear_cache()
    
    # Basic data state
    if 'trips_df' not in st.session_state:
        st.session_state.trips_df = None
    if 'phleb_df' not in st.session_state:
        st.session_state.phleb_df = None
    if 'workload_df' not in st.session_state:
        st.session_state.workload_df = None
    if 'dates' not in st.session_state:
        st.session_state.dates = []
    if 'date_city_map' not in st.session_state:
        st.session_state.date_city_map = {}
    
    # History/cache state
    if 'history_items' not in st.session_state:
        st.session_state.history_items = get_history_items()
    if 'results_from_cache' not in st.session_state:
        st.session_state.results_from_cache = False

def save_assignment_results_with_cache(assignment_map, assigned_phlebs, assigned_patients, date, city, use_scheduled_time):
    """Save assignment results to files and cache"""
    # First save to files
    saved_files = utils.save_assignment_results(
        assignment_map,
        assigned_phlebs,
        assigned_patients,
        date,
        city,
        use_scheduled_time,
        phleb_df=st.session_state.phleb_df,
    )
    
    # Then save to cache
    save_to_cache(date, city, assignment_map, assigned_phlebs, assigned_patients, use_scheduled_time)
    
    return saved_files


# Modified display_results function without using 'key' on HTML component

def display_results():
    """Display assignment results with proper map refresh"""
    if ('assigned_phlebs' in st.session_state and st.session_state.assigned_phlebs is not None and
        'assigned_patients' in st.session_state and st.session_state.assigned_patients is not None):
        
        # Only log once when results are first displayed or regenerated
        if 'results_displayed' not in st.session_state or not st.session_state.results_displayed:
            if 'results_from_cache' in st.session_state and st.session_state.results_from_cache:
                logger.info("Displaying assignment results from cache")
            else:
                logger.info("Displaying newly computed assignment results")
            
            st.session_state.results_displayed = True
        
        st.header("Assignment Results")
        
        # If results loaded from cache, show an indicator
        if 'results_from_cache' in st.session_state and st.session_state.results_from_cache:
            st.success("Results loaded from history cache")
        
        # Display routing mode used
        routing_mode = "Scheduled Time" if st.session_state.use_scheduled_time else "Optimized Routing"
        st.subheader(f"Routing Mode: {routing_mode}")
        st.divider()
        
        # Display assignment statistics
        st.subheader("Assignment Statistics")
        col1, col2, col3 = st.columns(3)
        
        patients_count = len(st.session_state.assigned_patients)
        phlebs_count = len(st.session_state.assigned_phlebs)
        
        # Get total distance
        total_distance = sum(st.session_state.assigned_phlebs["total_distance"])
        
        with col1:
            st.metric("Patients Assigned", patients_count)
        
        with col2:
            st.metric("Phlebotomists Used", phlebs_count)
        
        with col3:
            # Calculate total distance
            st.metric("Total Route Distance", f"{total_distance:.2f} miles")
        
        # Display the map - use a container with a unique ID to help force refresh
        st.subheader("Route Map")
        
        # Create a new unique timestamp inside this specific function call
        # This ensures the map HTML is different each time, forcing a refresh
        timestamp = datetime.now().timestamp()
        
        if 'cached_map_html' in st.session_state and st.session_state.cached_map_html:
            # Instead of using a key, modify the HTML content itself to make it unique
            # Add a hidden timestamp comment that doesn't affect rendering but makes the HTML different
            modified_html = st.session_state.cached_map_html + f"<!-- timestamp: {timestamp} -->"
            # Display cached map HTML (now with timestamp comment)
            st.components.v1.html(modified_html, height=800)
        else:
            # Display newly generated map with timestamp comment
            if 'assignment_map' in st.session_state and st.session_state.assignment_map:
                html_temp = st.session_state.assignment_map.get_root().render() + f"<!-- timestamp: {timestamp} -->"
                st.components.v1.html(html_temp, height=800)
            else:
                st.warning("Map data is not available.")
        
        # Display phlebotomist assignments
        st.subheader("Phlebotomist Assignments")
        phleb_display = st.session_state.assigned_phlebs.copy()
        
        # Convert the list to a string for display
        phleb_display["assigned_patients"] = phleb_display["assigned_patients"].apply(lambda x: f"{len(x)}")
        phleb_display = phleb_display[[
            "PhlebotomistID.1", "current_workload", "total_distance", "assigned_patients"
        ]].rename(columns={
            "PhlebotomistID.1": "Phlebotomist ID", 
            "current_workload": "Workload Points",
            "total_distance": "Route Distance (miles)",
            "assigned_patients": "Patients Assigned"
        })
        
        # Use unique key for phlebotomist table based on current selection
        st.dataframe(phleb_display, key=f"phlebs_{timestamp}")
        
        # Display patient assignments
        st.subheader("Patient Assignments")
        
        # Add the preferred time column if it exists
        display_columns = ["PatientFirstName", "AssignedPhlebID", "TripOrderInDay", "WorkloadPoints"]
        column_renames = {
            "AssignedPhlebID": "Phlebotomist ID",
            "TripOrderInDay": "Trip Order",
            "WorkloadPoints": "Workload Points"
        }
        
        if "PreferredTime" in st.session_state.assigned_patients.columns:
            display_columns.extend(["ScheduledDtm", "PreferredTime"])
            column_renames.update({
                "ScheduledDtm": "Original Scheduled Time",
                "PreferredTime": "Preferred Visit Time"
            })
        else:
            display_columns.append("ScheduledDtm")
            column_renames.update({
                "ScheduledDtm": "Scheduled Time"
            })
            
        # Ensure all needed columns exist before displaying
        valid_columns = [col for col in display_columns if col in st.session_state.assigned_patients.columns]
        patient_display = st.session_state.assigned_patients[valid_columns].rename(
            columns={k: v for k, v in column_renames.items() if k in valid_columns}
        )
        
        # Use unique key for patient table based on timestamp
        st.dataframe(patient_display, key=f"patients_{timestamp}")
        
        # Only regenerate saved files if results are not from cache
        if not st.session_state.results_from_cache and 'assignment_map' in st.session_state:
            # Save results to files (only for newly computed results)
            if 'saved_files' not in st.session_state:
                date = st.session_state.selected_date
                city = st.session_state.selected_city
                st.session_state.saved_files = utils.save_assignment_results(
                    st.session_state.assignment_map,
                    st.session_state.assigned_phlebs,
                    st.session_state.assigned_patients,
                    date,
                    city,
                    st.session_state.use_scheduled_time,
                    phleb_df=st.session_state.phleb_df,
                )
                logger.info(f"Saved assignment results to files: {st.session_state.saved_files}")
        
        # Display download links
        if 'saved_files' in st.session_state:
            st.subheader("Download Results")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                map_path = st.session_state.saved_files["map"]
                if os.path.exists(map_path):
                    with open(map_path, "rb") as file:
                        st.download_button(
                            "Download Map (HTML)",
                            file,
                            file_name=os.path.basename(map_path),
                            mime="text/html",
                            key=f"dl_map_{timestamp}"
                        )
                else:
                    st.warning("Map file not found for download.")
            
            with col2:
                phlebs_path = st.session_state.saved_files["phlebs"]
                if os.path.exists(phlebs_path):
                    with open(phlebs_path, "rb") as file:
                        st.download_button(
                            "Download Phlebotomist Assignments (CSV)",
                            file,
                            file_name=os.path.basename(phlebs_path),
                            mime="text/csv",
                            key=f"dl_phlebs_{timestamp}"
                        )
                else:
                    st.warning("Phlebotomist assignments file not found for download.")
            
            with col3:
                patients_path = st.session_state.saved_files["patients"]
                if os.path.exists(patients_path):
                    with open(patients_path, "rb") as file:
                        st.download_button(
                            "Download Patient Assignments (CSV)",
                            file,
                            file_name=os.path.basename(patients_path),
                            mime="text/csv",
                            key=f"dl_patients_{timestamp}"
                        )
                else:
                    st.warning("Patient assignments file not found for download.")

# Improved load_history_item function to force map refresh without keys
def load_history_item(date, city):
    """Load assignment results from cache for a history item with proper map refresh"""
    logger.info(f"Loading history item for date: {date}, city: {city}")

    # Force refresh by clearing session state variables
    # First, clear any existing cached map to force refresh
    if 'cached_map_html' in st.session_state:
        del st.session_state.cached_map_html
    if 'assignment_map' in st.session_state:
        st.session_state.assignment_map = None
    
    # Reset results display flag to force re-render
    st.session_state.results_displayed = False
    
    # Load from cache
    cached_data = load_from_cache(date, city)

    if cached_data is None:
        logger.error("Cached data is invalid or not found.")
        return False

    # Force Streamlit to recalculate UI by setting unique timestamp
    st.session_state.last_refresh_time = datetime.now().timestamp()

    # Generate saved files for download if needed
    if 'saved_files' not in st.session_state:
        try:
            # Save results to files for download
            saved_files = utils.save_assignment_results(
                None,  # No map object
                st.session_state.assigned_phlebs,
                st.session_state.assigned_patients,
                date,
                city,
                st.session_state.use_scheduled_time,
                phleb_df=st.session_state.phleb_df,
            )
            st.session_state.saved_files = saved_files
        except Exception as e:
            logger.error(f"Failed to create saved files: {e}")

    logger.info("Successfully loaded cached assignment")
    return True

   
def display_history_sidebar():
    """Display the history items in the sidebar"""
    st.sidebar.header("History")
    
    if not st.session_state.history_items:
        st.sidebar.info("No history items available")
        return
    
    st.sidebar.write("Previously calculated assignments:")
    
    # Create a scrollable container for history items
    with st.sidebar.container(height=300):
        for item in st.session_state.history_items:
            date = item['date']
            city = item['city']
            
            # Create a clickable button for each history item
            if st.button(f"{date} - {city}", key=f"history_{date}_{city}"):
                success = load_history_item(date, city)
                if success:
                    # Force rerun - critical for UI update without duplicating elements
                    st.rerun()
    
    # Add a clear history button
    if st.sidebar.button("Clear History"):
        if clear_cache():
            st.rerun()


# The primary bug fix - return cached_data, not True
def load_from_cache(date, city):
    """Load assignment results from Redis cache"""
    if 'redis_conn' in st.session_state and st.session_state.redis_conn is not None:
        try:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
            key = f"history:{date_str}:{city}"
            
            if not st.session_state.redis_conn.exists(key):
                logger.info(f"Cache miss for {key}")
                return None

            cached_data_str = st.session_state.redis_conn.get(key)
            if not cached_data_str:
                return None

            cached_data = json.loads(cached_data_str)

            # Set session state values to override current UI
            st.session_state.assigned_phlebs = pickle.loads(base64.b64decode(cached_data['assigned_phlebs'].encode()))
            st.session_state.assigned_patients = pickle.loads(base64.b64decode(cached_data['assigned_patients'].encode()))
            st.session_state.assignment_map = folium.Map()  # Dummy, if needed to avoid crash
            st.session_state.cached_map_html = cached_data.get('map_html')
            st.session_state.use_scheduled_time = cached_data.get('use_scheduled_time', True)

            # Critical: Set selected date and city to match the cached data
            st.session_state.selected_date = datetime.strptime(date_str, '%Y-%m-%d') if isinstance(date, str) else date
            st.session_state.selected_city = city
            st.session_state.results_from_cache = True
            st.session_state.results_displayed = False  # Force re-render

            logger.info(f"Loaded assignment results from Redis cache: {key}")
            
            # Return the actual cached data instead of True
            return cached_data
        except Exception as e:
            logger.error(f"Failed to load assignment results from Redis cache: {e}", exc_info=True)
    return None


# Modify main() to ensure results always show below parameters
def main():
    """Main application flow - with results displayed BELOW parameters"""
    # Initialize session state variables
    initialize_session_state()
    
    st.title("Phlebotomist Assignment & Route Optimizer")
    
    trips_path = "req8425.csv"
    phlebs_path = "phlebotomists_with_city.csv"
    workload_path = "avg_workload_per_city_per_phleb.csv"
    
    logger.info(f"Attempting to load data from: trips={trips_path}, phlebs={phlebs_path}, workload={workload_path}")
    with st.spinner("Loading data..."):
        st.session_state.trips_df, st.session_state.phleb_df, st.session_state.workload_df = utils.load_data(
            trips_path, phlebs_path, workload_path
        )
        
        if st.session_state.trips_df is not None:
            st.session_state.dates = utils.get_available_dates(st.session_state.trips_df)
            logger.info(f"Found {len(st.session_state.dates)} available dates in data")
            
            st.session_state.date_city_map = utils.get_cities_by_date(st.session_state.trips_df)
            logger.info(f"Mapped {len(st.session_state.date_city_map)} dates to their respective cities")
            
            logger.info("Data loaded successfully")
        else:
            logger.error("Failed to load data - trips dataframe is None")
    
    # Get API key from environment variables
    api_key = os.getenv("ORS_API_KEY") or os.getenv("KEY")
    
    # Get Redis connection parameters from environment variables
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    # Initialize Redis and ORS clients if possible
    if 'redis_conn' not in st.session_state:
        try:
            st.session_state.redis_conn = initialize_redis(host=redis_host, port=redis_port)
            # Test Redis connection
            st.session_state.redis_conn.ping()
            logger.info("Successfully connected to Redis geospatial database")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using fallback geodesic method.")
            st.session_state.redis_conn = None
    
    if 'ors_client' not in st.session_state and api_key:
        try:
            st.session_state.ors_client = initialize_ors_client(api_key)
            logger.info("Successfully initialized OpenRouteService client for routing")
        except Exception as e:
            logger.warning(f"OpenRouteService initialization failed: {e}. Using fallback geodesic method.")
            st.session_state.ors_client = None
    
    # Display the history sidebar
    display_history_sidebar()
    
    # Main content area
    if st.session_state.trips_df is None:
        st.info("Please reload the page")
        logger.info("Waiting to load data")
        return
    
    # Display basic stats
    col1, col2, col3 = st.columns(3)
    total_patients = len(st.session_state.trips_df)
    total_phlebotomists = len(st.session_state.phleb_df["PhlebotomistID.1"].unique())
    cities_covered = len(set(city for cities in st.session_state.date_city_map.values() for city in cities))
    
    # Display service metrics
    with col1:
        st.metric("Total Patients", total_patients)
    
    with col2:
        st.metric("Total Phlebotomists", total_phlebotomists)
    
    with col3:
        st.metric("Cities Covered", cities_covered)
    
    # Add service status indicators
    st.sidebar.header("Service Status")
    
    # Check Redis status
    if st.session_state.redis_conn is not None:
        st.sidebar.success("✅ Redis Geospatial: Connected")
    else:
        st.sidebar.warning("⚠️ Redis Geospatial: Not connected (Using fallback method)")
    
    # Check ORS status
    if api_key and st.session_state.get('ors_client') is not None:
        st.sidebar.success("✅ OpenRouteService: Connected")
    else:
        st.sidebar.warning("⚠️ OpenRouteService: Not connected (Using geodesic distances)")
        
    # Only log these metrics once when they change
    if 'last_metrics' not in st.session_state or (total_patients, total_phlebotomists, cities_covered) != st.session_state.last_metrics:
        logger.info(f"Displaying stats: {total_patients} patients, {total_phlebotomists} phlebotomists, {cities_covered} cities")
        st.session_state.last_metrics = (total_patients, total_phlebotomists, cities_covered)
    
    # IMPORTANT: Always show the parameters UI section FIRST
    st.header("Phlebotomist Assignment")
    
    # Date and city selection
    col1, col2 = st.columns(2)
    selected_date = None
    with col1:
        if st.session_state.dates:
            # Convert dates to string format for date_input and create a mapping
            date_strings = [date.strftime("%Y-%m-%d") for date in st.session_state.dates]
            date_to_datetime = {date.strftime("%Y-%m-%d"): date for date in st.session_state.dates}
            
            min_date = min(st.session_state.dates)
            max_date = max(st.session_state.dates)
            
            # Only log date range information once
            if 'date_range_logged' not in st.session_state:
                logger.info(f"Date range available: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
                st.session_state.date_range_logged = True
            
            # Use date_input widget for calendar selection - Use the date from cache if available
            default_date = st.session_state.selected_date if 'selected_date' in st.session_state else max_date
            selected_date_str = st.date_input(
                "Select Date",
                min_value=min_date,
                max_value=max_date,
                value=default_date,
                format="YYYY-MM-DD",
                key="date_selector"  # Add a key for streamlit to track this widget
            ).strftime("%Y-%m-%d")
            
            # Find the closest available date if selected date is not in the dataset
            if selected_date_str not in date_strings:
                available_dates = sorted(date_strings)
                selected_date_str = min(available_dates, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - datetime.strptime(selected_date_str, "%Y-%m-%d")).days))
                st.info(f"Selected date not available. Using closest available date: {selected_date_str}")
                
                # Only log unavailable date warning if it changed
                if 'last_unavailable_date' not in st.session_state or st.session_state.last_unavailable_date != selected_date_str:
                    logger.warning(f"User selected unavailable date, using closest available date: {selected_date_str}")
                    st.session_state.last_unavailable_date = selected_date_str
            
            # Convert back to datetime object
            selected_date = date_to_datetime.get(selected_date_str)
            
            # Handle date change
            if 'selected_date' in st.session_state and st.session_state.selected_date != selected_date:
                # If date has changed from what's in cache, reset results_from_cache
                if 'results_from_cache' in st.session_state and st.session_state.results_from_cache:
                    current_key = f"history:{selected_date_str}:{st.session_state.selected_city}"
                    if 'loaded_history_key' in st.session_state and current_key != st.session_state.loaded_history_key:
                        st.session_state.results_from_cache = False
                
                logger.info(f"Updated selected date in session state to {selected_date_str}")
                st.session_state.selected_date = selected_date
        else:
            if 'no_dates_warned' not in st.session_state:
                st.warning("No dates available in the data.")
                logger.warning("No dates available in the data")
                st.session_state.no_dates_warned = True
    
    selected_city = None
    with col2:
        # Get cities for the selected date
        available_cities = []
        if selected_date is not None and st.session_state.date_city_map:
            date_key = selected_date.strftime("%Y-%m-%d")
            available_cities = st.session_state.date_city_map.get(date_key, [])
            
            # Only log available cities when the date changes
            if 'last_available_cities_date' not in st.session_state or st.session_state.last_available_cities_date != date_key:
                logger.info(f"Found {len(available_cities)} cities for date {date_key}")
                st.session_state.last_available_cities_date = date_key
        
        if available_cities:
            # Use the currently selected city as the default if available
            default_idx = 0
            if 'selected_city' in st.session_state and st.session_state.selected_city in available_cities:
                default_idx = available_cities.index(st.session_state.selected_city)
            
            selected_city = st.selectbox(
                "Select City", 
                options=available_cities, 
                index=default_idx,
                key="city_selector"  # Add a key for streamlit to track this widget
            )
            
            # Handle city change
            if 'selected_city' in st.session_state and st.session_state.selected_city != selected_city:
                # If city has changed from what's in cache, reset results_from_cache
                if 'results_from_cache' in st.session_state and st.session_state.results_from_cache:
                    date_str = selected_date.strftime('%Y-%m-%d')
                    current_key = f"history:{date_str}:{selected_city}"
                    if 'loaded_history_key' in st.session_state and current_key != st.session_state.loaded_history_key:
                        st.session_state.results_from_cache = False
                
                logger.info(f"User selected city: {selected_city}")
                st.session_state.selected_city = selected_city
        else:
            date_str = selected_date.strftime('%Y-%m-%d') if selected_date else 'None'
            
            # Only log the warning once per date
            if 'last_no_cities_date' not in st.session_state or st.session_state.last_no_cities_date != date_str:
                st.warning(f"No cities available for the selected date: {date_str}")
                logger.warning(f"No cities available for the selected date: {date_str}")
                st.session_state.last_no_cities_date = date_str
    
    # Process data when both date and city are selected
    if selected_date is not None and selected_city is not None:
        # Create a unique key for this date-city combination
        date_city_key = f"{selected_date.strftime('%Y-%m-%d')}_{selected_city}"
        
        # Only log processing data once per date-city combination
        if 'last_processed_date_city' not in st.session_state or st.session_state.last_processed_date_city != date_city_key:
            logger.info(f"Processing data for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
            st.session_state.last_processed_date_city = date_city_key
        
        # Check if parameters were changed and look for cache
        date_str = selected_date.strftime('%Y-%m-%d')
        current_key = f"history:{date_str}:{selected_city}"
        need_to_check_cache = (not st.session_state.get('results_from_cache', False) or 
                              'loaded_history_key' not in st.session_state or 
                              current_key != st.session_state.loaded_history_key)
        
        if need_to_check_cache:
            cached_data = load_from_cache(selected_date, selected_city)
            if cached_data is not None:
                # We found cache for this combination, update UI
                st.success(f"Loaded cached results for {selected_city} on {date_str}")
                st.session_state.loaded_history_key = current_key
                st.rerun()  # Refresh to display results with the updated parameters
        
        # Calculate phlebotomists needed
        phlebs_needed = utils.phlebs_required_asper_workload(
            st.session_state.workload_df,
            st.session_state.trips_df,
            selected_date,
            selected_city
        )
        
        if phlebs_needed:
            # Only log phlebs needed once per date-city combination
            if 'last_phlebs_needed_key' not in st.session_state or st.session_state.last_phlebs_needed_key != date_city_key:
                logger.info(f"Calculated {phlebs_needed} phlebotomists needed for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
                st.session_state.last_phlebs_needed_key = date_city_key
            
            st.info(f"Based on workload analysis, *{phlebs_needed}* phlebotomists are needed for {selected_city} on {selected_date.strftime('%Y-%m-%d')}.")

            ################ Verify Phlebotomist Availability Section #######################
            
            st.subheader("Verify Phlebotomist Availability")
            with st.expander("Phlebotomist List", expanded=False):

                # Initialize session state
                if 'selected_phlebs' not in st.session_state:
                    st.session_state.selected_phlebs = []

                # Auto-select phlebotomists in the same city during initialization
                # Use Redis geospatial indexing if available
                all_sorted_phlebs = utils.get_available_phlebotomists(
                    st.session_state.phleb_df, 
                    selected_city, 
                    len(st.session_state.phleb_df),
                    redis_conn=st.session_state.get('redis_conn'),
                    ors_api_key=api_key
                )
                
                for _, phleb in all_sorted_phlebs.iterrows():
                    if phleb.get("City") == selected_city and str(phleb["PhlebotomistID.1"]) not in st.session_state.selected_phlebs:
                        st.session_state.selected_phlebs.append(str(phleb["PhlebotomistID.1"]))
                
                # Create a search box for phlebotomist ID
                search_query = st.text_input("Search Phlebotomist ID", key="phleb_search")

                # Filter phlebotomists based on search query
                if search_query:
                    filtered_phlebs = all_sorted_phlebs[
                        all_sorted_phlebs["PhlebotomistID.1"].astype(str).str.contains(search_query, case=False)
                    ]
                else:
                    filtered_phlebs = all_sorted_phlebs

                # Display available phlebotomists header
                st.write(f"Available Phlebotomists for {selected_city} on {selected_date.strftime('%Y-%m-%d')} (sorted by distance)")

                # Use Streamlit's grid layout directly with 5 columns
                cols = st.columns(5)

                # Distribute phlebotomists across columns
                for i, (_, phleb) in enumerate(filtered_phlebs.iterrows()):
                    col_idx = i % 5
                    phleb_id = str(phleb["PhlebotomistID.1"])
                    phleb_name = phleb.get('PhlebotomistName', 'Unknown')
                    distance = phleb.get("distance_to_target", 0)

                    with cols[col_idx]:
                        # Create checkbox
                        is_selected = st.checkbox(
                            f"{phleb_id} - {phleb_name}",
                            value=phleb_id in st.session_state.selected_phlebs,
                            key=f"phleb_{phleb_id}"
                        )

                        # Show distance info
                        st.markdown(f'<div class="distance-info">{distance:.2f} miles away</div>', unsafe_allow_html=True)

                        # Handle selection
                        if is_selected and phleb_id not in st.session_state.selected_phlebs:
                            st.session_state.selected_phlebs.append(phleb_id)
                        elif not is_selected and phleb_id in st.session_state.selected_phlebs:
                            st.session_state.selected_phlebs.remove(phleb_id)
                st.write(f"Selected {len(st.session_state.selected_phlebs)}/ {phlebs_needed} phlebotomist(s)")
            
            ############################### section ends ##################################
            
            # Add checkbox for routing mode selection
            use_scheduled_time = st.checkbox(
                "Use patient scheduled times for routing", 
                value=st.session_state.get('use_scheduled_time', True),  # Use cached value if available 
                help="If checked, routes will be based on patient scheduled times. If unchecked, routes will be optimized for efficiency, adjusting appointment times within a ±2 hour window."
            )
            
            # Button to run the optimization - disabled until minimum phlebs are selected
            button_disabled = len(st.session_state.selected_phlebs) < phlebs_needed and len(st.session_state.selected_phlebs) != 0

            if button_disabled:
                st.write("⚠️ Please select at least the required number of phlebotomists to enable optimization.")

            # Button to run the optimization
            if st.button("Generate Optimal Assignments"):
                # Reset flags for new generation
                st.session_state.results_from_cache = False
                
                # IMPORTANT: Clear cached map to force refresh
                if 'cached_map_html' in st.session_state:
                    del st.session_state.cached_map_html
                            
                # Reset view flags first
                if 'results_displayed' in st.session_state:
                    st.session_state.results_displayed = False
                if 'saved_files' in st.session_state:
                    del st.session_state.saved_files
                
                logger.info(f"Starting optimization for {selected_city} on {selected_date.strftime('%Y-%m-%d')} with {'scheduled' if use_scheduled_time else 'optimized'} routing")
                
                selected_phleb_df = st.session_state.phleb_df[
                    st.session_state.phleb_df["PhlebotomistID.1"].astype(str).isin(st.session_state.selected_phlebs)
                ]
                
                with st.spinner("Optimizing assignments and routes..."):
                    
                    phleb_df_to_consider = selected_phleb_df if len(selected_phleb_df) > 0 else st.session_state.phleb_df
                    
                    if len(phleb_df_to_consider) != len(selected_phleb_df):
                        st.write("No Phlebotomist was found with same city. Nearest Phleb will be considered by default.")
                        st.write("Prefer selecting phlebs to consider them for this order(s)")
                    
                    # Process the assignments with the selected routing approach
                    assignment_map, assigned_phlebs, assigned_patients = utils.process_city_assignments(
                        st.session_state.trips_df,
                        phleb_df_to_consider,
                        st.session_state.workload_df,
                        selected_date,
                        selected_city,
                        api_key,
                        use_scheduled_time,
                        redis_host=redis_host,
                        redis_port=redis_port
                    )
                    
                    if assignment_map is None:
                        logger.error(f"Failed to generate assignments for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
                        st.error("Failed to generate assignments. Please check the data.")
                    else:
                        logger.info(f"Successfully generated assignments: {len(assigned_patients)} patients to {len(assigned_phlebs)} phlebotomists")
                        
                        # Save the results to files and cache
                        saved_files = save_assignment_results_with_cache(
                            assignment_map,
                            assigned_phlebs,
                            assigned_patients,
                            selected_date,
                            selected_city,
                            use_scheduled_time
                        )
                        
                        # Store results in session state
                        st.session_state.assignment_map = assignment_map
                        st.session_state.assigned_phlebs = assigned_phlebs
                        st.session_state.assigned_patients = assigned_patients
                        st.session_state.saved_files = saved_files
                        st.session_state.use_scheduled_time = use_scheduled_time
                        st.session_state.results_from_cache = True  # Mark as having results
                        
                        # Set loaded history key
                        st.session_state.loaded_history_key = f"history:{selected_date.strftime('%Y-%m-%d')}:{selected_city}"
                        
                        st.success(f"Successfully assigned {len(assigned_patients)} patients to {len(assigned_phlebs)} phlebotomists!")
                        
            else:
                # Only log warning once per date-city combination
                if 'last_no_phlebs_needed_key' not in st.session_state or st.session_state.last_no_phlebs_needed_key != date_city_key:
                    logger.warning(f"Could not determine number of phlebotomists needed for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
                    st.session_state.last_no_phlebs_needed_key = date_city_key
                
                st.warning(f"Could not determine the number of phlebotomists needed for {selected_city} on {selected_date}.")
    
    # IMPORTANT: Always show results AFTER all parameters UI
    # By moving this to the end, we ensure it always appears below the parameter selection
    if ('results_from_cache' in st.session_state and st.session_state.results_from_cache and 
        'assigned_phlebs' in st.session_state and 'assigned_patients' in st.session_state):
        display_results()

if __name__ == "__main__":
    try:
        main()
        # Only log application completion once per run
        if 'app_completed' not in st.session_state:
            logger.info("Application execution completed successfully")
            st.session_state.app_completed = True
    except Exception as e:
        logger.error(f"Application encountered an error: {str(e)}", exc_info=True)