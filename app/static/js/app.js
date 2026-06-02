function countWords(text) {
  return (text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean).length;
}

function updateEditorMetrics() {
  const config = window.talkEditorConfig;
  if (!config) return;

  const cards = document.querySelectorAll("[data-section-card]");
  let totalWords = 0;

  cards.forEach((card) => {
    const textArea = card.querySelector("[data-section-text]");
    const targetTimeInput = card.querySelector("[data-target-time-input]");
    const actualWordsEl = card.querySelector("[data-actual-words]");
    const actualTimeEl = card.querySelector("[data-actual-time]");
    const targetWordsEl = card.querySelector("[data-target-words]");

    const actualWords = countWords(textArea.value);
    const targetTime = parseFloat(targetTimeInput.value || "0");
    const targetWords = Math.round(targetTime * config.wordsPerMinute);
    const actualTime = config.wordsPerMinute
      ? (actualWords / config.wordsPerMinute).toFixed(2)
      : "0.00";

    totalWords += actualWords;
    actualWordsEl.textContent = actualWords;
    actualTimeEl.textContent = `${actualTime} min`;
    targetWordsEl.textContent = targetWords;
  });

  const totalTime = config.wordsPerMinute
    ? (totalWords / config.wordsPerMinute).toFixed(2)
    : "0.00";

  const totalWordsEl = document.querySelector("[data-talk-actual-words]");
  const totalTimeEl = document.querySelector("[data-talk-actual-time]");
  if (totalWordsEl) totalWordsEl.textContent = totalWords;
  if (totalTimeEl) totalTimeEl.textContent = `${totalTime} min`;
}

function renumberSortOrder() {
  const cards = document.querySelectorAll("[data-section-card]");
  cards.forEach((card, index) => {
    const input = card.querySelector("[data-sort-order-input]");
    if (input) input.value = index;
    const badge = card.querySelector("[data-section-position]");
    if (badge) badge.textContent = `Section ${index + 1}`;
  });
}

function hasPromptChanges() {
  const promptAreas = document.querySelectorAll("[data-section-prompt]");
  const sectionChanged = Array.from(promptAreas).some((area) => {
    const card = area.closest("[data-section-card]");
    const original = card.querySelector("[data-original-prompt]");
    return (area.value || "").trim() !== (original.value || "").trim();
  });
  if (sectionChanged) return true;

  const globalPrompt = document.getElementById("global-revision-prompt");
  const originalGlobalPrompt = document.getElementById("original-global-revision-prompt");
  return (
    globalPrompt &&
    originalGlobalPrompt &&
    (globalPrompt.value || "").trim() !== (originalGlobalPrompt.value || "").trim()
  );
}

function syncPromptChangedState() {
  document.querySelectorAll("[data-section-prompt]").forEach((area) => {
    const card = area.closest("[data-section-card]");
    const original = card.querySelector("[data-original-prompt]");
    const lastApplied = card.querySelector("[data-last-applied-prompt]");
    const status = card.querySelector("[data-section-prompt-status]");
    const value = (area.value || "").trim();
    const changed = (area.value || "").trim() !== (original.value || "").trim();
    card.classList.toggle("section-card-changed", changed);
    if (status) {
      const applied = (lastApplied?.value || "").trim();
      const state = !value ? "empty" : value === applied ? "applied" : "pending";
      status.textContent =
        state === "pending"
          ? "Pending changes for next AI update"
          : state === "applied"
            ? "Last used in AI update"
            : "No section prompt yet";
      status.className = `prompt-status prompt-status-${state}`;
    }
  });

  const globalPrompt = document.getElementById("global-revision-prompt");
  const originalGlobalPrompt = document.getElementById("original-global-revision-prompt");
  const lastAppliedGlobalPrompt = document.getElementById("last-applied-global-revision-prompt");
  const panel = document.querySelector(".global-prompt-panel");
  const status = document.querySelector("[data-global-prompt-status]");
  if (globalPrompt && originalGlobalPrompt && panel) {
    const changed =
      (globalPrompt.value || "").trim() !== (originalGlobalPrompt.value || "").trim();
    panel.classList.toggle("prompt-panel-changed", changed);
    if (status) {
      const value = (globalPrompt.value || "").trim();
      const applied = (lastAppliedGlobalPrompt?.value || "").trim();
      const state = !value ? "empty" : value === applied ? "applied" : "pending";
      status.textContent =
        state === "pending"
          ? "Pending changes for next AI update"
          : state === "applied"
            ? "Last used in AI update"
            : "No talk-level revision prompt yet";
      status.className = `prompt-status prompt-status-${state}`;
    }
  }
}

