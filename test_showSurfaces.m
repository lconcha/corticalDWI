
addpath(genpath('/misc/lauterbur/lconcha/code/BrainStat/brainstat_matlab'));
addpath(genpath('/misc/lauterbur/lconcha/code/gifti'));
addpath(genpath('/home/inb/soporte/lanirem_software/mrtrix_3.0.4/matlab'));


SUBJECTS_DIR = '/misc/lauterbur/lconcha/TMP/glaucoma/fs_glaucoma';
subjID = 'sub-74277';

surfgeom = fullfile(SUBJECTS_DIR,subjID,'surf/rh_pial_fsLR-32k.surf.gii');
cortical_streamlines = fullfile(SUBJECTS_DIR,subjID,'mri/rh_fsLR-32k_laplace-wm-streamlines.tck');

s   = read_surface(surfgeom);
tck = read_mrtrix_tracks(cortical_streamlines);


 
 
data = s.vertices(:,1);
data = rand(size(data));

srf = trisurf(s.faces , ...
            s.vertices(:,1), ...
            s.vertices(:,2), ...
            s.vertices(:,3), ...
            data, ...
            'EdgeColor', 'interp',...
            'FaceColor', 'interp');
material dull; lighting phong;

clim = [min(data) max(data)];
colormap(parula(256));
set(gca                                 , ...
    'Visible'           , 'off'         , ...
    'DataAspectRatio'   , [1 1 1]       , ...
    'PlotBoxAspectRatio', [1 1 1]       , ...
    'CLim'              , clim          );

% Add a camlight.
cam = camlight();


nv = length(tck.data);
x = zeros(length(data),1); y=x; z=x;
for d = 1 : 30
    for v = 1 : nv
        try
            x(v) = tck.data{v}(d,1);
            y(v) = tck.data{v}(d,2);
            z(v) = tck.data{v}(d,3);
            if v == 1
                fprintf(1,'Depth %d vertex %d : [%1.2f %1.2f %1.2f]\n',d,v,x(v),y(v),z(v));
            end
        catch
            fprintf(1,'  Vertex %d only has %d depths\n',v,length(tck.data{v}));
            x(v) = tck.data{v}(end,1);
            y(v) = tck.data{v}(end,2);
            z(v) = tck.data{v}(end,3);
        end
    end
   %thissrf = trisurf(s.faces,x,y,z,ones(size(data)));
   this_s.tri       = s.faces;
   this_s.coord     = [x y z]';
   [fold,fname,ext] = fileparts(surfgeom);
   fnamemod         = ['test_' num2str(d,'%02d') '_' fname];
   this_s_fname = fullfile(fold,fnamemod);
   fprintf(1,'Saving %s\n',this_s_fname);
   mx = io_utils.SurfStatWriteSurf1( this_s_fname, this_s, 'b'  );

end
