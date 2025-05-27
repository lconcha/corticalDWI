#!/bin/bash
source `which my_do_cmd`


#!/bin/bash

# Convert to gifti
left
mris_convert --to-scanner lh.white lh.white.surf.gii
wb_command -set-structure lh.white.surf.gii  CORTEX_LEFT -surface-type ANATOMICAL -surface-secondary-type GRAY_WHITE
mris_convert -c lh.curv lh.sphere lh.curv.shape.gii
wb_command -set-structure lh.curv.shape.gii CORTEX_LEFT
mris_convert -c lh.sulc lh.sphere lh.sulc.shape.gii
wb_command -set-structure lh.sulc.shape.gii CORTEX_LEFT
wb_command -metric-merge -metric lh.curv.shape.gii -metric lh.sulc.shape.gii lh.curv_sulc.shape.gii


mris_convert --to-scanner lh.pial lh.pial.surf.gii
wb_command -set-structure lh.pial.surf.gii  CORTEX_LEFT -surface-type ANATOMICAL -surface-secondary-type PIAL

mris_convert  lh.sphere lh.sphere.surf.gii; # notice lack of --to-scanner for spherical, otherwise -surface-resample complains
wb_command -set-structure lh.sphere.surf.gii  CORTEX_LEFT -surface-type SPHERICAL

# right
mris_convert --to-scanner rh.white rh.white.surf.gii
wb_command -set-structure rh.white.surf.gii  CORTEX_RIGHT -surface-type ANATOMICAL -surface-secondary-type GRAY_WHITE
mris_convert -c rh.curv rh.sphere rh.curv.shape.gii
wb_command -set-structure rh.curv.shape.gii CORTEX_RIGHT
mris_convert -c rh.sulc rh.sphere rh.sulc.shape.gii
wb_command -set-structure rh.sulc.shape.gii CORTEX_RIGHT
wb_command -metric-merge -metric rh.curv.shape.gii -metric rh.sulc.shape.gii rh.curv_sulc.shape.gii

mris_convert --to-scanner rh.pial rh.pial.surf.gii
wb_command -set-structure rh.pial.surf.gii  CORTEX_RIGHT -surface-type ANATOMICAL -surface-secondary-type PIAL

mris_convert rh.sphere rh.sphere.surf.gii
wb_command -set-structure rh.sphere.surf.gii  CORTEX_RIGHT -surface-type SPHERICAL


#Download fsLR spheres:
#wget https://templateflow.s3.amazonaws.com/tpl-fsLR/tpl-fsLR_hemi-L_den-32k_sphere.surf.gii
#wget https://templateflow.s3.amazonaws.com/tpl-fsLR/tpl-fsLR_hemi-R_den-32k_sphere.surf.gii



# Resample to fsLR32k
# left
target_sphere_left=tpl-fsLR_hemi-L_den-32k_sphere.surf.gii
wb_command -surface-resample lh.white.surf.gii  lh.sphere.surf.gii $target_sphere_left BARYCENTRIC lh.white.fsLR32k.surf.gii
wb_command -surface-resample lh.pial.surf.gii   lh.sphere.surf.gii $target_sphere_left BARYCENTRIC lh.pial.fsLR32k.surf.gii
wb_command -surface-resample lh.sphere.surf.gii lh.sphere.surf.gii $target_sphere_left BARYCENTRIC lh.sphere.fsLR32k.surf.gii
wb_command -metric-resample  lh.curv.shape.gii  lh.sphere.surf.gii $target_sphere_left BARYCENTRIC lh.fsLR32k.curv.shape.gii
wb_command -metric-resample  lh.curv_sulc.shape.gii  lh.sphere.surf.gii $target_sphere_left BARYCENTRIC lh.fsLR32k.curv_sulc.shape.gii

