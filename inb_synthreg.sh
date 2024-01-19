#!/bin/bash
source `which my_do_cmd`


threads=1
threads_max=$(($(nproc) -2))
doCortexOnly=0

print_help () {
  echo "
  `basename $0` -fixed <fixed> -moving <moving> -outbase <outbase> [options]

  fixed   : Reference image (any format that ANTS can read)
  moving  : Image to morph into the reference image.
  outbase : Prefix for all outputs
  

  Script to register two images driven by the automatic tissue segmentation of each one.
  Each image will undergo segmentation using mri_synthseg [1] available in freesurfer [2]. Next, 
  ANTS [3] will be used to compute the non-linear deformation field to morph the segmentation of <moving>
  to the segmentation of <fixed>. Finally, it will apply such deformations to <moving>.

  This script was inspired by the implementation done in micapipe [4].

  Options :

  -threads <int> : Number of threads to use. Default is $threads.
  -threads_max   : Use as many threads as possible. Calculated as (nproc - 2).
                   In this PC this would be $threads_max
  -neocortex     : Drive the segmentation using the cortical ribbon only.
                   Default is to use the segmentation of all tissue types, including basal ganglia,
                   but this option is useful if you want to refine the cortical ribbon segmentation 
                   (e.g. if you want to then use this to register cortical surfaces).
                   NOT IMPLEMENTED YET.
  

  LU15 (0N(H4
  INB, UNAM
  January 2024.
  lconcha@unam.mx

  1. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. B Billot, DN Greve, O Puonti, A Thielscher, K Van Leemput, B Fischl, AV Dalca, JE Iglesias. Medical Image Analysis, 83, 102789 (2023).
  2. https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg
  3. https://stnava.github.io/ANTs/
  4. https://micapipe.readthedocs.io/en/latest/
  "  
}


for arg in "$@"
do
  case "${arg}" in
    -h|-help)
        print_help
        exit 0
    ;;
    -fixed)
        fixed=$2
        shift;shift;
    ;;
    -moving)
        moving=$2
        shift;shift;
    ;;
    -outbase)
        outbase=$2
        shift;shift;
    ;;
    -threads)
        threads=$2
        shift;shift;
        echo "[INFO] Threads set to $threads"
    ;;
    -threads_max)
        threads=$threads_max
        shift;
        echo "[INFO] Threads set to $threads"
    ;;
    -neocortex)
        doCortexOnly=1
        echo "[INFO] Registration will be driven by cortical ribbon"
        shift;
    ;;
  esac
done

echo "[INFO]  Running on $threads threads"


echo "[INFO]  fixed  : $fixed"
echo "[INFO]  moving : $moving"
echo "[INFO]  outbase: $outbase"



fixed_seg=${outbase}_fixed_seg.nii
echolor cyan "[INFO] Segmentation of $fixed"
echolor cyan "[INFO]    This will create $fixed_seg"
my_do_cmd mri_synthseg \
   --threads $threads \
   --i $fixed \
   --o $fixed_seg \
   --resample ${outbase}_fixed_resampled.nii


moving_seg=${outbase}_moving_seg.nii
echolor cyan "[INFO] Segmentation of $moving"
echolor cyan "[INFO]    This will create $moving_seg"
my_do_cmd mri_synthseg \
   --threads $threads \
   --i $moving \
   --o $moving_seg \
   --resample ${outbase}_moving_resampled.nii


if [ $doCortexOnly -eq 1 ]
then
   my_do_cmd mrcalc $fixed_seg 42 -999 -replace 3 -999 -replace -999 -eq ${outbase}_fixed_seg_cortex.nii
   fixed_seg=${outbase}_fixed_seg_cortex.nii

   my_do_cmd mrcalc $moving_seg 42 -999 -replace 3 -999 -replace -999 -eq ${outbase}_moving_seg_cortex.nii
   moving_seg=${outbase}_moving_seg_cortex.nii
fi


my_do_cmd antsRegistrationSyN.sh -d 3 \
  -f "$fixed_seg" \
  -m "$moving_seg" \
  -o "${outbase}" \
  -t "s" \
  -n "$threads" \
  -p d \
  -i ["${fixed}","${moving}",0]


mv -v ${outbase}Warped.nii.gz ${outbase}_seg_Warped.nii.gz 

my_do_cmd antsApplyTransforms -d 3 \
  -i $moving \
  -r $fixed \
  -t ${outbase}0GenericAffine.mat \
  -t ${outbase}1Warp.nii.gz \
  -o ${outbase}Warped.nii.gz \
  -v -u int


echolor cyan "[INFO] Done. Check with:"
echolor bold "       mrview $fixed $fixed_seg ${outbase}Warped.nii.gz"
