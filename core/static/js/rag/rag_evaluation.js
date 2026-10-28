
document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("runRagEvaluationBtn");

    if (!button) return;

    let tenderId = null;

    document.addEventListener("raynder:tender-loaded", (event) => {
        tenderId = event.detail?.tender_id || null;
    });

    button.addEventListener("click", async () => {
        if (!tenderId) {
            alert("Tender information is still loading. Please try again.");
            return;
        }

        const originalContent = button.innerHTML;

        button.disabled = true;
        button.innerHTML = `
            <span class="spinner-border spinner-border-sm me-1"></span>
            Starting evaluation...
        `;

        try {
            const response = await fetch("/api/ai/evaluations/run/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({
                    tender_id: tenderId,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Could not start evaluation.");
            }

            alert(data.message || "Evaluation started successfully.");

        } catch (error) {
            alert(error.message || "An unexpected error occurred.");
        } finally {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    });

    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : "";
    }
});
