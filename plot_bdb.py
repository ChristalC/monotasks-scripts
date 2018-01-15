"""
This script generates graphs for Big Data Benchmark queries using Spark/Monotasks event logs. The
directory structure in which the event log files are stored should be:

  logs                       # root directory (input parameter)
   |
   | - 1a                    # query name (can be anything)
   |   |
   |   | - monotasks_branch  # Monotasks branch name (input parameter)
   |   |   |
   |   |   | - event_log
   |   |   | - [optional] ..._executor_monitor
   |   |   | - [optional] ..._executor_monitor
   |   |   ...
   |   |
   |   | - spark_branch      # Spark branch name (input parameter)
   |   |   |
   |   |   | - event_log
   |   |   | - [optional] ..._executor_monitor
   |   |   | - [optional] ..._executor_monitor
   |   |   ...
   |
   | - 1b
   |   |
   |   ...
   ...

* The root directory is an input parameter.
* There can be any number of queries, named in any fashion.
* The names of the branches are input parameters.
"""

import argparse
import functools
import numpy
import os
from os import path
import subprocess

import parse_event_logs
import utils


def main():
  args = __parse_args()
  queries = __find_event_logs(args)
  assert len(queries) > 0, "No valid data found in directory {}!".format(args.results_dir)
  __generate_graphs(queries, args)


def __parse_args():
  parser = argparse.ArgumentParser(
    description="Generate graphs for Big Data Benchmark experiments.")
  parser.add_argument(
    "-r",
    "--results-dir",
    help=("The location of the experiment results. See the comment at the top of this script " +
      "for details on how the results directory should be structured."),
    required=True)
  parser.add_argument(
    "-o",
    "--output-dir",
    help="The directory in which to store the graph and any supporting files.",
    required=True)
  parser.add_argument(
    "-m",
    "--monotasks-branch",
    help=("The branch of the 'spark-monotasks' repository that was used to execute the Monotasks " +
      "trials."),
    required=True)
  parser.add_argument(
    "-s",
    "--spark-branch",
    help=("The branch of the 'spark-monotasks' repository that was used to execute the Spark " +
      "trials."),
    required=True)
  parser.add_argument(
    "-w",
    "--num_warmup-trials",
    help="The number of trials to treat as warmup runs and discard.",
    required=True,
    type=int)
  parser.add_argument(
    "-c",
    "--plot-continuous-monitors",
    action="store_true",
    default=False,
    help=("If present, will plot all continuous monitors, whose names must end with " +
      "'executor_monitor'"),
    required=False)
  return parser.parse_args()


def __find_event_logs(args):
  """
  Navigates the filesystem hierarchy described in the comment at the top of this script and creates
  the following dictionary:
    { query name : ( monotasks event log file, spark event log file ) }
  """
  def error(log_file, program, query):
    raise Exception(
      "Unable to find {} file for branch {} for query {}".format(log_file, program, query))

  results_dir = args.results_dir
  monotasks_branch = args.monotasks_branch
  spark_branch = args.spark_branch
  plot_continuous_monitors = args.plot_continuous_monitors
  queries = {}

  for query_name in os.listdir(results_dir):
    # For every query...
    query_dir = path.join(results_dir, query_name)

    if (path.isdir(query_dir)):
      monotasks_event_log = None
      spark_event_log = None

      for branch_name in os.listdir(query_dir):
        # For every branch...
        is_monotasks_branch = branch_name == monotasks_branch
        is_spark_branch = branch_name == spark_branch

        branch_dir = path.join(query_dir, branch_name)
        if (path.isdir(branch_dir)):
          if plot_continuous_monitors:
            utils.plot_continuous_monitors(branch_dir)

          event_log = path.join(branch_dir, "event_log")
          if is_monotasks_branch:
            monotasks_event_log = event_log
          elif is_spark_branch:
            spark_event_log = event_log
          else:
            print "Unknown branch \"{}\", skipping it.".format(branch_name)

      if (monotasks_event_log is None):
        error("event log", monotasks_branch, query_name)
      if (spark_event_log is None):
        error("event_log", spark_branch, query_name)

      queries[query_name] = (monotasks_event_log, spark_event_log)

  return queries


