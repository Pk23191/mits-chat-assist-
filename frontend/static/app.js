/**
 * CampusAssist AI - Client Application Logic
 * Integrates Google Stitch UI with FastAPI /api/v1/ask and /api/v1/retrieve
 */

let currentQuery = "";
let currentAnswer = "";
let isRequestInProgress = false;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setupKeyboardListeners();

  // Handle URL hash navigation
  window.addEventListener("hashchange", handleHashNavigation);
  if (window.location.hash) {
    handleHashNavigation();
  }
});

function handleHashNavigation() {
  const hash = window.location.hash.replace("#", "");
  if (["chat", "explorer", "syllabus", "admin"].includes(hash)) {
    navigateTo(hash, false);
  }
}

/**
 * Switch view tabs in the single page app
 */
function navigateTo(viewName, updateHash = true) {
  const views = ["chat-home", "conversation", "explorer", "syllabus", "admin"];
  
  // Normalize viewName
  let targetViewId = "view-" + viewName;
  if (viewName === "chat") {
    targetViewId = currentAnswer ? "view-conversation" : "view-chat-home";
  }

  views.forEach((v) => {
    const el = document.getElementById("view-" + v);
    if (el) {
      if (el.id === targetViewId) {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    }
  });

  // Update sidebar active classes
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.remove("bg-surface-container-low", "text-primary", "font-semibold", "border-l-4", "border-primary");
    btn.classList.add("text-on-surface-variant");
  });

  const activeNavId = viewName === "chat-home" || viewName === "conversation" ? "nav-chat" : "nav-" + viewName;
  const activeNav = document.getElementById(activeNavId);
  if (activeNav) {
    activeNav.classList.add("bg-surface-container-low", "text-primary", "font-semibold", "border-l-4", "border-primary");
    activeNav.classList.remove("text-on-surface-variant");
  }

  if (updateHash && viewName !== "chat-home" && viewName !== "conversation") {
    window.location.hash = viewName;
  }
}

/**
 * Setup Enter key listeners for both textareas
 */
function setupKeyboardListeners() {
  const homeInput = document.getElementById("homePromptInput");
  if (homeInput) {
    homeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleHomeSend();
      }
    });
  }

  const activeInput = document.getElementById("activePromptInput");
  if (activeInput) {
    activeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleActiveSend();
      }
    });
  }

  const newChatBtn = document.getElementById("newChatBtn");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", startNewChat);
  }
}

function handleHomeSend() {
  const input = document.getElementById("homePromptInput");
  if (!input) return;
  const text = input.value.trim();
  if (text) {
    submitQuery(text);
    input.value = "";
  }
}

function handleActiveSend() {
  const input = document.getElementById("activePromptInput");
  if (!input) return;
  const text = input.value.trim();
  if (text) {
    submitQuery(text);
    input.value = "";
  }
}

function startNewChat() {
  currentQuery = "";
  currentAnswer = "";
  const homeInput = document.getElementById("homePromptInput");
  if (homeInput) homeInput.value = "";
  const activeInput = document.getElementById("activePromptInput");
  if (activeInput) activeInput.value = "";
  navigateTo("chat-home");
}

/**
 * Submit question to unified /api/v1/ask endpoint
 */
