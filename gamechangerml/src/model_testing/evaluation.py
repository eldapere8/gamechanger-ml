import os
import numpy as np
import pandas as pd
import csv
import math
from datetime import datetime
from gamechangerml.src.search.sent_transformer.model import SentenceEncoder, SentenceSearcher, SimilarityRanker
from gamechangerml.src.search.QA.QAReader import DocumentReader as QAReader
from gamechangerml.configs.config import QAConfig, EmbedderConfig, SimilarityConfig, ValidationConfig
from gamechangerml.src.utilities.model_helper import *
from gamechangerml.src.model_testing.validation_data import SQuADData, NLIData, MSMarcoData, QADomainData, RetrieverGSData
from gamechangerml.api.utils.pathselect import get_model_paths
from gamechangerml.api.utils.logger import logger
import signal
import torch

signal.signal(signal.SIGALRM, timeout_handler)

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
        model=None,
        config=QAConfig.MODEL_ARGS,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        data_name=None
        ):

        super().__init__(transformer_path, use_gpu)

        self.model_name = config['model_name']
        if model:
            self.model = model
        else:
            self.model = QAReader(os.path.join(self.transformer_path, self.model_name), config['qa_type'], config['nbest'], config['null_threshold'], self.use_gpu)
        self.model_path = os.path.join(transformer_path, config['model_name'])
        self.data_name=data_name

    def compare(self, prediction, query):
        '''Compare predicted to expected answers'''

        exact_match = 0
        partial_match = 0

        if prediction['text'] == '':
            if query['null_expected'] == True:
                exact_match = 1
                partial_match = 1
        else:
            clean_pred = normalize_answer(prediction['text'])
            clean_answers = set([normalize_answer(i['text']) for i in query['expected']])
            if clean_pred in clean_answers:
                exact_match = 1
                partial_match = 1
            else:
                for i in clean_answers:
                    if i in clean_pred:
                        partial_match = 1
                    elif clean_pred in i:
                        partial_match = 1
        
        return exact_match, partial_match

    def predict(self, data):
        '''Get answer predictions'''

        columns = [
            'index',
            'queries',
            'actual_answers',
            'predicted_answer',
            'exact_match',
            'partial_match'
        ]

        query_count = 0

        csv_filename = os.path.join(self.model_path, timestamp_filename(self.data_name, '.csv'))
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
                    exact_match, partial_match = self.compare(prediction, query)
                
                    row = [[
                            str(query_count),
                            str(query['question']),
                            str(actual),
                            str(prediction),
                            str(exact_match),
                            str(partial_match)
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

    def eval(self, data):
        '''Get evaluation stats across predicted/expected answer comparisons'''

        df = self.predict(data)

        num_queries = df['queries'].nunique()
        exact_match = np.round(np.mean(df['exact_match'].to_list()), 2)
        partial_match = np.round(np.mean(df['partial_match'].to_list()), 2)

        user = get_user(logger)

        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model_name,
            "validation_data": self.data_name,
            "query_count": num_queries,
            "proportion_exact_match": exact_match,
            "proportion_partial_match": partial_match,
        }

        file = "_".join(["qa_eval", self.data_name])
        output_file = timestamp_filename(file, '.json')
        save_json(output_file, self.model_path, agg_results)

        return agg_results

class SQuADQAEvaluator(QAEvaluator):

    def __init__(
        self, 
        model=None,
        config=QAConfig.MODEL_ARGS,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        sample_limit=None,
        data_name='squad'
        ):

        super().__init__(model, config, transformer_path, use_gpu, data_name)

        self.data = SQuADData(sample_limit)
        self.results = self.eval(data=self.data)

class IndomainQAEvaluator(QAEvaluator):

    def __init__(
        self, 
        model=None,
        config=QAConfig.MODEL_ARGS,
        transformer_path=LOCAL_TRANSFORMERS_DIR,
        use_gpu=False,
        data_name='domain'
        ):

        super().__init__(model, config, transformer_path, use_gpu, data_name)

        self.data = QADomainData()
        self.results = self.eval(data=self.data)


class RetrieverEvaluator(TransformerEvaluator):

    def __init__(
            self, 
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            encoder_config=EmbedderConfig.MODEL_ARGS,
            use_gpu=False
        ):

        super().__init__(transformer_path, use_gpu)

        self.model_name = encoder_config['model_name']
        self.model_path = os.path.join(self.transformer_path, self.model_name)

    def make_index(self, encoder, corpus_path):

        return encoder.index_documents(corpus_path)

    def predict(self, data, index, retriever):

        columns = [
            'index',
            'queries',
            'top_expected_ids',
            'hits',
            'proportion_hits',
            'any_hits'
        ]
        fname = index.split('/')[-1]
        csv_filename = os.path.join(self.model_path, timestamp_filename(fname, '.csv'))
        with open(csv_filename, 'w') as csvfile:
            csvwriter = csv.writer(csvfile)  
            csvwriter.writerow(columns) 

            query_count = 0
            for idx, query in data.queries.items(): 
                logger.info("Q-{}: {}".format(query_count, query))
                doc_texts, doc_ids, doc_scores = retriever.retrieve_topn(query)
                if index != 'msmarco_index':
                    doc_ids = ['.'.join(i.split('.')[:-1]) for i in doc_ids]
                expected_ids = data.relations[idx]
                if type(expected_ids) == str:
                    expected_ids = [expected_ids]
                    len_ids = len(expected_ids)
                hits = []
                total = 0
                for eid in expected_ids:
                    hit = {}
                    if eid in doc_ids:
                        hit['match'] = 1
                        rank = doc_ids.index(eid)
                        hit['rank'] = rank
                        hit['matching_text'] = data.collection[eid]
                        hit['score'] = doc_scores[rank]
                        hits.append(hit)
                        total += 1
                    else:
                        hit['match'] = 0
                        hit['rank'] = 'NA'
                        hit['matching_text'] = 'NA'
                        hit['score'] = 'NA'
                        hits.append(hit)
                mean = total / len(expected_ids)
                any_hits = math.ceil(mean)

                row = [[
                    str(query_count),
                    str(query),
                    str(expected_ids),
                    str(hits),
                    str(mean),
                    str(any_hits)
                ]]
                csvwriter.writerows(row)
                query_count += 1

        return pd.read_csv(csv_filename)
        
    def eval(self, data, index, retriever, data_name):
        
        df = self.predict(data, index, retriever)

        num_queries = df['queries'].shape[0]
        proportion_in_top_10 = np.round(np.mean(df['proportion_hits'].to_list()), 2)
        proportion_any_hits = np.round(np.mean(df['any_hits'].to_list()), 2)

        user = get_user(logger)
        
        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model_name,
            "validation_data": data_name,
            "query_count": num_queries,
            "proportion_in_top_10": proportion_in_top_10,
            "proportion_any_hits": proportion_any_hits
        }

        file = "_".join(["retriever_eval", data_name])
        output_file = timestamp_filename(file, '.json')
        save_json(output_file, self.model_path, agg_results)

        return agg_results

