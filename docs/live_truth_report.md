# Live Truth Report

Date: 2026-04-21 UTC

Scope:
- `http://127.0.0.1:8000`
- `http://203.0.113.10`

Focus:
- verification only
- current live behavior only

## Commands Run

```bash
curl -sS http://127.0.0.1:8000/chat | rg -n "gpt-4o|gpt-5.4|Claude Sonnet|Claude Opus|Claude Haiku|No description|Untitled project|New chat|Download file|Delete file"
curl -sS http://203.0.113.10/chat | rg -n "gpt-4o|gpt-5.4|Claude Sonnet|Claude Opus|Claude Haiku|No description|Untitled project|New chat|Download file|Delete file"
nl -ba /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html | sed -n '1298,1338p'
nl -ba /opt/ai-workspace/storage/projects/ai-platform/frontend/chat.html | sed -n '2287,2303p'
python3 /home/aiadmin/live_chat_verify.py
python3 - <<'PY'
import json, urllib.request, urllib.parse, time
def req(method, url, body=None):
    data=None; headers={}
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    request=urllib.request.Request(url, method=method, data=data, headers=headers)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as r:
        txt=r.read().decode()
        return r.status, json.loads(txt) if txt else None
for base in ['http://127.0.0.1:8000','http://203.0.113.10']:
    ts=str(int(time.time()))
    s,p=req('POST', base+'/api/auth/guest')
    token=p['sync_token']; user1=p['user_id']
    s,res=req('GET', base+'/api/auth/resolve?token='+urllib.parse.quote(token))
    user2=res['user_id']
    s,proj=req('POST', base+'/api/projects', {'name':f'sync-{ts}','description':'sync probe','user_id':user1})
    pid=proj['id']
    s,chat=req('POST', base+f'/api/projects/{pid}/chats', {'title':f'chat-{ts}','model':'claude-sonnet-4.6'})
    cid=chat['id']
    s,projects=req('GET', base+'/api/projects?user_id='+urllib.parse.quote(user2))
    s,chats=req('GET', base+f'/api/projects/{pid}/chats')
    s,projects2=req('GET', base+'/api/projects?user_id='+urllib.parse.quote(user2))
    s,chats2=req('GET', base+f'/api/projects/{pid}/chats')
    out={
      'base_url':base,
      'token':token,
      'user1':user1,
      'user2':user2,
      'same_user_after_resolve': user1==user2,
      'project_id':pid,
      'chat_id':cid,
      'project_visible_after_resolve': any(x['id']==pid for x in projects),
      'chat_visible_after_resolve': any(x['id']==cid for x in chats),
      'project_visible_after_refresh': any(x['id']==pid for x in projects2),
      'chat_visible_after_refresh': any(x['id']==cid for x in chats2),
      'hidden_workspace_divergence_observed': not(user1==user2 and any(x['id']==pid for x in projects) and any(x['id']==cid for x in chats) and any(x['id']==pid for x in projects2) and any(x['id']==cid for x in chats2))
    }
    print(json.dumps(out))
PY
```

## Localhost Matrix

