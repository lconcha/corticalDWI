function nifti = cortical_readnifti(f)

info = niftiinfo(f);
nDims = length(info.ImageSize);


switch nDims
  case 3
    strides = ' -strides 1,2,3 ';
  case 4
    strides = ' -strides 1,2,3,4 ';
  otherwise
    fprintf(1,'ERROR. Can only handle 3 or 4 dimensions')
    nifti = NaN;
    return
end


fprintf('Loading %s\n',f);

% Fix strides
tmpnifti =  ['/tmp/tempnifti_' num2str(rand) '.nii'];

systemcommand = ['export LD_LIBRARY_PATH="";mrconvert' strides f ' ' tmpnifti];
fprintf(1,'  executing: %s\n',systemcommand);
[status,result] = system(systemcommand);


nifti    = niftiread(tmpnifti);

systemcommand = ['rm -f ' tmpnifti];
fprintf(1,'  executing: %s\n',systemcommand);
[status,result] = system(systemcommand);


fprintf(1,'  Finished loading with correct strides\n');

