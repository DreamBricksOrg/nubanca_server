(function () {
  "use strict";

  const gallery = document.getElementById("photo-gallery");
  const scope = document.body.dataset.printScope;
  const warning = document.getElementById("history-warning");
  const printButtons = document.querySelectorAll(".print-photo");
  const acceptedThisPage = new Map();
  let refreshVersion = 0;

  function markPrinted(button, row) {
    const card = button.closest(".photo-card");
    card.classList.toggle("is-printed", Boolean(row));
    card.querySelector(".print-history-label").textContent = row
      ? `Enviada à impressão (${row.printCount} envio(s))` : "";
  }

  async function refreshHistory() {
    const version = ++refreshVersion;
    try {
      const rows = await window.PrintHistory.list(scope);
      if (version !== refreshVersion) return;
      const byKey = new Map(rows.map((row) => [row.key, row]));
      printButtons.forEach((button) => {
        const saved = byKey.get(button.dataset.key);
        const accepted = acceptedThisPage.get(button.dataset.key);
        markPrinted(button, saved && (!accepted || saved.printCount >= accepted.printCount) ? saved : accepted);
      });
      warning.textContent = "";
    } catch (error) {
      warning.textContent = "Histórico local indisponível. Os contornos e a previsão podem estar incompletos.";
    }
  }

  refreshHistory();
  window.addEventListener("focus", refreshHistory);

  printButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;

      const status = button.closest(".photo-card").querySelector(".print-status");
      button.disabled = true;
      button.textContent = "Imprimindo...";
      status.textContent = "Enviando foto para a impressora...";
      try {
        const response = await fetch(gallery.dataset.printUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: button.dataset.key }),
        });
        const result = await response.json();
        if (!response.ok || !result.success || !result.printed) {
          throw new Error(result.message || "Não foi possível imprimir a foto.");
        }
        status.textContent = result.message;
        const accepted = { key: button.dataset.key, printCount: 1 };
        acceptedThisPage.set(button.dataset.key, accepted);
        markPrinted(button, accepted);
        try {
          const row = await window.PrintHistory.record(scope, result.photo_key, result.queued_at);
          acceptedThisPage.set(button.dataset.key, row);
          markPrinted(button, row);
        } catch (error) {
          status.textContent += " Não foi possível salvar o histórico local; não imprima novamente por esse motivo.";
        }
      } catch (error) {
        status.textContent = error.message || "Não foi possível imprimir a foto. Tente novamente.";
      } finally {
        button.disabled = false;
        button.textContent = "Imprimir";
      }
    });
  });

  document.querySelectorAll(".estimate-photo").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      button.disabled = true;
      const output = button.closest(".photo-card").querySelector(".print-estimate");
      try {
        const result = await window.PrintHistory.estimate(scope, button.dataset.key);
        const time = new Date(result.readyAt).toLocaleString("pt-BR");
        const seconds = Math.ceil(result.remainingMs / 1000);
        const wait = `${Math.floor(seconds / 60)}min ${seconds % 60}s`;
        const prefix = result.recorded ? "Previsão" : "Se enviada agora, previsão";
        const remaining = result.recorded && seconds === 0
          ? "a estimativa já venceu; confirme na impressora" : `em cerca de ${wait}`;
        const fileTime = window.PrintHistory.fileTime(button.dataset.key);
        output.textContent = `${prefix}: ${time} (${remaining}).` +
          (fileTime ? ` Data do arquivo: ${fileTime} (horário do servidor).` : "");
      } catch (error) {
        output.textContent = "Não foi possível estimar: histórico local indisponível.";
      } finally {
        button.disabled = false;
      }
    });
  });
})();