# right
target_sphere_right=tpl-fsLR_hemi-R_den-32k_sphere.surf.gii
wb_command -surface-resample rh.white.surf.gii  rh.sphere.surf.gii $target_sphere_right BARYCENTRIC rh.white.fsLR32k.surf.gii
wb_command -surface-resample rh.pial.surf.gii   rh.sphere.surf.gii $target_sphere_right BARYCENTRIC rh.pial.fsLR32k.surf.gii
wb_command -surface-resample rh.sphere.surf.gii rh.sphere.surf.gii $target_sphere_right BARYCENTRIC rh.sphere.fsLR32k.surf.gii
wb_command -metric-resample  rh.curv.shape.gii  rh.sphere.surf.gii $target_sphere_right BARYCENTRIC rh.fsLR32k.curv.shape.gii
wb_command -metric-resample  rh.curv_sulc.shape.gii  rh.sphere.surf.gii $target_sphere_left BARYCENTRIC rh.fsLR32k.curv_sulc.shape.gii

## Flip left to right
#echo "---- Flip left to right"
#wb_command -surface-flip-lr \
#  lh.white.fsLR32k.surf.gii \
#  l2r.white.fsLR32k.surf.gii

## Run MSM
echo "----- run MSM on resampled curvatures"
msmoutput=l2r_msm_curv_sulc.
fcheck=${msmoutput}sphere.reg.surf.gii
if [ ! -f $fcheck ]
then
    # lh and rh resampled curvatures are provided to drive msm, no flipping left-right
    ${FSLDIR}/bin/msm \
    --inmesh=$target_sphere_left \
    --indata=lh.fsLR32k.curv_sulc.shape.gii \
    --refdata=rh.fsLR32k.curv_sulc.shape.gii \
    --format=GIFTI \
    --verbose --debug \
    --out=$msmoutput
else
  echo "**** MSM has already run: $fcheck"
fi 


#now, to visualize, we want to have lh and rh and l2r  all on the same surface (left was our input)
#  so we set the structure metadata for rh and lh2rh to be CORTEX_LEFT
wb_command -set-structure rh.fsLR32k.curv.shape.gii CORTEX_LEFT
wb_command -set-structure l2r_msm_fromResampled.sphere.reg.surf.gii CORTEX_LEFT

#now we can visualize as:
#wb_view $target_sphere_left l2r_msm_fromResampled.sphere.reg.surf.gii lh.fsLR32k.curv.shape.gii  rh.fsLR32k.curv.shape.gii   

#(select CORTEX_LEFT if a pop-up comes up)

# In wb_view:
#   1. if we visualize target_sphere_left with lh.fsLR32k.curv.shape.gii overlaid, this is the unwarped input (lh curv)
#   2. if we visualize target_sphere_left with rh.fsLR32k.curv.shape.gii overlaid, this is the reference input (rh curv, but visualized on left side)
#      - should see these are almost aligned but not quite (L-R asym)
#   3. if we visualize l2r_msm_fromResampled.sphere.reg.surf.gii  with lh.fsLR32k.curv.shape.gii overlaid, this is the warped lh
#      - we should see 3 should be well aligned with 2.
#




#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%5

# ## Convert to gifti
# # left
# my_do_cmd mris_convert --to-scanner lh.white lh.white.surf.gii
# my_do_cmd wb_command -set-structure lh.white.surf.gii  CORTEX_LEFT -surface-type ANATOMICAL -surface-secondary-type GRAY_WHITE
# my_do_cmd mris_convert -c lh.curv lh.sphere lh.curv.shape.gii

# my_do_cmd mris_convert --to-scanner lh.pial lh.pial.surf.gii
# my_do_cmd wb_command -set-structure lh.pial.surf.gii  CORTEX_LEFT -surface-type ANATOMICAL -surface-secondary-type PIAL

# my_do_cmd mris_convert  lh.sphere lh.sphere.surf.gii; # notice lack of --to-scanner for spherical, otherwise -surface-resample complains
# my_do_cmd wb_command -set-structure lh.sphere.surf.gii  CORTEX_LEFT -surface-type SPHERICAL

