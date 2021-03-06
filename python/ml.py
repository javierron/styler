import java_lang_utils as jlu
import tensorflow as tf
from functools import reduce
import numpy as np
from tensorflow import keras
from javalang import tokenizer
from tqdm import tqdm
import os
import random
import json
import sys
import pprint
import glob
import matplotlib
import java_lang_utils
import shutil
import uuid
from termcolor import colored
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from difflib import Differ
import configparser

from core import *
import token_utils

pp = pprint.PrettyPrinter(indent=4)

# tf.logging.set_verbosity(tf.logging.INFO)
config = configparser.ConfigParser()
config.read('config.ini')

__synthetic_dir = config['DEFAULT']['SYNTHETIC_DIR']
__protocol = 'protocol1'

def get_dataset_dir(dataset):
    return f'{__synthetic_dir}/dataset/{__protocol}/{dataset}'

def get_tokenized_dir(dataset):
    return f'/home/benjaminl/Documents/kth/data/synthetic_only_formatting/{dataset}'

def get_sub_set_dir(dataset, sub_set):
    return f'{get_dataset_dir(dataset)}/{sub_set}'


def get_token_value(token):
    if isinstance(token, tokenizer.Keyword):
        return token.value
    if isinstance(token, tokenizer.Separator):
        return token.value

    if isinstance(token, tokenizer.Comment):
        return token.__class__.__name__
    if isinstance(token, tokenizer.Literal):
        return token.__class__.__name__
    if isinstance(token, tokenizer.Operator):
        return token.value
        if token.is_infix():
            return "InfixOperator"
        if token.is_prefix():
            return "PrefixOperator"
        if token.is_postfix():
            return "PostfixOperator"
        if token.is_assignment():
            return "AssignmentOperator"

    return token.__class__.__name__

def get_space_value(space):
    if space[0] == 0:
        return f'{space[1]}_SP'
    else:
        result = f'{space[0]}_NL'
        if space[1] == 0:
            pass
        elif space[1] > 0:
            result += f'_{space[1]}_ID'
        else:
            result += f'_{-space[1]}_DD'
        return result

#Deprecated
def build_vocabulary(files):
    count = {}
    tokenized_files = [ jlu.tokenize_with_white_space(jlu.open_file(path)) for path in files ]
    whitespace_id = set()

    threshold = 30

    for spaces, tokens in tokenized_files:
        whitespace_id = set(spaces) | whitespace_id
        for token in tokens:
            name = get_token_value(token)
            if not name in count:
                count[name] = 0
            count[name] += 1

    litterals = list(filter(lambda key: count[key] >= threshold, count.keys()))
    litterals = { key:value for key, value in zip(litterals, range(len(litterals))) }

    whitespace_id = { key:value for key, value in zip(whitespace_id, range(len(whitespace_id))) }

    len_litterals = len(litterals)
    len_whitespace = len(whitespace_id)
    vec_size = len_litterals + 1 + len_whitespace

    def get_vector(space, token):
        vector = np.array([0]*vec_size)
        if get_token_value(token) in litterals:
            vector[litterals[get_token_value(token)]] = 1
        else:
            vector[len_litterals] = 1
        vector[len_litterals + 1 + whitespace_id[space]] = 1
        return vector

    print(litterals.keys())

    return get_vector, whitespace_id

