document.addEventListener("DOMContentLoaded", () => {
  setupSelectableOptionStates();
  setupSupportBundleForms();
  setupLauncherPresenceHeartbeat();
  setupSelfServeSymptomPicker();
  setupRunProgressPolling();
});

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function scrollIntoViewRespectingMotion(element) {
  if (!(element instanceof HTMLElement)) {
    return;
  }
  element.scrollIntoView({
    behavior: prefersReducedMotion() ? "auto" : "smooth",
    block: "start",
  });
}

function syncSelectableOptionStates(scope = document) {
  const options = scope.querySelectorAll(".selectable-option, .redaction-option");
  for (const option of options) {
    if (!(option instanceof HTMLElement)) {
      continue;
    }
    const input = option.querySelector("input");
    const isSelected = input instanceof HTMLInputElement && input.checked;
    option.classList.toggle("selectable-option-selected", isSelected);
    if (option.classList.contains("choice-card")) {
      option.classList.toggle("choice-card-active", isSelected);
    }
  }
}

function setupSelectableOptionStates() {
  syncSelectableOptionStates(document);
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (!target.matches(".selectable-option-input, .redaction-input")) {
      return;
    }
    syncSelectableOptionStates(target.form || document);
  });
}

function setupSupportBundleForms(scope = document) {
  const forms = scope.querySelectorAll("[data-support-bundle-form]");
  for (const form of forms) {
    if (!(form instanceof HTMLFormElement)) {
      continue;
    }
    syncSupportBundleFormState(form);
    if (form.dataset.bundleEnhancementBound === "true") {
      continue;
    }
    form.dataset.bundleEnhancementBound = "true";
    form.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.name !== "redaction_level") {
        return;
      }
      syncSupportBundleFormState(form);
    });
  }
}

function syncSupportBundleFormState(form) {
  const selectedInput = form.querySelector('input[name="redaction_level"]:checked');
  const selectedLevel = selectedInput instanceof HTMLInputElement ? selectedInput.value : "safe";
  form.dataset.selectedRedaction = selectedLevel;
  const warning = form.querySelector("[data-support-bundle-warning]");
  if (warning instanceof HTMLElement) {
    warning.hidden = selectedLevel !== "none";
  }
}

function setupLauncherPresenceHeartbeat() {
  const heartbeatMeta = document.querySelector(
    'meta[name="occams-browser-presence-heartbeat-url"]'
  );
  const closingMeta = document.querySelector(
    'meta[name="occams-browser-presence-closing-url"]'
  );
  const intervalMeta = document.querySelector(
    'meta[name="occams-browser-presence-interval-ms"]'
  );
  if (!(heartbeatMeta instanceof HTMLMetaElement)) {
    return;
  }
  if (!(closingMeta instanceof HTMLMetaElement)) {
    return;
  }

  const heartbeatUrl = heartbeatMeta.content;
  const closingUrl = closingMeta.content;
  const parsedIntervalMs = Number.parseInt(intervalMeta?.content || "", 10);
  const intervalMs = Number.isFinite(parsedIntervalMs) ? Math.max(parsedIntervalMs, 1000) : 15000;
  let stopped = false;

  const postPresenceUpdate = (url, { keepalive = false } = {}) => {
    if (keepalive && typeof navigator.sendBeacon === "function") {
      try {
        if (navigator.sendBeacon(url)) {
          return;
        }
      } catch (_error) {
        // Fall through to fetch when sendBeacon is unavailable or rejected.
      }
    }

    fetch(url, {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      keepalive,
    }).catch(() => {});
  };

  const sendHeartbeat = () => {
    if (stopped) {
      return;
    }
    postPresenceUpdate(heartbeatUrl);
  };

  sendHeartbeat();
  const intervalId = window.setInterval(sendHeartbeat, intervalMs);

  const handlePageClosing = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    window.clearInterval(intervalId);
    postPresenceUpdate(closingUrl, { keepalive: true });
  };

  window.addEventListener("pagehide", handlePageClosing);
  window.addEventListener("beforeunload", handlePageClosing);
}

function setupSelfServeSymptomPicker() {
  const form = document.querySelector("[data-self-serve-symptom-form]");
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const planRegion = document.querySelector("[data-self-serve-plan-region]");
  if (!(planRegion instanceof HTMLElement)) {
    return;
  }
  const planContent = planRegion.querySelector("[data-self-serve-plan-content]");
  if (!(planContent instanceof HTMLElement)) {
    return;
  }
  const planUrl = form.dataset.planUrl;
  let activePlanRequest = null;
  updateSelfServeChoiceState(form);
  const inputs = form.querySelectorAll('input[name="symptom"]');
  for (const input of inputs) {
    input.addEventListener("change", () => {
      if (!(input instanceof HTMLInputElement) || !input.checked) {
        return;
      }
      activePlanRequest = refreshSelfServePlan(
        form,
        planRegion,
        planContent,
        planUrl,
        activePlanRequest
      );
    });
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    activePlanRequest = refreshSelfServePlan(
      form,
      planRegion,
      planContent,
      planUrl,
      activePlanRequest
    );
  });
}

