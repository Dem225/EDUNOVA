/*
    EDUNOVA - Téléphone international : initialise intl-tel-input en français,
    contrôle le numéro et transmet la valeur E.164 à js/application.js.
    Script classique, sans module. Traductions : intl-tel-input 25.12.6 (MIT).
*/
(() => {
    "use strict";

    const formulaire = document.getElementById("application-form");
    const champ = document.getElementById("telephone");
    const erreur = document.getElementById("telephone-erreur");
    const dialogue = document.getElementById("candidature-dialog");

    // Noms de pays et textes de l'interface en français.
    const TRADUCTIONS_FR = {
        "ac": "Île de l'Ascension",
        "ad": "Andorre",
        "ae": "Émirats arabes unis",
        "af": "Afghanistan",
        "ag": "Antigua-et-Barbuda",
        "ai": "Anguilla",
        "al": "Albanie",
        "am": "Arménie",
        "ao": "Angola",
        "ar": "Argentine",
        "as": "Samoa américaines",
        "at": "Autriche",
        "au": "Australie",
        "aw": "Aruba",
        "ax": "Îles Åland",
        "az": "Azerbaïdjan",
        "ba": "Bosnie-Herzégovine",
        "bb": "Barbade",
        "bd": "Bangladesh",
        "be": "Belgique",
        "bf": "Burkina Faso",
        "bg": "Bulgarie",
        "bh": "Bahreïn",
        "bi": "Burundi",
        "bj": "Bénin",
        "bl": "Saint-Barthélemy",
        "bm": "Bermudes",
        "bn": "Brunéi Darussalam",
        "bo": "Bolivie",
        "bq": "Pays-Bas caribéens",
        "br": "Brésil",
        "bs": "Bahamas",
        "bt": "Bhoutan",
        "bw": "Botswana",
        "by": "Biélorussie",
        "bz": "Belize",
        "ca": "Canada",
        "cc": "Îles Cocos",
        "cd": "Congo-Kinshasa",
        "cf": "République centrafricaine",
        "cg": "Congo-Brazzaville",
        "ch": "Suisse",
        "ci": "Côte d’Ivoire",
        "ck": "Îles Cook",
        "cl": "Chili",
        "cm": "Cameroun",
        "cn": "Chine",
        "co": "Colombie",
        "countryListAriaLabel": "Liste des pays",
        "cr": "Costa Rica",
        "cu": "Cuba",
        "cv": "Cap-Vert",
        "cw": "Curaçao",
        "cx": "Île Christmas",
        "cy": "Chypre",
        "cz": "Tchéquie",
        "de": "Allemagne",
        "dj": "Djibouti",
        "dk": "Danemark",
        "dm": "Dominique",
        "do": "République dominicaine",
        "dz": "Algérie",
        "ec": "Équateur",
        "ee": "Estonie",
        "eg": "Égypte",
        "eh": "Sahara occidental",
        "er": "Érythrée",
        "es": "Espagne",
        "et": "Éthiopie",
        "fi": "Finlande",
        "fj": "Fidji",
        "fk": "Îles Malouines",
        "fm": "États fédérés de Micronésie",
        "fo": "Îles Féroé",
        "fr": "France",
        "ga": "Gabon",
        "gb": "Royaume-Uni",
        "gd": "Grenade",
        "ge": "Géorgie",
        "gf": "Guyane française",
        "gg": "Guernesey",
        "gh": "Ghana",
        "gi": "Gibraltar",
        "gl": "Groenland",
        "gm": "Gambie",
        "gn": "Guinée",
        "gp": "Guadeloupe",
        "gq": "Guinée équatoriale",
        "gr": "Grèce",
        "gt": "Guatemala",
        "gu": "Guam",
        "gw": "Guinée-Bissau",
        "gy": "Guyana",
        "hk": "R.A.S. chinoise de Hong Kong",
        "hn": "Honduras",
        "hr": "Croatie",
        "ht": "Haïti",
        "hu": "Hongrie",
        "id": "Indonésie",
        "ie": "Irlande",
        "il": "Israël",
        "im": "Île de Man",
        "in": "Inde",
        "io": "Territoire britannique de l’océan Indien",
        "iq": "Irak",
        "ir": "Iran",
        "is": "Islande",
        "it": "Italie",
        "je": "Jersey",
        "jm": "Jamaïque",
        "jo": "Jordanie",
        "jp": "Japon",
        "ke": "Kenya",
        "kg": "Kirghizistan",
        "kh": "Cambodge",
        "ki": "Kiribati",
        "km": "Comores",
        "kn": "Saint-Christophe-et-Niévès",
        "kp": "Corée du Nord",
        "kr": "Corée du Sud",
        "kw": "Koweït",
        "ky": "Îles Caïmans",
        "kz": "Kazakhstan",
        "la": "Laos",
        "lb": "Liban",
        "lc": "Sainte-Lucie",
        "li": "Liechtenstein",
        "lk": "Sri Lanka",
        "lr": "Libéria",
        "ls": "Lesotho",
        "lt": "Lituanie",
        "lu": "Luxembourg",
        "lv": "Lettonie",
        "ly": "Libye",
        "ma": "Maroc",
        "mc": "Monaco",
        "md": "Moldavie",
        "me": "Monténégro",
        "mf": "Saint-Martin",
        "mg": "Madagascar",
        "mh": "Îles Marshall",
        "mk": "Macédoine du Nord",
        "ml": "Mali",
        "mm": "Myanmar (Birmanie)",
        "mn": "Mongolie",
        "mo": "R.A.S. chinoise de Macao",
        "mp": "Îles Mariannes du Nord",
        "mq": "Martinique",
        "mr": "Mauritanie",
        "ms": "Montserrat",
        "mt": "Malte",
        "mu": "Maurice",
        "multipleSearchResults": "${count} résultats trouvés",
        "mv": "Maldives",
        "mw": "Malawi",
        "mx": "Mexique",
        "my": "Malaisie",
        "mz": "Mozambique",
        "na": "Namibie",
        "nc": "Nouvelle-Calédonie",
        "ne": "Niger",
        "nf": "Île Norfolk",
        "ng": "Nigéria",
        "ni": "Nicaragua",
        "nl": "Pays-Bas",
        "no": "Norvège",
        "noCountrySelected": "Aucun pays sélectionné",
        "np": "Népal",
        "nr": "Nauru",
        "nu": "Niue",
        "nz": "Nouvelle-Zélande",
        "om": "Oman",
        "oneSearchResult": "1 résultat trouvé",
        "pa": "Panama",
        "pe": "Pérou",
        "pf": "Polynésie française",
        "pg": "Papouasie-Nouvelle-Guinée",
        "ph": "Philippines",
        "pk": "Pakistan",
        "pl": "Pologne",
        "pm": "Saint-Pierre-et-Miquelon",
        "pr": "Porto Rico",
        "ps": "Territoires palestiniens",
        "pt": "Portugal",
        "pw": "Palaos",
        "py": "Paraguay",
        "qa": "Qatar",
        "re": "La Réunion",
        "ro": "Roumanie",
        "rs": "Serbie",
        "ru": "Russie",
        "rw": "Rwanda",
        "sa": "Arabie saoudite",
        "sb": "Îles Salomon",
        "sc": "Seychelles",
        "sd": "Soudan",
        "se": "Suède",
        "searchPlaceholder": "Recherche",
        "selectedCountryAriaLabel": "Pays sélectionné",
        "sg": "Singapour",
        "sh": "Sainte-Hélène",
        "si": "Slovénie",
        "sj": "Svalbard et Jan Mayen",
        "sk": "Slovaquie",
        "sl": "Sierra Leone",
        "sm": "Saint-Marin",
        "sn": "Sénégal",
        "so": "Somalie",
        "sr": "Suriname",
        "ss": "Soudan du Sud",
        "st": "Sao Tomé-et-Principe",
        "sv": "Salvador",
        "sx": "Saint-Martin (partie néerlandaise)",
        "sy": "Syrie",
        "sz": "Eswatini",
        "tc": "Îles Turques-et-Caïques",
        "td": "Tchad",
        "tg": "Togo",
        "th": "Thaïlande",
        "tj": "Tadjikistan",
        "tk": "Tokelau",
        "tl": "Timor oriental",
        "tm": "Turkménistan",
        "tn": "Tunisie",
        "to": "Tonga",
        "tr": "Turquie",
        "tt": "Trinité-et-Tobago",
        "tv": "Tuvalu",
        "tw": "Taïwan",
        "tz": "Tanzanie",
        "ua": "Ukraine",
        "ug": "Ouganda",
        "us": "États-Unis",
        "uy": "Uruguay",
        "uz": "Ouzbékistan",
        "va": "État de la Cité du Vatican",
        "vc": "Saint-Vincent-et-les-Grenadines",
        "ve": "Venezuela",
        "vg": "Îles Vierges britanniques",
        "vi": "Îles Vierges des États-Unis",
        "vn": "Vietnam",
        "vu": "Vanuatu",
        "wf": "Wallis-et-Futuna",
        "ws": "Samoa",
        "xk": "Kosovo",
        "ye": "Yémen",
        "yt": "Mayotte",
        "za": "Afrique du Sud",
        "zeroSearchResults": "Aucun résultat trouvé",
        "zm": "Zambie",
        "zw": "Zimbabwe"
    };

    if (!formulaire || !champ || typeof window.intlTelInput !== "function") return;

    let telephone = null;

    // Affiche ou masque l'erreur et l'état ARIA associé au champ.
    const afficherErreur = (visible) => {
        if (erreur) erreur.hidden = !visible;
        if (visible) champ.setAttribute("aria-invalid", "true");
        else champ.removeAttribute("aria-invalid");
    };

    // Remet le widget dans son état initial : Côte d'Ivoire et champ vide.
    const reinitialiser = () => {
        if (!telephone) return;
        champ.value = "";
        telephone.setCountry("ci");
        afficherErreur(false);
    };

    try {
        telephone = window.intlTelInput(champ, {
            initialCountry: "ci",
            countrySearch: true,
            separateDialCode: true,
            i18n: TRADUCTIONS_FR,
            autoPlaceholder: "off",
            useFullscreenPopup: false
        });
    } catch (exception) {
        // Repli silencieux : le champ texte d'origine reste utilisable.
        return;
    }

    // Convertit le numéro en E.164 avant l'écouteur de js/application.js.
    // La phase de capture garantit l'exécution avant l'envoi du formulaire.
    formulaire.addEventListener("submit", (evenement) => {
        const saisi = champ.value.trim();
        if (!saisi) {
            afficherErreur(false);
            return;
        }

        const valide = typeof telephone.isValidNumber === "function"
            ? telephone.isValidNumber()
            : /^\+?[0-9]{6,15}$/.test(saisi);
        if (!valide) {
            evenement.preventDefault();
            evenement.stopImmediatePropagation();
            afficherErreur(true);
            champ.focus();
            return;
        }

        afficherErreur(false);
        let complet = saisi;
        if (typeof telephone.getNumber === "function") {
            complet = telephone.getNumber() || saisi;
        }
        champ.value = complet.slice(0, 30);
    }, true);

    // Remise à zéro après un envoi réussi (form.reset()) ou une fermeture.
    formulaire.addEventListener("reset", () => {
        window.setTimeout(reinitialiser, 0);
    });
    if (dialogue) dialogue.addEventListener("close", reinitialiser);
})();
