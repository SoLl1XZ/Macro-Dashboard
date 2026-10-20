// Stress test for the dashboard, run in the browser - not by Node, since it needs the page.
//
// How: open the dashboard (locally or online), open the console (Cmd+Option+J), paste this
// whole file and press Enter. It visits every tab at several periods, draws every chart (also
// those the page would only draw when scrolled to), tries broken URLs and fast navigation,
// and prints a report. Takes about a minute. Repeat at a few window widths (e.g. 320, 768 and
// 1280 px in the device toolbar) - the overflow check depends on the width.
//
// A problem is: an error in the page, an empty chart, a y-axis the data fills less than 60 %
// of (charts with a reference line are exempt, see CLAUDE.md), two lines in one colour,
// NaN/undefined/Infinity in the text, or a page wider than the window. Each problem has a kind;
// "y-akse" is only a warning (it depends on the day's data), the rest are errors that
// run_browser_stress.mjs stops the publishing on.

(async () => {
  const RANGES = [5, 1, 10, 0]; // years; 0 = all history
  const BROKEN_URLS = [
    "#", "#nope", "#us?range=-5", "#us?range=abc", "#us?range=99999", "#us?panel=doesnotexist",
    "#us?panel=us_fed&full=1&from=2099-01&to=1900-01", "#compare?c=&p=", "#compare?c=atlantis&p=bogus",
    "#compare?a=nope&b=nope&index=1", `#compare?c=${MACRO_DATA.sections.filter(s => s.region).map(s => s.id).join(",")}`,
    "#us?%E0%A4%A",
  ];
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const errors = [];
  const onError = event => errors.push(`${event.message ?? event.reason} @ ${location.hash}`);
  addEventListener("error", onError);
  addEventListener("unhandledrejection", onError);

  // Share of the y-axis the visible data spans: below 0.6 the axis looks half empty.
  function axisFill(chart) {
    const { x, y } = chart.scales;
    let low = Infinity, high = -Infinity, points = 0;
    for (const dataset of chart.data.datasets) {
      for (const point of dataset.data) {
        const time = typeof point.x === "number" ? point.x : Date.parse(point.x);
        if (time >= x.min && time <= x.max && Number.isFinite(point.y)) {
          low = Math.min(low, point.y);
          high = Math.max(high, point.y);
          points++;
        }
      }
    }
    return { points, fill: high > low ? (high - low) / (y.max - y.min) : 1 };
  }

  async function checkPage(hash) {
    location.hash = hash;
    await wait(200);
    const problems = [];
    const add = (kind, text) => problems.push({ kind, text });
    for (const canvas of document.querySelectorAll("#panels .chart > canvas")) {
      const name = canvas.getAttribute("aria-label").replace("Graf: ", "");
      let chart = liveCharts.get(canvas);
      try {
        chart ??= createChart(canvas, withWindow(canvas.chartPanel));
        liveCharts.set(canvas, chart);
      } catch (error) {
        add("fejl", `kunne ikke tegne ${name}: ${error.message}`);
        continue;
      }
      const { points, fill } = axisFill(chart);
      const hasReferenceLine = (canvas.chartPanel.referenceLines ?? []).length > 0;
      if (points === 0) add("tom graf", name);
      else if (points > 1 && fill < 0.6 && !hasReferenceLine) add("y-akse", `${Math.round(fill * 100)} %: ${name}`);
      const colours = chart.data.datasets.map(dataset => dataset.borderColor);
      if (new Set(colours).size < colours.length) add("farve", `samme farve to gange: ${name}`);
    }
    if (/\b(NaN|undefined|Infinity)\b/.test(document.querySelector("main").innerText)) add("tekst", "NaN/undefined i teksten");
    const { scrollWidth, clientWidth } = document.documentElement;
    if (scrollWidth > clientWidth) add("overløb", `siden er ${scrollWidth - clientWidth} px for bred`);
    for (const [canvas, chart] of liveCharts) {
      chart.destroy();
      liveCharts.delete(canvas);
    }
    return problems;
  }

  const start = performance.now();
  const startHash = location.hash;
  const tabs = ["signals", ...MACRO_DATA.sections.map(section => section.id), "compare"];
  const rows = [];
  for (const range of RANGES) {
    for (const tab of tabs) {
      const hash = `#${tab}?range=${range}`;
      for (const problem of await checkPage(hash)) rows.push({ side: hash, ...problem });
    }
  }
  for (const hash of BROKEN_URLS) {
    for (const problem of await checkPage(hash)) rows.push({ side: hash, ...problem });
    document.querySelector("dialog[open]")?.close();
  }
  for (let i = 0; i < 60; i++) { // fast navigation: hash changes faster than the page draws
    location.hash = `#${tabs[i % tabs.length]}?range=${i % 30}`;
    await wait(5);
  }
  await wait(800);
  for (const error of errors) rows.push({ side: "", kind: "fejl", text: error });
  removeEventListener("error", onError);
  removeEventListener("unhandledrejection", onError);
  location.hash = startHash;

  const pages = tabs.length * RANGES.length + BROKEN_URLS.length;
  const seconds = Math.round((performance.now() - start) / 1000);
  const serious = rows.filter(row => row.kind !== "y-akse").length;
  const summary = `${innerWidth} px: ${pages} sider på ${seconds} s, ${serious} problemer, `
    + `${rows.length - serious} advarsler`;
  console.log(serious ? `✗ ${summary}` : `✓ ${summary}`);
  if (rows.length) console.table(rows);
  window.stressReport = { summary, serious, rows };
  return summary;
})();
