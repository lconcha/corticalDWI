#!/bin/bash
source `which my_do_cmd`
module load matlab
thispath=$(dirname $0)





tsf=$1
txt=$2
nDepths=$3


matlabjobfile=/tmp/matlabjobfile.m
####################### matlab job
echo "
addpath('${thispath}');
f_tsf   = '${tsf}';
nDepths = ${nDepths};
f_txt   = '${txt}';

tsf2txt(f_tsf,nDepths,f_txt)
exit
" > $matlabjobfile
###################### end of matlab job

cat $matlabjobfile

matlab -nodisplay -nosplash -nojvm <$matlabjobfile

rm $matlabjobfile
