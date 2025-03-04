#!/bin/bash
# Besides this comment every single line was generated by LLM. Amazing.

# Check if file is provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <csv_file>"
    exit 1
fi

# Use awk to process the file
awk -F, '
BEGIN {
    print "Server Statistics:"
    print "================="
}

{
    server = $1
    status = $2
    
    # Skip empty lines
    if (server == "") next
    
    # Increment total count for this server
    total[server]++
    
    # Count successes and failures
    if (status == "success") {
        successes[server]++
    } else if (status != "") {
        failures[server,status]++
    }
}

END {
    # Create a sorted array of server names
    n = asorti(total, servers)
    
    # Print statistics for each server in alphabetical order
    for (i = 1; i <= n; i++) {
        server = servers[i]
        success_count = (successes[server] ? successes[server] : 0)
        success_percent = (success_count / total[server] * 100)
        
        print "\n" server ":"
        print "  Total appearances: " total[server]
        printf "  Successful: %d (%.1f%%)\n", success_count, success_percent
        
        # Count how many different failure types we have
        failure_count = 0
        failure_total = 0
        for (key in failures) {
            split(key, arr, SUBSEP)
            if (arr[1] == server) {
                failure_count++
                failure_total += failures[key]
            }
        }
        
        if (failure_count > 0) {
            print "  Failures:"
            # Create a sorted array of failure types for this server
            delete failure_types
            for (key in failures) {
                split(key, arr, SUBSEP)
                if (arr[1] == server) {
                    failure_types[arr[2]] = failures[key]
                }
            }
            # Print failure types in sorted order
            n_failures = asorti(failure_types, sorted_types)
            for (j = 1; j <= n_failures; j++) {
                type = sorted_types[j]
                count = failure_types[type]
                percent = (count / total[server] * 100)
                printf "    - %s: %d (%.1f%%)\n", type, count, percent
            }
            printf "  Total failure rate: %.1f%%\n", (failure_total / total[server] * 100)
            
            # Store information for summary tables
            if (failure_total == total[server]) {
                completely_failed[server] = 1
                if (failure_types["sunbeam_deploy"] == total[server]) {
                    failed_deploy[server] = 1
                }
                if (failure_types["sunbeam_prepare_env"] == total[server]) {
                    failed_prepare[server] = 1
                }
            }
        } else if (success_count < total[server]) {
            print "  Failures: None"
        }
        
        # Store information about 100% successful servers
        if (success_count == total[server]) {
            completely_successful[server] = 1
        }
    }
    
    # Count entries for each summary to determine if they should be displayed
    success_count = 0
    fail_count = 0
    deploy_fail_count = 0
    prepare_fail_count = 0
    
    for (server in completely_successful) success_count++
    for (server in completely_failed) fail_count++
    for (server in failed_deploy) deploy_fail_count++
    for (server in failed_prepare) prepare_fail_count++
    
    # Print summary of 100% successful servers if any exist
    if (success_count > 0) {
        print "\n\nServers with 100% Success Rate:"
        print "=============================="
        for (i = 1; i <= n; i++) {
            server = servers[i]
            if (completely_successful[server]) {
                printf "%s (%d)\n", server, total[server]
            }
        }
    }
    
    # Print summary of 100% failed servers if any exist
    if (fail_count > 0) {
        print "\n\nServers with 100% Failure Rate:"
        print "=============================="
        for (i = 1; i <= n; i++) {
            server = servers[i]
            if (completely_failed[server]) {
                printf "%s (%d)\n", server, total[server]
            }
        }
    }
    
    # Print summary of 100% failed servers due to sunbeam_deploy if any exist
    if (deploy_fail_count > 0) {
        print "\n\nServers with 100% Failure Rate due to sunbeam_deploy:"
        print "================================================"
        for (i = 1; i <= n; i++) {
            server = servers[i]
            if (failed_deploy[server]) {
                printf "%s (%d)\n", server, total[server]
            }
        }
    }

    # Print summary of 100% failed servers due to sunbeam_prepare_env if any exist
    if (prepare_fail_count > 0) {
        print "\n\nServers with 100% Failure Rate due to sunbeam_prepare_env:"
        print "=================================================="
        for (i = 1; i <= n; i++) {
            server = servers[i]
            if (failed_prepare[server]) {
                printf "%s (%d)\n", server, total[server]
            }
        }
    }
}' "$1"