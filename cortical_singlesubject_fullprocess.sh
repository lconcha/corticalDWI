#!/bin/bash

###  SOURCE THIS FILE TO RUN THE FULL CORTICAL DWI PIPELINE FOR A SINGLE SUBJECT
###  Do not run it as a script!!!

#### Modify this ###############################3
# Subject data
subjid=sub-79864
bids_dir=/misc/nyquist/danielacoutino/glaucoma/bids
export SUBJECTS_DIR=/misc/sherrington/lconcha/TMP/glaucoma/fs_glaucoma
# Paths to tools needed
mrtrix_modules_dir=/misc/sherrington/lconcha/code/inb_mrtrix_modules/bin
corticalDWI_dir=/misc/sherrington/lconcha/code/corticalDWI
inb_tools_dir=/misc/sherrington/lconcha/code/inb_tools
#### Parameters
target_type=fsLR-32k
step_size="0.1"
nsteps=100
tck_step_size=0.5
target_type=fsLR-32k
fixel_dir=csd_fixels_singletissue
angle=45
nDepths=30
template=/misc/sherrington/lconcha/code/corticalDWI/test_cortical_mult-stats_per_region_template.txt
#### Do not modify below this line unless you know what you are doing





# Prepare the environment
module load freesurfer/7.3.2 mrtrix/3.0.4 ANTs/2.4.4 workbench_con/2.0.1
anaconda_on; # Remove this if you always have anaconda activated (I don't)
conda activate micapipe
export PATH=${mrtrix_modules_dir}:${corticalDWI_dir}:${inb_tools_dir}:$PATH



#### Start the pipeline
cortical_add_dwi_to_freesurfer.sh $subjid $bids_dir
cortical_compute_laplacian.sh $subjid
for hemi in lh rh; do
  for surf_type in white pial; do
    cortical_resample_surface.sh $subjid $hemi $surf_type $target_type
  done
done

for hemi in lh rh; do
  cortical_compute_streamlines.sh $subjid $hemi $target_type $nsteps $step_size
done

cortical_register_t1_to_dwi.sh $subjid

for hemi in lh rh; do
  cortical_warp_tck_to_dwi.sh $subjid $hemi $target_type $tck_step_size
done

cortical_CSD.sh $subjid
#cortical_MRDS.sh $subjid; # Uncomment this if you want to run MRDS 
cortical_tcksample_dti.sh $subjid $nDepths
cortical_tcksamplefixels_afd.sh $subjid $fixel_dir $angle $nDepths $target_type

for hemi in rh lh; do 
  cortical_separate_streamlines_by_aparc.sh $subjid $hemi $target_type
done

cortical_multi-stats_per_region.sh -t $template $subjid $target_type