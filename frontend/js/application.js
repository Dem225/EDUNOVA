
"use strict";

const form = document.getElementById("application-form");
const message = document.getElementById("message");
const submitButton = form.querySelector('button[type="submit"]');
const TEXTE_BOUTON = submitButton.textContent.trim();

const CHAMPS = {
    nom: { element: document.getElementById("nom"), libelle: "Nom" },
    prenom: { element: document.getElementById("prenom"), libelle: "Prénom(s)" },
    email: { element: document.getElementById("email"), libelle: "Adresse e-mail" },
    telephone: { element: document.getElementById("telephone"), libelle: "Téléphone" },
    niveau: { element: document.getElementById("niveau"), libelle: "Parcours éducatif" },
    motivation: { element: document.getElementById("motivation"), libelle: "Motivation" }
};

const MESSAGES = {
    envoi: "Envoi de votre candidature...",
    succes: "Votre candidature EDUNOVA a été envoyée avec succès !",
    reseau: "Impossible de joindre le serveur EDUNOVA. Vérifiez votre connexion puis réessayez.",
    timeout: "Le serveur EDUNOVA met trop de temps à répondre. Veuillez réessayer.",
    indisponible: "Le service est momentanément indisponible. Veuillez réessayer plus tard.",
    serveur: "Une erreur est survenue lors de l'envoi de votre candidature. Veuillez réessayer.",
    inattendu: "Le serveur a renvoyé une réponse inattendue. Veuillez réessayer.",
    generique: "Impossible d'envoyer votre candidature. Veuillez vérifier vos informations."
};

const DELAI_TIMEOUT_MS = 10000;
const DELAI_ATTENTE_MAX = 300;

let generation = 0;
let enAttente = false;

function apiBaseUrl() {
    const configuree = (
        form.dataset.apiBaseUrl ||
        window.EDUNOVA_API_BASE_URL ||
        ""
    ).trim();

    if (configuree) {
        return configuree.replace(/\/+$/, "");
    }

    const { protocol, hostname, port } = window.location;

    if (protocol === "file:") {
        return "http://127.0.0.1:8000";
    }

    if (
        (hostname === "127.0.0.1" || hostname === "localhost") &&
        (port === "5500" || port === "5501")
    ) {
        return "http://127.0.0.1:8000";
    }

    return window.location.origin;
}

function setMessage(texte, type) {
    message.textContent = texte;
    message.className = "message--" + type;
}

function nettoyerErreurs() {
    Object.values(CHAMPS).forEach(({ element }) => {
        element.removeAttribute("aria-invalid");
        element.classList.remove("est-invalide");
    });
}

function secondesAvantNouvelEnvoi(valeur) {
    if (!valeur) {
        return 60;
    }

    const secondes = Number(valeur.trim());
    if (Number.isFinite(secondes)) {
        return Math.max(1, Math.min(Math.ceil(secondes), DELAI_ATTENTE_MAX));
    }

    const date = Date.parse(valeur);
    if (!Number.isNaN(date)) {
        return Math.max(
            1,
            Math.min(Math.ceil((date - Date.now()) / 1000), DELAI_ATTENTE_MAX)
        );
    }

    return 60;
}

function messagesValidation(detail) {
    if (!Array.isArray(detail)) {
        return [];
    }

    const resultats = [];
    const vus = new Set();

    detail.forEach((erreur) => {
        const loc = Array.isArray(erreur.loc) ? erreur.loc : [];
        const cle = loc.find((partie) =>
            Object.prototype.hasOwnProperty.call(CHAMPS, partie)
        );
        const champ = cle ? CHAMPS[cle] : null;
        const type = String(erreur.type || "");
        const msg = String(erreur.msg || "").toLowerCase();
        const ctx = erreur.ctx || {};
        const limite = ctx.min_length ?? ctx.max_length ?? ctx.limit_value;
        let texte;

        if (
            cle === "email" &&
            (type.includes("email") || type.includes("value_error") || msg.includes("email"))
        ) {
            texte = "Veuillez saisir une adresse e-mail valide.";
        } else if (type.includes("missing")) {
            texte = champ
                ? "Le champ " + champ.libelle + " est obligatoire."
                : "Certains champs sont obligatoires.";
        } else if (type.includes("too_short") || type.includes("min_length")) {
            const borne = Number(limite);
            texte = (champ ? champ.libelle : "Ce champ") +
                " doit contenir au moins " + borne +
                " caractère" + (borne > 1 ? "s" : "") + ".";
        } else if (type.includes("too_long") || type.includes("max_length")) {
            const borne = Number(limite);
            texte = (champ ? champ.libelle : "Ce champ") +
                " doit contenir au plus " + borne +
                " caractère" + (borne > 1 ? "s" : "") + ".";
        } else if (type.includes("literal") || type.includes("enum")) {
            texte = "Veuillez choisir un parcours valide.";
        } else if (champ) {
            texte = "La valeur du champ " + champ.libelle + " n'est pas valide.";
        } else {
            texte = "Certaines informations ne sont pas valides.";
        }

        const signature = (cle || "") + "|" + texte;
        if (!vus.has(signature)) {
            vus.add(signature);
            resultats.push({ champ, texte });
        }
    });

    return resultats;
}

