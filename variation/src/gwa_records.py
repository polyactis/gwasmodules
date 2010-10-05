"""
A file which contains hdf5 interface for the phenotypes and results.

Overall data structure is: 

One hdf5 file per phenotype.
Three types of tables.
	- A info table, one for each transformation/accession subset.
	- phenotype table, one for each transformation/accession subset
	- result table, one for each transformation/accession subset and one for each analysis method.
	
	The minimum contains an info record, and a raw phenotype table.
"""
import tables
import phenotypeData as pd
import itertools
import scipy as sp

class PhenotypeInfo(tables.IsDescription):
	"""
	Phenotype info container
	"""
	name = tables.StringCol(256)
	num_values = tables.Int32Col()
	std_dev = tables.Float32Col()
	growth_conditions = tables.StringCol(256)
	phenotype_scoring = tables.StringCol(256)
	method_description = tables.StringCol(256)
	measurement_scale = tables.StringCol(256)
	is_binary = tables.BoolCol()



class TransformationInfo(tables.IsDescription):
	"""
	Info on the transformation.
	"""
	name = tables.StringCol(256)
	description = tables.StringCol(256)




class PhenotypeValue(tables.IsDescription):
	"""
	Phenotype value wrapper
	"""
	ecotype = tables.Int32Col()
	accession_name = tables.StringCol(16)
	mean_value = tables.Float32Col()
	std_dev = tables.Float32Col()
	comment = tables.StringCol(256)


class ResultInfo(tables.IsDescription):
	analysis_method = tables.StringCol(256)
	comment = tables.StringCol(256)

class ResultRecord(tables.IsDescription):
	"""
	A general result record structure
	"""
	chromosome = tables.Int32Col()
	position = tables.Int32Col()
	score = tables.Float32Col() #Perhaps 64 bits?? 
	maf = tables.Float32Col()
	mac = tables.Int32Col()

class ResultRecordLM(ResultRecord):
	"""
	Linear model, mixed models, etc.
	"""
	genotype_var_perc = tables.Float32Col()
	beta0 = tables.Float32Col()
	beta1 = tables.Float32Col()
	correlation = tables.Float32Col()


class ResultRecordKW(ResultRecord):
	"""
	Kruskal Wallis
	"""
	statistic = tables.Float32Col()


class ResultRecordFT(ResultRecord):
	"""
	Fisher's exact test
	"""
	odds_ratio = tables.Float32Col()


def init_file(hdf5_file_name):
	print 'Setting up file %s' % hdf5_file_name
	# Open a file in "w"rite mode
	h5file = tables.openFile(hdf5_file_name, mode="w", title="Phenotype_results_file")
	# Create a new group under "/" (root)
	g = h5file.createGroup("/", 'phenotypes', 'Basic phenotype folder')
	h5file.createTable(g, 'info', PhenotypeInfo, "Phenotyping information")
	h5file.flush()
	h5file.close()


def add_new_phenotype_file(hdf5_file_name, phenotype_file, phen_name, growth_conditions='', phenotype_scoring='',
			method_description='', measurement_scale='', is_binary=False):
	"""
	Initializes the phenotype group for this phenotype and inserts it into the file object.
	"""
	#Now parsing the phenotype file
	h5file = tables.openFile(hdf5_file_name, mode="rw")
	print h5file
	phend = pd.readPhenotypeFile(phenotype_file)
	_init_phenotype_(h5file, phen_name, growth_conditions=growth_conditions, phenotype_scoring=phenotype_scoring,
			method_description=method_description, measurement_scale=measurement_scale, is_binary=is_binary)
	add_phenotype_values(h5file, phen_name, phend.accessions, phend.getPhenVals(1), transformation='raw',
			accessions=phend.accessionNames, std_dev_values=None, value_comments=None)
	h5file.flush()
	h5file.close()



def add_new_phenotype(hdf5_file_name, phen_name, phenotype_values, ecotypes, accession_names=None, growth_conditions='', phenotype_scoring='',
			method_description='', measurement_scale='', is_binary=False):
	"""
	Initializes the phenotype group for this phenotype and inserts it into the file object.
	"""
	#Now parsing the phenotype file
	h5file = tables.openFile(hdf5_file_name, mode="r+")
	_init_phenotype_(h5file, phen_name, num_vals=len(phenotype_values), std_dev=sp.std(phenotype_values),
			growth_conditions=growth_conditions, phenotype_scoring=phenotype_scoring,
			method_description=method_description, measurement_scale=measurement_scale, is_binary=is_binary)

	add_phenotype_values(h5file, phen_name, ecotypes, phenotype_values, transformation='raw',
			accessions=accession_names, std_dev_values=None, value_comments=None)
	h5file.flush()
	h5file.close()