# # right
# my_do_cmd mris_convert --to-scanner rh.white rh.white.surf.gii
# my_do_cmd wb_command -set-structure rh.white.surf.gii  CORTEX_RIGHT -surface-type ANATOMICAL -surface-secondary-type GRAY_WHITE
# my_do_cmd mris_convert -c rh.curv rh.sphere rh.curv.shape.gii

# my_do_cmd mris_convert --to-scanner rh.pial rh.pial.surf.gii
# my_do_cmd wb_command -set-structure rh.pial.surf.gii  CORTEX_RIGHT -surface-type ANATOMICAL -surface-secondary-type PIAL

# my_do_cmd mris_convert rh.sphere rh.sphere.surf.gii
# my_do_cmd wb_command -set-structure rh.sphere.surf.gii  CORTEX_RIGHT -surface-type SPHERICAL


# # Resample to fsLR32k
# # left
# target_sphere=/misc/lauterbur/lconcha/code/corticalDWI/fsLR-32k/surf/fsLR-32k.L.sphere.surf.gii
# my_do_cmd wb_command -surface-resample lh.white.surf.gii  lh.sphere.surf.gii $target_sphere BARYCENTRIC lh.white.fsLR32k.surf.gii
# my_do_cmd wb_command -surface-resample lh.pial.surf.gii   lh.sphere.surf.gii $target_sphere BARYCENTRIC lh.pial.fsLR32k.surf.gii
# my_do_cmd wb_command -surface-resample lh.sphere.surf.gii lh.sphere.surf.gii $target_sphere BARYCENTRIC lh.sphere.fsLR32k.surf.gii
# my_do_cmd wb_command -metric-resample  lh.curv.shape.gii  lh.sphere.surf.gii $target_sphere BARYCENTRIC lh.fsLR32k.curv.shape.gii
# # right
# target_sphere=/misc/lauterbur/lconcha/code/corticalDWI/fsLR-32k/surf/fsLR-32k.R.sphere.surf.gii
# my_do_cmd wb_command -surface-resample rh.white.surf.gii  rh.sphere.surf.gii $target_sphere BARYCENTRIC rh.white.fsLR32k.surf.gii
# my_do_cmd wb_command -surface-resample rh.pial.surf.gii   rh.sphere.surf.gii $target_sphere BARYCENTRIC rh.pial.fsLR32k.surf.gii
# my_do_cmd wb_command -surface-resample rh.sphere.surf.gii rh.sphere.surf.gii $target_sphere BARYCENTRIC rh.sphere.fsLR32k.surf.gii
# my_do_cmd wb_command -metric-resample  rh.curv.shape.gii  rh.sphere.surf.gii $target_sphere BARYCENTRIC rh.fsLR32k.curv.shape.gii


# ## Flip left to right
# echo "---- Flip left to right"
# my_do_cmd wb_command -surface-flip-lr \
#   lh.white.fsLR32k.surf.gii \
#   l2r.white.fsLR32k.surf.gii

# ## Compute curvatures in fsLR-32k meshes
# echo "---- Compute curvatures in fsLR-32k meshes"
# my_do_cmd wb_command -surface-curvature \
#   rh.white.fsLR32k.surf.gii \
#   -mean rh.white.fsLR32k.computed.curv.shape.gii
# my_do_cmd wb_command -surface-curvature \
#   lh.white.fsLR32k.surf.gii \
#   -mean lh.white.fsLR32k.computed.curv.shape.gii
# my_do_cmd wb_command -surface-curvature \
#    l2r.white.fsLR32k.surf.gii \
#   -mean  l2r.white.fsLR32k.computed.curv.shape.gii





