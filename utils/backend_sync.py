import logging
from typing import Tuple
import pandas as pd
import requests


def sync_patients_to_backend(api_url: str, enriched_df: pd.DataFrame) -> Tuple[bool, str]:
    """Send enriched patient records to backend API.

    Parameters
    ----------
    api_url : str
        Endpoint URL to send the records to.
    enriched_df : pd.DataFrame
        Dataframe of patients to sync.

    Returns
    -------
    Tuple[bool, str]
        Success flag and response or error message.
    """
    try:
        response = requests.post(api_url, json=enriched_df.to_dict(orient='records'))
        if response.status_code == 200:
            return True, response.text
        return False, f"{response.status_code}: {response.text}"
    except Exception as exc:
        logging.getLogger(__name__).error("Backend sync failed", exc_info=True)
        return False, str(exc)
