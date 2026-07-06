function cortical_matlab_setup()
% Add toolbox paths needed by cortical_browser_2.

if ~exist('cortical_browser_2_config.m','file')
    error('cortical_browser_2_config.m not found. Copy default config or run setup.');
end
cfg = cortical_browser_2_config();

genpath_filtered(cfg.brainstat);
genpath_filtered(cfg.gifti);
genpath_filtered(cfg.mrtrix);
genpath_filtered(cfg.corticalDWI);
genpath_filtered(cfg.cbrewer);
end % function


function tf = isOnPath(folder)
    folder = char(folder);
    % Normalize trailing separator for reliable comparison
    if folder(end) == filesep
        folder(end) = [];
    end
    pathCell = strsplit(path, pathsep);
    if ispc  % Windows paths are case-insensitive
        tf = any(strcmpi(folder, pathCell));
    else
        tf = any(strcmp(folder, pathCell));
    end
end


function p = genpath_filtered(root, excludePatterns)
if nargin<2
    excludePatterns = {'.git', '.github', 'node_modules'};
end
if isOnPath(root)
    fprintf(1, 'Folder already in path: %s\n', root);
    return
end
fprintf(1,'Adding to path: %s\n',root);
allp = genpath(root);
folders = strsplit(allp, pathsep);
keep = true(size(folders));
for k = 1:numel(folders)
    f = folders{k};
    if isempty(f), keep(k)=false; continue; end
    for e = excludePatterns
        if contains(f, e{1})
            keep(k) = false;
            break
        end
    end
end
folders = folders(keep);
if isempty(folders)
    p = '';
else
    p = strjoin(folders, pathsep);
    addpath(p);
end
end

