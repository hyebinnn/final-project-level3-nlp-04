import re
import six
import numpy as np
import torch
from konlpy.tag import Mecab
from nltk.translate.bleu_score import corpus_bleu, SmoothingFunction
from rouge_score import scoring
from transformers import GPT2LMHeadModel
from sentence_transformers import SentenceTransformer 
from sklearn.metrics.pairwise import cosine_similarity
from rouge_utils import *


class RougeScorer(scoring.BaseScorer):
    def __init__(self, rouge_types):
        self.rouge_types = rouge_types
        self.tokenizer = Mecab()
        
    def score(self, references, predictions):
        ref_tokens = self.tokenizer.morphs(references)
        pred_tokens = self.tokenizer.morphs(predictions)
        result = {}
        
        for rouge_type in self.rouge_types:
            # ROUGE-L
            if rouge_type == "rougeL":
                scores = score_lcs(ref_tokens, pred_tokens)
            # ROUGE-N
            elif re.match(r"rouge[0-9]$", six.ensure_str(rouge_type)):
                n = int(rouge_type[5:]) # ex) rouge1 => 1
                if n <= 0:
                    raise ValueError(f"rougen requires positive n: {rouge_type}")
                ref_ngrams = create_ngrams(ref_tokens, n)
                pred_ngrams = create_ngrams(pred_tokens, n)
                scores = score_ngrams(ref_ngrams, pred_ngrams)
            else:
                raise ValueError(f"Invalid rouge type: {rouge_type}")
            result[rouge_type] = scores
        
        return result


def calc_corpus_bleu(predictions, references):
    references = [[ref] for ref in references]
    sf = SmoothingFunction(epsilon=1e-12).method1
    b1 = corpus_bleu(references, predictions, weights=(1.0 / 1.0,), smoothing_function=sf)
    b2 = corpus_bleu(references, predictions, weights=(1.0 / 2.0, 1.0 / 2.0), smoothing_function=sf)
    b3 = corpus_bleu(references, predictions, weights=(1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), smoothing_function=sf)
    b4 = corpus_bleu(references, predictions, weights=(1.0 / 4.0, 1.0 / 4.0, 1.0 / 4.0, 1.0 / 4.0),
                     smoothing_function=sf)
    return b1, b2, b3, b4


def bleu_score(predictions, references):
    mecab = Mecab()
    predictions = [mecab.morphs(pred) for pred in predictions]
    references = [mecab.morphs(ref) for ref in references]
    cbleu1, cbleu2, cbleu3, cbleu4 = calc_corpus_bleu(predictions, references)
    matrix = {
        'bleu1': cbleu1,
        'bleu2': cbleu2,
        'bleu3': cbleu3,
        'bleu4': cbleu4,
    }
    return matrix


def rdass_score(inputs, predictions, references):
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')

    V_d = model.encode(inputs)
    V_r = model.encode(references)
    V_p = model.encode(predictions)

    s_pr = cosine_similarity(V_p, V_r)
    s_pd = cosine_similarity(V_p, V_d)

    RDASS = (s_pr + s_pd) / 2
    RDASS_mean = RDASS.diagonal().mean()

    return RDASS_mean


def postprocess_text(preds, labels):
    preds = [pred.strip() for pred in preds]
    labels = [label.strip() for label in labels]
    return preds, labels


def compute(predictions, references):
    # ROUGE-N(unigram, bigram), ROUGE-L 측정
    rouge_types = ["rouge1", "rouge2", "rougeL"]
    scorer = RougeScorer(rouge_types=rouge_types)
    aggregator = scoring.BootstrapAggregator()
    
    for ref, pred in zip(references, predictions):
        aggregator.add_scores(scorer.score(ref, pred))
        
    result = aggregator.aggregate()
    return result


def compute_metrics(diary, preds, labels, tokenizer):
    # post-processing
    preds, labels = postprocess_text(preds, labels)
    
    # ROUGE score 계산
    result = compute(predictions=preds, references=labels)
    
    # median scores 추출
    result = {key: value.mid.fmeasure * 100 for key, value in result.items()}

    # BLEU Score 
    len_decoded_labels = len(labels)
    bleu_score_list_1 = np.zeros(len_decoded_labels)
    bleu_score_list_2 = np.zeros(len_decoded_labels)
    bleu_score_list_3 = np.zeros(len_decoded_labels)
    bleu_score_list_4 = np.zeros(len_decoded_labels)

    for i in range(len_decoded_labels):
        matrix = bleu_score([preds[i]], [labels[i]])
        bleu_score_list_1[i] = matrix['bleu1']
        bleu_score_list_2[i] = matrix['bleu2']
        bleu_score_list_3[i] = matrix['bleu3']
        bleu_score_list_4[i] = matrix['bleu4']
        
    result['bleu1'] = np.mean(bleu_score_list_1) * 100
    result['bleu2'] = np.mean(bleu_score_list_2) * 100
    result['bleu3'] = np.mean(bleu_score_list_3) * 100
    result['bleu4'] = np.mean(bleu_score_list_4) * 100

    #RDASS score 계산
    result['rdass'] = rdass_score(diary, preds, labels)

    prediction_lens = [len(tokenizer.encode(pred)) for pred in preds]
    result["gen_len"] = np.mean(prediction_lens)
    result = {k: round(v, 4) for k, v in result.items()}
    
    return result


def get_model_func(config, args, config_args):
    config.min_length = config_args.min_length
    config.no_repeat_ngram_size = config_args.no_repeat_ngram_size
    config.early_stopping = config_args.early_stopping
    config.length_penalty = config_args.length_penalty
    config.num_labels = config_args.num_labels
    config.num_beams = config_args.num_beams 

    model = GPT2LMHeadModel.from_pretrained(args.model_name_or_path, config=config)
    return model


def preprocess_logits_for_metrics(logits, labels):
    """
    Original Trainer may have a memory leak. 
    This is a workaround to avoid storing too many tensors that are not needed.
    """
    pred_ids = torch.argmax(logits[0], dim=-1)
    return pred_ids, labels 