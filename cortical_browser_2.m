function cortical_DWI_browser(subj_id)
%CORTICAL_DWI_BROWSER  Interactive browser for cortical DWI depth-profile data.
%
%  CORTICAL_DWI_BROWSER(subj_id) opens with subj_id pre-loaded instead of
%  the first subject found in SUBJECTS_DIR.
%
%  Three surface panels: LH overlay, RH overlay, LH asymmetry.
%  Panels 1 & 2 share colormap / CLim.  Panel 3 uses a diverging colormap.
%  A depth slider selects the data column shown on all surfaces.
%  Click any surface to select the nearest vertex and plot its depth profile.
%
%  Requires: read_surface, read_mrtrix_tsf, cortical_cell2mat (on path)

cortical_matlab_setup();

% ── Default paths ─────────────────────────────────────────────────────────
DEF_SUBJECTS_DIR = getenv('SUBJECTS_DIR');

subj_dirs = dir(fullfile(DEF_SUBJECTS_DIR, 'sub-*'));
subj_dirs = subj_dirs([subj_dirs.isdir]);
if isempty(subj_dirs)
    DEF_SUBJ_ID = '';
else
    [~, idx] = sort({subj_dirs.name});
    DEF_SUBJ_ID = subj_dirs(idx(1)).name;
end

if nargin > 0 && ~isempty(subj_id)
    DEF_SUBJ_ID = subj_id;
end

% ── App state ─────────────────────────────────────────────────────────────
S.subjects_dir   = DEF_SUBJECTS_DIR;
S.subj_id        = DEF_SUBJ_ID;
S.lh_surf_file   = '';
S.rh_surf_file   = '';
S.lh_tsf_file    = '';
S.rh_tsf_file    = '';
S.lh_files_list  = {};   % discovered paired files from scan
S.rh_files_list  = {};
S.metrics_list   = {};
S.lh_surf      = [];
S.rh_surf      = [];
S.lh_M         = [];   % nVerts × nDepths
S.rh_M         = [];
S.depth        = 1;
S.nDepths      = 1;
S.step_size    = 0.5;  % mm per depth step
S.metric_name  = 'Value';
S.clim         = [0 1];
S.clim_asym    = [-1 1];
S.cmap         = 'parula';
S.cmap_asym    = 'RdBu_r';
S.invert_cmap      = false;
S.invert_cmap_asym = false;
S.n_rings          = 0;
S.srf1         = [];   % trisurf handles
S.srf2         = [];
S.srf3         = [];
S.dot1         = [];   % selected-vertex markers (red)
S.dot2         = [];
S.dot3         = [];
S.nbr1         = [];   % neighbor-vertex markers (orange)
S.nbr2         = [];
S.nbr3         = [];
S.lst1         = [];   % vertex-list markers
S.lst2         = [];
S.lst3         = [];
S.vertex_list  = [];   % loaded vertex IDs
S.list_mode    = false;
S.sel_vertex   = NaN;
S.hDepthLine   = [];   % xline handle for depth marker in ax4
S.hDepthLine2  = [];   % xline handle for depth marker in ax5
S.vol_data     = [];   % 3D volume (double)
S.vol_info     = [];   % niftiinfo struct
S.vol_geom     = [];   % per-panel geometry (built from affine in buildVolGeom)
S.slice_idx    = [1 1 1];   % slice indices for [sagittal, coronal, axial] panels
S.lh_tck      = [];   % cell array of streamlines (one per vertex, LH)
S.rh_tck      = [];   % cell array of streamlines (one per vertex, RH)
S.tck_fig     = [];   % handle to separate streamline viewer figure

% ── Figure ────────────────────────────────────────────────────────────────
BG = [0.12 0.12 0.12];
hFig = uifigure('Name','Cortical Browser','Position',[30 30 1750 970],...
    'Color', BG, 'KeyPressFcn', @onKeyPress);

% ── Mode menu (radio-button style) ────────────────────────────────────────
hMenuMode = uimenu(hFig, 'Text', 'Selection Mode');
mClick = uimenu(hMenuMode, 'Text', 'Click vertex', ...
    'Checked', 'on', 'MenuSelectedFcn', @(~,~) setMode('click'));
mList  = uimenu(hMenuMode, 'Text', 'Load vertex list', ...
    'Checked', 'off', 'MenuSelectedFcn', @(~,~) setMode('list'));

% ── Volume menu ───────────────────────────────────────────────────────────
hMenuVol = uimenu(hFig, 'Text', 'Volume');
uimenu(hMenuVol, 'Text', 'Load volume…', 'MenuSelectedFcn', @onLoadVolume);
uimenu(hMenuVol, 'Text', 'Show coordinate diagnostics', 'MenuSelectedFcn', @onVolDiagnostics);

hMenuTck = uimenu(hFig, 'Text', 'Streamlines');
uimenu(hMenuTck, 'Text', 'Load LH TCK…', 'MenuSelectedFcn', @(~,~) onLoadTck('lh'));
uimenu(hMenuTck, 'Text', 'Load RH TCK…', 'MenuSelectedFcn', @(~,~) onLoadTck('rh'));
uimenu(hMenuTck, 'Text', 'Clear streamlines', 'MenuSelectedFcn', @onClearTck);

% ── View menu (independent panel toggles) ─────────────────────────────────
S.show_surf  = [true true true];   % [LH, RH, Asym]
S.show_ortho = [true true true];   % [Sagittal, Coronal, Axial]
S.show_plot  = [true true];        % [Depth profile, Asymmetry profile]
hMenuView  = uimenu(hFig, 'Text', 'View');
mShowLH    = uimenu(hMenuView, 'Text', 'LH surface',   'Checked','on', ...
    'MenuSelectedFcn', @(~,~) toggleSurface(1));
mShowRH    = uimenu(hMenuView, 'Text', 'RH surface',   'Checked','on', ...
    'MenuSelectedFcn', @(~,~) toggleSurface(2));
mShowAsym  = uimenu(hMenuView, 'Text', 'Asym surface', 'Checked','on', ...
    'MenuSelectedFcn', @(~,~) toggleSurface(3));
mShowSag   = uimenu(hMenuView, 'Text', 'Sagittal slice',   'Checked','on', ...
    'Separator','on', 'MenuSelectedFcn', @(~,~) toggleOrtho(1));
mShowCor   = uimenu(hMenuView, 'Text', 'Coronal slice',    'Checked','on', ...
    'MenuSelectedFcn', @(~,~) toggleOrtho(2));
mShowAx    = uimenu(hMenuView, 'Text', 'Axial slice',      'Checked','on', ...
    'MenuSelectedFcn', @(~,~) toggleOrtho(3));
mShowDepth = uimenu(hMenuView, 'Text', 'Depth profile',    'Checked','on', ...
    'Separator','on', 'MenuSelectedFcn', @(~,~) togglePlot(1));
mShowAsymP = uimenu(hMenuView, 'Text', 'Asymmetry profile','Checked','on', ...
    'MenuSelectedFcn', @(~,~) togglePlot(2));

% Main 3-row grid ──────────────────────────────────────────────────────────
mainGL = uigridlayout(hFig, [3,1]);
mainGL.RowHeight   = {'2x', '1.5x', '1x'};
mainGL.ColumnWidth = {'1x'};
mainGL.Padding     = [5 5 5 5];
mainGL.RowSpacing  = 5;
mainGL.BackgroundColor = BG;

% ── Top row: five axes panels ─────────────────────────────────────────────
topGL = uigridlayout(mainGL, [1,4]);
topGL.Layout.Row    = 1;
topGL.Layout.Column = 1;
topGL.ColumnWidth   = {'1x','1x','1x','1x'};
topGL.RowHeight     = {'1x'};
topGL.Padding       = [0 0 0 0];
topGL.ColumnSpacing = 5;
topGL.BackgroundColor = BG;

surfBG = [0.06 0.06 0.06];
plotBG = [0.14 0.14 0.14];

% Each surface panel gets a 2-row sub-grid: label (outside/above) + axes.
% This keeps the title out of the 3D scene regardless of camera angle.
surfLabels = {'Left Hemisphere', 'Right Hemisphere', 'Asymmetry index'};
surfAxes   = gobjects(1,3);
for col = 1:3
    sg = uigridlayout(topGL, [2,1]);
    sg.Layout.Row = 1; sg.Layout.Column = col;
    sg.RowHeight  = {20, '1x'};
    sg.Padding    = [0 0 0 0];
    sg.RowSpacing = 0;
    sg.BackgroundColor = BG;
    lbl = uilabel(sg, 'Text', surfLabels{col}, ...
        'FontColor','w', 'FontSize',11, 'FontWeight','bold', ...
        'HorizontalAlignment','center', 'BackgroundColor', BG);
    lbl.Layout.Row = 1; lbl.Layout.Column = 1;
    ax = uiaxes(sg, 'BackgroundColor', surfBG, 'Color', surfBG);
    ax.Layout.Row = 2; ax.Layout.Column = 1;
    surfAxes(col) = ax;
end
ax1 = surfAxes(1);
ax2 = surfAxes(2);
ax3 = surfAxes(3);

ax4 = uiaxes(topGL, 'BackgroundColor', plotBG, 'Color', plotBG);
ax4.Layout.Row=1; ax4.Layout.Column=4;

for ax = [ax1 ax2 ax3]
    axis(ax, 'equal');
    axis(ax, 'vis3d');
    ax.DataAspectRatio = [1 1 1];
    ax.XColor = 'none'; ax.YColor = 'none'; ax.ZColor = 'none';
end
title(ax4,'Vertex depth profile', 'Color','w','FontSize',11,'FontWeight','bold');

ax4.XColor    = [0.75 0.75 0.75];
ax4.YColor    = [0.75 0.75 0.75];
ax4.GridColor = [0.35 0.35 0.35]; ax4.GridAlpha = 0.5;
ax4.XGrid     = 'on'; ax4.YGrid = 'on';

