function cortical_DWI_browser()
%CORTICAL_DWI_BROWSER  Interactive browser for cortical DWI depth-profile data.
%
%  Three surface panels: LH overlay, RH overlay, LH asymmetry (L-R)/L [%].
%  Panels 1 & 2 share colormap / CLim.  Panel 3 uses a diverging colormap.
%  A depth slider selects the data column shown on all surfaces.
%  Click any surface to select the nearest vertex and plot its depth profile.
%
%  Requires: read_surface, read_mrtrix_tsf, cortical_cell2mat (on path)

addpath(genpath('/misc/lauterbur2/lconcha/code/gifti'));
addpath(genpath('/home/inb/soporte/lanirem_software/mrtrix_3.0.4/matlab'));
addpath(genpath('/misc/lauterbur2/lconcha/code/cbrewer'));
addpath(genpath('/misc/lauterbur2/lconcha/code/corticalDWI'));

% ── Default paths ─────────────────────────────────────────────────────────
DEF_SUBJECTS_DIR = '/misc/sherrington/lconcha/TMP/glaucoma/fs_glaucoma';
DEF_SUBJ_ID      = 'sub-79864';

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
S.srf1         = [];   % trisurf handles
S.srf2         = [];
S.srf3         = [];
S.dot1         = [];   % selected-vertex markers
S.dot2         = [];
S.dot3         = [];
S.sel_vertex   = NaN;
S.hDepthLine   = [];   % xline handle for depth marker in ax4
S.hDepthLine2  = [];   % xline handle for depth marker in ax5

% ── Figure ────────────────────────────────────────────────────────────────
BG = [0.12 0.12 0.12];
hFig = uifigure('Name','Cortical DWI Browser','Position',[30 30 1750 970],...
    'Color', BG);

% Main 2-row grid ──────────────────────────────────────────────────────────
mainGL = uigridlayout(hFig, [2,1]);
mainGL.RowHeight   = {'3x', '1x'};
mainGL.ColumnWidth = {'1x'};
mainGL.Padding     = [5 5 5 5];
mainGL.RowSpacing  = 5;
mainGL.BackgroundColor = BG;

% ── Top row: five axes panels ─────────────────────────────────────────────
topGL = uigridlayout(mainGL, [1,5]);
topGL.Layout.Row    = 1;
topGL.Layout.Column = 1;
topGL.ColumnWidth   = {'1x','1x','1x','1x','1x'};
topGL.RowHeight     = {'1x'};
topGL.Padding       = [0 0 0 0];
topGL.ColumnSpacing = 5;
topGL.BackgroundColor = BG;

surfBG = [0.06 0.06 0.06];
plotBG = [0.14 0.14 0.14];
ax1 = uiaxes(topGL, 'BackgroundColor', surfBG, 'Color', surfBG);
ax1.Layout.Row=1; ax1.Layout.Column=1;
ax2 = uiaxes(topGL, 'BackgroundColor', surfBG, 'Color', surfBG);
ax2.Layout.Row=1; ax2.Layout.Column=2;
ax3 = uiaxes(topGL, 'BackgroundColor', surfBG, 'Color', surfBG);
ax3.Layout.Row=1; ax3.Layout.Column=3;
ax4 = uiaxes(topGL, 'BackgroundColor', plotBG, 'Color', plotBG);
ax4.Layout.Row=1; ax4.Layout.Column=4;
ax5 = uiaxes(topGL, 'BackgroundColor', plotBG, 'Color', plotBG);
ax5.Layout.Row=1; ax5.Layout.Column=5;

for ax = [ax1 ax2 ax3]
    axis(ax, 'equal');
    axis(ax, 'vis3d');
    ax.DataAspectRatio = [1 1 1];
    ax.XColor = 'none'; ax.YColor = 'none'; ax.ZColor = 'none';
end
title(ax1,'Left Hemisphere',        'Color','w','FontSize',11,'FontWeight','bold');
title(ax2,'Right Hemisphere',       'Color','w','FontSize',11,'FontWeight','bold');
title(ax3,'Asymmetry (L-R)/L [%]', 'Color','w','FontSize',11,'FontWeight','bold');
title(ax4,'Vertex depth profile',   'Color','w','FontSize',11,'FontWeight','bold');
title(ax5,'Asymmetry index',        'Color','w','FontSize',11,'FontWeight','bold');

