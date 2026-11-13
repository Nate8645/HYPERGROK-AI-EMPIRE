// Static Devnet-only signature test page. Classic script (no ES modules).
// Official Safari path: https://phantom.com/ul/v1/connect then /signMessage, cluster=devnet.
// Session x25519 keys live in localStorage (10 min TTL) so a Phantom HTTPS redirect
// into a NEW Safari tab can still decrypt. That is NOT a wallet key.
(function () {
  "use strict";
  function boot() {
    const HG = window.HGPhantomDeeplink;
    const nacl = window.nacl;
    if (!HG || !nacl) {
      const el = document.getElementById("err");
      if (el) el.textContent = "Seite unvollständig geladen (lokale Skripte fehlen). Bitte in Safari neu laden.";
      return;
    }
    const { createDeeplink, b58encode, b58decode, formatPhantomError, validateConnectUrl, PHANTOM_UL, PHANTOM_APP_UL } = HG;
    const $ = (id) => document.getElementById(id);
    const CLUSTER = "devnet";
    const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";
    const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
    const DEVNET_TEST_HEADER = "HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION";
    const LIVE_HEADER = "HyperGrok LIVE approval v1";
    const STORE_LOCAL = "hg-devnet-test-state";
    const STORE_SESSION = "hg-devnet-approval";
    const STATE_TTL_MS = 10 * 60 * 1000;
    const STEP_TTL_MS = 5 * 60 * 1000;
    const STEP_ORDER = ["connect_started", "connected", "sign_requested", "signed", "verified"];
    let session = { publicKey: null, approval: null, method: null };
    let lastDebug = { callbackParamNames: [], publicKeyShort: null, fromSessionStorage: false, fromLocalStorage: false, newTabLikely: false };
    const dl = createDeeplink({ nacl });

    function looksMainnet(value) {
      const s = String(value ?? "").toLowerCase();
      if (!s) return false;
      return s.includes("mainnet") || s.includes("solana-mainnet");
    }
    function assertDevnet(cluster) {
      const c = String(cluster ?? "").toLowerCase();
      if (looksMainnet(c) || c === "mainnet-beta" || c === "mainnet" || c === "solana-mainnet") {
        throw new Error("MAINNET_REFUSED: this page only signs on Solana Devnet");
      }
      if (c !== "devnet") throw new Error("MAINNET_REFUSED: only Solana Devnet is allowed (got " + c + ")");
    }
    function assertNotMainnetHint(value, label) {
      if (looksMainnet(value)) throw new Error("MAINNET_REFUSED: " + label + " indicates mainnet");
    }
    function assertGenesis(hash) {
      if (hash == null || hash === "") return;
      const h = String(hash);
      if (h === MAINNET_GENESIS) throw new Error("MAINNET_REFUSED: Phantom reported the Solana mainnet genesis hash");
      if (h !== DEVNET_GENESIS) throw new Error("MAINNET_REFUSED: unexpected genesis hash (not devnet)");
    }
    function assertProviderDevnet(provider) {
      assertDevnet(CLUSTER);
      if (!provider) throw new Error("Phantom provider missing");
      const hints = [
        provider.cluster, provider.network, provider._network, provider.chain,
        provider.connection?.rpcEndpoint, provider.connection?._rpcEndpoint,
      ];
      for (const h of hints) assertNotMainnetHint(h, "Phantom network");
      assertGenesis(provider.genesisHash || provider._genesisHash || provider.connection?.genesisHash);
    }
    function getProvider() {
      const p = window.phantom?.solana || window.solana;
      if (p && p.isPhantom) return p;
      return null;
    }
    function pageBaseUrl() {
      return location.origin + location.pathname;
    }
    function randomNonceHex() {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    }
    function buildDevnetTestMessage({ nonce, issuedAt } = {}) {
      const n = nonce ?? randomNonceHex();
      const t = issuedAt ?? new Date().toISOString();
      return [
        DEVNET_TEST_HEADER,
        "network: solana-devnet",
        "purpose: signature-path test — not a live trading authorization",
        "nonce: " + n,
        "issuedAt: " + t,
      ].join("\n");
    }
    function assertTestOnlyMessage(text) {
      const m = String(text ?? "");
      if (m.includes(LIVE_HEADER) || m.startsWith("HyperGrok LIVE ")) {
        throw new Error("LIVE_FORMAT_REFUSED: this page will not sign a live approval message");
      }
      if (!m.startsWith(DEVNET_TEST_HEADER + "\n") && m !== DEVNET_TEST_HEADER) {
        throw new Error("TEST_MESSAGE_REQUIRED: message must start with the DEVNET TEST ONLY header");
      }
      if (!m.includes("DEVNET TEST ONLY")) {
        throw new Error("TEST_MESSAGE_REQUIRED: message must contain DEVNET TEST ONLY");
      }
      return m;
    }
    function parseMessageFields(text) {
      const o = {};
      for (const line of String(text).split("\n")) {
        const i = line.indexOf(": ");
        if (i > 0) o[line.slice(0, i)] = line.slice(i + 2);
      }
      return o;
    }
    function shortKey(pk) {
      const s = String(pk || "");
      if (s.length < 12) return s;
      return s.slice(0, 4) + "…" + s.slice(-4);
    }
    function nowMs() { return Date.now(); }
    function isExpired(state, ttl) {
      if (!state || !state.updatedAt) return false;
      return nowMs() - Date.parse(state.updatedAt) > ttl;
    }
    function readRaw(storage, key) {
      try { const v = storage.getItem(key); return v ? JSON.parse(v) : null; } catch { return null; }
    }
    function writeRaw(storage, key, obj) {
      storage.setItem(key, JSON.stringify(obj));
    }
    function clearSecretsFrom(state) {
      if (!state) return state;
      const copy = { ...state };
      delete copy.secret;
      delete copy.session;
      return copy;
    }
    function loadState() {
      const local = readRaw(localStorage, STORE_LOCAL);
      const sess = readRaw(sessionStorage, STORE_SESSION);
      lastDebug.fromLocalStorage = !!(local && (local.secret || local.step));
      lastDebug.fromSessionStorage = !!(sess && (sess.secret || sess.step));
      lastDebug.newTabLikely = lastDebug.fromLocalStorage && !lastDebug.fromSessionStorage;
      let state = local || sess;
      if (local && sess && sess.updatedAt && local.updatedAt && Date.parse(sess.updatedAt) > Date.parse(local.updatedAt)) state = { ...local, ...sess };
      if (state && state.expiresAt && Date.parse(state.expiresAt) <= nowMs()) {
        fail("Zeitüberschreitung: der gespeicherte Testzustand ist älter als 10 Minuten. Tippe «Neu starten».", "expired_ttl");
        clearAllStores(false);
        return null;
      }
      return state;
    }
    function saveState(partial) {
      const prev = readRaw(localStorage, STORE_LOCAL) || {};
      const next = { ...prev, ...partial, v: 1, updatedAt: new Date().toISOString() };
      if (!next.createdAt) next.createdAt = next.updatedAt;
      if (!next.expiresAt) next.expiresAt = new Date(nowMs() + STATE_TTL_MS).toISOString();
      writeRaw(localStorage, STORE_LOCAL, next);
      // sessionStorage copy when we are in the starting tab; new tabs still read localStorage
      try { writeRaw(sessionStorage, STORE_SESSION, next); } catch {}
      return next;
    }
    function clearAllStores(keepDebug) {
      const dbg = keepDebug ? lastDebug : null;
      try { localStorage.removeItem(STORE_LOCAL); } catch {}
      try { sessionStorage.removeItem(STORE_SESSION); } catch {}
      if (dbg) lastDebug = dbg;
    }
    function collectCallbackParams() {
      const search = new URLSearchParams(location.search);
      const hash = new URLSearchParams((location.hash || "").replace(/^#/, "").replace(/^\?/, ""));
      const names = [];
      const merged = new URLSearchParams();
      for (const src of [search, hash]) {
        for (const [k, v] of src.entries()) {
          if (!names.includes(k)) names.push(k);
          if (!merged.has(k)) merged.set(k, v);
        }
      }
      lastDebug.callbackParamNames = names;
      lastDebug.receivedAt = names.length ? new Date().toISOString() : lastDebug.receivedAt;
      return merged;
    }
    function setStatus(text) {
      $("status").textContent = text || "";
    }
    function setError(text) {
      $("err").textContent = text || "";
    }
    function markSteps(current, isError) {
      const reached = STEP_ORDER.indexOf(current);
      for (const li of $("steps").querySelectorAll("li")) {
        const s = li.getAttribute("data-step");
        li.classList.remove("done", "current", "failed");
        const idx = STEP_ORDER.indexOf(s);
        if (isError && s === current) li.classList.add("failed");
        else if (idx >= 0 && reached >= 0 && idx < reached) li.classList.add("done");
        else if (s === current && !isError) li.classList.add("current");
        if (s === "verified" && current === "verified") li.classList.add("done");
      }
    }
    function fail(message, code) {
      setError(message);
      setStatus("Fehler: " + (code || "unbekannt"));
      $("status").classList.add("err-status");
      const st = readRaw(localStorage, STORE_LOCAL) || {};
      if (st.step === "connect_started" || st.connectUrl) markSteps("connect_started");
      renderDebug({ step: "error", errorCode: code, connectUrl: st.connectUrl, variant: st.variant });
      try { $("debugWrap").open = true; } catch {}
    }
    function renderDebug(extra) {
      const st = readRaw(localStorage, STORE_LOCAL) || {};
      const url = extra?.connectUrl || st.connectUrl || lastDebug.connectUrl || "";
      const check = url ? validateConnectUrl(url) : null;
      const lines = [
        "Connect-Variante: " + (extra?.variant || st.variant || lastDebug.variant || "—"),
        "Connect-URL (alles öffentlich, keine Wallet-Geheimnisse):",
        url || "—",
        "Prüfung der Connect-URL: " + (check ? (check.ok ? "OK" : "FEHLER: " + check.errors.join("; ")) : "—"),
      ];
      if (check && check.details) {
        const d = check.details;
        lines.push(
          "  host/path: " + (d.hostPath || "—"),
          "  app_url: " + (d.params.app_url || "—"),
          "  redirect_link (einmal dekodiert): " + (d.params.redirect_link || "—"),
          "  dapp_encryption_public_key: " + (d.params.dapp_encryption_public_key || "—"),
          "  dapp_encryption_public_key Bytes: " + (d.pubkeyBytes == null ? "—" : String(d.pubkeyBytes)),
          "  cluster: " + (d.params.cluster || "—"),
          "  redirect_link einfach kodiert: " + (d.encoding && d.encoding.singleEncoded ? "ja" : "nein/unbekannt")
        );
      }
      lines.push(
        "Callback-Parameter (Namen; Werte nur bei öffentlichen Connect-Feldern oben): " + (lastDebug.callbackParamNames.join(", ") || "—"),
        "Öffentliche Adresse (gekürzt): " + (lastDebug.publicKeyShort || shortKey(st.publicKey) || "—"),
        "localStorage-Zustand gefunden: " + (lastDebug.fromLocalStorage ? "ja" : "nein"),
        "sessionStorage-Zustand gefunden: " + (lastDebug.fromSessionStorage ? "ja" : "nein"),
        "Vermutlich neuer Safari-Tab: " + (lastDebug.newTabLikely ? "ja" : "nein"),
        "Schritt: " + (extra?.step || st.step || "—"),
        "Aktualisiert: " + (st.updatedAt || "—"),
        "Läuft ab: " + (st.expiresAt || "—")
      );
      if (extra?.errorCode) lines.push("Fehlercode intern: " + extra.errorCode);
      $("debug").textContent = lines.join("\n");
    }
    function fillTestMessage() {
      $("message").value = buildDevnetTestMessage();
    }
    function message() {
      return assertTestOnlyMessage($("message").value);
    }
    function verifyLocal(messageText, signatureB58, publicKeyB58) {
      if (!nacl.sign?.detached?.verify) throw new Error("Lokale Signaturprüfung nicht verfügbar (nacl.sign fehlt).");
      const ok = nacl.sign.detached.verify(
        new TextEncoder().encode(messageText),
        b58decode(signatureB58),
        b58decode(publicKeyB58)
      );
      if (!ok) throw new Error("SIGNATUR_UNGUELTIG: die Signatur passt nicht zur öffentlichen Adresse und Nachricht.");
      return true;
    }
    function renderResult() {
      const fields = parseMessageFields(session.approval?.message ?? "");
      const out = {
        network: "solana-devnet",
        label: "DEVNET TEST ONLY — not a live trading approval, not broadcast, not a live order",
        method: session.method,
        signerPublicKey: session.publicKey,
        message: session.approval?.message ?? null,
        signature: session.approval?.signature ?? null,
        nonce: fields.nonce ?? null,
        issuedAt: fields.issuedAt ?? null,
        localEd25519Ok: session.approval ? true : null,
      };
      $("out").value = JSON.stringify(out, null, 2);
      $("btnDownload").disabled = !session.approval;
      $("btnCopy").disabled = !session.approval;
    }
    function showSignButton(state) {
      const a = $("btnSign");
      const msg = assertTestOnlyMessage(state.pendingMessage || $("message").value);
      const shared = dl.sharedSecret(state.phantomPub, Uint8Array.from(state.secret));
      const url = dl.signMessageUrl({
        dappEncryptionPublicKeyB58: state.pub,
        shared,
        session: state.session,
        message: msg,
        redirectLink: `${pageBaseUrl()}#step=approved`,
      });
      a.href = url;
      a.hidden = false;
      a.textContent = "Signatur in Phantom anfordern";
      return url;
    }
    function hideSignButton() {
      const a = $("btnSign");
      a.hidden = true;
      a.removeAttribute("href");
    }
    function enterConnected(state) {
      session.publicKey = state.publicKey;
      lastDebug.publicKeyShort = shortKey(state.publicKey);
      $("pkShort").textContent = state.publicKey ? "(" + shortKey(state.publicKey) + ")" : "";
      if (state.pendingMessage) $("message").value = state.pendingMessage;
      markSteps("connected");
      setStatus("Verbindung bestätigt. Auf dem iPhone braucht der Signatur-Schritt typischerweise einen Tipp, weil Safari nach der Rückkehr aus Phantom keine User Activation mehr hat.");
      setError("");
      const url = showSignButton(state);
      renderDebug({ step: "connected" });
      // Auto-navigation only if this document still has transient user activation.
      // After a Phantom→Safari redirect it almost never does; the visible button is the supported path.
      try {
        if (navigator.userActivation && navigator.userActivation.isActive) {
          location.href = url;
        }
      } catch {}
    }
    function clearQuery() {
      history.replaceState(null, "", pageBaseUrl());
    }

    $("btnDownload").onclick = () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([$("out").value], { type: "application/json" }));
      a.download = "signed-devnet-test-only.json";
      a.click();
    };
    $("btnCopy").onclick = async () => {
      const text = $("out").value;
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
        else {
          $("out").removeAttribute("readonly");
          $("out").select();
          document.execCommand("copy");
          $("out").setAttribute("readonly", "readonly");
        }
        setStatus("Ergebnis wurde kopiert. Nur öffentliche Adresse und Signatur zurückgeben — niemals Seed oder privaten Schlüssel.");
      } catch (e) {
        setError("Kopieren fehlgeschlagen. Bitte den Text im Ergebnisfeld manuell markieren und kopieren.");
      }
    };
    $("btnNewMessage").onclick = () => {
      fillTestMessage();
      setError("");
    };
    $("btnRestart").onclick = () => {
      clearAllStores(false);
      session = { publicKey: null, approval: null, method: null };
      lastDebug = { callbackParamNames: [], publicKeyShort: null, fromSessionStorage: false, fromLocalStorage: false, newTabLikely: false, connectUrl: "", variant: "" };
      hideSignButton();
      $("pkShort").textContent = "";
      $("out").value = "";
      $("btnCopy").disabled = true;
      $("btnDownload").disabled = true;
      markSteps("");
      setError("");
      setStatus("Zurückgesetzt. Du kannst die Verbindung neu starten.");
      fillTestMessage();
      renderDebug({ step: "idle" });
    };
    $("btnSign").addEventListener("click", () => {
      try {
        const st = loadState();
        if (!st?.secret || !st.session || !st.phantomPub) {
          throw new Error("Sitzungsschlüssel fehlt – die Seite wurde wahrscheinlich in einem neuen Tab geöffnet und der Zustand ist abgelaufen. Tippe «Neu starten».");
        }
        if (isExpired(st, STEP_TTL_MS)) {
          throw new Error("Zeitüberschreitung: der Verbindungs-Schritt ist älter als 5 Minuten. Tippe «Neu starten».");
        }
        showSignButton(st);
        saveState({ step: "sign_requested" });
        markSteps("sign_requested");
        setStatus("Signatur angefordert. Bitte in Phantom bestätigen. Du kehrst danach zu Safari zurück.");
        renderDebug({ step: "sign_requested" });
        // href on the <a> is the primary navigation (user gesture / universal link).
      } catch (e) { setError(String(e.message || e)); }
    });

    async function injectedSign() {
      assertDevnet(CLUSTER);
      const p = getProvider();
      if (!p) throw new Error("Phantom provider not found.");
      assertProviderDevnet(p);
      markSteps("connect_started");
      setStatus("Wallet-Verbindung gestartet (Phantom-Provider in dieser Seite).");
      const { publicKey } = await p.connect();
      assertProviderDevnet(p);
      session.publicKey = typeof publicKey === "string" ? publicKey : publicKey.toBase58();
      lastDebug.publicKeyShort = shortKey(session.publicKey);
      $("pkShort").textContent = "(" + shortKey(session.publicKey) + ")";
      markSteps("connected");
      const msg = message();
      markSteps("sign_requested");
      const sm = await p.signMessage(new TextEncoder().encode(msg), "utf8");
      const sigBytes = sm.signature ?? sm;
      const signature = b58encode(sigBytes);
      markSteps("signed");
      verifyLocal(msg, signature, session.publicKey);
      session.method = "injected";
      session.approval = { message: msg, signature, signerPublicKey: session.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
      markSteps("verified");
      setStatus("Signatur erhalten und lokal geprüft (ed25519, Test only). Bitte das Ergebnis kopieren und zurückgeben.");
      renderResult();
      renderDebug({ step: "verified" });
    }

    function variantSpec(name) {
      const page = pageBaseUrl();
      const origin = location.origin;
      const base = name === "host_phantom_app" ? PHANTOM_APP_UL : PHANTOM_UL;
      const appUrl = name === "app_url_origin" ? origin : page;
      let redirectLink;
      if (name === "clean_redirect") redirectLink = page;
      else redirectLink = page + "#step=connected";
      return { name, base, appUrl, redirectLink, cluster: "devnet" };
    }

    function startDeeplinkConnect(variantName) {
      assertDevnet(CLUSTER);
      const spec = variantSpec(variantName || "standard");
      if (spec.cluster !== "devnet") throw new Error("MAINNET_REFUSED");
      const msg = message();
      const k = dl.newSessionEncryptionKeys();
      const url = dl.connectUrl({
        dappEncryptionPublicKeyB58: k.publicKeyB58,
        appUrl: spec.appUrl,
        redirectLink: spec.redirectLink,
        cluster: "devnet",
        base: spec.base,
      });
      const check = validateConnectUrl(url);
      if (!check.ok) throw new Error("CONNECT_URL_INVALID: " + check.errors.join("; "));
      lastDebug.connectUrl = url;
      lastDebug.variant = spec.name;
      saveState({
        secret: [...k.secret],
        pub: k.publicKeyB58,
        pendingMessage: msg,
        step: "connect_started",
        session: null,
        phantomPub: null,
        publicKey: null,
        variant: spec.name,
        connectUrl: url,
      });
      markSteps("connect_started");
      setStatus("Wallet-Verbindung gestartet (" + spec.name + "). Phantom wird geöffnet. Nach der Bestätigung kehrst du zu Safari zurück.");
      renderDebug({ step: "connect_started", connectUrl: url, variant: spec.name });
      location.href = url;
    }

    function handleCallback() {
      const q = collectCallbackParams();
      renderDebug({ step: "callback" });
      const state = loadState();
      const step = q.get("step") || "";
      if (step.startsWith("tx-") || state?.pendingTx) return "ignored"; // Devnet transaction test owns this callback
      if (q.get("errorCode") || q.get("errorMessage")) {
        const text = formatPhantomError(q.get("errorCode") || "", q.get("errorMessage") || "");
        fail(text, "phantom_" + (q.get("errorCode") || "unknown"));
        clearSecretsOnError();
        clearQuery();
        return "error";
      }
      const isConnectCb = step === "connected" || (step !== "approved" && !step && q.get("phantom_encryption_public_key") && q.get("nonce") && q.get("data"));
      const isSignCb = step === "approved";
      if (isConnectCb) {
        if (!state?.secret) {
          fail("Sitzungsschlüssel fehlt – die Seite wurde in einem neuen Tab geöffnet und der lokale Testzustand ist nicht vorhanden oder abgelaufen. Tippe «Neu starten» und verbinde erneut.", "missing_session_key");
          clearQuery();
          return "error";
        }
        if (isExpired(state, STEP_TTL_MS) && state.step === "connect_started") {
          fail("Zeitüberschreitung: die Verbindung ist älter als 5 Minuten. Tippe «Neu starten».", "expired_step");
          clearAllStores(true);
          clearQuery();
          return "error";
        }
        let c;
        try {
          c = dl.parseConnectResponse(q, Uint8Array.from(state.secret));
        } catch (e) {
          fail("Entschlüsselung fehlgeschlagen: " + (e.message || e), "decrypt_failed");
          clearQuery();
          return "error";
        }
        const next = saveState({
          ...state,
          session: c.session,
          phantomPub: c.phantomEncryptionPublicKey,
          publicKey: c.publicKey,
          step: "connected",
        });
        if (next.pendingMessage) $("message").value = next.pendingMessage;
        clearQuery();
        enterConnected(next);
        return "connected";
      }
      if (isSignCb) {
        if (!state?.secret || !state.phantomPub) {
          fail("Sitzungsschlüssel fehlt – die Signatur-Antwort konnte nicht entschlüsselt werden. Tippe «Neu starten».", "missing_session_key");
          clearQuery();
          return "error";
        }
        let signature;
        try {
          const shared = dl.sharedSecret(state.phantomPub, Uint8Array.from(state.secret));
          signature = dl.parseSignMessageResponse(q, shared).signature;
        } catch (e) {
          fail("Entschlüsselung fehlgeschlagen: " + (e.message || e), "decrypt_failed");
          clearQuery();
          return "error";
        }
        const msg = assertTestOnlyMessage(state.pendingMessage ?? $("message").value);
        $("message").value = msg;
        markSteps("signed");
        verifyLocal(msg, signature, state.publicKey);
        session.publicKey = state.publicKey;
        session.method = "deeplink";
        session.approval = { message: msg, signature, signerPublicKey: state.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
        lastDebug.publicKeyShort = shortKey(state.publicKey);
        $("pkShort").textContent = "(" + shortKey(state.publicKey) + ")";
        markSteps("verified");
        setStatus("Signatur erhalten und lokal geprüft (ed25519, Test only). Bitte das Ergebnis kopieren und zurückgeben.");
        setError("");
        hideSignButton();
        renderResult();
        clearAllStores(true);
        saveState({ step: "verified", publicKey: state.publicKey, pendingMessage: msg, expiresAt: new Date(nowMs() + 60 * 1000).toISOString() });
        // do not persist x25519 secret or phantom session after success
        const cleaned = readRaw(localStorage, STORE_LOCAL) || {};
        delete cleaned.secret;
        delete cleaned.session;
        delete cleaned.phantomPub;
        writeRaw(localStorage, STORE_LOCAL, cleaned);
        clearQuery();
        renderDebug({ step: "verified" });
        return "done";
      }
      // No callback: restore visible state if a pending connect/sign lives in localStorage (e.g. original tab).
      if (state && state.pendingTx) return "ignored";
      if (state && state.step === "connected" && state.secret && state.session) {
        if (isExpired(state, STEP_TTL_MS)) {
          fail("Zeitüberschreitung: der Verbindungs-Schritt ist älter als 5 Minuten. Tippe «Neu starten».", "expired_step");
          return "error";
        }
        enterConnected(state);
        return "restored";
      }
      if (state && state.step === "connect_started") {
        if (isExpired(state, STEP_TTL_MS)) {
          fail("Zeitüberschreitung: die Verbindung wurde vor mehr als 5 Minuten gestartet und es kam kein Callback. Tippe «Neu starten».", "expired_step");
          return "error";
        }
        markSteps("connect_started");
        setStatus("Wallet-Verbindung gestartet. Warte auf die Rückkehr aus Phantom. Falls du schon verbunden hast und diese Seite sich nicht aktualisiert, prüfe, ob Safari einen neuen Tab geöffnet hat.");
        renderDebug({ step: "connect_started" });
        return "waiting";
      }
      if (state && state.step === "verified" && !session.approval) {
        markSteps("verified");
        if (state.pendingMessage) $("message").value = state.pendingMessage;
        setStatus("In diesem Browser ist bereits eine geprüfte Test-Signatur vermerkt. Für eine neue Signatur: «Neu starten».");
        renderDebug({ step: "verified" });
      }
      return "idle";
    }
    function clearSecretsOnError() {
      const st = readRaw(localStorage, STORE_LOCAL);
      if (!st) return;
      delete st.secret;
      delete st.session;
      writeRaw(localStorage, STORE_LOCAL, st);
    }

    function startFromButton(variantName, allowInjected) {
      try {
        setError("");
        $("status").classList.remove("err-status");
        assertDevnet(CLUSTER);
        if (allowInjected && getProvider()) injectedSign().catch((e) => setError(String(e.message || e)));
        else startDeeplinkConnect(variantName);
      } catch (e) { setError(String(e.message || e)); }
    }
    $("btnStart").onclick = () => startFromButton("standard", true);
    $("btnVarAppHost").onclick = () => startFromButton("host_phantom_app", false);
    $("btnVarOrigin").onclick = () => startFromButton("app_url_origin", false);
    $("btnVarCleanRedirect").onclick = () => startFromButton("clean_redirect", false);

    window.addEventListener("storage", (ev) => {
      if (ev.key !== STORE_LOCAL) return;
      try {
        lastDebug.fromLocalStorage = true;
        handleCallback();
      } catch (e) { setError(String(e.message || e)); }
    });

    try {
      assertDevnet(CLUSTER);
      if (!$("message").value) fillTestMessage();
      handleCallback();
    } catch (e) {
      setError(String(e.message || e));
      renderDebug({ step: "error" });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
