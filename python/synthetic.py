# -*- coding: utf-8 -*-

import java_lang_utils as jlu
import checkstyle
import subprocess
import os
from Corpus import *
import shutil
import random
import configparser
import sys
import glob
from tqdm import tqdm
import uuid
from functools import reduce
import java_lang_utils
import graph_plot
import copy
import threading

from core import *
import repair
import styler
import ml

config = configparser.ConfigParser()
config.read('config.ini')

class Synthetic_Checkstyle_Error:

    def __init__(self, dir):
        self.dir = dir
        self.id = int(dir.split('/')[-1])
        self.type = dir.split('/')[-2]
        self.metadata = None
        self.diff = None
        self.original = None
        self.errored = None
        self.file_name = glob.glob(f'{self.dir}/*.java')[0].split('/')[-1].split('.')[0]
        if 'orig' in self.file_name:
             self.file_name = self.file_name[:-5]

    def get_diff(self):
        if not self.diff:
            self.load_diff()
        return self.diff

    def get_count(self):
        diff = self.get_diff()
        plus = 0
        minus = 0
        for line in diff.split('\n'):
            if line.startswith('> '):
                plus += 1
            if line.startswith('< '):
                minus += 1
        return max(plus, minus)

    def get_metadata(self):
        if not self.metadata:
            self.load_metadata()
        return self.metadata

    def get_original(self):
        if not self.original:
            self.load_original()
        return self.original

    def get_errored(self):
        if not self.errored:
            self.load_errored()
        return self.errored

    def get_diff_path(self):
        return f'{self.dir}/diff.diff'

    def get_errored_path(self):
        return f'{self.dir}/{self.file_name}.java'

    def get_original_path(self):
        return f'{self.dir}/{self.file_name}-orig.java'

    def get_metadata_path(self):
        return f'{self.dir}/metadata.json'

    def load_diff(self):
        self.diff = open_file(self.get_diff_path())

    def load_metadata(self):
        self.metadata = open_json(self.get_metadata_path())

    def load_original(self):
        self.original = open_file(self.get_original_path())

    def load_errored(self):
        self.errored = open_file(self.get_errored_path())

__experiments_dir = './experiments/ml'
__base_dir = config['DEFAULT']['SYNTHETIC_DIR']

# def gen_ugly(corpus):
#     modifications = {}
#     for id, file in corpus.get_files().items():
#         if id not in modifications:
#             modifications[id] = {}
#         modifications[id][folder] = {}
#         for index in range(n):
#             modifications[id][folder][index] = java_lang_utils.gen_ugly( file[2], self.get_dir( os.path.join("./ugly/" + str(id) + "/{}/".format(folder) + str(index) + "/")), action)


def get_experiment_dir(id):
    return f'{__experiments_dir}/{id}'

def get_dir(dir):
    return os.path.join(__base_dir, dir)

__protocol = 'protocol1'

def get_repo_dir(repo):
    return get_dir(f'./dataset/{__protocol}/{repo}')

def get_repo_type_dir(repo, type):
    return get_dir(f'./dataset/{__protocol}/{repo}/{type}')

def get_synthetic_error_dir(repo, type, id):
    return get_dir(f'{get_repo_dir(repo)}/{type}/{id}')

def list_errors(repo):
    types = ('learning', 'validation', 'testing')
    result = []
    for type in types:
        result += [ get_synthetic_error_dir(repo, type, element) for element in list_elements(repo, type) ]
    return result

def list_elements(repo, type):
    dir = get_repo_type_dir(repo, type)
    if os.path.exists(dir):
        return [ element for element in os.listdir(dir) if os.path.isdir(get_synthetic_error_dir(repo, type, element)) ]
    else:
        return []


def list_folders(dir):
    return [ element for element in os.listdir(dir) if os.path.isdir(os.path.join(dir, element)) ]

def copy_originals(corpus, repo_name):
    folder = os.path.join(get_repo_dir(repo_name), './originals')
    create_dir(folder)
    for id, file in corpus.files.items():
        create_dir(f'{folder}/{id}')
        shutil.copyfile(file[2], f'{folder}/{id}/{file[0]}')
        # print(corpus.files[file])

