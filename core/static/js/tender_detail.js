
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

            uploadButton.addEventListener("click", function () {
                documentInput.click();
            });

            documentInput.addEventListener("change", async function () {

                // Your existing upload code here

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
