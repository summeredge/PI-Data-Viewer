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

  function dialogFocusables(dialog) {
    return Array.from(
      dialog.querySelectorAll(
        "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex=\"-1\"])"
      )
    ).filter(function (element) {
      return element.offsetParent !== null;
    });
  }

  function makeTagSearchDialogAccessible() {
    const modal = document.getElementById("tag-search-modal");
    const dialog = modal?.querySelector(".tag-search-dialog");
    if (!modal || !dialog) return;

    function isOpen() {
      return getComputedStyle(modal).display !== "none";
    }

    function syncFocus() {
      const open = isOpen();
      if (open && modal.dataset.dialogOpen !== "true") {
        modal.dataset.dialogOpen = "true";
        requestAnimationFrame(function () {
          if (isOpen()) document.getElementById("tag-search-mask")?.focus();
        });
      } else if (!open && modal.dataset.dialogOpen === "true") {
        modal.dataset.dialogOpen = "false";
        document.getElementById("open-tag-search-button")?.focus();
      }
    }

    if (!dialog.dataset.focusBehavior) {
      dialog.dataset.focusBehavior = "true";
      document.addEventListener("keydown", function (event) {
        if (!isOpen()) return;

        if (event.key === "Escape") {
          event.preventDefault();
          document.getElementById("close-tag-search-button")?.click();
          return;
        }

        if (event.key !== "Tab") return;
        const focusable = dialogFocusables(dialog);
        if (!focusable.length) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!dialog.contains(document.activeElement)) {
          event.preventDefault();
          first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });

      new MutationObserver(syncFocus).observe(modal, {
        attributes: true,
        attributeFilter: ["style"],
      });
    }

    syncFocus();
  }

  function updateEmptyPlotChrome() {
    document.querySelectorAll(".dash-graph").forEach(function (container) {
      const graph = container.querySelector(".js-plotly-plot");
      if (!graph) return;

      function hasTraceData() {
        const data = Array.isArray(graph.data) ? graph.data : [];
        const keys = [
          "x",
          "y",
          "z",
          "values",
          "labels",
          "r",
          "theta",
          "open",
          "high",
          "low",
          "close",
        ];
        return data.some(function (trace) {
          return keys.some(function (key) {
            return trace[key] != null && trace[key].length > 0;
          });
        });
      }

      container.classList.toggle("plot-empty", !hasTraceData());
      if (graph.dataset.emptyChromeBound || typeof graph.on !== "function") return;
      graph.dataset.emptyChromeBound = "true";
      graph.on("plotly_afterplot", updateEmptyPlotChrome);
    });
  }

  function watchLayout() {
    addFileInput();
    reverseTrendZoomMask();
    makeTabsKeyboardAccessible();
    makeTagSearchDialogAccessible();
    updateEmptyPlotChrome();
    new MutationObserver(function () {
      addFileInput();
      reverseTrendZoomMask();
      makeTabsKeyboardAccessible();
      makeTagSearchDialogAccessible();
      updateEmptyPlotChrome();
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