def tokenize_file_to_repair(file_path, error):
    spaces, tokens = jlu.tokenize_with_white_space(jlu.open_file(file_path))

    info = {}

    token_started = False
    token_line_start = -1
    token_line_end = -1
    count = 0

    tokens_errored = []
    n_lines = 6

    start = len(tokens)
    end = 0

    from_token = 0
    to_token = 0

    for token, space in zip(tokens, spaces):
        if token.position[0] >= int(error['line']) - n_lines and token.position[0] <= int(error['line']) + n_lines :
            start = min(count, start)
            end = max(count, end)
        if not token_started and int(error['line']) == token.position[0]:
            token_started = True
            token_line_start = count
        if token_started and  int(error['line']) < token.position[0]:
            token_started = False
            token_line_end = count
        count += 1
    start = max(0, start - 2)
    end = min(len(tokens), end + 2)
    if token_line_end == -1:
        token_line_end = token_line_start

    # print(error)

    if 'column' in error and error['type'] != 'OneStatementPerLine':
        errored_token_index = -1
        around = 10
        for token, index in zip(tokens,range(len(tokens))):
            if token.position[0] <= int(error['line']) and token.position[1] <= int(error['column']):
                errored_token_index = index
        from_token = max(0, errored_token_index - around)
        to_token = min(len(tokens), errored_token_index + 1 + around)
    else:
        around = 2
        around_after = 13
        errored_token_index = -1
        if token_line_start != -1:
            from_token = max(start, token_line_start - around)
            to_token = min(end, token_line_end + around_after + 1)
        else:
            errored_token_index = -1
            around = 2
            around_after = 18
            for token, index in zip(tokens,range(len(tokens))):
                if token.position[0] < int(error['line']):
                    errored_token_index = index
            from_token = max(0, errored_token_index - around)
            to_token = min(len(tokens), errored_token_index + 1 + around_after)
    tokens_errored_in_tag = []
    for token, space in zip(tokens[from_token:to_token], spaces[from_token:to_token]):
        tokens_errored_in_tag.append(get_token_value(token))
        tokens_errored_in_tag.append(get_space_value(space))


    for token, space in zip(tokens[start:from_token], spaces[start:from_token]):
        tokens_errored.append(get_token_value(token))
        tokens_errored.append(get_space_value(space))
    tokens_errored.append(f'<{error["type"]}>')
    for token, space in zip(tokens[from_token:to_token], spaces[from_token:to_token]):
        tokens_errored.append(get_token_value(token))
        tokens_errored.append(get_space_value(space))
    tokens_errored.append(f'</{error["type"]}>')
    for token, space in zip(tokens[to_token:end], spaces[to_token:end]):
        tokens_errored.append(get_token_value(token))
        tokens_errored.append(get_space_value(space))

    info['from_token'] = from_token
    info['to_token'] = to_token
    info['start'] = start
    info['end'] = end
    info['error'] = error
    info['tokens_errored_in_tag'] = tokens_errored_in_tag

    return tokens_errored, info

def tokenize_errored_file_model2(file, file_orig, error):

    # else:
    #     for token, space in zip(tokens[start:end], spaces[start:end]):
    #         tokens_errored.append(get_token_value(token))
    #         tokens_errored.append(get_space_value(space))
    #     tokens_errored.append(f'<{error["type"]}>')
    #     tokens_errored.append(f'</{error["type"]}>')

    tokens_errored, info = tokenize_file_to_repair(file, error)

    tokens_errored_in_tag = info['tokens_errored_in_tag']
    from_token = info['from_token']
    to_token = info['to_token']

    spaces, tokens = jlu.tokenize_with_white_space(jlu.open_file(file_orig))
    tokens_correct = []

    for token, space in zip(tokens[from_token:to_token], spaces[from_token:to_token]):
        tokens_correct.append(get_token_value(token))
        tokens_correct.append(get_space_value(space))

    if len(tokens_errored_in_tag) != len(tokens_correct):
        print("WHAAAAATT")
    info['count_diff'] = 0
    for t_A, t_B in zip(tokens_errored_in_tag, tokens_correct):
        if t_A != t_B:
            info['count_diff'] += 1

    return tokens_errored, tokens_correct, tokens_errored_in_tag, info

def tokenize_errored_file(file, file_orig, error):
    spaces, tokens = jlu.tokenize_with_white_space(jlu.open_file(file))
    token_started = False
    from_token = -1
    to_token = -1
    count = 0
    tokens_errored = []
    n_lines = 5
    for token, space in zip(tokens, spaces):
        if not token_started and int(error['line']) == token.position[0]:
            token_started = True
            tokens_errored.append(f'<{error["type"]}>')
            from_token = count
        if token_started and  int(error['line']) < token.position[0]:
            token_started = False
            tokens_errored.append(f'</{error["type"]}>')
            to_token = count
        if token.position[0] >= int(error['line']) - n_lines and token.position[0] <= int(error['line']) + n_lines :
            tokens_errored.append(get_token_value(token))
            tokens_errored.append(get_space_value(space))
        count += 1
    if from_token == -1:
        tokens_errored.append(f'<{error["type"]}>')
        tokens_errored.append(f'</{error["type"]}>')

    spaces, tokens = jlu.tokenize_with_white_space(jlu.open_file(file_orig))
    tokens_correct = []
    for token, space in zip(tokens[from_token:to_token], spaces[from_token:to_token]):
        tokens_correct.append(get_token_value(token))
        tokens_correct.append(get_space_value(space))
    return tokens_errored, tokens_correct

def whatever(dir, folder, id, only_formatting=False):
    dir = os.path.join(dir, f'./{folder}/{id}')
    file_name = [ java_file for java_file in glob.glob(f'{dir}/*.java') if 'orig' not in java_file ][0].split('/')[-1].split('.')[0]
    file = f'{dir}/{file_name}.java'
    file_orig = f'{dir}/{file_name}-orig.java'
    error_file = f'{dir}/metadata.json'
    error = open_json(error_file)
    return tokenize_errored_file_model2(file, file_orig, error)

