function cortical_matlab_setup()
% Add toolbox paths needed by cortical_browser_2.
% Edit the paths in this section to match your system.

%%% Edit this section %%%
brainstat   = '/misc/lauterbur2/lconcha/code/BrainStat/brainstat_matlab';
gifti       = '/misc/lauterbur2/lconcha/code/gifti';
mrtrix      = '/home/inb/soporte/lanirem_software/mrtrix_3.0.4/matlab';
corticalDWI = '/misc/lauterbur2/lconcha/code/corticalDWI';
cbrewer     = '/misc/lauterbur2/lconcha/code/cbrewer';
%%%%%%%%%%%%%%%%%%%%%%%%%%%

addpath(genpath(brainstat));
addpath(genpath(gifti));
addpath(genpath(mrtrix));
addpath(genpath(corticalDWI));
addpath(genpath(cbrewer));

end