async function submitQuery(queryText) {
  if (isRequestInProgress || !queryText.trim()) return;

  currentQuery = queryText.trim();
  isRequestInProgress = true;

  // Show conversation view
  navigateTo("conversation", false);

  // Update student question bubble
  const userQueryEl = document.getElementById("userQueryText");
  const queryTitleEl = document.getElementById("activeQueryTitle");
  if (userQueryEl) userQueryEl.textContent = currentQuery;
  if (queryTitleEl) queryTitleEl.textContent = currentQuery.length > 50 ? currentQuery.substring(0, 47) + "..." : currentQuery;

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const timestampEl = document.getElementById("queryTimestamp");
  if (timestampEl) timestampEl.textContent = timeStr;

  // Show loading indicator & hide old answer
  const loadingIndicator = document.getElementById("loadingIndicator");
  const aiResponseCard = document.getElementById("aiResponseCard");
  if (loadingIndicator) loadingIndicator.classList.remove("hidden");
  if (aiResponseCard) aiResponseCard.classList.add("hidden");

  try {
    const response = await fetch("/api/v1/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: currentQuery, top_k: 4 }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const errMsg = (errData.detail && errData.detail.message) || (errData.error && errData.error.message) || "Failed to process inquiry.";
      throw new Error(errMsg);
    }

    const data = await response.json();
    currentAnswer = data.answer || "";

    // Render Answer and Sources
    renderAnswerResponse(data);

  } catch (err) {
    console.error("Ask API error:", err);
    renderErrorResponse(err.message || "Failed to retrieve grounded answer.");
  } finally {
    isRequestInProgress = false;
    if (loadingIndicator) loadingIndicator.classList.add("hidden");
    if (aiResponseCard) aiResponseCard.classList.remove("hidden");
  }
}

/**
 * Render the verified answer and source cards
 */
