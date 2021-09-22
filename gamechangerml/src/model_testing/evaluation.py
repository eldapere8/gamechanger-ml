import os
import numpy as np
import pandas as pd
import csv
import math
from datetime import datetime
from gamechangerml.src.search.sent_transformer.model import SentenceEncoder, SentenceSearcher, SimilarityRanker
from gamechangerml.src.search.QA.QAReader import DocumentReader as QAReader
from gamechangerml.src.search.query_expansion.qe import QE
from gamechangerml.src.search.query_expansion.utils import remove_original_kw
from gamechangerml.configs.config import QAConfig, EmbedderConfig, SimilarityConfig, QexpConfig, ValidationConfig
from gamechangerml.src.utilities.text_utils import normalize_answer, get_tokens
from gamechangerml.src.utilities.test_utils import *
from gamechangerml.src.model_testing.validation_data import SQuADData, NLIData, MSMarcoData, QADomainData, RetrieverGSData, QEXPDomainData
from gamechangerml.api.utils.pathselect import get_model_paths
from gamechangerml.src.model_testing.metrics import *
from gamechangerml.api.utils.logger import logger
import signal
import torch

retriever_k = EmbedderConfig.MODEL_ARGS['n_returns'] # k

init_timer()
model_path_dict = get_model_paths()
LOCAL_TRANSFORMERS_DIR = model_path_dict["transformers"]
SENT_INDEX_PATH = model_path_dict["sentence"]

class TransformerEvaluator():

    def __init__(self, transformer_path=LOCAL_TRANSFORMERS_DIR, use_gpu=False):

        self.transformer_path = transformer_path
        if use_gpu and torch.cuda.is_available():
            self.use_gpu = use_gpu
        else:
            self.use_gpu = False

class QAEvaluator(TransformerEvaluator):

    def __init__(
        self, 
        model_name, 
        qa_type, 
        nbest,
        null_threshold,
        model=None,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        data_name=None
        ):

        super().__init__(transformer_path, use_gpu)

        self.model_name = model_name
        self.model_path = os.path.join(transformer_path, model_name)
        if model:
            self.model = model
        else:
            self.model = QAReader(transformer_path, model_name, qa_type, nbest, null_threshold, use_gpu)
        self.data_name=data_name

    def compare(self, prediction, query):
        '''Compare predicted to expected answers'''

        exact_match = 0
        partial_match = 0 # true positive
        true_negative = 0
        false_negative = 0
        false_positive = 0

        if prediction['text'] == '':
            if query['null_expected'] == True:
                exact_match = partial_match = true_negative = 1
            else:
                false_negative = 1
        elif query['null_expected'] == True:
            false_positive = 1
        else:
            clean_pred = normalize_answer(prediction['text'])
            clean_answers = set([normalize_answer(i['text']) for i in query['expected']])
            if clean_pred in clean_answers:
                exact_match = partial_match = 1
            else:
                for i in clean_answers:
                    if i in clean_pred:
                        partial_match = 1
                    elif clean_pred in i:
                        partial_match = 1
            false_positive = 1 - partial_match
        
        return exact_match, partial_match, true_negative, false_negative, false_positive

    def predict(self, data, eval_path):
        '''Get answer predictions'''

        columns = [
            'index',
            'queries',
            'actual_answers',
            'predicted_answer',
            'exact_match',
            'partial_match',
            'true_negative',
            'false_negative',
            'false_positive'
        ]

        query_count = 0

        csv_filename = os.path.join(eval_path, timestamp_filename(self.data_name, '.csv'))
        with open(csv_filename, 'w') as csvfile: 
            csvwriter = csv.writer(csvfile)  
            csvwriter.writerow(columns)

            for query in data.queries:
                signal.alarm(20)
                try:
                    logger.info("Q-{}: {}".format(query_count, query['question']))
                    actual = query['expected']
                    context = query['search_context']
                    if type(context) == str:
                        context = [context]
                    prediction = self.model.answer(query['question'], context)[0]
                    exact_match, partial_match, true_negative, false_negative, false_positive = self.compare(prediction, query)
                
                    row = [[
                            str(query_count),
                            str(query['question']),
                            str(actual),
                            str(prediction),
                            str(exact_match),
                            str(partial_match),
                            str(true_negative),
                            str(false_negative),
                            str(false_positive)
                        ]]
                    csvwriter.writerows(row)
                    query_count += 1
                except TimeoutException:
                    logger.info("Query timed out before answer")
                    query_count += 1
                    continue
                else:
                    signal.alarm(0)

        return pd.read_csv(csv_filename)

    def eval(self, data, eval_path):
        '''Get evaluation stats across predicted/expected answer comparisons'''

        df = self.predict(data, eval_path)

        num_queries = df['queries'].nunique()
        if num_queries > 0:
            exact_match = np.round(np.mean(df['exact_match'].to_list()), 2)
            partial_match = np.round(np.mean(df['partial_match'].to_list()), 2)
            true_positives = df['partial_match'].map(int).sum()
            true_negatives = df['true_negative'].map(int).sum()
            false_positives = df['false_positive'].map(int).sum()
            false_negatives = df['false_negative'].map(int).sum()
            precision = true_positives / (true_positives + false_positives)
            recall = true_positives / (true_positives + false_negatives)
            f1 = 2 * ((precision * recall) / (precision + recall))
        else:
            exact_match = partial_match = precision = recall = f1 = 0
        user = get_user(logger)

        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model_name,
            "validation_data": self.data_name,
            "query_count": clean_nans(num_queries),
            "exact_match_accuracy": clean_nans(exact_match),
            "partial_match_accuracy": clean_nans(partial_match),
            "precision": precision,
            "recall": recall,
            "f1": f1
        }

        file = "_".join(["qa_eval", self.data_name])
        output_file = timestamp_filename(file, '.json')
        save_json(output_file, eval_path, agg_results)

        return agg_results

