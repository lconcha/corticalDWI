#!/bin/bash
source `which my_do_cmd`
module load matlab
thispath=$(dirname $0)


help() {
  echo "
  Usage: $(basename $0) <fixel_dir>
  
  <fixel_dir>  directory containing fixel files, e.g., csd_fixel
  
  Converts all .tsf files in the fixel_dir to .txt files.

  "
}

if [ $# -ne 2 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi

fixel_dir=$1

echolor cyan "[INFO] Will convert all tsf files in $fixel_dir to txt files."


for f in $fixel_dir/*.tsf
do
  txt=${f%.tsf}.txt
  if [ -f $txt ]
  then
    echolor green "[WARN] $txt exists, skipping."
  else
    my_do_cmd tsf2txt $f $txt
  fi
done


