SUBJECTS_DIR = getenv('SUBJECTS_DIR');


f_subjects = [SUBJECTS_DIR '/templates/subjects_to_average.txt'];

metrics = {'fa','md','ad','rd',...
           'afd-par','afd-perp'};

subjects = readlines(f_subjects);
subjects = subjects(strlength(strtrim(subjects)) > 0);

lh_tsfs = containers.Map();
rh_tsfs = containers.Map();

for m = 1:numel(metrics)
    metric = metrics{m};
    lh_files = {};
    rh_files = {};

    for s = 1:numel(subjects)
        subj_dir = fullfile(SUBJECTS_DIR, subjects{s});

        lh_found = dir(fullfile(subj_dir, '**', ['lh_ico6_sym_' metric '.tsf']));
        rh_found = dir(fullfile(subj_dir, '**', ['rh_ico6_sym_' metric '.tsf']));

        for k = 1:numel(lh_found)
            lh_files{end+1} = fullfile(lh_found(k).folder, lh_found(k).name); %#ok<AGROW>
        end
        for k = 1:numel(rh_found)
            rh_files{end+1} = fullfile(rh_found(k).folder, rh_found(k).name); %#ok<AGROW>
        end
    end

    lh_tsfs(metric) = lh_files;
    rh_tsfs(metric) = rh_files;
end


% Average across subjects, per vertex/streamline and per depth point.
% Streamline lengths vary within and across subjects (cortical thickness),
% so each subject's data is NaN-padded to a common width before averaging
% with 'omitnan', which naturally accounts for the varying number of
% subjects contributing at each depth point.
lh_avg = containers.Map();
rh_avg = containers.Map();
lh_std = containers.Map();
rh_std = containers.Map();
lh_n   = containers.Map();
rh_n   = containers.Map();

out_dir = fullfile(SUBJECTS_DIR, 'templates', 'normative');
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end

for m = 1:numel(metrics)
    metric = metrics{m};
    fprintf(1,'  Averaging %s\n',metric);

    [lh_avg(metric), lh_std(metric), lh_n(metric)] = average_tsf_files(lh_tsfs(metric));
    [rh_avg(metric), rh_std(metric), rh_n(metric)] = average_tsf_files(rh_tsfs(metric));

    save_tsf_matrix(lh_avg(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_mean.tsf']));
    save_tsf_matrix(lh_std(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_std.tsf']));
    save_tsf_matrix(lh_n(metric),   fullfile(out_dir, ['lh_ico6_sym_' metric '_n.tsf']));

    save_tsf_matrix(rh_avg(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_mean.tsf']));
    save_tsf_matrix(rh_std(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_std.tsf']));
    save_tsf_matrix(rh_n(metric),   fullfile(out_dir, ['rh_ico6_sym_' metric '_n.tsf']));

    save_gifti_matrix(lh_avg(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_mean.func.gii']));
    save_gifti_matrix(lh_std(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_std.func.gii']));
    save_gifti_matrix(lh_n(metric),   fullfile(out_dir, ['lh_ico6_sym_' metric '_n.func.gii']));

    save_gifti_matrix(rh_avg(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_mean.func.gii']));
    save_gifti_matrix(rh_std(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_std.func.gii']));
    save_gifti_matrix(rh_n(metric),   fullfile(out_dir, ['rh_ico6_sym_' metric '_n.func.gii']));
end


function [M_avg, M_std, M_n] = average_tsf_files(tsf_files)
% Load one .tsf file per subject (same hemisphere/metric) and average
% them per-streamline, per-depth-point. Each tsf's data cell is converted
% to a matrix via cortical_cell2mat (NaN-padded to that subject's own
% longest streamline), then all subjects are stacked into a 3D array
% NaN-padded to the longest streamline across subjects, and averaged
% along the subject dimension with 'omitnan'.

nSubj = numel(tsf_files);
fprintf(1,'    (n=%d)\n',nSubj);

subj_mats = cell(1, nSubj);
maxLen = 0;

for s = 1:nSubj
    tsf = read_mrtrix_tsf(tsf_files{s});
    subj_mats{s} = cortical_cell2mat(tsf.data);
    fprintf(1,'  Loaded %s (%d streamlines)\n',tsf_files{s},length(tsf.data));
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


function save_tsf_matrix(M, filename)
% Write a NaN-padded (per-streamline, per-depth-point) matrix to a
% MRtrix .tsf file, trimming each row's trailing NaN padding back to
% that streamline's real length before writing.

tsf = struct();
tsf.data = trim_nan_padding(M);
write_mrtrix_tsf(tsf, filename);
fprintf(1,'    Wrote %s\n', filename);

end


function save_gifti_matrix(M, filename)
% Write an N x maxLen matrix (one row per vertex/streamline, one column
% per depth point) as a multi-map .func.gii, one map per depth point, so
% it can be viewed (e.g. as a time series) in fsleyes or wb_view.

g = gifti({M});
save(g, filename);
fprintf(1,'    Wrote %s\n', filename);

end


function data = trim_nan_padding(M)
% Convert an N x maxLen NaN-padded matrix (NaN padding only ever at the
% end of each row, per cortical_cell2mat's convention) back into a
% 1 x N cell array of column vectors with the padding removed.

nRows = size(M, 1);
data = cell(1, nRows);
for i = 1:nRows
    valid = find(~isnan(M(i, :)), 1, 'last');
    if isempty(valid)
        valid = 0;
    end
    data{i} = M(i, 1:valid).';
end

end

