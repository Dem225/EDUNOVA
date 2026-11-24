/*
    EDUNOVA - Interactions simples : menu mobile et dialogue de candidature.
    Aucun framework, aucune dépendance, scripts chargés avec defer.
*/
(() => {
  "use strict";

  // ===== MENU MOBILE =====

  const boutonMenu = document.querySelector("[data-menu-mobile]");
  const panneauMenu = document.querySelector("[data-menu-mobile-panneau]");

  // Ferme le panneau et remet le bouton dans son état initial.
  const fermerMenu = () => {
    if (!boutonMenu || !panneauMenu) return;
    panneauMenu.classList.add("cache");
    boutonMenu.setAttribute("aria-expanded", "false");
    boutonMenu.setAttribute("aria-label", "Ouvrir le menu de navigation");
  };

  if (boutonMenu && panneauMenu) {
    // Ouvre ou ferme le menu au clic.
    boutonMenu.addEventListener("click", () => {
      const estOuvert = boutonMenu.getAttribute("aria-expanded") === "true";
      if (estOuvert) {
        fermerMenu();
        return;
      }
      panneauMenu.classList.remove("cache");
      boutonMenu.setAttribute("aria-expanded", "true");
      boutonMenu.setAttribute("aria-label", "Fermer le menu de navigation");
    });

    // Un clic sur un lien referme le menu.
    panneauMenu.querySelectorAll("a").forEach((lien) => {
      lien.addEventListener("click", fermerMenu);
    });

    // Échap referme le menu.
    document.addEventListener("keydown", (evenement) => {
      if (evenement.key === "Escape") fermerMenu();
    });

    // Le menu se referme quand on revient à l'affichage bureau.
    const bureau = window.matchMedia("(min-width: 768px)");
    const surChangement = (evenement) => {
      if (evenement.matches) fermerMenu();
    };
    if (typeof bureau.addEventListener === "function") {
      bureau.addEventListener("change", surChangement);
    } else if (typeof bureau.addListener === "function") {
      bureau.addListener(surChangement);
    }
  }

  // ===== LIEN ACTIF DE NAVIGATION (détecté depuis l'URL) =====

  // Seule la navigation du haut est concernée : menu bureau et panneau mobile.
  // Les liens du pied de page sont volontairement exclus : aucun aria-current,
  // aucune classe « active » et aucun trait n'y sera appliqué.
  const liensNavigation = document.querySelectorAll(
    ".nav-principale a.lien-nav, .menu-mobile a.lien-nav"
  );

  // « Vision & mission » est une sous-rubrique de « À propos » : elle partage
  // son entrée de navigation, qui n'existe pas encore comme lien distinct.
  const aliasPages = {
    "vision-mission.html": "a-propos.html",
  };

  const nomDePage = (chemin) => {
    const morceaux = chemin.split("/").filter(Boolean);
    // Une URL de dossier (/frontend/) sert index.html : le dernier morceau
    // est le nom du dossier, pas celui de la page.
    if (!morceaux.length || chemin.endsWith("/")) return "index.html";
    const dernier = morceaux[morceaux.length - 1];
    try {
      return decodeURIComponent(dernier);
    } catch (erreur) {
      return dernier;
    }
  };

  const marquerPageActive = () => {
    if (!liensNavigation.length) return;

    liensNavigation.forEach((lien) => {
      lien.removeAttribute("aria-current");
      lien.classList.remove("active");
    });

    const pageOuverte = nomDePage(window.location.pathname);
    const pageCible = aliasPages[pageOuverte] || pageOuverte;

    const liensActifs = Array.from(liensNavigation).filter((lien) => {
      // Une ancre seule (#accueil) pointe toujours vers l'accueil, même
      // depuis une autre page : sinon elle serait prise pour la page ouverte.
      const hrefBrut = lien.getAttribute("href") || "";
      if (hrefBrut.startsWith("#")) {
        return pageCible === "index.html";
      }
      const urlLien = new URL(lien.href, window.location.href);
      return nomDePage(urlLien.pathname) === pageCible;
    });

    // Différé d'une frame : le trait part de scaleX(0) puis s'anime, y compris
    // lors de l'arrivée sur une page après un clic.
    window.requestAnimationFrame(() => {
      liensActifs.forEach((lien) => {
        lien.setAttribute("aria-current", "page");
        lien.classList.add("active");
      });
    });
  };

  marquerPageActive();
  window.addEventListener("pageshow", marquerPageActive);

  // ===== DIALOGUE DE CANDIDATURE =====

  const dialogue = document.getElementById("candidature-dialog");
  const boutonsOuverture = document.querySelectorAll("[data-ouvrir-candidature]");
  const boutonFermeture = dialogue
    ? dialogue.querySelector("[data-fermer-candidature]")
    : null;
  let elementDeclencheur = null;

  if (dialogue && typeof dialogue.showModal === "function") {
    // Ouvre le dialogue en conservant le bouton d'origine.
    boutonsOuverture.forEach((bouton) => {
      bouton.addEventListener("click", () => {
        elementDeclencheur = bouton;
        dialogue.showModal();
      });
    });

    // Bouton de fermeture visible dans l'en-tête du dialogue.
    if (boutonFermeture) {
      boutonFermeture.addEventListener("click", () => dialogue.close());
    }

    // Comportement natif confirmé pour la touche Échap.
    dialogue.addEventListener("cancel", () => dialogue.close());

    // Clic sur le fond : fermeture sans changement d'apparence.
    dialogue.addEventListener("click", (evenement) => {
      if (evenement.target === dialogue) dialogue.close();
    });

    // Rend le focus au bouton qui a ouvert le dialogue.
    dialogue.addEventListener("close", () => {
      if (elementDeclencheur && document.contains(elementDeclencheur)) {
        elementDeclencheur.focus();
      }
      elementDeclencheur = null;
    });
  }
})();