# ## Run MSM
# MSMcommand=$FSLDIR/bin/msm
# echo "----- run MSM on resampled curvatures"
# echo "----- MSM command is $MSMcommand"
# msmoutput=l2r_msm_fromResampled.
# fcheck=${msmoutput}sphere.reg.surf.gii
# if [ ! -f $fcheck ]
# then
#     # lh and rh resampled curvatures are provided to drive msm, no flipping left-right
#     my_do_cmd $MSMcommand \
#     --inmesh=$target_sphere \
#     --refmesh=$target_sphere \
#     --indata=lh.fsLR32k.curv.shape.gii \
#     --refdata=rh.fsLR32k.curv.shape.gii \
#     --format=GIFTI \
#     --verbose --debug \
#     --out=$msmoutput
# else
#   echo "**** MSM has already run: $fcheck"
# fi 

# echo "----- run MSM on computed curvatures"
# msmoutput=l2r_msm_fromComputed.
# fcheck=${msmoutput}sphere.reg.surf.gii
# if [ ! -f $fcheck ]
# then
#     # Here I use the computed curvature of the left-to-right surface vs. the rh curvature to drive msm.
#     my_do_cmd $MSMcommand \
#     --inmesh=$target_sphere \
#     --refmesh=$target_sphere \
#     --indata=l2r.white.fsLR32k.computed.curv.shape.gii \
#     --refdata=rh.white.fsLR32k.computed.curv.shape.gii \
#     --format=GIFTI \
#     --verbose --debug \
#     --out=$msmoutput
# else
#   echo "**** MSM has already run: $fcheck"
# fi 


# echolor cyan "Resample surface based on MSM registration"
# my_do_cmd wb_command -surface-resample \
#   l2r.white.fsLR32k.surf.gii \
#   $target_sphere \
#   ${msmoutput}sphere.reg.surf.gii \
#   BARYCENTRIC \
#   l2r.white_deformed.surf.gii

# echolor cyan "Flip the surface back (l2r_deformed --> lh_deformed)"
# my_do_cmd wb_command -surface-flip-lr \
#   l2r.white_deformed.surf.gii \
#   lh.white_deformed.surf.gii
#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%5

#freeview -f ?h.white.fsLR32k.surf.gii lh.white_deformed.surf.gii


# # just for completeness, check the number of data points
# for metricfile in {lh,rh}.fsLR32k.curv.shape.gii {l2r,rh}.white.fsLR32k.computed.curv.shape.gii
# do
#   echo "Checking metric file $metricfile"
#   my_do_cmd wb_command -metric-stats $metricfile -reduce COUNT_NONZERO
# done










# ext_surf=surf.gii
# ext_data=curv.shape.gii


# my_do_cmd mris_convert lh.sphere lh.sphere.${ext_surf}
# my_do_cmd mris_convert rh.sphere rh.sphere.${ext_surf}
# my_do_cmd mris_convert lh.white lh.white.${ext_surf}
# my_do_cmd mris_convert rh.white rh.white.${ext_surf}
# my_do_cmd mris_convert -c lh.curv lh.sphere lh.${ext_data}; # careful, as mris_convert likes to write lh. or rh. before whatever output file name (unless it is alreadh ?h)
# my_do_cmd mris_convert -c rh.curv rh.sphere rh.${ext_data}


# echolor cyan "Create corresponding l/r spherical surfaces"
# nVertices=32492
# my_do_cmd wb_command -surface-create-sphere $nVertices Sphere.lconcha.R.surf.gii
# my_do_cmd wb_command -surface-flip-lr Sphere.lconcha.R.surf.gii Sphere.lconcha.L.surf.gii
# my_do_cmd wb_command -set-structure Sphere.lconcha.R.surf.gii CORTEX_RIGHT
# my_do_cmd wb_command -set-structure Sphere.lconcha.L.surf.gii CORTEX_LEFT


# echolor cyan "Resample to my spherical surfaces"
# my_do_cmd wb_command -surface-resample \
#   lh.white.${ext_surf} \
#   lh.sphere.${ext_surf} \
#   Sphere.lconcha.L.${ext_surf} \
#   BARYCENTRIC \
#   my_lh.lconcha.white.${ext_surf}

