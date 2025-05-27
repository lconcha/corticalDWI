#!/bin/bash
source `which my_do_cmd`
module load matlab
thispath=$(dirname $0)



fixel_dir=$1
nDepths=$2

# tsf=$1
# txt=$2
# nDepths=$3


matlabjobfile=/tmp/matlabjobfile.m
####################### matlab job
echo "
addpath('${thispath}');

D = dir(['${fixel_dir}' '/*.tsf']);

for t = 1 : length(D)
    f_tsf   = fullfile('${fixel_dir}',D(t).name);
    f_txt   = strrep(f_tsf,'.tsf','.txt');
    nDepths = ${nDepths};
    %f_txt   = '${txt}';
    tsf2txt(f_tsf,nDepths,f_txt)
end

exit
" > $matlabjobfile
###################### end of matlab job

cat $matlabjobfile

matlab -nodisplay -nosplash -nojvm <$matlabjobfile

rm $matlabjobfile
