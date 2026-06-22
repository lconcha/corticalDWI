function cortical_save_gifti_matrix(M, filename)
% function cortical_save_gifti_matrix(M, filename)
%
% Write an N x maxLen matrix (one row per vertex/streamline, one column
% per depth point) as a multi-map .func.gii, one map per depth point, so
% it can be viewed (e.g. as a time series) in fsleyes or wb_view, or read
% back with cortical_load_gifti_matrix.

g = gifti({M});
fprintf(1,'Saving %s\n',filename)
save(g, filename);

end
