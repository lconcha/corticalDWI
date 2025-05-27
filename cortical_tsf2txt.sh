#!/bin/bash
source `which my_do_cmd`


tsf=$1
txt=$2
nCols=$3


tmpDir=$(mktemp -d)


my_do_cmd tsfinfo -ascii ${tmpDir}/prefix $tsf

#paste ${tmpDir}/prefix* >> $txt

#ulimit -n 99999
#printf "%s\n" ${tmpDir}/prefix* | sort -n | xargs -d '\n' paste > $txt


n=$(ls ${tmpDir}/prefix*  | wc -l)
echolor cyan "[INFO] Transposing each txt ($n in total)"
for f in ${tmpDir}/prefix*
do
  ft=${f}_transposed
  transpose_table.sh $f | sed 's/\t/ /g' > $ft
done
cat ${tmpDir}/*transposed >> ${tmpDir}/full.txt



echolor cyan "[INFO] Retaining only the first $nCols columns"
cut -d ' ' -f 1-$nCols ${tmpDir}/full.txt >  ${tmpDir}/cropped.txt
awk  -v C=$nCols '{ for(N=1; N<=C; N++) if($N=="") $N="-1" } 1' ${tmpDir}/cropped.txt > $txt


rm -fR $tmpDir