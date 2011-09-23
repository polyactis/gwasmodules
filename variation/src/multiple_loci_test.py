"""
Tests involving stepwise regressions, and model selection.

Option:

	-i ...			The run phenotype index/indices.  
	-o ...			The run_id, used as unique identifier for this run.  
	-s			Collect results and plot things (Does not generate pvalue files...) 

	-t ...			What data set is used. (75 is default)

	-n ...			Number of SNPs (phenotypes) per node, default is 1
	-d ...			Debug filter, random fraction of phenotypes or snps will be used.

	-l ...			Type of latent variable: random_snps (default), random, pc_split, etc..
	-h ...			Heritability in percentages, possible values are 1,10,25,50,75,90,99
	
	-m ...			How to generate the phenotypes: plus, xor, or

	--save_plots           	Plot Manhattan plots
	--save_pvals           	Include p-values into the .pickled files.
	--phen_file=...		File where the phenotypes will be saved, and loaded from.
	--sim_phen		Simulate phenotype, write to phenotype file.
	--parallel		Run parallel on the cluster
	--num_steps=...		Number of steps in the regression. (Default is 10)
	--herit_plots=...	Plot heritabilities
	--var_plots		Plot variation analysis


Examples:
python multiple_loci_test.py run_index test -i 1,5 -a kw,emmax -b most_normal -r ~/Projects/Data/phenotypes/phen_raw_092910.tsv 

"""
import matplotlib
matplotlib.use('Agg')

import pylab
import cPickle
import scipy as sp
import linear_models as lm
import scipy.linalg as linalg
import phenotypeData
import snpsdata
import sys
import os
import env
import random
import dataParsers as dp
import util
import gwaResults as gr
import analyze_gwas_results as agr
import traceback
import getopt
import time
import pdb


mapping_methods = ['LM', 'KW', 'EX', 'Stepw_LM', 'Stepw_EX'] #5 in total

def parse_parameters():
	'Parse the parameters into a dict, etc.'
	if len(sys.argv) == 1:
		print __doc__
		sys.exit(2)

	long_options_list = ['save_plots', 'phen_file=', 'sim_phen', 'num_steps=', 'parallel', 'herit_plots=', 'var_plots', 'save_pvals']
	try:
		opts, args = getopt.getopt(sys.argv[1:], "i:o:t:k:n:d:l:m:h:s", long_options_list)

	except:
		traceback.print_exc()
		print __doc__
		sys.exit(2)

	p_dict = {'number_per_run':20, 'debug_filter':1.0, 'summarize':False,
		'latent_variable':'random_snp', 'phenotype_model':'plus', 'run_id':'mlt',
		'mapping_method':'emmax', 'heritability':50, 'save_plots':False, 'call_method_id':75,
		'phen_file':env.env['phen_dir'] + 'multi_locus_phen.pickled', 'num_steps':10,
		'phen_index':None, 'sim_phen':False, 'parallel':False, 'herit_plots':None,
		'var_plots':False, 'save_pvals':False}


	for opt, arg in opts:
		if opt in ('-i'): p_dict['phen_index'] = util.parse_ids(arg)
		elif opt in ('-o'): p_dict['run_id'] = arg
		elif opt in ('-t'): p_dict['call_method_id'] = int(arg)
		elif opt in ('-n'): p_dict['number_per_run'] = int(arg)
		elif opt in ('-m'): p_dict['phenotype_model'] = arg
		elif opt in ('-d'): p_dict['debug_filter'] = float(arg)
		elif opt in ('-l'): p_dict['latent_variable'] = arg
		elif opt in ("-s"): p_dict['summarize'] = True
		elif opt in ('-h'): p_dict['heritability'] = int(arg)
		elif opt in ("--phen_file"): p_dict['phen_file'] = arg
		elif opt in ("--save_plots"): p_dict['save_plots'] = True
		elif opt in ("--save_pvals"): p_dict['save_pvals'] = True
		elif opt in ("--sim_phen"): p_dict['sim_phen'] = True
		elif opt in ("--num_steps"): p_dict['num_steps'] = int(arg)
		elif opt in ("--parallel"): p_dict['parallel'] = True
		elif opt in ("--herit_plots"): p_dict['herit_plots'] = util.parse_ids(arg)
		elif opt in ("--var_plots"): p_dict['var_plots'] = True
		else:
			print "Unkown option!!\n"
			print __doc__
			sys.exit(2)

	print p_dict, args
	return p_dict, args




def run_parallel(run_id, start_i, stop_i, latent_var, heritability, phen_model,
		phen_file, summary_run, call_method_id, num_steps, cluster='gmi'):
	"""
	If no mapping_method, then analysis run is set up.
	"""
	phen_ids_str = '%d-%d' % (start_i, stop_i)
	job_id = '%s_%s_lv%s_h%d_m%s_ns%d_t%d' % (run_id, phen_ids_str , latent_var,
						heritability, phen_model, num_steps, call_method_id)
	file_prefix = env.env['results_dir'] + job_id

	#Cluster specific parameters	
	if cluster == 'gmi': #GMI cluster.  
		shstr = '#!/bin/bash\n'
		shstr += '#$ -S /bin/bash\n'
		shstr += '#$ -N %s\n' % job_id
		shstr += '#$ -o %s_job_$JOB_ID.out\n' % file_prefix
		shstr += '#$ -e %s_job_$JOB_ID.err\n' % file_prefix
		shstr += 'source /etc/modules-env.sh\n'
		shstr += 'module load scipy/GotoBLAS2/0.9.0\n'
		shstr += 'module load matplotlib/1.0.0\n'
		shstr += 'module load mysqldb/1.2.3\n'
		shstr += 'export GOTO_NUM_THREADS=1\n'

	elif cluster == 'usc':  #USC cluster.
		shstr = "#!/bin/csh\n"
		shstr += "#PBS -l walltime=%s \n" % '72:00:00'
		shstr += "#PBS -l mem=%s \n" % '2950mb'
		shstr += "#PBS -q cmb\n"
		shstr += "#PBS -N p%s \n" % job_id

	shstr += "python %smultiple_loci_test.py -i %s -l %s -h %d -m %s --phen_file=%s -t %d --num_steps=%d " % \
		(env.env['script_dir'], phen_ids_str, latent_var, heritability, phen_model, phen_file, call_method_id, num_steps)
	if summary_run:
		shstr += '-s '

	#shstr += "> " + file_prefix + "_job.out) >& " + file_prefix + "_job.err\n"
	print '\n', shstr, '\n'
	script_file_name = run_id + ".sh"
	f = open(script_file_name, 'w')
	f.write(shstr)
	f.close()

	#Execute qsub script
	if cluster == 'gmi':
		os.system("qsub " + script_file_name)
	elif cluster == 'usc':
		os.system("qsub " + script_file_name)




def get_snps_heritabilities(snps, phenotype):
	Y = sp.mat(phenotype).T
	rss_0 = sp.var(Y) * len(phenotype)
	X_0 = sp.mat(sp.ones((len(phenotype), 1)))

	h_expl = []
	for snp in snps:
		rss = linalg.lstsq(sp.hstack([X_0, sp.mat(snp).T]), Y)[1]
		h_expl.append(1 - (rss / rss_0))
	return h_expl


def __get_latent_snps__(ets):
	ecotype_info_dict = phenotypeData.get_ecotype_id_info_dict()
	north_south_split_snp = []
	lats = [ecotype_info_dict[int(et)][2] for et in ets]
	m = sp.median(lats)
	for et in ets:
		latitude = ecotype_info_dict[int(et)][2]
		north_south_split_snp.append(1) if latitude > m else north_south_split_snp.append(0)
	pc_snp = []
	K = dp.load_kinship() #All ecotypes
	(evals, evecs) = linalg.eigh(K)
	pc = (sp.mat(evecs).T[-1]).tolist()[0]
	m = sp.median(pc)
	for v in pc:
		pc_snp.append(1) if v > m else pc_snp.append(0)
	return sp.array(north_south_split_snp, dtype='int8'), sp.array(pc_snp, dtype='int8')


