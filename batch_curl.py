import json
import os
import platform
import subprocess
import time
from typing import List, Dict, Any


def _run_curl_command(command: list) -> Dict[str, Any]:
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    results = []
    for line in process.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return {
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "results": results,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def download_image_batch(
    downloads: List[Dict[str, str]],
    destination_folder: str,
    headers: Dict[str, str] | None = None,
    parallel_max: int = 16,
    use_http2: bool = True,
    sequential_delay: float = 1.0,
) -> Dict[str, Any]:

    if platform.system() != 'Linux':
        print("This function can only run on a Linux-based device.")
        return {"success": False, "return_code": 1, "results": [], "stdout": "", "stderr": ""}

    os.makedirs(destination_folder, exist_ok=True)

    def base_command():
        cmd = ["curl_chrome116", "--parallel", "--parallel-max", str(parallel_max)]
        if use_http2:
            cmd.insert(1, "--http2")
        cmd += [
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--write-out", "%{json}\\n",
        ]
        if headers:
            for name, value in headers.items():
                cmd.extend(["-H", f"{name}: {value}"])
        return cmd

    if not use_http2:
        combined = {"success": True, "return_code": 0, "results": [], "stdout": "", "stderr": ""}
        for i, download in enumerate(downloads):
            if i > 0:
                time.sleep(sequential_delay)
            cmd = base_command()
            output_path = os.path.join(destination_folder, download["file"])
            cmd.extend(["--output", output_path, download["url"]])
            result = _run_curl_command(cmd)
            combined["results"].extend(result["results"])
            combined["stdout"] += result["stdout"]
            combined["stderr"] += result["stderr"]
            if not result["success"]:
                combined["success"] = False
                combined["return_code"] = result["return_code"]
        return combined

    command = base_command()
    for download in downloads:
        output_path = os.path.join(destination_folder, download["file"])
        command.extend(["--output", output_path, download["url"]])

    return _run_curl_command(command)