function navigateSelfServeSymptomSelection(form) {
  const destination = new URL(form.action || window.location.href, window.location.href);
  const formData = new FormData(form);
  const searchParams = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (typeof value !== "string" || value.length === 0) {
      continue;
    }
    searchParams.append(key, value);
  }
  destination.search = searchParams.toString();
  destination.hash = "self-serve-plan-step";
  return destination;
}

function refreshSelfServePlan(form, planRegion, planContent, planUrl, activePlanRequest) {
  if (activePlanRequest instanceof AbortController) {
    activePlanRequest.abort();
  }

  updateSelfServeChoiceState(form);
  const destination = navigateSelfServeSymptomSelection(form);
  const requestUrl = new URL(planUrl || destination.toString(), window.location.href);
  requestUrl.search = destination.search;
  const abortController = new AbortController();
  const requestId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  planRegion.setAttribute("aria-busy", "true");
  planRegion.dataset.planRequestId = requestId;
  delete planRegion.dataset.planNavigating;
  setSelfServePlanLoadingState(planRegion, {
    visible: true,
    title: "Preparing the recommended plan",
    copy: "Reviewing your selection and loading the next step.",
  });

  fetch(requestUrl.toString(), {
    headers: {
      Accept: "text/html",
    },
    cache: "no-store",
    signal: abortController.signal,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`plan-refresh-failed:${response.status}`);
      }
      return response.text();
    })
    .then((html) => {
      planContent.innerHTML = html;
      syncSelectableOptionStates(planContent);
      window.history.replaceState({}, "", destination.toString());
      const planStep = planContent.querySelector("#self-serve-plan-step");
      if (planStep instanceof HTMLElement) {
        scrollIntoViewRespectingMotion(planStep);
        planStep.focus({ preventScroll: true });
      }
      setSelfServePlanLoadingState(planRegion, { visible: false });
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      planRegion.dataset.planNavigating = requestId;
      setSelfServePlanLoadingState(planRegion, {
        visible: true,
        title: "Opening the full plan view",
        copy: "The inline update did not finish, so the server-rendered page is loading instead.",
      });
      window.setTimeout(() => {
        window.location.assign(destination.toString());
      }, 180);
    })
    .finally(() => {
      if (planRegion.dataset.planRequestId === requestId) {
        planRegion.removeAttribute("aria-busy");
        delete planRegion.dataset.planRequestId;
        if (planRegion.dataset.planNavigating !== requestId) {
          setSelfServePlanLoadingState(planRegion, { visible: false });
        }
      }
    });

  return abortController;
}

function updateSelfServeChoiceState(form) {
  syncSelectableOptionStates(form);
}

function setSelfServePlanLoadingState(planRegion, { visible, title = "", copy = "" }) {
  const loadingShell = planRegion.querySelector("[data-self-serve-plan-loading]");
  if (!(loadingShell instanceof HTMLElement)) {
    return;
  }
  const titleElement = loadingShell.querySelector("[data-self-serve-plan-loading-title]");
  const copyElement = loadingShell.querySelector("[data-self-serve-plan-loading-copy]");
  if (titleElement instanceof HTMLElement && title) {
    titleElement.textContent = title;
  }
  if (copyElement instanceof HTMLElement && copy) {
    copyElement.textContent = copy;
  }
  loadingShell.hidden = !visible;
}