| Check | Status | Factual result |
|---|---|---|
| Identity fallback to local random UUID if `/api/auth/guest` fails | FAIL | Current frontend no longer does this. In the failure branch at `frontend/chat.html:1333-1337`, it explicitly says `Do NOT create a local UUID`, updates sync UI to `—`, logs the error, and returns `false`. |
| Manual sync-token still required for cross-device sync | PASS | Yes. The second-device flow is still driven by manual token entry and `GET /api/auth/resolve?token=...` at `frontend/chat.html:2301-2303`. |
| Project appears on another device after sync-token resolve | PASS | Live probe: guest token resolved to the same `user_id`, and the created project was visible under that resolved identity. |
| Chat appears on another device after sync-token resolve | PASS | Live probe: the created chat under the synced project was visible after resolve. |
| Refresh preserves synced project/chat state | PASS | Live probe: project and chat were still present on repeated discovery calls after the resolve flow. |
| Hidden workspace divergence in tested sync flow | PASS | Not observed. The same sync token resolved to the same server `user_id`, and project/chat visibility stayed consistent after refresh. |
| Uploaded project files are actually used in `/complete` | PASS | Live file probe returned the exact secret token from the uploaded file: `FILETOKEN-ed1efdb8145243b5`. |
| `gpt-4o` gone from served UI | PASS | Not present in the current served `/chat`. |
| `gpt-5.4` present in served UI | PASS | Present in both model selectors. |
| Supported Claude options present | PASS | `claude-sonnet-4.6`, `claude-opus-4.6`, and `claude-haiku-4.5` are present in the served UI. |
| Raw backend IDs hidden from primary selector labels | PASS | Primary user-facing labels are friendly: `Claude Sonnet`, `Claude Opus`, `Claude Haiku`, `ChatGPT (GPT-5.4)`. The raw IDs are only in option `value`s, not in the primary visible labels. |
| Remaining visible English strings in served `/chat` | PASS | I did not find any remaining visible English strings in the current served `/chat` source during this run. |

## Public Matrix

| Check | Status | Factual result |
|---|---|---|
| Identity fallback to local random UUID if `/api/auth/guest` fails | FAIL | Same code path as localhost. No local UUID fallback remains in the current failure branch. |
| Manual sync-token still required for cross-device sync | PASS | Yes. Public served UI still relies on manual token entry and `/api/auth/resolve`. |
| Project appears on another device after sync-token resolve | PASS | Live probe on public host resolved the same `user_id` and showed the created project. |
| Chat appears on another device after sync-token resolve | PASS | Live probe on public host showed the created chat after resolve. |
| Refresh preserves synced project/chat state | PASS | Repeated discovery after resolve still showed the same project and chat. |
| Hidden workspace divergence in tested sync flow | PASS | Not observed in the tested public flow. |
| Uploaded project files are actually used in `/complete` | PASS | Live file probe returned the exact secret token from the uploaded file: `FILETOKEN-483535a1f5174fb9`. |
| `gpt-4o` gone from served UI | PASS | Not present in the current served public `/chat`. |
| `gpt-5.4` present in served UI | PASS | Present in both model selectors. |
| Supported Claude options present | PASS | `claude-sonnet-4.6`, `claude-opus-4.6`, and `claude-haiku-4.5` are present in the served UI. |
| Raw backend IDs hidden from primary selector labels | PASS | Primary selector labels are user-facing names, not raw model IDs. |
| Remaining visible English strings in served `/chat` | PASS | I did not find any remaining visible English strings in the current served public `/chat` source during this run. |

## Exact Remaining Blockers

- Cross-device sync is still manual. Users must copy and enter a sync token on the second device; there is no automatic account/session-based shared identity flow.
- The frontend still stores the resolved `user_id` and sync token in `localStorage` after successful guest auth. The identity is now server-issued, but local persistence is still part of the client behavior.
- The guest-auth failure path now blocks instead of silently splitting the workspace, which is better, but it still means the product depends on `/api/auth/guest` availability to initialize identity cleanly.
- The Claude model labels are user-friendly, but the exact configured Claude `value`s remain version-like backend IDs (`claude-sonnet-4.6`, `claude-opus-4.6`, `claude-haiku-4.5`) under the hood.

## Bottom Line

Current live state is consistent across localhost and public nginx for the checked items:
- no local-random-UUID fallback remains
- sync-token resolve works end to end
- project and chat visibility survive sync and refresh
- file-to-chat completion is live
- `gpt-4o` is gone
- `gpt-5.4` is live
- I did not find remaining visible English strings in the served `/chat` source in this run

The main remaining blocker is that cross-device continuity is still a manual sync-token flow rather than an automatic shared identity/session model.
