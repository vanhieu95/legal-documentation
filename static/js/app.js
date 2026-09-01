(() => {
  "use strict";

  const documentRoot = document.documentElement;
  documentRoot.classList.remove("no-js");
  documentRoot.classList.add("js");

  const themeStorageKey = "vds-theme";
  try {
    const storedTheme = window.localStorage.getItem(themeStorageKey);
    if (storedTheme === "light" || storedTheme === "dark") {
      documentRoot.dataset.theme = storedTheme;
    }
  } catch {
    // A theme preference is optional when storage is unavailable.
  }

  const htmxSecurityDefaults = {
    historyEnabled: false,
    historyCacheSize: 0,
    allowEval: false,
    allowScriptTags: false,
    includeIndicatorStyles: false,
    selfRequestsOnly: true,
  };
  if (window.htmx) {
    Object.assign(window.htmx.config, htmxSecurityDefaults);
  }

  const clearHtmxHistoryMetadata = () => {
    try {
      window.sessionStorage.removeItem("htmx-current-path-for-history");
    } catch {
      // Storage can be unavailable under a restrictive browser policy; that is already safe.
    }
  };
  clearHtmxHistoryMetadata();
  document.addEventListener("htmx:beforeHistoryUpdate", () => {
    window.queueMicrotask(clearHtmxHistoryMetadata);
  });

  for (const themeButton of document.querySelectorAll("[data-theme-choice]")) {
    themeButton.addEventListener("click", () => {
      const themeChoice = themeButton.dataset.themeChoice;
      if (themeChoice === "system") {
        delete documentRoot.dataset.theme;
        try {
          window.localStorage.removeItem(themeStorageKey);
        } catch {
          // System preference still applies when storage is unavailable.
        }
      } else if (themeChoice === "light" || themeChoice === "dark") {
        documentRoot.dataset.theme = themeChoice;
        try {
          window.localStorage.setItem(themeStorageKey, themeChoice);
        } catch {
          // The selected theme remains active for the current page.
        }
      }
    });
  }

  for (const openButton of document.querySelectorAll("[data-dialog-open]")) {
    const dialog = document.getElementById(openButton.dataset.dialogOpen);
    if (!(dialog instanceof HTMLDialogElement)) {
      continue;
    }
    const dialogButtons = Array.from(dialog.querySelectorAll("button:not([disabled])"));
    openButton.addEventListener("click", () => {
      dialog.showModal();
      dialogButtons[0]?.focus();
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab" || dialogButtons.length === 0) {
        return;
      }
      const firstButton = dialogButtons[0];
      const lastButton = dialogButtons[dialogButtons.length - 1];
      if (event.shiftKey && document.activeElement === firstButton) {
        event.preventDefault();
        lastButton.focus();
      } else if (!event.shiftKey && document.activeElement === lastButton) {
        event.preventDefault();
        firstButton.focus();
      }
    });
    dialog.addEventListener("close", () => openButton.focus());
  }

  for (const closeButton of document.querySelectorAll("[data-dialog-close]")) {
    closeButton.addEventListener("click", () => closeButton.closest("dialog")?.close());
  }
})();
