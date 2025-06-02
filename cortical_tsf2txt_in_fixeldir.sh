#!/bin/bash
source `which my_do_cmd`
module load matlab
thispath=$(dirname $0)


help() {
  echo "
  Usage: $(basename $0) <fixel_dir> <nDepths>
  
  <fixel_dir>  directory containing fixel files, e.g., csd_fixel
  <nDepths>    number of depth points to keep in the txt file.
               This is in steps, not mm,
               and has to be less than or equal to the number of depth points in the tsf file.
  
  Converts all .tsf files in the fixel_dir to .txt files with nDepths depth points.

  "
}

if [ $# -ne 2 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi

fixel_dir=$1
nDepths=$2

for f in $fixel_dir/*.tsf
do
  cortical_tsf2txt.sh $f ${f%.tsf}.txt $nDepths
done
