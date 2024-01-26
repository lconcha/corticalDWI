function VALUES = displasia_tckfixelsample(f_tck, f_PDD, f_nComp, ff_values_in, f_prefix)
% VALUES = displasia_tckfixelsample(f_tck, f_PDD, f_nComp, ff_values_in, f_prefix)
%
% f_tck         : Filename for the streamlines tck
% f_PDD         : Filename for the Principal Diffusion Directions file (MRDS, 4D).
% f_nComp       : Filename for the number of components (MRDS, 3D).
% ff_values_in  : Cell array of filenames of MRDS metrics to sample. 
%                 Each file should be MRDS, 4D.
% f_prefix      : Prefix for the output file names.
%
% Consider:
% addpath('/home/lconcha/software/mrtrix_matlab/matlab');
% addpath(genpath('/home/lconcha/software/dicm2nii-master'))
% addpath /home/lconcha/software/Displasias/
%
% __________________________________________________________________________________
% EXAMPLE:
% f_tck         = 'dwi/15/tck/dwi_l_out_resampled_native.tck';
% f_PDD         = 'dwi/dwi_MRDS_Diff_BIC_PDDs_CARTESIAN.nii.gz';
% f_MRDS_ncomp  = 'dwi/dwi_MRDS_Diff_BIC_NUM_COMP.nii.gz';
% f_MRDS_FA     = 'dwi/dwi_MRDS_Diff_BIC_FA.nii.gz';
% f_MRDS_MD     = 'dwi/dwi_MRDS_Diff_BIC_MD.nii.gz';
% ff_values     = {f_MRDS_FA, f_MRDS_MD};
% f_prefix      = '/tmp/prefix';
% 
% VALUES = displasia_tckfixelsample(f_tck, f_PDD, f_MRDS_ncomp, ff_values, f_prefix);
% __________________________________________________________________________________
%
% LU15 (0N(H4
% INB-UNAM
% Feb 2023
% lconcha@unam.mx


%% Load tck
tck_world = read_mrtrix_tracks(f_tck);
tmptck =  '/tmp/tmp.tck';
fprintf(1, '[INFO]  Converting tck to voxel coordinates.\n')
systemcommand = ['export LD_LIBRARY_PATH="";tckconvert -scanner2voxel ' f_nComp ' ' f_tck ' ' tmptck ' -force -quiet'];
fprintf(1,'  executing: %s\n',systemcommand);
fprintf('Loading %s\n',f_tck);
[status,result] = system(systemcommand);
tck = read_mrtrix_tracks(tmptck);
[status,result] = system(['rm -f ' tmptck]);



%% Load voxel data for PDD and nComp

fprintf('Loading %s\n',f_PDD);
PDD    = niftiread(f_PDD);
info = niftiinfo(f_PDD);
if ndims(PDD) ~= 4
    fprintf(1,'ERROR. %s does not have 4 dimensions. It should be a 4D volume with nvolumes = 3, 6, 9 or 12. Bye.\n',f_PDD);
    VALUES = [];
    return
end
fprintf('Loading %s\n',f_nComp);
nComp    = niftiread(f_nComp);
info = niftiinfo(f_nComp);
if ndims(nComp) ~= 3
    fprintf(1,'ERROR. %s should have three dimensions Bye.\n',f_nComp);
    VALUES = [];
    return
end



%% displasia-specific problem related to brkraw. Need to permute axes.
volume_is_permuted = false;
% if size(PDD,2) > size(PDD,3)
%   fprintf(1,'\n\n*****\nWoah, it seems like slices in the PDD file are in the third dimension. For displasia project they should be on the second dimension.\n');
%   tmpPDD = '/tmp/PDD.nii.gz';
%   systemcommand = ['mrconvert -axes 0,2,1,3 -strides 1,2,3,4 -quiet -force ' f_PDD ' ' tmpPDD];
%   fprintf(1,'  Run something like this and come back: %s\n',systemcommand);
%   VALUES = NaN;
%   error('Wrong dimensions')
% end


%% Prepare tsfs
%nFixels = size(PDD,4) ./ 3;
nFixels = 3; % forcing 3 pixels

tsf_par                         = tck_world;
tsf_perp                        = tck_world;
tsf_index_par                   = tck_world;
tsf_ncomp                       = tck_world;
tsf_dot_parallel2streamline     = tck_world;
tsf_dot_perp2slicenormal        = tck_world;
       


%% Identify parallel/perpendicular
fprintf(1,'Identifying par/perp... ')
for s = 1 : length(tck.data)
   if mod(s,10) == 0
        fprintf (1,'%d ',length(tck.data)-s);
   end
   this_streamline      = tck.data{s};
   this_index_par       = zeros(size(this_streamline,1),1);
   this_index_perp      = zeros(size(this_streamline,1),1);
   this_nComp           = zeros(size(this_streamline,1),1);
   this_dot_parallel2streamline = zeros(size(this_streamline,1),1);
   this_dot_perp2slicenormal    = zeros(size(this_streamline,1),1);

   Rxyz1 = this_streamline(1,:);
   origin = [0 0 0];
   Rxyz3 = this_streamline(end,:);

   PLANE = createPlane(normalizeVector3d(Rxyz1), origin ,normalizeVector3d(Rxyz3)); % create a plane centered at origin
   NORMAL = planeNormal(PLANE);


   for p = 1 : size(this_streamline,1);
       Axyz = this_streamline(p,:);
       if p == size(this_streamline,1)
        Bxyz = this_streamline(p-1,:);
       else
        Bxyz = this_streamline(p+1,:);
       end
       
       normSegment = (Axyz-Bxyz) ./ norm(Axyz-Bxyz);
%        vox_indices = [Axyz 1]  * inv(info.Transform.T);
%        vox_indices = vox_indices(1:3);
%        mindices    = vox_indices + 1;
%        matlab_indices = uint8(vox_indices + 1);
         mindices = Axyz +1;

       PDD1(1) =  interp3(PDD(:,:,:,1),mindices(2), mindices(1), mindices(3)); % I cannot get interpn to work, so I do this stupid thing.
       PDD1(2) =  interp3(PDD(:,:,:,2),mindices(2), mindices(1), mindices(3));
       PDD1(3) =  interp3(PDD(:,:,:,3),mindices(2), mindices(1), mindices(3));

       PDD2(1) =  interp3(PDD(:,:,:,4),mindices(2), mindices(1), mindices(3)); 
       PDD2(2) =  interp3(PDD(:,:,:,5),mindices(2), mindices(1), mindices(3));
       PDD2(3) =  interp3(PDD(:,:,:,6),mindices(2), mindices(1), mindices(3));

       PDD3(1) =  interp3(PDD(:,:,:,7),mindices(2), mindices(1), mindices(3)); 
       PDD3(2) =  interp3(PDD(:,:,:,8),mindices(2), mindices(1), mindices(3));
       PDD3(3) =  interp3(PDD(:,:,:,9),mindices(2), mindices(1), mindices(3));

       normPDD1= PDD1./norm(PDD1);
       normPDD2= PDD2./norm(PDD2);
       normPDD3= PDD3./norm(PDD3);
       normPDDs = [normPDD1;normPDD2;normPDD3];

       dots(1) = dot(normSegment,normPDD1);
       dots(2) = dot(normSegment,normPDD2);
       dots(3) = dot(normSegment,normPDD3);

       thisnComp = interp3(nComp,mindices(2), mindices(1), mindices(3), 'nearest');


       if thisnComp < 3
         dots(thisnComp+1:end) = NaN; % Remove PDDs if nCom does not support them.
       end

       if thisnComp > 1
           [themax,indexpar]  = max(abs(dots));       
           [themin,indexperp] = min(abs(dots));
       else
           [themax,indexpar]  = max(abs(dots));       
           themin             = NaN;
           indexperp          = 3;
       end

       thisnComp = interp3(nComp,mindices(2), mindices(1), mindices(3), 'nearest');

       
       this_index_par(p,1)  = indexpar;
       this_index_perp(p,1) = indexperp;
       this_nComp(p,1)      = thisnComp;

       % calculate the absolute dot products between:
       % Streamline to parallel tensor
       this_dot_parallel2streamline(p,1)  = abs(dots(indexpar));
       % Slice normal to perpendicular tensor
       if thisnComp > 1
        this_dot_perp2slicenormal(p,1)     = abs(dot(normPDDs(indexperp,:),NORMAL));
       else
        this_dot_perp2slicenormal(p,1) = -999; % cannot calculate this value if we only found one tensor. -999 is a placeholder for trash.
       end

       


   end
   try
    tsf_index_par.data{s}                 = this_index_par;
    tsf_index_perp.data{s}                = this_index_perp;
    tsf_ncomp.data{s}                     = this_nComp;
    tsf_dot_parallel2streamline.data{s}   = this_dot_parallel2streamline;
    tsf_dot_perp2slicenormal.data{s}      = this_dot_perp2slicenormal;
    VALUES.dot_parallel2streamline(s,:)   = this_dot_parallel2streamline;
    VALUES.dot_perp2slicenormal(s,:)      = this_dot_perp2slicenormal;
    VALUES.ncomp{s}                       = this_nComp;
   catch
    fprintf(1,'Hey!')
   end
end
fprintf (1,'\nFinished identifying par/perp\n',s);



%% Do the sampling
for i = 1 : length(ff_values_in)
    f_values_in = ff_values_in{i};
    fprintf('Loading %s ... ',f_values_in);
    V    = niftiread(f_values_in);
    fprintf(1,'\n');
    info      = niftiinfo(f_values_in);
    [fold,fname,ext] = fileparts(info.Filename);
    varName = strrep(fname,'.nii','');
    if ndims(V) ~= 4
        fprintf(1,'ERROR. %s does not have 4 dimensions. This script can only handle 4D. Bye.\n',f_values_in);
        VALUES = [];
        return
    end
    fprintf(1,'[INFO] Sampling %s \n', f_values_in)
    for s = 1 : length(tck.data)
       if mod(s,10) == 0
        fprintf (1,'%d ',length(tck.data)-s);
       end
       this_streamline = tck.data{s};
       this_data_par        = zeros(size(this_streamline,1),1);
       this_data_perp       = zeros(size(this_streamline,1),1);
       for p = 1 : size(this_streamline,1);
           xyz = this_streamline(p,:);
           
%            vox_indices = [xyz 1]  * inv(info.Transform.T);
%            vox_indices = vox_indices(1:3);
%            mindices    = vox_indices + 1;
%            matlab_indices = uint8(vox_indices + 1);
           mindices = xyz +1;

         
           %thisnComp = interp3(nComp,mindices(2), mindices(1), mindices(3), 'nearest');
           thisnComp  = tsf_ncomp.data{s}(p);
           indexpar   = tsf_index_par.data{s}(p);
           indexperp  = tsf_index_perp.data{s}(p);
    
           vals(1) = interp3(V(:,:,:,1),mindices(2), mindices(1), mindices(3));
           vals(2) = interp3(V(:,:,:,2),mindices(2), mindices(1), mindices(3));
           vals(3) = interp3(V(:,:,:,3),mindices(2), mindices(1), mindices(3));
    
           if thisnComp < 3
            vals(thisnComp+1:end) = -1; % remove values if nComp does not support them.
           end
    
           if max(vals) < 0 && thisnComp > 0
            fprintf(1,'WTF? All values are invalid!')
            fprintf(1,'Streamline %d, point %d\n',s,p);
            disp(vals)
           end
    
           val_par  = vals(indexpar);
           val_perp = vals(indexperp);
    
           this_data_par(p,1)  = val_par;
           this_data_perp(p,1) = val_perp;       
       end
       
       tsf_par.data{s}  = this_data_par;
       tsf_perp.data{s} = this_data_perp;

    end
    fprintf (1,'\nFinished sampling %s\n',fname);
    
    %%%%% write per-value tsf files
    f_tsf_par_out  = [f_prefix '_' varName '_par.tsf'];
    f_tsf_perp_out = [f_prefix '_' varName '_perp.tsf'];

    fprintf(1,'  [INFO] Writing tsf_par: %s\n',f_tsf_par_out);
    write_mrtrix_tsf(tsf_par,f_tsf_par_out);
    fprintf(1,'  [INFO] Writing tsf_perp: %s\n',f_tsf_perp_out);
    write_mrtrix_tsf(tsf_perp,f_tsf_perp_out);


 
    if regexp(varName,'^[0-9]')
       varName = ['x_' varName];
    end
    VALUES.par.(varName)  = tsf_par.data;
    VALUES.perp.(varName) = tsf_perp.data;
end


%%%%% writer overall tsf files
fprintf(1,'[INFO] Writing tsf files\n');
f_tsf_dot_parallel2streamline = [f_prefix '_dot_parallel2streamline.tsf'];
f_tsf_dot_perp2slicenormal    = [f_prefix '_dot_perp2slicenormal.tsf'];
f_tsf_ncomp                   = [f_prefix '_ncomp.tsf'];
fprintf(1,'  [INFO] Writing tsf_dot_parallel2streamline: %s\n',f_tsf_dot_parallel2streamline);
write_mrtrix_tsf(tsf_dot_parallel2streamline,f_tsf_dot_parallel2streamline);
fprintf(1,'  [INFO] Writing tsf_dot_perp2slicenormal: %s\n',f_tsf_dot_perp2slicenormal);
write_mrtrix_tsf(tsf_dot_perp2slicenormal,f_tsf_dot_perp2slicenormal);
fprintf(1,'  [INFO] Writing tsf_ncomp: %s\n',f_tsf_ncomp);
write_mrtrix_tsf(tsf_ncomp,f_tsf_ncomp);
f_tsf_par_index_out = [f_prefix '_par_index.tsf'];
fprintf(1,'  [INFO] Writing tsf_index_par: %s\n',f_tsf_par_index_out);
write_mrtrix_tsf(tsf_index_par,f_tsf_par_index_out)

fprintf(1,'[INFO] Writing text files\n');
varNames = fieldnames(VALUES.par);
for n = 1 : length(varNames)
  thisVarName = varNames{n};
  f_txt = [f_prefix '_' thisVarName '_par.txt'];
    thismat = cell2mat(VALUES.par.(thisVarName));
    fprintf(1,'  [INFO] Writing %s\n',f_txt);
    save(f_txt,'thismat','-ascii');
  f_txt = [f_prefix '_' thisVarName '_perp.txt'];
    thismat = cell2mat(VALUES.perp.(thisVarName));
    fprintf(1,'  [INFO] Writing %s\n',f_txt);
    save(f_txt,'thismat','-ascii');   
end
f_txt = [f_prefix '_dot_parallel2streamline.txt'];
    thismat = VALUES.dot_parallel2streamline;
    fprintf(1,'  [INFO] Writing %s\n',f_txt);
    save(f_txt,'thismat','-ascii');   
f_txt = [f_prefix '_dot_perp2slicenormal.txt'];
    thismat = VALUES.dot_perp2slicenormal;
    fprintf(1,'  [INFO] Writing %s\n',f_txt);
    save(f_txt,'thismat','-ascii');   
f_txt = [f_prefix '_nComp.txt'];
    thismat = cell2mat(VALUES.ncomp);
    fprintf(1,'  [INFO] Writing %s\n',f_txt);
    save(f_txt,'thismat','-ascii'); 
   