def _init_phenotype_(h5file, phen_name, num_vals=0.0, std_dev=0.0, growth_conditions='', phenotype_scoring='',
			method_description='', measurement_scale='', is_binary=False):
	"""
	Insert a new phenotype into the DB
	"""
	group = h5file.createGroup("/phenotypes", phen_name, 'Phenotype folder for ' + phen_name)
	table = h5file.getNode('/phenotypes/info')
	info = table.row
	info['name'] = phen_name
	info['num_values'] = num_vals
	info['std_dev'] = std_dev
	info['growth_conditions'] = growth_conditions
	info['phenotype_scoring'] = phenotype_scoring
	info['method_description'] = method_description
	info['measurement_scale'] = measurement_scale
	info['is_binary'] = is_binary
	info.append()
	table.flush()


def add_phenotype_values(h5file, phen_name, ecotypes, values, transformation='raw', transformation_description=None,
			accessions=None, std_dev_values=None, value_comments=None):
	"""
	Adds phenotype values, to an existing phenotype, e.g. when applying different transformations.
	"""

	phen_group = h5file.getNode('/phenotypes/%s' % phen_name)
	table = h5file.createTable(phen_group, 'transformation_info', TransformationInfo, "Transformation information")
	info = table.row
	info['name'] = transformation
	if transformation_description: info['description'] = transformation_description
	info.append()
	table.flush()

	trans_group = h5file.createGroup(phen_group, transformation, 'Transformation: ' + transformation)
	table = h5file.createTable(trans_group, 'values', PhenotypeValue, "Phenotype values")
	value = table.row
	for i, (ei, v) in enumerate(itertools.izip(ecotypes, values)):
		value['ecotype'] = ei
		value['mean_value'] = v
		if accessions: value['accession_name'] = accessions[i]
		if std_dev_values: value['std_dev'] = std_dev_values[i]
		if value_comments: value['comment'] = value_comments[i]
		value.append()
	table.flush()



def get_phenotype_values(hdf5_filename, phen_name, transformation='raw'):
	"""
	Returns the phenotype values
	"""
	h5file = tables.openFile(hdf5_filename, mode="r")
	table = h5file.getNode('/phenotypes/%s/%s/values' % (phen_name, transformation))
	d = {'ecotype' : [], 'mean_value' : [], 'accession_name': [], 'std_dev': [], 'comment':[]}
	for x in table.iterrows():
		for k in d:
			d[k].append(x[k])
	h5file.close()
	return d



def get_phenotype_info(hdf5_filename, phen_name=None):
	"""
	Returns the phenotype meta data in a dict.
	"""
	dict_list = []
	h5file = tables.openFile(hdf5_filename, mode="r")
	table = h5file.getNode('/phenotypes/info')
	if not phen_name:
		for x in table.iterrows():
			d = {'name': '', 'num_values': 0, 'std_dev': 0.0, 'growth_conditions': '',
				'phenotype_scoring': '', 'method_description': '', 'measurement_scale': '',
				'is_binary': False}
			for k in d:
				d[k] = x[k]
			dict_list.append(d)
	else:
		for x in table.where('name=="%s"' % phen_name):
			d = {'name': '', 'num_values': 0, 'std_dev': 0.0, 'growth_conditions': '',
				'phenotype_scoring': '', 'method_description': '', 'measurement_scale': '',
				'is_binary': False}
			for k in d:
				d[k] = x[k]
			dict_list.append(d)

	h5file.close()
	return dict_list



def get_phenotype_transformations(hdf5_filename, phen_name):
	"""
	Returns the phenotype values
	"""
	d = {'names': [], 'descriptions': []}
	h5file = tables.openFile(hdf5_filename, mode="r")
	table = h5file.getNode('/phenotypes/%s' % phen_name)
	for x in table.iterrows():
		for k in d:
			d[k].append(x[k])
	h5file.close()
	return d



