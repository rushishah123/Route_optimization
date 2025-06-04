# Import all functions from individual utility modules
from route_utils import (
    get_route,
    calculate_route_distance,
    calculate_distance,
    plot_routes_on_map
)

from workload_utils import (
    phlebs_required_asper_workload
)

from assignment_utils import (
    get_available_phlebotomists,
    assign_patients_to_phlebotomists,
    optimize_routes,
    process_city_assignments,
    save_assignment_results,
    estimate_travel_time,
    estimate_draw_time,
    # calculate_approach_comparison
)

from map_utils import (
    create_assignment_map,
    add_sequence_label,
    create_assignment_legend
)

from data_utils import (
    load_data,
    get_available_dates,
    get_available_cities,
    get_cities_by_date
)

from clustering_utils import (
    cluster_patients
)

from utils.enrichment_utils import enrich_patient_phlebotomist_fields
from utils.backend_sync import sync_patients_to_backend
import pandas as pd
import os

# Re-export all functions to maintain API compatibility
__all__ = [
    # Route utilities
    'get_route',
    'calculate_route_distance',
    'calculate_distance',
    'plot_routes_on_map',
    
    # Workload utilities
    'phlebs_required_asper_workload',
    
    # Assignment utilities
    'get_available_phlebotomists',
    'assign_patients_to_phlebotomists',
    'optimize_routes',
    'process_city_assignments',
    'save_assignment_results',
    'estimate_travel_time',
    'estimate_draw_time',
    'calculate_approach_comparison',
    
    # Map utilities
    'create_assignment_map',
    'add_sequence_label',
    'create_assignment_legend',
    
    # Data utilities
    'load_data',
    'get_available_dates',
    'get_available_cities',
    'get_cities_by_date',
    
    # Clustering utilities
    'cluster_patients',
    'enrich_patient_phlebotomist_fields',
    'sync_patients_to_backend',
    'save_enriched_patients'
]


def save_enriched_patients(enriched_df: pd.DataFrame, target_date, target_city) -> str:
    """Save enriched patients dataframe to CSV and return the path."""
    output_dir = os.path.join('GeneratedFiles')
    os.makedirs(output_dir, exist_ok=True)
    date_str = pd.to_datetime(target_date).strftime('%Y-%m-%d')
    city_str = str(target_city).replace(' ', '')
    filename = f'enriched_patients_{date_str}_{city_str}.csv'
    path = os.path.join(output_dir, filename)
    enriched_df.to_csv(path, index=False)
    return os.path.relpath(path).replace('\\', '/')