# my_do_cmd wb_command -surface-resample \
#   rh.white.${ext_surf} \
#   rh.sphere.${ext_surf} \
#   Sphere.lconcha.R.${ext_surf} \
#   BARYCENTRIC \
#   my_rh.lconcha.white.${ext_surf}

# echolor cyan "Flip left to right"
# my_do_cmd wb_command -surface-flip-lr \
#   lh_white_fsLR-32k.${ext_surf} \
#   my_flipped_l2r_fsLR-32k.${ext_surf}


# echolor cyan "Compute curvatures in lconcha meshes"
# my_do_cmd wb_command -surface-curvature \
#   my_lh.lconcha.white.${ext_surf} \
#   -mean my_lh.lconcha.white.${ext_data}
# my_do_cmd wb_command -surface-curvature \
#   my_rh.lconcha.white.${ext_surf} \
#   -mean my_rh.lconcha.white.${ext_data}
# my_do_cmd wb_command -surface-curvature \
#   my_flipped_l2r_fsLR-32k.${ext_surf} \
#   -mean my_flipped_l2r_fsLR-32k.${ext_data}

# msmoutput=my_lh_to_rh_lconcha_newmsm.
# if [ ! -f ${msmoutput}sphere.reg.surf.gii ]
# then
# echolor cyan "Run MSM"
# my_do_cmd $FSLDIR/bin/msm \
#   --inmesh=Sphere.lconcha.R.surf.gii \
#   --refmesh=Sphere.lconcha.R.surf.gii \
#   --indata=my_flipped_l2r_fsLR-32k.${ext_data} \
#   --refdata=my_rh.lconcha.white.${ext_data} \
#   --format=GIFTI \
#   --verbose --debug \
#   --out=$msmoutput
# # my_do_cmd newmsm \
# #   --inmesh=Sphere.lconcha.R.surf.gii \
# #   --refmesh=Sphere.lconcha.R.surf.gii \
# #   --indata=my_flipped_l2r_fsLR-32k.${ext_data} \
# #   --refdata=my_rh.lconcha.white.${ext_data} \
# #   --format=GIFTI \
# #   --verbose --debug \
# #   --numthreads=8 \
# #   --out=$msmoutput
# else
#   echolor green "MSM has already run: ${msmoutput}.sphere.reg.surf.gii"
# fi 


# echolor cyan "Resample surface based on MSM registration"
# my_do_cmd wb_command -surface-resample \
#   my_flipped_l2r_fsLR-32k.${ext_surf} \
#   Sphere.lconcha.R.surf.gii \
#   my_lh_to_rh_lconcha.sphere.reg.surf.gii \
#   BARYCENTRIC \
#   out_l2r.white_deformed.surf.gii


# echolor cyan "Flip back to left hemisphere"
# my_do_cmd wb_command -surface-flip-lr \
#   out_l2r.white_deformed.surf.gii \
#   my_lh_reg2rh.lconcha.white.${ext_surf}


# echolor green "freeview -f rh.white.${ext_surf} &; freeview -f my_lh_reg2rh.lconcha.white.${ext_surf} &"




# my_do_cmd $FSLDIR/bin/msmapplywarp \
#   my_lh_to_rh_lconchasphere.reg.surf.gii \
#   my_lh_to_rh_deformed_white \
#   -anat Sphere.lconcha.R.surf.gii \
#   my_flipped_l2r_fsLR-32k.${ext_surf}


# echolor cyan "Flip left to right"
# my_do_cmd wb_command -surface-flip-lr \
#   my_lh_to_rh_deformed_white.surf.gii_anatresampled.surf.gii \
#   my_lh_to_rh_deformed_white.surf.gii_anatresampled_movedbacktoLH.surf.gii




# echolor cyan "Flip left to right"
# my_do_cmd wb_command -surface-flip-lr \
#   lh_white_fsLR-32k.surf.gii \
#   my_flipped_l2r_fsLR-32k.surf.gii