injection_operator_types={
'insertion-space': (1,0,0,0,0),
'insertion-tab': (0,1,0,0,0),
'insertion-newline': (0,0,1,0,0),
'deletion-space': (0,0,0,1,0),
'deletion-newline': (0,0,0,0,1)
}

def run_diff(fileA, fileB):
    cmd = f'diff {fileA} {fileB}'
    # print(cmd)
    process = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE)
    output = process.communicate()[0]
    return output.decode("utf-8")

def gen_get_random_file(corpus, numbers):
    files = list(corpus.files.values())
    corpus_size = len(files)
    shuffle_list = random.sample(list(range(corpus_size)), corpus_size) # random.shuffled() shuffle the list and does not returned the shuffled list
    print(shuffle_list)
    total_numbers = sum(numbers.values())
    values = {}
    for goal in numbers.keys():
        to = round(numbers[goal]/total_numbers*corpus_size)
        values[goal] = shuffle_list[:to]
        shuffle_list = shuffle_list[to:]
    print(values)
    def get_file(goal):
        file = files[random.choice(values[goal])]
        # check if we can parse the file
        while not jlu.check_well_formed(file[2]):
            file = files[random.choice(values[goal])]
        return file
    return get_file

def gen_errored(corpus, get_random_corpus_file, repo_name, goal, id, target_dir):
    DEBUG = False
    folder = os.path.join(target_dir, f'./{goal}/{id}')
    file =  get_random_corpus_file(goal)
    file_dir = file[2]
    file_name = file[0].split('.')[0]
    done = False
    error = None
    ugly_file = ""
    max_attepts = 10
    attepts = 0
    while not done:
        if attepts >= max_attepts: # it is ugly but it i made in order to avoid the loop to get stuck
            file =  get_random_corpus_file(goal)
            file_dir = file[2]
            file_name = file[0].split('.')[0]
            attepts = 0
            continue
        if os.path.exists(folder):
            shutil.rmtree(folder)
        create_dir(folder)
        injection_operator = random.choice(list(injection_operator_types.keys()))
        ugly_file = os.path.join(folder, f'./{file_name}.java')
        modification = jlu.gen_ugly(file_dir, folder, modification_number=injection_operator_types[injection_operator])
        if DEBUG:
            print(modification)
        if not jlu.check_well_formed(ugly_file):
            if DEBUG:
                print('Not well formed')
            attepts = attepts + 1
            continue
        try:
            cs_result, number_of_errors = checkstyle.check(corpus.checkstyle, ugly_file)
        except:
            if DEBUG:
                print('Cant run checkstule')
            attepts = attepts + 1
            continue
        if number_of_errors != 1:
            if DEBUG:
                print(f'{number_of_errors} errors')
            attepts = attepts + 1
            continue
        spaces_original, tokens_original = jlu.tokenize_with_white_space(open_file(file_dir))
        spaces_errored, tokens_errored = jlu.tokenize_with_white_space(open_file(ugly_file))
        if len(tokens_original) != len(tokens_errored):
            if DEBUG:
                print(f'Not the same length : orig {len(tokens_original)} vs {len(tokens_errored)}')
            attepts = attepts + 1
            continue
        error = list(cs_result.values())[0]['errors'][0]
        done = True

    original_file = os.path.join(folder, f'./{file_name}-orig.java')
    if file_dir != original_file:
        shutil.copyfile(file_dir, original_file)
    save_file(folder, 'diff.diff', run_diff(original_file, ugly_file))

    report = {}
    report['injection_operator'] = injection_operator
    report['line'] = error['line']
    if 'column' in error:
        report['column'] = error['column']
    report['message'] = error['message']
    report['type'] = error['source'].split('.')[-1][:-5]

    save_json(folder, 'metadata.json', report)


def gen_dataset(corpus, numbers, target_dir=None):
    repo_name = corpus.name
    if target_dir is None:
        dir = get_repo_dir(repo_name)
    else:
        dir=target_dir
    if os.path.exists(dir):
        shutil.rmtree(dir)
    create_dir(dir)
    save_json(dir, 'repo.json', corpus.info)
    get_random_corpus_file = gen_get_random_file(corpus, numbers)
    shutil.copyfile(corpus.checkstyle, os.path.join(dir, f'./checkstyle.xml'))
    for goal, number in numbers.items():
        for i in tqdm(range(number), desc=f'{repo_name}/{goal}'):
            gen_errored(corpus, get_random_corpus_file, repo_name, goal, i, dir)
    # copy_originals(corpus, repo_name)


