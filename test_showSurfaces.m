
addpath(genpath('/misc/lauterbur/lconcha/code/BrainStat/brainstat_matlab'));
addpath(genpath('/misc/lauterbur/lconcha/code/gifti'));
addpath(genpath('/home/inb/soporte/lanirem_software/mrtrix_3.0.4/matlab'));
addpath(genpath('/misc/lauterbur/lconcha/code/corticalDWI'));


SUBJECTS_DIR = '/misc/lauterbur2/lconcha/Edmonton/fs_edmonton';
subjID = 'sub-Mcd004';

f        = fullfile(SUBJECTS_DIR,subjID,'surf/l2r.white.fsLR32k.surf.gii');
l2r_pre  = read_surface(f); 
f        = fullfile(SUBJECTS_DIR,subjID,'surf/l2r.white_deformed.surf.gii');
l2r_post = read_surface(f); 

nVerts = length(l2r_pre.vertices);
indices = 1:1:nVerts;
subplot(1,3,1);
    s = l2r_pre;
    srf = trisurf(s.faces , ...
            s.vertices(:,1), ...
            s.vertices(:,2), ...
            s.vertices(:,3), ...
            indices, ...
            'EdgeColor', 'flat',...
            'FaceColor', 'flat');
            axis vis3d; view(90,0)
            ax = gca;
            ax.Clipping = "off";
            title('left2right preMSM')
subplot(1,3,2);
    s = l2r_post;
    srf = trisurf(s.faces , ...
            s.vertices(:,1), ...
            s.vertices(:,2), ...
            s.vertices(:,3), ...
            indices, ...
            'EdgeColor', 'flat',...
            'FaceColor', 'flat');
            axis vis3d; view(90,0)
            ax = gca;
            ax.Clipping = "off";
            title('left2right postMSM')
subplot(1,3,3)
    skip = 20;
    for v = 1:skip:nVerts
      xyz1 = l2r_pre.vertices(v,:);
      xyz2 = l2r_post.vertices(v,:);
      XYZ  = [xyz1;xyz2];
      h_line(v) = plot3(XYZ(:,1),XYZ(:,2),XYZ(:,3),'- b','MarkerSize',6); hold on
    end
    axis vis3d; view(90,0)
    ax = gca;
    hold off;
    title('Deformation')


% f_rh_sphere = fullfile(SUBJECTS_DIR,subjID,'surf/rh.sphere.fsLR32k.surf.gii');
% rh_sphere   = read_surface(f_rh_sphere);
% f_sphere_reg = fullfile(SUBJECTS_DIR,subjID,'surf/l2r_msm_fromComputed.sphere.reg.surf.gii');
% rh_reg       = read_surface(f_sphere_reg);
% 
% 
% h_rh  = plot3(rh_sphere.vertices(:,1),rh_sphere.vertices(:,2),rh_sphere.vertices(:,3),' .k');
% hold on
% h_reg = plot3(rh_reg.vertices(:,1),rh_reg.vertices(:,2),rh_reg.vertices(:,3),' .r');
% 
% skip=2;
% nVerts = length(rh_reg.vertices);
% for v = 1:skip:nVerts
%   xyz1 = rh_sphere.vertices(v,:);
%   xyz2 = rh_reg.vertices(v,:);
%   XYZ  = [xyz1;xyz2];
%   h_line(v) = plot3(XYZ(:,1),XYZ(:,2),XYZ(:,3),'- b','MarkerSize',6);
% end
% hold off


