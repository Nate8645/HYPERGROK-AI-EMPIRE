# HyperGrok Phantom Devnet signing test

This branch contains **only** a static, public test page. It is not the live trading desk.

- **iPhone / Safari (official Phantom deeplink):** Open the page in Safari and tap **Mit Phantom verbinden**. After Phantom confirms the connection and returns to Safari, tap **Signatur in Phantom anfordern**. The second tap is required on iOS because opening a Universal Link needs a user gesture (WebKit user activation). The page uses `https://phantom.com/ul/v1/connect` then `https://phantom.com/ul/v1/signMessage` with `cluster=devnet` and an HTTPS `redirect_link` back to this GitHub Pages URL.
- Session x25519 encryption keys (not wallet keys) are stored in `localStorage` for at most 10 minutes so a redirect into a **new Safari tab** can still decrypt the callback (`sessionStorage` is per-tab). They are cleared after success or failure.
- Official docs: [Deep links](https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android), [Connect](https://docs.phantom.com/phantom-deeplinks/provider-methods/connect), [SignMessage](https://docs.phantom.com/phantom-deeplinks/provider-methods/signmessage), [Encryption](https://docs.phantom.com/phantom-deeplinks/encryption), [Specify redirects](https://docs.phantom.com/phantom-deeplinks/specifying-redirects).
- If Phantom injects `window.phantom.solana` / `window.solana`, the connect button uses that provider instead.
- **Network:** Solana Devnet only. No `signTransaction`, `signAndSendTransaction`, or `sendTransaction` calls or deeplinks.
- **Test message only**, always starting with `HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION`.
- **No secrets.** Do not enter a seed phrase or private key.

Verify a saved signature with `npm run verify-signature -- signed.json` (test-only). Do not merge this branch into `main`.