class SQuADQAEvaluator(QAEvaluator):

    def __init__(
        self, 
        model_name, 
        qa_type, 
        nbest,
        null_threshold,
        model=None,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        sample_limit=None,
        data_name='squad'
        ):

        super().__init__(model_name, qa_type, nbest, null_threshold, model, transformer_path, use_gpu, data_name)

        self.data = SQuADData(sample_limit)
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_squad'))
        self.results = self.eval(data=self.data, eval_path=self.eval_path)

class IndomainQAEvaluator(QAEvaluator):

    def __init__(
        self, 
        model_name, 
        qa_type, 
        nbest,
        null_threshold,
        model=None,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        data_name='domain'
        ):

        super().__init__(model_name, qa_type, nbest, null_threshold, model, transformer_path, use_gpu, data_name)

        self.data = QADomainData()
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_gc'))
        self.results = self.eval(data=self.data, eval_path=self.eval_path)


class RetrieverEvaluator(TransformerEvaluator):

    def __init__(
            self, 
            encoder_model_name,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            use_gpu=False
        ):

        super().__init__(transformer_path, use_gpu)

        self.encoder_model_name = encoder_model_name
        self.model_path = os.path.join(encoder_model_name, transformer_path)

    def make_index(self, encoder, corpus_path):

        return encoder.index_documents(corpus_path)

    def predict(self, data, index, retriever, eval_path, k):

        columns = [
            'index',
            'queries',
            'top_expected_ids',
            'hits',
            'true_positives',
            'false_positives',
            'false_negatives',
            'true_negatives',
            'reciprocal_rank',
            'average_precision',
            'precision@{}'.format(k),
            'recall@{}'.format(k)
        ]
        fname = index.split('/')[-1]
        csv_filename = os.path.join(eval_path, timestamp_filename(fname, '.csv'))
        with open(csv_filename, 'w') as csvfile:
            csvwriter = csv.writer(csvfile)  
            csvwriter.writerow(columns) 

            ## collect metrics for each query made + results generated
            query_count = 0
            tp = 0
            tn = 0
            fp = 0
            fn = 0
            total_expected = 0
            for idx, query in data.queries.items(): 
                logger.info("Q-{}: {}".format(query_count, query))
                doc_texts, doc_ids, doc_scores = retriever.retrieve_topn(query) ## returns results ordered highest - lowest score
                if index != 'msmarco_index':
                    doc_ids = ['.'.join(i.split('.')[:-1]) for i in doc_ids]
                expected_ids = data.relations[idx] # collect the expected results (ground truth)
                if type(expected_ids) == str:
                    expected_ids = [expected_ids]
                    len_ids = len(expected_ids)

                total_expected += len(expected_ids)
                ## collect ordered metrics
                recip_rank = reciprocal_rank(doc_ids, expected_ids)
                avg_p = average_precision(doc_ids, expected_ids)
                
                ## collect non-ordered metrics
                hits = []
                true_pos = 0
                false_pos = 0 # no negative samples to test against
                for eid in doc_ids:
                    hit = {}
                    if eid in expected_ids: ## we have a hit
                        rank = doc_ids.index(eid)
                        hit['rank'] = rank
                        hit['matching_text'] = data.collection[eid]
                        hit['score'] = doc_scores[rank]
                        hits.append(hit)
                        true_pos += 1
                if len(doc_ids) < k: # if there are not k predictions, there are pred negatives
                    remainder = k - len(doc_ids)
                    false_neg = np.min(len([i for i in expected_ids if i not in doc_ids], remainder))
                    true_neg = np.min((k - len(expected_ids)), (k - len(doc_ids)))
                else: # if there are k predictions, there are no predicted negatives
                    false_neg = true_neg = 0
                fn += false_neg
                tn += true_neg
                tp += true_pos
                
                ## save metrics to csv
                row = [[
                    str(query_count),
                    str(query),
                    str(expected_ids),
                    str(hits),
                    str(true_pos),
                    str(false_pos),
                    str(false_neg),
                    str(true_neg),
                    str(recip_rank), # reciprocal rank
                    str(avg_p) # average precision
                ]]
                csvwriter.writerows(row)
                query_count += 1

        return pd.read_csv(csv_filename), tp, tn, fp, fn, total_expected
        
    def eval(self, data, index, retriever, data_name, eval_path, model_name, k=retriever_k):
        
        df, tp, tn, fp, fn, total_expected = self.predict(data, index, retriever, eval_path, k)
        num_queries = df['queries'].shape[0]
        if num_queries > 0:
            _mrr = get_MRR(list(df['reciprocal_rank'].map(float)))
            _map = get_MAP(list(df['average_precision'].map(float)))
            recall = get_recall(true_positives=tp, false_negatives=(total_expected - tp))
            #precision = get_precision(true_positives=tp, false_positives=fp)
            #f1 = get_f1(precision, recall)
            #accuracy = get_accuracy(true_positives=tp, true_negatives=tn, total=total_expected)
        else:
            _mrr = _map = recall = 0

        user = get_user(logger)
        
        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": model_name,
            "validation_data": data_name,
            "query_count": num_queries,
            "k": k,
            "MRR": _mrr,
            "mAP": _map,
            "recall": recall
        }

        file = "_".join(["retriever_eval", data_name])
        output_file = timestamp_filename(file, '.json')
        save_json(output_file, eval_path, agg_results)

        return agg_results

