#!/bin/bash

cat tor3*.csv | sed "s/pro/ubuntu_pro/" > all_data.csv
./show_details.sh all_data.csv
echo "---------------------------------------------------------------"
cat all_data.csv | cut -d"," -f2 | sort | uniq -c | sort -r -n