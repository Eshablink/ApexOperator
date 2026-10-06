import os
import socket
import subprocess
import sys
import time
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

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(base + "/", wait_until="networkidle")

            expect(page.get_by_text("AI that")).to_be_visible()
            page.get_by_role("button", name="Open live control room").first.click()
            expect(page.get_by_text("Open the control room.")).to_be_visible()

            page.get_by_role("button", name="Finance Manager").click()
            expect(page.locator("#apiPill")).to_contain_text("API READY")

            page.locator("#invoiceInput").fill("INV-HIGH-001")
            page.locator("#justificationInput").fill("Threshold review")
            page.get_by_role("button", name="Run governed workflow").click()

            expect(page.locator(".toast.success").first).to_contain_text("HUMAN GATE")
            expect(page.locator("#operationsBody")).to_contain_text("INV-HIGH-001")

            page.get_by_role("button", name="Approve").first.click()
            expect(page.locator(".toast.success").first).to_contain_text("APPROVED")
            expect(page.locator("#operationsBody")).to_contain_text("APPROVED")

            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
