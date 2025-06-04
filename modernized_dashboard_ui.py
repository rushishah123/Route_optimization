import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from LogHandler import setup_logger

es_config = {
    "es_host": "localhost",
    "es_port": 9200,
    "index": "dashboard-logs"
}

# Only set up the logger once at app initialization
if 'logger' not in st.session_state:
    st.session_state.logger = setup_logger(
        log_file_prefix="dashboard",
        es_config=es_config
    )
    st.session_state.logger.info("Application started")

logger = st.session_state.logger

# Page configuration
st.set_page_config(layout="wide", page_title="Phlebotomist Mapping", page_icon="💉")
logger.info("Dashboard Started")

# Custom CSS for modern, immersive UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Poppins:wght@400;500;600;700&display=swap');
    
    /* Global Styles & Typography */
    * {
        font-family: 'Inter', sans-serif;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Poppins', sans-serif;
    }
    
    .main-header {
        font-size: 2.8rem;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        font-weight: 700;
        position: relative;
    }
    
    .main-header::after {
        content: "";
        position: absolute;
        bottom: 0;
        left: 25%;
        right: 25%;
        height: 4px;
        border-radius: 2px;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
    }
    
    .sub-header {
        color: #2980b9;
        font-size: 1.8rem;
        padding-top: 1.2rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
        position: relative;
        display: inline-block;
    }
    
    .sub-header::after {
        content: "";
        position: absolute;
        bottom: -5px;
        left: 0;
        width: 40px;
        height: 4px;
        border-radius: 2px;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
    }
    
    /* Modern Card Design */
    .stat-card {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        padding: 1.8rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        margin-bottom: 1.5rem;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        border: 1px solid rgba(255, 255, 255, 0.18);
        position: relative;
        overflow: hidden;
    }
    
    .stat-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 5px;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
    }
    
    .stat-card:hover {
        transform: translateY(-10px);
        box-shadow: 0 15px 35px rgba(58, 123, 213, 0.2);
    }
    
    .stat-value {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin: 10px 0;
        font-family: 'Poppins', sans-serif;
    }
    
    .stat-label {
        color: #4a5568;
        font-size: 1.1rem;
        text-align: center;
        font-weight: 600;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Modern Filter Section */
    .filter-section {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        padding: 1.8rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        position: relative;
        overflow: hidden;
    }
    
    .filter-section::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 5px;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
    }
    
    .stDateInput, .stSelectbox {
        background-color: white !important;
        border-radius: 12px !important;
        padding: 8px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
        border: 1px solid #e6e9ef !important;
        transition: all 0.3s ease !important;
    }
    
    .stDateInput:hover, .stSelectbox:hover {
        border: 1px solid #3a7bd5 !important;
        box-shadow: 0 4px 15px rgba(58, 123, 213, 0.15) !important;
        transform: translateY(-2px) !important;
    }
    
    /* Glossy Data Table */
    .data-table {
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.18);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(255, 255, 255, 0.7);
        padding: 0.5rem;
        border-radius: 50px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 50px;
        padding: 10px 20px;
        border: none;
        color: #4a5568;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
        color: white !important;
        box-shadow: 0 4px 15px rgba(58, 123, 213, 0.25);
    }
    
    .stTabs [data-baseweb="tab-panel"] {
        background-color: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        margin-top: 1rem;
    }
    
    /* Filter label */
    .filter-label {
        font-weight: 600;
        color: #4a5568;
        margin-bottom: 8px;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Button styling */
    .stButton>button {
        width: 100%;
        border-radius: 50px !important;
        font-weight: 600 !important;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff) !important;
        color: white !important;
        border: none !important;
        padding: 10px 20px !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        box-shadow: 0 10px 20px rgba(58, 123, 213, 0.25) !important;
    }
    
    .stButton>button:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 15px 30px rgba(58, 123, 213, 0.4) !important;
    }
    
    /* Responsive spacing */
    div[data-testid="stVerticalBlock"] {
        gap: 25px !important;
    }
    
    div[data-testid="stHorizontalBlock"] {
        gap: 20px !important;
    }
    
    /* Page background with subtle pattern */
    .main {
        background: linear-gradient(120deg, #f8f9fa, #e6f3ff);
    }
    
    /* Custom info box */
    .custom-info-box {
        background: rgba(58, 123, 213, 0.08);
        border-left: 4px solid #3a7bd5;
        padding: 15px 20px;
        border-radius: 10px;
        margin: 15px 0;
    }
    
    /* Animated pulse for important elements */
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(58, 123, 213, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(58, 123, 213, 0); }
        100% { box-shadow: 0 0 0 0 rgba(58, 123, 213, 0); }
    }
    
    .pulse-animation {
        animation: pulse 2s infinite;
    }
    
    /* Hover effects for interactive elements */
    .interactive-element {
        transition: all 0.3s ease;
    }
    
    .interactive-element:hover {
        transform: scale(1.03);
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(45deg, #3a7bd5, #00d2ff);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(45deg, #2d62aa, #00b8e0);
    }
    
    /* Add page background */
    .stApp {
        background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%233a7bd5' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
        background-color: #f8fbff;
    }
    
    /* Footer styling */
    .footer {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        padding: 1.5rem;
        border-radius: 20px;
        margin-top: 2rem;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        position: relative;
        overflow: hidden;
    }
    
    .footer::before {
        content: "";
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 5px;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff);
    }
    
    /* Download button */
    .stDownloadButton>button {
        width: auto !important;
        background: linear-gradient(90deg, #3a7bd5, #00d2ff) !important;
        color: white !important;
        border-radius: 50px !important;
        font-weight: 500 !important;
        border: none !important;
        padding: 8px 20px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(58, 123, 213, 0.25) !important;
    }
    
    .stDownloadButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(58, 123, 213, 0.4) !important;
    }
    
    /* Chart styling */
    .chart-container {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        transition: all 0.3s ease;
    }
    
    .chart-container:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 35px rgba(58, 123, 213, 0.15);
    }
    
    /* Map container */
    .map-container {
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.18);
        transition: all 0.3s ease;
    }
    
    .map-container:hover {
        box-shadow: 0 20px 40px rgba(58, 123, 213, 0.2);
    }
    
    /* Toast notifications */
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    .toast-notification {
        position: fixed;
        top: 20px;
        right: 20px;
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
        border-left: 5px solid #3a7bd5;
        animation: slideInRight 0.3s forwards;
        z-index: 9999;
        max-width: 300px;
    }
