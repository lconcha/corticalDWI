#!/bin/bash

gifti=$1
txt=$2


wb_command -gifti-convert \
  ASCII $gifti \
  ${gifti%.gii}.xml

# This extracts ony the data from the bit xml file
awk '/<Data>/{flag=1; next} /<\/Data>/{flag=0} flag' \
 ${gifti%.gii}.xml  | \
 awk '{print $1}' > $txt