# HyperGrok Phantom Devnet signing test

This branch contains **only** a static, public test page. It is not the live trading desk.

- **iPhone / Safari (official Phantom deeplink):** Open the page in Safari and tap the single button. The page uses Phantom's documented universal links `https://phantom.com/ul/v1/connect` then `https://phantom.com/ul/v1/signMessage` with `cluster=devnet` and an HTTPS `redirect_link` back to this GitHub Pages URL. Phantom returns the user to Safari. An in-app browser inside Phantom is not required.
- Official docs: [Deep links](https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android), [Connect](https://docs.phantom.com/phantom-deeplinks/provider-methods/connect), [SignMessage](https://docs.phantom.com/phantom-deeplinks/provider-methods/signmessage), [Encryption](https://docs.phantom.com/phantom-deeplinks/encryption), [Specify redirects](https://docs.phantom.com/phantom-deeplinks/specifying-redirects).
- If Phantom injects `window.phantom.solana` / `window.solana`, the same button uses that provider instead.
- **Network:** Solana Devnet only. `cluster` is always `devnet`. Mainnet cluster names and the mainnet genesis hash are refused. There are no `signTransaction`, `signAndSendTransaction`, or `sendTransaction` calls or deeplinks.
- **Test message only.** The page signs a message that always starts with:

      HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION

  That text can never authorize live trading.
- **No secrets.** Do not enter a seed phrase or private key. Only a public address and a `signMessage` signature leave the wallet. Session x25519 encryption keys stay in sessionStorage for this session only and cannot sign transactions.
- **No paid APIs, no analytics, no CDNs.** Scripts and styles are local. `connect-src 'none'`.

Verify a saved signature on the desk machine with `npm run verify-signature -- signed.json`. That check only confirms the ed25519 signature (labeled test-only). It is not a live approval. Do not merge this branch into `main`.
