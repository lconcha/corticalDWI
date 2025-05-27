function srf = inb_show_surface(s,dataStructure)
% DATA = dataStructure.DATA;
% step_size = dataStructure.step_size;
% metric_name = dataStructure.metric_name;


fh = figure;


subplot(121);
data1 = ones(length(dataStructure.DATA),1);
srf = trisurf(s.faces , ...
            s.vertices(:,1), ...
            s.vertices(:,2), ...
            s.vertices(:,3), ...
            data1, ...
            'EdgeColor', 'interp',...
            'EdgeAlpha', 0,...
            'FaceColor', 'interp');
material dull;lighting phong;
set(gca                                 , ...
    'Visible'           , 'off'         , ...
    'DataAspectRatio'   , [1 1 1]       , ...
    'PlotBoxAspectRatio', [1 1 1]       , ...
    'CLim'              , clim          );
% Add a camlight.
cam = camlight('headlight');
axis vis3d
view(-90,0)
ax_surf = gca;
ax_surf.Clipping = "off";
hold(ax_surf,'on');
my_dot = scatter3(0,0,0,'red','filled','Parent',ax_surf); hold on;


ax_plot = subplot(122);
get_vertex_index(srf,dataStructure,ax_surf,ax_plot)


