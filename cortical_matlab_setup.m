function cortical_matlab_setup()
% Add toolbox paths needed by cortical_browser_2.
% Edit the paths in this section to match your system.

%%% Edit this section %%%
brainstat   = '/misc/lauterbur2/lconcha/code/BrainStat/brainstat_matlab'; % https://github.com/MICA-MNI/Brainstat
gifti       = '/misc/lauterbur2/lconcha/code/gifti'; % https://github.com/gllmflndn/gifti
mrtrix      = '/home/inb/soporte/lanirem_software/mrtrix_3.0.4/matlab'; % https://github.com/Mrtrix3/mrtrix3
corticalDWI = '/misc/lauterbur2/lconcha/code/corticalDWI';
cbrewer     = '/misc/lauterbur2/lconcha/code/cbrewer';  % https://github.com/sijiazhao/cbrewer or https://git.fmrib.ox.ac.uk/amyh/bigmacanalysis/-/tree/main/cbrewer/cbrewer?ref_type=heads
%%%%%%%%%%%%%%%%%%%%%%%%%%%

addpath(genpath(brainstat));
addpath(genpath(gifti));
addpath(genpath(mrtrix));
addpath(genpath(corticalDWI));
addpath(genpath(cbrewer));

end
