#!/bin/bash
# This is just a wrapper script to call the cortical_var_explorer.py script with the correct arguments.

thisDir=$(readlink -f `dirname $0`)
$thisDir/cortical_browser/cortical_var_explorer.py $1 $2 $3 $4 $5 $6 $7 $8 $9
