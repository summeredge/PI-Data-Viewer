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

  function watchLayout() {
    addFileInput();
    new MutationObserver(function () {
      addFileInput();
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