% ── Middle row: orthoslice panels + asymmetry plot ────────────────────────
sliceBG = [0.04 0.04 0.04];
orthoGL = uigridlayout(mainGL, [2, 4]);
orthoGL.Layout.Row    = 2;
orthoGL.Layout.Column = 1;
orthoGL.ColumnWidth   = {'1x','1x','1x','1x'};
orthoGL.RowHeight     = {'1x', 28};
orthoGL.Padding       = [0 0 0 0];
orthoGL.ColumnSpacing = 5;
orthoGL.RowSpacing    = 2;
orthoGL.BackgroundColor = BG;

ax6 = uiaxes(orthoGL,'BackgroundColor',sliceBG,'Color',sliceBG);
ax6.Layout.Row=1; ax6.Layout.Column=1;
ax7 = uiaxes(orthoGL,'BackgroundColor',sliceBG,'Color',sliceBG);
ax7.Layout.Row=1; ax7.Layout.Column=2;
ax8 = uiaxes(orthoGL,'BackgroundColor',sliceBG,'Color',sliceBG);
ax8.Layout.Row=1; ax8.Layout.Column=3;
ax5 = uiaxes(orthoGL,'BackgroundColor',plotBG,'Color',plotBG);
ax5.Layout.Row=1; ax5.Layout.Column=4;

for ax = [ax6 ax7 ax8]
    ax.XColor = 'none'; ax.YColor = 'none';
    colormap(ax, gray(256));
end
title(ax6,'Sagittal',       'Color','w','FontSize',10,'FontWeight','bold');
title(ax7,'Coronal',        'Color','w','FontSize',10,'FontWeight','bold');
title(ax8,'Axial',          'Color','w','FontSize',10,'FontWeight','bold');
title(ax5,'Asymmetry index','Color','w','FontSize',11,'FontWeight','bold');

ax5.XColor    = [0.75 0.75 0.75];
ax5.YColor    = [0.75 0.75 0.75];
ax5.GridColor = [0.35 0.35 0.35]; ax5.GridAlpha = 0.5;
ax5.XGrid     = 'on'; ax5.YGrid = 'on';

sldSag = uislider(orthoGL,'Limits',[1 2],'Value',1,...
    'MajorTicks',[],'MinorTicks',[],...
    'ValueChangedFcn',@(src,~) onSliceChanged(src,1));
sldSag.Layout.Row=2; sldSag.Layout.Column=1;

sldCor = uislider(orthoGL,'Limits',[1 2],'Value',1,...
    'MajorTicks',[],'MinorTicks',[],...
    'ValueChangedFcn',@(src,~) onSliceChanged(src,2));
sldCor.Layout.Row=2; sldCor.Layout.Column=2;

sldAx = uislider(orthoGL,'Limits',[1 2],'Value',1,...
    'MajorTicks',[],'MinorTicks',[],...
    'ValueChangedFcn',@(src,~) onSliceChanged(src,3));
sldAx.Layout.Row=2; sldAx.Layout.Column=3;