def __generate_graphs(queries, args):
  """ Creates a graph comparing the JCTs of Monotasks and Spark. """
  # Assemble the xtics string.
  sorted_queries = sorted([(q.lower(), l) for (q, l) in queries.iteritems()])
  xtics = []
  i = 0.125
  for (query_name, _) in sorted_queries:
    xtics.append("\"{}\" {}".format(query_name, i))
    i += 1
  xtics = "({})".format(", ".join(xtics))
  x_max = len(sorted_queries) + 1

  # Construct the plot file.
  output_dir = args.output_dir
  plot_filepath = path.join(output_dir, "plot_bdb_runtimes_all.gp")
  monotasks_data_filepath = path.join(output_dir, "{}_results.data".format(args.monotasks_branch))
  spark_data_filepath = path.join(output_dir, "{}_results.data".format(args.spark_branch))
  graph_filepath = path.join(output_dir, "bdb_jcts.pdf")
  with open(plot_filepath, "w") as plot_file:
    current_dir = path.dirname(path.realpath(__file__))
    for line in open(path.join(current_dir, "gnuplot_files", "plot_bdb_base.gp"), "r"):
      new_line = line.replace("__MONOTASKS_DATA_FILEPATH__", monotasks_data_filepath)
      new_line = new_line.replace("__SPARK_DATA_FILEPATH__", spark_data_filepath)
      new_line = new_line.replace("__OUTPUT_FILEPATH__", graph_filepath)
      new_line = new_line.replace("__XTICS__", xtics)
      new_line = new_line.replace("__XRANGE__", str(x_max))
      plot_file.write(new_line)

  # Construct the data files.
  num_warmup_trials = args.num_warmup_trials
  with open(monotasks_data_filepath, "w") as monotasks_data_file, \
       open(spark_data_filepath, "w") as spark_data_file:
    i = 0
    for (query_name, (monotasks_event_log, spark_event_log)) in sorted_queries:
      print monotasks_event_log
      __add_jct_results(monotasks_data_file, monotasks_event_log, query_name, num_warmup_trials, i)
      print spark_event_log
      __add_jct_results(spark_data_file, spark_event_log, query_name, num_warmup_trials, i)
      i += 1

  # Generate the graph.
  subprocess.check_call("gnuplot {}".format(plot_filepath), shell=True)


def __drop_warmup_filterer(num_warmup_jobs, all_jobs_dict):
  """ A filterer that drops the first few jobs. """
  print num_warmup_jobs
  print all_jobs_dict
  return {k: v for k, v in sorted(all_jobs_dict.iteritems())[num_warmup_jobs:]}


def __build_data_line(query_name, x_coordinate, data_values):
  """ Formats a line of a gnuplot data file. """
  # Convert from milliseconds to seconds.
  scaled_values = [str(float(value) / 1000) for value in data_values]
  return "{} {} {}\n".format(query_name, x_coordinate, " ".join(scaled_values))


def __sum_adjacent_items(items):
  """ Returns a new list created by summing adjacent items in the provided list. """
  assert len(items) % 2 == 0, "Trying to sum adjacent items in a odd-lengthed list."

  result = []
  for i in xrange(len(items) / 2):
    result.append(items[2 * i] + items[(2 * i) + 1])
  return result


def __add_jct_results(data_file, event_log, query_name, num_warmup_trials, x_coordinate):
  """
  Parses the provided event log, extracts the JCTs, and writes the min, median, and max JCTs to the
  provided data file.
  """
  # Each trial of queries 3abc and 4 consists of two jobs.,
  has_two_jobs_per_trial = ("3" in query_name) or ("4" in query_name)
  num_warmup_jobs = 2 * num_warmup_trials if has_two_jobs_per_trial else num_warmup_trials

  filterer = functools.partial(__drop_warmup_filterer, num_warmup_jobs)
  analyzer = parse_event_logs.Analyzer(event_log, filterer)
  analyzer.output_stage_resource_metrics(event_log)
  analyzer.output_job_resource_metrics(event_log)
  analyzer.output_utilizations(event_log)
  analyzer.output_ideal_time_metrics(event_log)
  jcts = [job.runtime() for _, job in sorted(analyzer.jobs.iteritems())]

  if has_two_jobs_per_trial:
    # We sum adjacent JCTs together in order to get the total JCT for each trial.
    jcts = __sum_adjacent_items(jcts)
  data_values = [numpy.median(jcts), min(jcts), max(jcts)]
  data_file.write(__build_data_line(query_name, x_coordinate, data_values))


if __name__ == "__main__":
  main()
