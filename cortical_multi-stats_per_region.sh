#!/bin/bash

sID=$1
target_type=$2
f_template=$(dirname $0)/cortical_multi-stats_per_region_template.txt


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


