#!/bin/bash
source `which my_do_cmd`
thisDir=$(dirname $(readlink -f "$0"))

help() {
  echo "
  Usage: $(basename $0) -angle <deg> <fixel_image> <tck> <out_indices.tsf> <out_par.tsf> <out_perp.tsf> <out_perp_av.tsf>

  Drop-in replacement for:
    tcksamplefixels -angle <deg> <fixel_image> <tck> <out_indices.tsf> <out_par.tsf> <out_perp.tsf> <out_perp_av.tsf>

  that is robust to NaN/Inf voxels in <fixel_image>. See cortical_tcksample_safe.sh
  for why a non-finite sample corrupts the .tsf format (NaN doubles as the
  MRtrix streamline delimiter).

  If <fixel_image> contains any non-finite voxels, this script samples from a
  temporary copy with those voxels set to -1 instead (matching the existing
  MRtrix 'invalid sample' sentinel that cortical_browser.py already treats as
  missing data). The original <fixel_image> on disk is never modified. All
  four output .tsf files are then validated (streamline count vs. header); on
  any mismatch every malformed output is deleted and the script exits
  non-zero, rather than leaving files that look finished.
  "
}

if [ $# -ne 8 -o "$1" != "-angle" ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi

angle=$2
fixel=$3
tck=$4
out_indices=$5
out_par=$6
out_perp=$7
out_perp_av=$8

for f in $fixel $tck
do
  if [ ! -f $f ]
  then
    echolor red "[ERROR] File does not exist: $f"
    exit 2
  fi
done

tmpDir=$(mktemp -d)
fixelToSample=$fixel

nTotal=$(mrinfo -size $fixel 2>/dev/null | awk '{p=1; for(i=1;i<=NF;i++) p*=$i; print p}')
nFinite=$(mrstats -output count -quiet $fixel 2>/dev/null)

if [ -n "$nTotal" ] && [ -n "$nFinite" ] && [ "$nFinite" -ne "$nTotal" ]
then
  nBad=$((nTotal - nFinite))
  echolor yellow "[WARN] $fixel has $nBad non-finite (NaN/Inf) voxel(s) out of $nTotal."
  echolor yellow "[WARN] Sampling from a sanitized temporary copy (non-finite -> -1); $fixel is left untouched."
  fixelToSample=${tmpDir}/sanitized.mif
  my_do_cmd mrcalc $fixel -finite $fixel -1 -if $fixelToSample
fi

my_do_cmd tcksamplefixels \
  -angle $angle \
  $fixelToSample \
  $tck \
  $out_indices \
  $out_par \
  $out_perp \
  $out_perp_av

isOK=1
for tsfout in $out_indices $out_par $out_perp $out_perp_av
do
  if ! python3 ${thisDir}/helpers/cortical_validate_tsf.py $tsfout
  then
    echolor red "[ERROR] Sampling produced a malformed tsf: $tsfout"
    isOK=0
  fi
done

if [ $isOK -eq 0 ]
then
  echolor red "[ERROR] Deleting all outputs from this call, see errors above."
  rm -f $out_indices $out_par $out_perp $out_perp_av
  rm -fR $tmpDir
  exit 2
fi

rm -fR $tmpDir
