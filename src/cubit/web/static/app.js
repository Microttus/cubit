// Cubit's only script. No build step, no dependencies, nothing loaded from the
// network: the pages work without it, this just makes two things nicer.
(function () {
  "use strict";

  // 1. The running timer counts up, instead of showing the time at page load.
  function tick() {
    var el = document.querySelector("[data-started-at]");
    if (!el) return;
    var started = Date.parse(el.getAttribute("data-started-at"));
    if (isNaN(started)) return;

    var seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    el.textContent =
      (hours > 0 ? hours + "h" : "") +
      (hours > 0 ? String(minutes).padStart(2, "0") : minutes) +
      "m " +
      String(seconds % 60).padStart(2, "0") + "s";
  }

  // 2. The category list follows the project that is selected (FR-50).
  function bindCategories(form) {
    var project = form.querySelector("[data-project-select]");
    var category = form.querySelector("[data-category-input]");
    if (!project || !category) return;

    function follow() {
      category.setAttribute("list", "categories-" + project.value);
    }
    project.addEventListener("change", follow);
    follow();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(bindCategories);
    if (document.querySelector("[data-started-at]")) {
      tick();
      setInterval(tick, 1000);
    }
  });
})();