def merge_IOs(sub_set, ids, target):
    dir = f'{target}/{sub_set}'
    for type in ['I', 'O', 'E']:
        with open(os.path.join(target, f'{sub_set}-{type}.txt'), 'w+') as f:
            for id in tqdm(ids, desc=f'merging {type}s...'):
                f.write(open_file(os.path.join(dir, f'{id}-{type}.txt')))
                f.write('\n')

def get_length_and_vocabulary(folder):
    files = os.listdir(folder)
    Is = [ file for file in files if 'I.txt' in file ]
    Os = [ file for file in files if 'O.txt' in file ]
    max_length = 0
    in_length = []
    out_length = []
    max_out_length = 0
    vocabulary = set()
    for file in tqdm(Is, desc='Is'):
        tokens = open_file(os.path.join(folder, file)).split(' ')
        if len(tokens)<1000:
            in_length.append(len(tokens))
        vocabulary = vocabulary | set(tokens)
    for file in tqdm(Os, desc='Os'):
        tokens = open_file(os.path.join(folder, file)).split(' ')
        out_length.append(len(tokens))
        vocabulary = vocabulary | set(tokens)
    return vocabulary, in_length, out_length

def print_max_length_and_vocabulary(folder):
    vocabulary, in_length, out_length = get_length_and_vocabulary(folder)
    print(vocabulary)
    print(f'Vocabulary size {len(vocabulary)}')
    print(f'Max in lenght : {max(in_length)}')
    print(f'Max out lenght : {max(out_length)}')
    n_bins = 20

    fig, axs = plt.subplots(1, 2, sharey=True, tight_layout=True)

    # We can set the number of bins with the `bins` kwarg
    axs[0].hist(in_length, bins=n_bins)
    axs[1].hist(out_length, bins=n_bins)

    plt.show()

def gen_IO(dir, target, only_formatting=False):
    create_dir(target)
    # dir = get_dataset_dir(dataset)
    sub_sets = ['learning', 'validation', 'testing']
    diffs = []
    weirdos = []
    for sub_set in sub_sets:
        sub_set_dir = os.path.join(dir, f'./{sub_set}')
        if not os.path.exists(sub_set_dir):
            continue
        target_sub_set = f'{target}/{sub_set}'
        create_dir(target_sub_set)
        synthesis_error_ids = list_folders(sub_set_dir)
        synthesis_error_ids = sorted(synthesis_error_ids, key=int)
        for id in tqdm(synthesis_error_ids, desc=f'{dir.split("/")[-1]}/{sub_set}'):
            tokens_errored, tokens_correct, tokens_errored_in_tag, info = whatever(dir, sub_set, id)
            if only_formatting:
                tokens_correct = tokens_correct[1::2]
                tokens_errored_in_tag = tokens_errored_in_tag[1::2]
            save_file(target_sub_set, f'{id}-I.txt', " ".join(tokens_errored))
            save_file(target_sub_set, f'{id}-O.txt', " ".join(tokens_correct))
            save_file(target_sub_set, f'{id}-E.txt', " ".join(tokens_errored_in_tag))
            save_json(target_sub_set, f'{id}-info.json', info)
            diffs.append(info['count_diff'])
            if info['count_diff'] == 2:
                weirdos.append(f'{sub_set}/{id}')
        merge_IOs(sub_set, synthesis_error_ids, target)
    shutil.copy('./utils/send.sh', target)
    # print(weirdos)

def vectorize_file(path, vectorizer):
    spaces, tokens = jlu.tokenize_with_white_space(jlu.open_file(path))

    result = []
    for ws, t in zip(spaces, tokens):
        result.append(vectorizer(ws, t))

    return result

def print_diff(stringA, stringB):
    diffs = token_diff(stringA, stringB)
    count = 0
    for token in diffs:
        if token.startswith(' '):
            print(token[2:], end=' ')
            count += 1
        elif token.startswith('-'):
            if is_odd(count):
                print(colored(token[2:], 'blue'), end=' ')
            else:
                print(colored(token[2:], 'green'), end=' ')
            count += 1

    count = 0
    for token in diffs:
        if token.startswith(' '):
            print(token[2:], end=' ')
            count += 1
        elif token.startswith('+'):
            if is_odd(count):
                print(colored(token[2:], 'blue'), end=' ')
            else:
                print(colored(token[2:], 'red'), end=' ')
            count += 1
    print('')

