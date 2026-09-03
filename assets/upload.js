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

  function bindAdvancedToggle() {
    const toggle = document.getElementById("trend-advanced-toggle");
    const controls = document.getElementById("trend-controls");
    if (!toggle || !controls || toggle.dataset.bound) return;

    toggle.dataset.bound = "true";
    toggle.addEventListener("click", function () {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      controls.classList.toggle("advanced-open", !expanded);
      toggle.textContent = expanded ? "展开高级参数" : "收起高级参数";
    });
  }

  function watchLayout() {
    addFileInput();
    bindAdvancedToggle();
    new MutationObserver(function () {
      addFileInput();
      bindAdvancedToggle();
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
