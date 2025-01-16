function tsf2txt(f_tsf,nDepths,f_txt)
% function tsf2txt(f_tsf,nDepths,f_txt)

fprintf(1,'Will convert tsf to txt ...\n');

% add matlab libraries for mrtrix
[status,location] = system('which mrcalc');
mrtrix_dir = fileparts(fileparts(location));
mtrix_matlab_dir = [mrtrix_dir '/matlab'];
addpath(genpath(mtrix_matlab_dir));


%f_tsf = 'csd_fixels/rh_fsLR-5k_afd-par.tsf';
%nDepths = 20;
%f_txt   = 'blah.txt';

tsf = read_mrtrix_tsf(f_tsf);

nStreamlines = length(tsf.data);
M = zeros(nStreamlines,nDepths);
for s = 1 : nStreamlines
  d = tsf.data{s}';
  if length(d) < nDepths
      d(end+1:nDepths) = -1;
  end
  M(s,:) = d(1:nDepths);
end



writematrix(M,f_txt,'Delimiter','space');
fprintf(1,'Done.\n');