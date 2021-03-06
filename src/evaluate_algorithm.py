import argparse
import os
import re
import shutil
import time
import itertools
from multiprocessing import Pool, cpu_count
from subprocess import Popen, PIPE, STDOUT

import numpy as np

from src.util.overall_score import write_stats


def check_extension(filename, extension_list):
    return any(filename.endswith(extension) for extension in extension_list)


def get_file_list(dir, extension_list):
    list = []
    for root, _, fnames in sorted(os.walk(dir)):
        for fname in fnames:
            if check_extension(fname, extension_list):
                path = os.path.join(root, fname)
                list.append(path)
    list.sort()
    return list


def get_score(logs, token):
    for line in logs:
        line = str(line)
        if token in line:
            split = line.split('=')[1][0:8]
            split = re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", split)
            return float(split[0])
    return None


def compute_for_all(input_xml, gt_xml, gt_pxl, output_path, eval_tool):
    original_img_name = os.path.basename(gt_xml).replace('_gt.xml', '.jpg')
    original_img_path = os.path.dirname(gt_xml).replace('xml_gt', 'ori_img')

    print("Starting: JAR {}".format(input_xml))
    p = Popen(['java', '-jar', eval_tool,
               '-igt', gt_pxl,
               '-xgt', gt_xml,
               '-overlap', os.path.join(original_img_path, original_img_name),
               '-xp', input_xml,
               '-csv'], stdout=PIPE, stderr=STDOUT)
    logs = [line for line in p.stdout]
    print("Done: JAR {}".format(input_xml))
    return [get_score(logs, "line IU ="), logs]


def evaluate(input_folders_xml, gt_folders_xml, gt_folders_pxl, output_path, j, eval_tool, **kwargs):

    # Select the number of threads
    if j == 0:
        pool = Pool(processes=cpu_count())
    else:
        pool = Pool(processes=j)

    # Get the list of all input images
    input_xml = []
    for path in input_folders_xml:
        input_xml.extend(get_file_list(path, ['.xml']))

    # Get the list of all GT XML
    gt_xml = []
    for path in gt_folders_xml:
        gt_xml.extend(get_file_list(path, ['.xml', '.XML']))

    # Get the list of all GT pxl
    gt_pxl = []
    for path in gt_folders_pxl:
        gt_pxl.extend(get_file_list(path, ['.png']))

    # Create output path for run
    tic = time.time()

    if not os.path.exists(output_path):
        os.makedirs(os.path.join(output_path))
    else:
        for the_file in os.listdir(output_path):
            file_path = os.path.join(output_path, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(e)

    # Debugging purposes only!
    #input_images = [input_images[1]]
    #gt_xml = [gt_xml[1]]
    #gt_pxl = [gt_pxl[1]]

    # input_xml = input_xml[0:3]
    # gt_xml = gt_xml[0:3]
    # gt_pxl = gt_pxl[0:3]

    # For each file run
    results = list(pool.starmap(compute_for_all, zip(input_xml,
                                                    gt_xml,
                                                    gt_pxl,
                                                    itertools.repeat(output_path),
                                                    itertools.repeat(eval_tool)
                                                     )))
    pool.close()
    print("Pool closed)")

    scores = []
    errors = []

    for item in results:
        if item[0] is not None:
            scores.append(item[0])
        else:
            errors.append(item)

    if list(scores):
        score = np.mean(scores)
    else:
        score = -1

    # np.save(os.path.join(output_path, 'results.npy'), results)
    write_stats(output_path, errors)
    print('Total time taken: {:.2f}, avg_line_iu={}, nb_errors={}'.format(time.time() - tic, score, len(errors)))
    return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grid search to identify best hyper-parameters for text line '
                                                 'segmentation.')
    # Path folders
    parser.add_argument('--input-folders-xml', nargs='+', type=str,
                        required=True,
                        help='path to folders containing pixel-gt (e.g. /dataset/CB55/output-m /dataset/CSG18/output-m /dataset/CSG863/output-m)')
    parser.add_argument('--gt-folders-xml', nargs='+', type=str,
                        required=True,
                        help='path to folders containing xml-gt (e.g. /dataset/CB55/test-page /dataset/CSG18/test-page /dataset/CSG863/test-page)')
    parser.add_argument('--gt-folders-pxl', nargs='+', type=str,
                        required=True,
                        help='path to folders containing xml-gt (e.g. /dataset/CB55/test-m /dataset/CSG18/test-m /dataset/CSG863/test-m)')
    parser.add_argument('--output-path', metavar='DIR',
                        required=True,
                        help='path to store output files')

    # Method parameters
    # Environment
    parser.add_argument('--eval-tool', metavar='DIR',
                        default='./util/LineSegmentationEvaluator.jar',
                        help='path to folder containing DIVA_Line_Segmentation_Evaluator')
    parser.add_argument('-j', type=int,
                        default=0,
                        help='number of thread to use for parallel search. If set to 0 #cores will be used instead')
    args = parser.parse_args()

    evaluate(**args.__dict__)
