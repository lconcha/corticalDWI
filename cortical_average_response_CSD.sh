#!/bin/bash
source `which my_do_cmd`

help() {
  echo "
  Usage:
    $(basename $0)

  Compute group-average response functions (wm,gm,csf)
  from all subjects inside SUBJECTS_DIR.
  "
}

groupdir=${SUBJECTS_DIR}/average_response

mkdir -p $groupdir

group_wm=${groupdir}/average_response_wm.txt
group_gm=${groupdir}/average_response_gm.txt
group_csf=${groupdir}/average_response_csf.txt

echolor green "[INFO] Computing average WM response"
my_do_cmd responsemean \
  $(fd response_wm.txt ${SUBJECTS_DIR} | tr '\n' ' ') \
  $group_wm

echolor green "[INFO] Computing average GM response"
my_do_cmd responsemean \
  $(fd response_gm.txt ${SUBJECTS_DIR} | tr '\n' ' ') \
  $group_gm

echolor green "[INFO] Computing average CSF response"
my_do_cmd responsemean \
  $(fd response_csf.txt ${SUBJECTS_DIR} | tr '\n' ' ') \
  $group_csf

echolor green "[INFO] Group-average response functions saved in:"
echolor green "  $groupdir"