% ── Bottom row: control panel (4 rows × 8 cols) ───────────────────────────
%   Cols 1-3: scan controls  [label | field | button]
%   Cols 4-8: viz controls   [Depth | Data | Asym | Vertex# | Step]
%              R1 (labels):   Depth:   Data      Asym      Vertex#:  Step(mm):
%              R2 (boxes):    slider   clim(d)   clim(a)   vtx fld   step fld
%              R3 (dropdowns):depthval cmap(d)   cmap(a)   vtxhint   —
%              R4 (thin):     status (cols 1-3)
ctrlGL = uigridlayout(mainGL, [4, 8]);
ctrlGL.Layout.Row    = 3;
ctrlGL.Layout.Column = 1;
ctrlGL.ColumnWidth   = {100, '1.5x', 80, '2x', 130, 130, 100, 90};
ctrlGL.RowHeight     = {40, 40, 40, 18};
ctrlGL.Padding       = [8 5 8 5];
ctrlGL.ColumnSpacing = 8;
ctrlGL.RowSpacing    = 3;
ctrlGL.BackgroundColor = [0.17 0.17 0.17];

CB = [0.85 0.85 0.85];
FC = [0.10 0.10 0.10];
LC = [0.82 0.82 0.82];
LW = 'bold';

% ── Row 1: labels ─────────────────────────────────────────────────────────
lbl_sd = uilabel(ctrlGL,'Text','Subjects dir:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','right');
lbl_sd.Layout.Row=1; lbl_sd.Layout.Column=1;

edtSubjectsDir = uieditfield(ctrlGL,'text','Value',DEF_SUBJECTS_DIR,...
    'FontColor',FC,'BackgroundColor',CB,'Tooltip',DEF_SUBJECTS_DIR);
edtSubjectsDir.Layout.Row=1; edtSubjectsDir.Layout.Column=2;

btnBrowse = uibutton(ctrlGL,'Text','Browse...','ButtonPushedFcn',@onBrowseDir);
btnBrowse.Layout.Row=1; btnBrowse.Layout.Column=3;
btnBrowse.FontColor=[0.9 0.9 0.9]; btnBrowse.BackgroundColor=[0.28 0.30 0.35];

lbl_d = uilabel(ctrlGL,'Text','Depth:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_d.Layout.Row=1; lbl_d.Layout.Column=4;

lbl_data = uilabel(ctrlGL,'Text','Data','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_data.Layout.Row=1; lbl_data.Layout.Column=5;

lbl_asym = uilabel(ctrlGL,'Text','Asym','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_asym.Layout.Row=1; lbl_asym.Layout.Column=6;

lbl_vx = uilabel(ctrlGL,'Text','Vertex #:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_vx.Layout.Row=1; lbl_vx.Layout.Column=7;

lbl_st = uilabel(ctrlGL,'Text','Step (mm):','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_st.Layout.Row=1; lbl_st.Layout.Column=8;

% ── Row 2: boxes / slider ─────────────────────────────────────────────────
lbl_sj = uilabel(ctrlGL,'Text','Subject ID:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','right');
lbl_sj.Layout.Row=2; lbl_sj.Layout.Column=1;

edtSubjID = uieditfield(ctrlGL,'text','Value',DEF_SUBJ_ID,...
    'FontColor',FC,'BackgroundColor',CB);
edtSubjID.Layout.Row=2; edtSubjID.Layout.Column=2;

btnScan = uibutton(ctrlGL,'Text','Scan','ButtonPushedFcn',@onScan);
btnScan.Layout.Row=2; btnScan.Layout.Column=3;
btnScan.FontColor=[0.9 0.9 0.9]; btnScan.BackgroundColor=[0.25 0.35 0.50];

sldDepth = uislider(ctrlGL,'Limits',[1 2],'Value',1,...
    'ValueChangedFcn',@onDepthSlider,'MajorTicks',[],'MinorTicks',[]);
sldDepth.Layout.Row=2; sldDepth.Layout.Column=4;
sldDepth.FontColor=[0.8 0.8 0.8];

edtClim = uieditfield(ctrlGL,'text','Value','0  1',...
    'ValueChangedFcn',@onClimChanged,'FontColor',FC,'BackgroundColor',CB);
edtClim.Layout.Row=2; edtClim.Layout.Column=5;

edtClimA = uieditfield(ctrlGL,'text','Value','-1  1',...
    'ValueChangedFcn',@onClimAsymChanged,'FontColor',FC,'BackgroundColor',CB);
edtClimA.Layout.Row=2; edtClimA.Layout.Column=6;

edtVertex = uieditfield(ctrlGL,'numeric','Value',0,...
    'ValueDisplayFormat', '%d', ...
    'ValueChangedFcn',@onVertexEdited,'FontColor',FC,'BackgroundColor',CB);
edtVertex.Layout.Row=2; edtVertex.Layout.Column=7;

edtStep = uieditfield(ctrlGL,'numeric','Value',0.5,'Limits',[0.01 100],...
    'ValueChangedFcn',@onStepChanged,'FontColor',FC,'BackgroundColor',CB);
edtStep.Layout.Row=2; edtStep.Layout.Column=8;

% ── Row 3: dropdowns / depth value ────────────────────────────────────────
lbl_mt = uilabel(ctrlGL,'Text','Metric:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','right');
lbl_mt.Layout.Row=3; lbl_mt.Layout.Column=1;

ddMetric = uidropdown(ctrlGL,'Items',{'(scan first)'},'Value','(scan first)',...
    'ValueChangedFcn',@onMetricChanged,'BackgroundColor',CB,'FontColor',FC);
ddMetric.Layout.Row=3; ddMetric.Layout.Column=2;

btnReload = uibutton(ctrlGL,'Text','Reload','ButtonPushedFcn',@onReloadAll);
btnReload.Layout.Row=3; btnReload.Layout.Column=3;
btnReload.FontColor=[0.9 0.9 0.9]; btnReload.BackgroundColor=[0.20 0.38 0.28];

lblDepthVal = uilabel(ctrlGL,'Text','Depth: 1 / 1  (0.0 mm)',...
    'FontColor',[0.92 0.92 0.55],'FontWeight','bold','FontSize',11,...
    'HorizontalAlignment','center');
lblDepthVal.Layout.Row=3; lblDepthVal.Layout.Column=4;

ddCmap = uidropdown(ctrlGL,...
    'Items',{'parula','hot','gray','copper','jet','cool','autumn',...
             'Blues','Greens','Reds','Oranges','Purples','Greys',...
             'YlOrRd','YlOrBr','YlGnBu','YlGn','RdPu','PuRd',...
             'OrRd','PuBuGn','PuBu','BuPu','BuGn','GnBu'},...
    'Value','parula','ValueChangedFcn',@onCmapChanged,...
    'BackgroundColor',CB,'FontColor',FC);
ddCmap.Layout.Row=3; ddCmap.Layout.Column=5;

ddCmapAsym = uidropdown(ctrlGL,...
    'Items',{'RdBu_r','PuOr','PRGn','BrBG','Spectral'},...
    'Value','RdBu_r','ValueChangedFcn',@onCmapAsymChanged,...
    'BackgroundColor',CB,'FontColor',FC);
ddCmapAsym.Layout.Row=3; ddCmapAsym.Layout.Column=6;

lbl_rings = uilabel(ctrlGL,'Text','Rings:','FontColor',LC,'FontWeight',LW,...
    'HorizontalAlignment','center');
lbl_rings.Layout.Row=3; lbl_rings.Layout.Column=7;

% ── Row 4 (status strip + invert checkboxes + rings field) ────────────────
chkInvert = uicheckbox(ctrlGL,'Text','Invert','Value',false,...
    'FontColor',LC,'ValueChangedFcn',@onInvertCmap);
chkInvert.Layout.Row=4; chkInvert.Layout.Column=5;

chkInvertAsym = uicheckbox(ctrlGL,'Text','Invert','Value',false,...
    'FontColor',LC,'ValueChangedFcn',@onInvertCmapAsym);
chkInvertAsym.Layout.Row=4; chkInvertAsym.Layout.Column=6;

edtRings = uispinner(ctrlGL, 'Value', 0, ...
    'Limits', [0 20], 'Step', 1, ...
    'RoundFractionalValues', 'on', ...
    'ValueChangedFcn', @onRingsChanged, ...
    'FontColor', FC, 'BackgroundColor', CB);
edtRings.Layout.Row=4; edtRings.Layout.Column=7;

btnLoadList = uibutton(ctrlGL,'Text','Load list...','ButtonPushedFcn',@onLoadVertexList,...
    'Enable','off', ...
     'Tooltip', 'Load a text file with one vertex ID per row (zero-based indexing)');
btnLoadList.Layout.Row=3; btnLoadList.Layout.Column=8;
btnLoadList.FontColor=[0.9 0.9 0.9]; btnLoadList.BackgroundColor=[0.30 0.40 0.28];

btnClearList = uibutton(ctrlGL,'Text','Clear list','ButtonPushedFcn',@onClearVertexList,...
    'Enable','off');
btnClearList.Layout.Row=4; btnClearList.Layout.Column=8;
btnClearList.FontColor=[0.9 0.9 0.9]; btnClearList.BackgroundColor=[0.38 0.28 0.28];

btnExport = uibutton(ctrlGL,'Text','Export to workspace','ButtonPushedFcn',@onExport);
btnExport.Layout.Row=4; btnExport.Layout.Column=4;
btnExport.FontColor=[0.9 0.9 0.9]; btnExport.BackgroundColor=[0.35 0.28 0.45];

lblStatus = uilabel(ctrlGL,'Text','Press Scan to discover TSF files.',...
    'FontSize',9,'FontColor',[0.55 0.80 0.55], ...
    'WordWrap','on','HorizontalAlignment','left');
lblStatus.Layout.Row=4; lblStatus.Layout.Column=[1 3];

% Colorbars
% Colorbars are created inside renderSurfaces() after trisurf is drawn.

% ── Auto-scan on startup ───────────────────────────────────────────────────
onScan();

% ══════════════════════════════════════════════════════════════════════════
%  CALLBACKS
% ══════════════════════════════════════════════════════════════════════════

    function onBrowseDir(~,~)
        d = uigetdir(edtSubjectsDir.Value, 'Select SUBJECTS_DIR');
        if isequal(d,0), return; end
        edtSubjectsDir.Value   = d;
        edtSubjectsDir.Tooltip = d;
    end

    function onScan(~,~)
        lblStatus.Text = 'Scanning...'; drawnow;
        SDIR  = edtSubjectsDir.Value;
        SUBJ  = edtSubjID.Value;
        dwiDir = fullfile(SDIR, SUBJ, 'dwi');

        D = dir(fullfile(dwiDir, '**', '*ico6_sym*.tsf'));
        if isempty(D)
            lblStatus.Text = sprintf('No .tsf files found in %s', dwiDir);
            return;
        end

        lh_files  = {};
        rh_files  = {};
        lh_labels = {};
        for k = 1:length(D)
            fname = D(k).name;
            % Process only LH files; skip files that are already RH
            if ~contains(lower(fname),'lh'), continue; end
            rh_fname = strrep(fname,'lh','rh');
            rh_fpath = fullfile(D(k).folder, rh_fname);
            if ~exist(rh_fpath,'file'), continue; end
            [~, base] = fileparts(fname);
            label = regexprep(base, '^lh_?', '', 'ignorecase');
            lh_labels{end+1} = label;
            lh_files{end+1}  = fullfile(D(k).folder, fname);
            rh_files{end+1}  = rh_fpath;
        end

        if isempty(lh_labels)
            lblStatus.Text = 'No paired LH+RH .tsf files found.';
            return;
        end

        S.lh_files_list = lh_files;
        S.rh_files_list = rh_files;
        S.metrics_list  = lh_labels;
        ddMetric.Items  = lh_labels;
        ddMetric.Value  = lh_labels{1};

        % Auto-discover surface files
        surfDir = fullfile(SDIR, SUBJ, 'surf');
        lhS = dir(fullfile(surfDir, 'lh_white_ico6_sym.surf.gii'));
        rhS = dir(fullfile(surfDir, 'rh_white_ico6_sym.surf.gii'));
        if ~isempty(lhS)
            S.lh_surf_file = fullfile(lhS(1).folder, lhS(1).name);
        end
        if ~isempty(rhS)
            S.rh_surf_file = fullfile(rhS(1).folder, rhS(1).name);
        end

        lblStatus.Text = sprintf('Found %d metric(s).', length(lh_labels));
        onMetricChanged();
    end

    function onMetricChanged(~,~)
        if isempty(S.metrics_list), return; end
        idx = find(strcmp(S.metrics_list, ddMetric.Value), 1);
        if isempty(idx), return; end
        S.lh_tsf_file = S.lh_files_list{idx};
        S.rh_tsf_file = S.rh_files_list{idx};
        loadAndRender();
    end

    function onReloadAll(~,~)
        loadAndRender();
    end

    function onDepthSlider(src,~)
        S.depth = round(src.Value);
        sldDepth.Value = S.depth;
        updateDepthLabel();
        updateOverlays();
        updateDepthLine();   % move the marker; don't redraw the whole profile
    end

    function onClimChanged(src,~)
        vals = str2num(src.Value); %#ok<ST2NM>
        if numel(vals)==2 && vals(1)<vals(2)
            S.clim = vals;
            applyClim();
        end
    end

    function onClimAsymChanged(src,~)
        vals = str2num(src.Value); %#ok<ST2NM>
        if numel(vals)==2 && vals(1)<vals(2)
            S.clim_asym = vals;
            clim(ax3, S.clim_asym);
        end
    end

    function onCmapChanged(src,~)
        S.cmap = src.Value;
        applyDataCmap();
    end

    function onCmapAsymChanged(src,~)
        S.cmap_asym = src.Value;
        applyAsymCmap();
    end

    function onInvertCmap(src,~)
        S.invert_cmap = src.Value;
        applyDataCmap();
    end

    function onInvertCmapAsym(src,~)
        S.invert_cmap_asym = src.Value;
        applyAsymCmap();
    end

    function applyDataCmap()
        cm = getMATLABColormap(S.cmap);
        if S.invert_cmap, cm = flipud(cm); end
        colormap(ax1, cm);
        colormap(ax2, cm);
    end

    function applyAsymCmap()
        cm = getDivColormap(S.cmap_asym);
        if S.invert_cmap_asym, cm = flipud(cm); end
        colormap(ax3, cm);
    end

    function onStepChanged(src,~)
        S.step_size = src.Value;
        updateDepthLabel();
        updatePlot();
    end

    function onVertexEdited(src,~)
        v = round(src.Value);
        if ~isempty(S.lh_M) && v >= 1 && v <= size(S.lh_M,1)
            S.sel_vertex = v;
            updateMarkers(v);
            updatePlot();
        end
    end

    function onRingsChanged(src,~)
        S.n_rings = round(src.Value);
        if ~isnan(S.sel_vertex) && ~isempty(S.lh_M)
            updateMarkers(S.sel_vertex);
            updatePlot();
        end
    end

    function toggleSurface(idx)
        S.show_surf(idx) = ~S.show_surf(idx);
        mHandles = [mShowLH, mShowRH, mShowAsym];
        mHandles(idx).Checked = onOff(S.show_surf(idx));
        updateTopLayout();
    end

    function toggleOrtho(idx)
        S.show_ortho(idx) = ~S.show_ortho(idx);
        mHandles = [mShowSag, mShowCor, mShowAx];
        mHandles(idx).Checked = onOff(S.show_ortho(idx));
        updateOrthoLayout();
    end

    function togglePlot(idx)
        S.show_plot(idx) = ~S.show_plot(idx);
        mHandles = [mShowDepth, mShowAsymP];
        mHandles(idx).Checked = onOff(S.show_plot(idx));
        updateTopLayout();
        updateOrthoLayout();
    end

    function s = onOff(val)
        if val; s = 'on'; else; s = 'off'; end
    end

    function updateTopLayout()
        w = {'1x','1x','1x','1x'};
        for k = 1:3
            if ~S.show_surf(k), w{k} = 0; end
        end
        if ~S.show_plot(1), w{4} = 0; end
        topGL.ColumnWidth = w;
    end

    function updateOrthoLayout()
        w = {'1x','1x','1x','1x'};
        for k = 1:3
            if ~S.show_ortho(k), w{k} = 0; end
        end
        if ~S.show_plot(2), w{4} = 0; end
        orthoGL.ColumnWidth = w;
    end

    function setMode(mode)
        S.list_mode = strcmp(mode, 'list');
        mClick.Checked = 'off'; mList.Checked = 'off';
        if S.list_mode
            mList.Checked       = 'on';
            btnLoadList.Enable  = 'on';
            btnClearList.Enable = 'on';
            edtRings.Enable     = 'off';
            % hide single-vertex and neighbor markers
            for h = [S.dot1 S.dot2 S.dot3 S.nbr1 S.nbr2 S.nbr3]
                if ~isempty(h) && isvalid(h), set(h,'Visible','off'); end
            end
        else
            mClick.Checked      = 'on';
            btnLoadList.Enable  = 'off';
            btnClearList.Enable = 'off';
            edtRings.Enable     = 'on';
            % clear list state and markers
            S.vertex_list = [];
            for h = [S.lst1 S.lst2 S.lst3]
                if ~isempty(h) && isvalid(h)
                    set(h,'XData',NaN,'YData',NaN,'ZData',NaN,'Visible','off');
                end
            end
            % restore single-vertex marker if one is selected
            if ~isnan(S.sel_vertex) && ~isempty(S.srf1)
                updateMarkers(S.sel_vertex);
                updatePlot();
            end
        end
        lblStatus.Text = sprintf('Mode: %s', mode);
    end

    function onLoadVertexList(~,~)
        [fname, fpath] = uigetfile('*.txt', 'Select vertex ID file');
        if isequal(fname, 0), return; end
        raw  = dlmread(fullfile(fpath, fname)); %#ok<DLMRD>
        vids = unique(round(raw(:)));
        if ~isempty(S.lh_M)
            vids = vids(vids >= 1 & vids <= size(S.lh_M, 1));
        end
        if isempty(vids)
            lblStatus.Text = 'No valid vertices in file.';
            return;
        end
        vids = vids +1;  % convert from 0-based to 1-based indexing
        S.vertex_list = vids;
        lblStatus.Text = sprintf('Loading %d vertices…', numel(vids));
        drawnow;
        updateListMarkers();
        updatePlot();
        lblStatus.Text = sprintf('List loaded: %d vertices.', numel(vids));
    end

    function onClearVertexList(~,~)
        S.vertex_list = [];
        for h = [S.lst1 S.lst2 S.lst3]
            if ~isempty(h) && isvalid(h)
                set(h,'XData',NaN,'YData',NaN,'ZData',NaN,'Visible','off');
            end
        end
        lblStatus.Text = 'Vertex list cleared.';
    end

    function onVolDiagnostics(~,~)
        fprintf('\n══════ Coordinate Diagnostics ══════\n');

        if ~isempty(S.vol_info)
            T   = S.vol_info.Transform;
            M   = T.T;   % 4×4 in MATLAB row convention
            fprintf('\n─── NIfTI volume ───\n');
            fprintf('File:        %s\n', S.vol_info.Filename);
            fprintf('Dimensions:  %d × %d × %d\n', S.vol_info.ImageSize(1:3));
            fprintf('Voxel size:  %.4f × %.4f × %.4f mm\n', S.vol_info.PixelDimensions(1:3));
            fprintf('sform_code:  %d\n', S.vol_info.AdditiveOffset);   % proxy check
            fprintf('Affine (MATLAB Transform.T):\n');
            disp(M);
            dims = S.vol_info.ImageSize(1:3);
            p0 = transformPointsForward(T, [1 1 1]);
            p1 = transformPointsForward(T, dims);
            fprintf('World at voxel (1,1,1):       [%.2f  %.2f  %.2f] mm\n', p0);
            fprintf('World at voxel (%d,%d,%d): [%.2f  %.2f  %.2f] mm\n', dims, p1);
            if ~isempty(S.vol_geom)
                for w=1:3
                    p = S.vol_geom(w);
                    fprintf('Panel %d (%s): fix vox-dim %d, h-world %d, v-world %d, needs_T=%d\n',...
                        w, p.name, p.fix_vox, p.h_world, p.v_world, p.needs_T);
                end
            end
        else
            fprintf('No volume loaded.\n');
        end

        if ~isempty(S.lh_surf)
            lv = S.lh_surf.vertices;
            rv = S.rh_surf.vertices;
            fprintf('\n─── LH surface vertices ───\n');
            fprintf('X range: %.2f → %.2f\n', min(lv(:,1)), max(lv(:,1)));
            fprintf('Y range: %.2f → %.2f\n', min(lv(:,2)), max(lv(:,2)));
            fprintf('Z range: %.2f → %.2f\n', min(lv(:,3)), max(lv(:,3)));
            fprintf('\n─── RH surface vertices ───\n');
            fprintf('X range: %.2f → %.2f\n', min(rv(:,1)), max(rv(:,1)));
            fprintf('Y range: %.2f → %.2f\n', min(rv(:,2)), max(rv(:,2)));
            fprintf('Z range: %.2f → %.2f\n', min(rv(:,3)), max(rv(:,3)));
        else
            fprintf('No surface loaded.\n');
        end

        if ~isempty(S.vol_info) && ~isempty(S.lh_surf)
            lv = S.lh_surf.vertices;
            vol_center = transformPointsForward(S.vol_info.Transform, ...
                S.vol_info.ImageSize(1:3)/2);
            surf_center = mean(lv, 1);
            fprintf('\n─── Center comparison ───\n');
            fprintf('Volume center:  [%.2f  %.2f  %.2f] mm\n', vol_center);
            fprintf('LH surf center: [%.2f  %.2f  %.2f] mm\n', surf_center);
            fprintf('Offset (surf - vol): [%.2f  %.2f  %.2f] mm\n', surf_center - vol_center);
        end

        fprintf('═════════════════════════════════════\n\n');
    end

    function onLoadVolume(~,~)
        [fname, fpath] = uigetfile({ ...
            '*.nii;*.nii.gz;*.mgz', 'Volume files (*.nii, *.nii.gz, *.mgz)'; ...
            '*.nii;*.nii.gz',       'NIfTI files'; ...
            '*.mgz',                'FreeSurfer MGZ'}, ...
            'Select volume');
        if isequal(fname,0), return; end

        srcPath = fullfile(fpath, fname);
        [~, ~, fext] = fileparts(fname);
        tmpNii = '';

        if strcmpi(fext, '.mgz')
            lblStatus.Text = 'Converting MGZ → NIfTI…'; drawnow;
            tmpNii = [tempname '.nii'];
            cmd = sprintf('env -u LD_LIBRARY_PATH mrconvert "%s" "%s" -force', srcPath, tmpNii);
            [st, msg] = system(cmd);
            if st ~= 0
                uialert(hFig, sprintf('mrconvert failed:\n%s', msg), 'MGZ conversion failed');
                lblStatus.Text = 'Load failed.';
                return;
            end
            niiPath = tmpNii;
        else
            niiPath = srcPath;
        end

        lblStatus.Text = 'Loading volume…'; drawnow;
        S.vol_info = niftiinfo(niiPath);
        S.vol_data = double(niftiread(S.vol_info));
        S.vol_info.Filename = srcPath;   % show original filename in diagnostics

        if ~isempty(tmpNii) && isfile(tmpNii)
            delete(tmpNii);
        end

        S.vol_geom = buildVolGeom(S.vol_info, size(S.vol_data));

        % Start at center slice for each panel
        for w = 1:3
            S.slice_idx(w) = round(S.vol_geom(w).n_slices / 2);
        end
        sldSag.Limits = [1 S.vol_geom(1).n_slices]; sldSag.Value = S.slice_idx(1);
        sldCor.Limits = [1 S.vol_geom(2).n_slices]; sldCor.Value = S.slice_idx(2);
        sldAx.Limits  = [1 S.vol_geom(3).n_slices]; sldAx.Value  = S.slice_idx(3);
        updateSlices();
        dims = size(S.vol_data);
        lblStatus.Text = sprintf('Volume loaded: %d×%d×%d voxels.', dims(1), dims(2), dims(3));
    end

    function g = buildVolGeom(vol_info, dims)
        % Parse the affine to determine axis permutation (works for any
        % orthogonal NIfTI regardless of axis order or sign flips).
        %
        % MATLAB convention: [xw yw zw 1] = [xv yv zv 1] * T.T
        %   Row r of M33 = how a unit step in vox dim r affects world XYZ.
        %   Column c of M33 = which vox dim drives world axis c.
        M33   = vol_info.Transform.T(1:3, 1:3);
        transl = vol_info.Transform.T(4, 1:3);   % world origin offset

        % For each vox dim, find which world axis it drives (largest |value|)
        [~, vox2world] = max(abs(M33), [], 2);   % vox2world(d) = world axis (1=X,2=Y,3=Z)
        world2vox = zeros(1,3);
        for d = 1:3, world2vox(vox2world(d)) = d; end

        % Standard anatomical panel layout:
        %   Sagittal (fix world X): show Y horiz, Z vert
        %   Coronal  (fix world Y): show X horiz, Z vert
        %   Axial    (fix world Z): show X horiz, Y vert
        panel_h = [2 1 1];   % horizontal world axis per panel
        panel_v = [3 3 2];   % vertical   world axis per panel
        names   = {'Sagittal','Coronal','Axial'};
        wnames  = {'X','Y','Z'};

        for w = 1:3
            fvd = world2vox(w);          % vox dim to fix
            hw  = panel_h(w);            % desired horizontal world axis
            vw  = panel_v(w);            % desired vertical world axis
            hvd = world2vox(hw);         % vox dim for horizontal
            vvd = world2vox(vw);         % vox dim for vertical

            % World coords along each display axis (0-indexed: MATLAB array
            % index 1 = NIfTI voxel 0, and Transform.T is the raw 0-indexed affine)
            h_coords = M33(hvd, hw) * (0:dims(hvd)-1) + transl(hw);
            v_coords = M33(vvd, vw) * (0:dims(vvd)-1) + transl(vw);

            % squeeze(vol(...fixed at fvd...)) has dims in ascending vox-dim order.
            % We need rows=vvd, cols=hvd; check if transpose is required.
            other_sorted = sort(setdiff(1:3, fvd));
            needs_T = (other_sorted(1) == hvd);  % first squeeze dim is horiz → transpose

            g(w).fix_vox    = fvd;
            g(w).h_vox      = hvd;
            g(w).v_vox      = vvd;
            g(w).h_world    = hw;
            g(w).v_world    = vw;
            g(w).h_coords   = h_coords(:);
            g(w).v_coords   = v_coords(:);
            g(w).needs_T    = needs_T;
            g(w).scale_fix  = M33(fvd, w);
            g(w).transl_fix = transl(w);
            g(w).n_slices   = dims(fvd);
            g(w).name       = names{w};
            g(w).wname      = wnames{w};
        end
    end

    function onSliceChanged(src, dim)
        if isempty(S.vol_data), return; end
        S.slice_idx(dim) = round(src.Value);
        updateSlices();
    end

    function onKeyPress(~, event)
        if isempty(S.vol_geom), return; end
        switch event.Key
            case 'rightarrow'
                S.slice_idx(1) = min(S.vol_geom(1).n_slices, S.slice_idx(1) + 1);
            case 'leftarrow'
                S.slice_idx(1) = max(1, S.slice_idx(1) - 1);
            case 'pageup'
                S.slice_idx(2) = min(S.vol_geom(2).n_slices, S.slice_idx(2) + 1);
            case 'pagedown'
                S.slice_idx(2) = max(1, S.slice_idx(2) - 1);
            case 'uparrow'
                S.slice_idx(3) = min(S.vol_geom(3).n_slices, S.slice_idx(3) + 1);
            case 'downarrow'
                S.slice_idx(3) = max(1, S.slice_idx(3) - 1);
            otherwise
                return;
        end
        updateSlices();
    end

    function updateSlices()
        if isempty(S.vol_data) || isempty(S.vol_geom), return; end
        ax_h = [ax6, ax7, ax8];
        for w = 1:3
            ax = ax_h(w);
            p  = S.vol_geom(w);
            k  = S.slice_idx(w);

            % Preserve zoom/pan if the user has manually adjusted the view
            if strcmp(ax.XLimMode, 'manual')
                saved_xl = ax.XLim; saved_yl = ax.YLim;
            else
                saved_xl = [];
            end

            % Extract slice (fix the appropriate vox dim)
            idx = {':',':',':'};
            idx{p.fix_vox} = k;
            img = squeeze(S.vol_data(idx{:}));
            if p.needs_T, img = img'; end   % ensure rows=vert, cols=horiz

            cla(ax);
            imagesc(ax, p.h_coords, p.v_coords, img);
            set(ax, 'YDir','normal', 'XColor','none', 'YColor','none');
            if p.h_world == 1
                set(ax, 'XDir','reverse');
            else
                set(ax, 'XDir','normal');
            end
            axis(ax, 'image');

            % Restore zoom/pan
            if ~isempty(saved_xl)
                ax.XLim = saved_xl; ax.YLim = saved_yl;
            end

            world_pos = p.scale_fix * (k-1) + p.transl_fix;
            title(ax, sprintf('%s  %s=%.1f mm', p.name, p.wname, world_pos), ...
                'Color','w', 'FontSize',10, 'FontWeight','bold');
        end
        updateSliceContours();
        updateOrthoMarker();
        % Sync slider positions to S.slice_idx (safe here, outside ButtonDownFcn)
        sldSag.Value = S.slice_idx(1);
        sldCor.Value = S.slice_idx(2);
        sldAx.Value  = S.slice_idx(3);
        % Refresh planes in streamline viewer if the window is open
        if ~isempty(S.tck_fig) && isvalid(S.tck_fig)
            updateStreamlineView();
        end
    end

    function updateOrthoMarker()
        ax_h = [ax6, ax7, ax8];
        % Remove any stale marker (survives slice changes via hold; needed for updatePlot path)
        for w = 1:3
            delete(findobj(ax_h(w), 'Tag', 'ortho_vertex_marker'));
        end
        if isnan(S.sel_vertex) || S.list_mode || isempty(S.lh_surf) || isempty(S.vol_geom)
            return;
        end
        vcoord = S.lh_surf.vertices(S.sel_vertex, :);   % [X Y Z] world mm
        for w = 1:3
            ax = ax_h(w);
            p  = S.vol_geom(w);
            hold(ax, 'on');
            plot(ax, vcoord(p.h_world), vcoord(p.v_world), 'o', ...
                'MarkerSize', 6, 'MarkerEdgeColor', [1 0.25 0.25], ...
                'MarkerFaceColor', 'none', 'LineWidth', 2, ...
                'HandleVisibility', 'off', 'Tag', 'ortho_vertex_marker');
            hold(ax, 'off');
        end
    end

    function updateSliceContours()
        if isempty(S.lh_surf) || isempty(S.rh_surf) || isempty(S.vol_geom), return; end
        lv = S.lh_surf.vertices; lf = S.lh_surf.faces;
        rv = S.rh_surf.vertices; rf = S.rh_surf.faces;
        lh_col = [0.40 0.70 1.00];
        rh_col = [1.00 0.65 0.30];
        ax_h = [ax6, ax7, ax8];
        for w = 1:3
            ax = ax_h(w);
            p  = S.vol_geom(w);
            k  = S.slice_idx(w);
            world_pos = p.scale_fix * (k-1) + p.transl_fix;
            proj = [p.h_world, p.v_world];
            hold(ax, 'on');
            drawContour(ax, lv, lf, w, world_pos, proj, lh_col);
            drawContour(ax, rv, rf, w, world_pos, proj, rh_col);
            hold(ax, 'off');
        end
    end

    function drawContour(ax, verts, faces, dim, pos, proj, col)
        segs = meshPlaneIntersect(verts, faces, dim, pos);
        if isempty(segs), return; end
        % segs is Nx6: [p1x p1y p1z  p2x p2y p2z]
        % proj selects which two world coords to use as horiz/vert
        x_seg = [segs(:,proj(1)), segs(:,proj(1)+3), nan(size(segs,1),1)]';
        y_seg = [segs(:,proj(2)), segs(:,proj(2)+3), nan(size(segs,1),1)]';
        plot(ax, x_seg(:), y_seg(:), '-', 'Color', col, 'LineWidth', 0.7, ...
            'HitTest','off');
    end

    function segs = meshPlaneIntersect(verts, faces, dim, pos)
        d  = verts(:,dim) - pos;
        eA = [1 2 3];
        eB = [2 3 1];
        all_pts = zeros(0,3);
        all_tri = zeros(0,1,'int32');
        for e = 1:3
            da = d(faces(:,eA(e)));
            db = d(faces(:,eB(e)));
            mask = da .* db < 0;
            if ~any(mask), continue; end
            va = verts(faces(mask, eA(e)), :);
            vb = verts(faces(mask, eB(e)), :);
            t  = da(mask) ./ (da(mask) - db(mask));
            all_pts = [all_pts; va + t .* (vb - va)]; %#ok<AGROW>
            all_tri = [all_tri; int32(find(mask))];   %#ok<AGROW>
        end
        if isempty(all_tri), segs = zeros(0,6); return; end
        [sorted_tri, ord] = sort(all_tri);
        sorted_pts = all_pts(ord,:);
        [~, ia] = unique(sorted_tri,'first');
        [~, ib] = unique(sorted_tri,'last');
        valid = (ib - ia) == 1;
        segs = [sorted_pts(ia(valid),:), sorted_pts(ib(valid),:)];
    end

    function onExport(~,~)
        if isempty(S.lh_M)
            lblStatus.Text = 'Nothing to export — load data first.';
            return;
        end

        % Determine active vertex set (same logic as updatePlot)
        if S.list_mode && ~isempty(S.vertex_list)
            all_v = S.vertex_list;
        elseif ~isnan(S.sel_vertex)
            all_v = getNeighborRings(S.lh_surf.faces, S.sel_vertex, S.n_rings);
        else
            lblStatus.Text = 'No vertex selected.';
            return;
        end

        depths   = (0 : S.nDepths-1) .* S.step_size;
        lh_data  = double(S.lh_M(all_v, :));
        rh_data  = double(S.rh_M(all_v, :));
        asym_data = (lh_data - rh_data) ./ ((lh_data + rh_data) ./ 2);
        asym_data(~isfinite(asym_data)) = NaN;

        out.vertex_ids  = all_v;
        out.depths_mm   = depths(:);
        out.lh_data     = lh_data;
        out.rh_data     = rh_data;
        out.lh_mean     = mean(lh_data,  1, 'omitnan');
        out.rh_mean     = mean(rh_data,  1, 'omitnan');
        out.asym_data   = asym_data;
        out.asym_mean   = mean(asym_data, 1, 'omitnan');
        out.metric      = S.metric_name;
        out.subject     = S.subj_id;
        out.n_vertices  = numel(all_v);

        assignin('base', 'cortical_export', out);
        lblStatus.Text = sprintf('Exported ''cortical_export'' (%d vertices) to workspace.', numel(all_v));
    end

    function updateListMarkers()
        if isempty(S.vertex_list) || isempty(S.srf1), return; end
        vl   = S.srf1.Vertices;
        vr   = S.srf2.Vertices;
        vids = S.vertex_list;
        set(S.lst1,'XData',vl(vids,1),'YData',vl(vids,2),'ZData',vl(vids,3),'Visible','on');
        set(S.lst2,'XData',vr(vids,1),'YData',vr(vids,2),'ZData',vr(vids,3),'Visible','on');
        set(S.lst3,'XData',vl(vids,1),'YData',vl(vids,2),'ZData',vl(vids,3),'Visible','on');
    end

% ══════════════════════════════════════════════════════════════════════════
%  DATA LOADING
% ══════════════════════════════════════════════════════════════════════════

    function autoLoadBrain()
        mriDir = fullfile(S.subjects_dir, S.subj_id, 'mri');
        % Prefer an already-converted NIfTI to avoid mrconvert overhead
        candidates = { ...
            fullfile(mriDir, 'brain.nii.gz'), ...
            fullfile(mriDir, 'brain.nii'), ...
            fullfile(mriDir, 'brain.mgz')};
        volFile = '';
        for i = 1:numel(candidates)
            if isfile(candidates{i})
                volFile = candidates{i};
                break;
            end
        end
        if isempty(volFile), return; end

        [~, ~, fext] = fileparts(volFile);
        tmpNii = '';
        try
            if strcmpi(fext, '.mgz')
                lblStatus.Text = 'Converting brain.mgz → NIfTI…'; drawnow;
                tmpNii = [tempname '.nii'];
                cmd = sprintf('env -u LD_LIBRARY_PATH mrconvert "%s" "%s" -force', volFile, tmpNii);
                [st, msg] = system(cmd);
                if st ~= 0
                    fprintf('autoLoadBrain: mrconvert failed: %s\n', msg);
                    return;
                end
                niiPath = tmpNii;
            else
                niiPath = volFile;
            end
            S.vol_info = niftiinfo(niiPath);
            S.vol_data = double(niftiread(S.vol_info));
            S.vol_info.Filename = volFile;
            if ~isempty(tmpNii) && isfile(tmpNii), delete(tmpNii); end
            S.vol_geom = buildVolGeom(S.vol_info, size(S.vol_data));
            for w = 1:3
                S.slice_idx(w) = round(S.vol_geom(w).n_slices / 2);
            end
            sldSag.Limits = [1 S.vol_geom(1).n_slices]; sldSag.Value = S.slice_idx(1);
            sldCor.Limits = [1 S.vol_geom(2).n_slices]; sldCor.Value = S.slice_idx(2);
            sldAx.Limits  = [1 S.vol_geom(3).n_slices]; sldAx.Value  = S.slice_idx(3);
            updateSlices();
            [~, fn, fe] = fileparts(volFile);
            lblStatus.Text = sprintf('Loaded. %d vertices, %d depths. Volume: %s', ...
                size(S.lh_M,1), S.nDepths, [fn fe]);
        catch ME
            if ~isempty(tmpNii) && isfile(tmpNii), delete(tmpNii); end
            fprintf('autoLoadBrain: %s\n', ME.message);
        end
    end

    function loadAndRender()
        lblStatus.Text = 'Loading…';
        drawnow;
        try
            fprintf(1,'LOADING...\n');
            fprintf(1,'  LH surface: %s\n  RH surface: %s\n', S.lh_surf_file, S.rh_surf_file);
            S.lh_surf = read_surface(S.lh_surf_file);
            S.rh_surf = read_surface(S.rh_surf_file);

            fprintf(1,'  LH TSF: %s\n  RH TSF: %s\n', S.lh_tsf_file, S.rh_tsf_file);
            lh_tsf  = read_mrtrix_tsf(S.lh_tsf_file);
            rh_tsf  = read_mrtrix_tsf(S.rh_tsf_file);
            S.lh_M  = cortical_cell2mat(lh_tsf.data);
            S.rh_M  = cortical_cell2mat(rh_tsf.data);
            S.nDepths = size(S.lh_M, 2);
            S.depth   = 1;

            [~, fn] = fileparts(S.lh_tsf_file);
            S.metric_name = fn;

            % Auto CLim from finite values
            d1 = S.lh_M(:,1);
            d1 = d1(isfinite(d1));
            if ~isempty(d1)
                S.clim = [prctile(d1,2) prctile(d1,98)];
                edtClim.Value = sprintf('%.4g  %.4g', S.clim(1), S.clim(2));
            end

            sldDepth.Limits     = [1 max(S.nDepths, 2)];
            sldDepth.Value      = 1;
            nTick = min(S.nDepths, 6);
            sldDepth.MajorTicks = unique(round(linspace(1, S.nDepths, nTick)));

            S.sel_vertex  = NaN;
            edtVertex.Value = 0;

            renderSurfaces();
            updateDepthLabel();
            lblStatus.Text = sprintf('Loaded. %d vertices, %d depths.', ...
                size(S.lh_M,1), S.nDepths);
            autoLoadBrain();
        catch ME
            lblStatus.Text = ['Error: ' ME.message];
            warning('cortical_DWI_browser:load', '%s\n%s', ME.message, ME.getReport());
        end
    end

% ══════════════════════════════════════════════════════════════════════════
%  SURFACE RENDERING
% ══════════════════════════════════════════════════════════════════════════

    function renderSurfaces()
        cla(ax1); cla(ax2); cla(ax3);
        
        smallMarkerColor = [1 1 1] .* .8;
        smallMarkerSize  = 30;
        
        lh  = S.lh_surf;
        rh  = S.rh_surf;
        CL  = getDepthData(S.lh_M, S.depth);
        CR  = getDepthData(S.rh_M, S.depth);
        CA  = computeAsymmetry(CL, CR);

        % Panel 1 – LH data
        S.srf1 = trisurf(lh.faces, ...
            lh.vertices(:,1), lh.vertices(:,2), lh.vertices(:,3), CL, ...
            'Parent', ax1, 'EdgeColor','none', 'FaceColor','interp');
        styleSurface(S.srf1);
        view(ax1, -90, 0);          % set camera BEFORE headlight
        setupLight(ax1);
        hold(ax1,'on');
        S.nbr1 = scatter3(ax1, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');
        S.dot1 = scatter3(ax1, NaN,NaN,NaN, 120, 'r', 'filled', 'Visible','off');
        S.lst1 = scatter3(ax1, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');

        % Panel 2 – RH data
        S.srf2 = trisurf(rh.faces, ...
            rh.vertices(:,1), rh.vertices(:,2), rh.vertices(:,3), CR, ...
            'Parent', ax2, 'EdgeColor','none', 'FaceColor','interp');
        styleSurface(S.srf2);
        view(ax2, 90, 0);           % set camera BEFORE headlight
        setupLight(ax2);
        hold(ax2,'on');
        S.nbr2 = scatter3(ax2, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');
        S.dot2 = scatter3(ax2, NaN,NaN,NaN, 120, 'r', 'filled', 'Visible','off');
        S.lst2 = scatter3(ax2, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');

        % Panel 3 – Asymmetry on LH geometry
        S.srf3 = trisurf(lh.faces, ...
            lh.vertices(:,1), lh.vertices(:,2), lh.vertices(:,3), CA, ...
            'Parent', ax3, 'EdgeColor','none', 'FaceColor','interp');
        styleSurface(S.srf3);
        view(ax3, -90, 0);          % set camera BEFORE headlight
        setupLight(ax3);
        hold(ax3,'on');
        S.nbr3 = scatter3(ax3, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');
        S.dot3 = scatter3(ax3, NaN,NaN,NaN, 120, 'r', 'filled', 'Visible','off');
        S.lst3 = scatter3(ax3, NaN,NaN,NaN, smallMarkerSize, smallMarkerColor, 'filled', 'Visible','off');

        % Colormaps
        applyDataCmap();
        applyAsymCmap();

        % CLim
        applyClim();
        clim(ax3, S.clim_asym);

        % Click callbacks on trisurf objects
        S.srf1.ButtonDownFcn = @(src,ev) onSurfaceClick(src,ev,ax1,S.dot1,'lh');
        S.srf2.ButtonDownFcn = @(src,ev) onSurfaceClick(src,ev,ax2,S.dot2,'rh');
        S.srf3.ButtonDownFcn = @(src,ev) onSurfaceClick(src,ev,ax3,S.dot3,'lh');

        % Colorbars — recreated here so cla() can't destroy them first
        for cbax = [ax1 ax2 ax3]
            cb = colorbar(cbax, 'Location','southoutside', ...
                'Color','w', 'FontSize',7, 'TickDirection','out');
            cb.Label.Color = 'w';
        end

        % Refresh contours if a volume is already loaded
        if ~isempty(S.vol_data)
            updateSliceContours();
        end
    end

    function updateOverlays()
        if isempty(S.srf1), return; end
        CL = getDepthData(S.lh_M, S.depth);
        CR = getDepthData(S.rh_M, S.depth);
        CA = computeAsymmetry(CL, CR);
        set(S.srf1, 'CData', CL);
        set(S.srf2, 'CData', CR);
        set(S.srf3, 'CData', CA);
        drawnow limitrate;
    end

% ══════════════════════════════════════════════════════════════════════════
%  SURFACE CLICK → vertex selection
% ══════════════════════════════════════════════════════════════════════════

    function onSurfaceClick(src, event, ax, dot, hemi) %#ok<INUSL>
        clickPt = event.IntersectionPoint;
        verts   = src.Vertices;
        dists   = vecnorm(verts - clickPt, 2, 2);
        [~, v]  = min(dists);

        S.sel_vertex    = v;
        edtVertex.Value = v;
        updateMarkers(v);

        % Snap orthoslices to the selected vertex world position
        if ~isempty(S.vol_geom) && ~isempty(S.vol_info)
            wcoord = verts(v, :);
            affine = S.vol_info.Transform.T;
            vox0   = [wcoord 1] * inv(affine);
            vox1   = round(vox0(1:3)) + 1;
            for w = 1:3
                g = S.vol_geom(w);
                idx = vox1(g.fix_vox);
                if isfinite(idx)
                    S.slice_idx(w) = max(1, min(g.n_slices, idx));
                end
            end
            updateSlices();   % reads S.slice_idx; also syncs slider positions
        end

        updatePlot();
    end

    function updateMarkers(v)
        if isempty(S.srf1), return; end
        vl = S.srf1.Vertices;
        vr = S.srf2.Vertices;
        if v < 1 || v > size(vl,1), return; end

        % Selected vertex (red) — hidden in list mode
        vis = 'on';
        if S.list_mode, vis = 'off'; end
        set(S.dot1,'XData',vl(v,1),'YData',vl(v,2),'ZData',vl(v,3),'Visible',vis);
        set(S.dot2,'XData',vr(v,1),'YData',vr(v,2),'ZData',vr(v,3),'Visible',vis);
        set(S.dot3,'XData',vl(v,1),'YData',vl(v,2),'ZData',vl(v,3),'Visible',vis);

        % Neighbors (orange) — same topology for LH and RH
        all_v = getNeighborRings(S.lh_surf.faces, v, S.n_rings);
        nbrs = all_v(all_v ~= v);
        if ~isempty(nbrs)
            set(S.nbr1,'XData',vl(nbrs,1),'YData',vl(nbrs,2),'ZData',vl(nbrs,3),'Visible','on');
            set(S.nbr2,'XData',vr(nbrs,1),'YData',vr(nbrs,2),'ZData',vr(nbrs,3),'Visible','on');
            set(S.nbr3,'XData',vl(nbrs,1),'YData',vl(nbrs,2),'ZData',vl(nbrs,3),'Visible','on');
        else
            set(S.nbr1,'XData',NaN,'YData',NaN,'ZData',NaN,'Visible','off');
            set(S.nbr2,'XData',NaN,'YData',NaN,'ZData',NaN,'Visible','off');
            set(S.nbr3,'XData',NaN,'YData',NaN,'ZData',NaN,'Visible','off');
        end
    end

% ══════════════════════════════════════════════════════════════════════════
%  DEPTH PROFILE PLOT
% ══════════════════════════════════════════════════════════════════════════

    function updatePlot()
        if isempty(S.lh_M), return; end
        depths = (0 : S.nDepths-1) .* S.step_size;

        % Vertex set: list mode overrides single-vertex + rings
        if S.list_mode && ~isempty(S.vertex_list)
            all_v = S.vertex_list;
            nbrs  = [];
        elseif ~isnan(S.sel_vertex)
            v     = S.sel_vertex;
            all_v = getNeighborRings(S.lh_surf.faces, v, S.n_rings);
            nbrs  = all_v(all_v ~= v);
        else
            return;
        end
        d_lh_all = double(S.lh_M(all_v, :));
        d_rh_all = double(S.rh_M(all_v, :));
        d_lh_mean = mean(d_lh_all, 1, 'omitnan');
        d_rh_mean = mean(d_rh_all, 1, 'omitnan');

        lh_col  = [0.40 0.70 1.00];
        rh_col  = [1.00 0.52 0.30];
        bg      = [0.14 0.14 0.14];
        lh_thin = lh_col * 0.30 + bg * 0.70;   % muted opaque stand-in for alpha
        rh_thin = rh_col * 0.30 + bg * 0.70;

        if ~isempty(S.hDepthLine) && isvalid(S.hDepthLine)
            delete(S.hDepthLine);
        end
        S.hDepthLine = [];
        delete(findall(ax4, 'Type', 'line'));   % findall ignores HandleVisibility
        cla(ax4);
        hold(ax4, 'on');

        % Thin faint lines for individual vertices (capped for performance)
        MAX_THIN = 50;
        if numel(all_v) > 1 && numel(all_v) <= MAX_THIN
            for k = 1:size(d_lh_all, 1)
                plot(ax4, depths, d_lh_all(k,:), '-', ...
                    'Color', lh_thin, 'LineWidth', 0.7, ...
                    'HandleVisibility','off');
                plot(ax4, depths, d_rh_all(k,:), '-', ...
                    'Color', rh_thin, 'LineWidth', 0.7, ...
                    'HandleVisibility','off');
            end
        elseif numel(all_v) > MAX_THIN
            d_lh_sd = std(d_lh_all, 0, 1, 'omitnan');
            d_rh_sd = std(d_rh_all, 0, 1, 'omitnan');
            plot(ax4, depths, d_lh_mean + d_lh_sd, '--', ...
                'Color', lh_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
            plot(ax4, depths, d_lh_mean - d_lh_sd, '--', ...
                'Color', lh_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
            plot(ax4, depths, d_rh_mean + d_rh_sd, '--', ...
                'Color', rh_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
            plot(ax4, depths, d_rh_mean - d_rh_sd, '--', ...
                'Color', rh_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
        end

        % Thick mean lines
        plot(ax4, depths, d_lh_mean, '-', 'Color', lh_col, ...
            'LineWidth', 2.5, 'DisplayName', sprintf('LH mean (n=%d)', numel(all_v)));
        plot(ax4, depths, d_rh_mean, '-', 'Color', rh_col, ...
            'LineWidth', 2.5, 'DisplayName', sprintf('RH mean (n=%d)', numel(all_v)));

        hold(ax4, 'off');
        legend(ax4, 'TextColor','w','Color','none','EdgeColor','none','Location','best');
        xlabel(ax4, 'Depth from pial surface (mm)', 'Color',[0.80 0.80 0.80]);
        ylabel(ax4, S.metric_name, 'Color',[0.80 0.80 0.80], 'Interpreter','none');
        if S.list_mode
            title(ax4, sprintf('Vertex list  (n=%d)', numel(all_v)), 'Color','w');
        else
            title(ax4, sprintf('Vertex %d  (+%d nbrs, %d rings)', v, numel(nbrs), S.n_rings), 'Color','w');
        end
        ax4.XColor = [0.70 0.70 0.70]; ax4.YColor = [0.70 0.70 0.70];
        ax4.Color  = [0.14 0.14 0.14];
        ax4.XGrid  = 'on'; ax4.YGrid = 'on';

        updateAsymPlot();
        updateDepthLine();
        updateStreamlineView();
        updateOrthoMarker();
    end

    function updateAsymPlot()
        if isempty(S.lh_M), return; end
        depths = (0 : S.nDepths-1) .* S.step_size;

        if S.list_mode && ~isempty(S.vertex_list)
            all_v = S.vertex_list;
            nbrs  = [];
        elseif ~isnan(S.sel_vertex)
            v     = S.sel_vertex;
            all_v = getNeighborRings(S.lh_surf.faces, v, S.n_rings);
            nbrs  = all_v(all_v ~= v);
        else
            return;
        end
        d_lh_all = double(S.lh_M(all_v, :));
        d_rh_all = double(S.rh_M(all_v, :));

        % Asymmetry for every vertex in the group
        d_asym_all = (d_lh_all - d_rh_all) ./ ((d_lh_all + d_rh_all) ./ 2);
        d_asym_all(~isfinite(d_asym_all)) = NaN;
        d_asym_mean = mean(d_asym_all, 1, 'omitnan');

        asym_col  = [0.88 0.88 0.30];
        bg        = [0.14 0.14 0.14];
        asym_thin = asym_col * 0.30 + bg * 0.70;

        if ~isempty(S.hDepthLine2) && isvalid(S.hDepthLine2)
            delete(S.hDepthLine2);
        end
        S.hDepthLine2 = [];
        delete(findall(ax5, 'Type', 'line'));   % findall ignores HandleVisibility
        cla(ax5);
        hold(ax5, 'on');

        % Thin faint lines for individual vertices (capped for performance)
        MAX_THIN = 50;
        if numel(all_v) > 1 && numel(all_v) <= MAX_THIN
            for k = 1:size(d_asym_all, 1)
                plot(ax5, depths, d_asym_all(k,:), '-', ...
                    'Color', asym_thin, 'LineWidth', 0.7, ...
                    'HandleVisibility','off');
            end
        elseif numel(all_v) > MAX_THIN
            d_asym_sd = std(d_asym_all, 0, 1, 'omitnan');
            plot(ax5, depths, d_asym_mean + d_asym_sd, '--', ...
                'Color', asym_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
            plot(ax5, depths, d_asym_mean - d_asym_sd, '--', ...
                'Color', asym_thin, 'LineWidth', 1.0, 'HandleVisibility','off');
        end

        % Thick mean line
        plot(ax5, depths, d_asym_mean, '-', 'Color', asym_col, ...
            'LineWidth', 2.5, 'DisplayName', sprintf('Asym mean (n=%d)', numel(all_v)));

        yline(ax5, 0, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1, ...
            'HandleVisibility','off');

        ax5.YLim = [-max(abs(d_asym_mean))*1.2, max(abs(d_asym_mean))*1.2];

        hold(ax5, 'off');
        legend(ax5, 'TextColor','w','Color','none','EdgeColor','none','Location','best');
        xlabel(ax5, 'Depth from pial surface (mm)', 'Color',[0.80 0.80 0.80]);
        ylabel(ax5, 'Asymmetry index',              'Color',[0.80 0.80 0.80]);
        if S.list_mode
            title(ax5, sprintf('Vertex list  (n=%d)', numel(all_v)), 'Color','w');
        else
            title(ax5, sprintf('Vertex %d  (+%d nbrs, %d rings)', v, numel(nbrs), S.n_rings), 'Color','w');
        end
        ax5.XColor = [0.70 0.70 0.70]; ax5.YColor = [0.70 0.70 0.70];
        ax5.Color  = [0.14 0.14 0.14];
        ax5.XGrid  = 'on'; ax5.YGrid = 'on';

        updateDepthLine2();
    end

    function updateDepthLine()
        if isnan(S.sel_vertex) || isempty(S.lh_M), return; end
        cur_mm = (S.depth - 1) .* S.step_size;
        if isempty(S.hDepthLine) || ~isvalid(S.hDepthLine)
            hold(ax4, 'on');
            S.hDepthLine = xline(ax4, cur_mm, '--', ...
                'Color',[0.88 0.88 0.30], 'LineWidth',1.4, ...
                'HandleVisibility','off');
            hold(ax4, 'off');
        else
            S.hDepthLine.Value = cur_mm;
        end
        updateDepthLine2();
    end

    function updateDepthLine2()
        if isnan(S.sel_vertex) || isempty(S.lh_M), return; end
        cur_mm = (S.depth - 1) .* S.step_size;
        if isempty(S.hDepthLine2) || ~isvalid(S.hDepthLine2)
            hold(ax5, 'on');
            S.hDepthLine2 = xline(ax5, cur_mm, '--', ...
                'Color',[0.88 0.88 0.30], 'LineWidth',1.4, ...
                'HandleVisibility','off');
            hold(ax5, 'off');
        else
            S.hDepthLine2.Value = cur_mm;
        end
    end

% ══════════════════════════════════════════════════════════════════════════
%  HELPERS
% ══════════════════════════════════════════════════════════════════════════

    function styleSurface(h)
        h.AmbientStrength  = 0.35;
        h.DiffuseStrength  = 0.75;
        h.SpecularStrength = 0.05;
        h.FaceLighting     = 'gouraud';
    end

    function setupLight(ax)
        % Remove any lights left from a previous render
        delete(findobj(ax, 'Type', 'light'));
        hLight = camlight(ax, 'headlight');
        ax.Clipping = 'off';
        % Re-issue headlight whenever the camera moves (interactive rotation)
        addlistener(ax, 'CameraPosition', 'PostSet', ...
            @(~,~) safeRefreshLight(hLight));
    end

    function safeRefreshLight(hLight)
        if isvalid(hLight)
            camlight(hLight, 'headlight');
        end
    end

    function applyClim()
        clim(ax1, S.clim);
        clim(ax2, S.clim);
    end

    function updateDepthLabel()
        mm = (S.depth - 1) .* S.step_size;
        lblDepthVal.Text = sprintf('Depth: %d / %d  (%.2f mm)', ...
            S.depth, S.nDepths, mm);
    end

    function C = getDepthData(M, dep)
        if isempty(M)
            C = zeros(1,1);
            return;
        end
        d       = min(dep, size(M,2));
        C       = double(M(:,d));
        C(~isfinite(C)) = NaN;
    end

    function CA = computeAsymmetry(CL, CR)
        CA = (CL - CR) ./ ((CL + CR) / 2);
        CA(~isfinite(CA)) = 0;

    end

    function cmap = getMATLABColormap(name)
        cbrewer_seq = {'Blues','Greens','Reds','Oranges','Purples','Greys',...
                       'YlOrRd','YlOrBr','YlGnBu','YlGn','RdPu','PuRd',...
                       'OrRd','PuBuGn','PuBu','BuPu','BuGn','GnBu'};
        builtins = {'parula','hot','gray','copper','jet','cool','autumn',...
                    'summer','winter','spring','bone','pink','hsv'};
        if any(strcmp(name, cbrewer_seq))
            try
                raw  = cbrewer('seq', name, 9);
                raw  = max(0, min(1, raw));
                cmap = interp1(linspace(0,1,9), raw, linspace(0,1,256), 'pchip');
                cmap = max(0, min(1, cmap));
            catch
                cmap = parula(256);
            end
        elseif any(strcmpi(name, builtins))
            cmap = feval(lower(name), 256);
        else
            try
                cmap = feval(name, 256);
            catch
                cmap = parula(256);
            end
        end
    end

    function cmap = getDivColormap(name)
        % cbrewer diverging maps; fall back to blue-white-red.
        % Request the native 11-point palette (no interpolation inside cbrewer)
        % then resize to 256 with pchip to avoid the non-uniform-grid warning.
        flip_it  = length(name) >= 2 && strcmp(name(end-1:end),'_r');
        raw_name = strrep(name,'_r','');
        try
            raw  = cbrewer('div', raw_name, 11);
            raw  = max(0, min(1, raw));
            xi   = linspace(0, 1, 11);
            xo   = linspace(0, 1, 256);
            cmap = interp1(xi, raw, xo, 'pchip');
            cmap = max(0, min(1, cmap));
            if flip_it, cmap = flipud(cmap); end
        catch
            % Manual blue–white–red fallback
            n    = 128;
            cmap = [linspace(0,1,n)', linspace(0,1,n)', ones(n,1);
                    ones(n,1), linspace(1,0,n)', linspace(1,0,n)'];
        end
    end

    function nbrs = getMeshNeighbors(faces, v)
        % 1-ring neighbors of vertex v via shared triangle faces
        mask = any(faces == v, 2);
        nbrs = unique(faces(mask, :));
        nbrs = nbrs(nbrs ~= v);
    end

    function all_v = getNeighborRings(faces, v, n_rings)
        % BFS expansion: all_v includes v plus vertices within n_rings rings
        all_v = v;
        if n_rings == 0, return; end
        frontier = v;
        for r = 1:n_rings
            new_nbrs = [];
            for vi = frontier(:)'
                new_nbrs = [new_nbrs; getMeshNeighbors(faces, vi)]; %#ok<AGROW>
            end
            new_nbrs = setdiff(unique(new_nbrs), all_v);
            all_v = [all_v; new_nbrs]; %#ok<AGROW>
            frontier = new_nbrs;
            if isempty(frontier), break; end
        end
    end

    function s = shortenPath(p)
        if length(p) <= 42
            s = p;
        else
            s = ['...' p(end-38:end)];
        end
    end

    % ── TCK loader ────────────────────────────────────────────────────────────
    function onLoadTck(hemi)
        [fname, fpath] = uigetfile('*.tck', sprintf('Select %s TCK file', upper(hemi)));
        if isequal(fname, 0), return; end
        fullpath = fullfile(fpath, fname);
        lblStatus.Text = sprintf('Loading %s TCK…', upper(hemi));
        drawnow;
        try
            t = read_mrtrix_tracks(fullpath);
            if strcmp(hemi, 'lh')
                S.lh_tck = t.data;
                lblStatus.Text = sprintf('LH TCK loaded: %d streamlines.', numel(S.lh_tck));
            else
                S.rh_tck = t.data;
                lblStatus.Text = sprintf('RH TCK loaded: %d streamlines.', numel(S.rh_tck));
            end
            updateStreamlineView();
        catch ME
            lblStatus.Text = sprintf('TCK load failed: %s', ME.message);
        end
    end

    function onClearTck(~,~)
        S.lh_tck = [];
        S.rh_tck = [];
        if ~isempty(S.tck_fig) && isvalid(S.tck_fig)
            close(S.tck_fig);
        end
        S.tck_fig = [];
        lblStatus.Text = 'Streamlines cleared.';
    end

    function updateStreamlineView()
        if isempty(S.lh_tck) && isempty(S.rh_tck), return; end

        % Resolve vertex set
        if S.list_mode && ~isempty(S.vertex_list)
            all_v = S.vertex_list;
        elseif ~isnan(S.sel_vertex)
            all_v = getNeighborRings(S.lh_surf.faces, S.sel_vertex, S.n_rings);
        else
            all_v = [];
        end

        % Don't open the window without a selection; update if already open
        if isempty(all_v) && (isempty(S.tck_fig) || ~isvalid(S.tck_fig))
            return;
        end

        % Clamp indices to available streamlines
        if ~isempty(S.lh_tck) && ~isempty(all_v)
            lh_v = all_v(all_v >= 1 & all_v <= numel(S.lh_tck));
        else
            lh_v = [];
        end
        if ~isempty(S.rh_tck) && ~isempty(all_v)
            rh_v = all_v(all_v >= 1 & all_v <= numel(S.rh_tck));
        else
            rh_v = [];
        end

        % Create or reuse figure — preserve camera view between updates
        if isempty(S.tck_fig) || ~isvalid(S.tck_fig)
            S.tck_fig = figure('Name','Streamline Viewer', ...
                'Color',[0.08 0.08 0.08], 'NumberTitle','off');
            prev_view = [];
        else
            ax_old = findobj(S.tck_fig, 'Type','axes');
            if ~isempty(ax_old)
                prev_view = [get(ax_old(1),'CameraPosition'); ...
                             get(ax_old(1),'CameraTarget'); ...
                             get(ax_old(1),'CameraUpVector')];
            else
                prev_view = [];
            end
            clf(S.tck_fig);
        end

        ax = axes(S.tck_fig, 'Color',[0.08 0.08 0.08], ...
            'XColor','none','YColor','none','ZColor','none');
        hold(ax,'on');
        axis(ax,'equal'); axis(ax,'vis3d');
        colormap(ax, gray(256));

        % ── Orthoslice planes ────────────────────────────────────────────────
        if ~isempty(S.vol_data) && ~isempty(S.vol_geom)
            vol_clim = [min(S.vol_data(:)), max(S.vol_data(:))];
            for w = 1:3
                p   = S.vol_geom(w);
                k   = S.slice_idx(w);
                world_fix = p.scale_fix * (k-1) + p.transl_fix;

                idx = {':',':',':'};
                idx{p.fix_vox} = k;
                img = double(squeeze(S.vol_data(idx{:})));
                if p.needs_T, img = img'; end   % rows=v_world, cols=h_world

                [H, V] = meshgrid(p.h_coords, p.v_coords);
                Wg = zeros([size(H), 3]);
                Wg(:,:,p.h_world) = H;
                Wg(:,:,p.v_world) = V;
                Wg(:,:,w)         = world_fix;   % w == fixed world axis (1=X,2=Y,3=Z)

                surface(ax, Wg(:,:,1), Wg(:,:,2), Wg(:,:,3), img, ...
                    'EdgeColor','none', 'FaceColor','texturemap', ...
                    'CDataMapping','scaled');
            end
            set(ax, 'CLim', vol_clim);
        end

        % ── Streamlines ──────────────────────────────────────────────────────
        lh_col = [0.40 0.70 1.00];
        rh_col = [1.00 0.52 0.30];
        for k = 1:numel(lh_v)
            sl = S.lh_tck{lh_v(k)};
            if size(sl,1) < 2, continue; end
            plot3(ax, sl(:,1), sl(:,2), sl(:,3), '-', ...
                'Color', lh_col, 'LineWidth', 0.8);
        end
        for k = 1:numel(rh_v)
            sl = S.rh_tck{rh_v(k)};
            if size(sl,1) < 2, continue; end
            plot3(ax, sl(:,1), sl(:,2), sl(:,3), '-', ...
                'Color', rh_col, 'LineWidth', 0.8);
        end

        hold(ax,'off');

        % Restore camera or set default view
        if ~isempty(prev_view)
            set(ax, 'CameraPosition', prev_view(1,:), ...
                    'CameraTarget',   prev_view(2,:), ...
                    'CameraUpVector', prev_view(3,:));
        else
            view(ax, 3);
        end

        n = numel(lh_v) + numel(rh_v);
        title(ax, sprintf('Streamlines  (n=%d)', n), 'Color','w', 'FontSize',11);
    end

end  % cortical_DWI_browser


