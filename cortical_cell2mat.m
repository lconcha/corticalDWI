function M = cortical_cell2mat(C)
% function M = cortical_cell2mat(C)


maxLen = max(cellfun(@numel, C));
M = cell2mat(cellfun(@(x) [x(:).', NaN(1, maxLen - numel(x))], C(:), ...
    'UniformOutput', false));
