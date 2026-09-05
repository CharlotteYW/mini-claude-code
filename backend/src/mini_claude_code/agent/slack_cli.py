"""CLI for Slack OAuth install + Socket Mode bot (M18)."""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mini_claude_code.agent.slack_bot import run_socket_mode_bot
from mini_claude_code.agent.slack_oauth import (
    build_install_url,
    exchange_oauth_code,
    generate_oauth_state,
    installations_path,
    load_installations,
    save_installation,
)
from mini_claude_code.config import get_settings

_CALLBACK_SUFFIX = "/slack/oauth/callback"


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # agent/slack_cli.py → …/mini_claude_code/agent → parents[4] = repo root
    repo_root = Path(__file__).resolve().parents[4]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _is_oauth_callback_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == _CALLBACK_SUFFIX


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _run_oauth_install(settings) -> int:
    client_id = settings.slack_client_id.strip()
    client_secret = settings.slack_client_secret.strip()
    redirect_uri = settings.slack_oauth_redirect_uri.strip()
    if not client_id or not client_secret:
        print("ERROR: SLACK_CLIENT_ID and SLACK_CLIENT_SECRET required", file=sys.stderr)
        return 1

    existing = load_installations(installations_path(settings))
    if existing:
        teams = ", ".join(existing.keys())
        print(
            f"Note: installation already on disk for team(s): {teams}. "
            "Re-install only if you added new bot scopes (e.g. reactions:write)."
        )

    state = generate_oauth_state()
    install_url = build_install_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )
    parsed = urlparse(redirect_uri)
    port = settings.slack_oauth_port
    if parsed.port:
        port = parsed.port

    if _port_in_use("127.0.0.1", port):
        print(
            f"WARNING: port {port} is already in use on 127.0.0.1.\n"
            "Docker/Open WebUI often binds localhost:3000 — pick another port, e.g.:\n"
            "  SLACK_OAUTH_PORT=3917\n"
            "  SLACK_OAUTH_REDIRECT_URI=http://127.0.0.1:3917/slack/oauth/callback\n"
            "Then add the same Redirect URL in your Slack app settings.",
            file=sys.stderr,
        )

    result: dict[str, str | None] = {"code": None, "error": None}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            # Help debug 404 reports — show which path hit the callback server.
            try:
                msg = format % args
            except Exception:  # noqa: BLE001
                msg = format
            print(f"[oauth] {msg}", file=sys.stderr)

        def do_GET(self) -> None:
            parsed_req = urlparse(self.path)
            path = parsed_req.path or "/"
            query = parse_qs(parsed_req.query)

            if path in {"/favicon.ico", "/robots.txt"}:
                self.send_response(204)
                self.end_headers()
                return

            if path == "/":
                body = (
                    b"<html><body><h1>Waiting for Slack OAuth</h1>"
                    b"<p>Complete authorization in Slack; you will be redirected here.</p>"
                    b"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if not _is_oauth_callback_path(path) and "code" not in query:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(
                    f"Not found: {path}\nExpected OAuth redirect at {_CALLBACK_SUFFIX}\n".encode()
                )
                return

            if query.get("state", [""])[0] != state:
                result["error"] = "state mismatch"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"OAuth state mismatch")
                return

            if query.get("error", [None])[0]:
                result["error"] = str(query["error"][0])
                self.send_response(400)
                self.end_headers()
                self.wfile.write(
                    f"Slack OAuth error: {result['error']}".encode()
                )
                return

            code = query.get("code", [None])[0]
            if not code:
                result["error"] = "no code"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code query parameter")
                return

            result["code"] = code
            body = (
                b"<html><body><h1>Slack installed</h1>"
                b"<p>Success - you can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("127.0.0.1", port), _Handler)
    except OSError as exc:
        print(
            f"ERROR: cannot listen on 127.0.0.1:{port} ({exc}).\n"
            "Another app may be using port 3000 — stop it or set SLACK_OAUTH_PORT / "
            "SLACK_OAUTH_REDIRECT_URI to a free port.",
            file=sys.stderr,
        )
        return 1

    print(f"OAuth callback server listening on http://127.0.0.1:{port}")
    print(f"Expected redirect URI (must match Slack app settings): {redirect_uri}")
    print()
    print("Open this URL to install the Slack app to your workspace:")
    print(install_url)
    print()
    print("Waiting for Slack to redirect back after you click Allow...")

    # Start listening BEFORE opening the browser (avoid race on fast redirects).
    server.timeout = 1.0
    opened_browser = False
    while result["code"] is None and result["error"] is None:
        server.handle_request()
        if not opened_browser:
            try:
                webbrowser.open(install_url)
            except Exception:  # noqa: BLE001
                pass
            opened_browser = True

    if result["error"]:
        print(f"ERROR: OAuth failed: {result['error']}", file=sys.stderr)
        return 1

    installation = exchange_oauth_code(
        client_id=client_id,
        client_secret=client_secret,
        code=str(result["code"]),
        redirect_uri=redirect_uri,
    )
    save_installation(installation)
    print(f"Installed team {installation.team_name} ({installation.team_id})")
    print("Bot token saved to workspace/slack_installations.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Slack OAuth install + agent bot (M18).")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("install", help="Run OAuth v2 install flow (local callback server).")
    run_parser = sub.add_parser("run", help="Start Socket Mode bot (requires prior install).")
    run_parser.add_argument(
        "--checkpointer",
        choices=["memory", "postgres"],
        default=None,
        help="Override CHECKPOINT_BACKEND (use memory when Postgres is not running).",
    )

    args = parser.parse_args(argv)
    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    if args.command == "install":
        return _run_oauth_install(settings)
    if args.command == "run":
        try:
            run_socket_mode_bot(
                settings=settings,
                checkpointer_backend=args.checkpointer,  # type: ignore[arg-type]
            )
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
