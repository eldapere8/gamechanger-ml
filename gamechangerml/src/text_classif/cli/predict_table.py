"""
usage: predict_table.py [-h] -m MODEL_PATH -d DATA_PATH [-b BATCH_SIZE]
                        [-l MAX_SEQ_LEN] -g GLOB [-o OUTPUT_CSV] -e ENTITY_CSV
                        -a AGENCIES_FILE -t ENTITY_MENTIONS --num-labels
                        NUM_LABELS

Classification of responsibility statements. For each sentence in the
matching files. For each label > 0, sentences are linked to its closest
entity.

optional arguments:
  -h, --help            show this help message and exit
  -m MODEL_PATH, --model-path MODEL_PATH
                        directory containing the pytorch model
  -d DATA_PATH, --data-path DATA_PATH
                        path holding the .json corpus files
  -b BATCH_SIZE, --batch-size BATCH_SIZE
                        batch size for the data samples; default=8
  -l MAX_SEQ_LEN, --max-seq-len MAX_SEQ_LEN
                        maximum sequence length, 128 to 512; default=128
  -g GLOB, --glob GLOB  file glob pattern
  -o OUTPUT_CSV, --output-csv OUTPUT_CSV
                        the .csv for output
  -e ENTITY_CSV, --entity-csv ENTITY_CSV
                        csv of entities and abbreviations
  -a AGENCIES_FILE, --agencies-file AGENCIES_FILE
                        the .csv for agency abbreviations and references
  -t ENTITY_MENTIONS, --entity-mentions ENTITY_MENTIONS
                        JSON created by `entity_mentions.py`
  --num-labels NUM_LABELS
                        number of labels in the classification model
"""
import logging
import os
import time
import pandas as pd

import gamechangerml.src.text_classif.utils.classifier_utils as cu
from gamechangerml.src.featurization.abbreviations_utils import (
    get_references,
    get_agencies_dict,
    get_agencies,
)
from gamechangerml.src.entity.entity_link import EntityLink
from gamechangerml.src.text_classif.utils.log_init import initialize_logger
from gamechangerml.src.text_classif.utils.resp_stats import count_output

logger = logging.getLogger(__name__)


def _agg_stats(df):
    resp_per_doc, resp_no_entity, n_uniq_entities, n_docs = count_output(df)
    if resp_per_doc:
        df_resp_doc = pd.DataFrame(
            list(resp_per_doc.items()), columns=["doc", "count"]
        )
        df_resp_doc.to_csv("resp-in-doc-stats.csv", index=False)
    if resp_no_entity:
        df_resp_no_e = pd.DataFrame(
            list(resp_per_doc.items()), columns=["doc", "count"]
        )
        df_resp_no_e.to_csv("resp-no-entity-stats.csv", index=False)


def dump_label(df, num_labels, output_csv):
    out_path, fname = os.path.split(output_csv)
    fname, ext = os.path.splitext(fname)
    for lbl in range(num_labels):
        tdf = df[df.top_class == lbl].reset_index()
        if len(tdf) == 0:
            logger.warning("no output for label {}".format(lbl))
            continue
        out_csv_ = os.path.join(fname + "-label-{}".format(lbl) + ext)
        logger.info("writing {}".format(out_csv_))
        tdf.to_csv(out_csv_, index=False)
        _ = tdf.iloc[0:0]


