function lastVertexIndex = get_vertex_index(h,DATA,ax_surf,ax_plot)


% Function to update the shared variable


% make interactive
%h.ButtonDownFcn = @(src, event) getVertexIndex(src, event, h.Vertices(:,1), h.Vertices(:,2), h.Vertices(:,3),DATA,ax);
h.ButtonDownFcn = @(src, event) getVertexIndex(src, event,DATA,ax_surf,ax_plot);

  % function p = getVertexIndex(src,event,X,Y,Z,DATA,ax)
  function p = getVertexIndex(src,event,DATA,ax_surf,ax_plot)




        % Get the clicked point in axes coordinates
        clickedPoint = event.IntersectionPoint;
        
        % Reshape X, Y, Z into vectors for easier processing
        %vertices = [X(:), Y(:), Z(:)];
        vertices = src.Vertices;
        

        % Compute the Euclidean distance to all vertices
        distances = vecnorm(vertices - clickedPoint, 2, 2);
        
        % Find the index of the closest vertex
        [mindist, p] = min(distances);
        
        % Display the vertex index
        fprintf('Closest vertex index: %d (distance: %1.2f)\n' , p,mindist);
        %hb = plot3(vertices(p,1),vertices(p,2),vertices(p,3), ' or','Parent',ax_surf);
        %hb.XData = vertices(p,1);
        %hb.YData = vertices(p,2);
        %hb.ZData = vertices(p,3);
        ax_surf.Children(1).XData = vertices(p,1);
        ax_surf.Children(1).YData = vertices(p,2);
        ax_surf.Children(1).ZData = vertices(p,3);

       
        this_data = DATA(p,:);
        %h_plot = figure;
        hp = plot(this_data,'Parent',ax_plot);
        hold on;
        the_title = sprintf('Closest vertex index: %d (distance: %1.2f)' , p,mindist);
        htit = title(the_title,'Parent',ax_plot);
        htit.String = the_title;
        
        

    end
end