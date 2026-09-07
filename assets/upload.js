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

  /* Dash 4 的 Tab 渲染为 plain div：补 role/tabindex 与方向键、Enter 操作 */
  function makeTabsKeyboardAccessible() {
    const tabBar = document.querySelector(".viewer-tabs");
    if (!tabBar) return;

    const tabs = Array.from(tabBar.querySelectorAll(".viewer-tab"));
    if (!tabs.length) return;

    tabBar.setAttribute("role", "tablist");
    tabs.forEach(function (tab) {
      const selected = tab.classList.contains("viewer-tab-selected");
      tab.setAttribute("role", "tab");
      tab.setAttribute("tabindex", selected ? "0" : "-1");
      if (tab.dataset.keyboardTabs) return;

      tab.dataset.keyboardTabs = "true";
      tab.addEventListener("keydown", function (event) {
        const current = Array.from(tabBar.querySelectorAll(".viewer-tab"));
        const index = current.indexOf(tab);
        let target = null;

        if (event.key === "ArrowRight") {
          target = current[(index + 1) % current.length];
        } else if (event.key === "ArrowLeft") {
          target = current[(index - 1 + current.length) % current.length];
        } else if (event.key === "Home") {
          target = current[0];
        } else if (event.key === "End") {
          target = current[current.length - 1];
        } else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          tab.click();
          return;
        }

        if (!target) return;
        event.preventDefault();
        target.click();
        requestAnimationFrame(function () {
          const focused = tabBar.querySelector(".viewer-tab-selected");
          if (focused) focused.focus();
        });
      });
    });
  }

  function watchLayout() {
    addFileInput();
    reverseTrendZoomMask();
    makeTabsKeyboardAccessible();
    new MutationObserver(function () {
      addFileInput();
      reverseTrendZoomMask();
      makeTabsKeyboardAccessible();
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
