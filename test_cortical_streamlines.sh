#!/bin/bash
source `which my_do_cmd`

## PREPARE ENVIRONMENT
# path_add /misc/lauterbur/lconcha/code/corticalDWI
# anaconda_on
# module load freesurfer/7.4.0 ANTs/ workbench_con
# conda activate micapipe  # crucial to do after module load to get the correct python in path


export SUBJECTS_DIR=/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma
sID=sub-74277
nsteps=100
step_size="0.1"
tck_step_size=0.5
target_type=fsLR-5k



############## 1 ################
cortical_compute_laplacian.sh $sID
############## /1 ###############


############## 2 ################
for hemi in lh rh; do
  for surf_type in white pial; do
    cortical_resample_surface.sh $sID $hemi $surf_type $target_type
  done
done
############## /2 ###############


############## 3 ################
for hemi in lh rh; do
  cortical_compute_streamlines.sh $sID $hemi $target_type $nsteps $step_size
done
############## /3 ###############


############## 4 #################
cortical_register_t1_to_dwi.sh $sID
############## /4 ################


############## 5 #################
for hemi in lh rh; do
cortical_warp_tck_to_dwi.sh $sID $hemi $target_type
done
############## /5 ################



