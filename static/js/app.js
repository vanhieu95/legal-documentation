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

  const registerAlpineComponents = () => {
    window.Alpine.data("themeControls", () => ({
      currentTheme: documentRoot.dataset.theme || "system",
      chooseTheme(themeChoice) {
        if (themeChoice === "system") {
          delete documentRoot.dataset.theme;
          this.currentTheme = "system";
          try {
            window.localStorage.removeItem(themeStorageKey);
          } catch {
            // System preference still applies when storage is unavailable.
          }
        } else if (themeChoice === "light" || themeChoice === "dark") {
          documentRoot.dataset.theme = themeChoice;
          this.currentTheme = themeChoice;
          try {
            window.localStorage.setItem(themeStorageKey, themeChoice);
          } catch {
            // The selected theme remains active for the current page.
          }
        }
      },
    }));

    window.Alpine.data("applicationShell", () => ({
      drawerOpen: false,
      desktopNavigation: false,
      returnFocus: null,
      init() {
        const desktopQuery = window.matchMedia("(min-width: 1024px)");
        const updateNavigationMode = () => {
          this.desktopNavigation = desktopQuery.matches;
          if (this.desktopNavigation) {
            this.drawerOpen = false;
            document.body.classList.remove("drawer-open");
          }
        };
        updateNavigationMode();
        desktopQuery.addEventListener("change", updateNavigationMode);
      },
      drawerFocusableElements() {
        return Array.from(
          this.$refs.drawer.querySelectorAll(
            'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        );
      },
      openDrawer() {
        this.returnFocus = document.activeElement;
        this.drawerOpen = true;
        document.body.classList.add("drawer-open");
        this.$nextTick(() => this.drawerFocusableElements()[0]?.focus());
      },
      closeDrawer() {
        if (!this.drawerOpen) {
          return;
        }
        this.drawerOpen = false;
        document.body.classList.remove("drawer-open");
        this.$nextTick(() => this.returnFocus?.focus());
      },
      trapDrawerFocus(event) {
        if (!this.drawerOpen) {
          return;
        }
        const focusableElements = this.drawerFocusableElements();
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        if (event.shiftKey && document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        } else if (!event.shiftKey && document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      },
    }));
  };
  if (window.Alpine) {
    registerAlpineComponents();
  } else {
    document.addEventListener("alpine:init", registerAlpineComponents, { once: true });
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

  document.addEventListener("htmx:beforeSwap", (event) => {
    const redirect = event.detail.xhr.getResponseHeader("HX-Redirect");
    if (!redirect) {
      return;
    }
    const destination = new URL(redirect, window.location.origin);
    if (destination.origin !== window.location.origin || !destination.pathname.startsWith("/")) {
      return;
    }
    event.detail.shouldSwap = false;
    window.location.assign(`${destination.pathname}${destination.search}${destination.hash}`);
  });

  let activeHtmxRequests = 0;
  const updateBusyPresentation = () => {
    const isBusy = activeHtmxRequests > 0;
    const loadingStatus = document.getElementById("global-loading");
    const mainContent = document.getElementById("main-content");
    if (loadingStatus) {
      loadingStatus.setAttribute("aria-busy", String(isBusy));
      loadingStatus.classList.toggle("is-busy", isBusy);
    }
    if (mainContent) {
      mainContent.setAttribute("aria-busy", String(isBusy));
    }
  };
  document.addEventListener("htmx:beforeRequest", () => {
    activeHtmxRequests += 1;
    updateBusyPresentation();
  });
  document.addEventListener("htmx:afterRequest", () => {
    activeHtmxRequests = Math.max(0, activeHtmxRequests - 1);
    updateBusyPresentation();
  });

  const errorSummary = document.querySelector("[data-error-summary]");
  if (errorSummary instanceof HTMLElement) {
    errorSummary.focus();
  }

  for (const submitForm of document.querySelectorAll("[data-submit-form]")) {
    submitForm.addEventListener("submit", () => {
      const submitButton = submitForm.querySelector("[data-submit-button]");
      const submitLabel = submitForm.querySelector("[data-submit-label]");
      const submitLoading = submitForm.querySelector("[data-submit-loading]");
      if (submitButton instanceof HTMLButtonElement) {
        submitButton.disabled = true;
        submitButton.setAttribute("aria-busy", "true");
      }
      if (submitLabel instanceof HTMLElement) {
        submitLabel.hidden = true;
      }
      if (submitLoading instanceof HTMLElement) {
        submitLoading.hidden = false;
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
