# Max Payne Quote Matcher

Status: v1 implemented with ten curated quotes; audio is in the website repository; AWS deployment configuration remains

## Goal

Add a lore-matching experience to the existing Max Payne fan frontend, backed by the existing `mp-mcp` MCP server. A visitor can enter any text, whether or not it is about Max Payne. The MCP service looks for a connection to the game's story, dialogue, or references and retrieves the best-fitting item together with who said it (when a speaker is known).

The entertainment value comes from making an unexpected but recognizable connection between arbitrary user input and Max Payne lore. This is retrieval and matching from game-related material, not free-form quote generation.

## User Experience

- The feature is part of the existing Max Payne fan website.
- The visitor may supply any 1–20-character word or phrase; it does not need to mention Max Payne.
- The v1 service searches the small curated quote collection for a relevant connection. Expand the collection with reviewed game story, dialogue, and references over time.
- The result identifies the matching quote or reference and its speaker where known.
- Example: input `fallen` can match `The flesh of fallen angels!`, attributed to Jack Lupino.

## Frontend Requirements

- Integrate the feature into the existing static, vanilla HTML/CSS/JavaScript site in `optimized-website/`.
- Replace the existing Monologues content with the quote-matching interaction.
- Show one text field that accepts at most 20 characters, with an adjacent button labeled exactly `Maxpaynize It!`.
- On submission, send the entered text to the frontend-facing JSON API. The browser calls the frontend API, not the MCP endpoint, and must not contain the shared MCP bearer token.
- Show the `maxpaynized` result below the input and button. The result includes the matched quote/reference and its speaker when returned.
- Play a Beretta 9mm reload sound when the `Maxpaynize It!` button is hovered; play a Beretta 9mm gunshot sound when it is clicked to submit.
- Store the reload and gunshot audio assets in S3 and load them from the frontend when needed. The site expects `assets/audio/beretta-reload.mp3` and `assets/audio/beretta-shot.mp3`; source files are included and ready for upload.
- Keep the visual treatment consistent with the site's existing noir/comic style.
- Show searching, no-match, exhausted quota, and request-error states; use a labeled input and live result region. Browser playback rejection is ignored, and effects use 35% volume.

## Usage Limits

- Limit each source IP to 5 valid submissions in a fixed UTC window (86400 seconds by default). Visitors behind one public IP share a quota. After the limit, block further requests until the next window.
- Enforce the limit in the backend before it calls the MCP server; the frontend display is informational and must not be the enforcement mechanism.
- Show remaining uses and wait/reset status in the frontend. The API returns the reset timestamp and seconds remaining.
- Set the window with SAM parameter `MaxpaynizeWindowSeconds`; default is 86400 and shorter values support testing. Each valid POST consumes a use before MCP matching, including no-match and upstream failures. Invalid requests and quota reads do not consume uses.

## Implemented Architecture

- The MCP backend is the Python service in `mp-mcp/`, exposed over Streamable HTTP at `/mcp`.
- The frontend is the existing static Max Payne website in `optimized-website/`.
- The frontend calls a regular JSON API endpoint rather than acting as an MCP client.
- Request path: frontend → API Gateway HTTP API → proxy Lambda → MCP client → existing `mp-mcp` server. `POST /quote` accepts `{"text":"..."}`; `GET /quota` reports current usage.
- The proxy Lambda is responsible for acting as the MCP client and translating between the frontend API request/response and MCP tool call/result.
- The proxy Lambda retrieves the MCP bearer token from SSM Parameter Store and adds it when calling `mp-mcp`. The browser must not receive or contain this shared token.
- API Gateway CORS allows the configured `FrontendOrigin`; routes are throttled. DynamoDB stores usage by a SHA-256 hash of API Gateway's source IP, with TTL cleanup.
- The existing MCP endpoint remains available to MCP clients; the proxy is an additional frontend-facing path.
- `find_quote` uses Claude Haiku by default to select one ID from ten curated entries (the five current website monologue lines, the Jack Lupino example, and four memorable game lines featuring a V-junkie, Vinnie Gognitti in the Captain Baseball Bat Boy scene, Mona Sax, and Vladimir Lem). Quote text and speaker are returned from the local corpus; the model cannot create or alter the returned quote. Override the model with `ANTHROPIC_MODEL`.
- CI/CD setup is currently on hold and is outside this feature's requirements unless later specified.

## Remaining Setup

- Run `npm run deploy:assets` in `optimized-website/` to upload the included audio files. Their sources are documented in `optimized-website/src/assets/audio/README.md`.
- Configure `FrontendOrigin`, `MaxpaynizeLimit`, and `MaxpaynizeWindowSeconds` when deploying the SAM stack; publish the resulting `QuoteApiBaseUrl` as the website's `QUOTE_API_URL` repository variable.
- The SAM proxy reads the existing `/mcp-server/auth-token` from SSM. Deploy the SAM stack manually while CI/CD remains on hold.
- Grow the v1 corpus only with reviewed, accurately attributed entries in `src/mp_mcp/quotes.py`.

## V1 Decisions

The v1 defaults above implement the agreed scope. Revisit identity, quota windows, corpus size, or matching behavior as separate product decisions if the initial experience needs to change.
