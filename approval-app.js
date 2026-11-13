// Static Devnet-only signature test page. Phantom signMessage only.
// Never broadcasts. Never calls signAndSendTransaction or sendTransaction.
// Mainnet (cluster name or mainnet genesis hash) is hard-refused.
// The signed message is a DEVNET TEST ONLY message and is never a live approval.
// No seed or private key is requested or stored. No RPC URLs are used.
import { createDeeplink, b58encode } from "./phantom-deeplink.js";

const $ = (id) => document.getElementById(id);
const err = (e) => { $("err").textContent = String(e?.message ?? e); };
const CLUSTER = "devnet";
const MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";
const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
export const DEVNET_TEST_HEADER = "HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION";
const LIVE_HEADER = "HyperGrok LIVE approval v1";
let session = { publicKey: null, approval: null };

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

/** Inspect provider fields only. Never calls RPC (no getGenesisHash, no connection requests). */
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

function pageUrl() {
  return location.href.split("#")[0];
}

function phantomBrowseUrl() {
  const encoded = encodeURIComponent(pageUrl());
  const ref = encodeURIComponent(location.origin);
  return "https://phantom.app/ul/browse/" + encoded + "?ref=" + ref;
}

function showOpenInPhantom() {
  const wrap = $("openInPhantomWrap");
  const a = $("openInPhantom");
  wrap.hidden = false;
  a.href = phantomBrowseUrl();
  a.textContent = "In Phantom öffnen";
}

function randomNonceHex() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Canonical test-only message. Never the live 'HyperGrok LIVE approval v1' format. */
export function buildDevnetTestMessage({ nonce, issuedAt } = {}) {
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

function fillTestMessage() {
  $("message").value = buildDevnetTestMessage();
}

function message() {
  return assertTestOnlyMessage($("message").value);
}

function render() {
  const out = {
    network: "solana-devnet",
    label: "DEVNET TEST ONLY — not a live trading approval, not broadcast, not a live order",
    signerPublicKey: session.publicKey,
    message: session.approval?.message ?? null,
    signature: session.approval?.signature ?? null,
    ownerSignedApproval: session.approval,
  };
  $("out").value = JSON.stringify(out, null, 2);
  $("btnDownload").disabled = !session.approval;
}

$("btnDownload").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([$("out").value], { type: "application/json" }));
  a.download = "signed-devnet-test-only.json";
  a.click();
};

$("btnNewMessage").onclick = () => {
  fillTestMessage();
  $("err").textContent = "";
};

async function inAppSignMessage() {
  assertDevnet(CLUSTER);
  const p = getProvider();
  if (!p) throw new Error("Phantom provider not found. Open this page inside Phantom.");
  assertProviderDevnet(p);
  const { publicKey } = await p.connect();
  assertProviderDevnet(p);
  session.publicKey = typeof publicKey === "string" ? publicKey : publicKey.toBase58();
  const msg = message();
  const sm = await p.signMessage(new TextEncoder().encode(msg), "utf8");
  const sigBytes = sm.signature ?? sm;
  session.approval = { message: msg, signature: b58encode(sigBytes), signerPublicKey: session.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
  render();
}

function deeplinkMode() {
  const dl = createDeeplink({ nacl: window.nacl });
  const here = location.origin + location.pathname;
  if (location.protocol === "file:") $("err").textContent = "Deeplinks brauchen HTTPS (nicht file://). Im Phantom-In-App-Browser oder über GitHub Pages öffnen.";
  const q = new URLSearchParams(location.search);
  const S = JSON.parse(sessionStorage.getItem("hg-devnet-approval") ?? "null");
  const secret = S ? Uint8Array.from(S.secret) : null;
  if (q.get("step") === "connected" && S) {
    const c = dl.parseConnectResponse(q, secret);
    sessionStorage.setItem("hg-devnet-approval", JSON.stringify({ ...S, session: c.session, phantomPub: c.phantomEncryptionPublicKey, publicKey: c.publicKey }));
    session.publicKey = c.publicKey;
    history.replaceState(null, "", here);
    $("btnApprove").disabled = false;
  } else if (q.get("step") === "approved" && S?.phantomPub) {
    const shared = dl.sharedSecret(S.phantomPub, secret);
    const { signature } = dl.parseSignMessageResponse(q, shared);
    const msg = S.pendingMessage ?? "";
    session.publicKey = S.publicKey;
    session.approval = { message: msg, signature, signerPublicKey: S.publicKey, label: "DEVNET TEST ONLY — not a live trading approval" };
    sessionStorage.setItem("hg-devnet-approval", JSON.stringify({ ...S, approval: session.approval }));
    history.replaceState(null, "", here);
    render();
  } else if (S?.approval) {
    session.approval = S.approval;
    session.publicKey = S.publicKey;
    render();
  } else if (S?.session) $("btnApprove").disabled = false;

  $("btnConnect").onclick = () => {
    try {
      assertDevnet(CLUSTER);
      const k = dl.newSessionEncryptionKeys();
      sessionStorage.setItem("hg-devnet-approval", JSON.stringify({ secret: [...k.secret], pub: k.publicKeyB58 }));
      location.href = dl.connectUrl({ dappEncryptionPublicKeyB58: k.publicKeyB58, appUrl: location.origin, redirectLink: `${here}?step=connected`, cluster: "devnet" });
    } catch (e) { err(e); }
  };
  $("btnApprove").onclick = () => {
    try {
      assertDevnet(CLUSTER);
      const msg = message();
      const s = JSON.parse(sessionStorage.getItem("hg-devnet-approval"));
      sessionStorage.setItem("hg-devnet-approval", JSON.stringify({ ...s, pendingMessage: msg }));
      const shared = dl.sharedSecret(s.phantomPub, Uint8Array.from(s.secret));
      location.href = dl.signMessageUrl({ dappEncryptionPublicKeyB58: s.pub, shared, session: s.session, message: msg, redirectLink: `${here}?step=approved` });
    } catch (e) { err(e); }
  };
}

try {
  assertDevnet(CLUSTER);
  fillTestMessage();
  showOpenInPhantom();
  const provider = getProvider();
  if (provider) {
    $("modeInApp").hidden = false;
    $("btnInApp").onclick = () => inAppSignMessage().catch(err);
  } else {
    $("modeDeeplink").hidden = false;
    deeplinkMode();
  }
} catch (e) { err(e); }

export { assertDevnet, assertProviderDevnet, getProvider, phantomBrowseUrl, CLUSTER, MAINNET_GENESIS, DEVNET_GENESIS, assertTestOnlyMessage };
