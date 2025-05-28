#!/bin/bash

sID=$1
target_type=$2
f_template=$(dirname $0)/cortical_multi-stats_per_region_template.txt

help() {
  echo "
  Usage: $(basename $0) <subjID> <target_type> [options]

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


while getopts "f" opt
do
  case $opt in
    t)
      f_template=${OPTARG}
    ;;
    \?)
      echolor red "[ERROR] Invalid flag."
      exit 2
    ;;
  esac
done
shift $((OPTIND-1))


cat $f_template | while read line
do
    if [[ $line == \#* ]]; then continue;fi
    for hemi in lh rh
    do
        f=$(echo $line | awk '{print $1}' | sed "s/HEMI/${hemi}/" | sed "s/TARGET/${target_type}/")
        metric_name=$(echo $line | awk '{print $2}')
        cortical_stats_per_region.sh $sID $hemi $target_type $f $metric_name
    done
done


