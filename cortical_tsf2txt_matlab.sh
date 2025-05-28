#!/bin/bash
source `which my_do_cmd`
module load matlab
thispath=$(dirname $0)


help() {
  echo "
  Usage: $(basename $0) <fixel_dir> <nDepths>
  
  <fixel_dir>  directory containing fixel files, e.g., csd_fixel
  <nDepths>    number of depth points to keep in the txt file.
               This is in steps, not mm,
               and has to be less than or equal to the number of depth points in the tsf file.
  
  Converts all .tsf files in the fixel_dir to .txt files with nDepths depth points.

  Requires MATLAB, and calls tsf2txt.
  "
}

if [ $# -ne 2 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0


fixel_dir=$1
nDepths=$2



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
