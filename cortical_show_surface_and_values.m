function cortical_show_surface_and_values(SUBJECTS_DIR,subjID,step_size)


f_rh_surfgeom    = fullfile(SUBJECTS_DIR,subjID,'surf/rh_pial_fsLR-32k.surf.gii');
f_lh_surfgeom    = fullfile(SUBJECTS_DIR,subjID,'surf/lh_pial_fsLR-32k.surf.gii');
fs_data          = dir(fullfile(SUBJECTS_DIR,subjID,'dwi/*_fixels*/*.txt'));



SURF_LH           = read_surface({f_lh_surfgeom,f_rh_surfgeom});
SURF_L            = SURF_LH{1};
SURF_R            = SURF_LH{2};


metric_idx = 2;

f_dataXdepth = fullfile(fs_data(metric_idx).folder,fs_data(metric_idx).name);
dataXdepth   = load(f_dataXdepth);

dataStructure.DATA = dataXdepth;
dataStructure.step_size = step_size;
dataStructure.metric_name = fs_data(metric_idx).name;


srf = inb_show_surface(s,dataStructure)