% 
% s   = read_surface(surfgeom);
% tck = read_mrtrix_tracks(cortical_streamlines);
% 
% 
% 
% 
% data = s.vertices(:,1);
% data = rand(size(data));
% 
% srf = trisurf(s.faces , ...
%             s.vertices(:,1), ...
%             s.vertices(:,2), ...
%             s.vertices(:,3), ...
%             data, ...
%             'EdgeColor', 'interp',...
%             'FaceColor', 'interp');
% material dull; lighting phong;
% 
% clim = [min(data) max(data)];
% colormap(parula(256));
% set(gca                                 , ...
%     'Visible'           , 'off'         , ...
%     'DataAspectRatio'   , [1 1 1]       , ...
%     'PlotBoxAspectRatio', [1 1 1]       , ...
%     'CLim'              , clim          );
% 
% % Add a camlight.
% cam = camlight();
% 
% 
% % Create subsurfaces
% nv = length(tck.data);
% x = zeros(length(data),1); y=x; z=x;
% for d = 1 : 30
%     for v = 1 : nv
%         try
%             x(v) = tck.data{v}(d,1);
%             y(v) = tck.data{v}(d,2);
%             z(v) = tck.data{v}(d,3);
%             if v == 1
%                 fprintf(1,'Depth %d vertex %d : [%1.2f %1.2f %1.2f]\n',d,v,x(v),y(v),z(v));
%             end
%         catch
%             fprintf(1,'  Vertex %d only has %d depths\n',v,length(tck.data{v}));
%             x(v) = tck.data{v}(end,1);
%             y(v) = tck.data{v}(end,2);
%             z(v) = tck.data{v}(end,3);
%         end
%     end
%    %thissrf = trisurf(s.faces,x,y,z,ones(size(data)));
%    this_s.tri       = s.faces;
%    this_s.coord     = [x y z]';
%    [fold,fname,ext] = fileparts(surfgeom);
%    fnamemod         = ['test_' num2str(d,'%02d') '_' fname];
%    this_s_fname = fullfile(fold,fnamemod);
%    fprintf(1,'Saving %s\n',this_s_fname);
%    mx = io_utils.SurfStatWriteSurf1( this_s_fname, this_s, 'b'  );
% 
% end
% 
% 
% f_rh_surfgeom   = fullfile(SUBJECTS_DIR,subjID,'surf/rh_pial_fsLR-32k.surf.gii');
% f_lh_surfgeom   = fullfile(SUBJECTS_DIR,subjID,'surf/lh_pial_fsLR-32k.surf.gii');
% f_rh_data      = fullfile(SUBJECTS_DIR,subjID,'dwi/csd_fixels/rh_fsLR-32k_afd-par.txt');
% f_lh_data      = fullfile(SUBJECTS_DIR,subjID,'dwi/csd_fixels/lh_fsLR-32k_afd-par.txt');
% rh_data        = load(f_rh_data);
% lh_data        = load(f_lh_data);
% 
% SURF           = read_surface({f_lh_surfgeom,f_rh_surfgeom});
% %R = rh_data(:,1);
% %L = lh_data(:,1);
% DATA           = [lh_data;rh_data];
% DATA(DATA==-1) = NaN; % replace the -1 error codes for NaNs.
% 
% depthsToShow = round(linspace(1,size(DATA,2),5));
% labels_depth = {};
% tck_step_size = 0.5;
% for d = 1 : length(depthsToShow)
%   labels_depth{d} = [num2str( (depthsToShow(d)-1) .* tck_step_size) ' mm'];
% end
% obj = plot_hemispheres(DATA(:,depthsToShow),SURF,'labeltext',labels_depth);
% obj.colorlimits([0 1])
% 
% 
% 
% 
% sR   = read_surface(surfgeom);
% f_dataXdepth = fullfile(SUBJECTS_DIR,subjID,'dwi/csd_fixels/rh_fsLR-32k_afd-par.txt'); 
% dataXdepth   = load(f_dataXdepth);
% 
% 
% s = SURF{1};
% data = ones(size(s.vertices,1),1);
% 
% 
% % Create subsurfaces
% nv = length(tck.data);
% x = zeros(length(data),1); y=x; z=x;
% maxdepth = 20;
% XYZD = zeros(nv,3,maxdepth);
% for d = 1 : maxdepth
%     for v = 1 : nv
%         try
%             x(v) = tck.data{v}(d,1);
%             y(v) = tck.data{v}(d,2);
%             z(v) = tck.data{v}(d,3);
%             %if v == 1
%             %    fprintf(1,'Depth %d vertex %d : [%1.2f %1.2f %1.2f]\n',d,v,x(v),y(v),z(v));
%             %end
%         catch
%             %fprintf(1,'  Vertex %d only has %d depths\n',v,length(tck.data{v}));
%             x(v) = tck.data{v}(end,1);
%             y(v) = tck.data{v}(end,2);
%             z(v) = tck.data{v}(end,3);
%         end
% 
%     end
%     XYZD(:,:,d) = [x y z];
% end
% 
% 
% % show surface and peels
% srf = trisurf(s.faces , ...
%             s.vertices(:,1), ...
%             s.vertices(:,2), ...
%             s.vertices(:,3), ...
%             data, ...
%             'EdgeColor', 'interp',...
%             'EdgeAlpha', 0,...
%             'FaceColor', 'interp');
% material dull; lighting phong;
% set(gca                                 , ...
%     'Visible'           , 'off'         , ...
%     'DataAspectRatio'   , [1 1 1]       , ...
%     'PlotBoxAspectRatio', [1 1 1]       , ...
%     'CLim'              , clim          );
% % Add a camlight.
% cam = camlight();
% axis vis3d
% ax = gca;
% ax.Clipping = "off";
% 
% 
% dirout = '/misc/lauterbur2/lconcha/Edmonton/forMovie'
% view(90,0); % sag
% for d = 1 : maxdepth
%   srf.Vertices = XYZD(:,:,d);
%   drawnow
%   fout = fullfile(dirout,['sag_' num2str(d,'%04.0f') '.png']);
%   saveas(gca,fout);
% end
% view(180,0) % cor
% for d = 1 : maxdepth
%   srf.Vertices = XYZD(:,:,d);
%   drawnow
%     fout = fullfile(dirout,['cor_' num2str(d,'%04.0f') '.png']);
%   saveas(gca,fout);
% end
% view(-90,0) % medial
% for d = 1 : maxdepth
%   srf.Vertices = XYZD(:,:,d);
%   drawnow
%   fout = fullfile(dirout,['med_' num2str(d,'%04.0f') '.png']);
%   saveas(gca,fout);
% end
% view (0,90) % axial
% for d = 1 : maxdepth
%   srf.Vertices = XYZD(:,:,d);
%   drawnow
%   fout = fullfile(dirout,['ax_' num2str(d,'%04.0f') '.png']);
%   saveas(gca,fout);
% end
% 
% 
% 
% % plot interactively
% dataStructure.DATA = dataXdepth;
% dataStructure.step_size = 0.5;
% dataStructure.metric_name = 'AFD';
% inb_show_surface(s,dataStructure)
