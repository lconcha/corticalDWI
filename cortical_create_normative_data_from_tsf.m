function [lh_M, rh_M] = cortical_create_normative_data_from_tsf()

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
    lh_tsfs(metric) = cortical_find_subject_files(SUBJECTS_DIR, subjects, ['lh_ico6_sym_' metric '.tsf']);
    rh_tsfs(metric) = cortical_find_subject_files(SUBJECTS_DIR, subjects, ['rh_ico6_sym_' metric '.tsf']);
end

% Figure out the number of vertices so and build a large
% multidimensional matrix
dummyvar = lh_tsfs(metrics{1});
onetsf   = dummyvar{1};
dummytsf = read_mrtrix_tsf(onetsf);
nVerts   = size(dummytsf.data,2);
nMetrics = length(metrics);
dummyMat = cortical_cell2mat(dummytsf.data);
nDepths  = size(dummyMat,2) .* 2; % pad it twice as large, as other subjects may have deeper streamlines.
nSubjects= length(lh_tsfs(metrics{1}));
lh_M        = nan(nVerts,nDepths,nSubjects,nMetrics);
rh_M        = nan(nVerts,nDepths,nSubjects,nMetrics);

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

% Also save the full stack for each metric so we can build a
% multidimensional array
lh_stack = containers.Map();
rh_stack = containers.Map();

out_dir = fullfile(SUBJECTS_DIR, 'templates', 'normative');
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end

for m = 1:numel(metrics)
    metric = metrics{m};
    fprintf(1,'  Averaging %s (LH n=%d, RH n=%d)\n', metric, ...
        numel(lh_tsfs(metric)), numel(rh_tsfs(metric)));

    [lh_avg(metric), lh_std(metric), lh_n(metric), lh_stack(metric)] = cortical_average_tsf_files(lh_tsfs(metric));
    [rh_avg(metric), rh_std(metric), rh_n(metric), rh_stack(metric)] = cortical_average_tsf_files(rh_tsfs(metric));

    l_nDepths     = size(lh_stack(metric),2);
    r_nDepths     = size(rh_stack(metric),2);
    lh_M(:,1:l_nDepths,:,m) = lh_stack(metric);
    rh_M(:,1:r_nDepths ,:,m) = rh_stack(metric);

    save_tsf_matrix(lh_avg(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_mean.tsf']));
    save_tsf_matrix(lh_std(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_std.tsf']));
    save_tsf_matrix(lh_n(metric),   fullfile(out_dir, ['lh_ico6_sym_' metric '_n.tsf']));

    save_tsf_matrix(rh_avg(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_mean.tsf']));
    save_tsf_matrix(rh_std(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_std.tsf']));
    save_tsf_matrix(rh_n(metric),   fullfile(out_dir, ['rh_ico6_sym_' metric '_n.tsf']));

    cortical_save_gifti_matrix(lh_avg(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_mean.func.gii']));
    cortical_save_gifti_matrix(lh_std(metric), fullfile(out_dir, ['lh_ico6_sym_' metric '_std.func.gii']));
    cortical_save_gifti_matrix(lh_n(metric),   fullfile(out_dir, ['lh_ico6_sym_' metric '_n.func.gii']));

    cortical_save_gifti_matrix(rh_avg(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_mean.func.gii']));
    cortical_save_gifti_matrix(rh_std(metric), fullfile(out_dir, ['rh_ico6_sym_' metric '_std.func.gii']));
    cortical_save_gifti_matrix(rh_n(metric),   fullfile(out_dir, ['rh_ico6_sym_' metric '_n.func.gii']));
end


% remove the extra Nans at the end of second dimension in the large
% multidimensional matrices
lh_toRemove = sum(isnan(lh_M(:,:,1,1))) == nVerts;
lh_M(:,lh_toRemove,:,:) = [];
rh_toRemove = sum(isnan(rh_M(:,:,1,1))) == nVerts;
rh_M(:,rh_toRemove,:,:) = [];

fprintf(1,'Sizes of lh_M and rh_M:\n')
fprintf(1,'lh_M: %s\n', mat2str(size(lh_M)));
fprintf(1,'rh_M: %s\n', mat2str(size(rh_M)));


% save a .mat file for easier data handling of multivariate data
mat_fname = fullfile(out_dir, ['multivariate.mat']);
fprintf(1,'Saving multivariate mat file: %s\n',mat_fname);
save(mat_fname,'lh_M','rh_M','metrics','subjects');


function save_tsf_matrix(M, filename)
% Write a NaN-padded (per-streamline, per-depth-point) matrix to a
% MRtrix .tsf file, trimming each row's trailing NaN padding back to
% that streamline's real length before writing.

tsf = struct();
tsf.data = trim_nan_padding(M);
write_mrtrix_tsf(tsf, filename);
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

end% function