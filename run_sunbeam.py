#!/usr/bin/env python3

import datetime
import json
import os
import re
import requests
import sys
import time

from dotenv import load_dotenv
from pathlib import Path
from urllib.request import urlopen


class GitHubWorkflowAPI:
    def __init__(self, token, owner, repo):
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.owner = owner
        self.repo = repo

    def get_workflow_runs(self, workflow_id, branch=None, per_page=100, status=None):
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows/{workflow_id}/runs"

        params = {"per_page": per_page}

        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        return response.json()

    def format_workflow_runs(self, runs_data):
        formatted_runs = []

        for run in runs_data.get("workflow_runs", []):
            formatted_run = {
                "id": run["id"],
                "name": run["name"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "branch": run["head_branch"],
                "commit_sha": run["head_sha"][:7],
                "url": run["html_url"],
            }
            formatted_runs.append(formatted_run)

        return formatted_runs

    def delete_workflow_run(self, run_id):
        """
        Delete a specific workflow run

        Args:
            run_id (int): The ID of the workflow run to delete
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()

    def get_run_steps(self, run_id):
        url = (
            f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/jobs"
        )
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        jobs_data = response.json()
        result = []

        for job in jobs_data.get("jobs", []):
            job_info = {
                "job_name": job["name"],
                "job_status": job["conclusion"] or job["status"],
                "steps": [],
            }

            for step in job.get("steps", []):
                if "Layer" in step["name"] and "Post " not in step["name"]:
                    layer = step["name"].replace("Layer ", "")
                    t1 = datetime.datetime.strptime(
                        step["started_at"], "%Y-%m-%dT%H:%M:%SZ"
                    )
                    t2 = datetime.datetime.strptime(
                        step["completed_at"], "%Y-%m-%dT%H:%M:%SZ"
                    )
                    step_info = {
                        "name": layer,
                        "status": step["conclusion"] or step["status"],
                        "started_at": step["started_at"],
                        "completed_at": step["completed_at"],
                        "elapsed": (t2 - t1).seconds,
                    }
                    job_info["steps"].append(step_info)

            result.append(job_info)

        return result

    def dispatch_workflow(self, workflow_id, ref="main", inputs=None):
        """
        Dispatch a workflow run

        Args:
            workflow_id (str): The workflow ID or filename
            ref (str): The git ref (branch/tag) to run the workflow on
            inputs (dict): Optional inputs required by the workflow

        Returns:
            bool: True if dispatch was successful
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows/{workflow_id}/dispatches"

        data = {"ref": ref}

        if inputs:
            data["inputs"] = inputs

        response = requests.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        # The API returns 204 No Content on success
        if response.status_code != 204:
            return None

        for _ in range(3600):
            time.sleep(1)  # Wait 1 second between checks
            runs = self.get_workflow_runs(workflow_id, branch=ref, status="in_progress")
            if runs.get("workflow_runs"):
                # formatted_runs = github_api.format_workflow_runs(runs)
                for run in runs.get("workflow_runs"):
                    if server in run["name"]:
                        return run["id"]
        return None

    def wait_for_run_completion(self, run_id, poll_interval=60, timeout=18000):
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}"
        elapsed_time = 0

        while elapsed_time < timeout:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            run_data = response.json()

            status = run_data.get("status")
            conclusion = run_data.get("conclusion")

            # If the run is complete, return the final status
            if status == "completed":
                return {
                    "status": status,
                    "conclusion": conclusion,
                    "url": run_data.get("html_url"),
                }

            time.sleep(poll_interval)
            elapsed_time += poll_interval

        raise TimeoutError(f"Run {run_id} did not complete within {timeout} seconds")

    def find_step_logs(self, run_id, step_name_contains, search_text):
        jobs_url = (
            f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/jobs"
        )
        jobs_response = requests.get(jobs_url, headers=self.headers)
        jobs_response.raise_for_status()
        jobs_data = jobs_response.json()

        matching_lines = []

        job = jobs_data.get("jobs", [])[0]
        for step in job.get("steps", []):
            if step_name_contains.lower() in step["name"].lower():
                logs_url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/jobs/{job['id']}/logs"
                logs_response = requests.get(logs_url, headers=self.headers)
                if logs_response.status_code == 200:
                    logs = logs_response.text
                    for line in logs.split("\n"):
                        if search_text in line and "Command failed" not in line:
                            matching_lines.append(line.strip())
                return matching_lines

        return matching_lines


def get_next_server(filename):
    servers = []
    while True:
        try:
            yield servers.pop(0)
        except IndexError:
            with open(filename, "rt") as f:
                while line := f.readline().strip():
                    servers.append(line)
            continue