class MSMarcoRetrieverEvaluator(RetrieverEvaluator):

    def __init__(
            self, 
            encoder_model_name,
            sim_model_name,
            overwrite,
            min_token_len,
            return_id,
            verbose,
            n_returns,
            encoder=None,
            retriever=None,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            index='msmarco_index',
            use_gpu=False,
            data_name='msmarco'
        ):

        super().__init__(transformer_path, encoder_model_name, use_gpu)
        logger.info("Model path: {}".format(self.model_path))
        self.index_path = os.path.join(os.path.dirname(transformer_path), index)
        if not os.path.exists(self.index_path):  
            logger.info("Making new embeddings index at {}".format(str(self.index_path)))
            os.makedirs(self.index_path)
            if encoder:
                self.encoder=encoder
            else:
                self.encoder = SentenceEncoder(encoder_model_name=encoder_model_name, overwrite=overwrite, min_token_len=min_token_len, return_id=return_id, verbose=verbose, sent_index=self.index_path, use_gpu=use_gpu)
            self.make_index(encoder=self.encoder, corpus_path=None)
        self.data = MSMarcoData()
        if retriever:
            self.retriever = retriever
        else:
            self.retriever = SentenceSearcher(sim_model_name=sim_model_name, encoder_model_name=encoder_model_name, n_returns=n_returns, index_path=self.index_path, transformers_path=transformer_path)
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_msmarco'))
        logger.info("Evals path: {}".format(self.eval_path))
        self.results = self.eval(data=self.data, index=index, retriever=self.retriever, data_name=data_name, eval_path=self.eval_path, model_name=encoder_model_name)

