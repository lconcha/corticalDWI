function cortical_matlab_setup()
% Add toolbox paths needed by cortical_browser_2.
% Edit the paths in this section to match your system.

%%% Edit this section %%%
brainstat   = '/home/lconcha/BrainStat/brainstat_matlab'; % https://github.com/MICA-MNI/Brainstat
gifti       = '/home/lconcha/gifti'; % https://github.com/gllmflndn/gifti
mrtrix      = '/home/lconcha/mrtrix3/matlab'; % https://github.com/Mrtrix3/mrtrix3
corticalDWI = '/home/lconcha/corticalDWI'; 
cbrewer     = '/home/lconcha/cbrewer';  % https://github.com/sijiazhao/cbrewer or https://git.fmrib.ox.ac.uk/amyh/bigmacanalysis/-/tree/main/cbrewer/cbrewer?ref_type=heads
%%%%%%%%%%%%%%%%%%%%%%%%%%%


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



genpath_filtered(brainstat);
genpath_filtered(gifti);
genpath_filtered(mrtrix);
genpath_filtered(corticalDWI);
genpath_filtered(cbrewer);
end % function

