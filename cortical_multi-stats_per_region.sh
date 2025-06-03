#!/bin/bash
source `which my_do_cmd`

f_template=$(dirname $0)/cortical_multi-stats_per_region_template.txt

help() {
  echo "
  Usage: $(basename $0)  <subjID> <target_type> [options]

  <subjID>         subject ID in the form of sub-74277
  <target_type>    type of target (e.g., 'fsLR-32k')

  This script will compute cortical statistics per region for the given subject and target type.
  The regions are defined in a template file.
  
  Options:
    -t <template_file>   : Specify a custom template file for regions (default: $f_template
  "
}


if [ $# -lt 2 ]
then
  echolor red "[ERROR] Not enough arguments"
  help
  exit 0
fi


while getopts "t:" opt
do
  case $opt in
    t)
      f_template=${OPTARG}
      echolor green "[INFO] Using template file: $f_template"
    ;;
    \?)
      echolor red "[ERROR] Invalid flag."
      exit 2
    ;;
  esac
done
shift "$((OPTIND-1))"

subjID=$1
target_type=$2



if [ ! -f $f_template ]; then
  echolor red "[ERROR] Template file not found: $f_template"
  exit 1
fi


echolor green "[INFO] Processing subject: $subjID with target type: $target_type"
echolor green "[INFO] Using template file: $f_template"


tmpDir=$(mktemp -d)

cat $f_template | while read line
do
    if [[ $line == \#* ]]; then continue;fi
    for hemi in lh rh
    do
        f_metric=$(echo $line | awk '{print $1}' | sed "s/HEMI/${hemi}/" | sed "s/TARGET/${target_type}/")
        metric_name=$(echo $line | awk '{print $2}')
        echolor bold "Metric is $metric_name"
        #my_do_cmd  cortical_stats_per_region.sh $subjID $hemi $target_type $f $metric_name
 
        for f in ${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_streamlines_*_indices.txt
        do
            echolor cyan "$f"
            region=$(echo $(basename $f) | sed -E 's/.*_([0-9]*)_indices.txt/\1/')
            echolor green "[INFO] Obtaining $metric_name from region $region in $hemi $target_type"

            sedcmd=$(cat $f | sed 's/\s/p;/g' | sed 's/;\n//' | sed 's/.$//g')
            sed -n "$sedcmd" ${SUBJECTS_DIR}/${subjID}/$f_metric > ${tmpDir}/${region}_values.txt

            

            f_values_in=${tmpDir}/${region}_values.txt
            f_values_out=${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_${region}_mean_std_${metric_name}.txt
            my_do_cmd  cortical_stats_per_region.py $f_values_in $f_values_out
            my_do_cmd  cortical_1dplot.sh $f_values_out
        done
    done
done

rm -fR $tmpDir