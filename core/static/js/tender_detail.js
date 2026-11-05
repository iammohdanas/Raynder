

document.addEventListener("DOMContentLoaded", async function () {
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const tenderId = pathParts[pathParts.length - 1];

    if (!tenderId) {
        showError("Invalid tender ID.");
        return;
    }

    try {
        const response = await fetch(`/api/tenders/${tenderId}/`, {
            method: "GET",
            headers: { "Accept": "application/json" },
            credentials: "same-origin"
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Unable to load tender details.");
        }

        populateTender(result.data);
        document.dispatchEvent(
            new CustomEvent("raynder:tender-loaded", {
                detail: {
                    tender_id: result.data.tender_id
                }
            })
        );
        document.getElementById("loadingState").style.display = "none";
        document.getElementById("tenderContent").style.display = "block";

    } catch (error) {
        console.error("Tender detail error:", error);
        showError(error.message || "Unable to load tender details.");
    }
});

const uploadButton = document.getElementById("uploadDocumentsBtn");
const documentInput = document.getElementById("documentInput");

if (uploadButton && documentInput) {
    uploadButton.addEventListener("click", function () {
        documentInput.click();
    });
}

if (canUpload) {
    const uploadButton = document.getElementById("uploadDocumentsBtn");
    const documentInput = document.getElementById("documentInput");

    if (uploadButton && documentInput) {

        // Open file picker
        uploadButton.addEventListener("click", function () {
            documentInput.click();
        });

        // Upload selected documents
        documentInput.addEventListener("change", async function () {

            const files = Array.from(documentInput.files || []);

            if (!files.length) {
                return;
            }

            const pathParts = window.location.pathname
                .split("/")
                .filter(Boolean);

            const tenderId = pathParts[pathParts.length - 1];

            if (!tenderId) {
                alert("Invalid tender ID.");
                return;
            }

            try {

                uploadButton.disabled = true;

                uploadButton.innerHTML = `
                    <span class="spinner-border spinner-border-sm me-1"
                          role="status"
                          aria-hidden="true"></span>
                    Uploading...
                `;

                const formData = new FormData();

                // IMPORTANT:
                // Backend expects request.FILES.getlist("documents")
                files.forEach(function (file) {
                    formData.append("documents", file);
                });

                const response = await fetch(
                    `/api/tenders/${tenderId}/documents/`,
                    {
                        method: "POST",
                        body: formData,
                        credentials: "same-origin",
                        headers: {
                            "X-CSRFToken": getCookie("csrftoken")
                        }
                    }
                );

                const result = await response.json();

                if (!response.ok || !result.success) {
                    throw new Error(
                        result.error || "Unable to upload documents."
                    );
                }

                console.log("Upload successful:", result);

                // Clear file input
                documentInput.value = "";

                // Refresh tender details
                const tenderResponse = await fetch(
                    `/api/tenders/${tenderId}/`,
                    {
                        method: "GET",
                        headers: {
                            "Accept": "application/json"
                        },
                        credentials: "same-origin"
                    }
                );

                const tenderResult = await tenderResponse.json();

                if (!tenderResponse.ok || !tenderResult.success) {
                    throw new Error(
                        tenderResult.error ||
                        "Documents uploaded, but tender could not be refreshed."
                    );
                }

                // Re-render documents
                populateTender(tenderResult.data);

                alert(
                    result.message ||
                    "Documents uploaded successfully."
                );

            } catch (error) {

                console.error("Document upload error:", error);

                alert(
                    error.message ||
                    "Unable to upload documents."
                );

            } finally {

                uploadButton.disabled = false;

                uploadButton.innerHTML = `
                    <i class="fa-solid fa-cloud-arrow-up"
                       style="font-size: 0.95rem;"></i>
                    <span>Upload Attachment</span>
                `;
            }
        });
    }
}
// Helper to get file type details (icon, color, extension)
function getFileTypeDetails(fileName) {
    const ext = (fileName || "").split('.').pop().toLowerCase();
    switch (ext) {
        case 'pdf':
            return { icon: 'fa-file-pdf', color: '#dc2626', bg: '#fef2f2', border: '#fecaca', label: 'PDF' };
        case 'doc':
        case 'docx':
            return { icon: 'fa-file-word', color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', label: 'DOC' };
        case 'xls':
        case 'xlsx':
        case 'csv':
            return { icon: 'fa-file-excel', color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0', label: 'EXCEL' };
        case 'zip':
        case 'rar':
        case '7z':
            return { icon: 'fa-file-zipper', color: '#d97706', bg: '#fffbeb', border: '#fde68a', label: 'ARCHIVE' };
        case 'png':
        case 'jpg':
        case 'jpeg':
            return { icon: 'fa-file-image', color: '#9333ea', bg: '#faf5ff', border: '#e9d5ff', label: 'IMAGE' };
        default:
            return { icon: 'fa-file-lines', color: '#475569', bg: '#f8fafc', border: '#e2e8f0', label: ext.toUpperCase() || 'FILE' };
    }
}


function createDocumentRow(doc, container) {
    const filename = escapeHtml(doc.original_filename || "Document");
    const fileMeta = getFileTypeDetails(filename);

    const row = document.createElement("div");
    row.className = "document-row";
    row.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem 1.25rem;
            background: #ffffff;
            border: 1px solid #edf2f7;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.02);
            transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            gap: 12px;
        `;

    // Micro interaction transitions
    row.onmouseover = function () {
        this.style.borderColor = '#cbd5e1';
        this.style.transform = 'translateY(-2px)';
        this.style.boxShadow = '0 8px 16px -4px rgba(15, 23, 42, 0.06)';
        this.style.backgroundColor = '#fafcff';
    };
    row.onmouseout = function () {
        this.style.borderColor = '#edf2f7';
        this.style.transform = 'translateY(0)';
        this.style.boxShadow = '0 1px 3px rgba(15, 23, 42, 0.02)';
        this.style.backgroundColor = '#ffffff';
    };

    row.innerHTML = `
            <div style="display: flex; align-items: center; gap: 14px; min-width: 0; flex: 1;">
                <div style="width: 44px; height: 44px; border-radius: 10px; background-color: ${fileMeta.bg}; border: 1px solid ${fileMeta.border}; display: flex; align-items: center; justify-content: center; font-size: 1.25rem; color: ${fileMeta.color}; flex-shrink: 0;">
                    <i class="fa-solid ${fileMeta.icon}"></i>
                </div>
                <div style="min-width: 0; flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
                        <span style="font-weight: 600; color: #1e293b; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${filename}">
                            ${filename}
                        </span>
                        <span style="font-size: 0.65rem; font-weight: 700; background: ${fileMeta.bg}; color: ${fileMeta.color}; border: 1px solid ${fileMeta.border}; padding: 1px 6px; border-radius: 4px; font-family: 'JetBrains Mono', monospace;">
                            ${fileMeta.label}
                        </span>
                    </div>
                    <div style="font-size: 0.75rem; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
                        <i class="fa-regular fa-clock" style="font-size: 0.7rem;"></i>
                        <span>${formatDateTime(doc.uploaded_at)}</span>
                    </div>
                </div>
            </div>

            <!-- Action Buttons Toolbar -->
            <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
                <a href="${doc.file}" target="_blank" rel="noopener noreferrer"
                    style="display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 32px; padding: 0 10px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; color: #334155; font-size: 0.75rem; font-weight: 600; text-decoration: none; transition: all 0.15s ease;"
                    onmouseover="this.style.background='#eff6ff'; this.style.color='#2563eb'; this.style.borderColor='#bfdbfe';"
                    onmouseout="this.style.background='#ffffff'; this.style.color='#334155'; this.style.borderColor='#e2e8f0';"
                    title="View preview in new tab">
                    <i class="fa-solid fa-eye" style="font-size: 0.75rem;"></i>
                    <span class="d-none d-sm-inline">Preview</span>
                </a>

                <a href="${doc.file}" download
                    style="display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 32px; padding: 0 10px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; color: #334155; font-size: 0.75rem; font-weight: 600; text-decoration: none; transition: all 0.15s ease;"
                    onmouseover="this.style.background='#f0fdf4'; this.style.color='#16a34a'; this.style.borderColor='#bbf7d0';"
                    onmouseout="this.style.background='#ffffff'; this.style.color='#334155'; this.style.borderColor='#e2e8f0';"
                    title="Download file">
                    <i class="fa-solid fa-download" style="font-size: 0.75rem;"></i>
                    <span class="d-none d-sm-inline">Download</span>
                </a>

                ${canDelete ? `
    <button type="button"
        class="delete-document-btn"
        data-document-id="${doc.id}"
        data-document-name="${filename}"
        style="display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 32px; width: 32px; background: #ffffff; border: 1px solid #fee2e2; border-radius: 8px; color: #ef4444; font-size: 0.75rem; cursor: pointer; transition: all 0.15s ease;"
        onmouseover="this.style.background='#fef2f2'; this.style.borderColor='#fca5a5'; this.style.color='#dc2626';"
        onmouseout="this.style.background='#ffffff'; this.style.borderColor='#fee2e2'; this.style.color='#ef4444';"
        title="Delete document">
        <i class="fa-solid fa-trash"></i>
    </button>
` : ''}
            </div>
        `;

    container.appendChild(row);
}

function populateTender(tender) {
    setText("title", tender.title || "Untitled Tender");
    setText("source", tender.source || "TenderTiger");
    setText("tenderId", tender.tender_id || "—");
    setText("referenceNo", tender.tender_ref_no || "—");
    setText("tcno", tender.tcno || "—");

    setText("companyName", tender.company_name || "—");
    setText("tenderValue", formatCurrency(tender.tender_value));
    setText("earnestMoney", formatCurrency(tender.earnest_money));

    setText("tenderDate", formatDate(tender.tender_date));
    setText("openingDate", formatDate(tender.opening_date));
    setText("closingDate", formatDate(tender.closing_date));
    setText("createdAt", formatDateTime(tender.created_at));
    setText("updatedAt", formatDateTime(tender.updated_at));

    setText("state", tender.state || "—");
    setText("city", tender.city || "—");
    setText("address", tender.address || "—");

    setText("description", tender.description || "No description available.");
    setText("databaseId", tender.id || "—");
    setText("sourceTenderId", tender.source_tender_id || "—");

    const documentBadge = document.getElementById("documentBadge");
    if (tender.document_available) {
        documentBadge.style.display = "inline-flex";
    } else {
        documentBadge.style.display = "none";
    }

    setupLink("descriptionUrl", tender.description_url);
    setupLink("originalSource", tender.original_source);

    renderDocuments(tender.documents || []);
}

function renderDocuments(documents) {

    const documentsList = document.getElementById("documentsList");

    if (!documentsList) return;

    documentsList.innerHTML = "";

    if (!documents || documents.length === 0) {

        if (canUpload) {

            // Admin / Manager empty state
            documentsList.innerHTML = `
                <div id="noDocumentsMessage"
                    style="border: 2px dashed #e2e8f0;
                           border-radius: 14px;
                           padding: 2.75rem 1.5rem;
                           text-align: center;
                           background-color: #f8fafc;
                           transition: all 0.2s ease;">

                    <div
                        style="width: 52px;
                               height: 52px;
                               border-radius: 50%;
                               background: #ffffff;
                               box-shadow: 0 4px 12px rgba(0,0,0,0.04);
                               display: inline-flex;
                               align-items: center;
                               justify-content: center;
                               margin-bottom: 0.875rem;
                               color: #94a3b8;
                               font-size: 1.35rem;
                               border: 1px solid #f1f5f9;">

                        <i class="fa-regular fa-folder-open"></i>

                    </div>

                    <div
                        style="font-size: 0.9375rem;
                               font-weight: 600;
                               color: #334155;
                               margin-bottom: 4px;">

                        No documents attached yet

                    </div>

                    <div
                        style="font-size: 0.8125rem;
                               color: #94a3b8;
                               max-width: 320px;
                               margin: 0 auto 1.25rem;
                               line-height: 1.5;">

                        Upload notice invites, technical specs, or addendums
                        related to this tender.

                    </div>

                    <button type="button"
                        onclick="document.getElementById('documentInput').click();"
                        style="background: #ffffff;
                               color: #2563eb;
                               border: 1px solid #bfdbfe;
                               font-size: 0.8125rem;
                               font-weight: 600;
                               padding: 6px 14px;
                               border-radius: 8px;
                               cursor: pointer;
                               transition: all 0.2s ease;"

                        onmouseover="this.style.background='#eff6ff'; this.style.borderColor='#93c5fd';"

                        onmouseout="this.style.background='#ffffff'; this.style.borderColor='#bfdbfe';">

                        Select files to upload

                    </button>

                </div>
            `;

        } else {

            // View-only empty state
            documentsList.innerHTML = `
                <div id="noDocumentsMessage"
                    style="border: 1px solid #e2e8f0;
                           border-radius: 14px;
                           padding: 2.75rem 1.5rem;
                           text-align: center;
                           background-color: #f8fafc;">

                    <div
                        style="width: 52px;
                               height: 52px;
                               border-radius: 50%;
                               background: #ffffff;
                               box-shadow: 0 4px 12px rgba(0,0,0,0.04);
                               display: inline-flex;
                               align-items: center;
                               justify-content: center;
                               margin-bottom: 0.875rem;
                               color: #94a3b8;
                               font-size: 1.35rem;
                               border: 1px solid #f1f5f9;">

                        <i class="fa-regular fa-folder-open"></i>

                    </div>

                    <div
                        style="font-size: 0.9375rem;
                               font-weight: 600;
                               color: #334155;
                               margin-bottom: 4px;">

                        No documents available

                    </div>

                    <div
                        style="font-size: 0.8125rem;
                               color: #94a3b8;
                               max-width: 320px;
                               margin: 0 auto;
                               line-height: 1.5;">

                        There are currently no documents attached to this tender.

                    </div>

                </div>
            `;

        }

        return;
    }


    // Documents exist
    documents.forEach(function (doc) {
        createDocumentRow(doc, documentsList);
    });
}
document.addEventListener("click", async function (event) {
    const deleteButton = event.target.closest(".delete-document-btn");
    if (!deleteButton) return;

    const documentId = deleteButton.dataset.documentId;
    const documentName = deleteButton.dataset.documentName || "this document";

    const confirmed = confirm(`Are you sure you want to delete "${documentName}"?`);
    if (!confirmed) return;

    try {
        deleteButton.disabled = true;
        deleteButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width: 12px; height: 12px;"></span>`;

        const response = await fetch(`/api/tender-documents/${documentId}/`, {
            method: "DELETE",
            headers: {
                "Accept": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            credentials: "same-origin"
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Unable to delete document.");
        }

        const row = deleteButton.closest(".document-row");
        if (row) {
            row.style.opacity = '0';
            row.style.transform = 'scale(0.95)';
            setTimeout(() => {
                row.remove();
                const documentsList = document.getElementById("documentsList");
                if (documentsList && documentsList.querySelectorAll(".document-row").length === 0) {
                    renderDocuments([]);
                }
            }, 150);
        }

        if (!result.document_available) {
            const documentBadge = document.getElementById("documentBadge");
            if (documentBadge) {
                documentBadge.style.display = "none";
            }
        }

    } catch (error) {
        console.error("Document deletion error:", error);
        alert(error.message || "Unable to delete document.");
        deleteButton.disabled = false;
        deleteButton.innerHTML = `<i class="fa-solid fa-trash"></i>`;
    }
});

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}

function setText(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = value;
    }
}

function setupLink(elementId, url) {
    const element = document.getElementById(elementId);
    if (!element) return;

    if (url) {
        element.href = url;
        element.style.display = "inline-flex";
    } else {
        element.style.display = "none";
    }
}

function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (isNaN(date)) return value;
    return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    });
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
        minute: "2-digit"
    });
}

