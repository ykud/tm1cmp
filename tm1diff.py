import sys
import copy
import logging
import configparser
import getopt
import time
import random
import json
import csv
import traceback
from os import scandir
from pathlib import Path
from os.path import isfile, join
import concurrent.futures 
import dictdiffer 
from TM1py.Services import TM1Service
from TM1py.Utils import CaseAndSpaceInsensitiveTuplesDict
from ast import literal_eval

def query_cube_view (config, view_definition):
	view_read_start_time =  time.time()
	tm1_server_name = view_definition ['server'] 
	cube_name = view_definition ['cube']
	if view_definition['view_type']=='native':
		view_name = view_definition ['view_name']
		with TM1Service(**config[tm1_server_name]) as tm1:
			cell_set = tm1.cubes.cells.execute_view (cube_name, view_name, private=False)
	elif view_definition['view_type']=='mdx':
		mdx_query = view_definition['mdx']
		view_name = "MDX query at %s" % (time.strftime("%Y%m%d-%H%M%S"))
		with TM1Service(**config[tm1_server_name]) as tm1:
			cell_set = tm1.cubes.cells.execute_mdx(mdx_query)
	elif view_definition['view_type']=='create':
		# this is where we try to create a new view and somehow 'randomise it' by selecting different elements
		# we are going to record this view back as [elements] for everything we generated randomly and assign it back
		# view_definition['mdx'] = whatever we generate converted to mdx
		logging.debug("generating mdx query on our definition")
		view_name = view_definition['view_name'] 
		axes = list()
		for dim in view_definition['view_definition']:
			#print (dim['dimension'],dim['type'])
			dim_elements = ''
			if dim['type'] == 'element list':
				# combine list of elements
				list_of_dim_elements = list()
				for el in dim['elements']:
					dim_element = "[%s].[%s]"%(dim['dimension'], el['element'])
					list_of_dim_elements.append(dim_element)
				dim_elements = "{%s}" % (','.join(list_of_dim_elements))
			elif dim['type'] == 'subset':
				dim_elements = "TM1SubsetToSet([%s],'%s')"%(dim['dimension'],dim['subset_name'])
			elif dim['type'] == 'random':
				# create mdx based on selection
				number_of_elements_to_return = int(dim['number_of_random_elements'])
				list_of_dim_elements = list()
				if dim['level_of_random_elements'] == 'All':
					mdx_query_for_elements = "[%s].Members" % (dim['dimension'])
				else:
					mdx_query_for_elements = "TM1FilterByLevel([%s].Members,%s)" % (dim['dimension'], dim['level_of_random_elements'])
				with TM1Service(**config[tm1_server_name]) as tm1:
					# limiting number of entries to something smaller than total elements just in case there's way too many
					element_list = tm1.dimensions.hierarchies.elements.execute_set_mdx(mdx=mdx_query_for_elements, top_records=number_of_elements_to_return * 30)
					for i in range(1, number_of_elements_to_return):
						dim_element = "[%s].[%s]"%(dim['dimension'], random.choice(element_list)[0]['Name'])
						list_of_dim_elements.append(dim_element)
				dim_elements = "{%s}" % (','.join(list_of_dim_elements))
			axes.append(dim_elements)
		column_axis = "%s " % (axes.pop())
		row_axis = '*'.join(axes)
		suppress_zeros = "NON EMPTY"	
		if "suppress_zeros" in view_definition:
			if view_definition['suppress_zeros'] == 'No':
				suppress_zeros = ''
		mdx_query = "SELECT %s %s on ROWS, %s %s on COLUMNS FROM [%s]" %(suppress_zeros, row_axis, suppress_zeros, column_axis, view_definition['cube'] )
		logging.debug ("MDX query generated: %s" %(mdx_query))
		# updating view definition to make it mdx view for comparison
		view_definition ['view_type'] = 'mdx'
		view_definition ['comment'] = "Converted manual view to MDX"
		view_definition ['mdx'] = mdx_query
		with TM1Service(**config[tm1_server_name]) as tm1:
			cell_set = tm1.cubes.cells.execute_mdx(mdx_query)
	else: 
		logging.error("View type %s in test definition is not implemented" % (view_definition['view_type']) )
		raise Exception('View type not implemented')
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

