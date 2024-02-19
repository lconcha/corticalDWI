function VALUES = cortical_par-perp_sample(f_tck,f_fixeldir)




afd_tsf_base = '/misc/lauterbur/lconcha/TMP/test_fixels/afd_';
f_tsf_out    = '/misc/lauterbur/lconcha/TMP/test_fixels/afd_par.tsf';
TSFS = cell(8,1);
for t = 0:8
  this_ftsf = [afd_tsf_base num2str(t) '.tsf']
  this_tsf  = read_mrtrix_tsf(this_ftsf);
  TSFS{t+1} = this_tsf;
end
f_afd4d = '/misc/lauterbur/lconcha/TMP/test_fixels/allafds.mif';
AFD4D = read_mrtrix (f_afd4d);
f_tsffixelindices = '/misc/lauterbur/lconcha/TMP/test_fixels/lh2.tsf';
fixelIndices = read_mrtrix_tsf(f_tsffixelindices);
fixelValues = fixelIndices; % copy
for s = 1 : length(fixelIndices.data)
  this_indices = fixelIndices.data{s};
  this_indices = this_indices +1; %matlab offset
  this_afds = [TSFS{1}.data{s} TSFS{2}.data{s} TSFS{3}.data{s} TSFS{4}.data{s} TSFS{5}.data{s} TSFS{6}.data{s} TSFS{7}.data{s} TSFS{8}.data{s} TSFS{9}.data{s}];
  this_afd = zeros(size(this_indices));
  for c = 1 : 9
    this_afd(this_indices==c) = this_afds(this_indices==c,c);
  end
  fixelValues.data{s} = this_afd;
end
write_mrtrix_tsf (fixelValues, f_tsf_out);