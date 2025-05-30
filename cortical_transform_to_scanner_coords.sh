#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage: $(basename $0) <in_gii> <in_fs> <out_gii>

  <in_gii>         input GIFTI file to be transformed
  <in_fs>          input FreeSurfer surface file (e.g., lh.white).
                   The transformation matrix will be derived from this file.
  <out_gii>        output GIFTI file with transformed coordinates

  
  This script transforms the coordinates of the input GIFTI file,
  such that they match the scanner coordinates of the FreeSurfer surface.

  Use this in case mris_convert --to-scanner does not work for your GIFTI file.
  "
}


in_gii=$1
in_fs=$2
out_gii=$3



line=$(mris_info $in_fs 2>&1 | grep -e 'c_(ras)')
#A=$(echo $line | sed 's@c_\(ras\) : \(([0-9])\)@\1@' )
line=$(echo $line | awk -F: '{print $2}' | sed 's/(//g' | sed 's/)//g' | sed 's/ //g')

A=$(echo $line | awk -F, '{print $1}')
A=$(mrcalc $A -1 -mul); # invert all values
B=$(echo $line | awk -F, '{print $2}')
B=$(mrcalc $B -1 -mul); # invert all values
C=$(echo $line | awk -F, '{print $3}')
C=$(mrcalc $C -1 -mul); # invert all values


matrix=mimatriz.txt

printf "%1.6f\t%1.6f\t%1.6f\t%1.6f\n" 1 0 0 $A > $matrix
printf "%1.6f\t%1.6f\t%1.6f\t%1.6f\n" 0 1 0 $B >> $matrix
printf "%1.6f\t%1.6f\t%1.6f\t%1.6f\n" 0 0 1 $C >> $matrix
printf "%1.6f\t%1.6f\t%1.6f\t%1.6f\n" 0 0 0 1 >> $matrix


echo "Transformation matrix:"
cat $matrix

my_do_cmd wb_command -surface-apply-affine \
  $in_gii \
  $matrix \
  $out_gii


rm -f $matrix