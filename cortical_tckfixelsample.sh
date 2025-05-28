#!/bin/bash

# this is just a wrapper for the matlab function

help() {
  echo "
  Usage: $(basename $0) [options] -t <tck> -d <PDD> -n <nComp> -i <input1> [-i <input2> ...] -p <prefix>

  Options:
  -t <tck>       : Path to the input tck file.
  -d <PDD>       : Path to the PDD file.
  -n <nComp>     : Number of components to use.
  -i <input>     : Input files (can be specified multiple times).
  -p <prefix>    : Prefix for output files.

  This script will run a MATLAB function to sample fixel values from a tck file.
  "
}

if [ $# -lt 1 ]
then
  echolor red "Not enough arguments"
  help
  exit 0
fi


Inputs=""
while getopts "t:d:n:i:p:" flag
do
    case "${flag}" in
        t) tck=${OPTARG};;
        d) PDD=${OPTARG};;
        n) nComp=${OPTARG};;
        i) input=${OPTARG};Inputs="$Inputs '$input'";;
        p) prefix=${OPTARG};;
    esac
done

mInputs=`echo $Inputs | sed 's/ /,/g'`

matlabjobfile=/tmp/matlabjobfile.m

####################### matlab job
echo "

addpath('/home/inb/lconcha/fmrilab_software/mrtrix3/matlab/');
addpath('/misc/mansfield/lconcha/software/Displasias');

  f_tck     = '$tck';
  f_PDD     = '$PDD';
  f_ncomp   = '$nComp';
  ff_values = {$mInputs};
  f_prefix  = '$prefix';
  
  
VALUES = displasia_tckfixelsample(f_tck, f_PDD, f_ncomp, ff_values, f_prefix);
exit

" > $matlabjobfile
###################### end of matlab job

cat $matlabjobfile

matlab -nodisplay -nosplash -nojvm <$matlabjobfile

rm $matlabjobfile

