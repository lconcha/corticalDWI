#!/bin/bash

f=$1


TITLE=$(basename $f)
XLABEL="Depth (steps)"
YLABEL="Value"

gnuplot <<EOF
  set title "$TITLE"
  set xlabel "$XLABEL"
  set terminal dumb
  unset grid
  #unset xtics
  #unset ytics
  #unset border
  plot "$f" using 1 with points pointtype "X"
EOF