def gen_dataset_batch(corpus, numbers, batch_size=5, target_dir=None):
    repo_name = corpus.name
    if target_dir is None:
        dir = get_repo_dir(repo_name)
    else:
        dir=target_dir
    if os.path.exists(dir):
        shutil.rmtree(dir)
    create_dir(dir)
    save_json(dir, 'repo.json', corpus.info)
    get_random_corpus_file = gen_get_random_file(corpus, numbers)
    shutil.copyfile(corpus.checkstyle, os.path.join(dir, f'./checkstyle.xml'))
    # checkstyle_batch = gen_checkstyle_batch(batch_size, corpus.checkstyle)
    for goal, number in numbers.items():
        print(batch_size)
        def task(i):
            gen_errored(corpus, get_random_corpus_file, repo_name, goal, i, dir)
        start_pool(list(range(number)), batch_size, task)

def map_and_count(reducer, data):
    result = {}
    for element in map(reducer, data):
        if element not in result:
            result[element] = 0
        result[element] += 1
    return result


def load_repo(repo):
    return [ Synthetic_Checkstyle_Error(synthetic_error) for synthetic_error in list_errors(repo) ]

def check_token_length(repo):
    synthetic_errors = load_repo(repo)
    not_good = []
    for error in tqdm(synthetic_errors, desc=dataset):
        spaces_original, tokens_original = jlu.tokenize_with_white_space(error.get_original())
        spaces_errored, tokens_errored = jlu.tokenize_with_white_space(error.get_errored())
        if len(tokens_original) != len(tokens_errored):
            not_good.append({ 'type': error.type, 'id': error.id, 'error': error.get_metadata()['type'] })
    return not_good

def summary(repo):
    synthetic_errors = load_repo(repo)
    for error in synthetic_errors:
        if error.get_metadata()['type'] == 'EmptyBlock':
            print(error.dir)
    results = {}
    results['type_count'] = map_and_count(lambda x: x.get_metadata()['type'], synthetic_errors)
    results['operator_count'] = map_and_count(lambda x: x.get_metadata()['injection_operator'], synthetic_errors)
    results['file_count'] = map_and_count(lambda x: x.file_name, synthetic_errors)
    # print(results)
    save_json(get_repo_dir(repo), 'stats.json', results)
    return results

###  Experiment ####

def copy_uglies(from_dir, to_dir):
    create_dir(to_dir)
    uglies = [
        java_file for java_file in glob.glob(f'{from_dir}/*/*.java')
        if 'orig' not in java_file
    ]
    for file in tqdm(uglies, desc='Copy uglies'):
        id, file_name = file.split('/')[-2:]
        target = os.path.join(to_dir, id)
        create_dir(target)
        target_file = os.path.join(target, file_name)
        shutil.copy(file, target_file)
        # metadata
        metadata_file = file[:file.rfind('/')] + '/metadata.json'
        target_metadata = os.path.join(target, 'metadata.json')
        shutil.copy(metadata_file, target_metadata)


def with_index(iterator):
    return zip(iterator, range(len(iterator)))

def copy_origs(from_dir, to_dir):
    create_dir(to_dir)
    origs = set([
        file.split('/')[-1]
        for file in glob.glob(f'{from_dir}/*/*-orig.java')
    ])
    if len(origs) > 500:
        random.seed(a=hash("".join(from_dir.split('/')[-3:-1])))
        origs = random.sample(origs, k=500)
    for file_name, index in tqdm(with_index(origs), desc='Copy origs', total=len(origs)):
        file_dir = glob.glob(f'{from_dir}/*/{file_name}')[0]
        target = os.path.join(to_dir, str(index))
        create_dir(target)
        target_file = os.path.join(target, file_name)
        shutil.copy(file_dir, target_file)

