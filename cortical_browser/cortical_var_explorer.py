#!/usr/bin/env python3
"""
cortical_var_explorer.py — interactive viewer for the per-vertex, per-depth
linear regressions cortical_zscore_tsf.py --adjust-for fits and caches
(metric ~ covariate across the control cohort, see that script's own
docstring and _block_stats_adj/load_normative_stats_adj).

Three panels: LH surface, RH surface, scatter plot. Pick a metric and a
covariate from the dropdowns (a depth slider appears for a depth-wise
metric — a scalar one like thickness/curv/sulc has no depth axis), then
click a vertex on either surface — or type a hemisphere + vertex id into
the "Vertex" box and hit Enter/Go for the same effect without clicking:
the scatter shows one point per cohort
subject (covariate on x, that subject's raw metric value on y, both read
straight from the normative HDF5 and the covariates table — never from a
z-scored file) plus the cached regression line, its slope/intercept, n, and
the two-sided p-value for the slope (H0: slope == 0).

At startup this loads into memory:
  - every metric's (a, b, resid_sd, se_b, p, n) arrays from each
    <TEMPLATE>_multivariate_zscore_stats_adj-<tag>.npz already built under
    templates/normative/ — one such cache exists per covariate you've
    already run `cortical_zscore_tsf.py --stats-only --adjust-for <col>`
    for; the covariate dropdown is empty until at least one exists. A cache
    built before this viewer existed (no stored p-value) is skipped with a
    warning instead of crashing — rebuild it with --stats-only to pick it up.
  - the covariates table (same resolution as --adjust-for: --covariates, else
    <subjects_dir>/bids/participants.tsv, else <subjects_dir>/templates/covariates.tsv)

The normative HDF5 itself is NOT fully materialized into memory — lh_M/rh_M
can be several GB (nVerts x nDepths x nSubjects x nMetrics); a per-subject
raw-value query for one clicked vertex is instead read on demand from the
still-open HDF5 file, which is cheap (that file's own chunking puts a full
vertex's depth+subject+metric data in a single chunk — see
cortical_create_normative_data_from_tsf.py's own comment on it).

Usage:
    python cortical_var_explorer.py [subjects_dir] [--port 8788]
                                     [--covariates FILE] [--covariate-id-col COL]
"""
import os, sys, json, glob, argparse, threading, time, webbrowser, html as htmlmod
import numpy as np
import h5py
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortical_io import read_covariates, default_covariates_path
from cortical_browser_config import TEMPLATE, print_config_report

NIIVUE_CDN = 'https://cdn.jsdelivr.net/npm/@niivue/niivue/dist/index.js'
PLOTLY_CDN = 'https://cdn.plot.ly/plotly-2.35.2.min.js'

_WEB_DIR = os.path.dirname(os.path.abspath(__file__))


def _read_web_file(name):
    with open(os.path.join(_WEB_DIR, name), encoding='utf-8') as f:
        return f.read()


_HTML = _read_web_file('var_explorer.html')
_JS   = _read_web_file('var_explorer.js')


def _jsonable(arr):
    """numpy array -> nested Python list with NaN/inf replaced by None, so
    the front end draws a gap/skips a point rather than choking on NaN
    (which isn't valid JSON)."""
    a = np.asarray(arr, dtype=np.float64)
    conv = lambda x: (float(x) if np.isfinite(x) else None)
    if a.ndim == 0:
        return conv(a)
    return [conv(v) for v in a]


def _metric_is_scalar(h5f, mi, sample=8):
    """True if metric index mi has no real depth axis (thickness/curv/sulc):
    the normative builder broadcasts a scalar metric's single value across
    every depth column (see build_normative_stack's own comment), so
    checking a few vertices' depth columns for exact (NaN-aware) equality
    against depth 0 is an exact test, not a heuristic — a genuinely
    depth-wise metric would need an implausible coincidence to pass it."""
    d = h5f['lh_M']
    if d.shape[1] <= 1:
        return True
    n = min(sample, d.shape[0])
    blk = d[:n, :, :, mi]
    ref = blk[:, 0:1, :]
    with np.errstate(invalid='ignore'):
        return bool(np.all((blk == ref) | (np.isnan(blk) & np.isnan(ref))))


