#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""A basic python wrapper for checkstyle
    """


import xml.etree.ElementTree as ET
import subprocess
import sys
from functools import reduce

import pprint
pp = pprint.PrettyPrinter(indent=4)

from core import *

_CHECKSTYLE_JAR = "../jars/checkstyle-8.12-all.jar"


def check(checkstyle_file_path, file_path, checkstyle_jar=_CHECKSTYLE_JAR, only_targeted=False):
    """
    Run checkstyle on the dir
    """
    cmd = "java -jar {} -f xml -c {} {}".format(checkstyle_jar, checkstyle_file_path, file_path)
    process = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE)
    output = process.communicate()[0]
    # deletion of non xml strings
    if ( process.returncode > 0):
        output = b''.join(output.split(b'</checkstyle>')[0:-1]) + b'</checkstyle>'
    # parsing
    output = parse_res(output, only_targeted=only_targeted)
    return (output, process.returncode)

def parse_res(output, only_targeted=False):
    """
    Parse the reults from XML to a dict
    """
    xml_output = ET.fromstring(output)
    output_parsed = dict()
    for elem_file in xml_output.getchildren():
        output_parsed[elem_file.attrib['name']] = dict()
        output_parsed[elem_file.attrib['name']]['errors'] = list()
        for elem_error in elem_file.getchildren():
            if ( elem_error.tag == 'error' ):
                if only_targeted:
                    if is_error_targeted(elem_error.attrib):
                        output_parsed[elem_file.attrib['name']]['errors'].append(elem_error.attrib)
                else:
                    output_parsed[elem_file.attrib['name']]['errors'].append(elem_error.attrib)
    return output_parsed

def parse_file(file_path):
    with open(file_path) as f:
        file_content = f.read()
    return parse_res(file_content)

def analyse_results(results):
    """
    Depreciated.
    Gives quick analyse of the checkstyle results
    """
    FIXABLE = (
        'RegexpSinglelineCheck',
        'WitespaceAfterCheck',
        'OneStatementPerLineCheck',
        'NoLineWrapCheck',
        'OperatorWrapCheck',
        'ParentPadCheck',
        'NoWhitespaceBeforeCheck',
        'FileTabCharacterCheck',
        'IndentationCheck',
    )

    # sanitize the results
    is_java = lambda file: file.split('.')[-1] == 'java'
    results_sanitized = {key:value for key, value in results.items() if is_java(key)}

    # count some stuff
    number_of_files = len(results_sanitized)
    files_with_errors = { key:value for key, value in results_sanitized.items() if len(value["errors"]) }
    error_to_name = lambda error: error['source'].split('.')[-1]
    errors = map(error_to_name, reduce(list.__add__, map(lambda x: x["errors"],files_with_errors.values())));
    errors_count = {}
    for error in errors:
        errors_count[error] = errors_count.get(error, 0) + 1
    total_number_of_errors = sum(errors_count.values())
    number_of_files_error_free = number_of_files - len(files_with_errors)
    possibly_fixable_errors_count = {key:value for key, value in errors_count.items() if key in FIXABLE}
    possibly_fixable_count = sum(possibly_fixable_errors_count.values())
    return {
        "number_of_files": number_of_files,
        "number_of_files_error_free": number_of_files_error_free,
        "errors_count": errors_count,
        "total_number_of_errors": total_number_of_errors,
        "possibly_fixable_errors_count": possibly_fixable_errors_count,
        "possibly_fixable_count": possibly_fixable_count,
    }

if __name__ == "__main__":
    if sys.argv[1] == "cs":
        checkstyle_path = "./test_corpora/commons-lang/checkstyle.xml"
        file_path = "./ugly/java-design-patterns/Target.java ./ugly/java-design-patterns/Client.java"
        if ( len(sys.argv) >= 4):
            checkstyle_path = sys.argv[2]
            file_path = sys.argv[3]

        (output_raw, errorcode) = check(checkstyle_path, file_path)
        print(output_raw, errorcode)
    elif sys.argv[1] == "read":
        pp.pprint(analyse_results(parse_file(sys.argv[2])))
