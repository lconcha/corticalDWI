function lastVertexIndex = get_vertex_index(h,dataStructure,ax_surf,ax_plot)

DATA = dataStructure.DATA;
step_size = dataStructure.step_size;
metric_name = dataStructure.metric_name;




% make interactive
h.ButtonDownFcn = @(src, event) getVertexIndex(src, event,DATA,ax_surf,ax_plot);

  % function p = getVertexIndex(src,event,X,Y,Z,DATA,ax)
  function p = getVertexIndex(src,event,DATA,ax_surf,ax_plot)




        % Get the clicked point in axes coordinates
        clickedPoint = event.IntersectionPoint;
        
        % Reshape X, Y, Z into vectors for easier processing
        vertices = src.Vertices;
        

        % Compute the Euclidean distance to all vertices
        distances = vecnorm(vertices - clickedPoint, 2, 2);
        
        % Find the index of the closest vertex
        [mindist, p] = min(distances);
        
        % Display the vertex index
        %fprintf('Closest vertex index: %d (distance: %1.2f)\n' , p,mindist);
        ax_surf.Children(1).XData = vertices(p,1);
        ax_surf.Children(1).YData = vertices(p,2);
        ax_surf.Children(1).ZData = vertices(p,3);

       
        this_data = DATA(p,:);
        %h_plot = figure;
        depths = [0:size(this_data,2)-1] .* step_size;
        hp = plot(depths,this_data,'Parent',ax_plot);
        hold on;
        the_title = sprintf('Closest vertex: %d (distance: %1.2f mm)' , p,mindist);
        ax_plot.Title.String = the_title;
        ax_plot.YLabel.String = metric_name;
        ax_plot.XLabel.String = 'Depth from pial surface (mm)';
        ax_plot.YLabel.Interpreter = 'none';

        
        

    end
end