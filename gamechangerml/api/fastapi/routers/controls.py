from fastapi import APIRouter, Response, status
import subprocess
import os
import json
import tarfile
import shutil

from datetime import datetime
from gamechangerml import DATA_PATH
from gamechangerml.src.utilities import utils
from gamechangerml.api.fastapi.model_config import Config
from gamechangerml.api.fastapi.version import __version__
from gamechangerml.api.fastapi.settings import *
from gamechangerml.api.fastapi.routers.startup import *
from gamechangerml.api.utils.threaddriver import MlThread
from gamechangerml.train.pipeline import Pipeline
from gamechangerml.api.utils import processmanager
from gamechangerml.api.fastapi.model_loader import ModelLoader
from gamechangerml.src.utilities.test_utils import (
    collect_evals,
    handle_sent_evals,
)

router = APIRouter()
MODELS = ModelLoader()
## Get Methods ##

pipeline = Pipeline()


@router.get("/")
async def api_information():
    return {
        "API": "FOR TRANSFORMERS",
        "API_Name": "GAMECHANGER ML API",
        "Version": __version__,
    }


@router.get("/getProcessStatus")
async def get_process_status():
    return {
        "process_status": processmanager.PROCESS_STATUS.value,
        "completed_process": processmanager.COMPLETED_PROCESS.value,
    }

@router.get("/getDataList")
def get_downloaded_data_list():
    files = []
    dir_arr = []
    logger.info(DATA_PATH)

    for dir in os.listdir(DATA_PATH):
        temp_path = os.path.join(DATA_PATH,dir)
        if os.path.isdir(temp_path):
            for dirpath, dirnames, filenames in os.walk(temp_path):
                dir_arr.append({'name':dirpath.replace(temp_path,''),'path':dir,'files':filenames,'subdirectories':dirnames})

    return {'dirs':dir_arr}

