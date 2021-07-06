from fastapi import APIRouter, Response, status
# must import sklearn first or you get an import error
from gamechangerml.src.search.query_expansion.utils import remove_original_kw
from gamechangerml.src.featurization.keywords.extract_keywords import get_keywords
from gamechangerml.api.fastapi.version import __version__

# from gamechangerml.models.topic_models.tfidf import bigrams, tfidf_model
from gamechangerml.src.featurization.summary import GensimSumm
from gamechangerml.api.fastapi.settings import *

router = APIRouter()

@router.post("/transformerSearch", status_code=200)
async def transformer_infer(query: dict, response: Response) -> dict:
    """transformer_infer - endpoint for transformer inference
    Args:
        query: dict; format of query
            {"query": "test", "documents": [{"text": "...", "id": "xxx"}, ...]
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
        results: dict; results of inference
    """
    logger.debug("TRANSFORMER - predicting query: " + str(query))
    results = {}
    try:
        results = sparse_reader.predict(query)
        logger.info(results)
    except Exception:
        logger.error(f"Unable to get results from transformer for {query}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    return results


@router.post("/textExtractions", status_code=200)
async def textExtract_infer(query: dict, extractType: str, response: Response) -> dict:
    """textExtract_infer - endpoint for sentence transformer inference
    Args:
        query: dict; format of query
            {"text": "i am text"}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
        extractType: topics, keywords, or summary
    Returns:
        results: dict; results of inference
    """
    results = {}
    try:
        query_text = query["text"]
        results["extractType"] = extractType
        if extractType == "topics":
            logger.debug("TOPICS - predicting query: " + str(query))
            # topics = tfidf_model.get_topics(
            #    topic_processing(query_text, bigrams), topn=5
            # )
            # logger.info(topics)
            # results["extracted"] = topics
        elif extractType == "summary":
            summary = GensimSumm(
                query_text, long_doc=False, word_count=30
            ).make_summary()
            results["extracted"] = summary
        elif extractType == "keywords":
            logger.debug("keywords - predicting query: " + str(query))
            results["extracted"] = get_keywords(query_text)

    except Exception:
        logger.error(f"Unable to get extract text for {query}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    return results


@router.post("/transSentenceSearch", status_code=200)
async def trans_sentence_infer(
    query: dict, response: Response, num_results: int = 5
) -> dict:
    """trans_sentence_infer - endpoint for sentence transformer inference
    Args:
        query: dict; format of query
            {"text": "i am text"}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
        results: dict; results of inference
    """
    logger.debug("SENTENCE TRANSFORMER - predicting query: " + str(query))
    results = {}
    try:
        query_text = query["text"]
        results = sentence_trans.search(query_text, n_returns=num_results)
        logger.info(results)
    except Exception:
        logger.error(
            f"Unable to get results from sentence transformer for {query}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    return results


@router.post("/questionAnswer", status_code=200)
async def qa_infer(query: dict, response: Response) -> dict:
    """qa_infer - endpoint for sentence transformer inference
    Args:
        query: dict; format of query, text must be concatenated string
            {"query": "what is the navy",
            "search_context":["pargraph 1", "xyz"]}
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
        results: dict; results of inference
    """
    logger.debug("QUESTION ANSWER - predicting query: " + str(query["query"]))
    results = {}

    try:
        query_text = query["query"]
        query_context = query["search_context"]
        start = time.perf_counter()
        answers = qa_model.answer(query_text, query_context)
        end = time.perf_counter()
        logger.info(answers)
        logger.info(f"time: {end - start:0.4f} seconds")
        results["answers"] = answers
        results["question"] = query_text

    except Exception:
        logger.error(f"Unable to get results from QA model for {query}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    return results

@router.post("/expandTerms", status_code=200)
async def post_expand_query_terms(termsList: dict, response: Response) -> dict:
    """post_expand_query_terms - endpoint for expand query terms
    Args:
        termsList: dict;
        Response: Response class; for status codes(apart of fastapi do not need to pass param)
    Returns:
        expansion_dict: dict; expanded dictionary of terms
    """
    termsList = termsList["termsList"]
    expansion_dict = {}
    # logger.info("[{}] expanded: {}".format(user, termsList))

    logger.info(f"Expanding: {termsList}")
    try:
        for term in termsList:
            term = unquoted(term)
            expansion_list = query_expander.expand(term)
            # turn word pairs into search phrases since otherwise it will just search for pages with both words on them
            # removing original word from the return terms unless it is combined with another word
            logger.info(f"original expanded terms: {expansion_list}")
            finalTerms = remove_original_kw(expansion_list, term)
            expansion_dict[term] = ['"{}"'.format(exp) for exp in finalTerms]
            logger.info(f"-- Expanded {term} to \n {finalTerms}")
        return expansion_dict
    except:
        logger.error(f"Error with query expansion on {termsList}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

def unquoted(term):
    """unquoted - unquotes string
    Args:
        term: string
    Returns:
        term: without quotes
    """
    if term[0] in ["'", '"'] and term[-1] in ["'", '"']:
        return term[1:-1]
    else:
        return term