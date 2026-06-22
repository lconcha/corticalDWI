function [M_avg, M_std, M_n] = cortical_average_tsf_files(tsf_files)
% function [M_avg, M_std, M_n] = cortical_average_tsf_files(tsf_files)
%
% Load one .tsf file per subject (same hemisphere/metric) and average them
% per-streamline, per-depth-point. Each tsf's data cell is converted to a
% matrix via cortical_cell2mat (NaN-padded to that subject's own longest
% streamline), then all subjects are stacked into a 3D array NaN-padded to
% the longest streamline across subjects, and averaged along the subject
% dimension with 'omitnan' — which naturally accounts for the varying
% number of subjects contributing at each depth point.

nSubj = numel(tsf_files);

subj_mats = cell(1, nSubj);
maxLen = 0;

for s = 1:nSubj
    tsf = read_mrtrix_tsf(tsf_files{s});
    subj_mats{s} = cortical_cell2mat(tsf.data);
    maxLen = max(maxLen, size(subj_mats{s}, 2));
end

nStreamlines = size(subj_mats{1}, 1);
stack = NaN(nStreamlines, maxLen, nSubj);

for s = 1:nSubj
    this_mat = subj_mats{s};
    stack(:, 1:size(this_mat, 2), s) = this_mat;
end

M_avg = mean(stack, 3, 'omitnan');
M_std = std(stack, 0, 3, 'omitnan');
M_n   = sum(~isnan(stack), 3);

end