function renderAnswerResponse(data) {
  const answerBody = document.getElementById("aiAnswerBody");
  const statusBadge = document.getElementById("responseStatusBadge");
  const modelBadge = document.getElementById("responseModelBadge");
  const timestamp = document.getElementById("responseTimestamp");
  const citationsHeader = document.getElementById("citationsHeader");
  const citationsGrid = document.getElementById("citationsGrid");
  const confidenceNotice = document.getElementById("confidenceNotice");

  if (answerBody) {
    // Format paragraphs and bold text nicely
    answerBody.innerHTML = formatMarkdown(data.answer);
  }

  const sources = data.sources || [];

  if (statusBadge) {
    if (data.grounded) {
      statusBadge.textContent = "Verified Official Response";
    } else if (sources.length > 0) {
      statusBadge.textContent = "Retrieved Excerpts";
    } else {
      statusBadge.textContent = "No Sources Found";
    }
  }

  if (modelBadge) {
    if (data.status === "success" && data.grounded) {
      modelBadge.textContent = "Gemini Grounded";
      modelBadge.className = "inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#F0FDF4] border border-[#BBF7D0] text-[#166534] text-xs font-semibold";
    } else if (sources.length > 0) {
      modelBadge.textContent = "ChromaDB Grounded";
      modelBadge.className = "inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant/40 text-on-surface text-xs font-medium";
    } else {
      modelBadge.textContent = "No Matches";
      modelBadge.className = "inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant/40 text-on-surface-variant text-xs font-medium";
    }
  }

  if (timestamp) {
    timestamp.textContent = "Generated today at " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Populate Grounded Institutional Citations
  if (citationsGrid) {
    citationsGrid.innerHTML = "";
    
    if (citationsHeader) {
      citationsHeader.textContent = `Grounded Institutional Citations (${sources.length} Sources)`;
    }

    if (sources.length === 0) {
      citationsGrid.innerHTML = `
        <div class="col-span-2 p-4 rounded-xl bg-surface-bright border border-outline-variant/30 text-on-surface-variant text-body-sm italic">
          No specific source documents exceeded the similarity threshold.
        </div>
      `;
      if (confidenceNotice) {
        confidenceNotice.textContent = "No sources exceeded similarity threshold";
      }
    } else {
      let maxConfidence = 0;
      sources.forEach((src) => {
        if (src.confidence > maxConfidence) maxConfidence = src.confidence;
        const card = document.createElement("div");
        card.className = "p-4 rounded-xl bg-surface-bright border border-outline-variant/40 hover:shadow-md transition-shadow flex flex-col justify-between";

        const categoryTag = src.category ? src.category.toUpperCase() : "OFFICIAL";
        const urlLink = src.url ? src.url : "https://web.mitsgwalior.in";

        card.innerHTML = `
          <div>
            <div class="flex items-center justify-between gap-2 mb-2">
              <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#F0FDF4] border border-[#BBF7D0] text-[#166534] text-xs font-semibold">
                <span class="material-symbols-outlined text-[13px]">verified</span>
                ${escapeHtml(categoryTag)}
              </span>
              <span class="text-xs font-semibold text-secondary">${src.confidence}% Match</span>
            </div>
            <h4 class="text-body-md font-bold text-on-surface leading-snug">
              ${escapeHtml(src.title || "Official MITS Document")}
            </h4>
            <div class="mt-2.5 p-2.5 rounded-lg bg-[#DCFCE7]/30 border border-[#BBF7D0]/60 text-xs text-on-surface-variant italic">
              "${escapeHtml(src.excerpt)}"
            </div>
          </div>
          <div class="pt-3 mt-3 flex items-center justify-between border-t border-outline-variant/20">
            <span class="text-[11px] text-on-surface-variant font-medium">ChromaDB Verified</span>
            <a href="${escapeHtml(urlLink)}" target="_blank" class="inline-flex items-center gap-1 text-primary hover:underline text-xs font-semibold">
              <span>View Source</span>
              <span class="material-symbols-outlined text-[14px]">open_in_new</span>
            </a>
          </div>
        `;
        citationsGrid.appendChild(card);
      });

      if (confidenceNotice && maxConfidence > 0) {
        confidenceNotice.textContent = `ChromaDB Top Match: ${maxConfidence}%`;
      }
    }
  }
}

/**
 * Render error state in response card
 */
function renderErrorResponse(errorMessage) {
  const answerBody = document.getElementById("aiAnswerBody");
  const statusBadge = document.getElementById("responseStatusBadge");
  const citationsGrid = document.getElementById("citationsGrid");

  if (answerBody) {
    answerBody.innerHTML = `
      <div class="p-4 rounded-xl bg-error-container/40 border border-error/30 text-on-error-container text-body-md">
        <p class="font-bold flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px] text-error">error</span>
          <span>Inquiry Service Unavailable</span>
        </p>
        <p class="mt-1">${escapeHtml(errorMessage)}</p>
        <button onclick="regenerateLastAnswer()" class="mt-3 px-3 py-1.5 rounded-lg bg-surface-container-lowest border border-outline-variant text-body-sm font-semibold hover:bg-surface-container transition-colors">
          Retry Inquiry
        </button>
      </div>
    `;
  }
  if (statusBadge) statusBadge.textContent = "Error Occurred";
  if (citationsGrid) citationsGrid.innerHTML = "";
}

function regenerateLastAnswer() {
  if (currentQuery) {
    submitQuery(currentQuery);
  }
}

function copyAnswerText() {
  if (!currentAnswer) return;
  navigator.clipboard.writeText(currentAnswer).then(() => {
    const copyBtnText = document.getElementById("copyBtnText");
    if (copyBtnText) copyBtnText.textContent = "Copied!";
    showToast("Answer copied to clipboard!");
    setTimeout(() => {
      if (copyBtnText) copyBtnText.textContent = "Copy Answer";
    }, 2000);
  }).catch(() => {
    showToast("Failed to copy to clipboard.");
  });
}

/**
 * Raw search execution for College Explorer view
 */
async function executeRawSearch() {
  const input = document.getElementById("explorerSearchInput");
  const resultsDiv = document.getElementById("explorerResults");
  if (!input || !resultsDiv) return;
  const query = input.value.trim();
  if (!query) return;

  resultsDiv.innerHTML = `<p class="text-body-sm text-outline animate-pulse">Querying vector store...</p>`;

  try {
    const res = await fetch("/api/v1/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: query, top_k: 4 }),
    });

    if (!res.ok) throw new Error("Search failed.");
    const data = await res.json();

    if (data.no_results || !data.results || data.results.length === 0) {
      resultsDiv.innerHTML = `
        <div class="p-4 rounded-xl bg-surface-bright border border-outline-variant/30 text-on-surface-variant text-body-sm">
          No matching documents found for "${escapeHtml(query)}".
        </div>
      `;
      return;
    }

    resultsDiv.innerHTML = data.results.map((r, i) => `
      <div class="p-4 rounded-xl bg-surface-bright border border-outline-variant/30 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-primary px-2 py-0.5 rounded bg-surface-container">${escapeHtml(r.document_name || r.source_id || "Document")}</span>
          <span class="text-xs text-outline">Distance: ${r.distance !== undefined ? Number(r.distance).toFixed(3) : (r.score || "N/A")}</span>
        </div>
        <p class="text-body-sm text-on-surface">${escapeHtml(r.content || r.text || "")}</p>
      </div>
    `).join("");

  } catch (err) {
    resultsDiv.innerHTML = `<p class="text-body-sm text-error">${escapeHtml(err.message)}</p>`;
  }
}

