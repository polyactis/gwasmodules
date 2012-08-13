#!/bin/sh

noOfLinesDefault=30
noOfLines=$1
if [ -z $noOfLines ]
then
	noOfLines=$noOfLinesDefault
fi

watch -d -n 12 "condor_q -cputime -dag |tail -n $noOfLines"
