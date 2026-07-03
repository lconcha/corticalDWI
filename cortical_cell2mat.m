function M = cortical_cell2mat(C, varargin)
% M = cortical_cell2mat(C)
% M = cortical_cell2mat(C, 'MaskInvalid', true)
%
% Converts a cell array of row vectors to a padded matrix (NaN fill).
% With 'MaskInvalid', true, values of -1 are replaced with NaN (used to
% mark missing data in MRtrix TSF files).

p = inputParser;
p.addParameter('MaskInvalid', false, @islogical);
p.parse(varargin{:});

maxLen = max(cellfun(@numel, C));
M = cell2mat(cellfun(@(x) [x(:).', NaN(1, maxLen - numel(x))], C(:), ...
    'UniformOutput', false));

if p.Results.MaskInvalid
    M(M == -1) = NaN;
end