/**
 * Check health status from server
 */
async function checkHealth() {
  const syncDot = document.getElementById("syncDot");
  const syncText = document.getElementById("syncText");
  const profileStatusDot = document.getElementById("profileStatusDot");
  const statusBadgeText = document.getElementById("statusBadgeText");
  const adminApiStatus = document.getElementById("adminApiStatus");
  const adminRetrievalStatus = document.getElementById("adminRetrievalStatus");

  try {
    const readyRes = await fetch("/health/ready");
    if (readyRes.ok) {
      const data = await readyRes.json();
      if (data.status === "ready") {
        if (syncDot) syncDot.className = "relative inline-flex rounded-full h-2 w-2 bg-secondary";
        if (syncText) syncText.textContent = "MITS Gwalior Portal Sync: Connected";
        if (profileStatusDot) profileStatusDot.className = "w-2.5 h-2.5 rounded-full bg-secondary";
        if (statusBadgeText) statusBadgeText.textContent = "Knowledge Base Ready";
        if (adminApiStatus) adminApiStatus.textContent = "Online";
        if (adminRetrievalStatus) adminRetrievalStatus.textContent = "ChromaDB Ready";
        return;
      }
    }
    throw new Error("Service not ready");
  } catch (e) {
    if (syncDot) syncDot.className = "relative inline-flex rounded-full h-2 w-2 bg-error";
    if (syncText) syncText.textContent = "Portal Sync: Initializing...";
    if (profileStatusDot) profileStatusDot.className = "w-2.5 h-2.5 rounded-full bg-error";
    if (statusBadgeText) statusBadgeText.textContent = "Retrieval Initializing";
    if (adminRetrievalStatus) adminRetrievalStatus.textContent = "Initializing...";
  }
}

/**
 * Simple toast popup helper
 */
function showToast(msg) {
  const toast = document.getElementById("toast");
  const toastMessage = document.getElementById("toastMessage");
  if (toast && toastMessage) {
    toastMessage.textContent = msg;
    toast.classList.remove("translate-y-24", "opacity-0");
    setTimeout(() => {
      toast.classList.add("translate-y-24", "opacity-0");
    }, 2800);
  }
}

/**
 * Simple markdown-to-HTML formatter (supports **bold**, bullets, line breaks)
 */
function formatMarkdown(text) {
  if (!text) return "";
  let formatted = escapeHtml(text);

  // Bold
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // Bullet points
  formatted = formatted.replace(/^\s*[\*\-]\s+(.*)$/gm, '<li class="ml-4 list-disc">$1</li>');

  // Paragraph breaks
  formatted = formatted.replace(/\n\n+/g, "</p><p class='mt-3 leading-relaxed'>");
  formatted = "<p class='leading-relaxed'>" + formatted + "</p>";

  return formatted;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