def load_adjusted_caches(normative_dir, template, metrics):
    """{covariate_label: {(hemi, metric_idx): {'a':.., 'b':.., 'rs':.., 'se':.., 'p':.., 'n':..}}}
    from every *_zscore_stats_adj-*.npz already built under normative_dir.
    Each array for every (hemi, metric_idx) pair is loaded fully into
    memory (small — one float per vertex+depth, no subject axis), keyed by
    the covariate's own stored label (recovered from inside the file, not
    guessed from its sanitized filename tag)."""
    adj = {}
    pattern = os.path.join(normative_dir, f'{template}_multivariate_zscore_stats_adj-*.npz')
    for path in sorted(glob.glob(pattern)):
        try:
            z = np.load(path)
        except Exception as e:
            print(f'  [skip] {path}: unreadable ({e})')
            continue
        if 'covariate_label' not in z.files:
            print(f'  [skip] {path}: no stored covariate_label (built before cortical_var_explorer.py existed) — '
                  f'rebuild with cortical_zscore_tsf.py --stats-only --adjust-for <col> to pick it up')
            continue
        label = str(z['covariate_label'])
        n_metrics = int(z['n_metrics'])
        if n_metrics != len(metrics):
            print(f'  [skip] {path}: built for {n_metrics} metrics, current normative data has {len(metrics)}')
            continue
        if n_metrics and f'lh_0_p' not in z.files:
            print(f'  [skip] {path}: no stored p-value (built before cortical_var_explorer.py existed) — '
                  f'rebuild with cortical_zscore_tsf.py --stats-only --adjust-for {label} to pick it up')
            continue
        entry = {}
        for h in ('lh', 'rh'):
            for i in range(n_metrics):
                entry[(h, i)] = {k: z[f'{h}_{i}_{k}'] for k in ('a', 'b', 'rs', 'se', 'p', 'n')}
        adj[label] = entry
        print(f'  covariate available: {label!r}  ({os.path.basename(path)})')
    return adj


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('subjects_dir', nargs='?', default=os.environ.get('SUBJECTS_DIR'))
    ap.add_argument('--port', type=int, default=8788)
    ap.add_argument('--covariates', metavar='FILE', help='overrides the usual bids/participants.tsv / '
                     'templates/covariates.tsv auto-detection')
    ap.add_argument('--covariate-id-col', default='participant_id', metavar='COL')
    args = ap.parse_args()
    if not args.subjects_dir:
        sys.exit('subjects_dir not given and SUBJECTS_DIR is not set')

    print_config_report(args.subjects_dir)

    h5_path = os.path.join(args.subjects_dir, 'templates', 'normative', f'{TEMPLATE}_multivariate.h5')
    if not os.path.isfile(h5_path):
        sys.exit(f'Normative data not found: {h5_path}')

    surf_paths = {hemi: os.path.join(args.subjects_dir, 'templates', 'surf', f'{hemi}_very-inflated.{TEMPLATE}.surf.gii')
                  for hemi in ('lh', 'rh')}
    missing = [p for p in surf_paths.values() if not os.path.isfile(p)]
    if missing:
        sys.exit('Surface(s) not found: ' + ', '.join(missing))

    h5f = h5py.File(h5_path, 'r')   # kept open for the server's lifetime; per-vertex reads are on demand
    metrics = [m.decode() if isinstance(m, bytes) else m for m in h5f['metrics'][:]]
    norm_subjects = [x.decode() if isinstance(x, bytes) else x for x in h5f['subjects'][:]]
    n_depths = h5f['lh_M'].shape[1]
    print(f'Normative data: {len(norm_subjects)} subjects, {len(metrics)} metrics ({", ".join(metrics)}), '
          f'{n_depths} depths')
    is_scalar = [_metric_is_scalar(h5f, i) for i in range(len(metrics))]

    normative_dir = os.path.join(args.subjects_dir, 'templates', 'normative')
    print('Scanning for covariate-adjusted fits already built there…')
    adj = load_adjusted_caches(normative_dir, TEMPLATE, metrics)
    if not adj:
        print('  none found — run `cortical_zscore_tsf.py --stats-only <subjects_dir> --adjust-for <col>` '
              'for whichever covariate you want to inspect first.')

    covariates_path = args.covariates or default_covariates_path(args.subjects_dir)
    cov_values = {}   # covariate_label -> (nSubjects,) float64, aligned to norm_subjects
    if adj:
        if not covariates_path or not os.path.isfile(covariates_path):
            print(f'  [warn] no covariates file found (checked --covariates, '
                  f'{args.subjects_dir}/bids/participants.tsv, {args.subjects_dir}/templates/covariates.tsv) — '
                  f'scatter points will be empty for every covariate')
        else:
            print(f'Covariates file: {covariates_path}')
            cov_table = read_covariates(covariates_path, id_col=args.covariate_id_col)
            for label in adj:
                vals = np.full(len(norm_subjects), np.nan, dtype=np.float64)
                for i, s in enumerate(norm_subjects):
                    v = cov_table.get(s, {}).get(label, float('nan'))
                    vals[i] = np.nan if isinstance(v, str) else v
                n_have = int(np.isfinite(vals).sum())
                print(f'  {label!r}: {n_have}/{len(norm_subjects)} cohort subjects have a value')
                cov_values[label] = vals

    def vertex_payload(hemi, mi, depth, covariate, vertex):
        a = adj[covariate][(hemi, mi)]
        depth = min(depth, a['a'].shape[1] - 1)
        fit = {k: (None if not np.isfinite(a[k][vertex, depth]) else float(a[k][vertex, depth]))
               for k in ('a', 'b', 'rs', 'se', 'p')}
        fit['n'] = int(a['n'][vertex, depth])
        y = np.asarray(h5f[f'{hemi}_M'][vertex, depth, :, mi], dtype=np.float64)
        x = cov_values.get(covariate, np.full(len(norm_subjects), np.nan))
        ok = np.isfinite(x) & np.isfinite(y)
        return {
            'x': _jsonable(x[ok]), 'y': _jsonable(y[ok]),
            'subjects': [norm_subjects[i] for i in np.flatnonzero(ok)],
            'fit': fit, 'metric': metrics[mi], 'covariate': covariate,
            'depth': depth, 'vertex': vertex, 'hemi': hemi,
        }

    metric_opts = '\n'.join(f'      <option value="{i}">{htmlmod.escape(m)}</option>' for i, m in enumerate(metrics))
    covariate_opts = ('\n'.join(f'      <option value="{htmlmod.escape(c)}">{htmlmod.escape(c)}</option>' for c in adj)
                       if adj else '      <option value="">(none built yet)</option>')

    base = f'http://localhost:{args.port}'
    subs = [
        ('__NIIVUE_CDN__', NIIVUE_CDN),
        ('__PLOTLY_CDN__', PLOTLY_CDN),
        ('__BASE_URL__', base),
        ('__METRIC_OPTIONS__', metric_opts),
        ('__COVARIATE_OPTIONS__', covariate_opts),
        ('__IS_SCALAR_JSON__', json.dumps(is_scalar)),
        ('__MAX_DEPTH__', str(n_depths - 1)),
        ('__TEMPLATE__', TEMPLATE),
        ('__N_VERTS_LH__', str(h5f['lh_M'].shape[0])),
        ('__N_VERTS_RH__', str(h5f['rh_M'].shape[0])),
    ]
    html, js = _HTML, _JS
    for k, v in subs:
        html = html.replace(k, v)
        js = js.replace(k, v)
    html_bytes = html.encode('utf-8')
    js_bytes = js.encode('utf-8')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/', '/index.html'):
                self._reply(200, 'text/html; charset=utf-8', html_bytes)
            elif path == '/static/var_explorer.js':
                self._reply(200, 'text/javascript; charset=utf-8', js_bytes)
            elif path in ('/surf/lh.surf.gii', '/surf/rh.surf.gii'):
                # NiiVue's mesh loader picks its parser from the URL's own
                # filename extension (ignoring query strings) — an
                # extensionless path like the old /surf/lh here silently
                # failed to load as a mesh at all.
                hemi = path.rsplit('/', 1)[-1].split('.', 1)[0]
                with open(surf_paths[hemi], 'rb') as fh:
                    self._reply(200, 'application/octet-stream', fh.read(), cacheable=True)
            elif path == '/vertex':
                self._serve_vertex()
            else:
                self._reply(404, 'text/plain', b'Not found\n')

        def _serve_vertex(self):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            try:
                hemi = q['hemi'][0]
                mi = int(q['metric'][0])
                depth = int(q.get('depth', ['0'])[0])
                covariate = q['covariate'][0]
                vertex = int(q['vertex'][0])
                if (hemi not in ('lh', 'rh') or covariate not in adj or not (0 <= mi < len(metrics))
                        or not (0 <= vertex < h5f[f'{hemi}_M'].shape[0]) or depth < 0):
                    raise ValueError('bad parameter')
            except (KeyError, ValueError):
                self._reply(400, 'text/plain', b'bad request\n')
                return
            payload = vertex_payload(hemi, mi, depth, covariate, vertex)
            self._reply(200, 'application/json', json.dumps(payload).encode('utf-8'))

        def _reply(self, code, ctype, data, cacheable=False):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if cacheable else 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = HTTPServer(('localhost', args.port), Handler)
    url = f'{base}/'
    print(f'\nViewer: {url}')
    print('Ctrl+C to quit.\n')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        h5f.close()
        print('Done.')


if __name__ == '__main__':
    main()
