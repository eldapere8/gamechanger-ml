import datetime
import logging
import time

import pandas as pd
from tqdm import tqdm

from gamechangerml.src.featurization.ref_list import collect_ref_list

logger = logging.getLogger(__name__)


def get_agencies_dict(agencies_file):
    """
    Pulls agencies list into a dictionary for use in abbreviations pipeline.

    Args:
        agencies_file: file of the agency documents. currently set to
            agencies.csv

    Returns:

    """
    df = pd.read_csv(agencies_file)

    aliases = {}
    duplicates = []

    for index, row in df.iterrows():
        temp = list(str(row["Agency_Aliases"]).split(";"))
        for i in temp:
            agency_list = []
            if i not in aliases:
                agency_list.append(row["Agency_Name"])
                aliases[i] = agency_list
            else:
                duplicates.append(i)
                aliases[i].append(row["Agency_Name"])
        aliases[row["Agency_Name"]] = [row["Agency_Name"]]

    return duplicates, aliases


def get_agencies(file_dataframe, doc_dups, duplicates, agencies_dict):
    """
    Get all the disambiguated agencies for a list of documents.

    Args:
        file_dataframe: dataframe generated by responsibilities.py for a given
            set of documents
        doc_dups: list of disambiguated agencies
        duplicates: list of potentially ambiguous agencies
        agencies_dict: dictionary of agency acronyms to full agency names

    Returns:
        Vector of all extracted agencies for every row of the input dataframe.
    """
    aliases = agencies_dict
    duplicates = duplicates
    all_agencies = []

    # speeds up iterating through the various dataframe columns dynamically,
    # excludes doc name and primary entity
    logger.info(
        "building intermediate table, size : {:,}".format(len(file_dataframe))
    )
    start = time.time()
    combined_cols = pd.DataFrame(
        file_dataframe[file_dataframe.columns[2:]].apply(
            lambda x: ",".join(x.dropna().astype(str)), axis=1
        ),
        columns=["text"],
    )
    elapsed_rounded = int(round(time.time() - start))
    fmt = str(datetime.timedelta(seconds=elapsed_rounded))
    logger.info("intermediate table built : {:}".format(fmt))

    # TODO make faster - the double iteration is very slow
    logger.info("attaching agencies...")
    start = time.time()
    for i, row in combined_cols.iterrows():
        agencies = []
        for x in aliases.keys():
            if " " + x in row["text"]:
                if x not in duplicates:
                    agencies.append(aliases[x])
                if doc_dups is not None:
                    if doc_dups[i] is not None:
                        agencies.append(doc_dups[i])
        flat_a = [item for sublist in agencies for item in sublist]
        flat_a = ["".join(x) for x in flat_a]
        flat_a = set(flat_a)
        all_agencies.append(",".join(flat_a))

    elapsed_rounded = int(round(time.time() - start))
    fmt = str(datetime.timedelta(seconds=elapsed_rounded))
    logger.info("agencies attached : {:}".format(fmt))
    return all_agencies


def get_references(file_dataframe, doc_title_col="doc"):
    """
    Get all the refs for a list of documents.

    Args:
        file_dataframe: dataframe generated by the predictive model for a given
            set of documents

    Returns:
        Vector of all extracted agencies for every row of the input dataframe.
    """
    df = file_dataframe
    all_refs = []

    for i, row in tqdm(df.iterrows(), total=len(df), desc="refs"):
        refs = []
        for j in list(df.columns):
            if type(row[j]) == str:
                if j != doc_title_col:
                    refs.append(list(collect_ref_list(row[j]).keys()))
        flat_r = [item for sublist in refs for item in sublist]
        flat_r = list(set(flat_r))
        all_refs.append(flat_r)

    return all_refs


def check_duplicates(text, duplicates, agencies_dict):
    """
    For a given text, checks to see if there are duplicate agencies and returns
    proper agency or agency abbreviation.

    Args:
        text: raw text of file from input json
        duplicates: list of acronyms with multiple associated agencies
        agencies: agencies file based around columns "Agency_Aliases" and
            "Agency_Names"

    Returns:
        list of agency names (or acronyms) where agency alias was ambiguous
    """

    duplicates = duplicates
    agencies_dict = agencies_dict
    best_agencies = []

    for dup in duplicates:
        if dup in text:
            for i in agencies_dict[dup]:
                if i in text:
                    best_agencies.append(i)
                if len(best_agencies) < 1:
                    best_agencies.append(dup)
    if len(best_agencies) > 0:
        return best_agencies
    else:
        return None