def compare_cell_sets(check_file, cell_set_source, cell_set_target, check_tolerance):
	# Compare results
	source_target_match = True
	if (cell_set_source != cell_set_target):
			variances_folder = 'check_variances/'
			Path(variances_folder).mkdir(parents=True, exist_ok=True)
			file_name_to_write_diff = join(variances_folder,"%s_%s.csv" % (Path(check_file).stem,time.strftime("%Y%m%d-%H%M%S")))
			field_names = ['change_type', 'cell', 'source_value','target_value']
			num_of_variances = 0
			for diff in dictdiffer.diff(cell_set_source, cell_set_target):
				source_value = diff[2][0]
				target_value = diff[2][1]
				# compare with given tolerance
				#print ("source %f, target %f, variance %f, comparing to %f"%(source_value, target_value,abs(source_value - target_value),check_tolerance ) ))
				if abs(source_value - target_value) > check_tolerance:
					num_of_variances = num_of_variances + 1
					if num_of_variances == 1:
						diff_file = open(file_name_to_write_diff, 'w')
						csv_writer = csv.DictWriter(diff_file, fieldnames=field_names, quotechar='"',quoting=csv.QUOTE_ALL)
						csv_writer.writeheader()
					csv_writer.writerow({'change_type':diff[0], 'cell':diff[1],'source_value':source_value, 'target_value':target_value})
			if num_of_variances > 0:
				diff_file.close()
				logging.warning ("Source and target views do not match, %i cells vary, please find list of differences in the file %s" %(num_of_variances ,file_name_to_write_diff))
				source_target_match = False
			else:
				logging.info ("Source and target views match within the given tolerance of %.8f" %(check_tolerance))
	else:
		logging.info ("Source and target views match absolutely")
	return source_target_match

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
	with open(input_file) as check_json:
  		check_definition = json.load(check_json)
	logging.info('Start running test %s'%(Path(input_file).stem))

	if check_definition['source']['type'] == 'tm1':
		cell_set_source = query_cube_view(config, check_definition['source'])
	elif check_definition['source']['type'] == 'file':
		cell_set_source = read_cell_set_from_file(check_definition['source']['filename'])
	else:
		logging.error("Source type %s in test definition is not implemented" % (check_definition['source']['type']) )
		raise Exception('Source type not implemented')

	if check_definition['target']['type'] == 'tm1':
		cell_set_target = query_cube_view(config, check_definition['target'])
	elif check_definition['target']['type'] == 'file':
		# write results to the file
		# need a special export folder? 
		export_folder = 'test_exports'
		if check_definition['target']['folder'] != '': export_folder = check_definition['target']['folder']
		Path(export_folder).mkdir(parents=True, exist_ok=True)
		file_name_to_export = join(export_folder,"%s_%s_export_data.csv" % (Path(input_file).stem,time.strftime("%Y%m%d-%H%M%S")))
		write_cell_set_to_file(cell_set_source,file_name_to_export)
		# generate a 'reverse' check definition to be able to run backwards comparison easily
		generate_reverse_json_check_file(input_file, check_definition, file_name_to_export)
		# stop comparing
		return True
	else:
		logging.error("Target type %s in test definition is not implemented" % (check_definition['target']['type']) )
		raise Exception('Target type not implemented')
	if "tolerance" in check_definition:
		check_tolerance = check_definition['tolerance']
	else:
		check_tolerance = 0.00001
	return compare_cell_sets(input_file, cell_set_source, cell_set_target,check_tolerance)
	

def main (argv):
	"""Command line format python3 tm1diff.py -i folder_with_tests -th number_of_threads -l test.log """
	# setting defaults
	number_of_threads = 5
	# getting command line arguments
	try:
		opts,args = getopt.getopt(argv, "h:i:t:m::l:", ["help","input=","threads=","log="])
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
	# adding the console logger as well
	logging.getLogger().addHandler(logging.StreamHandler())
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
	# let's make the command return an execution code 0 for success and 1 if there were any mismatches -- maybe somebody will wrap it around with more detection logic
	if num_errors == 0 & num_matches == num_tests:
		sys.exit(0)
	else:
		sys.exit(1)
if __name__ == "__main__":
    main(sys.argv[1:])