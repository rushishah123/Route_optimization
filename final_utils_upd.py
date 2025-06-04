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
    'cluster_patients'
]