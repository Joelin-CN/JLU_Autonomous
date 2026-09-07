---
name: ask-deepseek-question
description: Automate asking DeepSeek questions on chat.deepseek.com with playwright-cli in headed persistent Google Chrome. Use when Codex needs to reuse an existing DeepSeek browser session when possible, log into DeepSeek from passwords/pwd.txt only when needed, ask text questions with Fast mode plus DeepThink and Search forced on, ask DeepSeek about a user-specified image or current screenshot in Image mode with DeepThink forced on, and report the result or blocking issue.
---

# Ask DeepSeek Question

## Overview

Use `playwright-cli` to operate `https://chat.deepseek.com/` in headed, persistent Google Chrome, reuse the existing browser session when possible, log in with credentials stored in the workspace only when needed, route text and image tasks to separate tabs, choose the required chat mode, force the required toggles on, optionally upload an image, submit the user's prompt, and report the outcome.

Do not expose credentials in chat. Read them only to fill the login form.

## Required Setup

- Use the local `playwright-cli` skill if available, and read its `SKILL.md` before browser automation.
- Run commands from the workspace root.
- Use a named persistent session, usually `-s=deepseek`, so subsequent commands target the same Chrome window.
- Before opening Chrome, check whether the persistent session is already open:

```powershell
playwright-cli.cmd list
```

- If `deepseek` is already open, do not run `open` again and do not repeat login. Reuse the session, select or create the tab for the current task type, and continue from `snapshot`.
- If `deepseek` is not open, open Chrome with:

```powershell
playwright-cli.cmd -s=deepseek open --browser=chrome --headed --persistent https://chat.deepseek.com/
```
- Keep the persistent browser open after completion unless the user asks to close it.
- Prefer one `playwright-cli.cmd` browser action per shell command. Do not chain multiple `playwright-cli.cmd` invocations inside one PowerShell script; session state can become flaky and report `Browser 'deepseek' is not open` even when the daemon later lists it as open.
- If a command reports `Browser 'deepseek' is not open`, run `playwright-cli.cmd list`. If `deepseek` is open, retry the last single action once. If no browser is open, reopen Chrome with the command above and continue from a fresh snapshot.

## Credential Lookup

Read `passwords/pwd.txt` in the workspace root and find the entry whose website is `https://chat.deepseek.com/` or `chat.deepseek.com`.

The file may display mojibake for Chinese labels in PowerShell output. Parse by locating the DeepSeek URL block rather than relying on exact Chinese label text. The URL and credential values are the important fields.

Never print the password back to the user. Do not use `Select-String -Context` or other commands that echo neighboring credential lines. Parse credentials in memory, pass them to the browser, and keep command output out of the final answer. If login fails, say that the stored credential failed without revealing it.

## Workflow

1. Check for an existing persistent DeepSeek session:

```powershell
playwright-cli.cmd list
```

   If `deepseek` is open, reuse it and skip the browser open/login path unless the selected tab is on the sign-in page. If it is not open, open DeepSeek in Chrome:

```powershell
playwright-cli.cmd -s=deepseek open --browser=chrome --headed --persistent https://chat.deepseek.com/
```

2. Select or create the tab for the current task type before taking action.

   - Maintain two DeepSeek tabs in the same `deepseek` browser session: prefer tab `0` for ordinary text questions in `快速模式`, and tab `1` for image questions in `识图模式`.
   - Use `playwright-cli.cmd -s=deepseek tab-list` to inspect open tabs. After the session is open, ensure there are two DeepSeek tabs available. If only one DeepSeek tab exists, create a second tab with:

```powershell
playwright-cli.cmd -s=deepseek tab-new https://chat.deepseek.com/
```

   - Reuse tab `0` for non-image prompts and tab `1` for prompts with a user-provided image path or current screenshot upload when practical. Select the matching tab with `tab-select <index>` before changing modes, filling prompts, or uploading files. If existing tabs do not match this convention, select a DeepSeek tab, set the required mode for the current task, and leave the other tab for the other task type.
   - Do not close the other tab; it is the prepared workspace for the other question type and avoids repeating the browser-open/login flow on consecutive skill calls.

3. Take a snapshot:

```powershell
playwright-cli.cmd -s=deepseek snapshot
```

