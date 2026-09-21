# Live Image/Theme Truth Report

Date: 2026-04-21 UTC

Scope:
- `http://127.0.0.1:8000`
- `http://203.0.113.10`

Focus:
- live image handling
- honest failure behavior
- theme system
- attachment UX

## Commands Run

```bash
curl -sS http://127.0.0.1:8000/chat | rg -n "theme|light|dark|preview|attachment|progress|uploading|msgAttachments|themeToggle|data-theme|localStorage"
curl -sS http://203.0.113.10/chat | rg -n "theme|light|dark|preview|attachment|progress|uploading|msgAttachments|themeToggle|data-theme|localStorage"
rg -n ... /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html
nl -ba /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html | sed -n '1978,2060p'
nl -ba /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html | sed -n '2230,2496p'
nl -ba /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html | sed -n '2518,2560p'
sed -n '1,240p' /opt/ai-workspace/storage/projects/ai-platform/backend/app/api/ai_chat.py
sed -n '1,260p' /opt/ai-workspace/storage/projects/ai-platform/backend/app/services/model_router.py
```

Additional live verification:
- direct API probes for image upload + `/complete` on localhost and public
- headless Chromium DOM verification for rendered localhost theme state
- headless Chromium browser session on localhost for:
  - theme toggle
  - theme persistence after refresh
  - preview before send
  - upload progress indication
  - sent attachment rendering in thread
  - live image completion behavior
- focused headless Chromium retry on public host, which returned `ERR_EMPTY_RESPONSE`

## Localhost Matrix

| Check | Status | Factual result |
|---|---|---|
| Image can be selected from chat UI | PASS | Pending attachment chip appeared before send with image thumbnail and file name. |
| Image upload completes | PASS | Upload path executed and pending chip cleared after send. |
| Sent message visibly includes attachment | PASS | Thread rendered image thumbnail after send. |
| `/complete` actually analyzes image | FAIL | It did not identify the red image. |
| Exact live error | FAIL | Wrapped upstream error: `HTTPStatusError: Server error '502 Bad Gateway' for url 'https://api.claudehub.fun/v1/chat/completions' ...` |
| Honest failure behavior in Russian | FAIL | No clear Russian unsupported-image explanation on the actual failure path. |
| No fake/broken vision behavior | FAIL | UI allows image send, but live multimodal completion fails. |
| Light theme exists | PASS | Verified. |
| Dark theme exists | PASS | Verified. |
| Default theme is light | PASS | Rendered DOM showed `data-theme="light"`. |
| Theme persists after refresh | PASS | After toggle to dark and reload, theme stayed dark. |
| Preview before send | PASS | Verified in browser session. |
| Upload progress indication | PASS | Pending chip showed progress overlay and status text `Загрузка изображений…`. |
| Sent attachment rendering in thread | PASS | Verified in browser session. |

## Public Matrix

| Check | Status | Factual result |
|---|---|---|
| Image upload path exists and completes | PASS | `POST /api/chats/{id}/upload` returned `201` with temp image ref. |
| `/complete` actually analyzes image | FAIL | Public live path also failed to analyze the image. |
| Exact live error | FAIL | Public image completion returned wrapped API/provider failure instead of image analysis. |
| Honest failure behavior in Russian | FAIL | No clear Russian unsupported-image explanation on the actual failure path. |
| Light theme exists | PASS | Present in served UI. |
| Dark theme exists | PASS | Present in served UI. |
| Default theme is light | PASS | Public boot logic defaults to `light`. |
| Theme persists after refresh | PARTIAL | Served code persists theme in `localStorage`, but browser-level public verification was blocked by `ERR_EMPTY_RESPONSE`. |
| Preview before send | PARTIAL | Served code matches localhost, but browser-level public verification was blocked. |
| Upload progress indication | PARTIAL | Served code matches localhost, but browser-level public verification was blocked. |
| Sent attachment rendering in thread | PARTIAL | Served code matches localhost, but browser-level public verification was blocked. |

## Exact Image-Support Conclusion

Current live image understanding is not working correctly.

What is directly observed:
- image attachment can be prepared in the UI
- upload succeeds
- message thread can visibly show the image thumbnail
- completion fails after upload instead of analyzing the image

What failed in live behavior:
- localhost browser session with `gpt-5.4` returned a wrapped upstream error:
  - `HTTPStatusError: Server error '502 Bad Gateway' for url 'https://api.claudehub.fun/v1/chat/completions'`
- direct live API probes for:
  - `gpt-5.4`
  - `claude-sonnet-4.6`
  - `claude-opus-4.6`
  - `claude-haiku-4.5`
  all failed instead of recognizing the red image

What can be concluded without speculation:
- this is not UI-only
- upload and send path works
- the failure happens in the multimodal completion path
- the returned assistant message already contains the wrapped upstream/provider error

Most precise non-speculative conclusion:
- the current provider/backend multimodal integration is failing on live image completion

## Exact Blockers Remaining

- Live image understanding is still broken on both hosts.
- The actual failure happens after successful upload, during multimodal `/complete`.
- UI currently behaves as if vision is supported, but real provider path fails.
- Actual failure path is not explained clearly in Russian; users get a raw wrapped API/provider error instead.
- Public browser-level verification of theme persistence and attachment UX is incomplete because headless Chromium hit `ERR_EMPTY_RESPONSE` for `http://203.0.113.10/chat`, despite `curl` and API requests working.
- Because of that public browser-loading issue, public theme persistence and public attachment preview/progress/thread rendering remain only partially browser-verified.
