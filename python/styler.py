
import ml
import sys
import glob
from git import Repo
from tqdm import tqdm
import real
from scipy import stats

from core import *
import checkstyle
from Corpus import Corpus
import synthetic
import ml

__model_dir = './styler/models'

def get_model_dir(name, only_formatting=False):
    if only_formatting:
        return os.path.join(__model_dir, f'{name}-of.pt')
    else:
        return os.path.join(__model_dir, f'{name}.pt')

def tokenize_errors(file_path, errors):
    inputs = []
    for error in errors:
        error['type'] = checkstyle_source_to_error_type(error['source'])
        if is_error_targeted(error):
            tokenized_file, info = ml.tokenize_file_to_repair(file_path, error)
            inputs += [ (" ".join(tokenized_file), info) ]
    return inputs

def de_tokenize(original_file_path, info):
    pass

def gen_translator(model_name, batch_size=5, only_formatting=False):
    tmp_dir = './styler/tmp'
    model_dir = get_model_dir(model_name, only_formatting=only_formatting)
    ml.create_dir(tmp_dir)
    tmp_input_file_name = 'input.txt'
    tmp_input_file_path = os.path.join(tmp_dir, tmp_input_file_name)
    tmp_output_file_name = 'output.txt'
    tmp_output_file_path = os.path.join(tmp_dir, tmp_output_file_name)
    def translator(input):
        save_file(tmp_dir, tmp_input_file_name, input)
        run_translate(model_dir, tmp_input_file_path, tmp_output_file_path, batch_size=batch_size)
        return list(filter(lambda a: a!='', open_file(tmp_output_file_path).split('\n')))
    return translator

def run_translate(model_dir, input_file, output_file, batch_size=5):
    open_nmt_dir = './OpenNMT-py'
    translate_script = os.path.join(open_nmt_dir, 'translate.py')

    options = [
        f'-model {model_dir}',
        f'-src {input_file}',
        f'-output {output_file}',
        f'-n_best {batch_size}'
    ]
    cmd = f'python {translate_script} {" ".join(options)}'

    process = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE)
    output = process.communicate()[0]

    return output

def join_token(tokens):
    return ' '.join(tokens)

def print_translations(file_path, metadata_path, translate):
    metadata = open_json(metadata_path)
    for tokenized_errors, info in tokenize_errors(file_path, metadata['errors']):
        print(info)
        for translation in translate(tokenized_errors):
            ml.print_diff(join_token(info['tokens_errored_in_tag']) + '\n', translation)
            print()

def de_tokenize(file_path, info, new_tokens, only_formatting=False):
    source_code = open_file(file_path)
    result = ml.de_tokenize(source_code, info, new_tokens.split(' '), tabulations=False, only_formatting=only_formatting)
    return result

def get_files_without_errors(checkstyle_result):
    return [ file for file, result in checkstyle_result.items() if len(result['errors']) == 0 ]

def get_files_with_errors(checkstyle_result):
    return [ file for file, result in checkstyle_result.items() if len(result['errors']) > 0 ]

def create_corpus(dir, name, checkstyle_dir):
    if dir.endswith('/'):
        dir = dir[:-1]
    corpus_dir = f'./styler/{name}-corpus'

    (output, returncode) = checkstyle.check(checkstyle_file_path=checkstyle_dir, file_path=dir)

    files_without_errors = get_files_without_errors(output)
    files_with_errors = get_files_with_errors(output)

    print(f'Found {len(files_without_errors)} files with no errors.')
    print(f'Found {len(files_with_errors)} files with errors.')

    def is_good_candidate(file_path):
        if not file_path.endswith('.java'):
            return False
        return True

    candidate_files = filter(is_good_candidate, files_without_errors)

    create_dir(corpus_dir)
    shutil.copy(checkstyle_dir, os.path.join(corpus_dir, 'checkstyle.xml'))
    for id, file in tqdm(enumerate(candidate_files), desc='Copy'):
        file_target_dir = os.path.join(corpus_dir, f'data/{id}')
        file_name = file.split('/')[-1]
        file_target = os.path.join(file_target_dir, file_name)
        create_dir(file_target_dir)
        shutil.copy(file, file_target)

    corpus_info = {
        'grammar': 'Java8',
        'indent': '4'
    }
    save_json(corpus_dir, 'corpus.json', corpus_info)
    return corpus_dir

def create_corpus_git(dir, commit, checkstyle_relative_dir):
    if dir.endswith('/'):
        dir = dir[:-1]
    corpus_dir = f'./styler/{dir.split("/")[-1]}-corpus'

    repo = Repo(dir)
    repo.git.checkout(commit)

    checkstyle_results = find_all(dir, 'checkstyle-result.xml')
    for checkstyle_result in checkstyle_results:
        os.remove(checkstyle_result)

    checkstyle_dir = os.path.join(dir, checkstyle_relative_dir)
    (output, returncode) = checkstyle.check(checkstyle_file_path=checkstyle_dir, file_path=dir)

    files_without_errors = get_files_without_errors(output)
    files_with_errors = get_files_with_errors(output)

    print(f'Found {len(files_without_errors)} files with no errors.')
    print(f'Found {len(files_with_errors)} files with errors.')

    def is_good_candidate(file_path):
        if not file_path.endswith('.java'):
            return False
        return True

    candidate_files = filter(is_good_candidate, files_without_errors)

    create_dir(corpus_dir)
    shutil.copy(checkstyle_dir, os.path.join(corpus_dir, 'checkstyle.xml'))
    for id, file in tqdm(enumerate(candidate_files), desc='Copy'):
        file_target_dir = os.path.join(corpus_dir, f'data/{id}')
        file_name = file.split('/')[-1]
        file_target = os.path.join(file_target_dir, file_name)
        create_dir(file_target_dir)
        shutil.copy(file, file_target)

    corpus_info = {
        'grammar': 'Java8',
        'indent': '4'
    }
    save_json(corpus_dir, 'corpus.json', corpus_info)

