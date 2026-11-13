// Phantom deeplink protocol helpers (classic script, no ES modules).
// Official base: https://phantom.com/ul/v1  (docs: use phantom.com, not phantom.app)
// Docs: https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android
//       https://docs.phantom.com/phantom-deeplinks/provider-methods/connect
//       https://docs.phantom.com/phantom-deeplinks/provider-methods/signmessage
//       https://docs.phantom.com/phantom-deeplinks/encryption
// No wallet signing keys here: only per-session x25519 ENCRYPTION keys (nacl.box).
(function (global) {
  "use strict";
  const PHANTOM_UL = "https://phantom.com/ul/v1";
  const ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  const MAP = Object.fromEntries([...ALPHABET].map((c, i) => [c, i]));

  function b58encode(bytes) {
    bytes = Uint8Array.from(bytes);
    let zeros = 0; while (zeros < bytes.length && bytes[zeros] === 0) zeros++;
    const digits = [];
    for (let i = zeros; i < bytes.length; i++) {
      let carry = bytes[i];
      for (let j = 0; j < digits.length; j++) { carry += digits[j] << 8; digits[j] = carry % 58; carry = (carry / 58) | 0; }
      while (carry) { digits.push(carry % 58); carry = (carry / 58) | 0; }
    }
    return "1".repeat(zeros) + digits.reverse().map((d) => ALPHABET[d]).join("");
  }
  function b58decode(str) {
    if (typeof str !== "string" || !/^[1-9A-HJ-NP-Za-km-z]*$/.test(str)) throw new Error("invalid base58");
    let zeros = 0; while (zeros < str.length && str[zeros] === "1") zeros++;
    const bytes = [];
    for (let i = zeros; i < str.length; i++) {
      let carry = MAP[str[i]];
      for (let j = 0; j < bytes.length; j++) { carry += bytes[j] * 58; bytes[j] = carry & 0xff; carry >>= 8; }
      while (carry) { bytes.push(carry & 0xff); carry >>= 8; }
    }
    return Uint8Array.from([...new Array(zeros).fill(0), ...bytes.reverse()]);
  }
  const enc = (s) => new TextEncoder().encode(s);
  const dec = (b) => new TextDecoder().decode(b);


  const PHANTOM_APP_UL = "https://phantom.app/ul/v1";
  const ALLOWED_CONNECT_BASES = new Set([PHANTOM_UL, PHANTOM_APP_UL]);

  function isHttpsUrl(value) {
    try {
      const u = new URL(String(value ?? ""));
      if (u.protocol === "https:") return true;
      // Local test servers only. The public GitHub Pages URL is always https.
      if (u.protocol === "http:" && (u.hostname === "127.0.0.1" || u.hostname === "localhost")) return true;
      return false;
    } catch {
      return false;
    }
  }

  // Automated check of a generated Phantom connect URL against official docs:
  // https://docs.phantom.com/phantom-deeplinks/provider-methods/connect
  function validateConnectUrl(url) {
    const errors = [];
    const details = { url: String(url ?? ""), hostPath: "", params: {}, pubkeyBytes: null, encoding: {} };
    let u;
    try { u = new URL(url); } catch {
      return { ok: false, errors: ["URL is not parseable"], details };
    }
    details.hostPath = u.origin + u.pathname;
    const allowedPaths = new Set(["https://phantom.com/ul/v1/connect", "https://phantom.app/ul/v1/connect"]);
    if (!allowedPaths.has(details.hostPath)) errors.push("host/path must be https://phantom.com/ul/v1/connect or https://phantom.app/ul/v1/connect");
    if (u.protocol !== "https:") errors.push("connect URL must be https");
    const q = u.searchParams;
    const keys = [...q.keys()];
    details.paramNames = keys;
    const required = ["app_url", "dapp_encryption_public_key", "redirect_link", "cluster"];
    for (const k of required) if (!q.get(k)) errors.push("missing required param " + k);
    const allowed = new Set(required);
    for (const k of keys) if (!allowed.has(k)) errors.push("unexpected param " + k);
    const cluster = q.get("cluster");
    details.params.cluster = cluster;
    if (cluster && cluster !== "devnet") errors.push("cluster must be exactly devnet (got " + cluster + ")");
    if (cluster === "mainnet-beta" || cluster === "mainnet" || (cluster && /mainnet/i.test(cluster))) {
      errors.push("MAINNET_REFUSED");
    }
    const appUrl = q.get("app_url");
    const redirect = q.get("redirect_link");
    details.params.app_url = appUrl;
    details.params.redirect_link = redirect;
    details.params.dapp_encryption_public_key = q.get("dapp_encryption_public_key");
    if (appUrl && !isHttpsUrl(appUrl)) errors.push("app_url must be a valid https URL");
    if (redirect && !isHttpsUrl(redirect)) errors.push("redirect_link must be a valid https URL");
    // URLSearchParams.get already decodes once. A correctly single-encoded https URL
    // should not still be percent-encoded after that decode.
    if (redirect && /%3A%2F%2F/i.test(redirect)) errors.push("redirect_link appears double-encoded");
    if (appUrl && /%3A%2F%2F/i.test(appUrl)) errors.push("app_url appears double-encoded");
    const rawQuery = u.search;
    const redirRaw = (rawQuery.match(/[?&]redirect_link=([^&]*)/) || [])[1] || "";
    details.encoding.redirect_link_query_piece = redirRaw;
    try {
      details.encoding.redirect_decoded_once = decodeURIComponent(redirRaw);
      details.encoding.singleEncoded = decodeURIComponent(redirRaw) === redirect;
    } catch {
      errors.push("redirect_link query piece is not decodable");
    }
    const pubB58 = q.get("dapp_encryption_public_key") || "";
    if (pubB58) {
      if (!/^[1-9A-HJ-NP-Za-km-z]+$/.test(pubB58)) errors.push("dapp_encryption_public_key is not valid base58");
      else {
        try {
          const bytes = b58decode(pubB58);
          details.pubkeyBytes = bytes.length;
          if (bytes.length !== 32) errors.push("dapp_encryption_public_key decodes to " + bytes.length + " bytes, expected 32");
        } catch (e) {
          errors.push("dapp_encryption_public_key base58 decode failed: " + (e.message || e));
        }
      }
    }
    return { ok: errors.length === 0, errors, details };
  }

  function createDeeplink({ nacl, base = PHANTOM_UL }) {
    if (!nacl?.box) throw new Error("tweetnacl required");
    const api = {
      newSessionEncryptionKeys() { const kp = nacl.box.keyPair(); return { publicKeyB58: b58encode(kp.publicKey), secret: kp.secretKey }; },
      sharedSecret(phantomEncryptionPublicKeyB58, dappSecret) { return nacl.box.before(b58decode(phantomEncryptionPublicKeyB58), dappSecret); },
      encryptPayload(obj, shared) {
        const nonce = nacl.randomBytes(24);
        const boxed = nacl.box.after(enc(JSON.stringify(obj)), nonce, shared);
        return { nonce: b58encode(nonce), payload: b58encode(boxed) };
      },
      decryptPayload(dataB58, nonceB58, shared) {
        const opened = nacl.box.open.after(b58decode(dataB58), b58decode(nonceB58), shared);
        if (!opened) throw new Error("PHANTOM_DECRYPT_FAILED: wrong shared secret or tampered data");
        return JSON.parse(dec(opened));
      },
      connectUrl({ dappEncryptionPublicKeyB58, appUrl, redirectLink, cluster, base: baseOverride }) {
        if (cluster !== "devnet") throw new Error("MAINNET_REFUSED: this page only connects on Solana Devnet (cluster must be exactly devnet)");
        const root = baseOverride || base;
        if (!ALLOWED_CONNECT_BASES.has(root)) {
          throw new Error("CONNECT_HOST_REFUSED: host must be https://phantom.com/ul/v1 or https://phantom.app/ul/v1");
        }
        if (!isHttpsUrl(appUrl)) throw new Error("APP_URL_MUST_BE_HTTPS");
        if (!isHttpsUrl(redirectLink)) throw new Error("REDIRECT_LINK_MUST_BE_HTTPS");
        const pub = b58decode(dappEncryptionPublicKeyB58);
        if (pub.length !== 32) throw new Error("DAPP_ENCRYPTION_PUBLIC_KEY must be base58 of a 32-byte x25519 public key");
        const q = new URLSearchParams({
          app_url: appUrl,
          dapp_encryption_public_key: dappEncryptionPublicKeyB58,
          redirect_link: redirectLink,
          cluster: "devnet",
        });
        const url = `${root}/connect?${q}`;
        const check = validateConnectUrl(url);
        if (!check.ok) throw new Error("CONNECT_URL_INVALID: " + check.errors.join("; "));
        return url;
      },
      parseConnectResponse(params, dappSecret) {
        const p = params instanceof URLSearchParams ? params : new URLSearchParams(params);
        if (p.get("errorCode") || p.get("errorMessage")) throw phantomQueryError(p);
        for (const k of ["phantom_encryption_public_key", "nonce", "data"]) if (!p.get(k)) throw new Error(`connect response missing ${k}`);
        const shared = api.sharedSecret(p.get("phantom_encryption_public_key"), dappSecret);
        const d = api.decryptPayload(p.get("data"), p.get("nonce"), shared);
        if (!d.public_key || !d.session) throw new Error("connect response lacks public_key/session");
        b58decode(d.public_key);
        return { publicKey: d.public_key, session: d.session, phantomEncryptionPublicKey: p.get("phantom_encryption_public_key"), shared };
      },
      signMessageUrl({ dappEncryptionPublicKeyB58, shared, session, message, redirectLink }) {
        const { nonce, payload } = api.encryptPayload({ message: b58encode(enc(message)), session, display: "utf8" }, shared);
        const q = new URLSearchParams({ dapp_encryption_public_key: dappEncryptionPublicKeyB58, nonce, redirect_link: redirectLink, payload });
        return `${base}/signMessage?${q}`;
      },
      parseSignMessageResponse(params, shared) {
        const p = params instanceof URLSearchParams ? params : new URLSearchParams(params);
        if (p.get("errorCode") || p.get("errorMessage")) throw phantomQueryError(p);
        for (const k of ["nonce", "data"]) if (!p.get(k)) throw new Error(`signMessage response missing ${k}`);
        const d = api.decryptPayload(p.get("data"), p.get("nonce"), shared);
        if (!d.signature || b58decode(d.signature).length !== 64) throw new Error("signMessage response lacks a 64-byte signature");
        return { signature: d.signature };
      },
    };
    return api;
  }

  function phantomQueryError(p) {
    const code = p.get("errorCode") || "";
    const msg = p.get("errorMessage") || "";
    const e = new Error(formatPhantomError(code, msg));
    e.code = "PHANTOM_REJECTED";
    e.errorCode = code;
    e.errorMessage = msg;
    return e;
  }

  // Official codes: https://docs.phantom.com/solana/errors
  const PHANTOM_ERROR_DE = {
    "4001": "Du hast die Anfrage in Phantom abgelehnt.",
    "4100": "Diese Methode oder dieses Konto wurde in Phantom nicht berechtigt.",
    "4900": "Phantom konnte keine Netzwerkverbindung herstellen.",
    "-32000": "Ungültige oder fehlende Parameter.",
    "-32002": "In Phantom ist bereits ein Bestätigungsfenster offen. Bitte zuerst dort bestätigen oder ablehnen.",
    "-32003": "Phantom hat die Anfrage als ungültige Transaktion abgelehnt.",
    "-32601": "Phantom kennt diese Methode nicht.",
    "-32603": "In Phantom ist ein interner Fehler aufgetreten. Häufig bei Connect: Testnet Mode ist aus, oder ein Connect-Parameter wird von dieser Phantom-Version nicht erwartet. In Phantom: Profil → Einstellungen → Developer Settings → Testnet Mode, Netzwerk Solana Devnet. Danach eine der Varianten-Knöpfe auf dieser Seite versuchen.",
  };

  function formatPhantomError(code, message) {
    const de = PHANTOM_ERROR_DE[String(code)] || "Phantom hat die Anfrage nicht abgeschlossen.";
    const parts = ["Phantom-Fehler"];
    if (code) parts.push(`(code ${code})`);
    parts.push("—", de);
    if (message) parts.push("Meldung von Phantom:", message);
    return parts.join(" ");
  }

  global.HGPhantomDeeplink = { PHANTOM_UL, PHANTOM_APP_UL, b58encode, b58decode, createDeeplink, validateConnectUrl, formatPhantomError, phantomQueryError, isHttpsUrl };
})(window);
