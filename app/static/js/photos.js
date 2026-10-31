(function () {
  "use strict";

  const gallery = document.getElementById("photo-gallery");
  document.querySelectorAll(".print-photo").forEach((button) => {
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
      } catch (error) {
        status.textContent = error.message || "Não foi possível imprimir a foto. Tente novamente.";
      } finally {
        button.disabled = false;
        button.textContent = "Imprimir";
      }
    });
  });
})();
