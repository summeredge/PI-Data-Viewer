(function () {
  function addFileInput() {
    const container = document.getElementById("file-input-container");
    if (!container || container.querySelector("#file-upload")) return;

    const input = document.createElement("input");
    input.id = "file-upload";
    input.type = "file";
    input.accept = ".csv,.xlsx";
    input.className = "file-input";
    input.setAttribute("aria-label", "选择 CSV 或 Excel 文件");
    input.style.width = "100%";
    container.replaceChildren(input);
  }

  function reverseTrendZoomMask() {
    const graph = document.querySelector("#trend-graph .js-plotly-plot");
    if (!graph || graph.dataset.reverseZoomMask) return;

    graph.dataset.reverseZoomMask = "true";
    graph.on("plotly_relayouting", function () {
      const zoomBox = graph.querySelector(".zoomlayer .zoombox");
      const path = zoomBox?.getAttribute("d") || "";
      const selectedPathStart = path.indexOf("M", 1);
      if (zoomBox && selectedPathStart > 0) {
        zoomBox.setAttribute("d", path.slice(selectedPathStart));
        zoomBox.style.fill = "rgba(0, 0, 0, 0.4)";
      }
    });
  }

  function watchLayout() {
    addFileInput();
    reverseTrendZoomMask();
    new MutationObserver(function () {
      addFileInput();
      reverseTrendZoomMask();
    }).observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchLayout, {once: true});
  } else {
    watchLayout();
  }
})();