function setupRunProgressPolling() {
  const shell = document.querySelector("[data-run-progress]");
  if (!(shell instanceof HTMLElement)) {
    return;
  }

  const statusUrl = shell.getAttribute("data-status-url");
  const fallbackResultsUrl = shell.getAttribute("data-results-url");
  if (!statusUrl) {
    return;
  }

  const statusLabel = shell.querySelector("[data-run-status-label]");
  const headline = shell.querySelector("[data-run-headline]");
  const body = shell.querySelector("[data-run-body]");
  const count = shell.querySelector("[data-progress-count]");
  const currentDomain = shell.querySelector("[data-current-domain]");
  const progressbar = shell.querySelector("[data-progressbar]");
  const progressFill = shell.querySelector("[data-progress-fill]");
  const rows = shell.querySelector("[data-progress-rows]");
  const errorText = shell.querySelector("[data-run-error]");
  const errorShell = shell.querySelector("[data-run-error-shell]");
  const failureActions = shell.querySelector("[data-run-failure-actions]");
  const guidance = shell.querySelector("[data-run-guidance]");
  const elapsed = shell.querySelector("[data-run-elapsed]");
  const updateNote = shell.querySelector("[data-run-update-note]");
  const presenceNote = shell.querySelector("[data-run-presence-note]");
  const modeNote = shell.querySelector("[data-run-mode-note]");
  const liveRegion = shell.querySelector("[data-run-live-region]");
  let lastLiveKey = shell.dataset.liveKey || "";

  const renderRows = (items) => {
    if (!rows) {
      return;
    }
    rows.replaceChildren();
    for (const item of items) {
      const row = document.createElement("li");
      row.className = item.subdued
        ? "progress-domain-row progress-domain-row-subdued"
        : "progress-domain-row";
      if (item.active) {
        row.classList.add("progress-domain-row-active");
        row.setAttribute("aria-current", "step");
      }

      const stack = document.createElement("div");
      stack.className = "stack-xs";

      const header = document.createElement("div");
      header.className = "row-inline";

      const title = document.createElement("strong");
      title.textContent = item.label;

      const stepCount = document.createElement("span");
      stepCount.className = "summary-meta";
      stepCount.textContent = item.step_progress_label || "";

      const badge = document.createElement("span");
      badge.className = `status-pill status-${item.status}`;
      badge.textContent = item.status_label;

      header.append(title, stepCount, badge);

      const summary = document.createElement("p");
      summary.className = "muted";
      summary.textContent = item.summary;

      stack.append(header, summary);

      const meta = document.createElement("div");
      meta.className = "domain-meta";

      const duration = document.createElement("span");
      duration.textContent = item.duration_label || "Pending";

      const scope = document.createElement("span");
      scope.textContent = item.scope_label || "Local only";

      meta.append(duration, scope);
      row.append(stack, meta);
      rows.append(row);
    }
  };

  const announceMajorStatusChange = (payload) => {
    if (!(liveRegion instanceof HTMLElement)) {
      return;
    }
    const liveKey = `${payload.status}:${payload.current_domain_label || ""}:${payload.error || ""}`;
    if (liveKey === lastLiveKey) {
      return;
    }
    lastLiveKey = liveKey;
    shell.dataset.liveKey = liveKey;
    liveRegion.textContent = payload.live_status_message || payload.status_label;
  };

  const applyPayload = (payload) => {
    if (statusLabel) {
      statusLabel.textContent = payload.status_label;
      statusLabel.className = `status-pill status-${payload.status_tone}`;
    }
    if (headline) {
      headline.textContent = payload.headline;
    }
    if (body) {
      body.textContent = payload.body;
    }
    if (count) {
      count.textContent = `${payload.completed_count} of ${payload.total_count}`;
    }
    if (currentDomain) {
      currentDomain.textContent = payload.current_domain_label || "Preparing the next step";
    }
    if (elapsed) {
      elapsed.textContent = payload.elapsed_label || "";
    }
    if (progressFill) {
      progressFill.style.width = `${payload.progress_percent}%`;
    }
    if (progressbar) {
      progressbar.setAttribute("aria-valuemax", String(payload.total_count));
      progressbar.setAttribute("aria-valuenow", String(payload.completed_count));
      progressbar.setAttribute("aria-valuetext", payload.progress_text);
    }
    if (updateNote) {
      updateNote.textContent = payload.update_notice || "";
    }
    if (presenceNote) {
      presenceNote.textContent = payload.presence_notice || "";
    }
    if (modeNote) {
      modeNote.textContent = payload.mode_notice || "";
    }
    if (Array.isArray(payload.rows)) {
      renderRows(payload.rows);
    }
    announceMajorStatusChange(payload);

    if (payload.status === "failed") {
      if (guidance) {
        guidance.hidden = true;
      }
      if (errorShell) {
        errorShell.hidden = false;
      }
      if (errorText) {
        errorText.textContent = payload.error || "The run stopped before results were ready.";
      }
      if (failureActions) {
        failureActions.hidden = false;
      }
      return false;
    }

    if (guidance) {
      guidance.hidden = false;
    }
    if (payload.status === "completed") {
      window.location.assign(payload.results_url || fallbackResultsUrl || window.location.href);
      return false;
    }

    return true;
  };

  const poll = async () => {
    try {
      const response = await fetch(statusUrl, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        window.setTimeout(poll, 1500);
        return;
      }
      const payload = await response.json();
      if (applyPayload(payload)) {
        window.setTimeout(poll, 1000);
      }
    } catch (_error) {
      window.setTimeout(poll, 1500);
    }
  };

  window.setTimeout(poll, 600);
}