for ax = [ax4 ax5]
    ax.XColor    = [0.75 0.75 0.75];
    ax.YColor    = [0.75 0.75 0.75];
    ax.GridColor = [0.35 0.35 0.35]; ax.GridAlpha = 0.5;
    ax.XGrid     = 'on'; ax.YGrid = 'on';
end

% ── Bottom row: control panel (4 rows × 8 cols) ───────────────────────────
%   Cols 1-3: scan controls  [label | field | button]
%   Cols 4-8: viz controls   [Depth | Data | Asym | Vertex# | Step]
%              R1 (labels):   Depth:   Data      Asym      Vertex#:  Step(mm):
%              R2 (boxes):    slider   clim(d)   clim(a)   vtx fld   step fld
%              R3 (dropdowns):depthval cmap(d)   cmap(a)   vtxhint   —
%              R4 (thin):     status (cols 1-3)
ctrlGL = uigridlayout(mainGL, [4, 8]);
ctrlGL.Layout.Row    = 2;
ctrlGL.Layout.Column = 1;
ctrlGL.ColumnWidth   = {100, '1.5x', 80, '2x', 130, 130, 100, 90};
ctrlGL.RowHeight     = {'1x','1x','1x', 18};
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

lbl_vtxhint = uilabel(ctrlGL,'Text','Click surface to select',...
    'FontSize',9,'FontColor',[0.55 0.55 0.55],'HorizontalAlignment','center');
lbl_vtxhint.Layout.Row=3; lbl_vtxhint.Layout.Column=7;

% ── Row 4 (status strip + invert checkboxes) ──────────────────────────────
chkInvert = uicheckbox(ctrlGL,'Text','Invert','Value',false,...
    'FontColor',LC,'ValueChangedFcn',@onInvertCmap);
chkInvert.Layout.Row=4; chkInvert.Layout.Column=5;

chkInvertAsym = uicheckbox(ctrlGL,'Text','Invert','Value',false,...
    'FontColor',LC,'ValueChangedFcn',@onInvertCmapAsym);
chkInvertAsym.Layout.Row=4; chkInvertAsym.Layout.Column=6;

lblStatus = uilabel(ctrlGL,'Text','Press Scan to discover TSF files.',...
    'FontSize',9,'FontColor',[0.55 0.80 0.55],'FontStyle','italic',...
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

        D = dir(fullfile(dwiDir, '**', '*.tsf'));
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

% ══════════════════════════════════════════════════════════════════════════
%  DATA LOADING
% ══════════════════════════════════════════════════════════════════════════

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
        S.dot1 = scatter3(ax1, 0,0,0, 120, 'r', 'filled', 'Visible','off');

        % Panel 2 – RH data
        S.srf2 = trisurf(rh.faces, ...
            rh.vertices(:,1), rh.vertices(:,2), rh.vertices(:,3), CR, ...
            'Parent', ax2, 'EdgeColor','none', 'FaceColor','interp');
        styleSurface(S.srf2);
        view(ax2, 90, 0);           % set camera BEFORE headlight
        setupLight(ax2);
        hold(ax2,'on');
        S.dot2 = scatter3(ax2, 0,0,0, 120, 'r', 'filled', 'Visible','off');

        % Panel 3 – Asymmetry on LH geometry
        S.srf3 = trisurf(lh.faces, ...
            lh.vertices(:,1), lh.vertices(:,2), lh.vertices(:,3), CA, ...
            'Parent', ax3, 'EdgeColor','none', 'FaceColor','interp');
        styleSurface(S.srf3);
        view(ax3, -90, 0);          % set camera BEFORE headlight
        setupLight(ax3);
        hold(ax3,'on');
        S.dot3 = scatter3(ax3, 0,0,0, 120, 'r', 'filled', 'Visible','off');

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
                'Color','w', 'FontSize',8, 'TickDirection','out');
            cb.Label.Color = 'w';
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
        updatePlot();
    end

    function updateMarkers(v)
        if isempty(S.srf1), return; end
        vl = S.srf1.Vertices;
        vr = S.srf2.Vertices;
        if v < 1 || v > size(vl,1), return; end
        set(S.dot1,'XData',vl(v,1),'YData',vl(v,2),'ZData',vl(v,3),'Visible','on');
        set(S.dot2,'XData',vr(v,1),'YData',vr(v,2),'ZData',vr(v,3),'Visible','on');
        set(S.dot3,'XData',vl(v,1),'YData',vl(v,2),'ZData',vl(v,3),'Visible','on');
    end

% ══════════════════════════════════════════════════════════════════════════
%  DEPTH PROFILE PLOT
% ══════════════════════════════════════════════════════════════════════════

    function updatePlot()
        if isnan(S.sel_vertex) || isempty(S.lh_M), return; end
        v      = S.sel_vertex;
        depths = (0 : S.nDepths-1) .* S.step_size;
        d_lh   = double(S.lh_M(v,:));
        d_rh   = double(S.rh_M(v,:));

        if ~isempty(S.hDepthLine) && isvalid(S.hDepthLine)
            delete(S.hDepthLine);
        end
        S.hDepthLine = [];
        cla(ax4);
        hold(ax4, 'on');
        plot(ax4, depths, d_lh, '-o', 'Color',[0.40 0.70 1.00], ...
            'LineWidth',2, 'MarkerSize',3, 'DisplayName','LH');
        plot(ax4, depths, d_rh, '-o', 'Color',[1.00 0.52 0.30], ...
            'LineWidth',2, 'MarkerSize',3, 'DisplayName','RH');
        hold(ax4, 'off');
        legend(ax4, {'LH','RH'}, 'TextColor','w', ...
            'Color','none', 'EdgeColor','none', 'Location','best');
        xlabel(ax4, 'Depth from pial surface (mm)', 'Color',[0.80 0.80 0.80]);
        ylabel(ax4, S.metric_name, 'Color',[0.80 0.80 0.80], 'Interpreter','none');
        title(ax4, sprintf('Vertex %d', v), 'Color','w');
        ax4.XColor = [0.70 0.70 0.70]; ax4.YColor = [0.70 0.70 0.70];
        ax4.Color  = [0.14 0.14 0.14];
        ax4.XGrid  = 'on'; ax4.YGrid = 'on';

        updateAsymPlot();
        updateDepthLine();
    end

    function updateAsymPlot()
        if isnan(S.sel_vertex) || isempty(S.lh_M), return; end
        v      = S.sel_vertex;
        depths = (0 : S.nDepths-1) .* S.step_size;
        d_lh   = double(S.lh_M(v,:));
        d_rh   = double(S.rh_M(v,:));
        d_asym = (d_lh - d_rh) ./ ((d_lh + d_rh) ./ 2);
        d_asym(~isfinite(d_asym)) = NaN;

        if ~isempty(S.hDepthLine2) && isvalid(S.hDepthLine2)
            delete(S.hDepthLine2);
        end
        S.hDepthLine2 = [];
        cla(ax5);
        hold(ax5, 'on');
        asymcolor = [0.8 0.8 0.8];
        plot(ax5, depths, d_asym, '-s', 'Color',asymcolor, ...
            'LineWidth',2, 'MarkerSize',3, 'DisplayName','Asym index');
        yline(ax5, 0, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1, ...
            'HandleVisibility','off');
        hold(ax5, 'off');
        xlabel(ax5, 'Depth from pial surface (mm)', 'Color',asymcolor);
        ylabel(ax5, 'Asymmetry index',              'Color',asymcolor);
        title(ax5, sprintf('Vertex %d', v), 'Color','w');
        ax5.XColor = [0.70 0.70 0.70]; ax5.YColor = [0.70 0.70 0.70];
        ax5.Color  = [0.14 0.14 0.14];
        ax5.XGrid  = 'on'; ax5.YGrid = 'on';
        %ax5.YLim   = [-1*max(abs(d_asym)) max(abs(d_asym))];
        ax5.YLim  = [-1 1];

        % depth marker for ax5
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

    function s = shortenPath(p)
        if length(p) <= 42
            s = p;
        else
            s = ['...' p(end-38:end)];
        end
    end

end  % cortical_DWI_browser