def gen_experiment(dataset_name):
    dir = create_dir(get_repo_dir(dataset_name))
    experiment_id = dataset_name
    target = create_dir(get_experiment_dir(experiment_id))
    shutil.copy(os.path.join(dir, 'checkstyle.xml'), os.path.join(target, 'checkstyle.xml'))
    checkstyle_suppressions_file_dir = os.path.join(dir, 'checkstyle-suppressions.xml')
    if os.path.exists(checkstyle_suppressions_file_dir):
        shutil.copy(checkstyle_suppressions_file_dir, os.path.join(target, 'checkstyle-suppressions.xml'))
    shutil.copy(os.path.join(dir, 'repo.json'), os.path.join(target, 'metadata.json'))
    ugly_dir = create_dir(os.path.join(target, 'ugly'))
    copy_uglies(os.path.join(dir, 'testing'), ugly_dir)
    orig_dir = create_dir(os.path.join(target, 'orig'))
    copy_origs(os.path.join(dir, 'learning'), orig_dir)

def file_has_new_line_at_EOF(file_path):
    char = b''
    with open(file_path, 'rb+') as f:
        f.seek(-1,2)
        char = f.read()
    return char == b'\n'

def insert_new_line_at_EOF(dir):
    files_path = glob.glob(f'{dir}/*/*.java')
    modified_files = []
    for file in files_path:
        if not file_has_new_line_at_EOF(file):
            modified_files.append(file)
            with open(file, 'a+') as f:
                f.write('\n')
    return modified_files

def gen_repaired(tool, dir, dataset_metadata):
    if tool == 'styler':
        return tool, dir
    ugly_dir = os.path.join(dir, 'ugly')
    orig_dir = os.path.join(dir, 'orig')
    bin_dir = os.path.join(dir, 'bin')
    tool_dir = os.path.join(dir, tool)
    checkstyle_rules = os.path.join(dir, 'checkstyle.xml')
    repair.call_repair_tool(tool, orig_dir, ugly_dir, tool_dir, dataset_metadata)
    parse_exception_files = move_parse_exception_files(tool_dir, bin_dir)
    insert_new_line_at_EOF(tool_dir)
    return tool, dir


def compute_diff_size(experiment_id, dataset, tool):
    experiment_dir = get_experiment_dir(experiment_id)
    json_file_name = f'diff_results_{tool}.json'
    json_path = os.path.join(experiment_dir, json_file_name)
    if os.path.exists(json_path):
        return open_json(json_path)

    dir = os.path.join(experiment_dir, tool)
    original_dir = os.path.join(get_repo_dir(dataset), 'testing')
    if tool == 'styler':
        repaired_files = repair.get_repaired(tool, experiment_dir, batch=True)
    else:
        repaired_files = repair.get_repaired(tool, experiment_dir)
    diffs = []

    def get_orig(original_dir, file_id):
        return [
            path
            for path in glob.glob(f'{original_dir}/{file_id}/*.java')
            if 'orig' not in path
        ][0]

    if tool == 'loriot_repair':
        repaired_files_codebuff_sniper = repair.get_repaired('codebuff_sniper', experiment_dir)
        repaired_files_naturalize_sniper = repair.get_repaired('naturalize_sniper', experiment_dir)
        dir_codebuff_sniper = os.path.join(get_experiment_dir(experiment_id), 'codebuff_sniper')
        dir_naturalize_sniper = os.path.join(get_experiment_dir(experiment_id), 'naturalize_sniper')
        repaired_files = list(set(repaired_files_naturalize_sniper) | set(repaired_files_codebuff_sniper))
        for file_id in tqdm(repaired_files, desc=f'diff {tool}'):
            original_file_path = get_orig(original_dir, file_id)
            diffs_count = sys.maxsize
            if file_id in repaired_files_codebuff_sniper:
                new_file_path = glob.glob(f'{dir_codebuff_sniper}/{file_id}/*.java')[0]
                diffs_count = min(java_lang_utils.compute_diff_size(new_file_path, original_file_path), diffs_count)
            if file_id in repaired_files_naturalize_sniper:
                new_file_path = glob.glob(f'{dir_naturalize_sniper}/{file_id}/*.java')[0]
                diffs_count = min(java_lang_utils.compute_diff_size(new_file_path, original_file_path), diffs_count)
            diffs += [diffs_count]
    elif tool == 'styler':
        checkstyle_results, number_of_errors = repair.get_checkstyle_results(tool, experiment_dir)
        batch_result = styler.get_batch_results(checkstyle_results)
        batch_size = len(batch_result)
        for file_id in tqdm(repaired_files, desc=f'diff {tool}'):
            original_file_path = get_orig(original_dir, file_id)
            diffs_count = sys.maxsize
            for batch_id in range(batch_size):
                if file_id in batch_result[batch_id]:
                    new_file_path = glob.glob(f'{dir}/batch_{batch_id}/{file_id}/*.java')[0]
                    diffs_count = min(java_lang_utils.compute_diff_size(new_file_path, original_file_path), diffs_count)
            diffs += [diffs_count]
    else:
        for file_id in tqdm(repaired_files, desc=f'diff {tool}'):
            new_file_path = glob.glob(f'{dir}/{file_id}/*.java')[0]
            original_file_path = get_orig(original_dir, file_id)
            # print(new_file_path, original_file_path)
            diffs_count = java_lang_utils.compute_diff_size(new_file_path, original_file_path)
            diffs += [diffs_count]

    save_json(experiment_dir, json_file_name, diffs)

    return diffs