function formatCurrency(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (isNaN(number)) return value;
    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0
    }).format(number);
}

function showError(message) {
    document.getElementById("loadingState").style.display = "none";
    document.getElementById("tenderContent").style.display = "none";
    document.getElementById("errorState").style.display = "block";
    document.getElementById("errorMessage").textContent = message;
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}




document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("runRagEvaluationBtn");
    const panel = document.getElementById("ragEvaluationPanel");

    if (!button || !panel) return;

    const $ = (id) => document.getElementById(id);

    let tenderId = null;
    let activeRunId = null;
    let polling = false;


    function setTenderId(event) {
        tenderId = event.detail?.tender_id || null;
    }

    document.addEventListener("raynder:tender-loaded", setTenderId);

    // Recover the tender ID from the URL if the event already fired.
    if (!tenderId) {
        const pathParts = window.location.pathname
            .split("/")
            .filter(Boolean);

        tenderId = pathParts[pathParts.length - 1] || null;
    }

    button.addEventListener("click", startEvaluation);

    async function startEvaluation() {
        if (!tenderId) {
            showError("Tender information is still loading. Please try again.");
            panel.hidden = false;
            return;
        }

        if (polling) return;

        panel.hidden = false;
        clearError();
        resetResults();

        setStatus("Submitting evaluation...");
        setButtonBusy(true);

        try {
            const response = await fetch("/api/ai/evaluations/run/", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ tender_id: tenderId }),
            });

            const data = await readJson(response);

            if (!response.ok) {
                throw new Error(data.error || "Could not start evaluation.");
            }

            activeRunId = data.run_id;
            polling = true;

            $("ragEvaluationProgressSection").hidden = false;
            setStatus("Queued");

            await pollStatus(activeRunId);
        } catch (error) {
            showError(error.message || "Evaluation could not be started.");
            setStatus("Error");
        } finally {
            polling = false;
            setButtonBusy(false);
        }
    }

    async function pollStatus(runId) {
        while (activeRunId === runId) {
            let response;
            let data;

            try {
                response = await fetch(
                    `/api/ai/evaluations/${encodeURIComponent(runId)}/`,
                    { credentials: "same-origin" }
                );
                data = await readJson(response);

                if (!response.ok) {
                    throw new Error(data.error || "Could not fetch evaluation status.");
                }
            } catch (error) {
                showError(error.message || "Unable to retrieve evaluation status.");
                setStatus("Connection error");
                return;
            }

            updateProgress(data);
            setStatus(formatStatus(data.status));

            if (data.status === "completed") {
                try {
                    await loadResults(runId);
                } catch (error) {
                    showError(error.message || "Could not load evaluation results.");
                }
                return;
            }

            if (data.status === "failed") {
                showError(data.error || "The evaluation task failed.");
                return;
            }

            await delay(2000);
        }
    }

    function updateProgress(data) {
        const total = Number(data.total_cases || 0);
        const completed = Number(data.completed_cases || 0);
        const passed = Number(data.passed_cases || 0);
        const failed = Number(data.failed_cases || 0);

        const percentage = total > 0
            ? Math.min(100, Math.round((completed / total) * 100))
            : 0;

        $("ragEvaluationProgressText").textContent =
            `${completed} / ${total} questions`;

        $("ragEvaluationProgressBar").style.width = `${percentage}%`;
        $("ragEvaluationProgressBar").setAttribute(
            "aria-valuenow",
            String(percentage)
        );

        $("ragPassedCount").textContent = passed;
        $("ragFailedCount").textContent = failed;

        $("ragPassRate").textContent =
            completed > 0 ? `${data.pass_rate ?? 0}%` : "—";
    }

    async function loadResults(runId) {
        const response = await fetch(
            `/api/ai/evaluations/${encodeURIComponent(runId)}/results/`,
            { credentials: "same-origin" }
        );

        const data = await readJson(response);

        if (!response.ok) {
            throw new Error(data.error || "Could not load results.");
        }

        const container = $("ragEvaluationResults");
        container.replaceChildren();

        for (const result of data.results || []) {
            container.appendChild(renderResult(result));
        }

        $("ragEvaluationResultsSection").hidden = false;
    }

    function renderResult(result) {
        const card = document.createElement("div");
        card.className = "border rounded-3 p-3";

        const heading = document.createElement("div");
        heading.className =
            "d-flex justify-content-between align-items-start gap-2 flex-wrap mb-3";

        const question = document.createElement("div");
        question.className = "fw-semibold";
        question.textContent = result.question || "Untitled question";

        const badge = document.createElement("span");
        badge.className = result.overall_pass
            ? "status-pill badge-doc-available"
            : "status-pill";
        badge.textContent = result.overall_pass ? "PASS" : "FAIL";

        if (!result.overall_pass) {
            badge.style.background = "#fef2f2";
            badge.style.color = "#b91c1c";
            badge.style.border = "1px solid #fecaca";
        }

        heading.append(question, badge);
        card.appendChild(heading);

        appendField(card, "Expected answer", result.expected_answer);
        appendField(card, "Actual answer", result.actual_answer);

        const checks = document.createElement("div");
        checks.className = "d-flex flex-wrap gap-2 mt-3";

        checks.append(
            makeCheckBadge("Answer", result.answer_pass),
            makeCheckBadge("Citations", result.citation_pass),
            makeCheckBadge(
                "Evidence detection",
                result.insufficient_evidence_pass
            )
        );

        card.appendChild(checks);

        if (result.missing_terms?.length) {
            appendField(
                card,
                "Missing terms",
                result.missing_terms.join(", ")
            );
        }

        if (result.citations?.length) {
            const citations = result.citations.map((citation) => {
                const quote = citation.quote ? ` — "${citation.quote}"` : "";
                return `${citation.document || "Document"}, page ${citation.page ?? "unknown"
                    }${quote}`;
            });

            appendField(card, "Citations", citations.join("\n"));
        }

        if (result.error) {
            appendField(card, "Error", result.error);
        }

        return card;
    }

    function appendField(container, label, value) {
        if (value === undefined || value === null || value === "") return;

        const wrapper = document.createElement("div");
        wrapper.className = "mt-2";

        const title = document.createElement("div");
        title.className = "small fw-semibold text-secondary mb-1";
        title.textContent = label;

        const text = document.createElement("div");
        text.className = "small";
        text.style.whiteSpace = "pre-wrap";
        text.textContent = String(value);

        wrapper.append(title, text);
        container.appendChild(wrapper);
    }

    function makeCheckBadge(label, passed) {
        const badge = document.createElement("span");
        badge.className = passed
            ? "status-pill badge-doc-available"
            : "status-pill";

        if (!passed) {
            badge.style.background = "#fef2f2";
            badge.style.color = "#b91c1c";
            badge.style.border = "1px solid #fecaca";
        }

        badge.textContent = `${label}: ${passed ? "Passed" : "Failed"}`;
        return badge;
    }

    async function readJson(response) {
        try {
            return await response.json();
        } catch {
            throw new Error(`Server returned an invalid response (${response.status}).`);
        }
    }

    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function setButtonBusy(busy) {
        button.disabled = busy;
        button.innerHTML = busy
            ? '<span class="spinner-border spinner-border-sm me-1"></span> Evaluating...'
            : '<i class="fa-solid fa-flask me-1"></i><span>Evaluate RAG</span>';
    }

    function setStatus(status) {
        $("ragEvaluationStatus").textContent = status;
    }

    function showError(message) {
        const element = $("ragEvaluationError");
        element.textContent = message;
        element.hidden = false;
    }

    function clearError() {
        $("ragEvaluationError").textContent = "";
        $("ragEvaluationError").hidden = true;
    }

    function resetResults() {
        $("ragEvaluationProgressSection").hidden = true;
        $("ragEvaluationResultsSection").hidden = true;
        $("ragEvaluationResults").replaceChildren();

        $("ragEvaluationProgressText").textContent = "0 / 0 questions";
        $("ragEvaluationProgressBar").style.width = "0%";
        $("ragEvaluationProgressBar").setAttribute("aria-valuenow", "0");

        $("ragPassedCount").textContent = "0";
        $("ragFailedCount").textContent = "0";
        $("ragPassRate").textContent = "—";
    }

    function formatStatus(status) {
        const labels = {
            queued: "Queued",
            running: "Running",
            completed: "Completed",
            failed: "Failed",
        };

        return labels[status] || status || "Unknown";
    }

    function delay(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
});



