// Devnet transaction test (classic script). Official RPCs only: https://api.devnet.solana.com
// Official Phantom path: connect (cluster=devnet) then signTransaction. No signAndSendTransaction.
// Broadcast happens only after an explicit checkbox + button. Not a live trade.
(function () {
  "use strict";
  function boot() {
    const HG = window.HGPhantomDeeplink;
    const TX = window.HGSolanaTx;
    const nacl = window.nacl;
    if (!HG || !TX || !nacl) return;
    const { createDeeplink, b58encode, b58decode, formatPhantomError, validateConnectUrl, PHANTOM_UL } = HG;
    const $ = (id) => document.getElementById(id);
    if (!$("txTest")) return;

    const DEVNET_RPC = "https://api.devnet.solana.com";
    const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
    const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";
    const EXPECTED_OWNER = "3gdr5XAjSswQekThSGBSZuGXxAkwo4Lc8c1Bim44EjXR";
    const LAMPORTS = 1000;
    const MEMO = "HyperGrok DEVNET TEST";
    const STORE = "hg-devnet-tx-test";
    const SENT = "hg-devnet-tx-sent";
    const SESSION = "hg-devnet-test-state"; // may share a recent connect session
    const STEP_TTL_MS = 5 * 60 * 1000;
    const dl = createDeeplink({ nacl, base: PHANTOM_UL });

    function setStatus(t) { $("txStatus").textContent = t || ""; }
    function germanize(t) {
      const s = String(t || "");
      if (/^MAINNET_REFUSED/.test(s) || /mainnet/i.test(s) && /genesis/i.test(s)) return "Falsches Netzwerk: die RPC-Antwort ist Solana Mainnet. Mainnet ist auf dieser Seite vollständig gesperrt. Nichts wird gesendet.";
      if (/^WRONG_NETWORK/.test(s)) return "Falsches Netzwerk: die Genesis-Hash der RPC ist nicht die offizielle Devnet-Genesis (EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG). Bitte nur api.devnet.solana.com verwenden. " + s;
      if (/^TX_ALTERED/.test(s)) return "Die signierte Transaktion wurde verändert (Message-Bytes nicht identisch). Senden verweigert. Bitte neu vorbereiten.";
      if (/^DUPLICATE/.test(s)) return "Doppelte Ausführung verweigert: diese Signatur oder dieser Message-Hash wurde bereits gesendet. " + s;
      if (/Zeitüberschreitung: lastValidBlockHeight|Blockhash abgelaufen/.test(s)) return s.replace(/^Zeitüberschreitung: /, "Zeitüberschreitung: Blockhash abgelaufen, neu vorbereiten. ");
      if (/^WRONG_SIGNER/.test(s)) return "Falsche Wallet: Phantom ist nicht mit der bestätigten Adresse 3gdr5XAjSswQekThSGBSZuGXxAkwo4Lc8c1Bim44EjXR verbunden. " + s;
      if (/^SIGNATUR_UNGUELTIG/.test(s)) return "Die Signatur ist ungültig (ed25519-Prüfung fehlgeschlagen). Senden verweigert.";
      if (/^RPC_METHOD_REFUSED/.test(s)) return "Diese RPC-Methode ist auf der Testseite nicht erlaubt.";
      return s;
    }
    function setErr(t) { $("txErr").textContent = germanize(t); }
    function mark(step, failed) {
      for (const li of $("txSteps").querySelectorAll("li")) {
        const s = li.getAttribute("data-step");
        li.classList.remove("done", "current", "failed");
        const order = ["prepared", "reviewed", "signed", "sent", "confirmed"];
        const i = order.indexOf(s), c = order.indexOf(step);
        if (failed && s === step) li.classList.add("failed");
        else if (i >= 0 && c >= 0 && i < c) li.classList.add("done");
        else if (s === step && !failed) li.classList.add(step === "confirmed" ? "done" : "current");
        if (s === "confirmed" && step === "confirmed" && !failed) li.classList.add("done");
      }
    }
    function pageBase() { return location.origin + location.pathname; }
    function load(key) { try { return JSON.parse(localStorage.getItem(key) ?? "null"); } catch { return null; } }
    function save(key, obj) { localStorage.setItem(key, JSON.stringify(obj)); }
    function sentLog() { return load(SENT) || { signatures: [], messageHashes: [] }; }
    function rememberSent(sig, hash) {
      const L = sentLog();
      if (sig && !L.signatures.includes(sig)) L.signatures.push(sig);
      if (hash && !L.messageHashes.includes(hash)) L.messageHashes.push(hash);
      save(SENT, L);
    }

    const ALLOWED_RPC = Object.freeze(["getHealth", "getGenesisHash", "getVersion", "getBalance", "getLatestBlockhash", "getBlockHeight", "getFeeForMessage", "simulateTransaction", "sendTransaction", "getSignatureStatuses", "getTransaction"]);
    async function rpc(method, params) {
      if (!ALLOWED_RPC.includes(method)) throw new Error("RPC_METHOD_REFUSED: " + method);
      const res = await fetch(DEVNET_RPC, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params }),
      });
      const body = await res.json();
      if (!res.ok && !body) throw new Error("RPC HTTP " + res.status);
      if (body.error) throw new Error("RPC " + method + " error " + body.error.code + ": " + body.error.message);
      return body.result;
    }
    async function assertDevnetGenesis() {
      const g = await rpc("getGenesisHash", []);
      if (g === MAINNET_GENESIS) throw new Error("MAINNET_REFUSED: getGenesisHash returned Solana mainnet");
      if (g !== DEVNET_GENESIS) throw new Error("WRONG_NETWORK: genesis " + g + " != official devnet " + DEVNET_GENESIS);
      return g;
    }
    function collectParams() {
      const search = new URLSearchParams(location.search);
      const hash = new URLSearchParams((location.hash || "").replace(/^#/, "").replace(/^\?/, ""));
      const merged = new URLSearchParams();
      for (const src of [search, hash]) for (const [k, v] of src.entries()) if (!merged.has(k)) merged.set(k, v);
      return merged;
    }
    function clearQuery() { history.replaceState(null, "", pageBase()); }

    async function readBalance() {
      try {
        await assertDevnetGenesis();
        const r = await rpc("getBalance", [EXPECTED_OWNER, { commitment: "confirmed" }]);
        const lamports = r.value;
        $("txBalance").textContent = lamports + " Lamports (" + (lamports / 1e9) + " SOL) auf Devnet";
        $("txFaucet").hidden = lamports >= LAMPORTS + 5000;
        return lamports;
      } catch (e) {
        $("txBalance").textContent = "Lesen fehlgeschlagen: " + (e.message || e);
        $("txFaucet").hidden = false;
        throw e;
      }
    }

    function fmtSummary(prep) {
      const s = prep.simulation;
      const fee = prep.feeLamports;
      return [
        "Netzwerk: solana-devnet (api.devnet.solana.com)",
        "Genesis: " + prep.genesis,
        "Absender (fee payer): " + prep.feePayer,
        "Empfänger: " + prep.recipient + "  (Selbsttransfer — bewusst gewählt, kein Dritter erhält Test-SOL)",
        "Betrag: " + prep.lamports + " Lamports (0.000001 SOL)",
        "Memo: " + (prep.memo || "—"),
        "Recent blockhash: " + prep.recentBlockhash,
        "lastValidBlockHeight: " + prep.lastValidBlockHeight,
        "Geschätzte Gebühr (getFeeForMessage): " + (fee == null ? "unbekannt — Senden verweigert" : fee + " Lamports"),
        "Erwartete Kontostandsänderung: " + (fee == null ? "unbekannt" : "netto ca. −" + fee + " Lamports (1000 raus, 1000 wieder rein, plus Gebühr)"),
        "Kontostand vorbereiten: " + prep.balanceBefore + " Lamports",
        "Message-Hash (SHA-256 der Message-Bytes): " + prep.messageSha256,
        "Simulation (sigVerify=false, replaceRecentBlockhash=false): " + (s.err ? "FEHLER " + JSON.stringify(s.err) : "OK"),
        "Simulation units: " + (s.unitsConsumed ?? "—") + (s.logs ? "\nLogs:\n  " + s.logs.slice(-8).join("\n  ") : ""),
        "Instruktionen:",
        ...prep.instructions.map((ix, i) => "  " + (i + 1) + ". " + ix.type + " via " + ix.program + (ix.lamports != null ? " " + ix.lamports + " lamports " + ix.from + " → " + ix.to : "") + (ix.text ? " \"" + ix.text + "\"" : "")),
        "Hinweis: Dies ist KEIN Live-Trade und KEINE Live-Freigabe.",
      ].join("\n");
    }

    async function prepare() {
      setErr("");
      $("txReview").hidden = true;
      $("txSignedBox").hidden = true;
      $("txResultBox").hidden = true;
      $("btnTxSend").disabled = true;
      $("txConfirmBox").checked = false;
      setStatus("Genesis, Kontostand und Blockhash werden von api.devnet.solana.com gelesen…");
      const genesis = await assertDevnetGenesis();
      const balanceBefore = await readBalance();
      const bh = await rpc("getLatestBlockhash", [{ commitment: "finalized" }]);
      const built = TX.buildLegacySelfTransfer({
        feePayer: EXPECTED_OWNER,
        recipient: EXPECTED_OWNER,
        lamports: LAMPORTS,
        recentBlockhash: bh.value.blockhash,
        memo: MEMO,
      });
      const messageSha256 = await TX.sha256hex(built.message);
      const sent = sentLog();
      if (sent.messageHashes.includes(messageSha256)) throw new Error("DUPLICATE: diese Message wurde hier schon gesendet. Bitte neu vorbereiten.");
      let feeLamports = null;
      const feeRes = await rpc("getFeeForMessage", [built.messageB64, { commitment: "confirmed" }]);
      feeLamports = feeRes?.value ?? null;
      if (feeLamports == null) throw new Error("getFeeForMessage lieferte keine Gebühr — Senden nicht möglich, bitte später neu vorbereiten.");
      const sim = await rpc("simulateTransaction", [built.unsignedTxB64, { encoding: "base64", sigVerify: false, replaceRecentBlockhash: false, commitment: "processed" }]);
      const simVal = sim.value || sim;
      const prep = {
        genesis, feePayer: EXPECTED_OWNER, recipient: EXPECTED_OWNER, lamports: LAMPORTS, memo: MEMO,
        recentBlockhash: bh.value.blockhash, lastValidBlockHeight: bh.value.lastValidBlockHeight,
        feeLamports, balanceBefore, messageSha256,
        messageB64: built.messageB64, unsignedTxB64: built.unsignedTxB64, unsignedTxB58: built.unsignedTxB58,
        instructions: built.instructions,
        simulation: { err: simVal.err ?? null, logs: simVal.logs ?? [], unitsConsumed: simVal.unitsConsumed ?? null, accounts: simVal.accounts ?? null },
        preparedAt: new Date().toISOString(),
      };
      save(STORE, { ...load(STORE), prep, step: "prepared", signedTxB58: null, signature: null });
      $("txSummary").textContent = fmtSummary(prep);
      $("txReview").hidden = false;
      mark("reviewed");
      if (prep.simulation.err) {
        setStatus("Simulation fehlgeschlagen. Bitte den Inhalt prüfen (oft: zu wenig Devnet-SOL). Signatur ist deaktiviert.");
        $("btnTxSign").disabled = true;
        setErr("Simulation: " + JSON.stringify(prep.simulation.err));
      } else if (balanceBefore < LAMPORTS + feeLamports) {
        setStatus("Kontostand reicht nicht für 1000 Lamports plus Gebühr. Bitte zuerst Devnet-SOL über faucet.solana.com holen.");
        $("btnTxSign").disabled = true;
        $("txFaucet").hidden = false;
      } else {
        $("btnTxSign").disabled = false;
        setStatus("Transaktion vorbereitet und simuliert. Prüfe die Werte, dann «In Phantom signieren» tippen.");
      }
      return prep;
    }

    function sessionOk() {
      const s = load(SESSION);
      if (!s?.secret || !s.session || !s.phantomPub || !s.pub) return null;
      if (s.publicKey && s.publicKey !== EXPECTED_OWNER) throw new Error("WRONG_SIGNER: verbunden ist " + s.publicKey + ", erwartet " + EXPECTED_OWNER);
      return s;
    }
    async function expired(prep) {
      const h = await rpc("getBlockHeight", [{ commitment: "confirmed" }]);
      return { height: h, expired: h > prep.lastValidBlockHeight };
    }

    function startConnect() {
      const k = dl.newSessionEncryptionKeys();
      const pending = load(STORE) || {};
      const url = dl.connectUrl({
        dappEncryptionPublicKeyB58: k.publicKeyB58,
        appUrl: pageBase(),
        redirectLink: pageBase() + "#step=tx-connected",
        cluster: "devnet",
        base: PHANTOM_UL,
      });
      const check = validateConnectUrl(url);
      if (!check.ok) throw new Error("CONNECT_URL_INVALID: " + check.errors.join("; "));
      save(SESSION, { secret: [...k.secret], pub: k.publicKeyB58, step: "connect_started", pendingTx: true, updatedAt: new Date().toISOString(), expiresAt: new Date(Date.now() + 10 * 60 * 1000).toISOString() });
      save(STORE, { ...pending, waiting: "connect" });
      setStatus("Phantom wird für die Devnet-Verbindung geöffnet (cluster=devnet)…");
      location.href = url;
    }

    function startSign(S, prep) {
      const url = dl.signTransactionUrl({
        dappEncryptionPublicKeyB58: S.pub,
        shared: dl.sharedSecret(S.phantomPub, Uint8Array.from(S.secret)),
        session: S.session,
        transactionBytes: TX.b58decode(prep.unsignedTxB58),
        redirectLink: pageBase() + "#step=tx-signed",
      });
      save(STORE, { ...load(STORE), waiting: "sign" });
      setStatus("Phantom wird für signTransaction geöffnet. Bitte die konkrete Transaktion prüfen und signieren — sie wird dort NICHT gesendet.");
      location.href = url;
    }

    async function onSigned(bytes, prep) {
      const parsed = TX.parseLegacyTx(bytes);
      if (!TX.bytesEqual(parsed.message, TX.b64decode(prep.messageB64))) {
        throw new Error("TX_ALTERED: die signierte Message ist nicht identisch mit der vorbereiteten. Senden verweigert.");
      }
      const hash = await TX.sha256hex(parsed.message);
      if (hash !== prep.messageSha256) throw new Error("TX_ALTERED: Message-Hash weicht ab.");
      const feePayer = parsed.keys[0];
      if (feePayer !== EXPECTED_OWNER) throw new Error("WRONG_SIGNER: fee payer " + feePayer);
      const sigB58 = TX.firstSignatureB58(bytes);
      const ok = nacl.sign.detached.verify(parsed.message, parsed.signatures[0], TX.b58decode(EXPECTED_OWNER));
      if (!ok) throw new Error("SIGNATUR_UNGUELTIG");
      const signedTxB58 = TX.b58encode(bytes);
      const signedTxB64 = TX.b64(bytes);
      save(STORE, { ...load(STORE), step: "signed", signedTxB58, signedTxB64, signature: sigB58, waiting: null });
      $("txSignedSummary").textContent = [
        "Signatur (base58): " + sigB58,
        "Message-Hash unverändert: " + hash,
        "Fee payer: " + feePayer,
        "Netzwerk: solana-devnet",
        "Betrag: 1000 Lamports Selbsttransfer + Memo \"" + MEMO + "\"",
        "Gebühr: " + prep.feeLamports + " Lamports",
        "Diese Transaktion wurde noch NICHT gesendet.",
      ].join("\n");
      $("txSignedBox").hidden = false;
      $("btnTxSend").disabled = true;
      mark("signed");
      setStatus("Signatur geprüft, Message identisch. Zum Senden die Checkbox setzen und den roten Senden-Knopf tippen.");
    }

    async function sendNow() {
      const st = load(STORE);
      if (!st?.prep || !st.signedTxB64 || !st.signature) throw new Error("Keine geprüfte Signatur vorhanden. Bitte zuerst vorbereiten und signieren.");
      if (!$("txConfirmBox").checked) throw new Error("Bitte die Bestätigungs-Checkbox setzen.");
      const prep = st.prep;
      const exp = await expired(prep);
      if (exp.expired) throw new Error("Zeitüberschreitung: lastValidBlockHeight " + prep.lastValidBlockHeight + " ist überschritten (aktuell " + exp.height + "). Bitte neu vorbereiten. Die alte Transaktion wird nicht gesendet.");
      const sent = sentLog();
      if (sent.signatures.includes(st.signature) || sent.messageHashes.includes(prep.messageSha256)) {
        throw new Error("DUPLICATE: diese Transaktion (Signatur oder Message-Hash) wurde hier schon gesendet. Kein erneutes Senden.");
      }
      const statuses = await rpc("getSignatureStatuses", [[st.signature], { searchTransactionHistory: true }]);
      const existing = (statuses.value || statuses)[0];
      if (existing) throw new Error("DUPLICATE: getSignatureStatuses kennt diese Signatur bereits. Kein erneutes Senden.");
      await assertDevnetGenesis();
      setStatus("Sende die signierte Transaktion NUR an api.devnet.solana.com…");
      const sig = await rpc("sendTransaction", [st.signedTxB64, { encoding: "base64", skipPreflight: false, preflightCommitment: "confirmed", maxRetries: 0 }]);
      if (sig !== st.signature) throw new Error("RPC gab eine andere Signatur zurück (" + sig + "). Bitte prüfen, nicht blind erneut senden.");
      rememberSent(sig, prep.messageSha256);
      mark("sent");
      setStatus("Gesendet. Warte auf Bestätigung…");
      let confirmation = null, tx = null, err = null;
      for (let i = 0; i < 30; i++) {
        const stt = await rpc("getSignatureStatuses", [[sig], { searchTransactionHistory: true }]);
        const v = (stt.value || stt)[0];
        if (v) {
          if (v.err) { err = v.err; confirmation = v; break; }
          if (v.confirmationStatus === "confirmed" || v.confirmationStatus === "finalized") { confirmation = v; break; }
        }
        const height = await rpc("getBlockHeight", [{ commitment: "confirmed" }]);
        if (height > prep.lastValidBlockHeight && !v) throw new Error("Blockhash abgelaufen, bevor die Signatur bestätigt wurde. Nicht erneut senden; neu vorbereiten.");
        await new Promise((r) => setTimeout(r, 2000));
      }
      if (!confirmation) throw new Error("Bestätigung zeitüberschritten. Signatur merken und später mit npm run devnet:verify-tx prüfen — nicht blind erneut senden.");
      try { tx = await rpc("getTransaction", [sig, { encoding: "jsonParsed", commitment: "confirmed", maxSupportedTransactionVersion: 0 }]); } catch {}
      const balanceAfter = (await rpc("getBalance", [EXPECTED_OWNER, { commitment: "confirmed" }])).value;
      const feeActual = tx?.meta?.fee ?? null;
      const pre = tx?.meta?.preBalances?.[0];
      const post = tx?.meta?.postBalances?.[0];
      const result = {
        network: "solana-devnet",
        label: "DEVNET TEST self-transfer — not a live trade, not mainnet, not a live approval",
        kind: "DEVNET_TEST",
        signerPublicKey: EXPECTED_OWNER,
        recipient: EXPECTED_OWNER,
        lamports: LAMPORTS,
        memo: MEMO,
        signature: sig,
        slot: confirmation.slot ?? tx?.slot ?? null,
        confirmationStatus: confirmation.confirmationStatus ?? null,
        err: err || tx?.meta?.err || null,
        feeLamportsEstimated: prep.feeLamports,
        feeLamportsActual: feeActual,
        balanceBefore: prep.balanceBefore,
        balanceAfter,
        preBalance: pre ?? null,
        postBalance: post ?? null,
        expectedNetLamports: -prep.feeLamports,
        observedNetLamports: (post != null && pre != null) ? (post - pre) : (balanceAfter - prep.balanceBefore),
        messageSha256: prep.messageSha256,
        recentBlockhash: prep.recentBlockhash,
        lastValidBlockHeight: prep.lastValidBlockHeight,
        simulation: prep.simulation,
        simulationMatch: !err && prep.simulation.err == null && (feeActual == null || feeActual === prep.feeLamports),
        rpc: DEVNET_RPC,
        genesis: prep.genesis,
      };
      if (result.observedNetLamports !== result.expectedNetLamports) {
        result.simulationMatchNote = "Nettoänderung " + result.observedNetLamports + " != erwartete −" + prep.feeLamports + " (bitte prüfen).";
      }
      save(STORE, { ...st, step: err ? "failed" : "confirmed", result });
      $("txOut").value = JSON.stringify(result, null, 2);
      $("txResultBox").hidden = false;
      if (err) {
        mark("confirmed", true);
        setErr("Transaktion auf Devnet fehlgeschlagen: " + JSON.stringify(err));
        setStatus("Gesendet, aber fehlgeschlagen. Siehe Ergebnis-JSON.");
      } else {
        mark("confirmed");
        setStatus("Bestätigt auf Devnet. Bitte das JSON kopieren und an den Desk geben. LIVE-READINESS bleibt: NICHT LIVE.");
      }
    }

    async function handleReturn() {
      const q = collectParams();
      if (!(q.get("step") || "").startsWith("tx-") && !q.get("errorCode") && !(load(STORE) || {}).waiting) {
        if (load(STORE)?.prep) {
          $("txSummary").textContent = fmtSummary(load(STORE).prep);
          $("txReview").hidden = false;
          if (load(STORE).signature) {
            $("txSignedBox").hidden = false;
            $("txSignedSummary").textContent = "Zuvor geprüfte Signatur: " + load(STORE).signature;
          }
          if (load(STORE).result) {
            $("txOut").value = JSON.stringify(load(STORE).result, null, 2);
            $("txResultBox").hidden = false;
          }
        }
        return;
      }
      if (q.get("errorCode") || q.get("errorMessage")) {
        setErr(formatPhantomError(q.get("errorCode") || "", q.get("errorMessage") || ""));
        setStatus("Phantom hat die Anfrage nicht abgeschlossen.");
        if (q.get("errorCode") === "4001") setErr("Phantom-Fehler (code 4001) — Du hast die Anfrage in Phantom abgelehnt.");
        clearQuery();
        return;
      }
      const Sraw = load(SESSION);
      if (q.get("step") === "tx-connected") {
        if (!Sraw?.secret) { setErr("Sitzungsschlüssel fehlt (möglicherweise neuer Tab ohne localStorage). Bitte neu vorbereiten."); clearQuery(); return; }
        try {
          const c = dl.parseConnectResponse(q, Uint8Array.from(Sraw.secret));
          if (c.publicKey !== EXPECTED_OWNER) throw new Error("WRONG_SIGNER: Phantom lieferte " + c.publicKey + ", erwartet " + EXPECTED_OWNER);
          save(SESSION, { ...Sraw, session: c.session, phantomPub: c.phantomEncryptionPublicKey, publicKey: c.publicKey });
          clearQuery();
          const prep = load(STORE)?.prep;
          if (!prep) { setStatus("Verbunden. Tippe «Transaktion vorbereiten», dann erneut signieren."); return; }
          // After connect callback there is typically no user activation — show the sign button, don't auto-jump.
          setStatus("Verbindung bestätigt (" + c.publicKey.slice(0, 4) + "…" + c.publicKey.slice(-4) + "). Tippe «In Phantom signieren».");
          $("txReview").hidden = false;
          $("txSummary").textContent = fmtSummary(prep);
          $("btnTxSign").disabled = false;
        } catch (e) { setErr(String(e.message || e)); clearQuery(); }
        return;
      }
      if (q.get("step") === "tx-signed") {
        try {
          const S = load(SESSION);
          const prep = load(STORE)?.prep;
          if (!S?.phantomPub || !S.secret || !prep) throw new Error("Sitzung oder vorbereitete Transaktion fehlt. Bitte neu vorbereiten.");
          const shared = dl.sharedSecret(S.phantomPub, Uint8Array.from(S.secret));
          const { transactionBytes } = dl.parseSignTransactionResponse(q, shared);
          clearQuery();
          await onSigned(transactionBytes, prep);
        } catch (e) { setErr(String(e.message || e)); clearQuery(); }
      }
    }

    $("btnTxPrepare").onclick = () => { prepare().catch((e) => { setErr(String(e.message || e)); setStatus("Vorbereitung fehlgeschlagen."); }); };
    // iOS: a universal link only opens Phantom when navigation happens synchronously inside the tap.
    // So the expiry check uses a block height cached in the background, never an await in the click handler.
    let cachedHeight = null, cachedHeightAt = 0;
    async function refreshHeight() {
      try { cachedHeight = await rpc("getBlockHeight", [{ commitment: "confirmed" }]); cachedHeightAt = Date.now(); } catch {}
    }
    refreshHeight(); setInterval(refreshHeight, 5000);
    $("btnTxSign").onclick = () => {
      try {
        setErr("");
        const prep = load(STORE)?.prep;
        if (!prep) throw new Error("Bitte zuerst vorbereiten.");
        if (cachedHeight == null || Date.now() - cachedHeightAt > 30000) { refreshHeight(); throw new Error("Blockhöhe wird noch geladen. Bitte in 5 Sekunden erneut tippen."); }
        if (cachedHeight > prep.lastValidBlockHeight) throw new Error("Zeitüberschreitung: Blockhash abgelaufen. Bitte neu vorbereiten.");
        const S = sessionOk();
        if (!S) startConnect();
        else startSign(S, prep);
      } catch (e) { setErr(String(e.message || e)); }
    };
    $("txConfirmBox").onchange = () => {
      $("btnTxSend").disabled = !$("txConfirmBox").checked || !load(STORE)?.signature;
    };
    $("btnTxSend").onclick = () => { sendNow().catch((e) => { setErr(String(e.message || e)); setStatus("Senden nicht ausgeführt oder fehlgeschlagen."); }); };
    $("btnTxCopy").onclick = async () => {
      try { await navigator.clipboard.writeText($("txOut").value); setStatus("Ergebnis kopiert."); } catch { setErr("Kopieren fehlgeschlagen — Text manuell markieren."); }
    };

    readBalance().catch(() => {});
    handleReturn().catch((e) => setErr(String(e.message || e)));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