@router.get("/getModelsList")
def get_downloaded_models_list():
    qexp_list = {}
    sent_index_list = {}
    transformer_list = {}
    topic_models = {}
    ltr_list = {}
    try:
        for f in os.listdir(Config.LOCAL_PACKAGED_MODELS_DIR):
            if ("qexp_" in f) and ("tar" not in f):
                qexp_list[f] = {}
                meta_path = os.path.join(
                    Config.LOCAL_PACKAGED_MODELS_DIR, f, "metadata.json"
                )
                if os.path.isfile(meta_path):
                    meta_file = open(meta_path)
                    qexp_list[f] = json.load(meta_file)
                    qexp_list[f]["evaluation"] = {}
                    qexp_list[f]["evaluation"] = collect_evals(
                        os.path.join(Config.LOCAL_PACKAGED_MODELS_DIR, f)
                    )
                    meta_file.close()
    except Exception as e:
        logger.error(e)
        logger.info("Cannot get QEXP model path")

    # TRANSFORMER MODEL PATH
    try:
        for trans in os.listdir(LOCAL_TRANSFORMERS_DIR.value):
            if trans not in ignore_files and "." not in trans:
                transformer_list[trans] = {}
                config_path = os.path.join(
                    LOCAL_TRANSFORMERS_DIR.value, trans, "config.json"
                )
                if os.path.isfile(config_path):
                    config_file = open(config_path)
                    transformer_list[trans] = json.load(config_file)
                    transformer_list[trans]["evaluation"] = {}
                    transformer_list[trans]["evaluation"] = collect_evals(
                        os.path.join(LOCAL_TRANSFORMERS_DIR.value, trans)
                    )
                    config_file.close()
    except Exception as e:
        logger.error(e)
        logger.info("Cannot get TRANSFORMER model path")
    # SENTENCE INDEX
    # get largest file name with sent_index prefix (by date)
    try:
        for f in os.listdir(Config.LOCAL_PACKAGED_MODELS_DIR):
            if ("sent_index" in f) and ("tar" not in f):
                logger.info(f"sent indices: {str(f)}")
                sent_index_list[f] = {}
                meta_path = os.path.join(
                    Config.LOCAL_PACKAGED_MODELS_DIR, f, "metadata.json"
                )
                if os.path.isfile(meta_path):
                    meta_file = open(meta_path)
                    sent_index_list[f] = json.load(meta_file)
                    sent_index_list[f]["evaluation"] = {}

                    sent_index_list[f]["evaluation"] = handle_sent_evals(
                        os.path.join(Config.LOCAL_PACKAGED_MODELS_DIR, f)
                    )
                    meta_file.close()
    except Exception as e:
        logger.error(e)
        logger.info("Cannot get Sentence Index model path")

    # TOPICS MODELS
    try:

        topic_dirs = [
            name
            for name in os.listdir(Config.LOCAL_PACKAGED_MODELS_DIR)
            if os.path.isdir(os.path.join(Config.LOCAL_PACKAGED_MODELS_DIR, name))
            and "topic_model_" in name
        ]
        for topic_model_name in topic_dirs:
            topic_models[topic_model_name] = {}
            try:
                with open(
                    os.path.join(
                        Config.LOCAL_PACKAGED_MODELS_DIR,
                        topic_model_name,
                        "metadata.json",
                    )
                ) as mf:
                    topic_models[topic_model_name] = json.load(mf)
            except:
                topic_models[topic_model_name] = {
                    "Error": "Failed to load metadata file for this model"
                }

    except Exception as e:
        logger.error(e)
        logger.info("Cannot get Topic model path")

    # LTR
    try:
        for f in os.listdir(Config.LOCAL_PACKAGED_MODELS_DIR):
            if ("ltr" in f) and ("tar" not in f):
                logger.info(f"LTR: {str(f)}")
                ltr_list[f] = {}
                meta_path = os.path.join(
                    Config.LOCAL_PACKAGED_MODELS_DIR, f, "metadata.json"
                )
                if os.path.isfile(meta_path):
                    meta_file = open(meta_path)
                    ltr_list[f] = json.load(meta_file)
                    meta_file.close()
    except Exception as e:
        logger.error(e)
        logger.info("Cannot get Sentence Index model path")

    model_list = {
        "transformers": transformer_list,
        "sentence": sent_index_list,
        "qexp": qexp_list,
        "topic_models": topic_models,
        "ltr": ltr_list,
    }
    return model_list

@router.post("/deleteLocalModel")
async def delete_local_model(model: dict, response:Response):
    def removeDirectory(dir):
        try:
            logger.info(f'Removing directory {os.path.join(dir,model["model"])}')
            shutil.rmtree(os.path.join(dir,model['model']))
        except OSError as e:
            logger.error(e)

    def removeFiles(dir):
        for f in os.listdir(dir):
            if model['model'] in f:
                logger.info(f'Removing file {f}')
                try:
                    os.remove(os.path.join(dir,f))
                except OSError as e:
                    logger.error(e)

    logger.info(model)
    if model['type'] == 'transformers':
        removeDirectory(LOCAL_TRANSFORMERS_DIR.value)
    elif model['type'] == 'sentence' or model['type'] == 'qexp':
        removeDirectory(Config.LOCAL_PACKAGED_MODELS_DIR)
        removeFiles(Config.LOCAL_PACKAGED_MODELS_DIR)

    return await get_process_status()
    
@router.get("/LTR/initLTR", status_code=200)
async def initLTR(response: Response):
    """generate judgement - checks how many files are in the corpus directory
    Args:
    Returns: integer
    """
    number_files = 0
    resp = None
    try:
        pipeline.init_ltr()
    except Exception as e:
        logger.warning("Could not init LTR")
    return resp


@router.get("/LTR/createModel", status_code=200)
async def create_LTR_model(response: Response):
    """generate judgement - checks how many files are in the corpus directory
    Args:
    Returns: integer
    """
    number_files = 0
    resp = None
    try:
        model = []

        def ltr_process():
            pipeline.create_ltr()

        ltr_thread = MlThread(ltr_process)

        ltr_thread.start()

    except Exception as e:
        logger.warning(e)
        logger.warning(f"There is an issue with LTR creation")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return response.status_code


