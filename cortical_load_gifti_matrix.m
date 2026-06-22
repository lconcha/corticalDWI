function M = cortical_load_gifti_matrix(filename)
% function M = cortical_load_gifti_matrix(filename)
%
% Read a multi-map .func.gii (as written by cortical_save_gifti_matrix)
% back into an N x maxLen numeric matrix. Returns [] if the file doesn't
% exist.

M = [];
if ~isfile(filename), return; end
g = gifti(filename);
M = double(g.cdata);

end
