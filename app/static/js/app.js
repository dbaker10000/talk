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

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-section-text], [data-target-time-input]")) {
    updateEditorMetrics();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  renumberSortOrder();
  updateEditorMetrics();
});