def run_experiment(dataset_name, gen_repaired_files=True):
    experiment_id = dataset_name
    dir = get_experiment_dir(experiment_id)
    ugly_dir = os.path.join(dir, 'ugly')
    orig_dir = os.path.join(dir, 'orig')
    dataset_metadata = open_json(os.path.join(dir, 'metadata.json'))
    # checkstyle_results, number_of_errors = repair.get_checkstyle_results(*gen_repaired('naturalize', dir, dataset_metadata))
    tools = ['naturalize', 'codebuff', 'naturalize_sniper', 'codebuff_sniper', 'styler']
    # tools = ['naturalize', 'codebuff', 'naturalize_sniper', 'codebuff_sniper'] #, 'styler']
    if gen_repaired_files:
        for tool in tqdm(tools, desc='gen'):
            if tool == 'styler':
                ml.de_tokenize_dataset(dataset_name, n=5, only_formatting=True)
            else:
                gen_repaired(tool, dir, dataset_metadata)

    repaired = {}
    for tool in tqdm(tools, desc=dataset_name):
        if tool == 'styler':
            repaired[tool] = repair.get_repaired(tool, dir, batch=True)
        else:
            repaired[tool] = repair.get_repaired(tool, dir)
    if 'styler' in tool:
        print(sorted( set(range(1000)) - set([int(x) for x in repaired['styler']])))
    if 'naturalize_sniper' in tools and 'codebuff_sniper' in tools:
        repaired['loriot_repair'] = list(set(repaired['naturalize_sniper']) | set(repaired['codebuff_sniper']))
    # repaired_codebuff_sniper = repair.get_repaired('codebuff_sniper', dir)
    # checkstyle_results, number_of_errors = checkstyle_results('naturalize_sniper', dir)

    result = {
        key:len(repaired_files)
        for key, repaired_files in repaired.items()
    }
    result['total'] = 1000
    return result

def get_diff_dataset(experiment_id, tools):
    dataset_name = experiment_id
    return {
        tool:compute_diff_size(experiment_id, dataset_name, tool)
        for tool in tools # if tool not in ['styler']
    }

def re_gen(dataset, type, id):
    corpus = Corpus(config['CORPUS'][dataset], dataset)
    tmp_dir = f'./tmp/{dataset}/{type}/{id}'
    create_dir(tmp_dir)
    def get_random_corpus_file(type):
        original_file_path = random.sample(glob.glob(os.path.join(get_repo_dir(dataset), f'./{type}/*/*-orig.java')), 1)[0]
        original_file_name = original_file_path.split('/')[-1].split('-orig')[0] + '.java'
        tmp_original_path = os.path.join(tmp_dir, original_file_name)
        shutil.copy(original_file_path, tmp_original_path)
        return (original_file_name, '',tmp_original_path)
    gen_errored(corpus, get_random_corpus_file, dataset, type, id, get_repo_dir(dataset))

