/* Veritas - language chooser: highlights the browser's language, nothing else. */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const wanted = (navigator.languages || [navigator.language || ""])
    .map((tag) => String(tag).slice(0, 2).toLowerCase())
    .find((code) => ["pt", "en", "fr"].includes(code));
  const card = wanted && document.querySelector(`.lang-card[data-lang="${wanted}"]`);
  if (card) card.classList.add("suggested");
});
