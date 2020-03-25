import sys
import copy
import logging
import configparser
import getopt
import time
import TM1py
import json
import csv
import traceback
from os import scandir
from pathlib import Path
from os.path import isfile, join
import concurrent.futures 
import asyncio
import dictdiffer 
from TM1py.Services import TM1Service
from TM1py.Utils import CaseAndSpaceInsensitiveTuplesDict
from ast import literal_eval
from pathlib import Path


def query_cube_view (config, tm1_server_name, cube_name, view_name):
	view_read_start_time =  time.time()
	
	logging.debug('%s.%s.%s view starting to read data'%(tm1_server_name, cube_name, view_name))
	with TM1Service(**config[tm1_server_name], timeout=50) as tm1:
			cell_set = tm1.cubes.cells.execute_view (cube_name, view_name, private=False)
	logging.info('%s.%s.%s view with %d cells read in %.2f'%( tm1_server_name, cube_name, view_name, len(cell_set),time.time()-view_read_start_time))
	return cell_set

def write_cell_set_to_file(cell_set, file_name):
	logging.info ("Exporting source view to file %s" %(file_name))
	field_names = ['cell', 'value']
	with  open(file_name, 'w')  as export_file:
		# pickle is simpler but not human-readable
		# pickle.dump(cell_set_source,export_file)
		csv_writer = csv.DictWriter(export_file, fieldnames=field_names, quotechar='"',quoting=csv.QUOTE_ALL)
		csv_writer.writeheader()
		for cell in cell_set.keys():
			csv_writer.writerow({'cell':cell,'value':cell_set[cell]})

def read_cell_set_from_file(file_name):
	logging.info ("Reading source view from file %s" %(file_name))
	# pickle is simpler but not human-readable
	# pickle.dump(cell_set_source,export_file)
	cell_set = CaseAndSpaceInsensitiveTuplesDict()
	with open(file_name, 'r') as export_file:
		field_names = ['cell', 'value']
		csv_reader = csv.DictReader(export_file, fieldnames=field_names, quotechar='"',quoting=csv.QUOTE_ALL)
		# skip header
		next(csv_reader, None)
		for row in csv_reader:
			#print(type(literal_eval(row['value'])))
			#print(type(literal_eval(row['cell'])))
			cell_set[literal_eval(row['cell'])] = literal_eval(row['value'])
	return cell_set

def compare_cell_sets(check_file, cell_set_source, cell_set_target):
	# Compare results
	if (cell_set_source != cell_set_target):
		variances_folder = 'check_variances/'
		Path(variances_folder).mkdir(parents=True, exist_ok=True)
		file_name_to_write_diff = join(variances_folder,"%s_%s.csv" % (Path(check_file).stem,time.strftime("%Y%m%d-%H%M%S")))
		diff_file = open(file_name_to_write_diff, 'w') 
		field_names = ['change_type', 'cell', 'source_value','target_value']
		csv_writer = csv.DictWriter(diff_file, fieldnames=field_names, quotechar='"',quoting=csv.QUOTE_ALL)
		csv_writer.writeheader()
		logging.warning ("Source and target views do not match, please find list of differences (first 10 lines) below, the rest will be recorded in the file %s" %(file_name_to_write_diff))
		num_lines = 0
		for diff in dictdiffer.diff(cell_set_source, cell_set_target):
			#csv_writer.write(str(diff))
			if num_lines <= 10: logging.warning (diff)
			num_lines += 1
			csv_writer.writerow({'change_type':diff[0], 'cell':diff[1],'source_value':diff[2][0], 'target_value':diff[2][1]})
		return False
	else:
		logging.info ("Source and target views match")
		return True

def generate_reverse_json_check_file(check_file_name, original_json,  target_export_file_name):
		json_check_file_name_reverse = Path(check_file_name).with_name("reverse_%s.json" % (Path(check_file_name).stem))
		reverse_check_config = copy.deepcopy(original_json)
		reverse_check_config["test_name"] = "Reversing the check %s, autogenerated at %s" % (Path(check_file_name).stem, time.strftime("%Y%m%d-%H%M%S"))
		reverse_check_config["source2"] = reverse_check_config.pop("target")
		reverse_check_config["target"] = reverse_check_config.pop("source")
		reverse_check_config["source"] = reverse_check_config.pop("source2")
		reverse_check_config["source"]["filename"] = target_export_file_name
		with  open(json_check_file_name_reverse, 'w') as json_check_file:
			json.dump(reverse_check_config, json_check_file)
		logging.info("Wrote a reverse of test %s to a file %s"%(check_file_name,json_check_file_name_reverse))