class MSMarcoRetrieverEvaluator(RetrieverEvaluator):

    def __init__(
            self, 
            encoder=None,
            retriever=None,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            index='msmarco_index',
            encoder_config=EmbedderConfig.MODEL_ARGS, 
            similarity_config=SimilarityConfig.MODEL_ARGS,
            use_gpu=False,
            data_name='msmarco'
        ):

        super().__init__(transformer_path, encoder_config, use_gpu)

        self.index_path = os.path.join(os.path.dirname(transformer_path), index)
        if not os.path.exists(self.index_path):  
            logger.info("Making new embeddings index at {}".format(str(self.index_path)))
            os.makedirs(self.index_path)
            if encoder:
                self.encoder=encoder
            else:
                self.encoder = SentenceEncoder(encoder_config, self.index_path, use_gpu)
            self.make_index(encoder=self.encoder, corpus_path=None)
        self.data = MSMarcoData()
        if retriever:
            self.retriever = retriever
        else:
            self.retriever = SentenceSearcher(self.index_path, transformer_path, encoder_config, similarity_config)
        self.results = self.eval(data=self.data, index=index, retriever=self.retriever, data_name=data_name)

class IndomainRetrieverEvaluator(RetrieverEvaluator):

    def __init__(
            self, 
            encoder=None,
            retriever=None,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            index=SENT_INDEX_PATH,
            encoder_config=EmbedderConfig.MODEL_ARGS, 
            similarity_config=SimilarityConfig.MODEL_ARGS,
            use_gpu=False,
            corpus_path=ValidationConfig.DATA_ARGS['test_corpus_dir'], 
            data_name='gold_standard'
        ):

        super().__init__(transformer_path, encoder_config, use_gpu)

        self.index_path = index
        if not os.path.exists(self.index_path):  
            logger.info("Making new embeddings index at {}".format(str(self.index_path)))
            os.makedirs(self.index_path)
            if encoder:
                self.encoder=encoder
            else:
                self.encoder = SentenceEncoder(encoder_config, self.index_path, use_gpu)
            self.make_index(encoder=self.encoder, corpus_path=corpus_path)
        self.doc_ids = open_txt(os.path.join(self.index_path, 'doc_ids.txt'))
        self.data = RetrieverGSData(self.doc_ids)
        if retriever:
            self.retriever=retriever
        else:
            self.retriever = SentenceSearcher(self.index_path, transformer_path, encoder_config, similarity_config)
        self.results = self.eval(data=self.data, index=index, retriever=self.retriever, data_name=data_name)

class SimilarityEvaluator(TransformerEvaluator):

    def __init__(
            self, 
            model=None,
            transformer_path=LOCAL_TRANSFORMERS_DIR,
            model_config=SimilarityConfig.MODEL_ARGS, 
            sample_limit=None,
            use_gpu=False
        ):

        super().__init__(transformer_path, use_gpu)

        if model:
            self.model = model
        else:
            self.model = SimilarityRanker(model_config, transformer_path)
        self.model_name = model_config['model_name']
        self.model_path = os.path.join(transformer_path, model_config['model_name'])
        self.data = NLIData(sample_limit)
        self.results = self.eval_nli()

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
        df['match'] = np.where(df['predicted_rank']==df['expected_rank'], True, False)

        return df

    def eval_nli(self):
        '''Get summary stats of predicted vs. expected ranking for NLI'''

        # create csv of predictions
        df = self.predict_nli()
        csv_filename = os.path.join(self.model_path, timestamp_filename('nli_eval', '.csv'))
        df.to_csv(csv_filename)

        # get overall stats
        proportion_all_match = np.round(df['match'].value_counts(normalize = True)[True], 2)
        proportion_top_match = np.round(df[df['expected_rank']==0]['match'].value_counts(normalize = True)[True], 2)
        num_queries = df['promptID'].nunique()
        num_sentence_pairs = df.shape[0]

        user = get_user(logger)

        agg_results = {
            "user": user,
            "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": self.model_name,
            "validation_data": "NLI",
            "query_count": num_queries,
            "pairs_count": num_sentence_pairs,
            "proportion_all_match": proportion_all_match,
            "proportion_top_match": proportion_top_match
        }

        output_file = timestamp_filename('sim_model_eval', '.json')
        save_json(output_file, self.model_path, agg_results)

        return agg_results