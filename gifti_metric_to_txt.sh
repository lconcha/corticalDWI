#!/bin/bash

help() {
  echo "
  Usage: $(basename $0) <gifti_file> <output_txt_file>
  
  <gifti_file>      input GIFTI file (with .gii extension)
  <output_txt_file> output text file to save the data
  
  Converts a GIFTI file to a text file containing the data.
  
  This script uses wb_command to convert the GIFTI file to XML,
  then extracts the data using an awk hack. Ugly, but quick.
  "
}

if [ $# -ne 2 ]
then
  echolor red "Wrong number of arguments"
  help
  exit 0
fi


gifti=$1
txt=$2


wb_command -gifti-convert \
  ASCII $gifti \
  ${gifti%.gii}.xml

# This extracts ony the data from the bit xml file
awk '/<Data>/{flag=1; next} /<\/Data>/{flag=0} flag' \
 ${gifti%.gii}.xml  | \
 awk '{print $1}' > $txt