async function lireJson(response) {
    try {
        return await response.json();
    } catch (erreur) {
        return null;
    }
}

function activerApresDelai(secondes, maGeneration) {
    let restant = secondes;
    submitButton.disabled = true;

    const afficher = () => {
        setMessage(
            "Trop de tentatives. Veuillez réessayer dans " + restant +
            " seconde" + (restant > 1 ? "s" : "") + ".",
            "erreur"
        );
    };

    afficher();

    const intervalle = setInterval(() => {
        if (maGeneration !== generation) {
            clearInterval(intervalle);
            return;
        }

        restant -= 1;

        if (restant <= 0) {
            clearInterval(intervalle);
            enAttente = false;
            submitButton.disabled = false;
            submitButton.textContent = TEXTE_BOUTON;
            setMessage("Vous pouvez à présent réessayer.", "info");
            return;
        }

        afficher();
    }, 1000);
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    generation += 1;
    const maGeneration = generation;
    enAttente = false;

    nettoyerErreurs();
    form.setAttribute("aria-busy", "true");

    submitButton.disabled = true;
    submitButton.textContent = "Envoi en cours...";
    setMessage(MESSAGES.envoi, "info");

    const candidature = {
        nom: document.getElementById("nom").value.trim(),
        prenom: document.getElementById("prenom").value.trim(),
        email: document.getElementById("email").value.trim(),
        telephone: document.getElementById("telephone").value.trim() || null,
        niveau: document.getElementById("niveau").value,
        motivation: document.getElementById("motivation").value.trim()
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), DELAI_TIMEOUT_MS);

    try {
        const response = await fetch(apiBaseUrl() + "/applications/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(candidature),
            signal: controller.signal
        });

        const contentType = (response.headers.get("content-type") || "").toLowerCase();
        const estJson = contentType.includes("application/json");

        if (response.status === 429) {
            const secondes = secondesAvantNouvelEnvoi(
                response.headers.get("retry-after")
            );
            enAttente = true;
            activerApresDelai(secondes, maGeneration);
            return;
        }

        if (response.status === 422) {
            const donneesErreur = estJson ? await lireJson(response) : null;
            const erreurs = messagesValidation(
                donneesErreur ? donneesErreur.detail : null
            );

            if (erreurs.length === 0) {
                setMessage(MESSAGES.generique, "erreur");
                return;
            }

            erreurs.forEach(({ champ }) => {
                if (champ) {
                    champ.element.setAttribute("aria-invalid", "true");
                    champ.element.classList.add("est-invalide");
                }
            });

            setMessage(
                "Veuillez corriger les informations suivantes :\n" +
                erreurs.map((erreur) => "• " + erreur.texte).join("\n"),
                "erreur"
            );

            const premierChamp = erreurs.find((erreur) => erreur.champ);
            if (premierChamp) {
                premierChamp.champ.element.focus();
            }
            return;
        }

        if (!response.ok) {
            const donneesErreur = estJson ? await lireJson(response) : null;

            if (response.status === 503) {
                setMessage(MESSAGES.indisponible, "erreur");
            } else if (response.status >= 500) {
                setMessage(MESSAGES.serveur, "erreur");
            } else if (donneesErreur && typeof donneesErreur.detail === "string") {
                setMessage(donneesErreur.detail, "erreur");
            } else {
                setMessage(MESSAGES.generique, "erreur");
            }
            return;
        }

        if (!estJson) {
            setMessage(MESSAGES.inattendu, "erreur");
            return;
        }

        const donnees = await lireJson(response);
        if (!donnees) {
            setMessage(MESSAGES.inattendu, "erreur");
            return;
        }

        setMessage(MESSAGES.succes, "succes");
        nettoyerErreurs();
        form.reset();

    } catch (error) {
        if (error && error.name === "AbortError") {
            setMessage(MESSAGES.timeout, "erreur");
        } else if (error instanceof TypeError) {
            setMessage(MESSAGES.reseau, "erreur");
        } else {
            setMessage(MESSAGES.serveur, "erreur");
        }
    } finally {
        clearTimeout(timeoutId);
        if (!enAttente && maGeneration === generation) {
            form.removeAttribute("aria-busy");
            submitButton.disabled = false;
            submitButton.textContent = TEXTE_BOUTON;
        }
    }
});
