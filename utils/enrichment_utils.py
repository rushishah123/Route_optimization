import pandas as pd
import logging
import os
import re
from typing import Tuple


def enrich_patient_phlebotomist_fields(
    patient_df: pd.DataFrame,
    phleb_df: pd.DataFrame,
    log_file_path: str
) -> pd.DataFrame:
    """Fill missing phlebotomist related fields on patient records.

    Only updates fields that are null. Uses phleb_df metadata matched by
    ``AssignedPhlebID`` on the patient record and ``PhlebotomistID.1`` on the
    phlebotomist dataframe.

    Parameters
    ----------
    patient_df : pd.DataFrame
        Assigned patient dataframe.
    phleb_df : pd.DataFrame
        Phlebotomist metadata dataframe.
    log_file_path : str
        Path to log file for skipped enrichments.

    Returns
    -------
    pd.DataFrame
        New dataframe with enriched fields.
    """
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    logger = logging.getLogger(__name__)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file_path)
               for h in logger.handlers):
        handler = logging.FileHandler(log_file_path)
        formatter = logging.Formatter('%(asctime)s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    patients = patient_df.copy()

    # prepare phlebotomist dataframe for merge
    phleb_merge = phleb_df.copy()
    phleb_merge['AssignedPhlebID'] = phleb_merge['PhlebotomistID.1'].astype(str)
    phleb_merge = phleb_merge.rename(columns={
        'PhlebotomistID.1': 'PhlebotomistID',
        'PhlebotomistName': 'PhlebotomistName_src',
        'City': 'PhlebotmistCity'
    })

    merge_cols = [
        'AssignedPhlebID',
        'PhlebotomistID',
        'PhlebotomistName_src',
        'PhlebotmistCity',
        'PhlebotomistLatitude',
        'PhlebotomistLongitude'
    ]

    optional_cols = ['PhlebotomistStreet1', 'PhlebotomistZip', 'DropOffLocation']
    for col in optional_cols:
        if col in phleb_merge.columns and col not in merge_cols:
            merge_cols.append(col)

    patients = patients.merge(phleb_merge[merge_cols], on='AssignedPhlebID', how='left', suffixes=('', '_phleb'))

    def valid_name(name: str) -> bool:
        return bool(re.fullmatch(r'[A-Za-z0-9\s]+', str(name)))

    duplicate_names = phleb_merge['PhlebotomistName_src'].value_counts()
    duplicate_names = set(duplicate_names[duplicate_names > 1].index)

    # Field mapping of patient column -> phleb merge column
    field_map = {
        'PhlebotomistID': 'PhlebotomistID',
        'PhlebotomistName': 'PhlebotomistName_src',
        'PhlebotmistCity': 'PhlebotmistCity',
        'PhlebotomistLatitude': 'PhlebotomistLatitude',
        'PhlebotomistLongitude': 'PhlebotomistLongitude',
        'PhlebotomistStreet1': 'PhlebotomistStreet1',
        'PhlebotomistZip': 'PhlebotomistZip',
        'DropOffLocation': 'DropOffLocation'
    }

    for patient_col, phleb_col in field_map.items():
        if patient_col not in patients.columns or phleb_col not in patients.columns:
            continue
        if patient_col == 'PhlebotomistName':
            mask = patients[patient_col].isna()
            name_candidates = patients.loc[mask, phleb_col]
            valid_mask = name_candidates.apply(lambda x: valid_name(x) and x not in duplicate_names)
            invalid = patients.loc[mask & ~valid_mask, ['AssignedPhlebID', phleb_col]]
            for _, row in invalid.iterrows():
                logger.info(f"Skipped name for PhlebID {row['AssignedPhlebID']} -> {row[phleb_col]}")
            patients.loc[mask & valid_mask, patient_col] = name_candidates[valid_mask]
        else:
            mask = patients[patient_col].isna()
            patients.loc[mask, patient_col] = patients.loc[mask, phleb_col]

    # Drop the extra merged columns created during the merge
    patients = patients.drop(columns=[c for c in patients.columns if c.endswith('_phleb')])

    return patients