def simulate_phenotypes(phen_file, sd, mac_threshold=0, debug_filter=1.0, num_phens=100):
	"""
	Simulate the phenotypes
	"""
	print 'Generating the phenotypes'
	latent_var_keys = ['random_snp', 'random', 'north_south_split', 'pc_split']
	phenotype_models = ['xor', 'or', 'plus', 'xor2']
	heritabilities = [1, 2, 5, 10, 15, 20, 25, 50] #in percentages

	if mac_threshold > 0:
		sd.filter_mac_snps(mac_threshold)
	num_lines = len(sd.accessions)  #Number of lines
	mafs = sd.get_mafs()["marfs"]
	if debug_filter:
		sd.sample_snps(debug_filter)
	snp_chr_pos_maf_list = sd.get_all_snp_w_info()
	all_indices = range(len(snp_chr_pos_maf_list))
	snp_indices = random.sample(all_indices, num_phens)
	map(all_indices.remove, snp_indices)

	#The first locus..
	snp_chr_pos_maf_list = [snp_chr_pos_maf_list[i] for i in snp_indices]

	#Invert every other SNP (randomize the SNP decoding)
	all_indices = range(len(snp_chr_pos_maf_list))
	invert_indices = random.sample(all_indices, num_phens / 2)
	for i in invert_indices:
		snp, chr, pos, maf = snp_chr_pos_maf_list[i]
		snp_chr_pos_maf_list[i] = (lm.get_anti_snp(snp), chr, pos, maf)

	north_south_split_snp, pc_snp = __get_latent_snps__(sd.accessions)

	phen_dict = {'snp_chr_pos_maf_list': snp_chr_pos_maf_list, 'snp_indices':snp_indices,
			'north_south_split_snp':north_south_split_snp, 'pc_snp':pc_snp}
	for latent_var in latent_var_keys:
		d = {}
		if latent_var == 'random_snp':
			l_snp_indices = random.sample(all_indices, num_phens)
			latent_snps = [snp_chr_pos_maf_list[i][0] for i in l_snp_indices]
			d['latent_chr_pos_maf_list'] = \
				[(snp_chr_pos_maf_list[i][1], snp_chr_pos_maf_list[i][2], \
				snp_chr_pos_maf_list[i][3]) for i in l_snp_indices]
			d['latent_snps'] = latent_snps

		elif latent_var == 'random':
			latent_snps = []
			for i in range(num_phens):
				num_ones = random.randint(1, num_lines - 1)
				l_snp = [0] * num_lines
				one_indices = random.sample(range(num_lines), num_ones)
				for i in one_indices:
					l_snp[i] = 1
				latent_snps.append(sp.array(l_snp, dtype='int8'))
			d['latent_snps'] = latent_snps

		elif latent_var == 'north_south_split':
			latent_snp = north_south_split_snp
			d['latent_snp'] = latent_snp

		elif latent_var == 'pc_snp':
			latent_snp = pc_snp
			d['latent_snp'] = latent_snp

		for h in heritabilities:
			her = h / 100.0
			d2 = {}
			for phen_model in phenotype_models:  #Simulate all phenotype models.
				d3 = {'phenotypes': [], 'h_estimates': [], 'h_loci_est_list': []}
				for i in range(num_phens):
					if latent_var in ['random_snp', 'random']:
						latent_snp = latent_snps[i]
					snp = snp_chr_pos_maf_list[i][0]
					if phen_model == 'xor':
						phenotype = snp ^ latent_snp
					elif phen_model == 'or':
						phenotype = snp | latent_snp
					elif phen_model == 'plus':
						phenotype = snp + latent_snp
					elif phen_model == 'xor2':
						phenotype = (snp ^ latent_snp) + 0.5 * (snp & latent_snp)
					if len(sp.unique(phenotype)) > 1:
						phen_var = sp.var(phenotype, ddof=1)
						error_vector = sp.random.normal(0, 1, size=num_lines)
						error_var = sp.var(error_vector, ddof=1)
						scalar = sp.sqrt((phen_var / error_var) * ((1 - her) / her))
						phenotype = phenotype + error_vector * scalar
						h_est = phen_var / sp.var(phenotype, ddof=1)
						h_est_snp1 = sp.corrcoef(snp, phenotype)[0, 1]
						h_est_snp2 = sp.corrcoef(latent_snp, phenotype)[0, 1]
						#print phen_model, latent_var, her, h_est, h_est_snp1 ** 2, h_est_snp2 ** 2
						d3['h_loci_est_list'].append(h_est)
						d3['h_estimates'].append((h_est_snp1 ** 2, h_est_snp2 ** 2))
					else:
						print 'encountered invalid phenotype for phen_model: %s' % phen_model
						phenotype = None
					d3['phenotypes'].append(phenotype)
				d2[phen_model] = d3
			d[h] = d2
		phen_dict[latent_var] = d


	#phenotype_models for loop ends.
	f = open(phen_file, "wb")
	print "dumping phenotypes to file:", f
	cPickle.dump(phen_dict, f, protocol=2)
	f.close()


def load_phenotypes(phen_file):
	print 'Loading phenotypes and related data'
        f = open(phen_file, "rb")
	phen_dict = cPickle.load(f)
	f.close()
        print 'Loading done..'
	return phen_dict


