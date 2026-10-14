#!/bin/bash
# This is just a wrapper script to call the cortical_qc.py script with the correct arguments.

thisDir=$(readlink -f `dirname $0`)
$thisDir/cortical_qc/cortical_qc.py "$@"
