
document.addEventListener("DOMContentLoaded", function () {
    const $ = (id) => document.getElementById(id);

    const button = $("generateSummaryBtn");
    const panel = $("tenderSummaryPanel");

    if (!button || !panel) return;

    // The URL contains the Tender database primary key.
    const pathParts = window.location.pathname
        .split("/")
        .filter(Boolean);

    const tenderPk = pathParts[pathParts.length - 1];

    if (!tenderPk) return;

    const API_BASE = `/api/ai/tenders/${encodeURIComponent(tenderPk)}`;

    let polling = false;
    let pollGeneration = 0;

    button.addEventListener("click", generateSummary);

    // Load an existing summary whenever the page opens.
    loadExistingSummary();

    async function generateSummary() {
        if (polling) return;

        panel.hidden = false;
        clearError();
        setButtonBusy(true);

        $("summaryLoading").hidden = false;
        $("summaryContent").hidden = true;
        $("summaryEmpty").hidden = true;

        setStatus("Submitting...");

        try {
            const response = await fetch(
                `${API_BASE}/generate-summary/?retry=true`,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                    },
                }
            );

            const data = await readJson(response);

            if (!response.ok) {
                throw new Error(
                    data.error || "Could not start summary generation."
                );
            }

            if (data.status === "completed") {
                await loadExistingSummary();
                return;
            }

            if (!["queued", "running"].includes(data.status)) {
                throw new Error(
                    data.message || "Summary generation could not be started."
                );
            }

            polling = true;
            const generation = ++pollGeneration;

            setStatus(data.status);
            await pollSummary(generation);

        } catch (error) {
            console.error("Summary generation error:", error);
            showError(error.message || "Summary generation failed.");
            setStatus("Failed");

        } finally {
            polling = false;
            setButtonBusy(false);
        }
    }

    async function loadExistingSummary() {
        panel.hidden = false;

        try {
            const response = await fetch(
                `${API_BASE}/summary/`,
                {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                    },
                }
            );

            const data = await readJson(response);

            if (!response.ok) {
                throw new Error(
                    data.error || "Could not retrieve tender summary."
                );
            }

            setStatus(formatStatus(data.status));

            if (data.status === "completed" && data.found) {
                renderSummary(data.summary, data.generated_at);
                return;
            }

            if (["queued", "running"].includes(data.status)) {
                $("summaryLoading").hidden = true;
                $("summaryContent").hidden = false;

                setStatus(formatStatus(data.status));

                // Do not disable the button or start polling automatically.
                button.disabled = false;

                return;
            }

            $("summaryLoading").hidden = true;
            $("summaryContent").hidden = true;
            $("summaryEmpty").hidden = false;

            if (data.status === "failed") {
                showError(data.error || "Previous summary generation failed.");
            }

        } catch (error) {
            console.error("Summary loading error:", error);
            showError(error.message || "Unable to load summary.");
        }
    }

    async function pollSummary(generation) {
        while (polling && generation === pollGeneration) {
            await delay(20000);

            if (!polling || generation !== pollGeneration) return;

            try {
                const response = await fetch(
                    `${API_BASE}/summary/`,
                    {
                        credentials: "same-origin",
                        headers: {
                            "Accept": "application/json",
                        },
                    }
                );

                const data = await readJson(response);

                if (!response.ok) {
                    throw new Error(
                        data.error || "Could not retrieve summary status."
                    );
                }

                setStatus(formatStatus(data.status));

                if (data.status === "completed") {
                    $("summaryLoading").hidden = true;

                    if (data.found && data.summary) {
                        renderSummary(data.summary, data.generated_at);
                    } else {
                        throw new Error(
                            "Generation completed but no summary was saved."
                        );
                    }

                    return;
                }

                if (data.status === "failed") {
                    throw new Error(
                        data.error || "Summary generation failed."
                    );
                }

                if (!["queued", "running"].includes(data.status)) {
                    throw new Error(
                        "Unexpected summary status: " + data.status
                    );
                }

            } catch (error) {
                showError(error.message || "Unable to check summary status.");
                setStatus("Error");
                return;
            }
        }
    }

    // --------------------------------------------------
    // Render structured summary
    // --------------------------------------------------


    function renderSummary(summary, generatedAt) {
        $("summaryLoading").hidden = true;
        $("summaryEmpty").hidden = true;
        $("summaryContent").hidden = false;

        clearError();

        // Hide/remove the old Executive Summary content.
        const executiveSummary = $("summaryExecutive");

        if (executiveSummary) {
            executiveSummary.textContent =
                summary.executive_summary || "Executive summary not available.";
        }

        const sectionsContainer = $("summarySections");
        sectionsContainer.replaceChildren();

        // Render summary statistics
        const stats = summary.statistics || {};

        const statsContainer = document.createElement("div");
        statsContainer.className = "row g-2 mb-4";

        ["found", "not_found", "unclear", "conflicting"].forEach(status => {
            const col = document.createElement("div");
            col.className = "col-6 col-md-3";

            col.innerHTML = `
            <div class="border rounded-3 p-3">
                <div class="small text-secondary text-capitalize">
                    ${status.replace("_", " ")}
                </div>
                <div class="fs-4 fw-bold">
                    ${stats[status] || 0}
                </div>
            </div>
        `;

            statsContainer.appendChild(col);
        });

        sectionsContainer.appendChild(statsContainer);

        // Render all individual heading sections
        // Render all individual heading sections
        (summary.sections || []).forEach(item => {

            const section = document.createElement("details");
            section.className = "summary-accordion";

            // -----------------------------------------
            // Always visible heading / one-liner
            // -----------------------------------------

            const summaryHeader = document.createElement("summary");

            const headerContent = document.createElement("div");
            headerContent.className = "summary-accordion-header";

            const heading = document.createElement("div");
            heading.className = "summary-accordion-title";
            heading.textContent = `${item.sr_no}. ${item.heading}`;

            const rightContent = document.createElement("div");
            rightContent.className = "d-flex align-items-center gap-2 flex-shrink-0";

            const status = document.createElement("span");

            status.className = "badge rounded-pill " + ({
                found: "bg-success",
                not_found: "bg-secondary",
                unclear: "bg-warning text-dark",
                conflicting: "bg-danger"
            }[item.status] || "bg-secondary");

            status.textContent = (item.status || "unclear").replace("_", " ");

            const chevron = document.createElement("i");
            chevron.className = "fa-solid fa-chevron-down summary-accordion-chevron";

            rightContent.append(status, chevron);
            headerContent.append(heading, rightContent);

            const oneLiner = document.createElement("div");
            oneLiner.className = "summary-one-liner";
            oneLiner.textContent = item.one_liner || "Quick summary not available.";

            summaryHeader.append(headerContent, oneLiner);

            // -----------------------------------------
            // Expandable content
            // -----------------------------------------

            const body = document.createElement("div");
            body.className = "summary-accordion-body";

            // Detailed summary
            const summaryLabel = document.createElement("div");
            summaryLabel.className = "summary-detail-label";
            summaryLabel.textContent = "Detailed Summary";

            const summaryText = document.createElement("div");
            summaryText.className = "summary-detail-text";
            summaryText.textContent = item.summary || "No information available.";

            body.append(summaryLabel, summaryText);

            // -----------------------------------------
            // Citations
            // -----------------------------------------

            const citationsSection = document.createElement("div");
            citationsSection.className = "mt-4 pt-3 border-top";

            const citationTitle = document.createElement("div");
            citationTitle.className = "summary-detail-label";
            citationTitle.innerHTML = `
        <i class="fa-solid fa-book-open me-1"></i>
        Source Evidence
    `;

            citationsSection.appendChild(citationTitle);

            if (item.citations?.length) {

                item.citations.forEach(citation => {

                    const citationCard = document.createElement("div");
                    citationCard.className = "summary-citation-card";

                    const source = document.createElement("div");
                    source.className = "summary-citation-source";

                    const documentName = citation.document ||
                        citation.source_id ||
                        "Document";

                    const page = citation.page != null
                        ? ` | Page ${citation.page}`
                        : "";

                    source.textContent = `${documentName}${page}`;

                    const quote = document.createElement("div");
                    quote.className = "summary-citation-quote";
                    quote.textContent = citation.quote
                        ? `"${citation.quote}"`
                        : "No quotation available.";

                    citationCard.append(source, quote);
                    citationsSection.appendChild(citationCard);
                });

            } else {

                const empty = document.createElement("div");
                empty.className = "small text-secondary";
                empty.textContent = "No source citations available.";

                citationsSection.appendChild(empty);
            }

            body.appendChild(citationsSection);

            section.append(summaryHeader, body);
            sectionsContainer.appendChild(section);
        });
        $("summaryGeneratedAt").textContent =
            generatedAt ? formatDateTime(generatedAt) : "—";

        setStatus("Completed");
    }


    function renderCitations(citations) {
        const container = $("summaryCitations");
        container.replaceChildren();

        if (!citations.length) {
            const empty = document.createElement("div");
            empty.className = "small text-secondary";
            empty.textContent = "No source citations available.";
            container.appendChild(empty);
            return;
        }

        citations.forEach((citation) => {
            const card = document.createElement("div");
            card.className = "border rounded-3 p-3";

            const heading = document.createElement("div");
            heading.className = "fw-semibold small mb-2";

            heading.textContent =
                `${citation.document || "Document"} | Page ${citation.page ?? "Unknown"} | ${citation.source_id || ""}`;

            const quote = document.createElement("div");
            quote.className = "small text-secondary";
            quote.style.whiteSpace = "pre-wrap";
            quote.textContent = `"${citation.quote || ""}"`;

            card.append(heading, quote);
            container.appendChild(card);
        });
    }

    // --------------------------------------------------
    // Helpers
    // --------------------------------------------------

    function setButtonBusy(busy) {
        button.disabled = busy;

        button.innerHTML = busy
            ? '<span class="spinner-border spinner-border-sm me-1"></span> Generating...'
            : '<i class="fa-solid fa-wand-magic-sparkles me-1"></i><span>Generate Summary</span>';
    }

    function setStatus(status) {
        $("summaryStatus").textContent = status;
    }

    function formatStatus(status) {
        const labels = {
            not_generated: "Not generated",
            queued: "Queued",
            running: "Generating",
            completed: "Completed",
            failed: "Failed",
        };

        return labels[status] || status || "Unknown";
    }

    function showError(message) {
        const element = $("summaryError");
        element.textContent = message;
        element.hidden = false;
    }

    function clearError() {
        $("summaryError").textContent = "";
        $("summaryError").hidden = true;
    }

    async function readJson(response) {
        try {
            return await response.json();
        } catch {
            throw new Error(
                `Server returned an invalid response (${response.status}).`
            );
        }
    }

    function getCsrfToken() {
        const match = document.cookie.match(
            /(?:^|;\s*)csrftoken=([^;]*)/
        );

        return match ? decodeURIComponent(match[1]) : "";
    }

    function formatDateTime(value) {
        if (!value) return "—";

        const date = new Date(value);

        if (isNaN(date)) return value;

        return date.toLocaleString("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function delay(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
});
