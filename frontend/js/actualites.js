/*
    EDUNOVA - Page « Actualités » : filtres de catégories et animations
    discrètes. Script classique, sans module. GSAP et ScrollTrigger sont
    chargés avant. Sans ces bibliothèques, ou si le mouvement est réduit,
    le contenu reste entièrement visible : aucune classe n'est ajoutée
    à <html>.
*/
(() => {
    "use strict";

    // État partagé entre les filtres et les animations.
    const racine = document.documentElement;
    const elements = document.querySelectorAll(".actu-anime");
    const mouvement = window.matchMedia("(prefers-reduced-motion: reduce)");
    const gsap = window.gsap;
    const ScrollTrigger = window.ScrollTrigger;
    let declencheurs = [];
    let actif = false;

    /* ===== FILTRES DE CATÉGORIES =====
       Les six cartes de démonstration sont réellement filtrées : les
       boutons mettent à jour l'état aria-pressed et un message vivant. */

    const boutonsFiltre = document.querySelectorAll("[data-filtre]");
    const publications = document.querySelectorAll(".actu-publication[data-categorie]");
    const statutFiltre = document.getElementById("statut-filtre");

    const appliquerFiltre = (valeur) => {
        let visible = 0;

        publications.forEach((publication) => {
            const correspond = valeur === "toutes" || publication.dataset.categorie === valeur;
            publication.hidden = !correspond;
            if (correspond) visible += 1;
        });

        let libelle = "Toutes";
        boutonsFiltre.forEach((bouton) => {
            const actif = bouton.dataset.filtre === valeur;
            bouton.classList.toggle("est-actif", actif);
            bouton.setAttribute("aria-pressed", actif ? "true" : "false");
            if (actif) libelle = bouton.dataset.libelle || bouton.textContent.trim();
        });

        if (statutFiltre) {
            statutFiltre.textContent = `${visible} publication${visible > 1 ? "s" : ""} de démonstration affichée${visible > 1 ? "s" : ""} pour ${libelle}.`;
        }
    };

    boutonsFiltre.forEach((bouton) => {
        bouton.addEventListener("click", () => {
            appliquerFiltre(bouton.dataset.filtre);
            if (actif && ScrollTrigger && typeof ScrollTrigger.refresh === "function") {
                ScrollTrigger.refresh();
            }
        });
    });

    /* ===== ANIMATIONS DISCRÈTES ===== */

    if (!elements.length) return;

    // Retire l'état caché et toutes les animations en cours.
    const arreter = () => {
        declencheurs.forEach((declencheur) => declencheur.kill());
        declencheurs = [];
        racine.classList.remove("actu-animations-actives");
        if (gsap) gsap.set(elements, { clearProps: "opacity,transform,visibility" });
        actif = false;
    };

    // Regroupe les éléments par section pour un léger échelonnement.
    const grouperParSection = () => {
        const groupes = new Map();
        elements.forEach((element) => {
            const section = element.closest("section") || document.body;
            if (!groupes.has(section)) groupes.set(section, []);
            groupes.get(section).push(element);
        });
        return groupes;
    };

    // Apparition au défilement : une seule fois, 0,6 à 0,9 s, power3.out.
    const demarrer = () => {
        if (actif || mouvement.matches || !gsap || !ScrollTrigger) return;
        actif = true;

        gsap.registerPlugin(ScrollTrigger);
        racine.classList.add("actu-animations-actives");

        grouperParSection().forEach((groupe, section) => {
            const estTitre = groupe[0].matches("h1, h2, .surtitre, .badge, .panneau__surtitre, .actu-actions");
            const animation = gsap.to(groupe, {
                opacity: 1,
                y: 0,
                duration: estTitre ? 0.7 : 0.85,
                ease: "power3.out",
                stagger: 0.08,
                scrollTrigger: {
                    trigger: section,
                    start: "top 85%",
                    once: true
                }
            });

            if (animation.scrollTrigger) declencheurs.push(animation.scrollTrigger);
        });

        ScrollTrigger.refresh();
    };

    // Aucune animation si la préférence système change en cours de session.
    const surChangementMouvement = (evenement) => {
        if (evenement.matches) arreter();
        else demarrer();
    };

    if (typeof mouvement.addEventListener === "function") {
        mouvement.addEventListener("change", surChangementMouvement);
    } else if (typeof mouvement.addListener === "function") {
        mouvement.addListener(surChangementMouvement);
    }

    demarrer();

    // Les polices peuvent modifier la hauteur des textes : recalcule alors
    // les positions des déclencheurs pour éviter qu'un seuil soit manqué.
    if (document.fonts && typeof document.fonts.ready.then === "function") {
        document.fonts.ready.then(() => {
            if (actif) ScrollTrigger.refresh();
        });
    }
})();