</style>
""", unsafe_allow_html=True)

# Load the data
@st.cache_data
def load_data():
    logger.info("Loading data...")
    data = pd.read_csv('Req.csv')

    # Convert date columns to datetime
    logger.debug("Converting date columns to datetime format")
    data['ScheduledDtm'] = pd.to_datetime(data['ScheduledDtm'])

    # Handle NaN values
    logger.debug("Handling missing values in dataset")
    data.fillna({
        'ServiceAreaDescription': 'Unknown',
        'City': 'Unknown',
        'PatientLatitude': 0,
        'PatientLongitude': 0,
        'PhlebotomistLatitude': 0,
        'PhlebotomistLongitude': 0,
        'PhlebotomistName': 'Unknown'
    }, inplace=True)

    # Drop rows with critical missing information
    logger.info(f"Data loaded successfully. {len(data)} records found.")
    data.dropna(subset=['ScheduledDtm', 'PatientLatitude', 'PatientLongitude',
                         'PhlebotomistLatitude', 'PhlebotomistLongitude'], inplace=True)

    return data

data = load_data()

# Title with animated gradient
st.markdown("<h1 class='main-header'>Phlebotomist & Patient Mapping</h1>", unsafe_allow_html=True)

# Modern description
st.markdown("""
<div class="custom-info-box" style="text-align: center; background: rgba(58, 123, 213, 0.05); border: none; border-radius: 20px; padding: 20px; margin-bottom: 30px;">
    <p style="margin: 0; font-size: 1.1rem; color: #4a5568; line-height: 1.6;">
        Welcome to the interactive phlebotomist mapping dashboard. Visualize appointment distributions, 
        optimize routes, and enhance patient service with our advanced analytics.
    </p>