class IndomainRetrieverEvaluator(RetrieverEvaluator):

    def __init__(
            self,
            encoder_model_name,
            sim_model_name,
            overwrite,
            min_token_len,
            return_id,
            verbose,
            n_returns,
            encoder=None,
            retriever=None,
            data_name='gold_standard',
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            index=SENT_INDEX_PATH,
            use_gpu=False
        ):

        super().__init__(transformer_path, encoder_model_name, use_gpu)

        self.model_path = os.path.join(transformer_path, encoder_model_name)
        if not index:
            self.index_path = os.path.join(os.path.dirname(transformer_path), 'test_sent_index')
            logger.info("Making new embeddings index at {}".format(str(self.index_path)))
            if not os.path.exists(self.index_path):
                os.makedirs(self.index_path)
            if encoder:
                self.encoder=encoder
            else:
                self.encoder = SentenceEncoder(encoder_model_name=encoder_model_name, overwrite=overwrite, min_token_len=min_token_len, return_id=return_id, verbose=verbose, sent_index=self.index_path, use_gpu=use_gpu)
            self.make_index(encoder=self.encoder, corpus_path=ValidationConfig.DATA_ARGS['test_corpus_dir'])
        else:
            self.index_path = os.path.join(os.path.dirname(transformer_path), index)
            #self.index_path = 'gamechangerml/models/sent_index_20210715'
        self.doc_ids = open_txt(os.path.join(self.index_path, 'doc_ids.txt'))
        self.data = RetrieverGSData(self.doc_ids)
        logger.info("SENT INDEX PATH: {}".format(self.index_path))
        if retriever:
            self.retriever=retriever
        else:
            self.retriever = SentenceSearcher(sim_model_name=sim_model_name, encoder_model_name=encoder_model_name, n_returns=n_returns, index_path=self.index_path, transformers_path=transformer_path)
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_gc'))
        self.results = self.eval(data=self.data, index=index, retriever=self.retriever, data_name=data_name, eval_path=self.eval_path, model_name=encoder_model_name)

class SimilarityEvaluator(TransformerEvaluator):

    def __init__(
            self, 
            sim_model_name,
            model=None,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            use_gpu=False
        ):

        super().__init__(transformer_path, use_gpu)

        if model:
            self.model = model
        else:
            self.model = SimilarityRanker(sim_model_name, transformer_path)
        self.sim_model_name = sim_model_name
        self.model_path = os.path.join(transformer_path, sim_model_name)

    def eval(self, predictions, eval_path):
        '''Get summary stats of predicted vs. expected ranking for NLI'''

        df = predictions
        csv_filename = os.path.join(eval_path, timestamp_filename('nli_eval', '.csv'))
        df.to_csv(csv_filename)

        # get overall stats
        all_accuracy = np.round(df['match'].mean(), 2)
        top_accuracy = np.round(df[df['expected_rank']==0]['match'].mean(), 2)
        num_queries = df['promptID'].nunique()
        num_sentence_pairs = df.shape[0]

        user = get_user(logger)

        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.sim_model_name,
            "validation_data": "NLI",
            "query_count": clean_nans(num_queries),
            "pairs_count": clean_nans(num_sentence_pairs),
            "all_accuracy": clean_nans(all_accuracy),
            "top_accuracy": clean_nans(top_accuracy)
        }

        output_file = timestamp_filename('sim_model_eval', '.json')
        save_json(output_file, eval_path, agg_results)

        return agg_results