document.addEventListener("DOMContentLoaded", function () {
    const pipelineButton = document.getElementById("runDocumentPipelineBtn");
    const pipelineStatus = document.getElementById("documentPipelineStatus");

    if (!pipelineButton || !pipelineStatus) return;

    const statusText = document.getElementById("pipelineStatusText");
    const progressBar = document.getElementById("pipelineProgressBar");

    let polling = false;

    pipelineButton.addEventListener("click", async function () {
        const tenderId = document.getElementById("tenderId")?.textContent.trim();

        if (!tenderId || tenderId === "—") {
            showPipelineStatus("Tender ID not found.", "danger");
            return;
        }

        if (polling) return;

        pipelineButton.disabled = true;
        pipelineButton.innerHTML =
            '<i class="fa-solid fa-spinner fa-spin"></i> Queuing Pipeline...';

        showPipelineStatus("Submitting document pipeline task...", "info");

        try {
            const response = await fetch(
                `/api/ai/tenders/${encodeURIComponent(tenderId)}/run-pipeline/`,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                        "X-CSRFToken": getCookie("csrftoken")
                    }
                }
            );

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    result.error || "Unable to start document pipeline."
                );
            }

            polling = true;

            pipelineButton.innerHTML =
                '<i class="fa-solid fa-spinner fa-spin"></i> Pipeline Running';

            showPipelineStatus(
                `Pipeline queued. Task ID: ${result.task_id}`,
                "info"
            );

            await pollDocumentPipeline(result.task_id);

        } catch (error) {
            console.error("Document pipeline error:", error);

            showPipelineStatus(
                error.message || "Unable to start document pipeline.",
                "danger"
            );

            pipelineButton.disabled = false;
            pipelineButton.innerHTML =
                '<i class="fa-solid fa-gears"></i> Run Document Pipeline';

        } finally {
            polling = false;
        }
    });

    async function pollDocumentPipeline(taskId) {
        const statusUrl =
            `/api/ai/tasks/${encodeURIComponent(taskId)}/status/`;

        pipelineStatus.style.display = "block";

        if (progressBar) {
            progressBar.style.width = "100%";
            progressBar.className =
                "progress-bar progress-bar-striped progress-bar-animated bg-info";
        }

        while (true) {
            const response = await fetch(statusUrl, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error || "Unable to retrieve pipeline status."
                );
            }

            if (data.status === "SUCCESS") {
                if (statusText) {
                    statusText.textContent =
                        "Document pipeline completed successfully!";
                }

                if (progressBar) {
                    progressBar.className = "progress-bar bg-success";
                    progressBar.style.width = "100%";
                }

                pipelineButton.disabled = false;
                pipelineButton.innerHTML =
                    '<i class="fa-solid fa-check"></i> Pipeline Completed';

                return;
            }

            if (data.status === "FAILURE") {
                throw new Error(
                    data.error || "Document pipeline failed."
                );
            }

            if (statusText) {
                statusText.textContent =
                    data.status === "STARTED"
                        ? "Processing documents and indexing vectors..."
                        : "Pipeline queued. Waiting for worker...";
            }

            await new Promise(resolve => setTimeout(resolve, 2000));
        }
    }

    function showPipelineStatus(message, type) {
        pipelineStatus.style.display = "block";

        if (statusText) {
            statusText.textContent = message;
        } else {
            pipelineStatus.textContent = message;
        }

        pipelineStatus.className = `small mt-2 text-${type}`;
    }
});


