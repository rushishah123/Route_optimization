import pandas as pd

def phlebs_required_asper_workload(workload_df, city_orders_df, target_date, target_city):
    """
    Calculate the number of phlebotomists needed based on workload points.
    
    Args:
        workload_df: DataFrame with city workload information
        city_orders_df: DataFrame with all patient orders
        target_date: Date to analyze
        target_city: City to analyze
        
    Returns:
        Number of phlebotomists needed or None if data not available
    """
    if type(target_date) == str:
        target_date = pd.to_datetime(target_date).date()
    
    # Filter data for the given city and date
    filtered_patients = city_orders_df[
        (city_orders_df["City"] == target_city) & 
        (city_orders_df["ScheduledDtm"].dt.date == target_date)
    ]
    
    if filtered_patients.empty:
        print("Filtered Patients empty in PRAPW function...")
        return None
        
    if target_city in workload_df["City"].values:
        avg_workload = workload_df.loc[workload_df["City"] == target_city, "Avg_Workload_Points_per_Phleb"].values[0]
        total_workload = filtered_patients["WorkloadPoints"].sum()
        avg_workload = max(1, avg_workload)  # Prevent division by zero
        phlebs_needed = max(1, total_workload // avg_workload)
        
        return int(phlebs_needed)
    
    print("Returning 1 bcoz city was not found in workload data")
    return 1  # If city is not found in workload data
