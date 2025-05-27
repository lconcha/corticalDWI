#!/bin/bash

f=$1


TITLE="$f"
XLABEL="Depth (steps)"
YLABEL="Value"

gnuplot <<EOF
  set title "$TITLE"
  set xlabel "$XLABEL"
  set ylabel "$YLABEL"
  set terminal dumb
  plot "$f" using 1 with points pointtype 24
EOF


