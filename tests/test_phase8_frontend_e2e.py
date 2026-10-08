import os
import socket
import subprocess
import sys
import time
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.time() + 25
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited early with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError("ApexOperator API did not become ready in time")


def test_frontend_live_control_room_end_to_end(tmp_path):
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'e2e.sqlite3'}"
    env["APP_ENV"] = "development"
    env["APEX_PLANNER"] = "mock"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apexoperator.api.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(f"{base}/health", process)

        # Seed a pending high-value task as the AP clerk; the manager UI then reviews it.
        request = urllib.request.Request(
            f"{base}/tasks",
            data=json.dumps({
                "invoice_id": "INV-HIGH-001",
                "justification": "Threshold review",
            }).encode("utf-8"),
            headers={
                "Authorization": "Bearer dev-clerk-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            seeded = json.load(response)
        assert seeded["status"] == "PENDING_HUMAN_APPROVAL"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page_errors = []
            console_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.goto(base + "/", wait_until="networkidle")

            expect(page.get_by_text("AI that")).to_be_visible()
            page.get_by_role("button", name="Open live control room").first.click()
            expect(page.get_by_text("Open the control room.")).to_be_visible()

            page.get_by_role("button", name="Sign in as Finance Manager").click()
            try:
                expect(page.locator("#apiPill")).to_contain_text("API READY", timeout=15000)
            except AssertionError:
                raise AssertionError(
                    f"frontend errors={page_errors!r}; console_errors={console_errors!r}; "
                    f"record_hint={page.locator('#recordHint').inner_text()!r}; "
                    f"wake_message={page.locator('#wakeMessage').inner_text()!r}"
                )

            expect(page.locator("#operationsBody")).to_contain_text("INV-HIGH-001")
            expect(page.locator(".mini-tag.pending").first).to_contain_text("PENDING HUMAN APPROVAL")

            page.get_by_role("button", name="Open INV-HIGH-001 operation detail").click()
            expect(page.locator("#taskDetailTitle")).to_have_text("INV-HIGH-001")
            expect(page.locator("#taskDetailBody")).to_contain_text("MODEL OUTPUT · UNTRUSTED")
            expect(page.locator("#taskDetailBody")).to_contain_text("APPLICATION POLICY")

            expect(page.locator("#reviewReason")).to_be_visible()
            # Approval requires an explicit reason and uses the idempotent transition.
            page.get_by_label("Decision reason · required").fill("Verified invoice against source and policy.")
            page.get_by_role("button", name="Approve").click()
            expect(page.locator(".toast.success", has_text="APPROVED")).to_be_visible()
            expect(page.locator("#operationsBody")).to_contain_text("APPROVED")

            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
