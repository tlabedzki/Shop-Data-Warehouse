"""
Headless Chrome or Edge through the DevTools protocol, for the README charts and the app screenshots.

The browser takes a free DevTools port (port 0, read back from DevToolsActivePort in its own profile), so it never
attaches to another browser on the machine, and only its own process tree is stopped at the end.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser",
]
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def find_browser() -> str:
    for candidate in filter(None, [os.environ.get("CHROME"), *BROWSERS]):
        path = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if path:
            return path
    sys.exit("Chrome, Chromium or Edge not found. Set CHROME to the browser executable.")


def wait_for(url: str, seconds: float = 90) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.3)
    raise SystemExit(f"{url} did not answer in {seconds:.0f} s")


def stop_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


class Page:
    """One browser tab: evaluate JavaScript, wait for a condition, take a screenshot of an element."""

    def __init__(self, ws):
        self.ws, self.counter = ws, 0

    async def send(self, method: str, **params):
        self.counter += 1
        await self.ws.send(json.dumps({"id": self.counter, "method": method, "params": params}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == self.counter:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    async def js(self, expression: str):
        result = await self.send("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        return result.get("result", {}).get("value")

    async def until(self, expression: str, seconds: float = 120) -> None:
        for _ in range(int(seconds * 4)):
            if await self.js(expression):
                return
            await asyncio.sleep(0.25)
        raise SystemExit(f"Timed out waiting for: {expression}")

    async def viewport(self, width: int, height: int, scale: float = 1, mobile: bool = False) -> None:
        await self.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale,
                        mobile=mobile)

    async def open(self, url: str) -> None:
        await self.send("Page.navigate", url=url)

    async def shot(self, selector: str, path: Path, pad: int = 0, full_width: bool = False) -> None:
        """PNG of one element (plus `pad` CSS pixels around it), at the device scale of the viewport."""
        box = await self.js(f"(() => {{ const r = document.querySelector({json.dumps(selector)})"
                            f".getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height];"
                            f" }})()")
        x, y, width, height = box
        if full_width:
            x, width = 0, await self.js("document.documentElement.clientWidth")
        clip = {"x": max(x - pad, 0), "y": max(y - pad, 0), "width": width + 2 * pad, "height": height + 2 * pad,
                "scale": 1}
        result = await self.send("Page.captureScreenshot", format="png", captureBeyondViewport=True, clip=clip)
        path.write_bytes(base64.b64decode(result["data"]))


class Browser:
    """`async with Browser() as page:` starts a headless browser on a free port and stops it afterwards."""

    def __init__(self):
        self.profile = tempfile.mkdtemp()
        self.process = None
        self.connection = None

    async def __aenter__(self) -> Page:
        self.process = subprocess.Popen(
            [find_browser(), "--headless=new", "--disable-gpu", "--remote-debugging-port=0", "--hide-scrollbars",
             "--force-color-profile=srgb", "--font-render-hinting=none", f"--user-data-dir={self.profile}",
             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **HIDDEN)
        active = Path(self.profile) / "DevToolsActivePort"
        deadline = time.time() + 30
        while not (active.exists() and active.read_text().strip()):
            if time.time() > deadline:
                raise SystemExit("The browser did not open a DevTools port")
            await asyncio.sleep(0.1)
        port = int(active.read_text().split()[0])
        wait_for(f"http://127.0.0.1:{port}/json/version")
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
        target = next(t for t in targets if t["type"] == "page")
        self.connection = await websockets.connect(target["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024,
                                                   ping_interval=None)
        return Page(self.connection)

    async def __aexit__(self, *exc) -> None:
        if self.connection is not None:
            await self.connection.close()
        stop_tree(self.process)
        shutil.rmtree(self.profile, ignore_errors=True)
