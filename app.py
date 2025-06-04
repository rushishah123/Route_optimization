import streamlit as st
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv
import folium
from streamlit_folium import st_folium
from LogHandler import setup_logger
import final_utils_upd as utils

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

def main():
    st.title("Phlebotomist Assignment & Route Optimizer")
    
    trips_path = "trip0804.csv"
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
    
    api_key = os.getenv("KEY")
    
    # Initialize session state variables if they don't exist
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
    # if 'comparison_metrics' not in st.session_state:
    #     st.session_state.comparison_metrics = {}
    
    # Main content area
    if st.session_state.trips_df is None:
        st.info("Please reload the page")
        logger.info("Waiting to load data")
    else:
        # Display basic stats
        col1, col2, col3 = st.columns(3)
        total_patients = len(st.session_state.trips_df)
        total_phlebotomists = len(st.session_state.phleb_df["PhlebotomistID.1"].unique())
        cities_covered = len(set(city for cities in st.session_state.date_city_map.values() for city in cities))
        
        # Only log these metrics once when they change
        if 'last_metrics' not in st.session_state or (total_patients, total_phlebotomists, cities_covered) != st.session_state.last_metrics:
            logger.info(f"Displaying stats: {total_patients} patients, {total_phlebotomists} phlebotomists, {cities_covered} cities")
            st.session_state.last_metrics = (total_patients, total_phlebotomists, cities_covered)
        
        # Assignment section
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
                
                # Use date_input widget for calendar selection
                selected_date_str = st.date_input(
                    "Select Date",
                    min_value=min_date,
                    max_value=max_date,
                    value=max_date,
                    format="YYYY-MM-DD"
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
                
                # Store selected date in session state for dynamic city filtering and only log when it changes
                if 'selected_date' not in st.session_state or st.session_state.selected_date != selected_date:
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
                selected_city = st.selectbox("Select City", options=available_cities)
                
                # Only log selected city when it changes
                if 'last_selected_city' not in st.session_state or st.session_state.last_selected_city != selected_city:
                    logger.info(f"User selected city: {selected_city}")
                    st.session_state.last_selected_city = selected_city
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
                    # if 'selected_phlebs' not in st.session_state:
                    st.session_state.selected_phlebs = []

                    # Auto-select phlebotomists in the same city during initialization
                    all_sorted_phlebs = utils.get_available_phlebotomists(st.session_state.phleb_df, selected_city, len(st.session_state.phleb_df))
                    for _, phleb in all_sorted_phlebs.iterrows():
                        if phleb.get("City") == selected_city:
                            st.session_state.selected_phlebs.append(str(phleb["PhlebotomistID.1"]))
                    
                    # st.write(st.session_state.selected_phlebs)

                    # Create a search box for phlebotomist ID
                    search_query = st.text_input("Search Phlebotomist ID", key="phleb_search")

                    # Get all available phlebotomists sorted by distance from target city
                    all_sorted_phlebs = utils.get_available_phlebotomists(st.session_state.phleb_df, selected_city, len(st.session_state.phleb_df))

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

                    # Display summary of selected phlebotomists
                    
                ############################### section ends ##################################
                
                # Add checkbox for routing mode selection
                use_scheduled_time = st.checkbox("Use patient scheduled times for routing", value=True, 
                                               help="If checked, routes will be based on patient scheduled times. If unchecked, routes will be optimized for efficiency, adjusting appointment times within a ±2 hour window.")
                
                # Button to run the optimization - disabled until minimum phlebs are selected
                button_disabled = len(st.session_state.selected_phlebs) < phlebs_needed and len(st.session_state.selected_phlebs)!=0

                if button_disabled:
                    st.write("⚠️ Please select at least the required number of phlebotomists to enable optimization.")

                # Button to run the optimization
                if st.button("Generate Optimal Assignments"):
                    
                    # Reset view flags first
                    if 'map_rendered' in st.session_state:
                        del st.session_state.map_rendered
                    if 'phlebs_displayed' in st.session_state:
                        del st.session_state.phlebs_displayed
                    if 'patients_displayed' in st.session_state:
                        del st.session_state.patients_displayed
                    if 'downloads_added' in st.session_state:
                        del st.session_state.downloads_added
                    
                    logger.info(f"Starting optimization for {selected_city} on {selected_date.strftime('%Y-%m-%d')} with {'scheduled' if use_scheduled_time else 'optimized'} routing")
                    
                    selected_phleb_df = st.session_state.phleb_df[
                        st.session_state.phleb_df["PhlebotomistID.1"].astype(str).isin(st.session_state.selected_phlebs)
                    ]
                    
                    with st.spinner("Optimizing assignments and routes..."):
                        
                        phleb_df_to_consider = selected_phleb_df if len(selected_phleb_df)>0 else st.session_state.phleb_df
                        
                        if len(phleb_df_to_consider) != len(selected_phleb_df):
                            st.write("No Phlebotomist was found with same city. Nearest Phleb will be considered by default.")
                            st.write("Prefer selecting phlebs to consider them for this order(s)")
                        
                        # Process the assignments with the selected routing approach
                        assignment_map, assigned_phlebs, assigned_patients, comparison_metrics = utils.process_city_assignments(
                            st.session_state.trips_df,
                            phleb_df_to_consider,
                            st.session_state.workload_df,
                            selected_date,
                            selected_city,
                            api_key,
                            use_scheduled_time
                        )
                        print(assigned_phlebs)
                        
                        if assignment_map is None:
                            logger.error(f"Failed to generate assignments for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
                            st.error("Failed to generate assignments. Please check the data.")
                        else:
                            logger.info(f"Successfully generated assignments: {len(assigned_patients)} patients to {len(assigned_phlebs)} phlebotomists")
                            
                            # Save the results
                            saved_files = utils.save_assignment_results(
                                assignment_map,
                                assigned_phlebs,
                                assigned_patients,
                                selected_date,
                                selected_city,
                                use_scheduled_time
                            )
                            
                            logger.info(f"Saved assignment results to files: {saved_files}")
                            
                            # Store results in session state
                            st.session_state.assignment_map = assignment_map
                            print("LINE: 335\n", assigned_phlebs)
                            st.session_state.assigned_phlebs = assigned_phlebs
                            print("LINE: 336\n", st.session_state.assigned_phlebs)
                            st.session_state.assigned_patients = assigned_patients
                            st.session_state.saved_files = saved_files
                            # Enrich patient data with phlebotomist metadata
                            enriched_patients = utils.enrich_patient_phlebotomist_fields(
                                assigned_patients,
                                st.session_state.phleb_df,
                                log_file_path="logs/phleb_enrichment_fails.log"
                            )
                            enriched_csv = utils.save_enriched_patients(
                                enriched_patients,
                                selected_date,
                                selected_city
                            )
                            st.session_state.enriched_patients = enriched_patients
                            st.session_state.enriched_csv_path = enriched_csv
                            st.session_state.results_generated = True
                            # st.session_state.comparison_metrics = comparison_metrics
                            st.session_state.use_scheduled_time = use_scheduled_time
                            
                            st.success(f"Successfully assigned {len(assigned_patients)} patients to {len(assigned_phlebs)} phlebotomists!")
            else:
                # Only log warning once per date-city combination
                if 'last_no_phlebs_needed_key' not in st.session_state or st.session_state.last_no_phlebs_needed_key != date_city_key:
                    logger.warning(f"Could not determine number of phlebotomists needed for {selected_city} on {selected_date.strftime('%Y-%m-%d')}")
                    st.session_state.last_no_phlebs_needed_key = date_city_key
                
                st.warning(f"Could not determine the number of phlebotomists needed for {selected_city} on {selected_date}.")
        
        # Display results if available
        if 'assignment_map' in st.session_state and st.session_state.assignment_map is not None:
            # Only log once when results are first displayed or regenerated
            if 'results_displayed' not in st.session_state or not st.session_state.results_displayed or st.session_state.results_generated:
                logger.info("Displaying assignment results")
                st.session_state.results_displayed = True
                # Reset the generated flag
                if 'results_generated' in st.session_state:
                    st.session_state.results_generated = False
            
            st.header("Assignment Results")
            
            # Display routing mode used
            routing_mode = "Scheduled Time" if st.session_state.use_scheduled_time else "Optimized Routing"
            st.subheader(f"Routing Mode: {routing_mode}")
            st.divider()
            
            
            # Display assignment statistics
            st.subheader("Assignment Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            patients_count = len(st.session_state.assigned_patients)
            phlebs_count = len(st.session_state.assigned_phlebs)
            
            # Get the correct total distance based on the approach used
            if st.session_state.use_scheduled_time and 'comparison_metrics' in st.session_state:
                total_distance = st.session_state.comparison_metrics['scheduled']['stats']['total_distance']
            elif 'comparison_metrics' in st.session_state:
                total_distance = st.session_state.comparison_metrics['optimized']['stats']['total_distance']
            else:
                total_distance = sum(st.session_state.assigned_phlebs["total_distance"])
            
            # Only log assignment stats when they change
            stats_key = f"{patients_count}_{phlebs_count}_{total_distance:.2f}"
            if 'last_stats_key' not in st.session_state or st.session_state.last_stats_key != stats_key:
                logger.info(f"Assignment stats: {patients_count} patients, {phlebs_count} phlebotomists, {total_distance:.2f} miles total distance")
                st.session_state.last_stats_key = stats_key
            
            with col1:
                st.metric("Patients Assigned", patients_count)
            
            with col2:
                st.metric("Phlebotomists Used", phlebs_count)
            
            with col3:
                # Calculate total distance
                st.metric("Total Route Distance", f"{total_distance:.2f} miles")
            
            # Display the map
            st.subheader("Route Map")
            
            # Use a container to avoid re-rendering
            map_container = st.container()
            with map_container:
                if 'map_rendered' not in st.session_state:
                    html_temp = st.session_state.assignment_map.get_root().render()
                    st.components.v1.html(html_temp, height=600)
                    logger.info("Rendered route map in UI")
                    st.session_state.map_rendered = True
            
            # Display phlebotomist assignments
            st.subheader("Phlebotomist Assignments")
            phleb_display = st.session_state.assigned_phlebs.copy()
            print("*******"*5)
            # print(type(phleb_display["assigned_patients"][0]))
            print(type(phleb_display["assigned_patients"].iloc[0]))

            # Convert the list to a string for display
            phleb_display["assigned_patients"] = phleb_display["assigned_patients"].apply(lambda x: f"{len(x)}")
            print(phleb_display["assigned_patients"])
            phleb_display = phleb_display[[
                "PhlebotomistID.1", "current_workload", "total_distance", "assigned_patients"
            ]].rename(columns={
                "PhlebotomistID.1": "Phlebotomist ID", 
                "current_workload": "Workload Points",
                "total_distance": "Route Distance (miles)",
                "assigned_patients": "Patients Assigned"
            })
            
            # Use a container for phlebotomist table to avoid re-rendering
            phleb_container = st.container()
            with phleb_container:
                if 'phlebs_displayed' not in st.session_state:
                    st.dataframe(phleb_display)
                    logger.info(f"Displayed phlebotomist assignments table with {len(phleb_display)} rows")
                    st.session_state.phlebs_displayed = True
            
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
                
            patient_display = st.session_state.assigned_patients[display_columns].rename(columns=column_renames)
            
            # Use a container for patient table to avoid re-rendering
            patient_container = st.container()
            with patient_container:
                if 'patients_displayed' not in st.session_state:
                    st.dataframe(patient_display)
                    logger.info(f"Displayed patient assignments table with {len(patient_display)} rows")
                    st.session_state.patients_displayed = True
            
            # Download links for the generated files
            st.subheader("Download Results")
            col1, col2, col3 = st.columns(3)
            
            # Use a container for download buttons to avoid re-rendering
            downloads_container = st.container()
            with downloads_container:
                if 'downloads_added' not in st.session_state:
                    with col1:
                        map_path = st.session_state.saved_files["map"]
                        with open(map_path, "rb") as file:
                            st.download_button(
                                "Download Map (HTML)",
                                file,
                                file_name=os.path.basename(map_path),
                                mime="text/html"
                            )
                    
                    with col2:
                        phlebs_path = st.session_state.saved_files["phlebs"]
                        with open(phlebs_path, "rb") as file:
                            st.download_button(
                                "Download Phlebotomist Assignments (CSV)",
                                file,
                                file_name=os.path.basename(phlebs_path),
                                mime="text/csv"
                            )
                    
                    with col3:
                        patients_path = st.session_state.saved_files["patients"]
                        with open(patients_path, "rb") as file:
                            st.download_button(
                                "Download Patient Assignments (CSV)",
                                file,
                                file_name=os.path.basename(patients_path),
                                mime="text/csv"
                            )

                    if 'enriched_csv_path' in st.session_state:
                        with col4:
                            enriched_path = st.session_state.enriched_csv_path
                            with open(enriched_path, "rb") as file:
                                st.download_button(
                                    "Download Enriched Patients (CSV)",
                                    file,
                                    file_name=os.path.basename(enriched_path),
                                    mime="text/csv"
                                )

                    logger.info("Added download buttons for result files")
                    st.session_state.downloads_added = True

            if 'enriched_patients' in st.session_state:
                if st.button("✅ Verified"):
                    success, msg = utils.sync_patients_to_backend(
                        "http://localhost:8000/api/patients/bulk_update",
                        st.session_state.enriched_patients
                    )
                    if success:
                        st.success("Patients synced successfully")
                    else:
                        st.error(f"Failed to sync patients: {msg}")
                        os.makedirs("logs", exist_ok=True)
                        with open("logs/db_sync_errors.log", "a") as f:
                            f.write(f"{datetime.now()}: {msg}\n")


if __name__ == "__main__":
    try:
        main()
        # Only log application completion once per run
        if 'app_completed' not in st.session_state:
            logger.info("Application execution completed successfully")
            st.session_state.app_completed = True
    except Exception as e:
        logger.error(f"Application encountered an error: {str(e)}", exc_info=True)
