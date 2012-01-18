#!/usr/bin/env python
"""
2011-11-22
	a common class for pegasus workflows that work on NGS (next-gen sequencing) data
"""
import sys, os, math

sys.path.insert(0, os.path.expanduser('~/lib/python'))
sys.path.insert(0, os.path.join(os.path.expanduser('~/script')))

import subprocess, cStringIO
import VervetDB
from pymodule import ProcessOptions, getListOutOfStr, PassingData, yh_pegasus, NextGenSeq
from Pegasus.DAX3 import *


class AbstractNGSWorkflow(object):
	__doc__ = __doc__
	option_default_dict = {('drivername', 1,):['postgresql', 'v', 1, 'which type of database? mysql or postgresql', ],\
						('hostname', 1, ): ['localhost', 'z', 1, 'hostname of the db server', ],\
						('dbname', 1, ): ['vervetdb', 'd', 1, 'database name', ],\
						('schema', 0, ): ['public', 'k', 1, 'database schema name', ],\
						('db_user', 1, ): [None, 'u', 1, 'database username', ],\
						('db_passwd', 1, ): [None, 'p', 1, 'database password', ],\
						('ref_ind_seq_id', 1, int): [524, 'a', 1, 'IndividualSequence.id. To pick alignments with this sequence as reference', ],\
						("samtools_path", 1, ): ["%s/bin/samtools", '', 1, 'samtools binary'],\
						("picard_path", 1, ): ["%s/script/picard/dist", '', 1, 'picard folder containing its jar binaries'],\
						("gatk_path", 1, ): ["%s/script/gatk/dist", '', 1, 'GATK folder containing its jar binaries'],\
						("vervetSrcPath", 1, ): ["%s/script/vervet/src", '', 1, 'vervet source code folder'],\
						("home_path", 1, ): [os.path.expanduser("~"), 'e', 1, 'path to the home directory on the working nodes'],\
						('tabixPath', 1, ): ["%s/bin/tabix", '', 1, 'path to the tabix binary', ],\
						("javaPath", 1, ): ["/usr/bin/java", 'J', 1, 'java interpreter binary'],\
						("dataDir", 0, ): ["", 't', 1, 'the base directory where all db-affiliated files are stored. \
									If not given, use the default stored in db.'],\
						("localDataDir", 0, ): ["", 'D', 1, 'localDataDir should contain same files as dataDir but accessible locally.\
									If not given, use the default stored in db. This argument is used to find all input files available.'],\
						
						("site_handler", 1, ): ["condorpool", 'l', 1, 'which site to run the jobs: condorpool, hoffman2'],\
						("input_site_handler", 1, ): ["local", 'j', 1, 'which site has all the input files: local, condorpool, hoffman2. \
							If site_handler is condorpool, this must be condorpool and files will be symlinked. \
							If site_handler is hoffman2, input_site_handler=local induces file transfer and input_site_handler=hoffman2 induces symlink.'],\
						('clusters_size', 1, int):[30, 'C', 1, 'For short jobs that will be clustered, how many of them should be clustered int one'],\
						('outputFname', 1, ): [None, 'o', 1, 'xml workflow output file'],\
						('checkEmptyVCFByReading', 0, int):[0, 'E', 0, 'toggle to check if a vcf file is empty by reading its content'],\
						('debug', 0, int):[0, 'b', 0, 'toggle debug mode'],\
						('report', 0, int):[0, 'r', 0, 'toggle report, more verbose stdout/stderr.']}
						#('bamListFname', 1, ): ['/tmp/bamFileList.txt', 'L', 1, 'The file contains path to each bam file, one file per line.'],\

	def __init__(self,  **keywords):
		"""
		2011-7-11
		"""
		from pymodule import ProcessOptions
		self.ad = ProcessOptions.process_function_arguments(keywords, self.option_default_dict, error_doc=self.__doc__, \
														class_to_have_attr=self)
		self.samtools_path = self.insertHomePath(self.samtools_path, self.home_path)
		self.picard_path =  self.insertHomePath(self.picard_path, self.home_path)
		self.gatk_path =  self.insertHomePath(self.gatk_path, self.home_path)
		self.vervetSrcPath =  self.insertHomePath(self.vervetSrcPath, self.home_path)
		self.tabixPath =  self.insertHomePath(self.tabixPath, self.home_path)
		
		import re
		self.chr_pattern = re.compile(r'(\w+\d+).*')
		self.contig_id_pattern = re.compile(r'Contig(\d+).*')
	
	def insertHomePath(self, inputPath, home_path):
		"""
		2012.1.9
		"""
		if inputPath.find('%s')!=-1:
			inputPath = inputPath%home_path
		return inputPath
	
	def registerJars(self, workflow, ):
		"""
		2011-11-22
			register jars to be used in the worflow
		"""
		site_handler = self.site_handler
		#add the MergeSamFiles.jar file into workflow
		abs_path = os.path.join(self.picard_path, 'MergeSamFiles.jar')
		mergeSamFilesJar = File(abs_path)	#using abs_path avoids add this jar to every job as Link.INPUT
		mergeSamFilesJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(mergeSamFilesJar)
		workflow.mergeSamFilesJar = mergeSamFilesJar
		
		abs_path = os.path.join(self.picard_path, 'BuildBamIndex.jar')
		BuildBamIndexFilesJar = File(abs_path)
		BuildBamIndexFilesJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(BuildBamIndexFilesJar)
		workflow.BuildBamIndexFilesJar = BuildBamIndexFilesJar
		
		abs_path = os.path.join(self.gatk_path, 'GenomeAnalysisTK.jar')
		genomeAnalysisTKJar = File(abs_path)
		genomeAnalysisTKJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(genomeAnalysisTKJar)
		workflow.genomeAnalysisTKJar = genomeAnalysisTKJar
		
		abs_path = os.path.join(self.picard_path, 'CreateSequenceDictionary.jar')
		createSequenceDictionaryJar = File(abs_path)
		createSequenceDictionaryJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(createSequenceDictionaryJar)
		workflow.createSequenceDictionaryJar = createSequenceDictionaryJar
		
		abs_path = os.path.join(self.picard_path, 'AddOrReplaceReadGroupsAndCleanSQHeader.jar')
		addOrReplaceReadGroupsAndCleanSQHeaderJar = File(abs_path)
		addOrReplaceReadGroupsAndCleanSQHeaderJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(addOrReplaceReadGroupsAndCleanSQHeaderJar)
		workflow.addOrReplaceReadGroupsAndCleanSQHeaderJar = addOrReplaceReadGroupsAndCleanSQHeaderJar
		
		abs_path = os.path.join(self.picard_path, 'AddOrReplaceReadGroups.jar')
		addOrReplaceReadGroupsJar = File(abs_path)
		addOrReplaceReadGroupsJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(addOrReplaceReadGroupsJar)
		workflow.addOrReplaceReadGroupsJar=addOrReplaceReadGroupsJar
		
		abs_path = os.path.join(self.picard_path, 'MarkDuplicates.jar')
		MarkDuplicatesJar = File(abs_path)
		MarkDuplicatesJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(MarkDuplicatesJar)
		workflow.MarkDuplicatesJar = MarkDuplicatesJar
		
		abs_path = os.path.join(self.picard_path, 'SplitReadFile.jar')
		SplitReadFileJar = File(abs_path)
		SplitReadFileJar.addPFN(PFN("file://" + abs_path, site_handler))
		workflow.addFile(SplitReadFileJar)
		workflow.SplitReadFileJar = SplitReadFileJar
	
	def registerCustomJars(self, workflow, ):
		"""
		2012.1.9
		"""
		pass
	
	def registerExecutables(self, workflow):
		"""
		2012.1.9 a symlink to registerCommonExecutables()
		"""
		self.registerCommonExecutables(workflow)
	
	def registerCommonExecutables(self, workflow):
		"""
		2011-11-22
		"""
		namespace = workflow.namespace
		version = workflow.version
		operatingSystem = workflow.operatingSystem
		architecture = workflow.architecture
		clusters_size = workflow.clusters_size
		site_handler = workflow.site_handler
		vervetSrcPath = self.vervetSrcPath
		
		#mkdirWrap is better than mkdir that it doesn't report error when the directory is already there.
		mkdirWrap = Executable(namespace=namespace, name="mkdirWrap", version=version, os=operatingSystem, \
							arch=architecture, installed=True)
		mkdirWrap.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/mkdirWrap.sh"), site_handler))
		mkdirWrap.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%workflow.clusters_size))
		workflow.addExecutable(mkdirWrap)
		workflow.mkdirWrap = mkdirWrap
		
		#mv to rename files and move them
		mv = Executable(namespace=namespace, name="mv", version=version, os=operatingSystem, arch=architecture, installed=True)
		mv.addPFN(PFN("file://" + "/bin/mv", site_handler))
		mv.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(mv)
		workflow.mv = mv
		
		selectAndSplit = Executable(namespace=namespace, name="SelectAndSplitAlignment", version=version, \
								os=operatingSystem, arch=architecture, installed=True)
		selectAndSplit.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "SelectAndSplitAlignment.py"), site_handler))
		workflow.addExecutable(selectAndSplit)
		workflow.selectAndSplit = selectAndSplit
		
		selectAndSplitFasta = Executable(namespace=namespace, name="SelectAndSplitFastaRecords", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		selectAndSplitFasta.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "SelectAndSplitFastaRecords.py"), site_handler))
		workflow.addExecutable(selectAndSplitFasta)
		workflow.selectAndSplitFasta = selectAndSplitFasta
		
		samtools = Executable(namespace=namespace, name="samtools", version=version, os=operatingSystem, arch=architecture, installed=True)
		samtools.addPFN(PFN("file://" + self.samtools_path, site_handler))
		workflow.addExecutable(samtools)
		workflow.samtools = samtools
		
		java = Executable(namespace=namespace, name="java", version=version, os=operatingSystem, arch=architecture, installed=True)
		java.addPFN(PFN("file://" + self.javaPath, site_handler))
		workflow.addExecutable(java)
		workflow.java = java
		
		addOrReplaceReadGroupsJava = Executable(namespace=namespace, name="addOrReplaceReadGroupsJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		addOrReplaceReadGroupsJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		workflow.addExecutable(addOrReplaceReadGroupsJava)
		workflow.addOrReplaceReadGroupsJava = addOrReplaceReadGroupsJava
		
		genotyperJava = Executable(namespace=namespace, name="genotyperJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		genotyperJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		#clustering is controlled by a separate parameter
		#genotyperJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(genotyperJava)
		workflow.genotyperJava = genotyperJava
		
		BuildBamIndexFilesJava = Executable(namespace=namespace, name="BuildBamIndexFilesJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		BuildBamIndexFilesJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		workflow.addExecutable(BuildBamIndexFilesJava)
		workflow.BuildBamIndexFilesJava = BuildBamIndexFilesJava
		
		createSequenceDictionaryJava = Executable(namespace=namespace, name="createSequenceDictionaryJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		createSequenceDictionaryJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		workflow.addExecutable(createSequenceDictionaryJava)
		workflow.createSequenceDictionaryJava = createSequenceDictionaryJava
		
		DOCWalkerJava = Executable(namespace=namespace, name="DepthOfCoverageWalker", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		#no clusters_size for this because it could run on a whole bam for hours
		#DOCWalkerJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		DOCWalkerJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		workflow.addExecutable(DOCWalkerJava)
		workflow.DOCWalkerJava = DOCWalkerJava
		
		VariousReadCountJava = Executable(namespace=namespace, name="VariousReadCountJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		VariousReadCountJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		#no clusters_size for this because it could run on a whole bam for hours
		#VariousReadCountJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(VariousReadCountJava)
		workflow.VariousReadCountJava = VariousReadCountJava
		
		
		MarkDuplicatesJava = Executable(namespace=namespace, name="MarkDuplicatesJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		MarkDuplicatesJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		#MarkDuplicatesJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(MarkDuplicatesJava)
		workflow.MarkDuplicatesJava = MarkDuplicatesJava
		
		SelectVariantsJava = Executable(namespace=namespace, name="SelectVariantsJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		SelectVariantsJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		SelectVariantsJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(SelectVariantsJava)
		workflow.SelectVariantsJava = SelectVariantsJava
		
		CombineVariantsJava = Executable(namespace=namespace, name="CombineVariantsJava", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		CombineVariantsJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		CombineVariantsJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(CombineVariantsJava)
		workflow.CombineVariantsJava = CombineVariantsJava
		
		CallVariantBySamtools = Executable(namespace=namespace, name="CallVariantBySamtools", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		CallVariantBySamtools.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/CallVariantBySamtools.sh"), site_handler))
		#clustering is controlled by a separate parameter
		#CallVariantBySamtools.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(CallVariantBySamtools)
		workflow.CallVariantBySamtools = CallVariantBySamtools
		
		genotypeCallByCoverage = Executable(namespace=namespace, name="GenotypeCallByCoverage", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		genotypeCallByCoverage.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "GenotypeCallByCoverage.py"), site_handler))
		genotypeCallByCoverage.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(genotypeCallByCoverage)
		workflow.genotypeCallByCoverage = genotypeCallByCoverage
		
		mergeGenotypeMatrix = Executable(namespace=namespace, name="MergeGenotypeMatrix", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		mergeGenotypeMatrix.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "MergeGenotypeMatrix.py"), site_handler))
		mergeGenotypeMatrix.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(mergeGenotypeMatrix)
		workflow.mergeGenotypeMatrix = mergeGenotypeMatrix
		
		bgzip_tabix = Executable(namespace=namespace, name="bgzip_tabix", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		bgzip_tabix.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/bgzip_tabix.sh"), site_handler))
		bgzip_tabix.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(bgzip_tabix)
		workflow.bgzip_tabix = bgzip_tabix
		
		vcf_convert = Executable(namespace=namespace, name="vcf_convert", version=version, \
								os=operatingSystem, arch=architecture, installed=True)
		vcf_convert.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcf_convert.sh"), site_handler))
		vcf_convert.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(vcf_convert)
		workflow.vcf_convert = vcf_convert
		
		vcf_isec = Executable(namespace=namespace, name="vcf_isec", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		vcf_isec.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcf_isec.sh"), site_handler))
		vcf_isec.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(vcf_isec)
		workflow.vcf_isec = vcf_isec
		
		vcf_concat = Executable(namespace=namespace, name="vcf_concat", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		vcf_concat.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcf_concat.sh"), site_handler))
		#vcf_concat might involve a very long argument, which would be converted to *.arg and then pegasus bug
		vcf_concat.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(vcf_concat)
		workflow.vcf_concat = vcf_concat
		
		concatGATK = Executable(namespace=namespace, name="concatGATK", version=version, \
							os=operatingSystem, arch=architecture, installed=True)
		concatGATK.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcf_concat.sh"), site_handler))
		concatGATK.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(concatGATK)
		workflow.concatGATK = concatGATK
		
		concatSamtools = Executable(namespace=namespace, name="concatSamtools", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		concatSamtools.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcf_concat.sh"), site_handler))
		concatSamtools.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(concatSamtools)
		workflow.concatSamtools = concatSamtools
		
		calcula = Executable(namespace=namespace, name="CalculatePairwiseDistanceOutOfSNPXStrainMatrix", \
							version=version, os=operatingSystem, arch=architecture, installed=True)
		calcula.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "CalculatePairwiseDistanceOutOfSNPXStrainMatrix.py"), site_handler))
		calcula.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(calcula)
		workflow.calcula = calcula
		
		#2011-11-28
		mergeSameHeaderTablesIntoOne = Executable(namespace=namespace, name="MergeSameHeaderTablesIntoOne", \
							version=version, os=operatingSystem, arch=architecture, installed=True)
		mergeSameHeaderTablesIntoOne.addPFN(PFN("file://" + os.path.join(vervetSrcPath, "reducer/MergeSameHeaderTablesIntoOne.py"), site_handler))
		#long arguments will happen, so no clustering.
		#2012.12.8 bug fixed now.
		mergeSameHeaderTablesIntoOne.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(mergeSameHeaderTablesIntoOne)
		workflow.mergeSameHeaderTablesIntoOne = mergeSameHeaderTablesIntoOne
		
		ReduceMatrixByChosenColumn = Executable(namespace=namespace, name="ReduceMatrixByChosenColumn", \
							version=version, os=operatingSystem, arch=architecture, installed=True)
		ReduceMatrixByChosenColumn.addPFN(PFN("file://" + os.path.join(vervetSrcPath, "reducer/ReduceMatrixByChosenColumn.py"), site_handler))
		ReduceMatrixByChosenColumn.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(ReduceMatrixByChosenColumn)
		workflow.ReduceMatrixByChosenColumn = ReduceMatrixByChosenColumn
		
		ReduceMatrixBySumSameKeyColsAndThenDivide = Executable(namespace=namespace, name="ReduceMatrixBySumSameKeyColsAndThenDivide", \
							version=version, os=operatingSystem, arch=architecture, installed=True)
		ReduceMatrixBySumSameKeyColsAndThenDivide.addPFN(PFN("file://" + os.path.join(vervetSrcPath, "reducer/ReduceMatrixBySumSameKeyColsAndThenDivide.py"), \
															site_handler))
		ReduceMatrixBySumSameKeyColsAndThenDivide.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(ReduceMatrixBySumSameKeyColsAndThenDivide)
		workflow.ReduceMatrixBySumSameKeyColsAndThenDivide = ReduceMatrixBySumSameKeyColsAndThenDivide
		
		ReduceMatrixByAverageColumnsWithSameKey = Executable(namespace=namespace, name="ReduceMatrixByAverageColumnsWithSameKey", \
							version=version, os=operatingSystem, arch=architecture, installed=True)
		ReduceMatrixByAverageColumnsWithSameKey.addPFN(PFN("file://" + os.path.join(vervetSrcPath, "reducer/ReduceMatrixByAverageColumnsWithSameKey.py"), site_handler))
		ReduceMatrixByAverageColumnsWithSameKey.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(ReduceMatrixByAverageColumnsWithSameKey)
		workflow.ReduceMatrixByAverageColumnsWithSameKey = ReduceMatrixByAverageColumnsWithSameKey
		
		vcftoolsPath = os.path.join(self.home_path, "bin/vcftools/vcftools")
		workflow.vcftoolsPath = vcftoolsPath	#vcftoolsPath is first argument to vcftoolsWrapper
		vcftoolsWrapper = Executable(namespace=namespace, name="vcftoolsWrapper", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		vcftoolsWrapper.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/vcftoolsWrapper.sh"), site_handler))
		vcftoolsWrapper.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		vcftoolsWrapper.vcftoolsPath = vcftoolsPath
		workflow.addExecutable(vcftoolsWrapper)
		workflow.vcftoolsWrapper = vcftoolsWrapper
		
		tabix = Executable(namespace=namespace, name="tabix", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		tabix.addPFN(PFN("file://" + self.tabixPath, site_handler))
		tabix.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(tabix)
		workflow.tabix = tabix
		
		#2011.12.21 moved from FilterVCFPipeline.py
		FilterVCFByDepthJava = Executable(namespace=namespace, name="FilterVCFByDepth", version=version, os=operatingSystem,\
											arch=architecture, installed=True)
		FilterVCFByDepthJava.addPFN(PFN("file://" + self.javaPath, site_handler))
		FilterVCFByDepthJava.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(FilterVCFByDepthJava)
		workflow.FilterVCFByDepthJava = FilterVCFByDepthJava
		
		#2011.12.21	for OutputVCFSiteStat.py
		tabixRetrieve = Executable(namespace=namespace, name="tabixRetrieve", version=version, \
										os=operatingSystem, arch=architecture, installed=True)
		tabixRetrieve.addPFN(PFN("file://" + os.path.join(self.vervetSrcPath, "shell/tabixRetrieve.sh"), site_handler))
		tabixRetrieve.addProfile(Profile(Namespace.PEGASUS, key="clusters.size", value="%s"%clusters_size))
		workflow.addExecutable(tabixRetrieve)
		workflow.tabixRetrieve = tabixRetrieve
		
	def initiateWorkflow(self, workflowName):
		"""
		2011-11-22
		"""
		# Create a abstract dag
		workflow = ADAG(workflowName)
		workflow.site_handler = self.site_handler
		workflow.input_site_handler = self.input_site_handler
		# Add executables to the DAX-level replica catalog
		# In this case the binary is keg, which is shipped with Pegasus, so we use
		# the remote PEGASUS_HOME to build the path.
		workflow.architecture = "x86_64"
		workflow.operatingSystem = "linux"
		workflow.namespace = "workflow"
		workflow.version="1.0"
		#clusters_size controls how many jobs will be aggregated as a single job.
		workflow.clusters_size = self.clusters_size
		return workflow
	
	@classmethod
	def addBAMIndexJob(cls, workflow, BuildBamIndexFilesJava=None, BuildBamIndexFilesJar=None, \
					inputBamF=None,\
					parentJob=None, parentJobLs=[], namespace='workflow', version='1.0',\
					stageOutFinalOutput=True, javaMaxMemory=2500,\
					**keywords):
		"""
		2011-11-20
		"""
		index_sam_job = Job(namespace=getattr(workflow, 'namespace', namespace), name=BuildBamIndexFilesJava.name, \
						version=getattr(workflow, 'version', version))
		baiFile = File('%s.bai'%inputBamF.name)
		index_sam_job.addArguments("-Xms128m", "-Xmx%sm"%(javaMaxMemory), "-jar", BuildBamIndexFilesJar, "VALIDATION_STRINGENCY=LENIENT", \
						"INPUT=", inputBamF, "OUTPUT=", baiFile)
		yh_pegasus.setJobProperRequirement(index_sam_job, job_max_memory=javaMaxMemory)
		index_sam_job.bamFile = inputBamF
		index_sam_job.baiFile = baiFile
		if stageOutFinalOutput:
			index_sam_job.uses(inputBamF, transfer=True, register=True, link=Link.INPUT)
			#index_sam_job.uses(inputBamF, transfer=True, register=True, link=Link.OUTPUT)
			index_sam_job.uses(baiFile, transfer=True, register=True, link=Link.OUTPUT)
		else:
			index_sam_job.uses(inputBamF, transfer=False, register=True, link=Link.INPUT)
			#index_sam_job.uses(inputBamF, transfer=False, register=True, link=Link.OUTPUT)
			index_sam_job.uses(baiFile, transfer=False, register=True, link=Link.OUTPUT)
			#pass	#don't register the files so leave them there
		workflow.addJob(index_sam_job)
		parentJobLs.append(parentJob)
		for parentJob in parentJobLs:
			if parentJob:
				workflow.depends(parent=parentJob, child=index_sam_job)
		return index_sam_job
	
	def registerCustomExecutables(self, workflow):
		"""
		2012.1.9
			abstract function
		"""
		pass
	
	def registerFilesAsInputToJob(self, job, inputFileList):
		"""
		2011-11-25
		"""
		for inputFile in inputFileList:
			job.uses(inputFile, transfer=True, register=True, link=Link.INPUT)
	
	def registerOneInputFile(self, workflow, inputFname,):
		"""
		2011.12.21
		"""
		file = File(os.path.basename(inputFname))
		file.addPFN(PFN("file://" + os.path.abspath(inputFname), workflow.input_site_handler))
		workflow.addFile(file)
		return file
	
	def addRefFastaFaiIndexJob(self, workflow, samtools=None, refFastaF=None, ):
		"""
		2011-11-25
			the *.fai file of refFastaF is required for GATK
		"""
		refFastaIndexFname = '%s.fai'%(refFastaF.name)	# the .fai file is required for GATK
		refFastaIndexF = File(refFastaIndexFname)
		#not os.path.isfile(refFastaIndexFname)
		fastaIndexJob = Job(namespace=workflow.namespace, name=samtools.name, version=workflow.version)
		fastaIndexJob.addArguments("faidx", refFastaF)
		fastaIndexJob.uses(refFastaF,  transfer=True, register=False, link=Link.INPUT)
		fastaIndexJob.uses(refFastaIndexFname, transfer=True, register=False, link=Link.OUTPUT)
		fastaIndexJob.refFastaIndexF = refFastaIndexF
		yh_pegasus.setJobProperRequirement(fastaIndexJob, job_max_memory=1000)
		workflow.addJob(fastaIndexJob)
		return fastaIndexJob
	
	def addRefFastaDictJob(self, workflow, createSequenceDictionaryJava=None, refFastaF=None):
		"""
		2011-11-25
			# the .dict file is required for GATK
		"""
		refFastaDictFname = '%s.dict'%(os.path.splitext(refFastaF.name)[0])
		refFastaDictF = File(refFastaDictFname)
		#not os.path.isfile(refFastaDictFname) or 
		fastaDictJob = Job(namespace=workflow.namespace, name=createSequenceDictionaryJava.name, version=workflow.version)
		fastaDictJob.addArguments('-jar', createSequenceDictionaryJar, \
				'REFERENCE=', refFastaF, 'OUTPUT=', refFastaDictF)
		fastaDictJob.uses(refFastaF,  transfer=True, register=False, link=Link.INPUT)
		fastaDictJob.uses(refFastaDictF, transfer=True, register=False, link=Link.OUTPUT)
		yh_pegasus.setJobProperRequirement(fastaDictJob, job_max_memory=1000)
		fastaDictJob.refFastaDictF = refFastaDictF
		workflow.addJob(fastaDictJob)
		return fastaDictJob
	
	def addStatMergeJob(self, workflow, statMergeProgram=None, outputF=None, \
					parentJobLs=[], \
					extraDependentInputLs=[], transferOutput=True, extraArguments=None, **keywords):
		"""
		2011-11-28
			moved from CalculateVCFStatPipeline.py
		2011-11-17
			add argument extraArguments
		"""
		statMergeJob = Job(namespace=workflow.namespace, name=statMergeProgram.name, version=workflow.version)
		statMergeJob.addArguments('-o', outputF)
		if extraArguments:
			statMergeJob.addArguments(extraArguments)
		statMergeJob.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		statMergeJob.output = outputF
		workflow.addJob(statMergeJob)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=statMergeJob)
		for input in extraDependentInputLs:
			statMergeJob.uses(input, transfer=True, register=True, link=Link.INPUT)
		return statMergeJob
	
	def addInputToStatMergeJob(self, workflow, statMergeJob=None, inputF=None, \
							parentJobLs=[], \
							namespace=None, version=None, extraDependentInputLs=[]):
		"""
		2011-11-28
			moved from CalculateVCFStatPipeline.py
		"""
		statMergeJob.addArguments(inputF)
		statMergeJob.uses(inputF, transfer=False, register=True, link=Link.INPUT)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=statMergeJob)
	
	def addRefFastaJobDependency(self, workflow, job, refFastaF=None, fastaDictJob=None, refFastaDictF=None, fastaIndexJob = None, refFastaIndexF = None):
		"""
		2011-9-14
		"""
		if fastaIndexJob:	#2011-7-22 if job doesn't exist, don't add it. means this job isn't necessary to run.
			workflow.depends(parent=fastaIndexJob, child=job)
			job.uses(refFastaIndexF, transfer=True, register=True, link=Link.INPUT)
		if fastaDictJob:
			workflow.depends(parent=fastaDictJob, child=job)
			job.uses(refFastaDictF, transfer=True, register=True, link=Link.INPUT)
		if fastaIndexJob or fastaDictJob:
			job.uses(refFastaF, transfer=True, register=True, link=Link.INPUT)
	
	def addVCFFormatConvertJob(self, workflow, vcf_convert=None, parentJob=None, inputF=None, outputF=None, \
							namespace=None, version=None, transferOutput=False):
		"""
		2011-11-4
		"""
		vcf_convert_job = Job(namespace=getattr(workflow, 'namespace', namespace), name=vcf_convert.name, \
							version=getattr(workflow, 'version', version))
		vcf_convert_job.addArguments(inputF, outputF)
		vcf_convert_job.uses(inputF, transfer=False, register=True, link=Link.INPUT)
		vcf_convert_job.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		workflow.addJob(vcf_convert_job)
		workflow.depends(parent=parentJob, child=vcf_convert_job)
		return vcf_convert_job
	
	def addBGZIP_tabix_Job(self, workflow, bgzip_tabix=None, parentJob=None, inputF=None, outputF=None, \
							namespace=None, version=None, transferOutput=False, parentJobLs=[], tabixArguments=""):
		"""
		2011.12.20
			pass additional tabix arguments to bgzip_tabix shell script
		2011-11-4
		
		"""
		bgzip_tabix_job = Job(namespace=getattr(workflow, 'namespace', namespace), name=bgzip_tabix.name, \
							version=getattr(workflow, 'version', version))
		tbi_F = File("%s.tbi"%outputF.name)
		bgzip_tabix_job.addArguments(inputF, outputF)
		if tabixArguments:
			bgzip_tabix_job.addArguments(tabixArguments)
		bgzip_tabix_job.uses(inputF, transfer=False, register=True, link=Link.INPUT)
		bgzip_tabix_job.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		bgzip_tabix_job.uses(tbi_F, transfer=transferOutput, register=True, link=Link.OUTPUT)
		bgzip_tabix_job.output = outputF
		bgzip_tabix_job.tbi_F = tbi_F
		workflow.addJob(bgzip_tabix_job)
		if parentJob:
			workflow.depends(parent=parentJob, child=bgzip_tabix_job)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=bgzip_tabix_job)
		return bgzip_tabix_job
	
	def addVCFConcatJob(self, workflow, concatExecutable=None, parentDirJob=None, outputF=None, \
							namespace=None, version=None, transferOutput=True, vcf_job_max_memory=None):
		"""
		2011-11-5
		"""
		#2011-9-22 union of all samtools intervals for one contig
		vcfConcatJob = Job(namespace=getattr(workflow, 'namespace', namespace), name=concatExecutable.name, \
						version=getattr(workflow, 'version', version))
		vcfConcatJob.addArguments(outputF)
		vcfConcatJob.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		tbi_F = File("%s.tbi"%outputF.name)
		vcfConcatJob.uses(tbi_F, transfer=transferOutput, register=True, link=Link.OUTPUT)
		yh_pegasus.setJobProperRequirement(vcfConcatJob, job_max_memory=vcf_job_max_memory)
		workflow.addJob(vcfConcatJob)
		workflow.depends(parent=parentDirJob, child=vcfConcatJob)
		return vcfConcatJob
	
	@classmethod
	def findProperVCFDirIdentifier(cls, vcfDir, defaultName='vcf1'):
		"""
		2011.11.28
		"""
		#name to distinguish between vcf1Dir, and vcf2Dir
		folderNameLs = vcfDir.split('/')
		vcf1Name=None
		for i in range(1, len(folderNameLs)+1):
			if folderNameLs[-i]:	#start from the end to find the non-empty folder name
				#the trailing "/" on self.vcf1Dir could mean  an empty string
				vcf1Name = folderNameLs[-i]
				break
		if not vcf1Name:
			vcf1Name = defaultName
		return vcf1Name
	
	def addSelectVariantsJob(self, workflow, SelectVariantsJava=None, genomeAnalysisTKJar=None, inputF=None, outputF=None, \
					refFastaFList=[], parentJobLs=[], \
					extraDependentInputLs=[], transferOutput=True, extraArguments=None, job_max_memory=2000, interval=None,\
					**keywords):
		"""
		2011-12.5
		"""
		javaMemRequirement = "-Xms128m -Xmx%sm"%job_max_memory
		refFastaF = refFastaFList[0]
		job = Job(namespace=workflow.namespace, name=SelectVariantsJava.name, version=workflow.version)
		job.addArguments(javaMemRequirement, '-jar', genomeAnalysisTKJar, "-T SelectVariants", "-R", refFastaF, \
						"--variant", inputF, "-o ", outputF, "-L %s"%(interval))
		if extraArguments:
			job.addArguments(extraArguments)
		for refFastaFile in refFastaFList:
			job.uses(refFastaFile, transfer=True, register=True, link=Link.INPUT)
		job.uses(inputF, transfer=True, register=True, link=Link.INPUT)
		job.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		job.output = outputF
		workflow.addJob(job)
		yh_pegasus.setJobProperRequirement(job, job_max_memory=job_max_memory)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=job)
		for input in extraDependentInputLs:
			job.uses(input, transfer=True, register=True, link=Link.INPUT)
		return job
	
	def getVCFFileID2path(self, inputDir):
		"""
		2011-12-1
		"""
		sys.stderr.write("Getting all vcf files from %s "%(inputDir))
		vcfFileID2path = {}
		for inputFname in os.listdir(inputDir):
			inputAbsPath = os.path.join(os.path.abspath(inputDir), inputFname)
			if NextGenSeq.isFileNameVCF(inputFname, includeIndelVCF=False) and not NextGenSeq.isVCFFileEmpty(inputAbsPath):
				fileID = self.chr_pattern.search(inputFname).group(1)
				if fileID in vcfFileID2path:
					sys.stderr.write("fileID %s already has value (%s) in dictionary. but now a 2nd file %s overwrites previous value.\n"%\
									(fileID, vcfFileID2path.get(fileID), inputFname))
				vcfFileID2path[fileID] = inputAbsPath
		sys.stderr.write("  found %s files.\n"%(len(vcfFileID2path)))
		return vcfFileID2path
	
	def addCheckTwoVCFOverlapJob(self, workflow, executable=None, vcf1=None, vcf2=None, chromosome=None, chrLength=None, \
					outputFnamePrefix=None, parentJobLs=[], \
					extraDependentInputLs=[], transferOutput=False, extraArguments=None, job_max_memory=1000, \
					**keywords):
		"""
		2011.12.9
		"""
		overlapSitePosF = File('%s_overlapSitePos.tsv'%(outputFnamePrefix))
		outputF = File('%s_overlap.tsv'%(outputFnamePrefix))
		job = Job(namespace=workflow.namespace, name=executable.name, version=workflow.version)
		job.addArguments("-i", vcf1, "-j", vcf2, "-c", chromosome, "-l %s"%(chrLength), '-o', outputF,\
						'-O', outputFnamePrefix)
		if extraArguments:
			job.addArguments(extraArguments)
		job.uses(vcf1, transfer=True, register=True, link=Link.INPUT)
		job.uses(vcf2, transfer=True, register=True, link=Link.INPUT)
		job.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		job.uses(overlapSitePosF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		job.overlapSitePosF = overlapSitePosF
		job.output = outputF
		workflow.addJob(job)
		yh_pegasus.setJobProperRequirement(job, job_max_memory=job_max_memory)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=job)
		for input in extraDependentInputLs:
			job.uses(input, transfer=True, register=True, link=Link.INPUT)
		return job
	
	def addFilterVCFByDepthJob(self, workflow, FilterVCFByDepthJava=None, genomeAnalysisTKJar=None, \
							refFastaFList=None, inputVCFF=None, outputVCFF=None, outputSiteStatF=None, \
							parentJobLs=[], alnStatForFilterF=None, \
							job_max_memory=1000, extraDependentInputLs=[], onlyKeepBiAllelicSNP=False, \
							namespace=None, version=None, transferOutput=False, **keywords):
		"""
		2011.12.20
			moved from FilterVCFPipeline.py
			add argument transferOutput, outputSiteStatF
		"""
		# Add a mkdir job for any directory.
		filterByDepthJob = Job(namespace=getattr(workflow, 'namespace', namespace), name=FilterVCFByDepthJava.name, \
							version=getattr(workflow, 'version', version))
		refFastaF = refFastaFList[0]
		filterByDepthJob.addArguments("-Xmx%sm"%(job_max_memory), "-jar", genomeAnalysisTKJar, "-R", refFastaF, "-T FilterVCFByDepth", \
							"--variant", inputVCFF, "-depthFname", alnStatForFilterF)
		if outputVCFF:
			filterByDepthJob.addArguments("-o", outputVCFF)
			filterByDepthJob.uses(outputVCFF, transfer=transferOutput, register=True, link=Link.OUTPUT)
			filterByDepthJob.output = outputVCFF
		
		if outputSiteStatF:
			filterByDepthJob.addArguments("-ssFname", outputSiteStatF)
			filterByDepthJob.uses(outputSiteStatF, transfer=transferOutput, register=True, link=Link.OUTPUT)
			filterByDepthJob.outputSiteStatF = outputSiteStatF
		
		if onlyKeepBiAllelicSNP:
			filterByDepthJob.addArguments("--onlyKeepBiAllelicSNP")
		
		for refFastaFile in refFastaFList:
			filterByDepthJob.uses(refFastaFile, transfer=True, register=True, link=Link.INPUT)
		filterByDepthJob.uses(alnStatForFilterF, transfer=True, register=True, link=Link.INPUT)
		filterByDepthJob.uses(inputVCFF, transfer=True, register=True, link=Link.INPUT)		
		for input in extraDependentInputLs:
			filterByDepthJob.uses(input, transfer=True, register=True, link=Link.INPUT)
		workflow.addJob(filterByDepthJob)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=filterByDepthJob)
		yh_pegasus.setJobProperRequirement(filterByDepthJob, job_max_memory=job_max_memory)
		return filterByDepthJob
	
	def addCalculateTwoVCFSNPMismatchRateJob(self, workflow, executable=None, \
							vcf1=None, vcf2=None, snpMisMatchStatFile=None, \
							maxSNPMismatchRate=1.0, parentJobLs=[], \
							job_max_memory=1000, extraDependentInputLs=[], \
							transferOutput=False, **keywords):
		"""
		2011.12.20
			
		"""
		job = Job(namespace=workflow.namespace, name=executable.name, \
												version=workflow.version)
		job.addArguments("-i", vcf1, "-j", vcf2, \
						"-m %s"%(maxSNPMismatchRate), '-o', snpMisMatchStatFile)
		job.uses(vcf1, transfer=True, register=True, link=Link.INPUT)
		job.uses(vcf2, transfer=True, register=True, link=Link.INPUT)
		job.uses(snpMisMatchStatFile, transfer=transferOutput, register=True, link=Link.OUTPUT)
		yh_pegasus.setJobProperRequirement(job, job_max_memory=job_max_memory)
		workflow.addJob(job)
		for input in extraDependentInputLs:
			job.uses(input, transfer=True, register=True, link=Link.INPUT)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=job)
		return job

	def addTabixRetrieveJob(self, workflow, executable=None, tabixPath=None, \
							inputF=None, outputF=None, regionOfInterest=None, includeHeader=True,\
							parentJobLs=[], job_max_memory=100, extraDependentInputLs=[], \
							transferOutput=False, **keywords):
		"""
		2011.12.20
			The executable should be tabixRetrieve (a tabix shell wrapper).
			
			http://samtools.sourceforge.net/tabix.shtml
			run something like below to extract data from regionOfInterest out of bgzipped&tabix-indexed file.
				tabix sorted.gff.gz chr1:10,000,000-20,000,000
		"""
		job = Job(namespace=workflow.namespace, name=executable.name, version=workflow.version)
		job.addArguments(tabixPath)
		job.addArguments(inputF, outputF, regionOfInterest)
		if includeHeader:
			job.addArguments("-h")
		job.uses(inputF, transfer=True, register=True, link=Link.INPUT)
		job.uses(outputF, transfer=transferOutput, register=True, link=Link.OUTPUT)
		
		job.output = outputF
		
		yh_pegasus.setJobProperRequirement(job, job_max_memory=job_max_memory)
		workflow.addJob(job)
		for input in extraDependentInputLs:
			job.uses(input, transfer=True, register=True, link=Link.INPUT)
		for parentJob in parentJobLs:
			workflow.depends(parent=parentJob, child=job)
		return job
	
	
	def getContigIDFromFname(self, filename):
		"""
		2011-10-20
			
			If filename is like .../Contig0.filter_by_vcftools.recode.vcf.gz,
				It returns "0", excluding the "Contig".
				If you want "Contig" included, use getChrIDFromFname().
			If search fails, it returns the prefix in the basename of filename.
		"""
		contig_id_pattern_sr = self.contig_id_pattern.search(filename)
		if contig_id_pattern_sr:
			contig_id = contig_id_pattern_sr.group(1)
		else:
			contig_id = os.path.splitext(os.path.split(filename)[1])[0]
		return contig_id
	
	def getChrFromFname(self, filename):
		"""
		2011-10-20
			filename example: Contig0.filter_by_vcftools.recode.vcf.gz
				It returns "Contig0".
				If you want just "0", use getContigIDFromFname().
			If search fails, it returns the prefix in the basename of filename.
		"""
		chr_pattern_sr = self.chr_pattern.search(filename)
		if chr_pattern_sr:
			chr = chr_pattern_sr.group(1)
		else:
			chr = os.path.splitext(os.path.split(filename)[1])[0]
		return chr