class NLIEvaluator(SimilarityEvaluator):

    def __init__(
        self, 
        sim_model_name,
        model=None,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        sample_limit=None,
        use_gpu=False
    ):

        super().__init__(sim_model_name, model, transformer_path, use_gpu)

        self.data = NLIData(sample_limit)
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_nli'))
        self.results = self.eval(predictions=self.predict_nli(), eval_path=self.eval_path)

    def predict_nli(self):
        '''Get rank predictions from similarity model'''

        df = self.data.sample_csv
        ranks = {}
        count = 0
        for i in df['promptID'].unique():
            subset = df[df['promptID']==i]
            iddict = dict(zip(subset['sentence2'], subset['pairID']))
            texts = [i for i in iddict.keys()]
            ids = [i for i in iddict.values()]
            query = self.data.query_lookup[i]
            logger.info("S-{}: {}".format(count, query))
            rank = 0
            for result in self.model.re_rank(query, texts, ids):
                match_id = result['id']
                ranks[match_id] = rank
                rank +=1

            count += 1
        
        df['predicted_rank'] = df['pairID'].map(ranks)
        df.dropna(subset = ['predicted_rank'], inplace = True)
        df['predicted_rank'] = df['predicted_rank'].map(int)
        df['match'] = np.where(df['predicted_rank']==df['expected_rank'], 1, 0)

        return df

class GCSimEvaluator(SimilarityEvaluator):

    def __init__(
        self,
        sim_model_name,
        model=None,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False
    ):
        ## TODO: add in-domain GC dataset for testing sim model (using pos/neg samples/ranking from search)

        super().__init__(sim_model_name, model, transformer_path, use_gpu)

        #self.data = NLIData(sample_limit)
        self.eval_path = check_directory(os.path.join(self.model_path, 'evals_gc'))
        #self.results = self.eval(predictions=self.predict_nli(), eval_path=self.eval_path)


class QexpEvaluator():

    def __init__(
        self, 
        qe_model_dir,
        qe_files_dir,
        method,
        topn,
        threshold,
        min_tokens,
        model=None
        ):

        self.model_path = qe_model_dir
        if model:
            self.QE = model
        else:
            self.QE = QE(qe_model_dir, qe_files_dir, method)

        self.data = QEXPDomainData().data
        self.topn = topn
        self.threshold = threshold
        self.min_tokens = min_tokens
        self.results = self.eval()
        
    def predict(self):

        columns = ['query', 'expected', 'received', 'any_match']
        csv_filename = os.path.join(self.model_path, timestamp_filename('qe_domain', '.csv'))
        with open(csv_filename, 'w') as csvfile:
            csvwriter = csv.writer(csvfile)  
            csvwriter.writerow(columns) 
        
            query_count = 0
            num_matching = 0
            num_expected = 0
            num_results = 0
            for query, expected in self.data.items():
                logger.info("Query {}: {}".format(str(query_count), query))
                results = self.QE.expand(query, self.topn, self.threshold, self.min_tokens)
                results = remove_original_kw(results, query)
                num_results += len(results)
                num_matching += len(set(expected).intersection(results)) 
                num_expected += np.min([len(results), self.topn])
                any_match = bool(num_matching)
                row = [[
                        str(query),
                        str(expected),
                        str(results),
                        str(any_match)
                    ]]
                csvwriter.writerows(row)
                query_count += 1
        
        precision = num_matching / num_results
        recall = num_matching / num_expected

        return pd.read_csv(csv_filename), precision, recall

    def eval(self):

        df, precision, recall = self.predict()

        # get overall stats
        num_queries = df.shape[0]

        user = get_user(logger)

        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model_path.split('/')[-1],
            "validation_data": "QE_domain",
            "query_count": clean_nans(num_queries),
            "precision": clean_nans(precision),
            "recall": clean_nans(recall)
        }

        output_file = timestamp_filename('qe_model_eval', '.json')
        save_json(output_file, self.model_path, agg_results)

        return agg_results