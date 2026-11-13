# HyperGrok Phantom Devnet signing test

This branch contains **only** a static, public test page. It is not the live trading desk.

- **iPhone / Safari (official Phantom deeplink):** Open the page in Safari and tap **Mit Phantom verbinden**. After Phantom confirms the connection and returns to Safari, tap **Signatur in Phantom anfordern**. The second tap is required on iOS because opening a Universal Link needs a user gesture (WebKit user activation). The page uses `https://phantom.com/ul/v1/connect` then `https://phantom.com/ul/v1/signMessage` with `cluster=devnet` and an HTTPS `redirect_link` back to this GitHub Pages URL.
- Session x25519 encryption keys (not wallet keys) are stored in `localStorage` for at most 10 minutes so a redirect into a **new Safari tab** can still decrypt the callback (`sessionStorage` is per-tab). They are cleared after success or failure.
- If Phantom returns `-32603` / `Unexpected error` on connect: enable **Testnet Mode** (Settings → Developer Settings → Testnet Mode, choose Solana Devnet), then retry. The page also offers labeled fallbacks (host `phantom.app`, `app_url` origin only, clean `redirect_link`). All keep `cluster=devnet`. There is no mainnet option. The exact connect URL (public params only) is shown in the debug panel.
- Official docs: [Deep links](https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android), [Connect](https://docs.phantom.com/phantom-deeplinks/provider-methods/connect), [SignMessage](https://docs.phantom.com/phantom-deeplinks/provider-methods/signmessage), [Encryption](https://docs.phantom.com/phantom-deeplinks/encryption), [Specify redirects](https://docs.phantom.com/phantom-deeplinks/specifying-redirects).
- If Phantom injects `window.phantom.solana` / `window.solana`, the connect button uses that provider instead.
- **Network:** Solana Devnet only. The separately labeled **Devnet-Transaktionstest** section may prepare, simulate, request a Phantom `signTransaction` signature, and — only after an explicit checkbox plus a second button — broadcast a 1000-lamport self-transfer to `https://api.devnet.solana.com`. `signAndSendTransaction` is not used (deprecated). Mainnet hosts are refused (genesis check against official devnet genesis `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG`). CSP `connect-src` allows only that official devnet RPC.
- **Test message only**, always starting with `HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION`.
- **No secrets.** Do not enter a seed phrase or private key.

Verify a saved signature with `npm run verify-signature -- signed.json` (test-only). Do not merge this branch into `main`.


## Devnet-Transaktionstest

This is **not** a live trade and **not** a live-trading approval.

1. Open the page in Safari on iPhone (Phantom). Confirm the address is `3gdr5XAjSswQekThSGBSZuGXxAkwo4Lc8c1Bim44EjXR`.
2. If the Devnet balance is 0, request free test SOL yourself at [https://faucet.solana.com](https://faucet.solana.com) (Devnet, max 2 requests / 8 hours; optional GitHub sign-in for a higher limit). The official `requestAirdrop` RPC is closed (HTTP 410). This page does not claim the web faucet works until you succeed.
3. Tap **Transaktion vorbereiten und simulieren**. Review network, sender, recipient (self-transfer), 1000 lamports, fee, expected balance change, decoded instructions, and message hash.
4. Tap **In Phantom signieren**. Phantom signs only; it does not send.
5. After Safari verifies the signed message bytes are identical to the prepared message, tick the confirmation checkbox and tap **Diese Transaktion jetzt auf Devnet senden**.
6. Copy the result JSON. On the desk box: `npm run devnet:verify-tx -- <signature>`.

Never enter a seed phrase or private key. A successful Devnet test does not authorize live trading.
