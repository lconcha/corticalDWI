

% f_fa  = '/datos/syphon/tmp/test_cortical/fa.nii.gz'
% f_tck = '/datos/syphon/tmp/test_cortical/lh_fsLR-32k_laplace-wm-streamlines_dwispace.tck'
% f_tck = '/datos/syphon/tmp/test_cortical/one.tck'
% f_prefix = '/datos/syphon/tmp/test_cortical/test'
% cortical_tckfixelsample(f_tck, f_fa, f_fa, f_fa, f_prefix)



mrtrixDir = '/home/inb/soporte/lanirem_software/mrtrix_3.0.4' 
addpath(fullfile(mrtrixDir,'matlab'))



dwidir = '/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma/sub-74277/dwi/';
f_tck  = fullfile(dwidir,'lh_fsLR-5k_laplace-wm-streamlines_dwispace.tck');
%f_tck  = fullfile(dwidir,'test.tck');
f_PDD = fullfile(dwidir,'mymrds_MRDS_Diff_BIC_PDDs_CARTESIAN.nii.gz');
f_nComp = fullfile(dwidir,'mymrds_MRDS_Diff_BIC_NUM_COMP.nii.gz');
f_MRDS_FA = fullfile(dwidir,'mymrds_MRDS_Diff_BIC_FA.nii.gz');
ff_values_in = {f_MRDS_FA};
f_prefix = fullfile(dwidir,'mytckfixelsampletest')
VALUES = cortical_tckfixelsample(f_tck, f_PDD, f_nComp, ff_values_in, f_prefix)