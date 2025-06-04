import pandas as pd
import streamlit as st

def load_data(trips_path, phlebs_path, workload_path):
    """
    Load and prepare all required data.
    
    Args:
        trips_path: Path to the trips CSV file
        phlebs_path: Path to the phlebotomists CSV file
        workload_path: Path to the workload CSV file
        
    Returns:
        Tuple of (trips_df, phleb_df, workload_df)
    """
    try:
        # Load trips data
        trips_df = pd.read_csv(trips_path)
        trips_df['ScheduledDtm'] = pd.to_datetime(trips_df['ScheduledDtm'])
        
        # Load phlebotomist locations
        phleb_df = pd.read_csv(phlebs_path)
        
        # Load workload data
        workload_df = pd.read_csv(workload_path)
        
        return trips_df, phleb_df, workload_df
    
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None

def get_available_dates(trips_df):
    """Get unique dates from the trips dataframe"""
    if trips_df is not None and 'ScheduledDtm' in trips_df.columns:
        return sorted(trips_df['ScheduledDtm'].dt.date.unique())
    return []

def get_available_cities(trips_df):
    """Get unique cities from the trips dataframe"""
    if trips_df is not None and 'City' in trips_df.columns:
        return sorted(trips_df['City'].unique())
    return []

def get_cities_by_date(trips_df):
    """
    Create a mapping of dates to available cities in the trips data
    
    Args:
        trips_df (pandas.DataFrame): DataFrame containing trip data
        
    Returns:
        dict: Mapping of date strings to lists of cities
    """
    date_city_map = {}
    
    # Ensure the ScheduledDtm column is in datetime format
    trips_df['ScheduledDtm'] = pd.to_datetime(trips_df['ScheduledDtm'])
    
    # Group by date and get unique cities for each date
    for date, group in trips_df.groupby(trips_df['ScheduledDtm'].dt.date.astype(str)):
        date_city_map[date] = sorted(group['City'].unique().tolist())
    
    return date_city_map
