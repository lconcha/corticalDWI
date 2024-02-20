
mrtrixDir = '/home/inb/soporte/lanirem_software/mrtrix_3.0.4' ;
addpath(fullfile(mrtrixDir,'matlab'))

SUBJECTS_DIR = getenv("SUBJECTS_DIR");
sID          = 'sub-26651';
hemi         = 'lh';
surf_type    = 'fsLR-5k';


f_tsf_parIndices = [SUBJECTS_DIR '/' sID '/dwi/' hemi '_' surf_type '_laplace-wm-streamlines_dwispace_parIndices_mrds.tsf']
parIndices_tsf = read_mrtrix_tsf(f_tsf_parIndices);

for t = 0:2
  this_f_tsf = [SUBJECTS_DIR '/' sID '/dwi/mrds_fixels/' sID '_MRDS_Diff_BIC_FA_' num2str(t) '.tsf'];
  this_tsf = read_mrtrix_tsf(this_f_tsf);
  FA_tsf{t+1} = this_tsf;

  this_f_tsf = [SUBJECTS_DIR '/' sID '/dwi/mrds_fixels/' sID '_MRDS_Diff_BIC_MD_' num2str(t) '.tsf'];
  this_tsf = read_mrtrix_tsf(this_f_tsf);
  MD_tsf{t+1} = this_tsf;
  
  this_f_tsf = [SUBJECTS_DIR '/' sID '/dwi/mrds_fixels/' sID '_MRDS_Diff_BIC_COMP_SIZE_' num2str(t) '.tsf'];
  this_tsf = read_mrtrix_tsf(this_f_tsf);
  COMPSIZE_tsf{t+1} = this_tsf;
end

for s = 1 : length(parIndices_tsf.data)
  this_parIndex = parIndices_tsf.data{s};
  this_parIndex = this_parIndex +1; % fix matlab offset
  this_FA3 = [FA_tsf{1}.data{s} FA_tsf{2}.data{s} FA_tsf{3}.data{s}];
  this_MD3 = [MD_tsf{1}.data{s} MD_tsf{2}.data{s} MD_tsf{3}.data{s}];
  for p = 1 : length(this_parIndex)
      this_FA_par(p) = this_FA3(p,this_parIndex(p));
      this_MD_par(p) = this_MD3(p,this_parIndex(p));
  end
end



%VALUES = cortical_tckfixelsample(f_tck, f_PDD, f_nComp, ff_values_in, f_prefix)