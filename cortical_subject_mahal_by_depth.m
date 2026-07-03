
function [Mahal_vector, zscores] = cortical_subject_mahal_by_depth(idx,subject_multidim,lh_M,rh_M)
% Mahal_vector = cortical_subject_mahal_by_depth(idx,subject_multidim,lh_M,rh_M)
%
% Returns a 1d vector of Mahalanobis distances wrt to the multidimensional
% centroid of normative data.
%
% Inputs:
% idx              : Holds the index to query. Thus, it is a single index.
% subject_multidim : A vector of features of of one vertex.
%                    It has size [nDepths nMetrics]
% lh_M and rh_M    : Multidimensional normative values.
%                    Both have size [nVertices nDepths nSubjects nMetrics]
%
% Outputs
% subject_mahal_by_depth : Vector of Mahal distances with size [1 nDepths]
% zcores                 : A [nDepths nMetrics] matrix of univariate
%                          z-scores.
%
% LU15 (0N(H4
% INB-UNAM
% June, 2026
% lconcha@unam.mx

if size(subject_multidim,2) ~= size(lh_M,4)
  subject_multidim = subject_multidim';
end


maxDepth = size(lh_M,2);
nMetrics = size(lh_M,4);
Mahal_vector = nan(maxDepth,1);
zscores      = nan(maxDepth,nMetrics);

% NaN-padded depths (fewer subjects/streamlines reaching that depth) make
% the cohort covariance rank-deficient at times, which mahal() reports via
% this warning on every call — expected and handled (yields NaN below), so
% silence it rather than spamming the console once per depth.
warnState = warning('off', 'MATLAB:nearlySingularMatrix');

for depth = 1 : maxDepth
    this_normative_multidim = [squeeze(lh_M(idx,depth,:,:)); squeeze(rh_M(idx,depth,:,:))]; %combine both hemispheres to improve estimation of covariance.
    valid_rows = ~any(isnan(this_normative_multidim), 2);
    this_normative_multidim = this_normative_multidim(valid_rows, :);

    this_subject_multidim   = squeeze(subject_multidim(depth,:));
    if any(isnan(this_subject_multidim)) 
       %fprintf(1,'Depth %d: Subject has NaN values for one or more metrics. Returning NaN.\n', depth);
       this_mahal = NaN;
    elseif size(this_normative_multidim, 1) <= nMetrics
        fprintf(1,'Depth %d: Not enough valid subjects (%d) to compute Mahalanobis distance for %d metrics. Returning NaN.\n', ...
            depth, size(this_normative_multidim, 1), nMetrics);
        this_mahal = NaN;
    else
        this_mahal = mahal(this_subject_multidim , this_normative_multidim);
    end

    Mahal_vector(depth) = this_mahal;

    this_mu = mean(this_normative_multidim,1, 'omitnan');
    this_sd = std (this_normative_multidim,1, 'omitnan');
    this_z  = (this_subject_multidim - this_mu) ./ this_sd;
    zscores(depth,:) = this_z;
end

warning(warnState);