@router.get("/getFilesInCorpus", status_code=200)
async def files_in_corpus(response: Response):
    """files_in_corpus - checks how many files are in the corpus directory
    Args:
    Returns: integer
    """
    number_files = 0
    try:
        logger.info("Reading files from local corpus")
        number_files = len(
            [
                name
                for name in os.listdir(CORPUS_DIR)
                if os.path.isfile(os.path.join(CORPUS_DIR, name))
            ]
        )
    except:
        logger.warning(f"Could not get files in corpus")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return json.dumps(number_files)


@router.get("/getCurrentTransformer")
async def get_trans_model():
    """get_trans_model - endpoint for current transformer
    Args:
    Returns:
        dict of model name
    """
    # sent_model = latest_intel_model_sent.value
    return {
        "sim_model": latest_intel_model_sim.value,
        "encoder_model": latest_intel_model_encoder.value,
        "sentence_index": SENT_INDEX_PATH.value,
        "qexp_model": QEXP_MODEL_NAME.value,
        "qa_model": latest_qa_model.value,
    }


@router.get("/download", status_code=200)
async def download(response: Response):
    """download - downloads dependencies from s3
    Args:
    Returns:
    """
    processmanager.update_status(processmanager.s3_dependency, 0, 1)
    def download_s3_thread():
        try:
            logger.info("Attempting to download dependencies from S3")
            output = subprocess.call(["gamechangerml/scripts/download_dependencies.sh"])
            # get_transformers(overwrite=False)
            # get_sentence_index(overwrite=False)
            processmanager.update_status(processmanager.s3_dependency, 1, 1)
        except:

            logger.warning(f"Could not get dependencies from S3")
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            processmanager.update_status(processmanager.s3_dependency, failed=True)

    thread = MlThread(download_s3_thread)
    thread.start()
    return await get_process_status()


@router.post("/downloadS3File", status_code=200)
async def download_s3_file(file_dict: dict, response: Response):
    """download - downloads dependencies from s3
    Args:
    Returns:
    """
    processmanager.update_status(processmanager.s3_file_download, 0, 1)
    def download_s3_thread():
        logger.info(f'downloading file {file_dict["file"]}')
        try:
        
            path = "gamechangerml/models/" if file_dict['dir'] == "models" else "gamechangerml/"
            downloaded_files = utils.get_model_s3(file_dict['file'],f"bronze/gamechanger/{file_dict['dir']}/",path)
            # downloaded_files = ['gamechangerml/models/20210223.tar.gz']
            processmanager.update_status(processmanager.s3_file_download, 0, len(downloaded_files))
            i = 0
            for f in downloaded_files:
                i+=1
                processmanager.update_status(processmanager.s3_file_download, 0,i)
                logger.info(f)
                if '.tar' in  f:
                    tar = tarfile.open(f)
                    if tar.getmembers()[0].name == '.':
                        if 'sentence_index' in file_dict['file']:
                            path += 'sent_index_'
                        elif 'jbook_qexp_model' in file_dict['file']: 
                            path += 'jbook_qexp_'
                        elif 'qexp_model' in file_dict['file']: 
                            path += 'qexp_'
                        elif 'topic_model' in file_dict['file']:
                            path += 'topic_models'

                        path += f.split('/')[-1].split('.')[0]

                    logger.info(f'Extracting {f} to {path}')
                    tar.extractall(path=path, members=[member for member in tar.getmembers() if('.git' not in member.name and '.DS_Store' not in member.name)])
                    tar.close()

        except PermissionError:
            failedExtracts = []
            for member in tar.getmembers():
                try:
                    tar.extract(member,path=path)
                except Exception as e:
                    failedExtracts.append(member.name)

            logger.warning(f'Could not extract {failedExtracts}')

        except Exception as e:
            logger.warning(e)
            logger.warning(f"Could download {file_dict['file']} from S3")
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            processmanager.update_status(processmanager.s3_file_download, failed=True)

        processmanager.update_status(processmanager.s3_file_download, len(downloaded_files),len(downloaded_files))

    thread = MlThread(download_s3_thread)
    thread.start()
    return await get_process_status()


