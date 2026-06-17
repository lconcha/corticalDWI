#!/bin/bash
source `which my_do_cmd`

## PREPARE ENVIRONMENT
# path_add /misc/lauterbur/lconcha/code/corticalDWI
# anaconda_on
# module load freesurfer ANTs/ workbench_con
# conda activate micapipe  # crucial to do after module load to get the correct python in path
###

export SUBJECTS_DIR=/datos/lauterbur2/lconcha/Edmonton/fs_edmonton
export CORTICAL_DWI_DIR=$(dirname $(realpath ${BASH_SOURCE[0]}))
sID=sub-Mcd014
nsteps=100
step_size="0.1"
tck_step_size=0.5
target_type=fsLR-32k



############## 1 ################
cortical_compute_laplacian.sh $sID
############## /1 ###############


############# 2 ################
# This version is for fsLR-32k
#for hemi in lh rh; do
#  for surf_type in white pial; do
#    cortical_resample_surface.sh $sID $hemi $surf_type $target_type
#  done
#done
############## /2 ###############


############# 2 ################
# This version is for ico6_sym
cortical_resample_surface_ico6_sym.sh $sID
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


############## 6 #################
cortical_DTI.sh $sID
############## /6 ################


############### 7 #################
cortical_CSD.sh $sID
############### /7 #################


############### 8 #################
cortical_MRDS.sh $sID
############### /8 #################