def summarize_runs(file_prefix, latent_var, heritability, phen_model, phen_d, index_list=None):
	"""
	Summarize runs.. duh
	"""
	pd = phen_d[latent_var][heritability][phen_model]
	if not index_list:
		index_list = range(len(pd['phenotypes']))

	num_pthres = len(pval_thresholds)
	num_winsizes = len(window_sizes)
	summary_dict = {'p_her':[]}
	analysis_methods = ['LM', 'KW', 'EX', 'Stepw_LM_Bonf', 'Stepw_LM_EBIC', 'Stepw_LM_MBIC',
				'Stepw_EX_Bonf', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC']

	#Initializing stuff
	for am in analysis_methods:
		if am in ['LM', 'EX', 'KW']:
			d = {'fdrs':sp.zeros((num_pthres, num_winsizes), dtype='double'),
				'tprs':sp.zeros((num_pthres, num_winsizes), dtype='double')}
			d['ks'] = []
			d['medp'] = []
		else:
			if am in ['Stepw_EX_EBIC', 'Stepw_EX_MBIC', 'Stepw_LM_EBIC', 'Stepw_LM_MBIC']:
				d = {'fdrs':sp.zeros((num_winsizes), dtype='double'),
					'tprs':sp.zeros((num_winsizes), dtype='double')}
			else:
				d = {'fdrs':sp.zeros((num_pthres, num_winsizes), dtype='double'),
					'tprs':sp.zeros((num_pthres, num_winsizes), dtype='double')}
			d['perc_var_expl'] = []
			if 'EX' in am:
				d['rem_p_her'] = []
				d['perc_phen_var_expl'] = []
				d['perc_err_var_expl'] = []

		summary_dict[am] = d

	criteria_map = {'mbonf':('Stepw_EX_Bonf', 'Stepw_LM_Bonf'), 'ebics': ('Stepw_EX_EBIC', 'Stepw_LM_EBIC'),
			'mbics': ('Stepw_EX_MBIC', 'Stepw_LM_MBIC')}

	num_files_found = 0
	print '%s_%d_%s_%s' % (file_prefix, heritability, latent_var, phen_model)
	for i in index_list:
		pickled_file = '%s_%d_%s_%s_%dresults.pickled' % (file_prefix, heritability, latent_var, phen_model, i)
		if os.path.isfile(pickled_file):
			num_files_found += 1
			with open(pickled_file) as f:
				r = cPickle.load(f)
			p_her = r['p_her']
			summary_dict['p_her'].append(p_her)
			for am in mapping_methods:
				if am == 'Stepw_LM':
					for criteria in ['mbonf', 'ebics', 'mbics']:
						for rs in ['fdrs', 'tprs']:
							rs_array = sp.array(r[am][criteria][rs])
							rs_array[rs_array == -1.0] = 0
							summary_dict[criteria_map[criteria][1]][rs] += rs_array

						summary_dict[criteria_map[criteria][1]]['perc_var_expl'].append(r[am][criteria]['perc_var_expl'])
				elif am == 'Stepw_EX':
					for criteria in ['mbonf', 'ebics', 'mbics']:
						for rs in ['fdrs', 'tprs']:
							rs_array = sp.array(r[am][criteria][rs])
							rs_array[rs_array == -1.0] = 0
							summary_dict[criteria_map[criteria][0]][rs] += rs_array
						if 'pseudo_heritability' in r[am][criteria]:
							rem_p_her = r[am][criteria]['pseudo_heritability']
						else:
							rem_p_her = r[am][criteria]['remaining_p_her']
						perc_var_expl = r[am][criteria]['perc_var_expl']
						summary_dict[criteria_map[criteria][0]]['rem_p_her'].append(rem_p_her)
						summary_dict[criteria_map[criteria][0]]['perc_var_expl'].append(perc_var_expl)
						rss_0 = r[am]['step_info_list'][0]['rss']
						rss = r[am]['step_info_list'][r[am][criteria]['opt_i']]['rss']

						if p_her > 0.01:
							summary_dict[criteria_map[criteria][0]]['perc_phen_var_expl'].append(1.0 - ((rss * rem_p_her) / (rss_0 * p_her)))
							summary_dict[criteria_map[criteria][0]]['perc_err_var_expl'].append(1.0 - ((rss * (1 - rem_p_her)) / (rss_0 * (1 - p_her))))
				elif am in ['LM', 'KW', 'EX']:
					summary_dict[am]['fdrs'] += sp.array(r[am]['fdrs'])
					summary_dict[am]['tprs'] += sp.array(r[am]['tprs'])
					summary_dict[am]['ks'].append(r[am]['ks_stat']['D'])
					summary_dict[am]['medp'].append(r[am]['med_pval'])
	print 'Found %d results' % num_files_found
	for am in analysis_methods:
		summary_dict[am]['bonf'] = {}
		for k in ['fdrs', 'tprs']:
			summary_dict[am][k] = summary_dict[am][k] / float(num_files_found)
			if not am in ['Stepw_LM_EBIC', 'Stepw_LM_MBIC', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC']:
				summary_dict[am]['bonf'][k] = summary_dict[am][k][11] * 0.74 + summary_dict[am][k][12] * 0.26
	return summary_dict



def plot_tprs_fdrs(file_prefix, summary_dict):
	"""
	Plot various things relating to run summaries
	"""
	import matplotlib.font_manager
	prop = matplotlib.font_manager.FontProperties(size=10)

	#Heritabilities..
	# - histogram of each category
	# - pseudoheritabilities vs. ks and med pval. of KW and LM

	# TPRs vs. FDRs
	am_list = ['LM', 'KW', 'EX', 'Stepw_LM_Bonf', 'Stepw_EX_Bonf']
	am_colors = ['r', 'g', 'b', 'r', 'b']
	am_ls = ['--', '--', '--', '-', '-']
	am_dot_list = ['Stepw_EX_EBIC', 'Stepw_EX_MBIC', 'Stepw_LM_EBIC', 'Stepw_LM_MBIC']
	am_dot_colors = ['#22DD66', '#22DD66', '#DD2266', '#DD2266']
	am_dot_marker = ['s', '^', 's', '^']

	for w_i, ws in enumerate(window_sizes):
		pylab.figure(figsize=(7, 6))
		pylab.axes([0.09, 0.08, 0.9, 0.85])
		for am, amc, amls in zip(am_list, am_colors, am_ls):
			xs = sp.zeros(len(pval_thresholds))
			ys = sp.zeros(len(pval_thresholds))
			for pt_i, pt in enumerate(pval_thresholds):
				ys[pt_i] = summary_dict[am]['tprs'][pt_i][w_i]
				xs[pt_i] = summary_dict[am]['fdrs'][pt_i][w_i]
			pylab.plot(xs, ys, label=am, color=amc, ls=amls, alpha=0.6, marker='.')
		for am, amc, amm in zip(am_dot_list, am_dot_colors, am_dot_marker):
			pylab.plot(summary_dict[am]['fdrs'][w_i], summary_dict[am]['tprs'][w_i], label=am, marker=amm,
				ls='', color=amc, alpha=0.6)
		png_file = '%s_w%d.png' % (file_prefix, ws)
		pylab.ylabel('Power')
		pylab.xlabel('FDR')
		pylab.legend(loc=4, prop=prop, numpoints=1, scatterpoints=1)
		x_min, x_max = pylab.xlim()
		x_range = x_max - x_min
		y_min, y_max = pylab.ylim()
		y_range = y_max - y_min
		pylab.axis([x_min - 0.025 * x_range, x_max + 0.025 * x_range,
				y_min - 0.025 * y_range, y_max + 0.025 * y_range])

		pylab.savefig(png_file)
		pylab.clf()



def plot_single_tprs_fdrs(summary_dict, ax, ws, w_legend=False, y_label='Power', x_label='FDR', y_lim=None):
	"""
	Plot various things relating to run summaries
	"""
	import matplotlib.font_manager
	prop = matplotlib.font_manager.FontProperties(size=10)

	#Heritabilities..
	# - histogram of each category
	# - pseudoheritabilities vs. ks and med pval. of KW and LM

	# TPRs vs. FDRs
	am_list = ['LM', 'EX', 'Stepw_LM_Bonf', 'Stepw_EX_Bonf']
	am_labels = ['LM', 'EX', 'SWLM', 'MLMM']
	#am_colors = ['#CC9922', '#2299CC', '#FF0022', '#0022FF']
	am_colors = ['#FF0022', '#0022FF', '#FF0022', '#0022FF']
	am_ls = ['--', '--', '-', '-']
	am_dot_list = ['Stepw_LM_EBIC', 'Stepw_EX_EBIC']
	am_dot_colors = ['#FF0022', '#0022FF']
	#am_dot_labels = ['MLML EBIC', 'SWLM EBIC']

	w_i = window_sizes.index(ws)
	for am, amc, amls, am_label in zip(am_list, am_colors, am_ls, am_labels):
		xs = sp.zeros(len(pval_thresholds))
		ys = sp.zeros(len(pval_thresholds))
		for pt_i, pt in enumerate(pval_thresholds):
			ys[pt_i] = summary_dict[am]['tprs'][pt_i][w_i]
			xs[pt_i] = summary_dict[am]['fdrs'][pt_i][w_i]
		ax.plot(xs, ys, label=am_label, color=amc, ls=amls, alpha=0.4, lw=2)
		ax.plot(summary_dict[am]['bonf']['fdrs'][w_i], summary_dict[am]['bonf']['tprs'][w_i], marker='o',
			ls='', color=amc, alpha=0.45)
	for am, amc in zip(am_dot_list, am_dot_colors):
		ax.plot(summary_dict[am]['fdrs'][w_i], summary_dict[am]['tprs'][w_i], marker='v',
			ls='', color=amc, alpha=0.45)
	ax.set_ylabel(y_label)
	ax.set_xlabel(x_label)
	if y_lim:
		ax.set_ylim(y_lim)
	x_min, x_max = ax.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax.get_ylim()
	y_range = y_max - y_min
	ax.plot(x_min - x_range, y_min - y_range, color='k', marker='v', label='EBIC', alpha=0.45)
	ax.plot(x_min - x_range, y_min - y_range, color='k', marker='o', label='Bonferroni', alpha=0.45)
	if w_legend:
		ax.legend(loc=4, prop=prop, numpoints=1, scatterpoints=1)
	ax.axis([x_min - 0.025 * x_range, x_max + 0.025 * x_range,
			y_min - 0.025 * y_range, y_max + 0.025 * y_range])



def plot_single_tprs_fdrs_2(summary_dict, ax, ws, w_legend=False, y_label='Power', x_label='FDR', y_lim=None):
	"""
	Plot various things relating to run summaries
	"""
	import matplotlib.font_manager
	prop = matplotlib.font_manager.FontProperties(size=10)

	#Heritabilities..
	# - histogram of each category
	# - pseudoheritabilities vs. ks and med pval. of KW and LM

	# TPRs vs. FDRs
	am_list = ['SLR', 'EMMAX', 'FBLR-bwd', 'MLMM-bwd']
	am_labels = ['LM', 'EX', 'SWLM', 'MLMM']
	am_colors = ['#CC9922', '#2299CC', '#FF0022', '#0022FF']
	am_ls = ['-', '-', '-', '-']
	am_dot_list = ['FBLR-bwd', 'MLMM-bwd']
	am_dot_colors = ['#FF0022', '#0022FF']

	for am, amc, amls, am_label in zip(am_list, am_colors, am_ls, am_labels):
		ax.plot(summary_dict[ws][am]['fdr'], summary_dict[ws][am]['power'], label=am_label, color=amc,
			ls=amls, alpha=0.4, lw=2)
		ax.plot(summary_dict[ws][am]['BONF']['fdr'], summary_dict[ws][am]['BONF']['power'], marker='o',
			ls='', color=amc, alpha=0.45)
	for am, amc in zip(am_dot_list, am_dot_colors):
		ax.plot(summary_dict[ws][am]['EBIC']['fdr'], summary_dict[ws][am]['EBIC']['power'], marker='v',
			ls='', color=amc, alpha=0.45)
	ax.set_ylabel(y_label)
	ax.set_xlabel(x_label)
	if y_lim:
		ax.set_ylim(y_lim)
	x_min, x_max = ax.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax.get_ylim()
	y_range = y_max - y_min
	ax.plot(x_min - x_range, y_min - y_range, color='k', marker='v', label='EBIC', alpha=0.45)
	ax.plot(x_min - x_range, y_min - y_range, color='k', marker='o', label='Bonferroni', alpha=0.45)
	if w_legend:
		ax.legend(loc=4, prop=prop, numpoints=1, scatterpoints=1)
	ax.axis([x_min - 0.025 * x_range, x_max + 0.025 * x_range,
			y_min - 0.025 * y_range, y_max + 0.025 * y_range])





def plot_herit_hist(file_prefix, her_dict, latent_var, phen_model):
	import matplotlib.font_manager
	prop = matplotlib.font_manager.FontProperties(size=10)
	file_prefix += '_%s_%s' % (latent_var, phen_model)
	png_file_name = file_prefix + '_h%s_hist.png' % ('_'.join(map(str, her_dict.keys())))
	max_bin_count = 0
	for h in sorted(her_dict):
		bin_counts, bins, patch_list = pylab.hist(her_dict[h]['p_her'], range=(0, 0.8), bins=25, alpha=0.6)
		max_bin_count = max(max_bin_count, max(bin_counts))
		pylab.axvline((h / 100.0), color='k', alpha=0.8, ls='-.')
		pylab.axvline(sp.median(her_dict[h]['p_her']), color='#DD3311', alpha=0.8, ls='-.')
	y_range = max_bin_count - 0
	pylab.axis([-0.8 * 0.025, 0.8 * 1.025, -0.025 * max_bin_count, max_bin_count * 1.025])
	pylab.xlabel('heritability')
	pylab.ylabel('Counts')
	pylab.savefig(png_file_name)

	pylab.figure()
	png_file_name = file_prefix + '_h%s_ks_her_scatter.png' % ('_'.join(map(str, her_dict.keys())))
	for h in sorted(her_dict):
		pylab.plot(her_dict[h]['p_her'], her_dict[h]['LM']['ks'], ls='', marker='.', alpha=0.5, label='herit.=%0.2f' % (h / 100.0))
	pylab.xlabel('pseudo-heritability')
	pylab.ylabel('Kolmogorov-Smirnov statistic')
	pylab.legend(loc=2, prop=prop, numpoints=1, scatterpoints=1)
	pylab.savefig(png_file_name)

	pylab.figure()
	png_file_name = file_prefix + '_h%s_pmed_her_scatter.png' % ('_'.join(map(str, her_dict.keys())))
	for h in sorted(her_dict):
		pylab.plot(her_dict[h]['p_her'], her_dict[h]['LM']['medp'], ls='', marker='.', alpha=0.5, label='herit.=%0.2f' % (h / 100.0))
	pylab.xlabel('pseudo-heritability')
	pylab.ylabel('Median pvalue bias')
	pylab.legend(loc=2, prop=prop, numpoints=1, scatterpoints=1)
	pylab.savefig(png_file_name)


	x = []
	for h in sorted(her_dict):
		pylab.figure()
		png_file_name = file_prefix + '_h%d_hist.png' % (h)
		p_her_bias = (sp.array(her_dict[h]['p_her']) - h / 100.0)
		bin_counts, bins, patch_list = pylab.hist(p_her_bias, range=(-0.25, 0.25), bins=25, alpha=0.6)
		max_bin_count = max(bin_counts)
		pylab.axvline(0.0, color='k', alpha=0.6, ls='-.')
		y_range = max_bin_count - 0
		pylab.axis([-0.25 - 0.025 * 0.5, 0.25 + 0.5 * 0.025, -0.025 * max_bin_count, max_bin_count * 1.025])
		pylab.xlabel('pseudo-heritability bias')
		pylab.ylabel('Counts')
		x.append(p_her_bias)
		pylab.savefig(png_file_name)

	#Box-plot version
	png_file_name = file_prefix + '_h%s_boxplot.png' % ('_'.join(map(str, her_dict.keys())))
	pylab.figure()
	pylab.boxplot(x)
	pylab.ylabel('psuedo-heritability bias')
	pylab.axhline(0.0, color='k', alpha=0.6, ls='-.')
	pylab.xticks(range(1, len(x) + 1), map(str, sorted(her_dict.keys())))
	pylab.xlabel('Heritability')
	pylab.savefig(png_file_name)



def plot_var(file_prefix, d, latent_variable, heritability, phen_models):
	"""
	Plots variance explained by the model for plus,  xor, and or.
	"""

	#Plot remaining heritability
	file_prefix += '_%s_%d' % (latent_variable, heritability)
	for am in ['Stepw_EX_Bonf', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC']:
		png_file_name = file_prefix + '_%s_pher_boxplot.png' % (am)
		pylab.figure()
		rem_pher_list = []
		for m in phen_models:
			rem_pher_list.append(d[m][am]['rem_p_her'])
		pylab.boxplot(rem_pher_list)
		pylab.axhline(0.0, color='k', alpha=0.6, ls='-.')
		pylab.xticks(range(1, len(phen_models) + 1), phen_models)
		pylab.ylabel('Remaining pseudo-heritability in the model')
		pylab.savefig(png_file_name)

	#Plot % explained variance.
	for am in ['Stepw_EX_Bonf', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC', 'Stepw_LM_Bonf', 'Stepw_LM_EBIC', 'Stepw_LM_MBIC']:
		png_file_name = file_prefix + '_%s_var_boxplot.png' % (am)
		pylab.figure()
		perc_var_list = []
		for m in phen_models:
			perc_var_list.append(d[m][am]['perc_var_expl'])
		pylab.boxplot(perc_var_list)
		pylab.axhline(heritability / 100.0, color='k', alpha=0.6, ls='-.')
		pylab.xticks(range(1, len(phen_models) + 1), phen_models)
		pylab.ylabel('Percentage of variance explained in the model')
		pylab.savefig(png_file_name)

	#Plot % explained phenot. variance
	for am in ['Stepw_EX_Bonf', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC']:
		png_file_name = file_prefix + '_%s_phen_var_boxplot.png' % (am)
		pylab.figure()
		perc_var_list = []
		for m in phen_models:
			perc_var_list.append(d[m][am]['perc_phen_var_expl'])
		pylab.boxplot(perc_var_list)
		pylab.axhline(1.0, color='k', alpha=0.6, ls='-.')
		pylab.xticks(range(1, len(phen_models) + 1), phen_models)
		pylab.ylabel('Percentage of phenotypic variance explained in the model')
		pylab.savefig(png_file_name)
	#Plot % explained error variance
	for am in ['Stepw_EX_Bonf', 'Stepw_EX_EBIC', 'Stepw_EX_MBIC']:
		png_file_name = file_prefix + '_%s_err_var_boxplot.png' % (am)
		pylab.figure()
		perc_var_list = []
		for m in phen_models:
			perc_var_list.append(d[m][am]['perc_err_var_expl'])
		pylab.boxplot(perc_var_list)
		pylab.axhline(0.0, color='k', alpha=0.6, ls='-.')
		pylab.xticks(range(1, len(phen_models) + 1), phen_models)
		pylab.ylabel('Percentage of error variance explained in the model')
		pylab.savefig(png_file_name)




#def __get_thresholds(min_thres=16, max_thres=1, num_thres=60):
def __get_thresholds(min_thres=10, max_thres=1, num_thres=18):
	thres_step = (min_thres - max_thres) / float(num_thres)
	pval_thresholds = []
	for i in range(num_thres):
		pval_thresholds.append(max_thres + i * thres_step)
	return pval_thresholds

pval_thresholds = __get_thresholds()

window_sizes = [0, 1000, 5000, 10000, 25000, 50000, 100000]



def _update_stats_(gwa_res, c_chr, c_pos, l_chr=None, l_pos=None, significance_threshold=None, sign_res=None):
	"""
	Update result dictionary.
	"""
	res_dict = {}
	cpl = [(c_chr, c_pos)]#Causal chr_pos_list
	if l_chr != None:
		cpl.append((l_chr, l_pos))
	caus_indices = gwa_res.get_indices(cpl)
	gwa_res._rank_scores_()

	#Calculate KS and P-med..
	pvals = gwa_res.snp_results['scores'][:]
	res_dict['ks_stat'] = agr.calc_ks_stats(pvals)
	res_dict['med_pval'] = agr.calc_median(pvals)

	#Get causal p-values, and ranks
	res_dict['causal_pvals'] = [gwa_res.snp_results['scores'][i] for i in caus_indices]
	res_dict['causal_ranks'] = [gwa_res.ranks[i] for i in caus_indices]

	#Get significant chrom_pos_pvals..
	if (not sign_res) and significance_threshold :
		sign_res = gwa_res.filter_attr('scores', significance_threshold, reversed=True, return_clone=True)
		res_dict['sign_chr_pos'] = sign_res.get_chr_pos_score_list()
		res_dict['causal_dist_matrix'] = sign_res.get_distances(cpl)
	elif sign_res:
		res_dict['sign_chr_pos'] = sign_res.get_chr_pos_score_list()
		res_dict['causal_dist_matrix'] = sign_res.get_distances(cpl)


	#Of all SNPs ranked higher than the second causative... which is farthest from a nearest causative.
	dist = gwa_res.get_farthest_w_stronger_association(cpl)
	res_dict['dist_f_w_s_a'] = -1 if dist[0] > 0 else dist[1]

	#Perform power (sensitivity, TPR), FDR, FPR calculations..
	gwa_res.neg_log_trans()
	tprs_list = []
	fdrs_list = []
	for pval_thres in pval_thresholds:
		#Filter data
		gwa_res.filter_attr('scores', pval_thres)
		tprs, fdrs = gwa_res.get_power_analysis(cpl, window_sizes)
		tprs_list.append(tprs)
		fdrs_list.append(fdrs)
	res_dict['tprs'] = tprs_list #[p_valthreshold][window_size]
	res_dict['fdrs'] = fdrs_list #[p_valthreshold][window_size]
	return res_dict



def _update_sw_stats_(res_dict, step_info_list, opt_dict, c_chr, c_pos, l_chr=None, l_pos=None,
			significance_threshold=None, type='LM'):
	"""
	Update result dictionary for a stepwise result.
	"""
	res_dict['step_info_list'] = step_info_list
	cpl = [(c_chr, c_pos)]#Causal chr_pos_list
	if l_chr != None:
		cpl.append((l_chr, l_pos))

	for criteria in ['mbonf', 'mbics', 'ebics']:
		opt_i = opt_dict[criteria]
		d = {'opt_i':opt_i}
		si = step_info_list[opt_i]
		if criteria == 'mbonf':
			tprs_list = []
			fdrs_list = []
			t_opt_i_list = []
			num_steps = len(step_info_list) / 2
			max_cof_pvals = -sp.log10([step_info_list[i]['mbonf'] for i in range(1, 2 * num_steps)])
			for pval_thres in pval_thresholds:
				t_opt_i = 0
				for i in range(num_steps):
					if max_cof_pvals[i] >= pval_thres:
						t_opt_i = i + 1
				for j in range(1, num_steps):
					i = 2 * num_steps - j - 1
					if max_cof_pvals[i] >= pval_thres:
						if j > t_opt_i:
							t_opt_i = i + 1
				if t_opt_i == 0:
					tprs = [-1 for ws in window_sizes]
					fdrs = [-1 for ws in window_sizes]
				else:
					t_si = step_info_list[t_opt_i]
					cpst = map(list, zip(*t_si['cofactors']))
					sign_res = gr.Result(scores=cpst[2], chromosomes=cpst[0], positions=cpst[1])
					tprs, fdrs = sign_res.get_power_analysis(cpl, window_sizes)
				tprs_list.append(tprs)
				fdrs_list.append(fdrs)
				t_opt_i_list.append(t_opt_i)
			d['tprs'] = tprs_list #[p_valthreshold][window_size]
			d['fdrs'] = fdrs_list #[p_valthreshold][window_size]
			d['t_opt_i_list'] = t_opt_i_list


		if opt_i == 0:
			#Set default values (Are these appropriate?)
			d['tprs'] = [-1 for ws in window_sizes]
			d['fdrs'] = [-1 for ws in window_sizes]
			d['sign_chr_pos'] = []
			d['causal_dist_matrix'] = []
		else:
			cpst = map(list, zip(*si['cofactors']))
			#Create a result object..
			sign_res = gr.Result(scores=cpst[2], chromosomes=cpst[0], positions=cpst[1])
			d['sign_chr_pos'] = sign_res.get_chr_pos_score_list()
			d['causal_dist_matrix'] = sign_res.get_distances(cpl)
			if criteria == 'mbonf':
				d['mbonf_tprs'], d['mbonf_fdrs'] = sign_res.get_power_analysis(cpl, window_sizes)
			else:
				d['tprs'], d['fdrs'] = sign_res.get_power_analysis(cpl, window_sizes)
		d['kolmogorov_smirnov'] = si['kolmogorov_smirnov']
		d['pval_median'] = si['pval_median']
		d['perc_var_expl'] = 1.0 - si['rss'] / step_info_list[0]['rss']
		d['num_cofactors'] = len(si['cofactors'])
		if type == 'EX':
			d['remaining_p_her'] = si['pseudo_heritability']
			d['perc_her_var_expl'] = (si['pseudo_heritability'] / step_info_list[0]['pseudo_heritability']) * d['perc_var_expl']
			d['perc_err_var_expl'] = ((1 - si['pseudo_heritability']) / (1 - step_info_list[0]['pseudo_heritability'])) * d['perc_var_expl']
		res_dict[criteria] = d




def run_analysis(sd, K, file_prefix, latent_var, heritability, phen_model, phen_index, phen_d,
		call_method_id, num_steps=10, pickle_results=True, save_plots=False, save_pvals=False):
	"""
	Perform the GWA mapping..
	using the different methods..
	
	Linear model, 
	Kruskal-Wallis
	EMMA
	
	Stepwise Linear Model (bonf. and ext. BIC)
	Stepwise EMMA (bonf. and ext. BIC)
	"""
	file_prefix += '_%d_%s_%s_%d' % (heritability, latent_var, phen_model, phen_index)

	pd = phen_d[latent_var][heritability][phen_model]

	result_dict = {}
	for mm in mapping_methods:
		result_dict[mm] = {}

	print "Loading SNPS dataset (again)"
	bonferroni_threshold = 1.0 / (20.0 * sd.num_snps())

	snps_list = sd.getSnps()
	phen_vals = pd['phenotypes'][phen_index]
	(c_snp, c_chr, c_pos, c_maf) = phen_d['snp_chr_pos_maf_list'][phen_index] #Causal SNP
	highlight_loci = [(c_chr, c_pos)]
	if latent_var == 'random_snp':
		(l_chr, l_pos, l_maf) = phen_d[latent_var]['latent_chr_pos_maf_list'][phen_index]
		highlight_loci.append((l_chr, l_pos))
	else:
		l_chr, l_pos = None, None

	print "Running Analysis"
	print 'Running KW'
	p_vals = util.kruskal_wallis(snps_list, phen_vals)['ps'].tolist()
	print len(p_vals)
	kw_res = gr.Result(snps_data=sd, scores=p_vals)
	if save_plots:
		kw_file_prefix = file_prefix + '_kw'
		kw_res.plot_manhattan(png_file=kw_file_prefix + '.png', highlight_loci=highlight_loci, neg_log_transform=True,
					plot_bonferroni=True)
		agr.plot_simple_qqplots(kw_file_prefix, [kw_res], result_labels=['Kruskal-Wallis'])


	print 'Updating stats for KW'
	result_dict['KW'] = _update_stats_(kw_res, c_chr, c_pos, l_chr, l_pos,
					significance_threshold=bonferroni_threshold)
	if save_pvals:
		result_dict['KW']['ps'] = p_vals

	#Finding the interesting plots hack...
	if result_dict['KW']['dist_f_w_s_a'] >= 0:
		return

	print 'Running SW LM'
	if save_plots:
		lm_file_prefix = file_prefix + '_lm'
	else:
		lm_file_prefix = None
	ret_dict = lm.lm_step_wise(phen_vals, sd, num_steps=num_steps, file_prefix=lm_file_prefix,
					highlight_loci=highlight_loci, save_pvals=save_pvals)
	lm_step_info = ret_dict['step_info_list']
	lm_pvals = ret_dict['first_lm_res']['ps'].tolist()
	lm_opt_dict = ret_dict['opt_dict']
	lm_res = gr.Result(scores=lm_pvals, snps_data=sd)
	print 'Updating stats for LM'
	result_dict['LM'] = _update_stats_(lm_res, c_chr, c_pos, l_chr, l_pos,
					significance_threshold=bonferroni_threshold)
	if save_pvals:
		result_dict['LM']['ps'] = lm_pvals
	#Finding the interesting plots hack...
	if result_dict['LM']['dist_f_w_s_a'] >= 0:
		return
	print 'Updating stats for SW LM'
	_update_sw_stats_(result_dict['Stepw_LM'], lm_step_info, lm_opt_dict, c_chr, c_pos, l_chr, l_pos,
					significance_threshold=bonferroni_threshold)


	print 'Running SW EX'
	if save_plots:
		emmax_file_prefix = file_prefix + '_emmax'
	else:
		emmax_file_prefix = None
	ret_dict = lm.emmax_step_wise(phen_vals, K, sd, num_steps=num_steps, file_prefix=emmax_file_prefix,
					highlight_loci=highlight_loci, save_pvals=save_pvals)
	emmax_step_info = ret_dict['step_info_list']
	emmax_pvals = ret_dict['first_emmax_res']['ps'].tolist()
	emmax_opt_dict = ret_dict['opt_dict']
	emmax_res = gr.Result(scores=emmax_pvals, snps_data=sd)
	print 'Updating stats for EX'
	result_dict['EX'] = _update_stats_(emmax_res, c_chr, c_pos, l_chr, l_pos,
					significance_threshold=bonferroni_threshold)
	if save_pvals:
		result_dict['EX']['ps'] = emmax_pvals
	print 'Updating stats for SW EX'
	_update_sw_stats_(result_dict['Stepw_EX'], emmax_step_info, emmax_opt_dict, c_chr, c_pos, l_chr, l_pos,
					significance_threshold=bonferroni_threshold, type='EX')


	#Record trait pseudo-heritability:
	result_dict['p_her'] = emmax_step_info[0]['pseudo_heritability']

	if pickle_results == True:
		pickled_results_file = file_prefix + 'results.pickled'
		print 'Pickling result dict in file: %s' % pickled_results_file
		with open(pickled_results_file, 'wb') as f:
			cPickle.dump(result_dict, f, protocol=2)

	return result_dict




def _run_():
	p_dict, args = parse_parameters()
	print args
	file_prefix = env.env['results_dir'] + p_dict['run_id']

	if p_dict['sim_phen'] and p_dict['phen_file']: 	#Simulate phenotypes
		print 'Setting up phenotype simulations'
		sd = dp.load_snps_call_method(75, debug_filter=p_dict['debug_filter'])
		simulate_phenotypes(p_dict['phen_file'], sd, debug_filter=p_dict['debug_filter'])

	elif p_dict['parallel']:
		#set up parallel runs
		if p_dict['phen_index'] == None:
			phen_d = load_phenotypes(p_dict['phen_file'])
			phenotypes = phen_d[p_dict['latent_variable']][p_dict['heritability']][p_dict['phenotype_model']]['phenotypes']
			start_i = 0
			end_i = len(phenotypes)
		else:
			start_i = p_dict['phen_index'][0]
			end_i = p_dict['phen_index'][-1]
		num_per_run = p_dict['number_per_run']
		for i in range(start_i, end_i, num_per_run):
			run_parallel(p_dict['run_id'], i, i + num_per_run - 1, p_dict['latent_variable'],
					p_dict['heritability'], p_dict['phenotype_model'],
					p_dict['phen_file'], p_dict['summarize'], p_dict['call_method_id'], p_dict['num_steps'],
					cluster='gmi')

	elif p_dict['phen_index']: #Run things..
		sd = dp.load_snps_call_method(75, debug_filter=p_dict['debug_filter'])
		K = dp.load_kinship(p_dict['call_method_id'])
		phed = load_phenotypes(p_dict['phen_file'])
		results_list = []
		for pid in p_dict['phen_index']:
			result_dict = run_analysis(sd, K, file_prefix, p_dict['latent_variable'], p_dict['heritability'],
						p_dict['phenotype_model'], pid, phed,
						p_dict['call_method_id'], num_steps=p_dict['num_steps'],
						save_plots=p_dict['save_plots'], save_pvals=p_dict['save_pvals'])
			results_list.append(result_dict)
		#Save as pickled

	else:
		if p_dict['summarize']:
			file_prefix = '/srv/lab/data/mlt_results/' + p_dict['run_id']
			phed = load_phenotypes(p_dict['phen_file'])
			summary_dict = summarize_runs(file_prefix, p_dict['latent_variable'], p_dict['heritability'],
							p_dict['phenotype_model'], phed,
							index_list=p_dict['phen_index'])
			plot_file_prefix = '%s_%d_%s_%s' % (file_prefix, p_dict['heritability'], p_dict['latent_variable'],
								p_dict['phenotype_model'])
			plot_tprs_fdrs(plot_file_prefix, summary_dict)

		if p_dict['herit_plots'] != None:
			d = {}
			file_prefix = '/srv/lab/data/mlt_results/' + p_dict['run_id']
			pd = load_phenotypes(p_dict['phen_file'])
			for her in p_dict['herit_plots']:
				d[her] = summarize_runs(file_prefix, p_dict['latent_variable'], her,
							p_dict['phenotype_model'], pd, index_list=p_dict['phen_index'])
			plot_herit_hist(file_prefix, d, p_dict['latent_variable'], p_dict['phenotype_model'])


		if p_dict['var_plots']:
			d = {}
			file_prefix = '/srv/lab/data/mlt_results/' + p_dict['run_id']
			pd = load_phenotypes(p_dict['phen_file'])
			for mod in ['plus', 'or', 'xor']:
				d[mod] = summarize_runs(file_prefix, p_dict['latent_variable'], p_dict['heritability'], mod, pd, index_list=p_dict['phen_index'])
			plot_var(file_prefix, d, p_dict['latent_variable'], p_dict['heritability'], ['plus', 'or', 'xor'])



#def _run_vincent_scripts_():
#	type = sys.argv[1]
#	start = int(sys.argv[2])
#	end = int(sys.argv[3])
#	if type == 'add_emmax':
#		exec_str = 'sim2loci_add_fwdbwdemmax.sh'
#	elif type == 'add_lm':
#		exec_str = 'sim2loci_add_fwdbwdlm.sh'
#	elif type == 'or_emmax':
#		exec_str = 'sim2loci_or_fwdbwdemmax.sh'
#	elif type == 'or_lm':
#		exec_str = 'sim2loci_or_fwdbwdlm.sh'
#	elif type == 'xor_emmax':
#		exec_str = 'sim2loci_xor_fwdbwdemmax.sh'
#	elif type == 'xor_lm':
#		exec_str = 'sim2loci_xor_fwdbwdlm.sh'
#	for i in range(start, end + 1):
#		exec_st = 'qsub -q cmb -l walltime=6:00:00 -l mem=2950mb /home/cmbpanfs-01/bvilhjal/vincent/jobs/' + exec_str + ' -v VARIABLE=' + str(i)
#		print exec_st
#		os.system(exec_st)



def generate_example_figure_1():
	import gwaResults as gr
	herit = 15
	pid = 13
	i_model = 'or'
	phed = load_phenotypes(env.env['phen_dir'] + 'multi_locus_phen.pickled')
	pickled_file = '%smlt_%d_random_snp_%s_%dresults.pickled' % (env.env['tmp_dir'], herit, i_model, pid)
	if os.path.isfile(pickled_file):
		with open(pickled_file) as f:
			r = cPickle.load(f)

	result_file_prefix = '%smlt_%d_random_snp_%s_%d_' % (env.env['tmp_dir'], herit, i_model, pid)
	result_files = [result_file_prefix + fn for fn in ['lm_step0.pvals', 'emmax_step0.pvals', 'emmax_step1.pvals']]
	#Load pickle file...
	r = cPickle.load(open(result_file_prefix[:-1] + 'results.pickled'))
	results = [gr.Result(result_file=fn) for fn in result_files]
	#Setting up figure
	f = pylab.figure(figsize=(9, 7))
	ax1 = f.add_axes([0.08, 0.07 + (0.667 * 0.94), 0.9, (0.3 * 0.94) ])
	ax1.spines['top'].set_visible(False)
	ax1.xaxis.set_visible(False)
	ax2 = f.add_axes([0.08, 0.07 + (0.333 * 0.94), 0.9, (0.3 * 0.94) ])
	ax2.spines['top'].set_visible(False)
	ax2.xaxis.set_visible(False)
	ax2.set_ylabel(r'$-$log$($p-value$)$')
	ax3 = f.add_axes([0.08, 0.07 , 0.9, (0.3 * 0.94) ])
	ax3.spines['top'].set_visible(False)
	ax3.xaxis.set_ticks_position('bottom')
	ax3.xaxis.set_label_position('bottom')
	res = results[0]
	chrom_ends = res.get_chromosome_ends()
	offset = 0
	tick_positions = []
	tick_labels = []
	for c_end in chrom_ends[:-1]:
		offset += c_end
		tick_positions.append(offset)
		tick_labels.append('')
	ax3.set_xticks(tick_positions)
	ax3.set_xticklabels(tick_labels)

	scpm = phed['snp_chr_pos_maf_list'][pid]
	lcpm = phed['random_snp']['latent_chr_pos_maf_list'][pid]
	highlight_loci = [(lcpm[0], lcpm[1]), (scpm[1], scpm[2])]
	print highlight_loci
	#Fill up the figure..
	cm = {1:'#1199EE', 2:'#11BB00', 3:'#1199EE', 4:'#11BB00', 5:'#1199EE'}
	results[0].plot_manhattan2(ax=ax1, neg_log_transform=True, plot_bonferroni=True,
				chrom_colormap=cm, highlight_loci=highlight_loci, sign_color='#DD1122')
	x_min, x_max = ax1.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax1.get_ylim()
	y_range = y_max - y_min
	ax1.text(0.96 * x_range + x_min, 0.85 * y_range + y_min, 'a')

	results[1].plot_manhattan2(ax=ax2, neg_log_transform=True, plot_bonferroni=True,
				chrom_colormap=cm, highlight_loci=highlight_loci, sign_color='#DD1122')
	x_min, x_max = ax2.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax2.get_ylim()
	y_range = y_max - y_min
	ax2.text(0.96 * x_range + x_min, 0.85 * y_range + y_min, 'b')

	cofactors = r['Stepw_EX']['step_info_list'][1]['cofactors']
	print r['Stepw_EX']['step_info_list'][1]['cofactors']
	results[2].plot_manhattan2(ax=ax3, neg_log_transform=True, plot_bonferroni=True,
				chrom_colormap=cm, highlight_markers=cofactors, highlight_loci=highlight_loci,
				sign_color='#DD1122')
	x_min, x_max = ax3.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax3.get_ylim()
	y_range = y_max - y_min
	ax3.text(0.96 * x_range + x_min, 0.85 * y_range + y_min, 'c')

	f.text(0.193, 0.04, '1')
	f.text(0.38, 0.04, '2')
	f.text(0.542, 0.04, '3')
	f.text(0.705, 0.04, '4')
	f.text(0.875, 0.04, '5')
	f.text(0.43, 0.01, 'Chromosome number')

	#Save the figure?
	pylab.savefig(env.env['tmp_dir'] + 'test.png', dpi=500)
	#pylab.savefig(env.env['tmp_dir'] + 'test.pdf', format='pdf')




def generate_results_figure_2(file_name='/tmp/test.png', herit=10, window_size=25000):
	file_prefix = '/srv/lab/data/mlt_results/mlt'
	phed = load_phenotypes(env.env['phen_dir'] + 'multi_locus_phen.pickled')
	f = pylab.figure(figsize=(11, 7))

	summary_dict = summarize_runs(file_prefix, 'random_snp', herit, 'plus', phed, index_list=range(1000))
	ax = f.add_axes([0.06, 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.3, 1.03), w_legend=True, x_label='')

	summary_dict = summarize_runs(file_prefix, 'random_snp', herit, 'or', phed, index_list=range(1000))
	ax = f.add_axes([0.06 + (0.33 * 0.93), 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.3, 1.03), y_label='', x_label='')

	summary_dict = summarize_runs(file_prefix, 'random_snp', herit, 'xor', phed, index_list=range(1000))
	ax = f.add_axes([0.054 + (0.667 * 0.93), 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.3, 1.03), y_label='', x_label='')

	summary_dict = summarize_runs(file_prefix, 'north_south_split', herit, 'plus', phed, index_list=range(1000))
	ax = f.add_axes([0.06, 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.0, 1.03))

	summary_dict = summarize_runs(file_prefix, 'north_south_split', herit, 'or', phed, index_list=range(1000))
	ax = f.add_axes([0.06 + (0.33 * 0.93), 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.0, 1.03), y_label='')

	summary_dict = summarize_runs(file_prefix, 'north_south_split', herit, 'xor', phed, index_list=range(1000))
	ax = f.add_axes([0.054 + (0.667 * 0.93), 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	plot_single_tprs_fdrs(summary_dict, ax, window_size, y_lim=(0.0, 1.03), y_label='')

	f.text(0.168, 0.962, 'Additive')
	f.text(0.496, 0.962, "'or'")
	f.text(0.796, 0.962, "'xor'")


	f.text(0.072, 0.91, 'A')
	f.text(0.382, 0.91, "B")
	f.text(0.688, 0.91, "C")
	f.text(0.072, 0.46, 'D')
	f.text(0.382, 0.46, "E")
	f.text(0.688, 0.46, "F")

	f.text(0.97, 0.125, 'North-south latent variable', rotation=90)
	f.text(0.97, 0.627, 'Two random SNPs', rotation=90)
	f.savefig(file_name)




def generate_results_figure_3():
	file_prefix = '/home/GMI/bjarni.vilhjalmsson/Projects/vincent_plots/plots_sim100loci/'
	caus_in_file = file_prefix + 'ROC_CAUS_IN.csv'
	caus_dropped_file = file_prefix + 'ROC_CAUS_DROP.csv'

	hertis = [25, 50, 75]
	analysis_methods = ['MLMM-fwd', 'MLMM-bwd', 'FBLR-fwd', 'FBLR-bwd', 'SLR', 'EMMAX']
	window_sizes = [0, 5000, 10000, 25000, 50000, 100000]

	caus_in_dict = {25:{}, 50:{}, 75:{}}
	caus_drop_dict = {25:{}, 50:{}, 75:{}}
	for h in hertis:
		for ws in window_sizes:
			caus_in_dict[h][ws] = {}
			caus_drop_dict[h][ws] = {}
			for am in analysis_methods:
				caus_in_dict[h][ws][am] = {'fdr':[], 'power':[]}
				caus_drop_dict[h][ws][am] = {'fdr':[], 'power':[]}

	with open(caus_in_file) as f:
		print f.next()
		for line in f:
			l = line.split(',')
			h = int(float(l[0]) * 100)
			am = l[1][1:-1]
			ws = int(l[2]) * 1000
			thres = l[3][1:-1]
			if thres == 'ebic':
				if am in ['MLMM-fwd', 'MLMM-bwd', 'FBLR-fwd', 'FBLR-bwd']:
					fdr = float(l[4])
					power = float(l[5])
					caus_in_dict[h][ws][am]['EBIC'] = {'fdr':fdr, 'power':power}
       				continue
			fdr = float(l[4])
                        power = float(l[5])
			if thres == 'bonf':
				caus_in_dict[h][ws][am]['BONF'] = {'fdr':fdr, 'power':power}
			else:
				caus_in_dict[h][ws][am]['fdr'].append(fdr)
				caus_in_dict[h][ws][am]['power'].append(power)

	with open(caus_dropped_file) as f:
		print f.next()
		for line in f:
			l = line.split(',')
			h = int(float(l[0]) * 100)
			am = l[1][1:-1]
			ws = int(l[2]) * 1000
			thres = l[3][1:-1]
			if thres == 'ebic':
				if am in ['MLMM-fwd', 'MLMM-bwd', 'FBLR-fwd', 'FBLR-bwd']:
					fdr = float(l[4])
					power = float(l[5])
					caus_drop_dict[h][ws][am]['EBIC'] = {'fdr':fdr, 'power':power}
				continue
			fdr = float(l[4])
			power = float(l[5])
			if thres == 'bonf':
				caus_drop_dict[h][ws][am]['BONF'] = {'fdr':fdr, 'power':power}
			else:
				caus_drop_dict[h][ws][am]['fdr'].append(fdr)
				caus_drop_dict[h][ws][am]['power'].append(power)


	f = pylab.figure(figsize=(11, 7))

	ax = f.add_axes([0.06, 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs_2(caus_in_dict[25], ax, 25000, y_lim=(0.16, 1.03), w_legend=True, x_label='')

	ax = f.add_axes([0.06 + (0.33 * 0.93), 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs_2(caus_in_dict[50], ax, 25000, y_lim=(0.16, 1.03), y_label='', x_label='')

	ax = f.add_axes([0.054 + (0.667 * 0.93), 0.08 + (0.5 * 0.9), (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	ax.set_xticklabels(['']*len(ax.get_xticks()))
	plot_single_tprs_fdrs_2(caus_in_dict[75], ax, 25000, y_lim=(0.16, 1.03), y_label='', x_label='')

	ax = f.add_axes([0.06, 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	plot_single_tprs_fdrs_2(caus_drop_dict[25], ax, 25000, y_lim=(0.06, 1.03))

	ax = f.add_axes([0.06 + (0.33 * 0.93), 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	plot_single_tprs_fdrs_2(caus_drop_dict[50], ax, 25000, y_lim=(0.06, 1.03), y_label='')

	ax = f.add_axes([0.054 + (0.667 * 0.93), 0.08, (0.3 * 0.93), (0.46 * 0.9) ])
	ax.set_yticklabels(['']*len(ax.get_yticks()))
	plot_single_tprs_fdrs_2(caus_drop_dict[75], ax, 25000, y_lim=(0.06, 1.03), y_label='')

	f.text(0.168, 0.962, r'$h^2 = 0.25 $')
	f.text(0.485, 0.962, r'$h^2 = 0.5 $')
	f.text(0.785, 0.962, r'$h^2 = 0.75 $')


	f.text(0.072, 0.91, 'A')
	f.text(0.382, 0.91, "B")
	f.text(0.688, 0.91, "C")
	f.text(0.072, 0.46, 'D')
	f.text(0.382, 0.46, "E")
	f.text(0.688, 0.46, "F")

	f.text(0.97, 0.105, 'Causatives dropped from data', rotation=90)
	f.text(0.97, 0.627, 'Causatives in data', rotation=90)
	f.savefig('/tmp/test.png')



def generate_example_figure_7():
	import gwaResults as gr

	result_file_prefix = env.env['results_dir'] + 'bf_most_norm_'
	cg_tair_ids = ['AT1G04400', 'AT1G65480', 'AT1G77080', 'AT2G26330', 'AT4G00650', 'AT5G10140', 'AT5G65050', \
			'AT5G65060', 'AT5G65070', 'AT5G65080'] \
			#FT, MAF, ER, FRI, FLC, MAF2-MAF5 (Salome et al. 2011)
	cgs = gr.get_genes_w_tair_id(cg_tair_ids)
	result_files = [result_file_prefix + fn for fn in ['DTF1stSpAverage2009_314_step1.ppas', \
							'DTF2ndSpAverage2009_315_opt_min_cof_ppa_step13.ppas', \
							'DTF1stSwAverage2009_316_step3.ppas', \
							'DTF2ndSwAverage2009_317_step4.ppas']]
	#Load pickle file...
	results = [gr.Result(result_file=fn) for fn in result_files]
	#Setting up figure
	f = pylab.figure(figsize=(9, 8))
	ax1 = f.add_axes([0.08, 0.07 + (0.75 * 0.94), 0.9, (0.225 * 0.94) ])
	ax1.spines['top'].set_visible(False)
	ax1.xaxis.set_visible(False)
	ax2 = f.add_axes([0.08, 0.07 + (0.5 * 0.94), 0.9, (0.225 * 0.94) ])
	ax2.spines['top'].set_visible(False)
	ax2.xaxis.set_visible(False)
	ax3 = f.add_axes([0.08, 0.07 + (0.25 * 0.94), 0.9, (0.225 * 0.94) ])
	ax3.spines['top'].set_visible(False)
	ax3.xaxis.set_visible(False)
	ax4 = f.add_axes([0.08, 0.07 , 0.9, (0.225 * 0.94) ])
	ax4.spines['top'].set_visible(False)
	ax4.xaxis.set_ticks_position('bottom')
	ax4.xaxis.set_label_position('bottom')
	res = results[0]
	chrom_ends = res.get_chromosome_ends()
	offset = 0
	tick_positions = []
	tick_labels = []
	for c_end in chrom_ends[:-1]:
		offset += c_end
		tick_positions.append(offset)
		tick_labels.append('')
	ax4.set_xticks(tick_positions)
	ax4.set_xticklabels(tick_labels)
	y_tick_positions = [0, 0.5, 1.0]
	y_tick_labels = ['0.0', '0.5', '1.0']

	max_y = offset + chrom_ends[-1]

	for ax in [ax1, ax2, ax3, ax4]:
		ax.set_ylim((-0.05, 1.05))
		ax.set_xlim((-0.02 * max_y, 1.02 * max_y))
		ax.set_yticks(y_tick_positions)
		ax.set_yticklabels(y_tick_labels)


	#Fill up the figure..
	cm = {1:'#1199EE', 2:'#11BB00', 3:'#1199EE', 4:'#11BB00', 5:'#1199EE'}
	results[0].plot_manhattan2(ax=ax1, neg_log_transform=False, plot_bonferroni=False,
				chrom_colormap=cm, highlight_markers=[(5, 3188327, 0.99957464909496818)],
				cand_genes=cgs)
	x_min, x_max = ax1.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax1.get_ylim()
	y_range = y_max - y_min
	ax1.text(0.95 * x_range + x_min, 0.85 * y_range + y_min, 'A')

	results[1].plot_manhattan2(ax=ax2, neg_log_transform=False, plot_bonferroni=False,
				chrom_colormap=cm, highlight_markers=[(5, 3188327, 0.99987154081342355), (4, 161496, 0.99792660595760496), (1, 24341345, 0.99816162117265428), (2, 8509438, 0.99185074339847878), (4, 633609, 0.87069974648101967), (4, 7232003, 0.70642884690410201), (1, 1630085, 0.62628047124132957)],
				cand_genes=cgs)
	x_min, x_max = ax2.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax2.get_ylim()
	y_range = y_max - y_min
	ax2.text(0.95 * x_range + x_min, 0.85 * y_range + y_min, 'B')

	results[2].plot_manhattan2(ax=ax3, neg_log_transform=False, plot_bonferroni=False,
				chrom_colormap=cm, highlight_markers=[(4, 1356197, 0.86299217462489453), (4, 493905, 0.95488774939952203), (5, 3188327, 0.5687697089878565)],
				cand_genes=cgs)
	x_min, x_max = ax3.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax3.get_ylim()
	y_range = y_max - y_min
	ax3.text(0.95 * x_range + x_min, 0.85 * y_range + y_min, 'C')

	results[3].plot_manhattan2(ax=ax4, neg_log_transform=False, plot_bonferroni=False,
				chrom_colormap=cm, highlight_markers=[(5, 3188327, 0.99975387199431631), (4, 493905, 0.98796470842089601), (5, 7476090, 0.78288774499946212), (1, 24341345, 0.62528073836407139)],
				cand_genes=cgs)
	x_min, x_max = ax4.get_xlim()
	x_range = x_max - x_min
	y_min, y_max = ax4.get_ylim()
	y_range = y_max - y_min
	ax4.text(0.95 * x_range + x_min, 0.85 * y_range + y_min, 'D')

	f.text(0.195, 0.04, '1')
	f.text(0.25, 0.04, 'FT')
	f.text(0.381, 0.04, '2')
	f.text(0.542, 0.04, '3')
	f.text(0.65, 0.04, 'FRI')
	f.text(0.704, 0.04, '4')
	f.text(0.82, 0.04, 'FLC')
	f.text(0.873, 0.04, '5')
	f.text(0.43, 0.01, 'Chromosome number')

	#Save the figure?
	pylab.savefig(env.env['tmp_dir'] + 'test.png')



def perform_human_emmax(pid=4):
	import dataParsers as dp
	import phenotypeData as pd
	import env
	import gwaResults as gr
	import random
	import sys
	s1 = time.time()
	plink_prefix = env.env['phen_dir'] + 'NFBC_20091001/NFBC_20091001'
	sd = dp.parse_plink_tped_file(plink_prefix)
	#sd.sample_snps(0.05)
	individs = sd.accessions[:]
	phed = pd.parse_phenotype_file(env.env['phen_dir'] + 'NFBC_20091001/phenotype.csv')
	#phed.filter_ecotypes(pid, random_fraction=0.2)
	sd.coordinate_w_phenotype_data(phed, pid)
	sd.filter_mac_snps(50)
	#K = sd.get_ibd_kinship_matrix(num_dots=10)
	K = lm.load_kinship_from_file('/home/GMI/bjarni.vilhjalmsson/Projects/data/NFBC_20091001/NFBC_20091001_kinship_diploid.ibs.pickled', sd.accessions)
	#K = prepare_k(K, individs, sd.accessions)
	phen_vals = phed.get_values(pid)
	phen_name = phed.get_name(pid)
	print 'Working on %s' % phen_name
	sys.stdout.flush()
	file_prefix = env.env['results_dir'] + 'NFBC_emmax_step_ibs_%s_pid%d' % (phen_name, pid)
	secs = time.time() - s1
	if secs > 60:
		mins = int(secs) / 60
		secs = secs - mins * 60
		print 'Took %d mins and %f seconds to load and preprocess the data.' % (mins, secs)
	else:
		print 'Took %f seconds to load and preprocess the data..' % (secs)
	chrom_col_map = {}
	for i in range(1, 24):
		if i % 2 == 0:
			chrom_col_map[i] = '#1199EE'
		else:
			chrom_col_map[i] = '#11BB00'
	emmax_res = lm.emmax_step_wise(phen_vals, K, sd=sd, num_steps=10, file_prefix=file_prefix, markersize=5,
				chrom_col_map=chrom_col_map, save_pvals=True)
	#snps = sd.getSnps()
	#emmax_res = emmax(snps, phen_vals, K)
	#res = gr.Result(scores=emmax_res['ps'].tolist(), snps_data=sd)
	#res.write_to_file(env.env['results_dir'] + 'NFBC_emmax_pid%d.pvals' % pid)
	#res.neg_log_trans()
	#res.plot_manhattan(png_file=file_prefix + '.png', plot_xaxis=False, plot_bonferroni=True)
	secs = time.time() - s1
	if secs > 60:
		mins = int(secs) / 60
		secs = secs - mins * 60
		print 'Took %d mins and %f seconds in total.' % (mins, secs)
	else:
		print 'Took %f seconds in total.' % (secs)



def perform_a_thal_emmax(pid=226):
	import dataParsers as dp
	import phenotypeData as pd
	import env
	import gwaResults as gr
	import random
	import sys
	s1 = time.time()
	sd = dp.load_snps_call_method(76)
	#sd.sample_snps(0.05)
	individs = sd.accessions[:]
	phed = pd.get_phenotypes_from_db([pid])
	phed.log_transform(pid)
	#phed.filter_ecotypes(pid, random_fraction=0.2)
	sd.coordinate_w_phenotype_data(phed, pid)
	sd.filter_mac_snps(15)
	K = sd.get_ibs_kinship_matrix(num_dots=10)
	#K = prepare_k(K, individs, sd.accessions)
	phen_vals = phed.get_values(pid)
	phen_name = phed.get_name(pid)
	print 'Working on %s' % phen_name
	sys.stdout.flush()
	file_prefix = env.env['results_dir'] + 'MLMM_t76_ibs_%s_pid%d' % (phen_name, pid)
	secs = time.time() - s1
	if secs > 60:
		mins = int(secs) / 60
		secs = secs - mins * 60
		print 'Took %d mins and %f seconds to load and preprocess the data.' % (mins, secs)
	else:
		print 'Took %f seconds to load and preprocess the data..' % (secs)
	chrom_col_map = {}
	for i in range(1, 6):
		if i % 2 == 0:
			chrom_col_map[i] = '#1199EE'
		else:
			chrom_col_map[i] = '#11BB00'
#	emmax_res = lm.emmax_step_wise(phen_vals, K, sd=sd, num_steps=10, file_prefix=file_prefix, markersize=5,
#				chrom_col_map=chrom_col_map)
	#snps = sd.getSnps()
	#emmax_res = emmax(snps, phen_vals, K)
	#res = gr.Result(scores=emmax_res['ps'].tolist(), snps_data=sd)
	#res.write_to_file(env.env['results_dir'] + 'NFBC_emmax_pid%d.pvals' % pid)
	#res.neg_log_trans()
	#res.plot_manhattan(png_file=file_prefix + '.png', plot_xaxis=False, plot_bonferroni=True)
	secs = time.time() - s1
	if secs > 60:
		mins = int(secs) / 60
		secs = secs - mins * 60
		print 'Took %d mins and %f seconds in total.' % (mins, secs)
	else:
		print 'Took %f seconds in total.' % (secs)

	cgs = gr.get_genes_w_tair_id(['AT4G10310'])
	s1 = time.time()
	sd = snpsdata.SNPsDataSet([sd.get_region_snpsd(4, 6360000, 6460000)],
				[4], data_format=sd.data_format)
	emmax_res = lm.emmax_step_wise(phen_vals, K, sd=sd, num_steps=0, file_prefix=file_prefix, markersize=5,
				chrom_col_map=chrom_col_map, local=True, cand_gene_list=cgs)
	#snps = sd.getSnps()
	#emmax_res = emmax(snps, phen_vals, K)
	#res = gr.Result(scores=emmax_res['ps'].tolist(), snps_data=sd)
	#res.write_to_file(env.env['results_dir'] + 'NFBC_emmax_pid%d.pvals' % pid)
	#res.neg_log_trans()
	#res.plot_manhattan(png_file=file_prefix + '.png', plot_xaxis=False, plot_bonferroni=True)
	secs = time.time() - s1
	if secs > 60:
		mins = int(secs) / 60
		secs = secs - mins * 60
		print 'Took %d mins and %f seconds in total.' % (mins, secs)
	else:
		print 'Took %f seconds in total.' % (secs)





if __name__ == '__main__':
#	for herit in [5, 10, 20, 25]:
#		for ws in [0, 1000, 5000, 10000, 25000]:
#			file_name = '/tmp/fig2_h%d_ws%d.png' % (herit, ws)
#			generate_results_figure_2(file_name=file_name, herit=herit, window_size=ws)
	#generate_example_figure_7()
	#_run_()
	generate_results_figure_2()
	#perform_human_emmax(4)
	#perform_human_emmax(2)
	#generate_example_figure_1()
#	sd = dp.load_250K_snps()
#	simulate_phenotypes(env.env['tmp_dir'] + 'simulated_phenotypes.pickled', sd)
	#perform_human_emmax(4)
	print "Done!!\n"