if __name__ == '__main__':
    if sys.argv[2] == 'all':
        dataset_list = list_folders(get_repo_dir(''))
    else:
        dataset_list = sys.argv[2:]

    if len(sys.argv) >= 2 and sys.argv[1] == 'run':
        corpora = []
        for corpus in sys.argv[2:]:
            corpora.append( Corpus(config['CORPUS'][corpus], corpus) )
        share = { key:config['DATASHARE'].getint(key) for key in ['learning', 'validation', 'testing'] }
        for corpus in corpora:
            gen_dataset(corpus, share)
    if len(sys.argv) >= 2 and sys.argv[1] == 'exp':
        for dataset in tqdm(dataset_list, desc='datasets'):
            target = get_experiment_dir(dataset)
            if not os.path.exists(target):
                gen_experiment(dataset)
            run_experiment(dataset)
    if len(sys.argv) >= 2 and sys.argv[1] == 'exp-cs':
        results = {}
        for dataset in dataset_list:
            results[dataset] = run_experiment(dataset, gen_repaired_files=False)
        # json_pp(diff)
        # Graph
        graph = {}
        graph['labels'] = ('styler', 'naturalize', 'codebuff')
        graph['y_label'] = ''
        graph['x_label'] = 'Proportion of repaired files'
        graph['colors'] = {
            'styler': styler_color,
            'codebuff': codebuff_color,
            'naturalize': naturalize_color
        }
        graph['data'] = {
            dataset:[ res[label]/res['total'] for label in graph['labels']]
            for dataset, res in results.items()
        }
        if 'java-design-patterns' in graph['data']:
            graph['data']['jdp'] = graph['data']['java-design-patterns'].copy()
            del graph['data']['java-design-patterns']
        if 'commons-lang' in graph['data']:
            graph['data']['commons-\nlang'] = graph['data']['commons-lang'].copy()
            del graph['data']['commons-lang']
        # json_pp(graph)
        graph_plot.n_bar_plot(graph)
    if len(sys.argv) >= 2 and sys.argv[1] == 'diff':
        diff = {}
        tools = ('styler', 'naturalize', 'codebuff')
        for dataset in tqdm(dataset_list, desc='Diff datasets'):
            diff[dataset] = get_diff_dataset(dataset, tools)
        graph = {}
        graph['sub_labels'] = tools
        graph['colors'] = [styler_color, naturalize_color, codebuff_color]
        graph['x_label'] = 'Diff size'
        graph['data'] = {
            dataset:{ key:value for key, value in res.items() if key in graph['sub_labels'] }
            for dataset, res in diff.items()
        }
        if 'java-design-patterns' in graph['data']:
            graph['data']['jdp'] = graph['data']['java-design-patterns'].copy()
            del graph['data']['java-design-patterns']
        if 'commons-lang' in graph['data']:
            graph['data']['commons-\nlang'] = graph['data']['commons-lang'].copy()
            del graph['data']['commons-lang']
        pp.pprint(list(graph['data'].keys()))
        graph_plot.boxplot(graph)
    if len(sys.argv) >= 2 and sys.argv[1] == 'diff-violin':
        diff = {}
        tools = ('styler', 'naturalize', 'codebuff')
        for dataset in tqdm(dataset_list, desc='Diff datasets'):
            diff[dataset] = get_diff_dataset(dataset, tools)
        keys = list(list(diff.values())[0].keys())
        total = { key:reduce( list.__add__ ,[e[key] for e in diff.values()]) for key in keys }
        graph = {}
        graph['data'] = total
        graph_plot.violin_plot(graph)
    if len(sys.argv) >= 2 and sys.argv[1] == 're-gen':
        dataset = sys.argv[2]
        type = sys.argv[3]
        id =  int(sys.argv[4])
        re_gen(dataset, type, id)
    if len(sys.argv) >= 2 and sys.argv[1] == 're-gen-check':
        wrong_token_lenght = open_json('./check.json')
        for dataset, errors in tqdm(wrong_token_lenght.items(), desc='dataset'):
            for error in tqdm(errors, desc=dataset):
                re_gen(dataset, error['type'],  error['id'])
    if len(sys.argv) >= 2 and sys.argv[1] == 'check':
        results = {}
        for dataset in dataset_list:
            results[dataset] = check_token_length(dataset)
        save_json('./', 'check.json',results)
    if len(sys.argv) >= 2 and sys.argv[1] == 'analyse':
        results = {}
        for dataset in tqdm(dataset_list):
            results[dataset] = summary(dataset)
        error_types = {
            dataset:summary['type_count']
            for dataset, summary in results.items()
        }
        graph_plot.cumulatives_bars({'data': error_types, 'title': 'Number of error type per dataset'})
