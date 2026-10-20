// Runs tests/browser_stress.js in headless Chrome at three window widths and exits with an
// error on serious problems (y-axis warnings are only printed). Used by GitHub Actions before
// the data is committed and the page published.
//
//   node tests/run_browser_stress.mjs [url]     default: http://127.0.0.1:8765/index.html
//
// Needs a web server on the page, Chrome (`google-chrome`, or the path in $CHROME) and Node 22
// or newer for its built-in WebSocket. No npm packages: Chrome is driven directly through the
// Chrome DevTools Protocol (CDP), the same protocol DevTools itself uses.

import { spawn } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const URL_UNDER_TEST = process.argv[2] ?? "http://127.0.0.1:8765/index.html";
const WIDTHS = [320, 768, 1280];
const PAGE_LOAD_TIMEOUT_MS = 60_000;

const stressScript = await readFile(new URL("./browser_stress.js", import.meta.url), "utf8");

// Port 0 lets Chrome pick a free port; it prints the address it listens on to stderr.
async function startChrome() {
  const profile = await mkdtemp(path.join(tmpdir(), "stress-chrome-"));
  return new Promise((resolve, reject) => {
    const chrome = spawn(process.env.CHROME ?? "google-chrome", [
      "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run",
      // GitHub's Ubuntu runners don't allow Chrome's sandbox; the page under test is our own.
      "--no-sandbox",
    ], { stdio: ["ignore", "ignore", "pipe"] });
    chrome.on("error", reject);
    let output = "";
    chrome.stderr.on("data", chunk => {
      output += chunk;
      const match = output.match(/DevTools listening on (ws:\/\/\S+)/);
      if (match) resolve({ chrome, browserUrl: match[1] });
    });
    chrome.on("exit", code => reject(new Error(`Chrome stopped (code ${code}):\n${output}`)));
  });
}

// A minimal CDP client: commands are JSON messages with an id, answered with the same id.
async function connect(browserUrl) {
  const socket = new WebSocket(browserUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = () => reject(new Error(`Could not connect to ${browserUrl}`));
  });
  let lastId = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    const waiting = pending.get(message.id);
    if (!waiting) return; // an event, not an answer
    pending.delete(message.id);
    if (message.error) waiting.reject(new Error(`${message.error.message} (${waiting.method})`));
    else waiting.resolve(message.result);
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++lastId;
    pending.set(id, { resolve, reject, method });
    socket.send(JSON.stringify({ id, method, params, sessionId }));
  });
  return { socket, send };
}

async function evaluate(send, sessionId, expression) {
  const { result, exceptionDetails } = await send("Runtime.evaluate",
    { expression, awaitPromise: true, returnByValue: true }, sessionId);
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function loadPage(send, sessionId) {
  await send("Page.navigate", { url: URL_UNDER_TEST }, sessionId);
  const deadline = Date.now() + PAGE_LOAD_TIMEOUT_MS;
  // The page is ready when its data and Chart.js (from the CDN) are loaded and the tab is drawn.
  const ready = 'document.readyState === "complete" && typeof MACRO_DATA === "object" '
    + '&& typeof Chart === "function" && document.querySelector("#panels")?.children.length > 0';
  while (!(await evaluate(send, sessionId, ready).catch(() => false))) {
    if (Date.now() > deadline) throw new Error(`The page did not load within ${PAGE_LOAD_TIMEOUT_MS / 1000} s`);
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}

const { chrome, browserUrl } = await startChrome();
let serious = 0;
try {
  const { socket, send } = await connect(browserUrl);
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  for (const width of WIDTHS) {
    await send("Emulation.setDeviceMetricsOverride",
      { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 }, sessionId);
    await loadPage(send, sessionId);
    await evaluate(send, sessionId, stressScript);
    const report = await evaluate(send, sessionId, "window.stressReport");
    console.log(`${report.serious ? "✗" : "✓"} ${report.summary}`);
    for (const row of report.rows.slice(0, 40)) {
      console.log(`    ${row.kind === "y-akse" ? "advarsel" : "PROBLEM "} ${row.kind}: ${row.text} ${row.side}`);
    }
    if (report.rows.length > 40) console.log(`    … og ${report.rows.length - 40} mere`);
    serious += report.serious;
  }
  socket.close();
} finally {
  chrome.kill();
}
if (serious) {
  console.error(`${serious} problemer: data committes ikke, og siden udgives ikke.`);
  process.exit(1);
}