def token_diff(stringA, stringB):
    d = Differ()
    tokensA = stringA.split(' ')
    tokensB = stringB.split(' ')
    result = list(d.compare(tokensA, tokensB))
    return result

def beam_search(target_dir, pred_dir, n=1, only_formatting=False):
    target_file = open(target_dir, 'r')
    pred_file = open(pred_dir, 'r')
    count = { i:0 for i in range(n) }
    count_whitepace = { i:0 for i in range(n) }
    total = 0
    target = target_file.readline()
    not_predicted = {}
    while target:
        preds = [ pred_file.readline() for i in range(n) ]
        select_whitespace = lambda x: " ".join(x.split(' ')[1::2])
        preds_whitespace = [ select_whitespace(pred) for pred in preds ]
        target_whitespace = select_whitespace(target)
        if target_whitespace in preds_whitespace:
            count_whitepace[preds_whitespace.index(target_whitespace)] += 1
            if preds_whitespace.index(target_whitespace) != 0:
                for pred in preds:
                    print_diff(target, pred)
                print('')
                print('')
        if target in preds:
            count[preds.index(target)] += 1
        else:
            not_predicted[target] = preds
        total += 1
        target = target_file.readline()
    target_file.close()
    pred_file.close()
    pp.pprint({ i:c/total for i,c in count.items() })
    pp.pprint(sum(count.values()) / total)
    pp.pprint({ i:c/total for i,c in count_whitepace.items() })
    pp.pprint(sum(count_whitepace.values()) / total)

    # pp.pprint(not_predicted)

def match_input_to_source(source, error_info, input):
    whitespace, tokens = jlu.tokenize_with_white_space(source)
    start = error_info['start']
    end = error_info['end']

    sub_sequence = tokens[start:end]
    ws_sub_sequence = whitespace[start:end]

    result = []
    count = 0
    ws_count = 0
    for input_token in input.split(' '):
        if token_utils.is_whitespace_token(input_token):
            result.append((input_token, get_space_value(ws_sub_sequence[ws_count])))
            ws_count += 1
        elif input_token.startswith('<') and input_token.endswith('>'):
            result.append((input_token, input_token))
        else:
            result.append((input_token, sub_sequence[count].value))
            count += 1


    return result

def de_tokenize(errored_source, error_info, new_tokens, tabulations, only_formatting=False):
    whitespace, tokens = jlu.tokenize_with_white_space(errored_source)
    from_token = error_info['from_token']
    to_token = error_info['to_token']


    if only_formatting:
        new_white_space_tokens = new_tokens
    else:
        new_white_space_tokens = new_tokens[1::2]
    # print(new_white_space_tokens)
    new_white_space = [ token_utils.whitespace_token_to_tuple(token) for token in new_white_space_tokens ]
    # print(new_white_space)

    # whitespace[from_token:to_token] = new_white_space
    # whitespace[from_token:min(from_token + len(new_white_space),to_token)] = new_white_space[:min(to_token - from_token, len(new_white_space))]
    for index in range(min(to_token - from_token, len(new_white_space))):
        whitespace[from_token + index] = new_white_space[index]

    result = jlu.reformat(whitespace, tokens, tabulations=tabulations)

    if 'error' in error_info:
        line = int(error_info['error']['line'])
        return jlu.mix_sources(errored_source, result, line-1, to_line=line+1)
    else:
        return result #jlu.mix_sources(errored_source, result, tokens[from_token].position[0], to_line=tokens[to_token].position[0])
    # return jlu.mix_sources(errored_source, result, tokens[from_token].position[0], to_line=tokens[to_token].position[0])

def get_predictions(dataset, n, id):
    tokenized_dir = get_tokenized_dir(dataset)
    return open_file(os.path.join(tokenized_dir, f'pred_{n}.txt')).split('\n')[(id*n):(id*n + n)]

def get_I(dataset, type, id):
    tokenized_dir = get_tokenized_dir(dataset)
    return open_file(os.path.join(tokenized_dir, f'{type}/{id}-I.txt'))

def get_O(dataset, type, id):
    tokenized_dir = get_tokenized_dir(dataset)
    return open_file(os.path.join(tokenized_dir, f'{type}/{id}-O.txt'))

def get_line(file, line):
    return open_file(file).split('\n')[line]