def run_check(input_file, config):
	# open config file 
	# TODO:-- need validations here for JSON existence, formats and all other things -- it will fail over with exception if read something wrong anyway
	with open(input_file) as test_json:
  		test_config = json.load(test_json)
	logging.info('Start running test %s'%(test_config['test_name']))
	# TODO: need to check source and target test types
	if test_config['source']['type'] == 'tm1':
		cell_set_source = query_cube_view(config, test_config['source']['server'], test_config['source']['view']['cube'], test_config['source']['view']['name'])
	elif test_config['source']['type'] == 'file':
		cell_set_source = read_cell_set_from_file(test_config['source']['filename'])
	else:
		logging.error("Source type %s in test definition is not implemented" % (test_config['source']['type']) )
		raise Exception('Source type not implemented')

	if test_config['target']['type'] == 'tm1':
		cell_set_target = query_cube_view(config, test_config['target']['server'], test_config['target']['view']['cube'], test_config['target']['view']['name'])
	elif test_config['target']['type'] == 'file':
		# write results to the file
		# need a special export folder? 
		export_folder = 'test_exports'
		if test_config['target']['folder'] != '': export_folder = test_config['target']['folder']
		Path(export_folder).mkdir(parents=True, exist_ok=True)
		file_name_to_export = join(export_folder,"%s_%s_export_data.csv" % (Path(input_file).stem,time.strftime("%Y%m%d-%H%M%S")))
		write_cell_set_to_file(cell_set_source,file_name_to_export)
		# generate a 'reverse' check definition to be able to run backwards comparison easily
		generate_reverse_json_check_file(input_file, test_config, file_name_to_export)
		# stop comparing
		return True
	else:
		logging.error("Target type %s in test definition is not implemented" % (test_config['target']['type']) )
		raise Exception('Target type not implemented')
	
	return compare_cell_sets(input_file, cell_set_source, cell_set_target)
	

def main (argv):
	"""Command line format python3 tm1diff.py -i folder_with_tests -t number_of_threads -l test.log """
	# setting defaults
	number_of_threads = 5
	# getting command line arguments
	try:
		opts, args = getopt.getopt(argv, "h:i:t::l:", ["help","input=","threads=","log="])
	except getopt.GetoptError:
		print (main.__doc__)
		sys.exit(2)
	if len(argv) <= 1:
		print (main.__doc__)
		sys.exit(2)
	for opt,arg in opts:
		if opt in ("-h","--help"):
			print (main.__doc__)
			sys.exit(2)
		elif opt in ("-i","--input"):
  			input_file_or_folder = arg
		elif opt in ("-t","--threads"):
  			number_of_threads = int(arg)
		elif opt in ("-l","--log"):
			log_file = arg

	logging.basicConfig(filename=log_file,
                            filemode='w',
                            format='%(asctime)s,%(msecs)d %(threadName)s %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.INFO)
	logging.info("Starting to run tests from %s with %s threads, output log to %s" %(input_file_or_folder, number_of_threads, log_file))						
	starttime_full=time.time()
	num_tests = 0
	num_matches = 0
	num_errors = 0
	config = configparser.ConfigParser()
	config.read('config.ini')
	if isfile(input_file_or_folder):
		test_files = [Path(input_file_or_folder)]
	else:
		test_files = [f for f in scandir(input_file_or_folder) if f.is_file()]
	
	with concurrent.futures.ThreadPoolExecutor(max_workers=number_of_threads,thread_name_prefix='Check') as executor:
		checks_to_run = {executor.submit(run_check, test_file, config) :test_file for test_file in test_files}
		for future in concurrent.futures.as_completed(checks_to_run):
			check_details = checks_to_run[future]	
			try: 
				if future.result(): num_matches += 1
			except Exception as exc: 
				logging.error("Check %r generated an exception %s, %s" %(check_details, exc, traceback.format_exc()))
				num_errors += 1
			num_tests += 1	
	logging.info("Ran %d tests with in " %(num_tests) + '%.2f'%(time.time()-starttime_full) + " seconds. %d matches, %d variances, %d errors "%(num_matches, num_tests - num_matches - num_errors, num_errors))

if __name__ == "__main__":
    main(sys.argv[1:])