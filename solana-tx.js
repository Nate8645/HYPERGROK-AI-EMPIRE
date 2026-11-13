// Minimal Solana legacy-transaction helper. Classic script, no CDN, no web3.js.
// Only SystemProgram.transfer + optional Memo. No mainnet defaults.
(function (global) {
  "use strict";
  const SYSTEM = "11111111111111111111111111111111";
  const MEMO = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";
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
  function concat(parts) {
    const n = parts.reduce((s, p) => s + p.length, 0);
    const out = new Uint8Array(n);
    let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }
  function compactU16(n) {
    if (!Number.isInteger(n) || n < 0 || n > 0xffff) throw new Error("compact-u16 out of range");
    const bytes = [];
    let rem = n;
    for (;;) {
      let elem = rem & 0x7f;
      rem >>= 7;
      if (rem === 0) { bytes.push(elem); break; }
      bytes.push(elem | 0x80);
    }
    return Uint8Array.from(bytes);
  }
  function readCompactU16(bytes, i) {
    let n = 0, shift = 0, used = 0;
    for (;;) {
      const b = bytes[i + used];
      if (b === undefined) throw new Error("compact-u16 truncated");
      n |= (b & 0x7f) << shift;
      used++;
      if ((b & 0x80) === 0) break;
      shift += 7;
      if (used > 3) throw new Error("compact-u16 too long");
    }
    return { n, used };
  }
  function pubkeyBytes(b58) {
    const b = b58decode(b58);
    if (b.length !== 32) throw new Error("public key must be 32 bytes");
    return b;
  }
  function u32le(n) {
    const b = new Uint8Array(4);
    new DataView(b.buffer).setUint32(0, n, true);
    return b;
  }
  function u64le(n) {
    const x = BigInt(n);
    const b = new Uint8Array(8);
    const v = new DataView(b.buffer);
    v.setUint32(0, Number(x & 0xffffffffn), true);
    v.setUint32(4, Number((x >> 32n) & 0xffffffffn), true);
    return b;
  }
  function transferData(lamports) {
    return concat([u32le(2), u64le(lamports)]); // SystemInstruction::Transfer
  }

  function buildLegacySelfTransfer({ feePayer, recipient, lamports, recentBlockhash, memo }) {
    if (feePayer !== recipient) throw new Error("DEVNET TEST requires a self-transfer (sender === recipient)");
    if (!Number.isInteger(lamports) || lamports <= 0 || lamports > 10_000) throw new Error("lamports must be in (0, 10000]");
    const payer = pubkeyBytes(feePayer);
    const bh = pubkeyBytes(recentBlockhash);
    const keys = [feePayer, SYSTEM];
    const memoText = memo ? String(memo) : "";
    if (memoText) keys.push(MEMO);
    const header = Uint8Array.from([1, 0, memoText ? 2 : 1]); // 1 required signer, 0 readonly signed, N readonly unsigned
    const keyBytes = concat([compactU16(keys.length), ...keys.map(pubkeyBytes)]);
    const ixTransfer = concat([
      Uint8Array.from([1]), // programIdIndex = System
      compactU16(2), Uint8Array.from([0, 0]), // from, to (same index)
      compactU16(12), transferData(lamports),
    ]);
    const ixs = [ixTransfer];
    if (memoText) {
      const data = new TextEncoder().encode(memoText);
      ixs.push(concat([
        Uint8Array.from([2]),
        compactU16(0),
        compactU16(data.length), data,
      ]));
    }
    const ixBytes = concat([compactU16(ixs.length), ...ixs]);
    const message = concat([header, keyBytes, bh, ixBytes]);
    const sigCount = compactU16(1);
    const emptySig = new Uint8Array(64);
    const unsignedTx = concat([sigCount, emptySig, message]);
    return {
      feePayer, recipient, lamports, recentBlockhash, memo: memoText || null,
      programs: memoText ? [SYSTEM, MEMO] : [SYSTEM],
      message, unsignedTx,
      messageB64: b64(message),
      unsignedTxB64: b64(unsignedTx),
      unsignedTxB58: b58encode(unsignedTx),
      instructions: [
        { program: "SystemProgram", programId: SYSTEM, type: "transfer", from: feePayer, to: recipient, lamports },
        ...(memoText ? [{ program: "Memo", programId: MEMO, type: "memo", text: memoText }] : []),
      ],
    };
  }

  function b64(bytes) {
    let s = "";
    const b = Uint8Array.from(bytes);
    for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return btoa(s);
  }
  function b64decode(str) {
    const bin = atob(str);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function parseLegacyTx(bytes) {
    bytes = Uint8Array.from(bytes);
    let i = 0;
    const sc = readCompactU16(bytes, i); i += sc.used;
    const signatures = [];
    for (let k = 0; k < sc.n; k++) {
      signatures.push(bytes.slice(i, i + 64));
      i += 64;
    }
    const message = bytes.slice(i);
    const numRequiredSignatures = message[0];
    const numReadonlySigned = message[1];
    const numReadonlyUnsigned = message[2];
    let j = 3;
    const kc = readCompactU16(message, j); j += kc.used;
    const keys = [];
    for (let k = 0; k < kc.n; k++) { keys.push(b58encode(message.slice(j, j + 32))); j += 32; }
    const recentBlockhash = b58encode(message.slice(j, j + 32)); j += 32;
    const ic = readCompactU16(message, j); j += ic.used;
    const instructions = [];
    for (let n = 0; n < ic.n; n++) {
      const programIdIndex = message[j++];
      const ac = readCompactU16(message, j); j += ac.used;
      const accounts = Array.from(message.slice(j, j + ac.n)); j += ac.n;
      const dc = readCompactU16(message, j); j += dc.used;
      const data = message.slice(j, j + dc.n); j += dc.n;
      instructions.push({ programIdIndex, programId: keys[programIdIndex], accounts: accounts.map((a) => keys[a]), data });
    }
    return { signatures, message, numRequiredSignatures, numReadonlySigned, numReadonlyUnsigned, keys, recentBlockhash, instructions };
  }

  function bytesEqual(a, b) {
    a = Uint8Array.from(a); b = Uint8Array.from(b);
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  async function sha256hex(bytes) {
    const hash = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes));
    return Array.from(new Uint8Array(hash), (x) => x.toString(16).padStart(2, "0")).join("");
  }

  function attachSignature(unsignedTx, signature64) {
    const sig = Uint8Array.from(signature64);
    if (sig.length !== 64) throw new Error("signature must be 64 bytes");
    const parsed = parseLegacyTx(unsignedTx);
    if (parsed.signatures.length !== 1) throw new Error("expected one signature slot");
    return concat([compactU16(1), sig, parsed.message]);
  }

  function firstSignatureB58(signedTx) {
    const p = parseLegacyTx(signedTx);
    if (!p.signatures[0] || p.signatures[0].every((b) => b === 0)) throw new Error("signed tx has an empty signature");
    return b58encode(p.signatures[0]);
  }

  global.HGSolanaTx = {
    SYSTEM, MEMO, b58encode, b58decode, b64, b64decode,
    compactU16, buildLegacySelfTransfer, parseLegacyTx, bytesEqual, sha256hex,
    attachSignature, firstSignatureB58, pubkeyBytes,
  };
})(typeof window !== "undefined" ? window : globalThis);
