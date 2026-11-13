
const API_URL = "http://127.0.0.1:8000";

const form = document.getElementById("application-form");
const message = document.getElementById("message");

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    message.textContent = "Envoi de votre candidature...";
    message.style.color = "#101C35";

    const candidature = {
        nom: document.getElementById("nom").value.trim(),
        prenom: document.getElementById("prenom").value.trim(),
        email: document.getElementById("email").value.trim(),
        telephone: document.getElementById("telephone").value.trim() || null,
        niveau: document.getElementById("niveau").value,
        motivation: document.getElementById("motivation").value.trim()
    };

    try {
        const response = await fetch(`${API_URL}/applications/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(candidature)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                typeof result.detail === "string"
                    ? result.detail
                    : "Impossible d'envoyer votre candidature."
            );
        }

        message.textContent =
            "Votre candidature EDUNOVA a été envoyée avec succès !";

        message.style.color = "#16803C";

        form.reset();

    } catch (error) {
        message.textContent = error.message;
        message.style.color = "#DC2626";
    }
});
