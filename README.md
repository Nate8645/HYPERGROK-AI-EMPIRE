# HyperGrok Phantom Devnet signing test

This branch contains **only** a static, public test page. It is not the live trading desk.

- **Network:** Solana Devnet only. Mainnet cluster names and the mainnet genesis hash are refused.
- **No transactions are sent.** The page never calls `signAndSendTransaction` or `sendTransaction`. There are no RPC URLs and no network fetches (`connect-src 'none'`).
- **Test message only.** The page signs a message that always starts with:

      HyperGrok DEVNET TEST ONLY - NO LIVE TRADING AUTHORIZATION

  That text can never authorize live trading. The desk live verifier rejects any message containing `DEVNET TEST ONLY` and any message that is not the exact live canonical format.
- **No secrets.** Do not enter a seed phrase or private key. Only a public address and a `signMessage` signature leave the wallet.
- **No paid APIs, no analytics, no CDNs.** Scripts and styles are local (inline or vendored).
- **iPhone:** Open the HTTPS URL in Safari, then use **In Phantom öffnen** (`https://phantom.app/ul/browse/<urlencoded-page-url>?ref=<origin>`). Inside Phantom's in-app browser the page uses `window.phantom.solana` or `window.solana`.

Verify a saved signature on the desk machine with `npm run verify-signature -- signed.json`. That check only confirms the ed25519 signature (labeled test-only). It is not a live approval.

This page is a free GitHub Pages site from this branch root. Do not merge this branch into `main`.
