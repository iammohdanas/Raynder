(() => {
  "use strict";

  const root = document.getElementById("raynder-ai-widget");
  if (!root || root.dataset.initialized === "true") return;
  root.dataset.initialized = "true";

  const $ = (id) => document.getElementById(id);
  const launcher = $("rai-launcher");
  const panel = $("rai-panel");
  const input = $("rai-input");
  const form = $("rai-composer");
  const send = $("rai-send");
  const welcome = $("rai-welcome");
  const welcomeTitle = $("rai-welcome-title");
  const welcomeDescription = $("rai-welcome-description");
  const messagesEl = $("rai-messages");
  const historyEl = $("rai-history-list");
  const filter = $("rai-history-filter");
  const typing = $("rai-typing");
  const toast = $("rai-toast");
  const scopeButton = $("rai-scope");
  const scopeLabel = $("rai-scope-label");
  const pageContext = $("rai-page-context");
  const pageTenderTitle = $("rai-page-tender-title");
  const pageNotice = $("rai-page-notice");
  const expandButton = $("rai-expand");

  const API_BASE = "/api/ai/chat/conversations/";

  // These values can be populated initially from the widget HTML, then updated
  // when the existing Tender Details API response is detected.
  let pageTenderId = (root.dataset.tenderId || "").trim() || null;
  let pageTenderTitleText = (root.dataset.tenderTitle || "").trim();

  let conversations = [];
  let activeId = null;
  let scope = pageTenderId ? "tender" : "all_tenders";
  let toastTimer = null;
  let sending = false;
  let loading = false;
  let selectedTenderId = pageTenderId;

  const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);

  function notify(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3500);
  }

  function getCsrfToken() {
    const cookie = document.cookie.split("; ").find((row) => row.startsWith("csrftoken="));
    if (cookie) return decodeURIComponent(cookie.split("=").slice(1).join("="));
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  }

  async function apiRequest(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    };

    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrfToken = getCsrfToken();
      if (csrfToken) headers["X-CSRFToken"] = csrfToken;
    }

    const response = await fetch(url, {
      ...options,
      method,
      headers,
      credentials: "same-origin",
    });

    const contentType = response.headers.get("content-type") || "";
    let data = {};

    if (contentType.includes("application/json")) {
      data = await response.json();
    } else if (!response.ok) {
      throw new Error(
        response.status === 403
          ? "Request forbidden. Check your login and CSRF configuration."
          : `Request failed (${response.status}).`
      );
    }

    if (!response.ok) {
      throw new Error(data.error || data.detail || `Request failed (${response.status}).`);
    }

    return data;
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function normalizeMessage(message) {
    return {
      id: message.id || null,
      role: message.role,
      content: message.content || "",
      citations: Array.isArray(message.citations) ? message.citations : [],
      metadata: message.metadata || {},
      time: formatTime(message.created_at),
      created_at: message.created_at || null,
    };
  }

  function normalizeConversation(conversation) {
    return {
      id: conversation.id,
      title: conversation.title || "New chat",
      scope: conversation.scope || "all_tenders",
      tender_id: conversation.tender_id || null,
      messages: (conversation.messages || []).map(normalizeMessage),
      updatedAt: conversation.updated_at
        ? new Date(conversation.updated_at).getTime()
        : Date.now(),
    };
  }

  function active() {
    return conversations.find((conversation) => conversation.id === activeId) || null;
  }

  function updateScopeLabel() {
    const isTenderPage = Boolean(pageTenderId);

    if (scopeLabel) {
      scopeLabel.textContent = scope === "tender" ? "Specific tender" : "All tenders";
    }

    if (scopeButton) {
      scopeButton.setAttribute("aria-label", "Switch chat scope");
      scopeButton.title = isTenderPage
        ? `Current page tender: ${pageTenderTitleText || pageTenderId}`
        : "Tender-specific chat is available on a Tender Details page";
    }

    if (pageContext) {
      pageContext.hidden = !(scope === "tender" && isTenderPage);
    }

    if (pageTenderTitle) {
      pageTenderTitle.textContent = pageTenderTitleText || pageTenderId || "";
    }

    if (pageNotice) {
      pageNotice.hidden = isTenderPage || scope !== "tender";
    }

    if (input) {
      if (scope === "all_tenders") {
        input.placeholder = "All-tenders chat is not implemented yet…";
      } else if (isTenderPage) {
        input.placeholder = "Ask about this tender's documents…";
      } else {
        input.placeholder = "Open a Tender Details page to ask about a tender…";
      }
    }

    if (welcomeTitle) {
      welcomeTitle.textContent = scope === "all_tenders"
        ? "Your tender copilot."
        : "Ask about this tender.";
    }

    if (welcomeDescription) {
      welcomeDescription.textContent = scope === "all_tenders"
        ? "All-tenders answering is not connected yet. Open a tender to ask questions about its indexed documents."
        : isTenderPage
          ? `I can answer questions using the indexed documents for ${pageTenderTitleText || "this tender"}.`
          : "Open a Tender Details page to ask questions about that tender's indexed documents.";
    }

    if (send) {
      send.disabled = sending
        || !input?.value.trim()
        || !(scope === "tender" && isTenderPage && String(selectedTenderId) === String(pageTenderId));
    }
  }

  function openWidget(open) {
    root.classList.toggle("rai-open", open);
    panel?.setAttribute("aria-hidden", String(!open));
    launcher?.setAttribute("aria-expanded", String(open));
    if (open) window.setTimeout(() => input?.focus(), 160);
  }

  async function loadConversations() {
    const data = await apiRequest(API_BASE);
    conversations = (data.conversations || [])
      .map(normalizeConversation)
      .sort((a, b) => b.updatedAt - a.updatedAt);
    renderHistory();
    return conversations;
  }

  async function createConversation(tenderId) {
    if (!tenderId) {
      throw new Error("Open a Tender Details page before starting a tender-specific chat.");
    }

    const payload = {
      title: "New chat",
      scope: "tender",
      tender_id: tenderId,
    };

    const data = await apiRequest(API_BASE, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (!data.conversation) {
      throw new Error("The server did not return the created conversation.");
    }

    const conversation = normalizeConversation(data.conversation);
    conversations = conversations.filter((item) => item.id !== conversation.id);
    conversations.unshift(conversation);
    activeId = conversation.id;
    selectedTenderId = tenderId;
    scope = "tender";
    render();
    return conversation;
  }

  function newChat() {
    if (sending) return;

    activeId = null;
    selectedTenderId = pageTenderId;
    scope = pageTenderId ? "tender" : "all_tenders";
    render();
    root.classList.remove("rai-history-open");
    if (input) input.focus();
  }

  async function loadConversation(id) {
    const data = await apiRequest(`${API_BASE}${encodeURIComponent(id)}/`);
    if (!data.conversation) throw new Error("The server did not return this conversation.");

    const conversation = normalizeConversation(data.conversation);
    conversations = conversations.filter((item) => item.id !== conversation.id);
    conversations.unshift(conversation);
    conversations.sort((a, b) => b.updatedAt - a.updatedAt);
    activeId = conversation.id;
    scope = conversation.scope;

    // The historical conversation may belong to another tender. Keep its saved
    // context for display, but sending is enabled only for the currently open tender.
    selectedTenderId = conversation.tender_id;
    render();
    root.classList.remove("rai-history-open");
  }

  async function deleteConversation(id) {
    try {
      await apiRequest(`${API_BASE}${encodeURIComponent(id)}/`, { method: "DELETE" });
      conversations = conversations.filter((conversation) => conversation.id !== id);

      if (activeId === id) {
        activeId = null;
        selectedTenderId = pageTenderId;
        scope = pageTenderId ? "tender" : "all_tenders";
      }

      render();
      notify("Conversation deleted.");
    } catch (error) {
      notify(error.message || "Could not delete conversation.");
    }
  }

  function renderHistory() {
    if (!historyEl) return;

    const query = (filter?.value || "").trim().toLowerCase();
    const list = conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(query)
    );

    if (!list.length) {
      historyEl.innerHTML = `<div class="rai-history-empty">${
        query ? "No matching conversations." : "Your conversations will appear here."
      }</div>`;
      return;
    }

    historyEl.innerHTML = list.map((conversation) => `
      <div class="rai-history-row">
        <button
          class="rai-history-item ${conversation.id === activeId ? "active" : ""}"
          type="button"
          data-id="${escapeHTML(conversation.id)}"
          title="${escapeHTML(conversation.title)}">
          <span>▤</span><span>${escapeHTML(conversation.title)}</span>
        </button>
        <button
          class="rai-history-delete"
          type="button"
          data-delete-id="${escapeHTML(conversation.id)}"
          aria-label="Delete ${escapeHTML(conversation.title)}"
          title="Delete conversation">×</button>
      </div>
    `).join("");
  }

  function renderMessages() {
    const conversation = active();
    const hasMessages = Boolean(conversation && conversation.messages.length);

    if (welcome) welcome.style.display = hasMessages ? "none" : "block";
    if (!messagesEl) return;

    messagesEl.classList.toggle("rai-visible", hasMessages);

    messagesEl.innerHTML = hasMessages
      ? conversation.messages.map((message) => {
          const citations = message.role === "assistant" && Array.isArray(message.citations)
            ? message.citations
            : [];

          const citationHTML = citations.length ? `
            <div class="rai-citations">
              <div class="rai-citations-heading">Sources</div>
              ${citations.map((citation) => `
                <div class="rai-citation">
                  <div class="rai-citation-title">
                    ${escapeHTML(citation.document || citation.source_id || "Tender document")}
                    ${citation.page != null ? ` · Page ${escapeHTML(citation.page)}` : ""}
                  </div>
                  ${citation.quote ? `<blockquote>${escapeHTML(citation.quote)}</blockquote>` : ""}
                </div>
              `).join("")}
            </div>
          ` : "";

          const evidenceNote = message.role === "assistant"
            && message.metadata?.insufficient_evidence === true
            ? `<div class="rai-evidence-note">The indexed documents did not provide enough evidence to verify this answer.</div>`
            : "";

          return `
            <article class="rai-message ${message.role === "assistant" ? "assistant" : "user"}">
              <div class="rai-message-avatar">${message.role === "user" ? "Y" : "R"}</div>
              <div class="rai-message-body">
                <div class="rai-message-content">${escapeHTML(message.content)}</div>
                ${citationHTML}
                ${evidenceNote}
                <div class="rai-message-meta">
                  ${message.role === "user" ? "You" : "Raynder AI"}${message.time ? ` · ${escapeHTML(message.time)}` : ""}
                </div>
              </div>
            </article>
          `;
        }).join("")
      : "";

    if (hasMessages) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function resize() {
    if (!input || !send) return;

    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 105)}px`;

    const canSend = scope === "tender"
      && Boolean(pageTenderId)
      && String(selectedTenderId) === String(pageTenderId);

    send.disabled = sending || !input.value.trim() || !canSend;
  }

  function render() {
    renderHistory();
    renderMessages();
    updateScopeLabel();
    resize();
  }

  async function sendMessage(raw) {
    const content = String(raw || "").trim();
    if (!content || sending) return;

    if (scope === "all_tenders") {
      notify("All-tenders chat is not implemented yet. Switch to Specific tender to ask document questions.");
      return;
    }

    if (!pageTenderId) {
      notify("Tender-specific AI chat is available only on a Tender Details page. Please open a tender first.");
      return;
    }

    if (String(selectedTenderId) !== String(pageTenderId)) {
      // Do not accidentally send a historical conversation's question to another tender.
      activeId = null;
      selectedTenderId = pageTenderId;
    }

    sending = true;
    resize();
    if (typing) typing.hidden = false;

    try {
      let conversation = active();

      // Never continue a conversation belonging to a different tender.
      if (
        !conversation
        || conversation.scope !== "tender"
        || String(conversation.tender_id) !== String(pageTenderId)
      ) {
        conversation = await createConversation(pageTenderId);
      }

      const conversationId = conversation.id;
      const data = await apiRequest(`${API_BASE}${encodeURIComponent(conversationId)}/messages/`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });

      const current = conversations.find((item) => item.id === conversationId);

      if (current) {
        if (data.message && !current.messages.some((message) => message.id === data.message.id)) {
          current.messages.push(normalizeMessage(data.message));
        }

        if (
          data.reply
          && typeof data.reply === "object"
          && !current.messages.some((message) => message.id === data.reply.id)
        ) {
          current.messages.push(normalizeMessage(data.reply));
        }

        if (current.title === "New chat") {
          current.title = content.length > 42 ? `${content.slice(0, 42).trim()}…` : content;
        }

        current.updatedAt = Date.now();
      }

      if (input) input.value = "";
      render();

      await loadConversations();
      await loadConversation(conversationId);

      if (!data.reply) {
        notify("Your message was saved, but no AI reply was returned.");
      }
    } catch (error) {
      notify(error.message || "Could not send your message.");
    } finally {
      if (typing) typing.hidden = true;
      sending = false;
      resize();
    }
  }

  function handleTenderLoaded(event) {
    const detail = event.detail || {};
    const tenderId = detail.tenderId == null ? "" : String(detail.tenderId).trim();

    if (!tenderId) return;

    const changedTender = String(pageTenderId || "") !== tenderId;
    pageTenderId = tenderId;
    pageTenderTitleText = detail.title || "";

    // A newly detected tender becomes the context for a fresh chat. Do not
    // silently repurpose an existing conversation from another tender.
    if (changedTender) {
      activeId = null;
      selectedTenderId = tenderId;
    } else if (!selectedTenderId) {
      selectedTenderId = tenderId;
    }

    if (!active()) {
      scope = "tender";
      selectedTenderId = tenderId;
    }

    root.dataset.tenderId = tenderId;
    root.dataset.tenderTitle = pageTenderTitleText;

    render();
  }

  // Register the listener before the page's async tender API request completes.
  document.addEventListener("raynder:tender-loaded", handleTenderLoaded);

  // Observe the existing Tender Details API response without editing tender_detail.js.
  // Install this before initialize() and before any async detail request completes.
  const originalFetch = window.fetch.bind(window);

  window.fetch = async function (...args) {
    const response = await originalFetch(...args);

    try {
      const requestInput = args[0];
      const requestUrlValue = typeof requestInput === "string"
        ? requestInput
        : requestInput?.url;

      if (!requestUrlValue) return response;

      const requestUrl = new URL(requestUrlValue, window.location.origin);
      const isTenderDetailEndpoint =
        requestUrl.pathname.startsWith("/api/tenders/")
        && requestUrl.pathname !== "/api/tenders/"
        && requestUrl.pathname.replace(/\/+$/, "").split("/").length >= 3;

      if (isTenderDetailEndpoint && response.ok) {
        const data = await response.clone().json();
        const tender = data?.data;

        // Use the internal tender_id returned by the API, not the URL/database PK.
        if (tender?.tender_id) {
          document.dispatchEvent(new CustomEvent("raynder:tender-loaded", {
            detail: {
              tenderId: String(tender.tender_id),
              title: tender.title || "",
            },
          }));
        }
      }
    } catch (error) {
      // Detection must never break the original API request.
      console.debug("Raynder AI: tender context detection skipped.", error);
    }

    return response;
  };

  launcher?.addEventListener("click", () => openWidget(true));
  $("rai-close")?.addEventListener("click", () => openWidget(false));
  $("rai-minimize")?.addEventListener("click", () => openWidget(false));

  expandButton?.addEventListener("click", () => {
    const expanded = root.classList.toggle("rai-expanded");
    expandButton.title = expanded ? "Restore size" : "Expand chat";
  });

  $("rai-new-chat")?.addEventListener("click", newChat);

  historyEl?.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const deleteButton = target.closest("[data-delete-id]");
    if (deleteButton) {
      event.stopPropagation();
      if (window.confirm("Delete this conversation and its messages?")) {
        await deleteConversation(deleteButton.dataset.deleteId);
      }
      return;
    }

    const button = target.closest("[data-id]");
    if (!button) return;

    try {
      await loadConversation(button.dataset.id);

      if (
        pageTenderId
        && scope === "tender"
        && String(selectedTenderId) !== String(pageTenderId)
      ) {
        notify("This conversation belongs to another tender. Start a new chat for the tender currently open.");
      }
    } catch (error) {
      notify(error.message || "Could not load conversation.");
    }
  });

  filter?.addEventListener("input", renderHistory);

  document.querySelectorAll(".rai-suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      if (!input) return;
      input.value = button.dataset.prompt || "";
      resize();
      input.focus();
    });
  });

  input?.addEventListener("input", resize);

  input?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form?.requestSubmit();
    }
  });

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!sending) sendMessage(input?.value || "");
  });

  scopeButton?.addEventListener("click", () => {
    if (sending) return;

    scope = scope === "tender" ? "all_tenders" : "tender";

    if (scope === "all_tenders") {
      notify("All-tenders chat is not implemented yet. Switch back to Specific tender to ask document questions.");
    } else if (!pageTenderId) {
      notify("Tender-specific AI chat is available only on a Tender Details page. Please open a tender first.");
    }

    if (pageTenderId) selectedTenderId = pageTenderId;

    updateScopeLabel();
    resize();
  });

  document.querySelector(".rai-brand")?.addEventListener("dblclick", () => {
    root.classList.toggle("rai-history-open");
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openWidget(true);
      newChat();
    }

    if (event.key === "Escape" && root.classList.contains("rai-open")) {
      if (root.classList.contains("rai-expanded")) {
        root.classList.remove("rai-expanded");
      } else {
        openWidget(false);
      }
    }
  });

  async function initialize() {
    loading = true;
    resize();

    try {
      await loadConversations();
      activeId = null; // Keep history, but start with a fresh chat on each page visit.
      selectedTenderId = pageTenderId;
      scope = pageTenderId ? "tender" : "all_tenders";
      render();
    } catch (error) {
      notify(error.message || "Could not load chat history.");
      updateScopeLabel();
    } finally {
      loading = false;
      resize();
    }
  }

  initialize();
})();