4. If the page is `https://chat.deepseek.com/sign_in`, click `密码登录` when the page starts in SMS-code login mode, then fill the username and password fields from `passwords/pwd.txt`, then submit the login form.

   Typical login controls may appear as Chinese text or mojibake depending on terminal encoding. Prefer role/name matching from the latest snapshot, and stop for human help if captcha, slider verification, SMS verification, or other interactive verification appears.

5. After login, confirm the page URL is `https://chat.deepseek.com/` or a chat URL under `/a/chat/`. If login was performed in one tab, the other tab in the same persistent browser should inherit the authenticated state; reload or navigate it to `https://chat.deepseek.com/` if needed.

6. Choose the required mode:

   - For ordinary text questions, choose `快速模式`.
   - For image questions, choose `识图模式`. In the observed UI, this appears in a radiogroup with `快速模式`, `专家模式`, and `识图模式`.
   - After changing modes, run `snapshot` again because element refs change.

7. Force the required feature toggles on without accidentally disabling already-enabled features.

   - In `快速模式`, force both `深度思考` and `智能搜索` on for every prompt. If either toggle is present and not selected, click it, then run `snapshot` or `eval` again to confirm it is selected.
   - In `识图模式`, force `深度思考` on for every prompt. `智能搜索` may be unavailable in `识图模式`; do not force it when the UI removes it.
   - Always verify required toggle state before sending. `快速模式` and `识图模式` are chat modes, not proof that feature toggles are on.
   - Trust the UI/DOM state for whether a toggle is enabled. Do not ask DeepSeek to self-report whether the toggle was enabled; the model may answer from prompt semantics instead of the page state.

   Before clicking a toggle, inspect `aria-pressed`, `aria-checked`, `data-state`, or the selected CSS class:

```powershell
playwright-cli.cmd -s=deepseek eval "el => JSON.stringify({ariaPressed: el.getAttribute('aria-pressed'), ariaChecked: el.getAttribute('aria-checked'), dataState: el.getAttribute('data-state'), className: el.className, text: el.textContent})" <ref>
```

   A required toggle with `aria-pressed: "true"` or class `ds-toggle-button--selected` is already enabled and should not be clicked again.

8. If the user asks about a specified image, upload that image:

   - Resolve the image path from the user request. Relative paths are relative to the workspace root. Prefer uploading an absolute path from `Resolve-Path`.
   - Click the attachment/image button in the input area.
   - When the file chooser appears, upload the file:

```powershell
playwright-cli.cmd -s=deepseek upload "C:\absolute\path\to\image.png"
```

   - Take a new snapshot and confirm the input area shows a thumbnail or a button named after the uploaded file.

9. If the user asks to use the current `playwright-cli screenshot`, save and upload the screenshot. Uploading the saved PNG is a reliable equivalent to pasting the screenshot into DeepSeek:

```powershell
playwright-cli.cmd -s=deepseek screenshot --filename=.playwright-cli\deepseek-current.png
playwright-cli.cmd -s=deepseek click <attachment-button-ref>
playwright-cli.cmd -s=deepseek upload "<absolute-path-to-workspace>\.playwright-cli\deepseek-current.png"
```

   Confirm the thumbnail appears before sending the prompt.

10. Fill the user's prompt into `textbox "给 DeepSeek 发送消息"` and submit with the send button only after the required tab, mode, upload, and toggle states are verified. Prefer refs from the latest snapshot because refs become stale after tab selection, mode changes, uploads, navigation, and submission.

```powershell
playwright-cli.cmd -s=deepseek fill <textbox-ref> "这是什么"
playwright-cli.cmd -s=deepseek click <send-button-ref>
```

11. Wait for the answer to finish. Poll snapshots until a visible assistant answer appears and generation has stopped. A successful image submission typically navigates to a URL like `https://chat.deepseek.com/a/chat/s/...` and may show a title such as `DeepSeek识图界面`.

12. Summarize DeepSeek's final answer or report the blocking condition. Do not include stored credentials.

## Observed Image Workflow

This workflow was verified for asking DeepSeek "这是什么" about the current page screenshot:

