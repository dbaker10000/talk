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
  });
}

function hasPromptChanges() {
  const promptAreas = document.querySelectorAll("[data-section-prompt]");
  return Array.from(promptAreas).some((area) => {
    const card = area.closest("[data-section-card]");
    const original = card.querySelector("[data-original-prompt]");
    return (area.value || "").trim() !== (original.value || "").trim();
  });
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
  overlay.hidden = false;
  document.body.classList.add("is-loading");
  document.querySelectorAll("button, input, textarea, select").forEach((element) => {
    element.disabled = true;
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
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.id !== "talk-editor-form") return;

  const action = document.getElementById("editor-action")?.value || "save";
  const forceRerunInput = document.getElementById("force-rerun-input");
  if (forceRerunInput) forceRerunInput.value = "0";

  if (action === "ai_update" && !hasPromptChanges()) {
    const confirmed = window.confirm(
      "No section prompts changed. Do you want to rerun the same AI update anyway?"
    );
    if (!confirmed) {
      event.preventDefault();
      return;
    }
    if (forceRerunInput) forceRerunInput.value = "1";
  }

  if (["generate", "ai_update", "update_section"].includes(action)) {
    setLoadingState(action);
  }
});

document.addEventListener("input", (event) => {
  if (
    event.target.matches("[data-section-text], [data-target-time-input], [data-section-prompt]")
  ) {
    updateEditorMetrics();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  renumberSortOrder();
  updateEditorMetrics();
});
