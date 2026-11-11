document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("userSearch");
  const select = document.getElementById("recipientSelect");
  if (search && select) {
    search.addEventListener("input", () => {
      const term = search.value.toLowerCase();
      [...select.options].forEach((option, index) => {
        if (index === 0) return;
        option.hidden = !option.text.toLowerCase().includes(term);
      });
    });
  }
  document.querySelectorAll("[data-copy]").forEach(button => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = "Copié !";
        setTimeout(() => button.textContent = "Copier", 1600);
      } catch {
        button.textContent = "Copie indisponible";
      }
    });
  });

  const dashboardStats = document.getElementById("dashboardBlockStats");
  if (dashboardStats) {
    const refreshDashboardStats = async () => {
      try {
        const response = await fetch(dashboardStats.dataset.refreshUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`Erreur HTTP ${response.status}`);
        const stats = await response.json();
        document.getElementById("dashboardBlockCount").textContent = stats.block_count;
        document.getElementById("dashboardGenerationHours").textContent =
          Number(stats.generation_hours).toLocaleString("fr-FR", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
          });
      } catch (error) {
        console.error("Impossible d'actualiser les statistiques des blocs.", error);
      }
    };
    window.setInterval(refreshDashboardStats, 2000);
  }

  const privateKeyButton = document.getElementById("togglePrivateKey");
  const privateKeyOutput = document.getElementById("privateKey");
  const privateKeyError = document.getElementById("privateKeyError");
  if (privateKeyButton && privateKeyOutput && privateKeyError) {
    privateKeyButton.addEventListener("click", async () => {
      privateKeyError.hidden = true;
      if (!privateKeyOutput.hidden) {
        privateKeyOutput.textContent = "";
        privateKeyOutput.hidden = true;
        privateKeyButton.textContent = "Afficher ma clé privée";
        privateKeyButton.setAttribute("aria-expanded", "false");
        return;
      }

      privateKeyButton.disabled = true;
      try {
        const response = await fetch(privateKeyButton.dataset.keyUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`Erreur HTTP ${response.status}`);
        const data = await response.json();
        if (typeof data.private_key !== "string" || !data.private_key) {
          throw new Error("La clé privée est absente de la réponse.");
        }
        privateKeyOutput.textContent = data.private_key;
        privateKeyOutput.hidden = false;
        privateKeyButton.textContent = "Cacher ma clé privée";
        privateKeyButton.setAttribute("aria-expanded", "true");
      } catch (error) {
        console.error("Impossible de charger la clé privée.", error);
        privateKeyError.textContent = "Impossible de charger la clé privée. Réessayez.";
        privateKeyError.hidden = false;
      } finally {
        privateKeyButton.disabled = false;
      }
    });
  }

  const chainList = document.getElementById("chainList");
  if (chainList) {
    const refreshChain = async () => {
      try {
        const response = await fetch(chainList.dataset.refreshUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`Erreur HTTP ${response.status}`);
        const html = await response.text();
        const openBlockIndexes = new Set(
          [...chainList.querySelectorAll(".block-row-details[open]")].map(details => details.dataset.blockIndex)
        );
        chainList.innerHTML = html;
        chainList.querySelectorAll(".block-row-details").forEach(details => {
          details.open = openBlockIndexes.has(details.dataset.blockIndex);
        });
      } catch (error) {
        console.error("Impossible d'actualiser la blockchain.", error);
      } finally {
        window.setTimeout(refreshChain, 2000);
      }
    };
    window.setTimeout(refreshChain, 2000);
  }
});
