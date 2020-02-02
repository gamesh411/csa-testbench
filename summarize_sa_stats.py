#!/usr/bin/env python2
from __future__ import division, print_function

import os
import re
import sys
from collections import defaultdict, OrderedDict
from enum import Enum
from math import floor, log10


def dice_coefficient(a, b):
    if not a or not b:
        return 0.0
    # Quick case for true duplicates.
    if a == b:
        return 1.0
    # If a != b, and a or b are single chars, then they can't possibly match.
    if len(a) == 1 or len(b) == 1:
        return 0.0

    # Use python list comprehension, preferred over list.append().
    a_bigram_list = [a[i:i + 2] for i in range(len(a) - 1)]
    b_bigram_list = [b[i:i + 2] for i in range(len(b) - 1)]

    a_bigram_list.sort()
    b_bigram_list.sort()

    lena = len(a_bigram_list)
    lenb = len(b_bigram_list)
    matches = i = j = 0
    while i < lena and j < lenb:
        if a_bigram_list[i] == b_bigram_list[j]:
            matches += 2
            i += 1
            j += 1
        elif a_bigram_list[i] < b_bigram_list[j]:
            i += 1
        else:
            j += 1
    score = matches / (lena + lenb)
    return score


# The different type of statistics and their corresponding pattern.
class StatType(Enum):
    NUM = '#'
    PER = '%'
    MAX = 'maximum'


def summ_stats(path, verbose=True):
    stat_map = defaultdict(int)
    per_helper = defaultdict(int)
    group = OrderedDict()
    if os.path.isdir(path):
        for stat_file in os.listdir(path):
            summ_stats_on_file(os.path.join(path, stat_file), stat_map, per_helper, group)
    elif os.path.isfile(path):
        summ_stats_on_file(path, stat_map, per_helper, group)
    else:
        return stat_map

    if verbose:
        # Print the content of stat_map in a formatted way grouped by the statistic producing file.
        last_space = floor(log10(max(stat_map.values()))) + 1
        for key in sorted(group.keys(), key=(lambda x: group[x])):
            val = stat_map[key]
            if isinstance(val, float):
                num_of_spaces = int(last_space - floor(log10(int(val)))) - 4
                sys.stdout.write("{0:.3f}".format(val))
            else:
                num_of_spaces = int(last_space - floor(log10(val)))
                sys.stdout.write(str(val))
            print(' ' * num_of_spaces + '- ' + key)

    return stat_map


def summ_stats_on_file(filename, stat_map, per_helper, group):
    """
    Example output

===-------------------------------------------------------------------------===
                          ... Statistics Collected ...
===-------------------------------------------------------------------------===

   12 AnalysisConsumer - The maximum number of basic blocks in a function.
 2524 AnalysisConsumer - The # of basic blocks in the analyzed functions.
  690 AnalysisConsumer - The # of functions at top level.
  453 AnalysisConsumer - The # of functions and blocks analyzed (as top level with inlining turned on).
 2266 AnalysisConsumer - The # of visited basic blocks in the analyzed functions.
   89 AnalysisConsumer - The % of reachable basic blocks.
  582 CoreEngine       - The # of paths explored by the analyzer.
21124 CoreEngine       - The # of steps executed.
  583 ExprEngine       - The # of times we inlined a call
   35 ExprEngine       - The # of aborted paths due to reaching the maximum block count in a top level function
    5 ExprEngine       - The # of times we split the path due to imprecise dynamic dispatch info
 6102 ExprEngine       - The # of times RemoveDeadBindings is called
  383 file-search      - Number of attempted #includes.
  193 file-search      - Number of #includes skipped due to the multi-include optimization.

===-------------------------------------------------------------------------===
                                Analyzer timers
===-------------------------------------------------------------------------===
  Total Execution Time: 0.1215 seconds (0.1214 wall clock)

   ---User Time---   --System Time--   --User+System--   ---Wall Time---  --- Name ---
   0.1099 ( 92.0%)   0.0000 (  0.0%)   0.1099 ( 90.5%)   0.1099 ( 90.5%)  Path exploration time
   0.0093 (  7.8%)   0.0020 (100.0%)   0.0113 (  9.3%)   0.0112 (  9.3%)  Syntax-based analysis time
   0.0003 (  0.2%)   0.0000 (  0.0%)   0.0003 (  0.2%)   0.0003 (  0.2%)  Path-sensitive report post-processing time
   0.1195 (100.0%)   0.0020 (100.0%)   0.1215 (100.0%)   0.1214 (100.0%)  Total
    """

    type_pattern = ''
    for t in StatType:
        type_pattern += t.value + '|'
    type_pattern = type_pattern[:-1]
    stat_pattern = re.compile(r"(?P<value>[0-9]+)\s+(?P<source>\S+)\s+-\s+(?P<name>The (?P<type>" + type_pattern + r") .+)")
    timer_pattern = re.compile(r"Total Execution Time: (?P<seconds>[0-9]+(?:\.[0-9]*)?) seconds",
                               re.IGNORECASE)
    act_nums = OrderedDict()
    per_to_num_map = OrderedDict()
    per_to_update = OrderedDict()
    is_in_stat_block = False
    f = open(filename)
    lines = f.readlines()
    for line in lines:
        m = timer_pattern.search(line)
        if m:
            val = float(m.group('seconds'))
            if "TU times" in stat_map:
                stat_map["TU times"].append(val)
            else:
                stat_map["TU times"] = [val]
        m = stat_pattern.search(line)
        if m:
            is_in_stat_block = True
            stat_type = StatType(m.group('type'))
            stat_name = m.group('name')
            stat_val = m.group('value')
            group[stat_name] = m.group('source')
            if stat_type == StatType.NUM:
                stat_map[stat_name] += int(stat_val)
                act_nums[stat_name] = int(stat_val)
            elif stat_type == StatType.MAX:
                stat_map[stat_name] = max(stat_map[stat_name], int(stat_val))
            elif stat_type == StatType.PER:
                per_to_update[stat_name] = stat_val
        # When all the other statistics has been processed (to a file) than check the % stats.
        elif is_in_stat_block:
            is_in_stat_block = False
            for key, val in per_to_update.items():
                # Find the most similar # stat.
                num_data = max(act_nums.keys(), key=(lambda x: dice_coefficient(x, key)))
                per_helper[num_data] += int(act_nums[num_data] * float(val))
                # Check for consistency.
                assert not (key in per_to_num_map and per_to_num_map[key] != num_data)
                per_to_num_map[key] = num_data
                stat_map[key] = floor(per_helper[num_data]) / stat_map[num_data]
            act_nums = OrderedDict()


def main(argv):
    summ_stats(argv[1])


if __name__ == "__main__":
    main(sys.argv)