@router.get("/s3", status_code=200)
async def s3_func(function, response: Response):
    """s3_func - s3 functionality for model managment
    Args:
        function: str
    Returns:
    """
    models = []
    try:
        logger.info("Retrieving model list from s3::")
        if function == "models":
            s3_path = "bronze/gamechanger/models/"
            models = utils.get_models_list(s3_path)
        elif function == "data":
            s3_path = "bronze/gamechanger/ml-data/"
            models = utils.get_models_list(s3_path)
    except:
        logger.warning(f"Could not get model list from s3")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return models


## Post Methods ##


@router.post("/reloadModels", status_code=200)
async def reload_models(model_dict: dict, response: Response):
    """load_latest_models - endpoint for updating the transformer model
    Args:
        model_dict: dict; {"sentence": "bert...", "qexp": "bert...", "transformer": "bert..."}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
    """
    try:
        total = len(model_dict)
        processmanager.update_status(processmanager.reloading, 0, total)
        # put the reload process on a thread

        def reload_thread(model_dict):
            try:
                progress = 0
                if "sentence" in model_dict:
                    sentence_path = os.path.join(
                        Config.LOCAL_PACKAGED_MODELS_DIR, model_dict["sentence"]
                    )
                    # uses SENT_INDEX_PATH by default
                    logger.info("Attempting to load Sentence Transformer")
                    MODELS.initSentenceSearcher(sentence_path)
                    SENT_INDEX_PATH.value = sentence_path
                    progress += 1
                    processmanager.update_status(
                        processmanager.reloading, progress, total
                    )
                if "qexp" in model_dict:
                    qexp_name = os.path.join(
                        Config.LOCAL_PACKAGED_MODELS_DIR, model_dict["qexp"]
                    )
                    # uses QEXP_MODEL_NAME by default
                    logger.info("Attempting to load QE")
                    MODELS.initQE(qexp_name)
                    QEXP_MODEL_NAME.value = qexp_name
                    progress += 1
                    processmanager.update_status(
                        processmanager.reloading, progress, total
                    )

                if "topics" in model_dict:
                    topics_name = os.path.join(
                        Config.LOCAL_PACKAGED_MODELS_DIR, model_dict["topics"]
                    )

                    logger.info("Attempting to load Topics")
                    MODELS.initTopics(topics_name)
                    TOPICS_MODEL.value = topics_name
                    progress += 1
                    processmanager.update_status(
                        processmanager.reloading, progress, total
                    )

            except Exception as e:
                logger.warning(e)
                processmanager.update_status(processmanager.reloading, failed=True)

        args = {"model_dict": model_dict}
        thread = MlThread(reload_thread, args)
        thread.start()
    except Exception as e:
        logger.warning(e)

    return await get_process_status()


@router.post("/downloadCorpus", status_code=200)
async def download_corpus(corpus_dict: dict, response: Response):
    """load_latest_models - endpoint for updating the transformer model
    Args:
        model_dict: dict; {"sentence": "bert...", "qexp": "bert...", "transformer": "bert..."}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
    """
    try:
        logger.info("Attempting to download corpus from S3")
        # grabs the s3 path to the corpus from the post in "corpus"
        # then passes in where to dowload the corpus locally.
        if not corpus_dict["corpus"]:
            corpus_dict = S3_CORPUS_PATH
        args = {"s3_corpus_dir": corpus_dict["corpus"], "output_dir": CORPUS_DIR}
        logger.info(args)
        processmanager.update_status(processmanager.corpus_download)
        corpus_thread = MlThread(utils.get_s3_corpus, args)
        corpus_thread.start()
    except:
        logger.warning(f"Could not get corpus from S3")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return await get_process_status()


# Create a mapping between the training methods and input from the api
# Methods for all the different models we can train
# Defined outside the function so they arent recreated each time its called


