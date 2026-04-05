document.addEventListener("DOMContentLoaded", function () {
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({
      theme: "base",
      themeVariables: {
        lineColor: "#8a8a8a",
        arrowheadColor: "#8a8a8a",
      },
    });
  }
});
