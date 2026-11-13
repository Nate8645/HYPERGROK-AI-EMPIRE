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
      connectUrl({ dappEncryptionPublicKeyB58, appUrl, redirectLink, cluster }) {
        if (cluster !== "devnet") throw new Error("MAINNET_REFUSED: this page only connects on Solana Devnet (cluster must be exactly devnet)");
        const q = new URLSearchParams({
          app_url: appUrl,
          dapp_encryption_public_key: dappEncryptionPublicKeyB58,
          redirect_link: redirectLink,
          cluster: "devnet",
        });
        return `${base}/connect?${q}`;
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
    "-32603": "In Phantom ist ein interner Fehler aufgetreten.",
  };

  function formatPhantomError(code, message) {
    const de = PHANTOM_ERROR_DE[String(code)] || "Phantom hat die Anfrage nicht abgeschlossen.";
    const parts = ["Phantom-Fehler"];
    if (code) parts.push(`(code ${code})`);
    parts.push("—", de);
    if (message) parts.push("Meldung von Phantom:", message);
    return parts.join(" ");
  }

  global.HGPhantomDeeplink = { PHANTOM_UL, b58encode, b58decode, createDeeplink, formatPhantomError, phantomQueryError };
})(window);
