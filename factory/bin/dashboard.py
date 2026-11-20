"""Serve the live factory board on loopback for this installation."""

import argparse
import hmac
import html
import http.client
import json
import re
import subprocess
import sys
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_hex
from threading import Thread
from urllib.parse import unquote, urlsplit

from projects import HOME, project_dir, registry, read_json, write_json
from runtime import WINDOWS, exclusive_lock

FACTORY = Path(__file__).resolve().parents[1]
STATE = HOME / "dashboard.json"
LOCK = HOME / "dashboard.lock"
HOST = "127.0.0.1"
CONTROL = "/_factory_dashboard"
JOB_ID = re.compile(r"[0-9]{3,}-[a-z0-9-]+")
ARTIFACT = re.compile(r"[a-z0-9-]+\.md")
ROUND = re.compile(r"round-[0-9]+")


def job_route(parts, directory):
    if not parts:
        return directory
    if not JOB_ID.fullmatch(parts[0]):
        return False
    if len(parts) == 1:
        return directory
    if len(parts) == 2:
        if directory:
            return bool(ROUND.fullmatch(parts[1]))
        return parts[1] == "job.json" or bool(ARTIFACT.fullmatch(parts[1]))
    return (len(parts) == 3 and not directory and bool(ROUND.fullmatch(parts[1]))
            and bool(ARTIFACT.fullmatch(parts[2])))


def public_job(job):
    fields = ("id", "issue", "title", "issue_url", "pr", "pr_url", "mode", "stage", "round",
              "intake", "agents", "handoff", "handoff_reason", "cost_usd", "started", "ended")
    return {key: job.get(key) for key in fields}


def board_data():
    projects = []
    jobs = []
    records = registry()["projects"]
    names = Counter(record["name"] for record in records.values())
    for project_id, record in records.items():
        name = record["name"]
        if names[name] > 1:
            name = f"{name} ({project_id[:8]})"
        projects.append({"id": project_id, "name": name, "concurrency": record["concurrency"]})
        directory = project_dir(project_id) / "jobs"
        for path in directory.glob("*/job.json"):
            if path.resolve() != path or not JOB_ID.fullmatch(path.parent.name):
                continue
            job = read_json(path, {})
            if job.get("id") == path.parent.name and job.get("project_id") == project_id:
                jobs.append({**public_job(job), "project_id": project_id, "project_name": name})
    return {"projects": projects, "jobs": sorted(jobs, key=lambda j: j.get("started") or "")}


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_content(self, data=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def is_local_host(self):
        return self.headers.get("Host") == f"{HOST}:{self.server.server_port}"

    def has_token(self):
        token = self.headers.get("X-Factory-Dashboard", "").encode("utf-8")
        return hmac.compare_digest(token, self.server.control_token)

    def do_GET(self):
        if not self.is_local_host():
            self.send_error(403)
            return
        path = unquote(urlsplit(self.path).path)
        if path == CONTROL and self.has_token():
            self.send_content()
        elif path in ("/", "/dashboard.html"):
            self.send_content((FACTORY / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/projects.json":
            self.send_content(json.dumps(board_data()).encode(), "application/json")
        elif path.startswith("/projects/"):
            parts = path.split("/", 4)
            if len(parts) == 5 and parts[3] == "jobs" and parts[2] in registry()["projects"]:
                self.send_job(project_dir(parts[2]) / "jobs", parts[4])
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != CONTROL or not self.is_local_host() or not self.has_token():
            self.send_error(403)
            return
        self.send_content()
        Thread(target=self.server.shutdown, daemon=True).start()

    def send_job(self, jobs, route):
        directory = not route or route.endswith("/")
        parts = route.removesuffix("/").split("/") if route else []
        source = jobs.joinpath(*parts)
        if not job_route(parts, directory) or source.resolve() != source:
            self.send_error(404)
            return
        if directory:
            self.send_listing(parts, source)
            return
        try:
            data = json.dumps(public_job(read_json(source))).encode() if source.name == "job.json" else source.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            self.send_error(404)
            return
        self.send_content(data)

    def send_listing(self, parts, source):
        if parts and not source.is_dir():
            self.send_error(404)
            return
        entries = []
        if source.is_dir():
            for child in sorted(source.iterdir()):
                directory = child.is_dir()
                if child.resolve() == child and job_route(parts + [child.name], directory):
                    name = html.escape(child.name) + ("/" if directory else "")
                    entries.append(f'<li><a href="{name}">{name}</a></li>')
        self.send_content(("<!doctype html><meta charset=utf-8><ul>" + "".join(entries) + "</ul>").encode(),
                          "text/html; charset=utf-8")


def request(state, method):
    try:
        port, token = state["port"], state["token"]
        connection = http.client.HTTPConnection(HOST, port, timeout=1)
        try:
            connection.request(method, CONTROL, headers={"X-Factory-Dashboard": token})
            response = connection.getresponse()
            response.read()
            return response.status == 200
        finally:
            connection.close()
    except (OSError, KeyError, TypeError, ValueError, http.client.HTTPException):
        return False


def read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def serve(token):
    if not (FACTORY / "dashboard.html").is_file():
        raise OSError("dashboard.html is missing")
    preferred = read_state().get("port", 0)
    try:
        listener = ThreadingHTTPServer((HOST, preferred), DashboardHandler)
    except OSError:
        listener = ThreadingHTTPServer((HOST, 0), DashboardHandler)
    with listener as server:
        server.control_token = token.encode("ascii")
        write_json(STATE, {"port": server.server_port, "token": token})
        server.serve_forever()


def start():
    with exclusive_lock(LOCK):
        state = read_state()
        if not request(state, "GET"):
            token = token_hex(24)
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "serve", token],
                cwd=Path(sys.executable).resolve().parent,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=flags, start_new_session=not WINDOWS,
            )
            for _ in range(100):
                state = read_state()
                if isinstance(state, dict) and state.get("token") == token and request(state, "GET"):
                    break
                if process.poll() is not None:
                    raise OSError("the live dashboard process exited during startup")
                time.sleep(0.05)
            else:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired as error:
                    raise OSError("the dashboard process did not exit after startup failed") from error
                raise OSError(f"the live dashboard could not be reached at {HOST}")
        return f"http://{HOST}:{state['port']}/dashboard.html"


def stop():
    with exclusive_lock(LOCK):
        state = read_state()
        if request(state, "GET"):
            if not request(state, "POST"):
                raise OSError("the live dashboard could not be stopped")
            for _ in range(30):
                if not request(state, "GET"):
                    break
                time.sleep(0.05)
            else:
                raise OSError("the live dashboard is still responding")
        if state.get("port"):
            write_json(STATE, {"port": state["port"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "serve"))
    parser.add_argument("token", nargs="?")
    parser.add_argument("--link", action="store_true", help="print a clickable dashboard address for chat")
    args = parser.parse_args()
    if args.link and args.action != "start":
        parser.error("--link is available with start")
    try:
        if args.action == "start":
            url = start()
            print(f"Live factory dashboard: [{url}]({url})" if args.link else url, flush=True)
        elif args.action == "stop":
            stop()
        elif args.token:
            serve(args.token)
        else:
            parser.error("serve requires a control token")
    except OSError as error:
        parser.exit(1, f"dashboard: {error}\n")


if __name__ == "__main__":
    main()