def update_metadata(model_dict):
    logger.info("Attempting to update feature metadata")
    pipeline = Pipeline()
    model_dict["build_type"] = "meta"
    try:
        corpus_dir = model_dict["corpus_dir"]
    except:
        corpus_dir = CORPUS_DIR
    try:
        retriever = MODELS.sentence_searcher
        logger.info("Using pre-loaded SentenceSearcher")
    except:
        retriever = None
        logger.info("Setting SentenceSearcher to None")
    try:
        meta_steps = model_dict["meta_steps"]
    except:
        meta_steps = [
            "pop_docs",
            "combined_ents",
            "rank_features",
            "update_sent_data",
        ]
    args = {
        "meta_steps": meta_steps,
        "corpus_dir": corpus_dir,
        "retriever": retriever,
    }
    pipeline.run(
        build_type=model_dict["build_type"],
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


def finetune_sentence(model_dict):
    logger.info("Attempting to finetune the sentence transformer")
    try:
        testing_only = model_dict["testing_only"]
    except:
        testing_only = False
    args = {
        "batch_size": model_dict["batch_size"],
        "epochs": model_dict["epochs"],
        "warmup_steps": model_dict["warmup_steps"],
        "testing_only": testing_only,
    }
    pipeline.run(
        build_type="sent_finetune",
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


def train_sentence(model_dict):
    logger.info("Attempting to start sentence pipeline")
    try:
        corpus_dir = model_dict["corpus_dir"]
    except:
        corpus_dir = CORPUS_DIR
    if not os.path.exists(corpus_dir):
        logger.warning(f"Corpus is not in local directory {str(corpus_dir)}")
        raise Exception("Corpus is not in local directory")
    args = {
        "corpus": corpus_dir,
        "encoder_model": model_dict["encoder_model"],
        "gpu": bool(model_dict["gpu"]),
        "upload": bool(model_dict["upload"]),
        "version": model_dict["version"],
    }
    logger.info(args)
    pipeline.run(
        build_type=model_dict["build_type"],
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


def train_qexp(model_dict):
    logger.info("Attempting to start qexp pipeline")
    args = {
        "model_id": model_dict["model_id"],
        "validate": bool(model_dict["validate"]),
        "upload": bool(model_dict["upload"]),
        "version": model_dict["version"],
    }
    pipeline.run(
        build_type=model_dict["build_type"],
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


def run_evals(model_dict):
    logger.info("Attempting to run evaluation")
    args = {
        "model_name": model_dict["model_name"],
        "eval_type": model_dict["eval_type"],
        "sample_limit": model_dict["sample_limit"],
        "validation_data": model_dict["validation_data"],
    }
    pipeline.run(
        build_type=model_dict["build_type"],
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


def train_topics(model_dict):
    logger.info("Attempting to train topic model")
    logger.info(model_dict)
    args = {"sample_rate": model_dict["sample_rate"], "upload": model_dict["upload"]}
    pipeline.run(
        build_type=model_dict["build_type"],
        run_name=datetime.now().strftime("%Y%m%d"),
        params=args,
    )


training_switch = {
    "sentence": train_sentence,
    "qexp": train_qexp,
    "sent_finetune": finetune_sentence,
    "eval": run_evals,
    "meta": update_metadata,
    "topics": train_topics,
}


@router.post("/trainModel", status_code=200)
async def train_model(model_dict: dict, response: Response):
    """load_latest_models - endpoint for updating the transformer model
    Args:
        model_dict: dict; {"encoder_model":"msmarco-distilbert-base-v2", "gpu":true, "upload":false,"version": "v5"}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
    """
    try:

        build_type = model_dict.get("build_type")
        training_method = training_switch.get(build_type)

        if not training_method:
            raise Exception(f"No training method mapped for build type {build_type}")

        # Set the training method to be loaded onto the thread
        training_thread = MlThread(training_method, args={"model_dict": model_dict})
        training_thread.start()

    except:
        logger.warning(f"Could not train/evaluate the model")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return await get_process_status()