# echolor cyan "Compute curvatures in fsLR meshes"
# my_do_cmd wb_command -surface-curvature \
#   lh_white_fsLR-32k.surf.gii \
#   -mean lh_white_fsLR-32k.${ext_data}
# my_do_cmd wb_command -surface-curvature \
#   my_flipped_l2r_fsLR-32k.surf.gii \
#   -mean my_flipped_l2r_fsLR-32k.${ext_data}

# lh_template_surf=/misc/lauterbur/lconcha/code/corticalDWI/fsLR-32k/surf/fsLR-32k.L.sphere.surf.gii
# rh_template_surf=/misc/lauterbur/lconcha/code/corticalDWI/fsLR-32k/surf/fsLR-32k.R.sphere.surf.gii
# echolor cyan "Compute spherical surfaces with fsLR mesh"
# my_do_cmd wb_command -surface-resample \
#   lh.sphere.${ext_surf} \
#   lh.sphere.${ext_surf} \
#   $lh_template_surf \
#   BARYCENTRIC \
#   my_lh_fsLR32k.sphere.${ext_surf}
# my_do_cmd wb_command -surface-resample \
#   rh.sphere.${ext_surf} \
#   rh.sphere.${ext_surf} \
#   $rh_template_surf \
#   BARYCENTRIC \
#   my_rh_fsLR32k.sphere.${ext_surf}

# my_do_cmd mris_convert lh.sphere lh.sphere.${ext_surf}
# my_do_cmd mris_convert ../xhemi/surf/rh.sphere rh.xhemi.sphere.${ext_surf}
# my_do_cmd mris_convert lh.white lh.white.${ext_surf}
# my_do_cmd mris_convert ../xhemi/surf/rh.white rh.xhemi.white.${ext_surf}
# my_do_cmd mris_convert -c lh.curv lh.sphere lh.${ext_data}; # careful, as mris_convert likes to write lh. or rh. before whatever output file name (unless it is alreadh ?h)
# my_do_cmd mris_convert -c ../xhemi/surf/rh.curv ../xhemi/surf/rh.sphere rh.xhemi.${ext_data}


# my_do_cmd $FSLDIR/bin/msm \
#   --inmesh=lh.sphere.${ext_surf} \
#   --refmesh=rh.sphere.${ext_surf} \
#   --indata=lh.${ext_data} \
#   --refdata=rh.${ext_data} \
#   --format=GIFTI \
#   --verbose \
#   --out=lh_to_rh


# my_do_cmd $FSLDIR/bin/msmapplywarp \
#   --inmesh=lh.white.${ext_surf} \
#   --refmesh=rh.white.${ext_surf} \
#   --warp=lh_to_rh_warp \
#   --out=lh_to_rh_anat




# inmesh=lh.sphere.${ext_surf}
# indata=lh.${ext_data}
# refmesh=rh.sphere.${ext_surf}
# refdata=rh.${ext_data}
# msmout=surf_msm_l2r

# my_do_cmd -fake $FSLDIR/bin/msm \
#   --inmesh=$inmesh \
#   --indata=$indata \
#   --refmesh=$refmesh \
#   --refdata=$refdata \
#   --format=GIFTI \
#   --verbose \
#   --out=$msmout
  

# my_do_cmd wb_command -surface-resample \
#   lh.white.${ext_surf} \
#   lh.sphere.${ext_surf} \
#   ${msmout}sphere.reg.surf.gii \
#   BARYCENTRIC \
#   out_l2r.white.surf.gii


# my_do_cmd ${FSLDIR}/bin/msmapplywarp \
#   surf_msm_l2rsphere.reg.surf.gii \
#   output_deformed_white.surf.gii \
#   -anat rh.sphere.surf.gii rh.white.surf.gii



# msmapplywarp \
#   input_mesh.sphere.reg.gii \
#   output_deformed_white.surf.gii \
#   -anat \
#   target_sphere.surf.gii \
#   target_white.surf.gii
