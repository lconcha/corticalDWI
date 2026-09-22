#!/bin/bash
source `which my_do_cmd`
thisDir=$(dirname $(readlink -f "$0"))

help() {
  echo "
  Usage: $(basename $0) <tck> <map> <tsfout>

  <tck>     input tck file
  <map>     input scalar image to sample (.nii/.nii.gz/.mif)
  <tsfout>  output tsf file

  Drop-in replacement for 'tcksample <tck> <map> <tsfout>' that is robust to
  NaN/Inf voxels in <map>. tcksample writes one scalar value per streamline
  point, and MRtrix uses a single NaN value to mark the boundary between
  streamlines in the .tsf file -- identical to a genuine non-finite sample.
  A real NaN in the map is therefore indistinguishable from a streamline
  delimiter, and silently corrupts the output (extra phantom streamlines,
  truncated per-streamline data) for every tool that parses the file.

  If <map> contains any non-finite voxels, this script samples from a
  temporary copy with those voxels set to -1 instead (matching the existing
  MRtrix 'invalid sample' sentinel that cortical_browser.py already treats
  as missing data). The original <map> on disk is never modified. The
  output .tsf is then validated (streamline count vs. header); on mismatch
  the malformed output is deleted and the script exits non-zero, rather
  than leaving a bad file that looks finished.
  "
}

if [ $# -ne 3 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi

tck=$1
map=$2
tsfout=$3

for f in $tck $map
do
  if [ ! -f $f ]
  then
    echolor red "[ERROR] File does not exist: $f"
    exit 2
  fi
done

tmpDir=$(mktemp -d)
mapToSample=$map

nTotal=$(mrinfo -size $map 2>/dev/null | awk '{p=1; for(i=1;i<=NF;i++) p*=$i; print p}')
nFinite=$(mrstats -output count -quiet $map 2>/dev/null)

if [ -n "$nTotal" ] && [ -n "$nFinite" ] && [ "$nFinite" -ne "$nTotal" ]
then
  nBad=$((nTotal - nFinite))
  echolor yellow "[WARN] $map has $nBad non-finite (NaN/Inf) voxel(s) out of $nTotal."
  echolor yellow "[WARN] Sampling from a sanitized temporary copy (non-finite -> -1); $map is left untouched."
  mapToSample=${tmpDir}/sanitized.nii
  my_do_cmd mrcalc $map -finite $map -1 -if $mapToSample
fi

my_do_cmd tcksample $tck $mapToSample $tsfout

if ! python3 ${thisDir}/helpers/cortical_validate_tsf.py $tsfout
then
  echolor red "[ERROR] Sampling produced a malformed tsf, deleting: $tsfout"
  rm -f $tsfout
  rm -fR $tmpDir
  exit 2
fi

rm -fR $tmpDir
