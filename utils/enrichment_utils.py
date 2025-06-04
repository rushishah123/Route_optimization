import pandas as pd
import logging
import os
import re


def enrich_patient_phlebotomist_fields(
    patient_df: pd.DataFrame,
    phleb_df: pd.DataFrame,
    log_file_path: str
) -> pd.DataFrame:
    """Fill missing phlebotomist related fields on patient records.

    Only updates fields that are null. It matches patient rows to
    ``phleb_df`` using the phlebotomist ID column present on the patient
    dataframe.  Most raw trip exports label this column ``PhlebotomistID.1``
    while some assignment routines may add an ``AssignedPhlebID`` column.
    Whichever of these columns exists will be used for the merge.

    The phlebotomist dataframe always uses ``PhlebotomistID.1`` as the
    unique identifier.

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
    if not any(
        isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file_path)
        for h in logger.handlers
    ):
        handler = logging.FileHandler(log_file_path)
        formatter = logging.Formatter("%(asctime)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    patients = patient_df.copy()

    # Determine which column to use for joining with phlebotomist metadata.
    if "PhlebotomistID.1" in patients.columns:
        join_col = "PhlebotomistID.1"
    elif "AssignedPhlebID" in patients.columns:
        join_col = "AssignedPhlebID"
    else:
        logger.warning(
            "No PhlebotomistID.1 or AssignedPhlebID column present; cannot merge phlebotomist metadata"
        )
        return patients

    patients["_join_phlebid"] = patients[join_col].astype(str)

    # Prepare phlebotomist dataframe for merge
    phleb_merge = phleb_df.copy()
    phleb_merge = phleb_merge.rename(
        columns={
            "PhlebotomistID.1": "PhlebotomistID",
            "City": "PhlebotmistCity",
        }
    )
    phleb_merge["_join_phlebid"] = phleb_merge["PhlebotomistID"].astype(str)

    # Determine which target fields exist on the patient dataframe
    target_fields = [
        "PhlebotomistID",
        "PhlebotomistName",
        "PhlebotmistCity",
        "PhlebotomistLatitude",
        "PhlebotomistLongitude",
        "PhlebotomistStreet1",
        "PhlebotomistZip",
        "DropOffLocation",
    ]
    existing_fields = [c for c in target_fields if c in patients.columns]

    # Merge only columns present in both dataframes
    merge_cols = ["_join_phlebid"]
    for col in existing_fields:
        if col in phleb_merge.columns:
            merge_cols.append(col)
    patients = patients.merge(
        phleb_merge[merge_cols],
        on="_join_phlebid",
        how="left",
        suffixes=("", "_phleb"),
    )

    # Validation helpers for name field
    valid_name_regex = re.compile(r"^[a-zA-Z\s]+$")
    duplicate_names = (
        phleb_merge["PhlebotomistName"].value_counts()
        if "PhlebotomistName" in phleb_merge.columns
        else pd.Series()
    )
    duplicate_names = set(duplicate_names[duplicate_names > 1].index)

    for col in existing_fields:
        col_phleb = f"{col}_phleb"
        if col_phleb not in patients.columns:
            continue
        mask = patients[col].isna()
        if col == "PhlebotomistName":
            name_vals = patients.loc[mask, col_phleb]
            valid_mask = name_vals.apply(
                lambda x: bool(valid_name_regex.fullmatch(str(x))) and x not in duplicate_names
            )
            invalid_rows = patients.loc[mask & ~valid_mask, ["_join_phlebid", col_phleb]]
            for _, row in invalid_rows.iterrows():
                logger.info(
                    f"Skipped name for PhlebID {row['_join_phlebid']} -> {row[col_phleb]}"
                )
            patients.loc[mask & valid_mask, col] = name_vals[valid_mask]
        else:
            patients.loc[mask, col] = patients.loc[mask, col_phleb]

    # Log rows where enrichment failed for any existing target column
    if existing_fields:
        failed_mask = patients[existing_fields].isna().any(axis=1)
        for _, row in patients.loc[failed_mask].iterrows():
            logger.info(f"Failed enrichment for row: {row.to_dict()}")

    # Drop helper columns
    drop_cols = [c for c in patients.columns if c.endswith("_phleb")]
    patients = patients.drop(columns=drop_cols, errors="ignore")

    # Remove temporary join column
    patients = patients.drop(columns=["_join_phlebid"], errors="ignore")

    # Remove assignment specific columns to retain original schema
    extraneous_cols = [
        "AssignedPhlebID",
        "TripOrderInDay",
        "PreferredTime",
    ]
    patients = patients.drop(columns=[c for c in extraneous_cols if c in patients.columns])

    return patients