async function pollDocumentPipeline(taskId) {
    const statusContainer = document.getElementById("documentPipelineStatus");
    const statusText = document.getElementById("pipelineStatusText");
    const progressBar = document.getElementById("pipelineProgressBar");
    const pipelineButton = document.getElementById("runDocumentPipelineBtn");

    const statusUrl = `/api/ai/tasks/${encodeURIComponent(taskId)}/status/`;

    statusContainer.style.display = "block";

    statusText.textContent = "Pipeline queued. Waiting for worker...";
    progressBar.className =
        "progress-bar progress-bar-striped progress-bar-animated bg-info";

    const checkStatus = async () => {
        try {
            const response = await fetch(statusUrl, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Unable to fetch task status.");
            }

            if (data.status === "SUCCESS") {
                statusText.textContent =
                    "Document pipeline completed successfully! Documents processed and indexing finished.";

                progressBar.className = "progress-bar bg-success";
                progressBar.style.width = "100%";

                pipelineButton.disabled = false;
                pipelineButton.innerHTML =
                    '<i class="fa-solid fa-check"></i> Pipeline Completed';

                // Optional browser notification
                if ("Notification" in window &&
                    Notification.permission === "granted") {
                    new Notification("Raynder", {
                        body: "Document pipeline completed successfully."
                    });
                }

                return;
            }

            if (data.status === "FAILURE") {
                statusText.textContent =
                    `Pipeline failed: ${data.error || "Unknown error"}`;

                progressBar.className = "progress-bar bg-danger";
                progressBar.style.width = "100%";

                pipelineButton.disabled = false;
                pipelineButton.innerHTML =
                    '<i class="fa-solid fa-rotate"></i> Retry Pipeline';

                return;
            }

            if (data.status === "STARTED") {
                statusText.textContent =
                    "Pipeline processing: extracting documents, generating chunks and indexing vectors...";
            } else {
                statusText.textContent =
                    "Pipeline queued. Waiting for worker...";
            }

            setTimeout(checkStatus, 2000);

        } catch (error) {
            console.error("Pipeline status error:", error);
            statusText.textContent =
                "Unable to retrieve pipeline status. Please refresh and check again.";
            pipelineButton.disabled = false;
        }
    };

    checkStatus();
}