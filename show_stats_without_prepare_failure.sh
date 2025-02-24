#!/bin/bash

cat tor3*.csv | sed "s/pro/ubuntu_pro/" | grep -v "sunbeam_prepare_env,failure" > all_data_no_prepare_env.csv
./show_details.sh all_data_no_prepare_env.csv
echo "---------------------------------------------------------------"
cat all_data_no_prepare_env.csv | cut -d"," -f2 | sort | uniq -c | sort -r -n