def silo_in_use(github_api, silo):
    runs = github_api.get_workflow_runs(WORKFLOW_ID, status="in_progress")
    formatted_runs = github_api.format_workflow_runs(runs)
    if len([run for run in formatted_runs if silo in run["name"]]) > 0:
        return True
    runs = github_api.get_workflow_runs(WORKFLOW_ID, status="pending")
    formatted_runs = github_api.format_workflow_runs(runs)
    return len([run for run in formatted_runs if silo in run["name"]]) > 0


def wait_until_silo_is_available(github_api, silo):
    while silo_in_use(github_api, silo):
        time.sleep(300)
    print(f"{silo} is available")


def get_agent_data(api_url):
    with urlopen(api_url) as response:
        if response.getcode() != 200:
            print("Failed to retrieve agent data from Testflinger.")
            exit(1)
        return json.loads(response.read().decode())


def get_available_server(servers):
    AGENT_DATA_URL = "https://testflinger.canonical.com/v1/agents/data"
    data = get_agent_data(AGENT_DATA_URL)
    first_server = None

    for server in servers:
        if first_server and server == first_server:
            print("Did not find available server")
            return None
        if not first_server:
            first_server = server
        print(f"Checking {server}")
        for entry in data:
            if server in entry.get("queues", []):
                if entry["state"] == "waiting":
                    print(f"{server} is available")
                    return server


def start_server_in_silo(github_api, silo, server, deployment_branch, addon):
    inputs = {
        "substrate": silo.rsplit("-", 1)[0],
        "cluster": silo.rsplit("-", 1)[1],
        "container_series": "jammy",
        "deployment_branch": deployment_branch,
        "addon_id": addon,
        "machine_name": server,
    }
    runid = github_api.dispatch_workflow(
        workflow_id=WORKFLOW_ID, ref="justsunbeam", inputs=inputs
    )

    if runid:
        print("Workflow dispatched successfully")
        print(f"Run ID is {runid}")
    return runid


def get_failed_plugin(github_api, runid):
    matching_lines = github_api.find_step_logs(
        run_id=runid,
        step_name_contains="sunbeam_enable_plugins_all",
        search_text="sunbeam enable",
    )
    if matching_lines:
        return re.sub(".*yaml ", "", matching_lines[-1]).split()[0]
    return "unknown"


def collect_run_data(github_api, server, runid):
    status = github_api.wait_for_run_completion(runid)["conclusion"]
    for step in github_api.get_run_steps(runid)[0]["steps"]:
        print(
            f"{step['name']:40}: {step['status']:10}\t{step['started_at']:10}\t{step['completed_at']:10}\t{step['elapsed']:10}"
        )
    output = ""
    for step in github_api.get_run_steps(runid)[0]["steps"]:
        if step["status"] == "failure":
            status = step["name"]
        output += f",{step['name']},{step['status']},{step['elapsed']}"
    if status == "sunbeam_enable_plugins_all":
        status = get_failed_plugin(github_api, runid)
    output = f"{server},{status},{runid}{output}\n"
    return output


def save_data(output, filename):
    with open(f"{filename}.csv", "a") as f:
        f.write(output)


def stop_requested(silo):
    file_path = Path(f"{silo}.stop")
    return file_path.exists()


def update_stop_file(silo, server):
    file_path = Path(f"{silo}.stop")
    if server:
        with open(file_path, "w") as f:
            f.write(server)


def get_last_server(silo):
    file_path = Path(f"{silo}.stop")
    if not file_path.exists():
        return None
    with open(file_path, "r") as f:
        server = f.read()
    file_path.unlink(missing_ok=True)
    return server


load_dotenv()
TOKEN = os.environ.get("TOKEN")
OWNER = os.environ["OWNER"]
REPO = os.environ["REPO"]
WORKFLOW_ID = os.environ["WORKFLOW_ID"]
DEPLOYMENT_BRANCH = os.environ["DEPLOYMENT_BRANCH"]
ADDON = os.environ["ADDON"]


if __name__ == "__main__":
    silo = sys.argv[1]
    servers = get_next_server(f"{silo}.txt")
    if last_server := get_last_server(silo):
        print(f"Last used server was {last_server}")
        for server in servers:
            if server == last_server:
                break
            print(f"Skipping {server}")

    github_api = GitHubWorkflowAPI(TOKEN, OWNER, REPO)

    while True:
        wait_until_silo_is_available(github_api, silo)
        if stop_requested(silo):
            update_stop_file(silo, last_server)
            break
        if not (server := get_available_server(servers)):
            print("No server available, wating 10 minutes")
            time.sleep(600)
            continue
        last_server = server
        runid = start_server_in_silo(github_api, silo, server, DEPLOYMENT_BRANCH, ADDON)
        if not runid:
            print("Something went south")
            continue
        output = collect_run_data(github_api, server, runid)
        print(output)
        save_data(output, silo)
        time.sleep(60)