1. Reused the existing `deepseek` persistent browser when it was open; otherwise opened `https://chat.deepseek.com/` with `playwright-cli.cmd -s=deepseek open --browser=chrome --headed --persistent ...`.
2. Selected or created the image-task tab so image prompts do not share the text-task tab.
3. Snapshot showed the user was already logged in, so no credential lookup or login was needed.
4. Clicked the `识图模式` radio. Snapshot then showed `使用识图模式开始对话` and a `图片理解功能内测中` notice.
5. Checked `深度思考` with `eval`; it was already enabled via `aria-pressed: "true"` and selected CSS class.
6. Saved the current browser screenshot to `.playwright-cli\deepseek-current.png`.
7. Clicked the attachment button, handled the file chooser with `playwright-cli upload <absolute path to deepseek-current.png>`, then confirmed a `deepseek-current.png` thumbnail was visible.
8. Filled `这是什么`, clicked send, and waited for the answer.
9. DeepSeek answered that the image was the DeepSeek AI chat page in `识图模式`, with an upload/input area and `深度思考` enabled.

## Common Issues

- **Already logged in**: if the first snapshot shows the main chat page, skip credential lookup and login.
- **Persistent session reuse**: if `playwright-cli.cmd list` shows `deepseek` open, skip `open` and login. Use `tab-list`, `tab-select`, and `tab-new` to route the task to the text or image tab.
- **Login page still visible after submit**: take a new snapshot and check for validation text, captcha, slider, SMS verification, or incorrect credentials. If human verification is required, stop and ask the user to complete it in the headed Chrome window.
- **Mojibake in `pwd.txt` or snapshots**: locate the DeepSeek URL and nearby account/password values instead of depending on Chinese field labels.
- **Credential leakage in command output**: avoid `Select-String -Context` on `passwords/pwd.txt`, and avoid relaying command output that contains login values. The final answer must never include the stored password.
- **Feature toggles are stateful**: inspect state before clicking. A selected toggle may show `aria-pressed: "true"` or a class such as `ds-toggle-button--selected`.
- **Toggle text can be ambiguous**: avoid broad locators such as `getByText('深度思考')` for state checks because status text like `未开启深度思考` can also match. Prefer the exact ref from the latest snapshot, or exact text/role locators that resolve to one toggle element.
- **Required toggle accidentally skipped**: this is a workflow failure unless the UI does not expose the control. In `快速模式`, verify both `深度思考` and `智能搜索`; in `识图模式`, verify `深度思考`. Mention the required toggle status in the final response.
- **DeepThink self-report is unreliable**: DeepSeek may title or answer a conversation as if `深度思考` was not enabled even when the UI shows `已思考（用时 ...）`. Use pre-submit `aria-pressed: "true"` / selected CSS class and post-answer `已思考` UI text as evidence, not the assistant's own wording.
- **Mode changes alter available controls**: `智能搜索` can disappear in `识图模式`; only force controls that are present and required for the current mode.
- **Refs become stale**: after tab selection, login, mode changes, upload, navigation, or message submission, run `snapshot` again and use the new refs.
- **Session state flickers**: if a single action says `Browser 'deepseek' is not open`, run `playwright-cli.cmd list`. Retry once when the list shows the Chrome session open; otherwise reopen Chrome and continue from a fresh snapshot.
- **File chooser is open**: run `playwright-cli upload <path>` immediately after clicking the attachment button.
- **Prompt text contains smart quotes**: PowerShell may treat curly quotes such as `“` and `”` as quote delimiters, causing `playwright-cli fill` to receive too many arguments. Prefer single-quoted PowerShell strings or avoid smart quotes in the command text.
- **Send button disabled**: verify the prompt textbox is filled and, for image questions, that the image thumbnail has appeared.
- **Screenshot paste request**: use `playwright-cli screenshot --filename=...` followed by file upload; it avoids clipboard fragility and produces the same visible attachment.
- **Persistent browser already open**: reuse `-s=deepseek`; avoid closing the browser unless the user asks.
- **Console errors visible in snapshots**: do not treat them as blockers unless the UI action fails or the page cannot submit.

## Completion Criteria

Finish only after one of these is true:

- DeepSeek has received the prompt and produced a visible answer.
- A specific blocking condition is reached, such as captcha, SMS verification, unavailable credentials, missing image path, upload failure, or a site error.

In the final response, state the browser/task status, which task tab was used, whether the required toggles were enabled or unavailable, and, if available, briefly relay DeepSeek's answer. Do not include the stored password.
