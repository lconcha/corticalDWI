#!/bin/bash


subjID=$1
hemi=$2
target_type=$3
f_metric=$4; # in the style of dwi/mrds_fixels/rh_fsLR-32k_FA-par.txt (it can also be in mri in case of T1 or FLAIR stuff)
metric=$5; # short name for the metric


function mean_std() {
    f=$1

    awk '
{
    for (i=1; i<=NF; i++) {
        sum[i] += $i
        sum_sq[i] += ($i)^2
    }
}
END {
    for (i=1; i<=NF; i++) {
        mean = sum[i]/NR
        stddev = sqrt((sum_sq[i] - sum[i]^2/NR)/NR)
        printf "%.7f,%.7f\n", mean, stddev
    }
}' $f

}




tmpDir=$(mktemp -d)



for f in ${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_streamlines_*_indices.txt;
do
    echolor cyan "$f"
    region=$(echo $(basename $f) | sed -E 's/.*_([0-9]*)_indices.txt/\1/')
    echolor green "[INFO] Obtaining $metric from region $region in $hemi $target_type"

    sedcmd=$(cat $f | sed 's/\s/p;/g' | sed 's/;\n//' | sed 's/.$//g')
    sed -n "$sedcmd" $f_metric > ${tmpDir}/${region}_values.txt

    f_values=${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_${region}_mean_std_${metric}.txt
    mean_std ${tmpDir}/${region}_values.txt > $f_values

    cortical_1dplot.sh $f_values

done



tmpDir=$(mktemp -d)
