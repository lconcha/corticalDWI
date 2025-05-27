#!/bin/bash


subjID=$1
hemi=$2
target_type=$3
f_metric=$4
metric=$5


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



for f in ${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_laplace-wm-streamlines_dwispace_*_indices.txt;
do
    region=$(echo $(basename $f) | sed -E 's/.*_([0-9]*)_indices.txt/\1/')
    echolor green "[INFO] Obtaining $metric from region $region in $hemi $target_type"

    sedcmd=$(cat $f | sed 's/\s/p;/g' | sed 's/;\n//' | sed 's/.$//g')
    sed -n "$sedcmd" $f_metric > ${tmpDir}/${region}_values.txt

    f_values=${SUBJECTS_DIR}/${subjID}/dwi/split/${hemi}_${target_type}_laplace-wm-streamlines_dwispace_${region}_mean_std_${metric}.txt
    mean_std ${tmpDir}/${region}_values.txt > $f_values

    cortical_1dplot.sh $f_values

done



tmpDir=$(mktemp -d)
