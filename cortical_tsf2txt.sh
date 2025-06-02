#!/bin/bash
source `which my_do_cmd`


help() {
  echo "
  Usage: $(basename $0) <tsf_file> <output_txt_file> <nCols>
  
  <tsf_file>        input tsf file
  <output_txt_file> output text file
  <nCols>           number of columns to retain in the output text file
  
  Converts a .tsf file to a .txt file.

  This script does not use MATLAB, but it is kinda slow, as it transposes
  intermediary text files one by one using awk (transpose_table.sh).

  This script should be rewritten in Python for speed.
  "
}

if [ $# -ne 3 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi


tsf=$1
txt=$2
nCols=$3


tmpDir=$(mktemp -d)


my_do_cmd tsfinfo -ascii ${tmpDir}/prefix $tsf


n=$(ls ${tmpDir}/prefix*  | wc -l)
for f in ${tmpDir}/prefix*
do
  echo "X" >> $f
done
cat ${tmpDir}/prefix* > ${tmpDir}/full_X.txt
cat ${tmpDir}/full_X.txt | tr '\n' ' ' | sed 's/X/\n/g' | sed 's/^ //g' > ${tmpDir}/full.txt


echolor cyan "[INFO] Retaining only the first $nCols columns"
cut -d ' ' -f 1-$nCols ${tmpDir}/full.txt >  ${tmpDir}/cropped.txt
awk  -v C=$nCols '{ for(N=1; N<=C; N++) if($N=="") $N="-1" } 1' ${tmpDir}/cropped.txt > $txt


rm -fR $tmpDir