# HyperGrok AI Office – Dashboard SNAPSHOT

**NOT LIVE · PAPER ONLY · read-only SNAPSHOT**

- Snapshot-Zeit: 15.11.2026 07:45 MEZ (2026-11-15T06:45:45.392689+00:00 UTC)
- Statischer Stand des lokalen Dashboards. Kein Server, keine WebSocket-Verbindung, kein Not-Aus-Endpunkt, keine Order-Funktion.
- Alle Trading-Werte sind **PAPER** (simuliert). Keine echten Orders, keine Live-Flags aktiv.
- Keine Kontostände, keine Keys oder Tokens. Coinbase wird nur als Status gezeigt (BLOCKED: can_transfer=true), Phantom nur mit öffentlicher Adresse.
- Inhalt: `index.html`, `assets/` (relative Pfade), `snapshot.json` (öffentliche Markt-, Meeting-, Discovery-, Seat- und Paper-Daten).
- Lokal öffnen: Ordner mit einem statischen Server ausliefern (z. B. `python3 -m http.server`) und `index.html` aufrufen.
