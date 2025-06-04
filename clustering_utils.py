import numpy as np
from sklearn.cluster import KMeans
from geopy.distance import geodesic

def cluster_patients(patient_df, num_clusters=None):
    """
    Cluster patients based on geographic location.
    
    Args:
        patient_df: DataFrame with patient information
        num_clusters: Number of clusters to create (optional)
        
    Returns:
        DataFrame with cluster assignments
    """
    if patient_df.empty:
        return patient_df
        
    # If number of clusters not specified, estimate based on data size
    if num_clusters is None:
        # Rule of thumb: sqrt of number of data points
        num_clusters = min(max(2, int(np.sqrt(len(patient_df)))), len(patient_df))
    
    # Extract coordinates for clustering
    coords = patient_df[['PatientLatitude', 'PatientLongitude']].values
    
    # Perform K-means clustering
    kmeans = KMeans(n_clusters=num_clusters, random_state=42)
    clusters = kmeans.fit_predict(coords)
    
    # Add cluster assignments to DataFrame
    result_df = patient_df.copy()
    result_df['Cluster'] = clusters
    
    return result_df