</div>
""", unsafe_allow_html=True)

# Initialize session state for tracking if reset was clicked
if 'reset_filters_clicked' not in st.session_state:
    st.session_state.reset_filters_clicked = False

# Get min and max dates from data for the date picker (outside of widget context)
min_date = data['ScheduledDtm'].min().date()
max_date = data['ScheduledDtm'].max().date()
default_date = min(datetime.now().date(), max_date)

# If reset was clicked, initialize default values for all widgets
if st.session_state.reset_filters_clicked:
    date_option = default_date
    selected_service_area = 'All'
    selected_city = 'All'
    selected_display = 'Both'
    # Reset the flag
    st.session_state.reset_filters_clicked = False
else:
    # Use existing session state values if available
    date_option = st.session_state.get('date_picker', default_date)
    selected_service_area = st.session_state.get('service_area_selector', 'All')
    selected_city = st.session_state.get('city_selector', 'All')
    selected_display = st.session_state.get('display_filter', 'Both')

# Create a section for filters with better styling
st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
st.markdown("""
<div style="display: flex; align-items: center; margin-bottom: 20px;">
    <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(45deg, #3a7bd5, #00d2ff); 
                display: flex; align-items: center; justify-content: center; margin-right: 15px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M9 5H7C5.89543 5 5 5.89543 5 7V19C5 20.1046 5.89543 21 7 21H17C18.1046 21 19 20.1046 19 19V7C19 5.89543 18.1046 5 17 5H15M9 5C9 6.10457 9.89543 7 11 7H13C14.1046 7 15 6.10457 15 5M9 5C9 3.89543 9.89543 3 11 3H13C14.1046 3 15 3.89543 15 5" 
                  stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M9 12H15" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M9 16H15" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </div>
    <h3 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.3rem;">Smart Filters</h3>
</div>
""", unsafe_allow_html=True)

# Create a horizontal layout for input controls
col1, col2, col3, col4 = st.columns(4)

# Date selector in first column with better styling
with col1:
    st.markdown("<p class='filter-label'>Select Date</p>", unsafe_allow_html=True)
    date_option = st.date_input("", date_option,
                              min_value=min_date, max_value=max_date,
                              key="date_picker", label_visibility="collapsed")
    logger.info(f"Date filter applied: {date_option}")

# Filter data based on selected date
date_filtered_data = data[data['ScheduledDtm'].dt.date == date_option]

# Service Area selector in second column
with col2:
    st.markdown("<p class='filter-label'>Select Service Area</p>", unsafe_allow_html=True)
    service_areas = ['All'] + sorted(date_filtered_data['ServiceAreaDescription'].unique().tolist())
    selected_service_area = st.selectbox("", service_areas, key="service_area_selector", 
                                        index=service_areas.index(selected_service_area) if selected_service_area in service_areas else 0,
                                        label_visibility="collapsed")
    logger.info(f"Service area filter applied: {selected_service_area}")

# City selector in third column
with col3:
    st.markdown("<p class='filter-label'>Select City</p>", unsafe_allow_html=True)
    if selected_service_area == 'All':
        city_data = date_filtered_data
    else:
        city_data = date_filtered_data[date_filtered_data['ServiceAreaDescription'] == selected_service_area]

    cities = ['All'] + sorted(city_data['City'].unique().tolist())
    selected_city = st.selectbox("", cities, key="city_selector", 
                               index=cities.index(selected_city) if selected_city in cities else 0,
                               label_visibility="collapsed")
    logger.info(f"City filter applied: {selected_city}")

# Display filter in fourth column
with col4:
    st.markdown("<p class='filter-label'>Display on Map</p>", unsafe_allow_html=True)
    display_options = ["Both", "Patients Only", "Phlebotomists Only"]
    selected_display = st.selectbox("", display_options, key="display_filter", 
                                  index=display_options.index(selected_display) if selected_display in display_options else 0,
                                  label_visibility="collapsed")
    logger.info(f"Display filter applied: {selected_display}")

# Define reset button callback
def on_reset_filters():
    st.session_state.reset_filters_clicked = True
    logger.info("User reset all filters to default values")

# Add a button to reset filters
col1, col2, col3 = st.columns([4, 1, 4])
with col2:
    reset_filters = st.button("Reset Filters", on_click=on_reset_filters, 
                            help="Reset all filters to their default values")

st.markdown("</div>", unsafe_allow_html=True)

# Apply all filters
if selected_service_area != 'All':
    filtered_data = date_filtered_data[date_filtered_data['ServiceAreaDescription'] == selected_service_area]
else:
    filtered_data = date_filtered_data

if selected_city != 'All':
    filtered_data = filtered_data[filtered_data['City'] == selected_city]

# Get all available phlebotomists for the selected date
phlebotomists_df = date_filtered_data[
    ['PhlebotomistName', 'ServiceAreaDescription', 'City',
     'PhlebotomistLatitude', 'PhlebotomistLongitude']
].drop_duplicates()

# Apply service area and city filters to phlebotomists
if selected_service_area != 'All':
    phlebotomists_df = phlebotomists_df[phlebotomists_df['ServiceAreaDescription'] == selected_service_area]
if selected_city != 'All':
    phlebotomists_df = phlebotomists_df[phlebotomists_df['City'] == selected_city]
logger.info(f"Filters applied - Date: {date_option}, Service Area: {selected_service_area}, City: {selected_city}, Display: {selected_display}")

# Dashboard Stats - Visual Cards
st.markdown("<h2 class='sub-header'>Key Metrics</h2>", unsafe_allow_html=True)

# Summary stats in card format
col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)

with col_stats1:
    st.markdown(f"""
    <div class='stat-card pulse-animation'>
        <div style="position: absolute; top: 10px; right: 10px; opacity: 0.2;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M17 21V19C17 16.7909 15.2091 15 13 15H5C2.79086 15 1 16.7909 1 19V21" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M9 11C11.2091 11 13 9.20914 13 7C13 4.79086 11.2091 3 9 3C6.79086 3 5 4.79086 5 7C5 9.20914 6.79086 11 9 11Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M23 21V19C22.9986 17.1771 21.765 15.5857 20 15.13" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M16 3.13C17.7699 3.58137 19.0078 5.17755 19.0078 7.005C19.0078 8.83245 17.7699 10.4286 16 10.88" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <p class='stat-label'>Total Patients</p>
        <p class='stat-value'>{len(filtered_data)}</p>
        <p style="text-align: center; color: #718096; font-size: 0.9rem; margin-top: 5px;">
            <span style="display: inline-flex; align-items: center;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 5px;">
                    <path d="M3 12L5 10M5 10L12 3L19 10M5 10V21H19V10M19 10L21 12" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Scheduled for {date_option.strftime('%b %d, %Y')}
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

with col_stats2:
    st.markdown(f"""
    <div class='stat-card'>
        <div style="position: absolute; top: 10px; right: 10px; opacity: 0.2;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M3 9L12 2L21 9V20C21 20.5304 20.7893 21.0391 20.4142 21.4142C20.0391 21.7893 19.5304 22 19 22H5C4.46957 22 3.96086 21.7893 3.58579 21.4142C3.21071 21.0391 3 20.5304 3 20V9Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M9 22V12H15V22" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <p class='stat-label'>Available Phlebotomists</p>
        <p class='stat-value'>{len(phlebotomists_df)}</p>
        <p style="text-align: center; color: #718096; font-size: 0.9rem; margin-top: 5px;">
            <span style="display: inline-flex; align-items: center;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 5px;">
                    <path d="M16 21V19C16 16.7909 14.2091 15 12 15H5C2.79086 15 1 16.7909 1 19V21" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M8.5 11C10.7091 11 12.5 9.20914 12.5 7C12.5 4.79086 10.7091 3 8.5 3C6.29086 3 4.5 4.79086 4.5 7C4.5 9.20914 6.29086 11 8.5 11Z" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Ready for assignments
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

with col_stats3:
    # Calculate average patients per phlebotomist
    if len(phlebotomists_df) > 0:
        avg_patients = round(len(filtered_data) / len(phlebotomists_df), 1)
    else:
        avg_patients = 0

    st.markdown(f"""
    <div class='stat-card'>
        <div style="position: absolute; top: 10px; right: 10px; opacity: 0.2;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M16 4H18C18.5304 4 19.0391 4.21071 19.4142 4.58579C19.7893 4.96086 20 5.46957 20 6V20C20 20.5304 19.7893 21.0391 19.4142 21.4142C19.0391 21.7893 18.5304 22 18 22H6C5.46957 22 4.96086 21.7893 4.58579 21.4142C4.21071 21.0391 4 20.5304 4 20V6C4 5.46957 4.21071 4.96086 4.58579 4.58579C4.96086 4.21071 5.46957 4 6 4H8" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M15 2H9C8.44772 2 8 2.44772 8 3V5C8 5.55228 8.44772 6 9 6H15C15.5523 6 16 5.55228 16 5V3C16 2.44772 15.5523 2 15 2Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 11H16" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 16H16" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M8 11H8.01" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M8 16H8.01" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <p class='stat-label'>Avg. Patients/Phlebotomist</p>
        <p class='stat-value'>{avg_patients}</p>
        <p style="text-align: center; color: #718096; font-size: 0.9rem; margin-top: 5px;">
            <span style="display: inline-flex; align-items: center;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 5px;">
                    <path d="M3.34277 11.0181L5.22793 12.3978C6.1215 12.2683 6.85428 11.535 6.98305 10.6414L5.09789 9.26172C4.20432 9.39119 3.47154 10.1245 3.34277 11.0181Z" fill="none" stroke="#718096" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M6.41797 8.78739L8.10005 9.84021" stroke="#718096" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M9 14.5H21" stroke="#718096" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M9 18.5H21" stroke="#718096" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M15 6.5L16.5 9.5L20 8L18.5 5L15 6.5Z" stroke="#718096" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Workload distribution
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

with col_stats4:
    # Get hourly distribution
    if not filtered_data.empty:
        hour_with_most_appointments = filtered_data['ScheduledDtm'].dt.hour.mode()[0]
        peak_hour_str = f"{hour_with_most_appointments:02d}:00-{hour_with_most_appointments+1:02d}:00"
    else:
        peak_hour_str = "N/A"

    st.markdown(f"""
    <div class='stat-card'>
        <div style="position: absolute; top: 10px; right: 10px; opacity: 0.2;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 6V12L16 14" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <p class='stat-label'>Peak Appointment Hour</p>
        <p class='stat-value'>{peak_hour_str}</p>
        <p style="text-align: center; color: #718096; font-size: 0.9rem; margin-top: 5px;">
            <span style="display: inline-flex; align-items: center;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 5px;">
                    <path d="M12 8V12L15 15" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M3.05078 11.0001C3.27441 7.10656 6.40612 4.0001 10.321 4.0001C13.5601 4.0001 16.3341 6.10005 17.3281 9.00007H19.9999C21.1045 9.00007 22 9.89557 22 11.0001C22 12.1046 21.1045 13.0001 19.9999 13.0001H17.3281C16.3341 15.9001 13.5601 18.0001 10.321 18.0001C6.40612 18.0001 3.27441 14.8936 3.05078 11.0001Z" stroke="#718096" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Highest activity time
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

# Create map with modern styling
st.markdown("<div class='map-container'>", unsafe_allow_html=True)
st.markdown("""
<div style="display: flex; align-items: center; margin-bottom: 20px; padding: 0 20px;">
    <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(45deg, #3a7bd5, #00d2ff); 
                display: flex; align-items: center; justify-content: center; margin-right: 15px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 10C21 17 12 23 12 23C12 23 3 17 3 10C3 7.61305 3.94821 5.32387 5.63604 3.63604C7.32387 1.94821 9.61305 1 12 1C14.3869 1 16.6761 1.94821 18.364 3.63604C20.0518 5.32387 21 7.61305 21 10Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 13C13.6569 13 15 11.6569 15 10C15 8.34315 13.6569 7 12 7C10.3431 7 9 8.34315 9 10C9 11.6569 10.3431 13 12 13Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </div>
    <h2 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.5rem;">Interactive Map Visualization</h2>
</div>
""", unsafe_allow_html=True)

# Create a map centered around the mean latitude and longitude of filtered data
if not filtered_data.empty:
    logger.info(f"Displaying stats for {len(filtered_data)} patients and {len(phlebotomists_df)} phlebotomists")
    map_center = [
        filtered_data['PatientLatitude'].mean(),
        filtered_data['PatientLongitude'].mean()
    ]
    zoom_level = 10
else:
    logger.warning("No data available for the selected filters")
    # Default center if no data
    map_center = [39.8283, -98.5795]  # Center of the US
    zoom_level = 4

m = folium.Map(location=map_center, zoom_start=zoom_level, tiles='CartoDB positron')

# Create marker clusters for better organization
from folium.plugins import MarkerCluster
patient_cluster = MarkerCluster(name="Patients").add_to(m)
assigned_phlebotomist_cluster = MarkerCluster(name="Assigned Phlebotomists").add_to(m)
available_phlebotomist_cluster = MarkerCluster(name="Available Phlebotomists").add_to(m)

# Add markers based on display filter
if selected_display in ["Both", "Patients Only"]:
    # Add patient markers
    for _, row in filtered_data.iterrows():
        folium.Marker(
            location=[row['PatientLatitude'], row['PatientLongitude']],
            popup=f"""
            <div style="width: 240px; font-family: 'Poppins', sans-serif; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(90deg, #e74c3c, #ff7675); padding: 10px 15px; color: white;">
                    <h4 style="margin: 0; font-size: 16px;">Patient Details</h4>
                </div>
                <div style="padding: 15px; background: white;">
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Service Area:</span> 
                        <span style="color: #4a5568;">{row['ServiceAreaDescription']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">City:</span> 
                        <span style="color: #4a5568;">{row['City']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Appointment:</span> 
                        <span style="color: #4a5568;">{row['ScheduledDtm'].strftime('%Y-%m-%d %H:%M')}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Assigned to:</span> 
                        <span style="color: #4a5568;">{row['PhlebotomistName']}</span>
                    </p>
                </div>
            </div>
            """,
            icon=folium.Icon(color='red', icon='user', prefix='fa'),
            tooltip="Patient"
        ).add_to(patient_cluster)

if selected_display in ["Both", "Phlebotomists Only"]:
    # Add assigned phlebotomist markers
    for _, row in filtered_data.iterrows():
        folium.Marker(
            location=[row['PhlebotomistLatitude'], row['PhlebotomistLongitude']],
            popup=f"""
            <div style="width: 240px; font-family: 'Poppins', sans-serif; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(90deg, #3a7bd5, #00d2ff); padding: 10px 15px; color: white;">
                    <h4 style="margin: 0; font-size: 16px;">Assigned Phlebotomist</h4>
                </div>
                <div style="padding: 15px; background: white;">
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Name:</span> 
                        <span style="color: #4a5568;">{row['PhlebotomistName']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Service Area:</span> 
                        <span style="color: #4a5568;">{row['ServiceAreaDescription']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">City:</span> 
                        <span style="color: #4a5568;">{row['City']}</span>
                    </p>
                </div>
            </div>
            """,
            icon=folium.Icon(color='blue', icon='user-md', prefix='fa'),
            tooltip=f"Assigned: {row['PhlebotomistName']}"
        ).add_to(assigned_phlebotomist_cluster)

    # Add markers for all available phlebotomists
    for _, row in phlebotomists_df.iterrows():
        folium.Marker(
            location=[row['PhlebotomistLatitude'], row['PhlebotomistLongitude']],
            popup=f"""
            <div style="width: 240px; font-family: 'Poppins', sans-serif; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(90deg, #27ae60, #2ecc71); padding: 10px 15px; color: white;">
                    <h4 style="margin: 0; font-size: 16px;">Available Phlebotomist</h4>
                </div>
                <div style="padding: 15px; background: white;">
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Name:</span> 
                        <span style="color: #4a5568;">{row['PhlebotomistName']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">Service Area:</span> 
                        <span style="color: #4a5568;">{row['ServiceAreaDescription']}</span>
                    </p>
                    <p style="margin: 5px 0; display: flex; align-items: center;">
                        <span style="font-weight: 600; color: #2d3748; width: 100px;">City:</span> 
                        <span style="color: #4a5568;">{row['City']}</span>
                    </p>
                </div>
            </div>
            """,
            icon=folium.Icon(color='green', icon='plus', prefix='fa'),
            tooltip=f"Available: {row['PhlebotomistName']}"
        ).add_to(available_phlebotomist_cluster)

# Enhanced legend with more detailed information and styling
legend_html = '''
<div style="position: fixed;
            bottom: 50px; right: 50px; width: 280px;
            border:none; z-index:9999; font-size:14px;
            background-color:white;
            padding: 20px;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            font-family: 'Inter', sans-serif;">
    <div style="text-align:center; margin-bottom: 15px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;">
        <strong style="font-size: 18px; background: linear-gradient(90deg, #3a7bd5, #00d2ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Map Legend</strong>
    </div>
    <div style="margin-bottom: 15px; display: flex; align-items: center;">
        <div style="width: 40px; height: 40px; border-radius: 50%; background: rgba(231, 76, 60, 0.1); display: flex; align-items: center; justify-content: center; margin-right: 15px;">
            <i class="fa fa-user" style="color:#e74c3c;"></i>
        </div>
        <div>
            <strong style="color: #e74c3c; font-size: 15px; display: block; margin-bottom: 3px;">Patient</strong>
            <div style="font-size: 12px; color: #718096;">Scheduled appointments</div>
        </div>
    </div>
    <div style="margin-bottom: 15px; display: flex; align-items: center;">
        <div style="width: 40px; height: 40px; border-radius: 50%; background: rgba(58, 123, 213, 0.1); display: flex; align-items: center; justify-content: center; margin-right: 15px;">
            <i class="fa fa-user-md" style="color:#3a7bd5;"></i>
        </div>
        <div>
            <strong style="color: #3a7bd5; font-size: 15px; display: block; margin-bottom: 3px;">Assigned</strong>
            <div style="font-size: 12px; color: #718096;">With patient visits</div>
        </div>
    </div>
    <div style="margin-bottom: 15px; display: flex; align-items: center;">
        <div style="width: 40px; height: 40px; border-radius: 50%; background: rgba(39, 174, 96, 0.1); display: flex; align-items: center; justify-content: center; margin-right: 15px;">
            <i class="fa fa-plus" style="color:#27ae60;"></i>
        </div>
        <div>
            <strong style="color: #27ae60; font-size: 15px; display: block; margin-bottom: 3px;">Available</strong>
            <div style="font-size: 12px; color: #718096;">Ready for assignments</div>
        </div>
    </div>
    <div style="font-size: 12px; margin-top: 15px; border-top: 1px solid #f1f5f9; padding-top: 10px; text-align: center; color: #a0aec0;">
        Click on any marker for detailed information
    </div>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

# Add Layer Control
folium.LayerControl().add_to(m)

# Display the map with custom styling
folium_static(m, width=1200, height=600)
st.markdown("</div>", unsafe_allow_html=True)

# Create charts for additional insights
st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="display: flex; align-items: center; margin-bottom: 20px;">
    <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(45deg, #3a7bd5, #00d2ff); 
                display: flex; align-items: center; justify-content: center; margin-right: 15px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 20V10" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 20V4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M6 20V14" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </div>
    <h2 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.5rem;">Advanced Analytics</h2>
</div>
""", unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
    if not filtered_data.empty:
        # Create hourly appointments chart
        hour_counts = filtered_data['ScheduledDtm'].dt.hour.value_counts().sort_index()
        hours = hour_counts.index
        counts = hour_counts.values

        # Format hours as strings with AM/PM
        hour_labels = [f"{h:02d}:00" for h in hours]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=hour_labels,
            y=counts,
            marker=dict(
                color=counts,
                colorscale=['#c1dbff', '#3a7bd5', '#00d2ff'],
                showscale=False
            ),
            hovertemplate='Hour: %{x}<br>Appointments: %{y}<extra></extra>'
        ))

        fig.update_layout(
            title={
                'text': 'Appointments by Hour',
                'y':0.95,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': dict(size=20, color='#4a5568', family="Poppins, sans-serif")
            },
            xaxis_title='Hour of Day',
            yaxis_title='Number of Appointments',
            height=400,
            margin=dict(l=40, r=40, t=70, b=40),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter, sans-serif", color="#4a5568"),
            hoverlabel=dict(
                bgcolor="white",
                font_size=14,
                font_family="Inter, sans-serif"
            ),
            xaxis=dict(
                showgrid=True,
                gridcolor='#f7fafc',
                tickfont=dict(
                    family='Inter, sans-serif',
                    size=12,
                    color='#4a5568'
                )
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#f7fafc',
                tickfont=dict(
                    family='Inter, sans-serif',
                    size=12,
                    color='#4a5568'
                )
            )
        )

        # Add hover effects
        fig.update_traces(
            marker_line_color='#3a7bd5',
            marker_line_width=1,
            opacity=0.8
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div class="custom-info-box">
            <p style="margin: 0; font-size: 15px; text-align: center; padding: 30px 0;">
                <svg width="50" height="50" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 15px;">
                    <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 8V12" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 16H12.01" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg><br>
                No data available for the selected filters to show hourly distribution.
            </p>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with chart_col2:
    st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
    if not filtered_data.empty:
        # Count appointments per phlebotomist
        phlebotomist_counts = filtered_data['PhlebotomistName'].value_counts()

        # Get top 8 phlebotomists and group the rest as "Others"
        if len(phlebotomist_counts) > 8:
            top_phlebotomists = phlebotomist_counts.nlargest(7)
            others_count = phlebotomist_counts[7:].sum()
            top_phlebotomists['Others'] = others_count
            phlebotomist_counts = top_phlebotomists

        fig = go.Figure()
        fig.add_trace(go.Pie(
            labels=phlebotomist_counts.index,
            values=phlebotomist_counts.values,
            textinfo='percent',
            insidetextorientation='radial',
            marker=dict(
                colors=px.colors.sequential.Blues_r,
                line=dict(color='#ffffff', width=2)
            ),
            hoverinfo='label+value+percent',
            hole=0.5
        ))

        fig.update_layout(
            title={
                'text': 'Phlebotomist Workload Distribution',
                'y':0.95,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': dict(size=20, color='#4a5568', family="Poppins, sans-serif")
            },
            height=400,
            margin=dict(l=40, r=40, t=70, b=40),
            annotations=[dict(text='Workload', x=0.5, y=0.5, font_size=18, font_family="Poppins, sans-serif", showarrow=False)],
            font=dict(family="Inter, sans-serif", color="#4a5568"),
            paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5,
                font=dict(family="Inter, sans-serif", size=12, color="#4a5568")
            ),
            hoverlabel=dict(
                bgcolor="white",
                font_size=14,
                font_family="Inter, sans-serif"
            )
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div class="custom-info-box">
            <p style="margin: 0; font-size: 15px; text-align: center; padding: 30px 0;">
                <svg width="50" height="50" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 15px;">
                    <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 8V12" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 16H12.01" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg><br>
                No data available for the selected filters to show phlebotomist distribution.
            </p>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Create tabs for detailed data tables with improved styling
st.markdown("""
<div style="margin-top: 40px; margin-bottom: 20px;">
    <div style="display: flex; align-items: center;">
        <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(45deg, #3a7bd5, #00d2ff); 
                    display: flex; align-items: center; justify-content: center; margin-right: 15px;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 3H5C3.89543 3 3 3.89543 3 5V9C3 10.1046 3.89543 11 5 11H9C10.1046 11 11 10.1046 11 9V5C11 3.89543 10.1046 3 9 3Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M9 13H5C3.89543 13 3 13.8954 3 15V19C3 20.1046 3.89543 21 5 21H9C10.1046 21 11 20.1046 11 19V15C11 13.8954 10.1046 13 9 13Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M19 3H15C13.8954 3 13 3.89543 13 5V9C13 10.1046 13.8954 11 15 11H19C20.1046 11 21 10.1046 21 9V5C21 3.89543 20.1046 3 19 3Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M19 13H15C13.8954 13 13 13.8954 13 15V19C13 20.1046 13.8954 21 15 21H19C20.1046 21 21 20.1046 21 19V15C21 13.8954 20.1046 13 19 13Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <h2 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.5rem;">Detailed Information</h2>
    </div>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📋 Phlebotomists", "👥 Patients"])

with tab1:
    st.markdown("""
    <div style="display: flex; align-items: center; margin-bottom: 20px;">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 10px;">
            <path d="M17 21V19C17 16.7909 15.2091 15 13 15H5C2.79086 15 1 16.7909 1 19V21" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M9 11C11.2091 11 13 9.20914 13 7C13 4.79086 11.2091 3 9 3C6.79086 3 5 4.79086 5 7C5 9.20914 6.79086 11 9 11Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M23 21V19C22.9986 17.1771 21.765 15.5857 20 15.13" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M16 3.13C17.7699 3.58137 19.0078 5.17755 19.0078 7.005C19.0078 8.83245 17.7699 10.4286 16 10.88" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <h3 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.2rem;">Phlebotomist Directory</h3>
    </div>
    """, unsafe_allow_html=True)

    # Enhanced phlebotomist dataframe
    phlebotomist_display = phlebotomists_df[['PhlebotomistName', 'ServiceAreaDescription', 'City']]

    # Add appointment count column
    phlebotomist_count = filtered_data['PhlebotomistName'].value_counts().reset_index()
    phlebotomist_count.columns = ['PhlebotomistName', 'AppointmentCount']

    phlebotomist_display = pd.merge(
        phlebotomist_display,
        phlebotomist_count,
        on='PhlebotomistName',
        how='left'
    ).fillna(0)

    phlebotomist_display['AppointmentCount'] = phlebotomist_display['AppointmentCount'].astype(int)
    phlebotomist_display = phlebotomist_display.sort_values('AppointmentCount', ascending=False)

    # Rename columns for better display
    phlebotomist_display.columns = ['Phlebotomist Name', 'Service Area', 'City', 'Appointment Count']

    # Add a download button
    csv = phlebotomist_display.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"phlebotomists_{date_option.strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        on_click=lambda: logger.info(f"Phlebotomist data downloaded for date: {date_option}"),
        help="Download the phlebotomist data as a CSV file"
    )

    st.markdown("<div class='data-table'>", unsafe_allow_html=True)
    st.dataframe(phlebotomist_display, use_container_width=True, height=300)
    st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.markdown("""
    <div style="display: flex; align-items: center; margin-bottom: 20px;">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 10px;">
            <path d="M17 21V19C17 16.7909 15.2091 15 13 15H5C2.79086 15 1 16.7909 1 19V21" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path fill-rule="evenodd" clip-rule="evenodd" d="M9 11C11.2091 11 13 9.20914 13 7C13 4.79086 11.2091 3 9 3C6.79086 3 5 4.79086 5 7C5 9.20914 6.79086 11 9 11Z" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <h3 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.2rem;">Patient Appointment Schedule</h3>
    </div>
    """, unsafe_allow_html=True)

    # Enhanced patient dataframe
    patient_display = filtered_data[['ScheduledDtm', 'PhlebotomistName', 'ServiceAreaDescription', 'City']]
    patient_display['ScheduledDtm'] = patient_display['ScheduledDtm'].dt.strftime('%Y-%m-%d %H:%M')
    patient_display = patient_display.sort_values('ScheduledDtm')

    # Rename columns for better display
    patient_display.columns = ['Scheduled Date & Time', 'Assigned Phlebotomist', 'Service Area', 'City']

    # Add a download button
    csv = patient_display.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"patients_{date_option.strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        on_click=lambda: logger.info(f"Patient data downloaded for date: {date_option}"),
        help="Download the patient data as a CSV file"
    )

    st.markdown("<div class='data-table'>", unsafe_allow_html=True)
    st.dataframe(patient_display, use_container_width=True, height=300)
    st.markdown("</div>", unsafe_allow_html=True)

# Modern footer with app info
st.markdown("""
<div class="footer">
    <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 15px;">
        <div style="width: 50px; height: 50px; border-radius: 15px; background: linear-gradient(45deg, #3a7bd5, #00d2ff); 
                    display: flex; align-items: center; justify-content: center; margin-right: 15px;">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 10C21 17 12 23 12 23C12 23 3 17 3 10C3 7.61305 3.94821 5.32387 5.63604 3.63604C7.32387 1.94821 9.61305 1 12 1C14.3869 1 16.6761 1.94821 18.364 3.63604C20.0518 5.32387 21 7.61305 21 10Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 13C13.6569 13 15 11.6569 15 10C15 8.34315 13.6569 7 12 7C10.3431 7 9 8.34315 9 10C9 11.6569 10.3431 13 12 13Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div>
            <h3 style="margin: 0; color: #4a5568; font-weight: 600; font-size: 1.3rem;">Phlebotomist Mapping Dashboard</h3>
            <p style="margin: 5px 0 0 0; color: #718096; font-size: 0.9rem;">Last updated: March 2025</p>
        </div>
    </div>
    <p style="margin: 0; color: #718096; font-size: 0.9rem; text-align: center;">
        Optimized for seamless visualization and enhanced user experience
    </p>
</div>

<!-- Toast notification for filters applied -->
<div class="toast-notification">
    <div style="display: flex; align-items: center;">
        <div style="width: 30px; height: 30px; border-radius: 50%; background: rgba(58, 123, 213, 0.1); 
                    display: flex; align-items: center; justify-content: center; margin-right: 10px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 11.0801V12.0001C21.9988 14.1565 21.3005 16.2548 20.0093 17.9819C18.7182 19.7091 16.9033 20.9726 14.8354 21.584C12.7674 22.1954 10.5573 22.122 8.53447 21.3747C6.51168 20.6274 4.78465 19.2462 3.61096 17.4371C2.43727 15.628 1.87979 13.4882 2.02168 11.3364C2.16356 9.18467 2.99721 7.13643 4.39828 5.49718C5.79935 3.85793 7.69279 2.71549 9.79619 2.24025C11.8996 1.76502 14.1003 1.98245 16.07 2.86011" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M22 4L12 14.01L9 11.01" stroke="#3a7bd5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div>
            <p style="margin: 0; font-weight: 600; color: #4a5568; font-size: 14px;">Filters Applied</p>
            <p style="margin: 3px 0 0 0; color: #718096; font-size: 12px;">Map and data updated successfully</p>
        </div>
    </div>
    <div style="position: absolute; top: 10px; right: 10px; cursor: pointer; color: #a0aec0;">×</div>
</div>
""", unsafe_allow_html=True)