def add_results(hdf5_filename, phen_name, chromosomes, positions, scores, mafs, macs, analysis_method,
		analysis_comment='', transformation='raw', **kwargs):
	"""
	Add a result to the hdf5 file.
	"""
	h5file = tables.openFile(hdf5_file_name, mode="r+")
	trans_group = h5file.getNode('/phenotypes/%s/%s' % (phen_name, transformation))
	table = h5file.createTable(phen_group, 'result_info', ResultInfo, "Result information")
	info = table.row
	info['analysis_method'] = analysis_method
	if analysis_comment: info['comment'] = analysis_comment
	info.append()
	table.flush()

	analysis_group = h5file.createGroup(trans_group, analysis_method, 'Analysis method: ' + analysis_method)
	if analysis_method in ['emmax', 'lm']:
		table = h5file.createTable(analysis_group, 'results', ResultRecordLM, "Regression result")
	elif analysis_method is 'kw':
		table = h5file.createTable(analysis_group, 'results', ResultRecordKW, "Regression result")
	else:
		raise Exception('Not implemented for analysis method %s' % analysis_method)
	result = table.row


	for i, cpsmm in enumerate(itertools.izip(chromosomes, positions, scores, mafs, macs)):
		(result['chromosome'], result['position'], result['score'], result['maf'], result['mac']) = cpsmm
		if analysis_method == 'kw':
			result['statistic'] = kwargs['statistics'][i]
		else: #EMMAX or LM
			result['beta0'] = kwargs['beta0'][i]
			result['beta1'] = kwargs['beta1'][i]
			result['correlation'] = kwargs['correlation'][i]
			result['genotype_var_perc'] = kwargs['genotype_var_perc'][i]
		result.append()
	table.flush()
	h5file.close()




def get_results(hdf5_filename, phen_name, analysis_method, transformation='raw'):
	"""
	Return results..
	"""
	d = {'chromosome': [], 'position': [], 'score': [], 'maf': [], 'mac': []}
	if analysis_method == 'kw':
		d['statistic'] = []
	else:
		d['beta0'] = []
		d['beta1'] = []
		d['correlation'] = []
		d['genotype_var_perc'] = []

	h5file = tables.openFile(hdf5_filename, mode="r")
	table = h5file.getNode('/phenotypes/%s/%s/%s/results' % (phen_name, transformation, analysis_method))
	for x in table.iterrows():
		for k in d:
			d[k].append(x[k])
	h5file.close()
	return d




def _test_():
	#Load phenotype data..
	import phenotypeData as pd
	import phenotypeData as pd
	import gwaResults as gr
	phed = pd.readPhenotypeFile('/Users/bjarnivilhjalmsson/Projects/Data/phenotypes/phen_raw_092910.tsv')
	pid1 = 1
	phed.filter_accessions_w_missing_data(pid1)
	phen_name = phed.getPhenotypeName(pid1)
	phen_vals = phed.getPhenVals(pid1)
	ecotypes = phed.accessions
	is_binary = phed.isBinary(pid1)

	#Creating the first hdf5 file
	hdf5_file_name_1 = '/Users/bjarni.vilhjalmsson/tmp/test1.hdf5'
	init_file(hdf5_file_name_1)
	add_new_phenotype(hdf5_file_name_1, phen_name, phen_vals, ecotypes, is_binary=is_binary)
	print "First file is constructed"

	print "Now testing it"
	r = get_phenotype_values(hdf5_file_name_1, phen_name, 'raw')
	#print r

	phed = pd.readPhenotypeFile('/Users/bjarnivilhjalmsson/Projects/Data/phenotypes/phen_raw_092910.tsv')
	pid2 = 5
	phed.filter_accessions_w_missing_data(pid2)
	phen_name = phed.getPhenotypeName(pid2)
	phen_vals = phed.getPhenVals(pid2)
	ecotypes = phed.accessions
	is_binary = phed.isBinary(pid2)
	add_new_phenotype(hdf5_file_name_1, phen_name, phen_vals, ecotypes, is_binary=is_binary)

	print "Now testing it"
	r = get_phenotype_values(hdf5_file_name_1, phen_name, 'raw')
	#print r
	r = get_phenotype_info(hdf5_file_name_1, phen_name)
	print r

	result_file = '/Users/bjarnivilhjalmsson/tmp/pi1_pid5_FT10_emmax_none.pvals'
	res = gr.Result(result_file=result_file, name='FT10')


	add_results(hdf5_file_name_1, phen_name, res.snp_results['chromosomes'], res.snp_results['positions'],
			res.snp_results['scores'], res.snp_results['marfs'], res.snp_results['mafs'],
			analysis_method='emmax', transformation='raw', beta0=res.snp_results['beta0'])
	#hdf5_file_name_2 = '/Users/bjarni.vilhjalmsson/tmp/test2.hdf5'
	#init_file(hdf5_file_name_2)
	#print "Second file is constructed"


if __name__ == '__main__':
	_test_()



