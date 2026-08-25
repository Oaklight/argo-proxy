/**
 * Argo-proxy admin panel customizations.
 *
 * Injected into the llm-rosetta gateway admin panel via custom_head.
 * Uses MutationObserver to modify the DOM after the SPA renders.
 *
 * Features:
 * - ARGO environment switcher in Server Settings
 * - Managed provider badges and read-only enforcement
 * - Info popup replacing "Add Provider" button
 * - Read-only provider modal for managed providers
 * - "Refresh Models" button in Models tab
 */
(function () {
  "use strict";

  var MANAGED = {
    "argo-openai": "argo--openai_chat",
    "argo-anthropic": "argo--anthropic",
  };
  var GATEWAY_DOCS =
    "https://llm-rosetta.readthedocs.io/en/latest/gateway/";

  // Track whether we've already injected widgets
  var _envInjected = false;
  var _infoInjected = false;
  var _refreshInjected = false;

  // --- ARGO environment switcher in Server Settings ---

  function _getAdminHeaders() {
    var h = { "Content-Type": "application/json" };
    var token = sessionStorage.getItem("adminToken");
    if (token) h["Authorization"] = "Bearer " + token;
    return h;
  }

  function patchEnvSwitcher() {
    if (_envInjected) return;
    var serverCard = document.querySelector(
      '#tab-providers .section .provider-card'
    );
    if (!serverCard) return;
    if (document.getElementById("argoEnvSwitcher")) return;

    var group = document.createElement("div");
    group.className = "form-group";
    group.id = "argoEnvSwitcher";
    group.innerHTML =
      '<label>ARGO Environment</label>' +
      '<div class="argo-env-group">' +
      '<div class="env-btn-group">' +
      '<button class="argo-env-btn" data-env="prod">prod</button>' +
      '<button class="argo-env-btn" data-env="dev">dev</button>' +
      '<button class="argo-env-btn" data-env="test">test</button>' +
      '<button class="argo-env-btn" data-env="custom">custom</button>' +
      '</div>' +
      '<span class="argo-env-url" id="argoEnvUrl"></span>' +
      '</div>' +
      '<div class="argo-env-custom" id="argoEnvCustom" style="display:none;margin-top:8px">' +
      '<div style="display:flex;gap:8px">' +
      '<input id="argoEnvCustomUrl" ' +
      'style="flex:1;padding:6px 10px;background:var(--bg);border:1px solid var(--border);' +
      'border-radius:6px;color:var(--text);font-size:12px">' +
      '<button class="btn btn-primary btn-sm" id="argoEnvCustomSave">Apply</button>' +
      '</div>' +
      '</div>';

    serverCard.insertBefore(group, serverCard.firstChild);
    _envInjected = true;

    _loadEnvState();

    group.querySelectorAll(".argo-env-btn").forEach(function (btn) {
      btn.onclick = function () {
        if (btn.dataset.env === "custom") {
          _showCustomInput(true);
        } else {
          _showCustomInput(false);
          _switchEnv(btn.dataset.env);
        }
      };
    });

    document.getElementById("argoEnvCustomSave").onclick = function () {
      var url = document.getElementById("argoEnvCustomUrl").value.trim();
      if (!url) return;
      _switchEnv("custom", url);
    };
  }

  function _loadEnvState() {
    fetch("/admin/api/argo/env", { headers: _getAdminHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) { _updateEnvUI(d.current, d.url); })
      .catch(function () { /* silent */ });
  }

  function _showCustomInput(show) {
    var el = document.getElementById("argoEnvCustom");
    if (el) el.style.display = show ? "block" : "none";
  }

  function _updateEnvUI(envName, envUrl) {
    document.querySelectorAll(".argo-env-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.env === envName);
      b.disabled = false;
    });
    var urlEl = document.getElementById("argoEnvUrl");
    if (urlEl) urlEl.textContent = envUrl || "";
    var isCustom = envName === "custom";
    _showCustomInput(isCustom);
    if (isCustom) {
      var input = document.getElementById("argoEnvCustomUrl");
      if (input) input.value = envUrl || "";
    }
  }

  function _switchEnv(envName, customUrl) {
    var btns = document.querySelectorAll(".argo-env-btn");
    btns.forEach(function (b) { b.disabled = true; });

    var payload = { env: envName };
    if (customUrl) payload.url = customUrl;

    fetch("/admin/api/argo/env", {
      method: "PUT",
      headers: _getAdminHeaders(),
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) {
          _updateEnvUI(d.env, d.url);
          if (typeof showToast === "function") {
            showToast(
              "Switched to " + d.env + (d.changed ? "" : " (already active)"),
              "success"
            );
          }
          if (d.changed && typeof loadConfig === "function") loadConfig();
        } else {
          btns.forEach(function (b) { b.disabled = false; });
          if (typeof showToast === "function")
            showToast(d.error || "Switch failed", "error");
        }
      })
      .catch(function () {
        btns.forEach(function (b) { b.disabled = false; });
        if (typeof showToast === "function")
          showToast("Environment switch failed", "error");
      });
  }

  // --- Provider cards: managed badges + read-only actions ---

  function patchProviderCards() {
    var cards = document.querySelectorAll(".provider-card");
    if (!cards.length) return;

    cards.forEach(function (card) {
      var nm = card.querySelector(".name");
      if (!nm) return;
      var pName = nm.textContent.replace(/\(managed\)/, "").trim();
      if (!MANAGED[pName]) return;

      // Add "(managed)" badge once
      if (!nm.querySelector(".managed-badge")) {
        var badge = document.createElement("span");
        badge.className = "managed-badge";
        badge.textContent = "(managed)";
        nm.appendChild(badge);
      }

      // Hide toggle
      var toggle = card.querySelector(".toggle");
      if (toggle) toggle.style.display = "none";

      // Actions: hide clone/delete, change Edit→View
      var btns = card.querySelectorAll(".actions .btn");
      btns.forEach(function (btn) {
        var text = btn.textContent.trim();
        if (text === "Clone" || text === "Delete" ||
            text === "克隆" || text === "删除") {
          btn.style.display = "none";
        }
        if (text === "Edit" || text === "编辑") {
          btn.textContent = "View";
        }
      });
    });
  }

  // --- Replace "Add Provider" with info icon ---

  function patchAddProviderButton() {
    if (_infoInjected) return;
    var addBtn = document.querySelector(
      'button[onclick*="openProviderModal()"]'
    );
    if (!addBtn) return;

    var info = document.createElement("span");
    info.id = "argoProviderInfo";
    info.className = "hint-icon argo-info-icon";
    info.innerHTML =
      "?" +
      '<span class="hint-popup">' +
      "Providers in argo-proxy are managed automatically from the ARGO " +
      "upstream and cannot be modified here.<br><br>" +
      "For custom provider configuration, use " +
      '<a href="' +
      GATEWAY_DOCS +
      '" target="_blank">llm-rosetta-gateway</a> directly.' +
      "</span>";
    addBtn.replaceWith(info);
    _infoInjected = true;
  }

  // --- Provider modal: read-only for managed providers ---

  function patchProviderModal() {
    var modal = document.getElementById("providerModal");
    if (!modal) return;
    // Only patch when visible (gateway uses .open class)
    if (!modal.classList.contains("open")) return;

    var nameInput = document.getElementById("provName");
    if (!nameInput) return;
    var provName = nameInput.value.trim();
    if (!MANAGED[provName]) return;

    // Already patched this open
    if (modal.dataset.argoPatched === provName) return;
    modal.dataset.argoPatched = provName;

    // Change title
    var title = document.getElementById("providerModalTitle");
    if (title) title.textContent = "View Provider";

    // Fix Provider Type dropdown — set to the shim name
    var typeSel = document.getElementById("provType");
    var shimName = MANAGED[provName];
    if (typeSel && shimName) {
      typeSel.value = shimName;
    }

    // Make all inputs/selects read-only
    modal.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.type === "checkbox") {
        el.disabled = true;
      } else {
        el.readOnly = true;
        el.disabled = true;
      }
    });

    // Hide Save button (keep Cancel)
    modal.querySelectorAll(".btn-primary").forEach(function (btn) {
      btn.style.display = "none";
    });
  }

  // Reset patched state when modal closes
  function resetModalPatch() {
    var modal = document.getElementById("providerModal");
    if (!modal) return;
    if (!modal.classList.contains("open")) {
      delete modal.dataset.argoPatched;
    }
  }

  // --- "Refresh Models" button in Models tab ---

  function patchRefreshModels() {
    if (_refreshInjected) return;
    var fetchBtn = document.querySelector(
      'button[onclick*="openFetchModelsModal"]'
    );
    if (!fetchBtn || document.getElementById("argoRefreshBtn")) return;

    var rb = document.createElement("button");
    rb.id = "argoRefreshBtn";
    rb.className = "btn btn-sm";
    rb.style.cssText = "margin-right:8px";

    var refreshSvg =
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" style="vertical-align:-2px">' +
      '<path d="M21.5 2v6h-6"/><path d="M2.5 22v-6h6"/>' +
      '<path d="M2 11.5a10 10 0 0 1 18.8-4.3"/>' +
      '<path d="M22 12.5a10 10 0 0 1-18.8 4.3"/></svg>';

    rb.innerHTML = refreshSvg + " Refresh Models";
    rb.onclick = function () {
      rb.disabled = true;
      rb.textContent = "Refreshing...";
      fetch("/refresh", { method: "POST" })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          rb.disabled = false;
          rb.innerHTML = refreshSvg + " Refresh Models";
          if (typeof showToast === "function")
            showToast(
              d.after.total_aliases +
                " models (" +
                d.after.unique_models +
                " unique)",
              "success"
            );
          if (typeof loadConfig === "function") loadConfig();
        })
        .catch(function () {
          rb.disabled = false;
          rb.innerHTML = refreshSvg + " Refresh Models";
          if (typeof showToast === "function")
            showToast("Refresh failed", "error");
        });
    };
    fetchBtn.parentNode.insertBefore(rb, fetchBtn);
    _refreshInjected = true;
  }

  // --- Page title (run immediately, before DOMContentLoaded) ---

  document.title = document.title.replace("llm-rosetta Gateway", "Argo Proxy");

  // --- Main observer ---

  document.addEventListener("DOMContentLoaded", function () {
    new MutationObserver(function () {
      patchEnvSwitcher();
      patchProviderCards();
      patchAddProviderButton();
      patchProviderModal();
      resetModalPatch();
      patchRefreshModels();
    }).observe(document.body, { childList: true, subtree: true });
  });
})();