function setLoadingState(action) {
  const overlay = document.getElementById("loading-overlay");
  const message = document.getElementById("loading-message");
  if (!overlay || !message) return;

  const messages = {
    generate: "Generating the talk structure and section drafts now.",
    ai_update: "Updating the talk with AI and reloading changed sections.",
    update_section: "Updating the selected section and reloading the editor.",
  };

  message.textContent =
    messages[action] || "Waiting for the AI response and reloading the updated draft.";
  overlay.style.display = "grid";
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("is-loading");
  document.querySelectorAll("button, input, textarea, select").forEach((element) => {
    element.disabled = true;
  });
}

function clearLoadingState() {
  const overlay = document.getElementById("loading-overlay");
  if (overlay) {
    overlay.style.display = "none";
    overlay.setAttribute("aria-hidden", "true");
  }
  document.body.classList.remove("is-loading");
  document.querySelectorAll("button, input, textarea, select").forEach((element) => {
    element.disabled = false;
  });
}

function moveSection(button, direction) {
  const card = button.closest("[data-section-card]");
  const container = card.parentElement;
  if (direction < 0 && card.previousElementSibling) {
    container.insertBefore(card, card.previousElementSibling);
  } else if (direction > 0 && card.nextElementSibling) {
    container.insertBefore(card.nextElementSibling, card);
  }
  renumberSortOrder();
  card.classList.add("section-card-moved");
  window.setTimeout(() => {
    card.classList.remove("section-card-moved");
  }, 700);
}

function continueSubmitAfterPaint(form, submitter) {
  window.setTimeout(() => {
    form.dataset.allowImmediateSubmit = "true";
    if (submitter && typeof form.requestSubmit === "function") {
      form.requestSubmit(submitter);
      return;
    }
    form.submit();
  }, 20);
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.id !== "talk-editor-form") return;

  if (form.dataset.allowImmediateSubmit === "true") {
    delete form.dataset.allowImmediateSubmit;
    return;
  }

  const submitter = event.submitter;
  const action =
    submitter?.dataset.submitAction ||
    submitter?.value ||
    submitter?.getAttribute("value") ||
    "save";
  const forceRerunInput = document.getElementById("force-rerun-input");
  if (forceRerunInput) forceRerunInput.value = "0";

  if (action === "ai_update" && !hasPromptChanges()) {
    const confirmed = window.confirm(
      "No talk-level or section-level revision prompts changed. Do you want to rerun the same AI update anyway?"
    );
    if (!confirmed) {
      event.preventDefault();
      return;
    }
    if (forceRerunInput) forceRerunInput.value = "1";
  }

  if (["generate", "ai_update", "update_section"].includes(action)) {
    event.preventDefault();
    setLoadingState(action);
    continueSubmitAfterPaint(form, submitter);
  }
});

document.addEventListener("input", (event) => {
  if (
    event.target.matches(
      "[data-section-text], [data-target-time-input], [data-section-prompt], [data-global-revision-prompt]"
    )
  ) {
    updateEditorMetrics();
    syncPromptChangedState();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  clearLoadingState();
  renumberSortOrder();
  updateEditorMetrics();
  syncPromptChangedState();
});
