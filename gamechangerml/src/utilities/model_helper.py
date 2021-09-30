import os
import string
import re
import json
import numpy as np
from datetime import date, datetime

from gamechangerml.api.utils.logger import logger
import torch

# https://stackoverflow.com/questions/25027122/break-the-function-after-certain-time/25027182
class TimeoutException(Exception):   # Custom exception class
    pass

# https://stackoverflow.com/questions/25027122/break-the-function-after-certain-time/25027182
def timeout_handler(signum, frame):   # Custom signal handler
    raise TimeoutException

# from create_embeddings.py
def get_user(logger):
    try:
        user = os.environ.get("GC_USER", default="root")
        if (user =="root"):
            user = str(os.getlogin())
    except Exception as e:
        user = "unknown"
        logger.info("Could not get system user")
        logger.info(e)

def save_json(filename, path, data):

    filepath = os.path.join(path, filename)
    with open(filepath, "w") as outfile: 
        return json.dump(data, outfile)

def open_json(filename, path):
    with open(os.path.join(path, filename)) as f:
        return json.load(f)

def open_jsonl(filename, path):

    with open(os.path.join(path, filename), 'r') as json_file:
        json_list = list(json_file)

    data = []
    for json_str in json_list:
        result = json.loads(json_str)
        data.append(result)
    
    return data

def open_txt(filepath):
    with open(filepath, "r") as fp:
        return fp.readlines()

def timestamp_filename(filename, extension):
    today = date.today()
    formatted = '_'.join([filename, today.strftime("%Y-%m-%d")])
    return formatted + extension

def check_directory(directory):

    if not os.path.exists(directory):
        logger.info("Creating new directory {}".format(directory))
        os.makedirs(directory)

    return directory

def make_timestamp_directory(base_dir):

    now = datetime.now()
    new_dir = os.path.join(base_dir, now.strftime("%Y-%m-%d_%H%M%S"))
    if not os.path.exists(new_dir):
        logger.info("Creating new directory {}".format(new_dir))
        os.makedirs(new_dir)
    else:
        logger.info("Directory {} already exists.".format(new_dir))
    
    return new_dir

# stackoverflow
class CustomJSONizer(json.JSONEncoder):
    def default(self, obj):
        return super().encode(bool(obj)) \
            if isinstance(obj, np.bool_) \
            else super().default(obj)


# Source: https://rajpurkar.github.io/SQuAD-explorer/
def normalize_answer(s):
    """Lower text and remove punctuation, articles and extra whitespace."""
    def remove_articles(text):
        regex = re.compile(r'\b(a|an|the)\b', re.UNICODE)
        return re.sub(regex, ' ', text)
    def white_space_fix(text):
        return ' '.join(text.split())
    def remove_punc(text):
        exclude = set(string.punctuation)
        return ''.join(ch for ch in text if ch not in exclude)
    def lower(text):
        return text.lower()
    return white_space_fix(remove_articles(remove_punc(lower(s))))

def get_tokens(s):
  if not s: return []
  return normalize_answer(s).split()

# from sentence_transformers==2.0.0
#https://github.com/UKPLab/sentence-transformers/blob/master/sentence_transformers/util.py
def cos_sim(a, b):
    """
    Computes the cosine similarity cos_sim(a[i], b[j]) for all i and j.
    :return: Matrix with res[i][j]  = cos_sim(a[i], b[j])
    """
    if not isinstance(a, torch.Tensor):
        a = torch.tensor(a)

    if not isinstance(b, torch.Tensor):
        b = torch.tensor(b)

    if len(a.shape) == 1:
        a = a.unsqueeze(0)

    if len(b.shape) == 1:
        b = b.unsqueeze(0)

    a_norm = torch.nn.functional.normalize(a, p=2, dim=1)
    b_norm = torch.nn.functional.normalize(b, p=2, dim=1)
    return torch.mm(a_norm, b_norm.transpose(0, 1))

def update_dictionary(old_dict, new_additions, prefix):
    '''Update master dictionary of unique queries'''

    def make_ids(new_additions, last_count, prefix):
        '''Make UUIDs for new queries/docs'''
    
        new_dict = {}
        for i in new_additions:
            if i not in old_dict.values():
                last_count += 1
                myid = str(last_count)
                add = str(0) * ( 7 - len(myid))
                myid = prefix + add + myid 
                new_dict[myid] = i

        return new_dict

    if old_dict != {}:
        last_count = [re.sub(r'[A-Z]', '', i) for i in old_dict.keys()][-1]
    else:
        last_count = -1
    new_dict = make_ids(new_additions, last_count, prefix)
        
    return {**old_dict, **new_dict}

def map_ids(iddict, df, mapcol, idcol):
    '''Map IDs back to df'''

    reverse = {iddict[k]: k for k in iddict.keys()}
    col = 'ID_' + idcol
    df[col] = df[mapcol].map(reverse)

    return df

def update_meta_relations(metadata, df, query_col, return_col):
    '''Update dict with relations and metadata about each match'''
    
    df = df.sort_values(by = ['date'], ascending = False).sort_values(by = ['ID_key'])

    for x in df['ID_key'].unique():
        subset = df[df['ID_key']==x].copy()
        for i in subset['ID_value'].unique():
            subsubset = subset[subset['ID_value']==i]
            exact_matches = []
            for k in subsubset.index:
                em = {}
                em['exact_query'] = subsubset.loc[k, query_col]
                em['exact_result'] = subsubset.loc[k, return_col]
                em['source'] = subsubset.loc[k, 'source']
                em['date'] = subsubset.loc[k, 'date']
                exact_matches.append(em)
                
            if x in metadata.keys() and i in metadata[x]:
                metadata[x][i]['exact_matches'].extend(exact_matches)
            else:
                matchdict = {}
                matchdict['correct_match'] = subset['correct_match'].all()
                matchdict['last_match_date'] = list(subset['date'])[0]
                matchdict['exact_matches'] = exact_matches
            
            if x in metadata.keys():
                metadata[x][i] = matchdict
            else:
                searchdict = {}
                searchdict[i] = matchdict
                metadata[x] = searchdict
                
            metadata[x][i]['times_matched'] = len(metadata[x][i]['exact_matches'])
            
    return metadata
    
def filter_rels(metadata, min_correct_matches, max_results):
    '''Filter relations by criteria'''
    
    correct_rels = {}
    incorrect_rels = {}
    for key in metadata:
        acceptable_positive_results = []
        negative_results = []
        if max_results and len(metadata[key]) > max_results: # if we have more than n max results, skip this match
            logger.info(f"Skipping {key}: has {str(len(metadata[key]))} unique matches")
            continue
        for match in metadata[key]:
            result = metadata[key][match]
            sources = [i['source'] for i in result['exact_matches']]
            if result['correct_match'] == True:
                if 'matamo' in sources: # we trust matamo data
                    acceptable_positive_results.append(match)
                elif result['times_matched'] >= min_correct_matches: # only pull history matches occurring more than x times
                    acceptable_positive_results.append(match)
            elif result['correct_match'] == False:
                negative_results.append(match)

        if acceptable_positive_results != []:
            correct_rels[key] = acceptable_positive_results
        if negative_results != []:
            incorrect_rels[key] = negative_results
        
    return correct_rels, incorrect_rels