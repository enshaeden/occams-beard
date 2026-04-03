document.addEventListener("DOMContentLoaded", () => {
  setupLauncherPresenceHeartbeat();
  setupSelfServeSymptomPicker();
  setupRunProgressPolling();
});

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
  const planUrl = form.dataset.planUrl;
  let activePlanRequest = null;
  const inputs = form.querySelectorAll('input[name="symptom"]');
  for (const input of inputs) {
    input.addEventListener("change", () => {
      if (!(input instanceof HTMLInputElement) || !input.checked) {
        return;
      }
      activePlanRequest = refreshSelfServePlan(form, planRegion, planUrl, activePlanRequest);
    });
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    activePlanRequest = refreshSelfServePlan(form, planRegion, planUrl, activePlanRequest);
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

function refreshSelfServePlan(form, planRegion, planUrl, activePlanRequest) {
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
      planRegion.innerHTML = html;
      window.history.replaceState({}, "", destination.toString());
      const planStep = document.querySelector("#self-serve-plan-step");
      if (planStep instanceof HTMLElement) {
        planStep.scrollIntoView({ behavior: "smooth", block: "start" });
        planStep.focus({ preventScroll: true });
      }
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      window.location.assign(destination.toString());
    })
    .finally(() => {
      if (planRegion.dataset.planRequestId === requestId) {
        planRegion.removeAttribute("aria-busy");
        delete planRegion.dataset.planRequestId;
      }
    });

  return abortController;
}

function updateSelfServeChoiceState(form) {
  const cards = form.querySelectorAll(".choice-card");
  for (const card of cards) {
    if (!(card instanceof HTMLElement)) {
      continue;
    }
    const input = card.querySelector('input[name="symptom"]');
    if (input instanceof HTMLInputElement && input.checked) {
      card.classList.add("choice-card-active");
      continue;
    }
    card.classList.remove("choice-card-active");
  }
}

function setupRunProgressPolling() {
  const shell = document.querySelector("[data-run-progress]");
  if (!shell) {
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
  const updateNote = shell.querySelector("[data-run-update-note]");
  const presenceNote = shell.querySelector("[data-run-presence-note]");
  const modeNote = shell.querySelector("[data-run-mode-note]");

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
