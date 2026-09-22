#!/usr/bin/env python3
"""Usage: cortical_validate_tsf.py <tsf_file>

Exits 0 if the .tsf file parses cleanly (its streamline count matches its
header), non-zero otherwise. Reuses cortical_browser's own tsf reader, so a
file that passes this check is guaranteed to load correctly in the browser
too. A non-finite (NaN/Inf) sample point is indistinguishable, in the tsf
binary format, from the delimiter MRtrix uses between streamlines' scalar
arrays, so a mismatch here almost always means the sampled map had NaNs that
weren't sanitized before tcksample/tcksamplefixels ran.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cortical_browser'))
from cortical_io import read_mrtrix_tsf


def main():
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} <tsf_file>', file=sys.stderr)
        sys.exit(2)

    path = sys.argv[1]
    try:
        read_mrtrix_tsf(path)
    except Exception as e:
        print(f'[INVALID] {path}: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