def get_batch_results(checkstyle_results):
    return {
        batch:set([
            file.split('/')[-2]
            for file, result in checkstyle_results.items()
            if len(result['errors']) == 0
            and f'batch_{batch}' == file.split('/')[-3]
        ])
        for batch in range(5)
    }

def identity(a):
    return a

def reverse_collection(collection, key_func=None):
    if key_func == None:
        key_func = identity
    result = {}
    for key, items in collection.items():
        for item in items:
            value = key_func(item)
            if value not in result:
                result[value] = []
            result[value] += [key]
    return result

def select_the_best_repair(correct_repairs, original):
    min_diff = 10000000
    file = ''
    for correct_repair in correct_repairs:
        diff_size = java_lang_utils.compute_diff_size(original, correct_repair)
        if diff_size < min_diff:
            file = correct_repair
    return file

def repair_files(dir, model_name, only_formatting=False):
    # dir= './styler/test'
    dir_files = os.path.join(dir, f'{model_name}/1')
    target = os.path.join(dir, 'repair-attempt')
    target_final = os.path.join(dir, 'files-repaired')
    checkstyle_rules = os.path.join(dir, 'checkstyle.xml')
    waste = os.path.join(dir, 'waste')
    create_dir(target)
    create_dir(waste)
    translate = gen_translator(model_name, batch_size=5, only_formatting=only_formatting)
    for folder_id in tqdm(list_folders(dir_files)):
        file_path = glob.glob(f'{dir_files}/{folder_id}/*.java')[0]
        metadata_path = f'{dir_files}/{folder_id}/metadata.json'
        for tokenized_errors, info in tokenize_errors(file_path, open_json(metadata_path)['errors']):
            for proposal_id, translation in enumerate(translate(tokenized_errors)):
                de_tokenized_translation = de_tokenize(file_path, info, translation, only_formatting=only_formatting)
                folder = f'{target}/batch_{proposal_id}/{folder_id}'
                create_dir(folder)
                save_file(folder, file_path.split('/')[-1], de_tokenized_translation)
    move_parse_exception_files(target, waste)
    checkstyle_result, number_of_errors = checkstyle.check(checkstyle_rules, target, only_targeted=True)
    # json_pp(checkstyle_result)
    files_properly_repaired = reverse_collection(get_batch_results(checkstyle_result))
    final_repairs = {
        id:select_the_best_repair(
            [ glob.glob(f'{target}/batch_{batch}/{id}/*.java')[0] for batch in repairs ],
            glob.glob(f'{dir_files}/{id}/*.java')[0]
        )
        for id, repairs
        in files_properly_repaired.items()
    }
    json_pp(final_repairs)
    for id, path in final_repairs.items():
        folder = create_dir(f'{target_final}/{id}')
        shutil.copy(path, folder)

def lits_and_create_corpora():
    repos = ['ONSdigital/rm-notify-gateway']#list(open_json('./travis/commits.json').keys()) + list(open_json('./travis/commits_oss.json').keys())
    for info in tqdm(real.get_repo_with_checkstyle(repos), desc='Total'):
        # print(info)
        commits = real.commit_until_last_modification(info['repo'], info['checkstyle_relative'])
        if len(commits):
            oldest_commit = commits[-1]
            print(f'{info["repo_full_name"]} -> {oldest_commit}')
            create_corpus_git(info['repo'].working_dir, oldest_commit, info['checkstyle_clean'])


def repair_real(name):
    repair_files(f'../datasets/real-errors', name, only_formatting=True)


def main(args):
    if args[1] == 'repair':
        if args[2] == 'all':
            datasets = ['be5', 'dagger', 'milo', 'okhttp', 'picasso']
        else:
            datasets = args[2:]
        for dataset in tqdm(datasets):
            repair_real(dataset)
    if args[1] == 'train':
        project_path = args[2]
        checkstyle_file_path = args[3]
        project_name = args[4]
        corpus_dir = create_corpus(
            project_path,
            project_name,
            checkstyle_file_path
        )
        corpus = Corpus(corpus_dir, project_name)
        share = { key:core_config['DATASHARE'].getint(key) for key in ['learning', 'validation', 'testing'] }
        synthetic.gen_dataset(corpus, share, target_dir=f'./styler/{project_name}-errors' )
        ml.gen_IO(f'./styler/{project_name}-errors', f'./styler/{project_name}-tokens', only_formatting=True)
        pass

if __name__ == "__main__":
    main(sys.argv)
