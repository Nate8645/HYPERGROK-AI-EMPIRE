// Static Devnet-only signature test page. Classic script (no ES modules).
// Official Safari path: https://phantom.com/ul/v1/connect then /signMessage, cluster=devnet,
// HTTPS redirect back to this page. No browse deeplink. No transaction methods.
// Injected provider (window.phantom.solana / window.solana) is used when present.
(function () {
  "use strict";
  const HG = window.HGPhantomDeeplink;
  const nacl = window.nacl;
  if (!HG || !nacl) {
    const el = document.getElementById("err");
    if (el) el.textContent = "Seite unvollständig geladen (lokale Skripte fehlen). Bitte in Safari neu laden.";
    return;
  }
  const { createDeeplink, b58encode, b58decode, formatPhantomError } = HG;
  const $ = (id) => document.getElementById(id);
  const err = (e) => { $("err").textContent = String(e?.message ?? e); };
  const setStatus = (t) => { const s = $("status"); if (!t) { s.hidden = true; s.textContent = ""; return; } s.hidden = false; s.textContent = t; };

  const CLUSTER = "devnet";
  const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";
  const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
  const DEVNET_TEST_HEADER = "HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION";
  const LIVE_HEADER = "HyperGrok LIVE approval v1";
  const STORE = "hg-devnet-approval";
  let session = { publicKey: null, approval: null, method: null };
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
  function render() {
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
      err(new Error("Kopieren fehlgeschlagen. Bitte den Text im Ergebnisfeld manuell markieren und kopieren."));
    }
  };
  $("btnNewMessage").onclick = () => {
    fillTestMessage();
    $("err").textContent = "";
    setStatus("");
  };

  function loadStore() {
    try { return JSON.parse(sessionStorage.getItem(STORE) ?? "null"); } catch { return null; }
  }
  function saveStore(obj) {
    sessionStorage.setItem(STORE, JSON.stringify(obj));
  }
  function clearQuery() {
    history.replaceState(null, "", pageBaseUrl());
  }

  async function injectedSign() {
    assertDevnet(CLUSTER);
    const p = getProvider();
    if (!p) throw new Error("Phantom provider not found.");
    assertProviderDevnet(p);
    setStatus("Phantom-Provider erkannt. Verbindung und Signatur werden angefordert…");
    const { publicKey } = await p.connect();
    assertProviderDevnet(p);
    session.publicKey = typeof publicKey === "string" ? publicKey : publicKey.toBase58();
    const msg = message();
    const sm = await p.signMessage(new TextEncoder().encode(msg), "utf8");
    const sigBytes = sm.signature ?? sm;
    const signature = b58encode(sigBytes);
    verifyLocal(msg, signature, session.publicKey);
    session.method = "injected";
    session.approval = { message: msg, signature, signerPublicKey: session.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
    setStatus("Signatur erhalten und lokal geprüft (ed25519, Test only). Bitte das Ergebnis kopieren und zurückgeben.");
    render();
  }

  function startDeeplinkConnect() {
    assertDevnet(CLUSTER);
    const msg = message();
    const k = dl.newSessionEncryptionKeys();
    saveStore({ secret: [...k.secret], pub: k.publicKeyB58, pendingMessage: msg, autoSign: true });
    setStatus("Phantom wird geöffnet. Bitte verbinden und danach die Nachricht signieren. Du kehrst anschliessend zu Safari zurück.");
    const url = dl.connectUrl({
      dappEncryptionPublicKeyB58: k.publicKeyB58,
      appUrl: pageBaseUrl(),
      redirectLink: `${pageBaseUrl()}?step=connected`,
      cluster: "devnet",
    });
    location.href = url;
  }

  function continueDeeplinkSign(S) {
    assertDevnet(CLUSTER);
    const msg = assertTestOnlyMessage(S.pendingMessage || $("message").value);
    const shared = dl.sharedSecret(S.phantomPub, Uint8Array.from(S.secret));
    saveStore({ ...S, pendingMessage: msg });
    setStatus("Verbindung steht. Phantom wird für die Signatur geöffnet…");
    location.href = dl.signMessageUrl({
      dappEncryptionPublicKeyB58: S.pub,
      shared,
      session: S.session,
      message: msg,
      redirectLink: `${pageBaseUrl()}?step=approved`,
    });
  }

  function handleRedirect() {
    const q = new URLSearchParams(location.search);
    if (q.get("errorCode") || q.get("errorMessage")) {
      $("err").textContent = formatPhantomError(q.get("errorCode") || "", q.get("errorMessage") || "");
      setStatus("Die Anfrage in Phantom wurde nicht abgeschlossen.");
      clearQuery();
      return "error";
    }
    const S = loadStore();
    const secret = S ? Uint8Array.from(S.secret || []) : null;
    if (q.get("step") === "connected") {
      if (!S?.secret) throw new Error("Sitzung verloren. Bitte den Knopf in Safari erneut tippen.");
      const c = dl.parseConnectResponse(q, secret);
      if (S.pendingMessage) $("message").value = S.pendingMessage;
      saveStore({ ...S, session: c.session, phantomPub: c.phantomEncryptionPublicKey, publicKey: c.publicKey });
      session.publicKey = c.publicKey;
      clearQuery();
      continueDeeplinkSign({ ...S, session: c.session, phantomPub: c.phantomEncryptionPublicKey, publicKey: c.publicKey });
      return "signing";
    }
    if (q.get("step") === "approved") {
      if (!S?.phantomPub) throw new Error("Sitzung verloren. Bitte den Knopf in Safari erneut tippen.");
      const shared = dl.sharedSecret(S.phantomPub, secret);
      const { signature } = dl.parseSignMessageResponse(q, shared);
      const msg = assertTestOnlyMessage(S.pendingMessage ?? $("message").value);
      $("message").value = msg;
      verifyLocal(msg, signature, S.publicKey);
      session.publicKey = S.publicKey;
      session.method = "deeplink";
      session.approval = { message: msg, signature, signerPublicKey: S.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
      saveStore({ ...S, approval: session.approval });
      clearQuery();
      setStatus("Signatur erhalten und lokal geprüft (ed25519, Test only). Bitte das Ergebnis kopieren und zurückgeben.");
      render();
      return "done";
    }
    if (S?.approval) {
      session.approval = S.approval;
      session.publicKey = S.publicKey;
      session.method = "deeplink";
      if (S.pendingMessage) $("message").value = S.pendingMessage;
      setStatus("Eine zuvor erstellte Test-Signatur ist noch in dieser Sitzung gespeichert.");
      render();
    }
    return "idle";
  }

  $("btnStart").onclick = () => {
    try {
      $("err").textContent = "";
      assertDevnet(CLUSTER);
      if (getProvider()) injectedSign().catch(err);
      else startDeeplinkConnect();
    } catch (e) { err(e); }
  };

  try {
    assertDevnet(CLUSTER);
    fillTestMessage();
    handleRedirect();
  } catch (e) { err(e); }
})();