def get_error_filename_and_content(dataset, id):
    synthetic_dir = os.path.join(get_dataset_dir(dataset), f'testing/{id}')
    errored_file_name = [ file for file in  os.listdir(synthetic_dir) if (file.endswith('.java') and 'orig' not in file ) ][0]
    errored_source = open_file(os.path.join(synthetic_dir, errored_file_name))
    return errored_file_name, errored_source

def get_orig_filename_and_content(dataset, id):
    synthetic_dir = os.path.join(get_dataset_dir(dataset), f'testing/{id}')
    orig_file_name = [ file for file in  os.listdir(synthetic_dir) if (file.endswith('.java') and 'orig' in file ) ][0]
    orig_source = open_file(os.path.join(synthetic_dir, orig_file_name))
    return orig_file_name, orig_source

def get_error_info(dataset, id):
    tokenized_dir = get_tokenized_dir(dataset)
    tokenized_testing_dir = f'{tokenized_dir}/testing'
    error_info = open_json(os.path.join(tokenized_testing_dir, f'{id}-info.json'))
    return error_info

def de_tokenize_file(dataset, n, id, only_formatting=False):
    # get the tokenization informations
    error_info = get_error_info(dataset, id)
    # Get the errored file
    errored_file_name, errored_source = get_error_filename_and_content(dataset, id)
    # get the new tokens
    new_tokens_predictions = get_predictions(dataset, n, id)
    tabulations = False
    if dataset == 'spoon':
        tabulations = True
    tokenized_results = [
        de_tokenize(errored_source, error_info, new_tokens.split(' '), tabulations, only_formatting=only_formatting)
        for new_tokens in new_tokens_predictions
    ]

    return tokenized_results, errored_file_name

def de_tokenize_dataset(dataset, n, only_formatting=False):
    target = f'./experiments/ml/{dataset}/styler'
    # for id in [529]:
    for id in tqdm(range(1000)):
        try:
            tokenized_results, errored_file_name = de_tokenize_file(dataset, n, id, only_formatting=only_formatting)
            for index in range(n):
                new_file_folder = os.path.join(target, f'batch_{index}/{id}')
                create_dir(new_file_folder)
                save_file(new_file_folder, errored_file_name, tokenized_results[index])
        except:
            pass
    move_parse_exception_files(target, f'./experiments/ml/{dataset}/bin')

def get_aligned_strings(tokens, n=2):
    result = ['']*n
    for t in tokens:
        l = max([len(e) for e in t])
        pattern = f'{{:{l}}} '
        if token_utils.is_whitespace_token(t[0]):
            equals = True
            for token_to_compare in t[1:]:
                equals = equals and (token_to_compare == t[0])
            if not equals:
                pattern = colored(pattern, color='red')

        for i, content in enumerate(t):
            result[i] = result[i] + pattern.format(content)
    return result

def print_aligned_strings(strings):
    line_lenght = int(os.popen('stty size', 'r').read().split()[1])
    length = max([ len(s) for s in strings])
    for from_char in range(0,length, line_lenght):
        for string in strings:
            print(string[from_char:(from_char + line_lenght)])
        print()

def main(args):
    if sys.argv[2] == 'all':
        dataset_list = list_folders(get_dataset_dir(''))
    else:
        dataset_list = sys.argv[2:]

    if len(args) >= 2 and args[1] == 'gen':
        target = get_tokenized_dir('')
        for dataset in dataset_list:
            gen_IO(get_dataset_dir(dataset), os.path.join(target, dataset), only_formatting=True)
    if len(args) >= 2 and args[1] == 'info':
        folder = args[2]
        print_max_length_and_vocabulary(folder)
    if args[1] == 'de-tokenize':
        for dataset in tqdm(dataset_list, desc='de tokenize'):
            de_tokenize_dataset(dataset, n=5, only_formatting=True)
    if len(args) == 4 and args[1] == 'beam':
        n = int(args[3])
        dataset = args[2]
        data_folder = get_tokenized_dir(dataset)
        pred_path = f'{data_folder}/pred_{n}.txt'
        testing_O_path = f'{data_folder}/testing-O.txt'
        beam_search(testing_O_path, pred_path, n=n, only_formatting=True)
    if len(args) == 5 and args[1] == 'get':
        n = int(args[3])
        id = int(args[4])
        dataset = args[2]
        input = get_I(dataset, 'testing', id)
        predictions = get_predictions(dataset, n, id)
        output = get_O(dataset, 'testing', id)
        error_info = get_error_info(dataset, id)
        orig_file_name, orig_source = get_orig_filename_and_content(dataset, id)
        print_aligned_strings(get_aligned_strings(match_input_to_source(orig_source, error_info, input)))

if __name__ == "__main__":
    main(sys.argv)