def predict_table(
    model_path,
    data_path,
    glob,
    max_seq_len,
    batch_size,
    output_csv,
    stats,
    entity_csv,
    entity_mentions,
    agencies_file,
    num_labels,
):
    """
    See the preamble (help) for a description of these arguments.

    For each file matching `glob`, the `raw_text` is parsed into sentences
    and run through the classifier. The final output is assembled by using
    sentences classified as `> 0` with organization information, references,
    document title, etc.

    Returns:
        pd.DataFrame
    """
    if os.path.isfile(output_csv):
        raise ValueError("output file exists. Please rename or remove.")
    if not os.path.isdir(data_path):
        raise ValueError("no data path {}".format(data_path))
    if not os.path.isdir(model_path):
        raise ValueError("no model path {}".format(model_path))
    if not os.path.isfile(entity_csv):
        raise FileNotFoundError("entity-csv got {}".format(entity_csv))
    if not os.path.isfile(agencies_file):
        raise FileNotFoundError("agencies-file got {}".format(agencies_file))
    if not os.path.isfile(entity_mentions):
        raise FileNotFoundError("entity-mentions got {}".format(entity_mentions))

    if num_labels < 1:
        raise ValueError("num labels must > 0; got {}".format(num_labels))

    dump_individ = True

    rename_dict = {
        "entity": "Organization / Personnel",
        "sentence": "Responsibility Text",
        "agencies": "Other Organization(s) / Personnel Mentioned",
        "refs": "Documents Referenced",
        "title": "Document Title",
        "source": "Source Document",
    }

    start = time.time()
    entity_linker = EntityLink(
        entity_csv=entity_csv,
        mentions_json=entity_mentions,
        use_na=False,
        topk=3,
        num_labels=num_labels,
        max_seq_len=max_seq_len,
        batch_size=batch_size,
    )
    logger.info("into the breach...")
    entity_linker.make_table(
        model_path,
        data_path,
        glob,
    )
    df = entity_linker.to_df()

    # for a post-run look
    if dump_individ:
        dump_label(df, num_labels, output_csv)

    df = df[df.top_class > 0].reset_index()

    logger.info("building agencies for entries {:,} entries".format(len(df)))
    logger.info("please be patient...")
    duplicates, aliases = get_agencies_dict(agencies_file)
    df["agencies"] = get_agencies(
        file_dataframe=df,
        doc_dups=None,
        duplicates=duplicates,
        agencies_dict=aliases,
        verbose=True,
    )

    logger.info("getting references...")
    df["refs"] = get_references(df, doc_title_col="src")

    renamed_df = df.rename(columns=rename_dict)
    final_df = renamed_df[
        [
            "Source Document",
            "Document Title",
            "Organization / Personnel",
            "Responsibility Text",
            "Other Organization(s) / Personnel Mentioned",
            "Documents Referenced",
        ]
    ]
    if output_csv is not None:
        final_df.to_csv(output_csv, index=False)
        logger.info("final csv written to {}".format(output_csv))
    if stats:
        _agg_stats(final_df)
    elapsed = time.time() - start

    logger.info("total time : {:}".format(cu.format_time(elapsed)))
    return final_df


if __name__ == "__main__":
    from argparse import ArgumentParser

    desc = "Classification of responsibility statements. For each sentence "
    desc += "in the matching files. For each label > 0, "
    desc += "sentences are linked to its closest entity."

    parser = ArgumentParser(prog=os.path.split(__file__)[-1], description=desc)
    parser.add_argument(
        "-m",
        "--model-path",
        dest="model_path",
        type=str,
        required=True,
        help="directory containing the pytorch model",
    )
    parser.add_argument(
        "-d",
        "--data-path",
        dest="data_path",
        type=str,
        required=True,
        help="path holding the .json corpus files",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        dest="batch_size",
        type=int,
        default=8,
        help="batch size for the data samples; default=8",
    )
    parser.add_argument(
        "-l",
        "--max-seq-len",
        dest="max_seq_len",
        type=int,
        default=128,
        help="maximum sequence length, 128 to 512; default=128",
    )
    parser.add_argument(
        "-g",
        "--glob",
        dest="glob",
        type=str,
        required=True,
        help="file glob pattern",
    )
    parser.add_argument(
        "-o",
        "--output-csv",
        dest="output_csv",
        type=str,
        default=None,
        help="the .csv for output",
    )
    parser.add_argument(
        "-e",
        "--entity-csv",
        dest="entity_csv",
        type=str,
        required=True,
        help="csv of entities and abbreviations",
    )
    parser.add_argument(
        "-a",
        "--agencies-file",
        dest="agencies_file",
        type=str,
        required=True,
        help="the .csv for agency abbreviations and references",
    )
    parser.add_argument(
        "-t",
        "--entity-mentions",
        dest="entity_mentions",
        type=str,
        required=True,
        help="JSON created by `entity_mentions.py`",
    )
    parser.add_argument(
        "--num-labels",
        dest="num_labels",
        type=int,
        required=True,
        help="number of labels in the classification model",
    )

    initialize_logger(to_file=False, log_name="none")

    args = parser.parse_args()
    stats_ = False

    _ = predict_table(
        args.model_path,
        args.data_path,
        args.glob,
        args.max_seq_len,
        args.batch_size,
        args.output_csv,
        stats_,
        args.entity_csv,
        args.entity_mentions,
        args.agencies_file,
        args.num_labels,
    )
