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
    historyEnabled: true,
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
    const targetId = event.detail.target?.id;
    const isDashboardUnavailable =
      event.detail.xhr.status === 503 &&
      (targetId === "dashboard-case-activity" || targetId === "dashboard-documents");
    if (event.detail.xhr.status === 422 || event.detail.xhr.status === 409 || isDashboardUnavailable) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
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
    document.getElementById("case-results")?.setAttribute("aria-busy", String(isBusy));
    document.getElementById("template-upload-workflow")?.setAttribute("aria-busy", String(isBusy));
    document.getElementById("document-draft-form")?.setAttribute("aria-busy", String(isBusy));
    document.getElementById("generation-history")?.setAttribute("aria-busy", String(isBusy));
  };
  const requestDashboardRegion = (requestElement) =>
    requestElement?.closest("#dashboard-case-activity, #dashboard-documents");
  document.addEventListener("htmx:beforeRequest", (event) => {
    activeHtmxRequests += 1;
    updateBusyPresentation();
    requestDashboardRegion(event.detail?.elt)?.setAttribute("aria-busy", "true");
  });
  const announceHtmxNetworkError = (requestElement) => {
    const errorRegion = document.getElementById("global-error");
    const caseResults = requestElement?.closest("#case-results");
    const dashboardActivity = requestElement?.closest("#dashboard-case-activity");
    const dashboardDocuments = requestElement?.closest("#dashboard-documents");
    const templateWorkflow = requestElement?.closest("#template-upload-workflow");
    const generationForm = requestElement?.closest("[data-generation-form]");
    const generationHistory = requestElement?.closest("[data-generation-history]");
    const affectedRegion =
      generationForm ||
      generationHistory ||
      caseResults ||
      dashboardActivity ||
      dashboardDocuments ||
      templateWorkflow;
    if (affectedRegion && errorRegion) {
      affectedRegion.setAttribute("aria-busy", "false");
      errorRegion.textContent = affectedRegion.dataset.networkErrorMessage || "";
    }
  };
  document.addEventListener("htmx:afterRequest", (event) => {
    activeHtmxRequests = Math.max(0, activeHtmxRequests - 1);
    updateBusyPresentation();
    requestDashboardRegion(event.detail?.elt)?.setAttribute("aria-busy", "false");
    if (event.detail?.successful === false) {
      announceHtmxNetworkError(event.detail?.elt);
    }
  });
  document.addEventListener("htmx:sendError", (event) => {
    announceHtmxNetworkError(event.detail.elt);
  });

  let referenceDialogTrigger = null;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-reference-dialog-trigger]");
    if (trigger instanceof HTMLElement) {
      referenceDialogTrigger = trigger;
    }
    const closeButton = event.target.closest("[data-reference-dialog-close]");
    if (closeButton) {
      document.getElementById("reference-dialog")?.close();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (target?.id === "case-section") {
      document.getElementById("case-section-heading")?.focus();
    }
    if (target?.id === "reference-dialog-content") {
      const dialog = document.getElementById("reference-dialog");
      if (dialog instanceof HTMLDialogElement) {
        dialog.showModal();
        dialog.querySelector("button, a, input, select, textarea")?.focus();
      }
    }
    const summary = document.querySelector("[data-error-summary], [data-conflict-summary]");
    if (summary instanceof HTMLElement) {
      summary.focus();
      return;
    }
    const templateOutcome = document.querySelector(
      "[data-template-result], [data-template-server-error], [data-generation-result]",
    );
    if (templateOutcome instanceof HTMLElement) {
      templateOutcome.focus();
      return;
    }
    const relationshipSuccess = document.querySelector("#relationship-form .alert-success");
    if (relationshipSuccess instanceof HTMLElement) {
      relationshipSuccess.focus();
      return;
    }
    const referenceFormHeading = document.querySelector("[data-reference-form-heading]");
    if (referenceFormHeading instanceof HTMLElement) {
      referenceFormHeading.focus();
    }
  });

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-formset-add]");
    if (addButton instanceof HTMLButtonElement) {
      const fieldset = addButton.closest("[data-formset]");
      const template = fieldset?.querySelector("[data-formset-template]");
      const rows = fieldset?.querySelector("[data-formset-rows]");
      const totalInput = fieldset?.querySelector('input[name$="-TOTAL_FORMS"]');
      if (
        template instanceof HTMLTemplateElement &&
        rows instanceof HTMLElement &&
        totalInput instanceof HTMLInputElement
      ) {
        const index = Number.parseInt(totalInput.value, 10);
        const wrapper = document.createElement("div");
        wrapper.append(template.content.cloneNode(true));
        wrapper.innerHTML = wrapper.innerHTML.replaceAll("__prefix__", String(index));
        const row = wrapper.firstElementChild;
        if (row) {
          rows.append(row);
          totalInput.value = String(index + 1);
          row.querySelector('input:not([type="hidden"]), select, textarea')?.focus();
        }
      }
      return;
    }
    const removeButton = event.target.closest("[data-formset-remove]");
    if (removeButton instanceof HTMLButtonElement) {
      const row = removeButton.closest("[data-formset-row]");
      const deleteInput = row?.querySelector('input[name$="-DELETE"]');
      if (row instanceof HTMLElement && deleteInput instanceof HTMLInputElement) {
        deleteInput.checked = true;
        row.hidden = true;
        row.closest("[data-formset]")?.querySelector("[data-formset-add]")?.focus();
      }
    }
  });
  document.getElementById("reference-dialog")?.addEventListener("close", () => {
    referenceDialogTrigger?.focus();
    referenceDialogTrigger = null;
  });

  let templateDialogTrigger = null;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-template-dialog-trigger]");
    if (trigger instanceof HTMLElement) {
      templateDialogTrigger = trigger;
    }
    if (event.target.closest("[data-template-dialog-close]")) {
      document.getElementById("template-transition-dialog")?.close();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target?.id !== "template-transition-dialog-content") {
      return;
    }
    const dialog = document.getElementById("template-transition-dialog");
    if (dialog instanceof HTMLDialogElement) {
      dialog.showModal();
      dialog.querySelector('button, a, input:not([type="hidden"])')?.focus();
    }
  });
  document.getElementById("template-transition-dialog")?.addEventListener("close", () => {
    templateDialogTrigger?.focus();
    templateDialogTrigger = null;
  });

  let caseDialogTrigger = null;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-case-dialog-trigger]");
    if (trigger instanceof HTMLElement) {
      caseDialogTrigger = trigger;
    }
    if (event.target.closest("[data-case-dialog-close]")) {
      document.getElementById("case-transition-dialog")?.close();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target?.id !== "case-transition-dialog-content") {
      return;
    }
    const dialog = document.getElementById("case-transition-dialog");
    if (dialog instanceof HTMLDialogElement) {
      dialog.showModal();
      dialog.querySelector('button, a, input:not([type="hidden"]), textarea, select')?.focus();
    }
  });
  document.getElementById("case-transition-dialog")?.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") {
      return;
    }
    const focusableElements = Array.from(
      event.currentTarget.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), select:not([disabled])',
      ),
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement?.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement?.focus();
    }
  });
  document.getElementById("case-transition-dialog")?.addEventListener("close", () => {
    caseDialogTrigger?.focus();
    caseDialogTrigger = null;
  });

  const errorSummary = document.querySelector("[data-error-summary], [data-conflict-summary]");
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
