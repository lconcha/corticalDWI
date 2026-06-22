function files = cortical_find_subject_files(SUBJECTS_DIR, subjects, filename)
% function files = cortical_find_subject_files(SUBJECTS_DIR, subjects, filename)
%
% Recursively searches each subject's directory under SUBJECTS_DIR for a
% file with the given exact basename (e.g. 'lh_ico6_sym_fa.tsf'), since the
% file may live directly under dwi/ or inside a fixel subdirectory
% depending on the metric. Returns a cell array of full paths, one per
% subject where the file was found (subjects missing the file are skipped).

files = {};
for s = 1:numel(subjects)
    subj_dir = fullfile(SUBJECTS_DIR, subjects{s});
    found = dir(fullfile(subj_dir, '**', filename));
    for k = 1:numel(found)
        files{end+1} = fullfile(found(k).folder, found(k).name); %#ok<AGROW>
    end
end
end
