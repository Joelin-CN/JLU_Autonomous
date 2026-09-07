// v17 Section Player — sequential video playback + inline next-section navigation.
// Migrated from etc/referrence_scripts2.txt video + gotoNextSection logic.
//
// Strategy (per the reference script):
//   1. Play videos sequentially (one at a time — natural student behavior)
//   2. Auto-resume on pause (reference script: 3s delay)
//   3. When video ends → check if section complete → auto-advance via "下一节"
//   4. Multi-strategy next-section finder (CSS selectors → catalog links → text match)
//   5. CAPTCHA detection during playback
//
// Returns:
//   "advanced:N"         — advanced to next section N times (chain mode)
//   "all-complete:..."   — all tasks done, couldn't advance further
//   "captcha-detected:..." — CAPTCHA blocked playback
//   "no-video-frames"    — no video iframes found
//   "no-kc-frame"        — no knowledge/cards iframe
async (page) => {
    const debugLog = [];

    // Auto-dismiss dialogs
    page.on('dialog', async (dialog) => {
        debugLog.push('dialog: ' + dialog.message().substring(0, 60));
        try { await dialog.accept(); } catch(e) {}
    });

    // ── Helper: safe click ──
    function safeClick(el) {
        try {
            if (!el) return false;
            el.click();
            el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            return true;
        } catch(e) { return false; }
    }

    // ── Helper: find "下一节" in a document (reference script gotoNextSection) ──
    async function findAndClickNextInDoc(doc, docLabel) {
        const textNextRegex = /下一(节|章|单元|页|个)|继续|下一步|下一个|Next/i;

        // Strategy 1: CSS selectors for next buttons
        const nextBtnSelectors = [
            '.next', '.vc-next', '.reader-next', 'a[title="下一页"]', '.btn-next', '#next',
            '.prev_next .right a', '.switch-btn.next', '.icon-arrow-right', '.right-btn .next'
        ];
        for (const sel of nextBtnSelectors) {
            try {
                const btn = doc.querySelector(sel);
                if (btn && !btn.getAttribute('disabled') && !String(btn.className).includes('disabled')) {
                    if (safeClick(btn)) {
                        debugLog.push('next-found: ' + sel + ' in ' + docLabel);
                        return true;
                    }
                }
            } catch(e) {}
        }

        // Strategy 2: Find current section marker → click next sibling's <a>
        const currentNodeSelectors = ['.cur', '.curr', 'li.active', 'li.selected', '.posCatalog_active'];
        for (const curSel of currentNodeSelectors) {
            try {
                const cur = doc.querySelector(curSel);
                if (cur && cur.nextElementSibling) {
                    const link = cur.nextElementSibling.querySelector('a');
                    if (link && safeClick(link)) {
                        debugLog.push('next-found: sibling of ' + curSel + ' in ' + docLabel);
                        return true;
                    }
                }
            } catch(e) {}
        }

        // Strategy 3: knowledgeId/chapterId/studentstudy links — find current, click next
        try {
            const links = Array.from(doc.querySelectorAll('a[href*="knowledgeId"], a[href*="chapterId"], a[href*="studentstudy"]'));
            if (links.length > 1) {
                const hrefNow = doc.location ? doc.location.href : '';
                if (hrefNow) {
                    const idx = links.findIndex(a => (a.href || '').includes('knowledgeId') && hrefNow.includes('knowledgeId') && a.href.split('knowledgeId')[1] === hrefNow.split('knowledgeId')[1]);
                    const next = idx >= 0 ? links[idx + 1] : null;
                    if (next && safeClick(next)) {
                        debugLog.push('next-found: knowledgeId link #' + (idx + 1) + ' in ' + docLabel);
                        return true;
                    }
                }
                // Fallback: no current URL? click the first knowledgeId link that's not current
                // (this handles the case where location.href is the studentstudy page)
            }
        } catch(e) {}

        // Strategy 4: Text-based — any <a> or <button> whose text matches "下一节" etc.
        try {
            const clickable = Array.from(doc.querySelectorAll('a, button, .btn, .el-button, .next'));
            for (const el of clickable) {
                const txt = (el.textContent || '').trim();
                if (!textNextRegex.test(txt)) continue;

                // Exclude close/cancel/delete/back/prev/disabled/popup elements
                const clsId = (el.className + ' ' + (el.id || '')).toLowerCase();
                const excludeWords = ['close', 'cancel', 'delete', 'remove', 'back', 'prev', 'disabled', 'popup', 'modal'];
                if (excludeWords.some(w => clsId.includes(w))) continue;

                // Visibility check
                const isVisible = el.offsetWidth > 0 && el.offsetHeight > 0 &&
                    window.getComputedStyle(el).display !== 'none' &&
                    window.getComputedStyle(el).visibility !== 'hidden';
                if (!isVisible) continue;

                // Valid navigation element?
                const isNavEl = (
                    (el.tagName === 'A' && (el.href || el.onclick)) ||
                    (el.tagName === 'BUTTON' && el.onclick) ||
                    el.className.includes('btn') ||
                    el.className.includes('next')
                ) && !el.closest('.popup, .modal, .dialog, .alert');

                const isNavText = /^(下一节|下一章|下一个|下一页|继续|Next)$/i.test(txt);
                if (isNavEl && isNavText) {
                    if (safeClick(el)) {
                        debugLog.push('next-found: text "' + txt + '" in ' + docLabel);
                        return true;
                    }
                }
            }
        } catch(e) {}

        return false;
    }

    // ── Helper: find "下一节" across all frames ──
    async function findAndClickNextAcrossFrames() {
        // Try main frame first
        try {
            const mainDoc = await page.evaluate(() => document);
            // Can't pass document across evaluate boundary, use locator instead
        } catch(e) {}

        // Try each iframe
        const frames = page.frames();
        for (const frame of frames) {
            if (frame === page.mainFrame()) continue;
            try {
                const url = frame.url();
                if (!url.includes('chaoxing.com')) continue;
                const found = await frame.evaluate((dl) => {
                    // The evaluate runs in the iframe context — doc = iframe's document
                    const doc = document;
                    const textNextRegex = /下一(节|章|单元|页|个)|继续|下一步|下一个|Next/i;

                    // Strategy 1: CSS selectors
                    const nextBtnSelectors = [
                        '.next', '.vc-next', '.reader-next', 'a[title="下一页"]', '.btn-next', '#next',
                        '.prev_next .right a', '.switch-btn.next'
                    ];
                    for (const sel of nextBtnSelectors) {
                        const btn = doc.querySelector(sel);
                        if (btn && !btn.getAttribute('disabled') && !String(btn.className).includes('disabled')) {
                            btn.click();
                            btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return 'clicked:' + sel;
                        }
                    }

                    // Strategy 2: current → next sibling
                    const curSels = ['.cur', '.curr', 'li.active', 'li.selected', '.posCatalog_active'];
                    for (const cs of curSels) {
                        const cur = doc.querySelector(cs);
                        if (cur && cur.nextElementSibling) {
                            const link = cur.nextElementSibling.querySelector('a');
                            if (link) { link.click(); return 'clicked:sibling-of-' + cs; }
                        }
                    }

                    // Strategy 4: text match
                    const clickable = Array.from(doc.querySelectorAll('a, button, .btn, .el-button, .next'));
                    for (const el of clickable) {
                        const txt = (el.textContent || '').trim();
                        if (!textNextRegex.test(txt)) continue;
                        const clsId = (el.className + ' ' + (el.id || '')).toLowerCase();
                        if (['close','cancel','delete','remove','back','prev','disabled','popup','modal'].some(w => clsId.includes(w))) continue;
                        if (!(el.offsetWidth > 0 && el.offsetHeight > 0)) continue;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const isNavEl = (el.tagName === 'A' || el.tagName === 'BUTTON') && !el.closest('.popup, .modal, .dialog, .alert');
                        if (isNavEl && /^(下一节|下一章|下一个|下一页|继续|Next)$/i.test(txt)) {
                            el.click();
                            el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return 'clicked:text-' + txt;
                        }
                    }

                    return 'not-found';
                }, debugLog);
                if (found && found.startsWith('clicked:')) {
                    debugLog.push('next-found: ' + found + ' in frame ' + url.substring(0, 60));
                    return true;
                }
            } catch(e) {
                // Cross-origin frame — skip
            }
        }
        return false;
    }

    // ── Helper: check if section has any actionable content (reference script hasActionableStudyContent) ──
    async function hasActionableContent() {
        const frames = page.frames().filter(f => f.url().includes('chaoxing.com'));
        for (const frame of frames) {
            try {
                const found = await frame.evaluate(() => {
                    // Video (reference script line 1381)
                    if (document.querySelector('video, .video-js video')) return true;
                    if (document.querySelector('.vjs-control, .vjs-big-play-button, .ans-attach-ct')) return true;

                    // Document/PPT (reference script line 1385)
                    if (document.querySelector('.reader, .ppt, .ppt-play, .catalog, .course_section')) return true;
                    if (document.querySelector('.posCatalog, .posCatalog_active, .catalogTree')) return true;

                    // Next buttons (PPT navigation)
                    if (document.querySelector('.next, .vc-next, .reader-next, a[title="下一页"], .btn-next, #next')) return true;

                    // Quiz (reference script line 1395)
                    if (document.querySelector('.question, .questionLi, .subject_item, .examPaper_subject, .questionContainer')) return true;
                    if (document.querySelector('.q-item, .subject_node, [class*="question"], .ti-item, .exam-item')) return true;
                    if (document.querySelector('input[type="radio"], input[type="checkbox"], textarea, select')) return true;

                    // Embedded content iframes (reference script line 1404-1408)
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    for (const f of iframes) {
                        const src = (f.getAttribute('src') || '').toLowerCase();
                        if (src.includes('mooc-ans') || src.includes('document') || src.includes('ppt')
                            || src.includes('video') || src.includes('knowledgeid')) return true;
                    }

                    // Current section marker (directory navigation)
                    if (document.querySelector('.cur, .curr, li.active, li.selected, .posCatalog_active')) return true;

                    return false;
                });
                if (found) return true;
            } catch(e) {}
        }
        return false;
    }

    // ── Helper: handle PPT content (reference script handlePPTInDocument line 1142-1156) ──
    async function handlePPT() {
        const frames = page.frames().filter(f => f.url().includes('chaoxing.com'));
        for (const frame of frames) {
            try {
                const result = await frame.evaluate(() => {
                    // Strategy 1: CSS selectors for next-page buttons
                    const nextSelectors = ['.next', '.vc-next', '.reader-next', 'a[title="下一页"]', '.btn-next', '#next'];
                    for (const sel of nextSelectors) {
                        const btn = document.querySelector(sel);
                        if (btn && !btn.className.includes('disabled') && !btn.getAttribute('disabled')) {
                            btn.click();
                            btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return 'clicked:' + sel;
                        }
                    }

                    // Strategy 2: scroll to bottom
                    const container = document.scrollingElement || document.body;
                    if (container) container.scrollTop = container.scrollHeight;
                    return 'scrolled';
                });
                if (result && result.startsWith('clicked:')) {
                    debugLog.push('PPT: ' + result);
                    return true;
                }
            } catch(e) {}
        }
        return false;
    }

    // ── Step 0: Empty section check (reference script tryAutoSkipEmptySection) ──
    const hasContent = await hasActionableContent();
    if (!hasContent) {
        debugLog.push('V17 empty-section: no actionable content detected');
        // Try to advance — empty section, just go to next
        const advanced = await findAndClickNextAcrossFrames();
        if (advanced) {
            return 'advanced:1 empty-section'
                + ' || ' + JSON.stringify(debugLog);
        }
        return 'all-complete:empty-section no-next-found'
            + ' || ' + JSON.stringify(debugLog);
    }

    // ── Step 1: Read JC.attachments ──
    const kcFrame = page.frames().find(f => f.url().includes('knowledge/cards'));
    if (!kcFrame) return 'no-kc-frame';
    let attachments = [];
    try {
        attachments = await kcFrame.evaluate(() => {
            if (typeof JC === 'undefined' || !JC.attachments) return [];
            return JC.attachments.map(a => ({
                jobid: a.jobid || '',
                objectId: a.objectId || '',
                name: a.property?.name || '?',
                duration: a.attDuration || 0,
            }));
        });
    } catch(e) { return 'jc-read-err: ' + e.message; }

    // Get video frames
    const vfs = page.frames().filter(f => f.url().includes('video/index.html'));
    if (vfs.length === 0) {
        // No video frames — try PPT handling (reference script handlePPTInDocument)
        debugLog.push('V17 no-video-frames, trying PPT...');
        const pptHandled = await handlePPT();
        if (pptHandled) {
            // PPT next-page clicked — wait a bit then try to advance
            await page.waitForTimeout(3000);
            const advanced = await findAndClickNextAcrossFrames();
            if (advanced) {
                return 'advanced:1 ppt-handled'
                    + ' || ' + JSON.stringify(debugLog);
            }
            return 'all-complete:ppt-handled no-next'
                + ' || ' + JSON.stringify(debugLog);
        }
        return 'no-video-frames';
    }

    const totalTasks = attachments.length || vfs.length;
    debugLog.push('V17 tasks=' + totalTasks + ' vfs=' + vfs.length + ' atts=' + attachments.length);

    // ── Step 2: Pre-check — which videos are already done? ──
    let html = '';
    try {
        html = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
    } catch(e) {}

    const doneCount = (html.match(/任务点已完成/g) || []).length;
    const notDoneCount = (html.match(/任务点未完成/g) || []).length;
    debugLog.push('V17 pre-check: done=' + doneCount + ' notDone=' + notDoneCount);

    if (doneCount >= totalTasks && notDoneCount === 0) {
        // All done — try to advance to next section
        const advanced = await findAndClickNextAcrossFrames();
        if (advanced) {
            return 'advanced:1 done=' + doneCount + ' notDone=0 all-done-pre-check'
                + ' || ' + JSON.stringify(debugLog);
        }
        return 'all-complete:done=' + doneCount + ' notDone=0 pre-check-skip'
            + ' vids=' + totalTasks + ' phase=sequential'
            + ' || ' + JSON.stringify(debugLog);
    }

    // Identify incomplete videos
    const incompleteIndices = [];
    if (attachments.length > 0 && html.length > 0) {
        for (let i = 0; i < attachments.length; i++) {
            const oid = attachments[i].objectId;
            if (!oid) { incompleteIndices.push(i); continue; }
            const oidPos = html.indexOf(oid);
            if (oidPos < 0) { incompleteIndices.push(i); continue; }
            const ctxStart = Math.max(0, oidPos - 5000);
            const ctxEnd = Math.min(html.length, oidPos + 2000);
            const ctx = html.substring(ctxStart, ctxEnd);
            const isDone = ctx.indexOf('任务点已完成') >= 0;
            const isNotDone = ctx.indexOf('任务点未完成') >= 0;
            if (isDone && !isNotDone) {
                debugLog.push('V17 skip[' + i + '] ' + attachments[i].name + ' (already done)');
            } else {
                incompleteIndices.push(i);
                debugLog.push('V17 play[' + i + '] ' + attachments[i].name
                    + ' dur=' + attachments[i].duration + 's');
            }
        }
    } else {
        for (let i = 0; i < vfs.length; i++) incompleteIndices.push(i);
    }

    if (incompleteIndices.length === 0) {
        const advanced = await findAndClickNextAcrossFrames();
        if (advanced) {
            return 'advanced:1 done=' + doneCount + ' notDone=0 per-video-all-done'
                + ' || ' + JSON.stringify(debugLog);
        }
        return 'all-complete:done=' + doneCount + ' notDone=0 per-video-all-done'
            + ' vids=' + totalTasks + ' phase=sequential'
            + ' || ' + JSON.stringify(debugLog);
    }
    debugLog.push('V17 incomplete: ' + incompleteIndices.length + '/' + totalTasks
        + ' [' + incompleteIndices.join(',') + ']');

    // ── Step 3: Play videos SEQUENTIALLY with auto-resume on pause ──
    let captchaCheckCounter = 0;
    const CAPTCHA_CHECK_INTERVAL = 6; // every ~30s

    for (let j = 0; j < incompleteIndices.length; j++) {
        const i = incompleteIndices[j];
        if (i >= vfs.length) {
            debugLog.push('V17 skip[' + i + '] no frame');
            continue;
        }

        const vidName = attachments[i]?.name || ('video-' + i);
        debugLog.push('V17 seq-start[' + i + '] ' + vidName);

        // ── 3a: Click play + mute + auto-resume on pause (reference script approach) ──
        let playTried = 0;
        let playStarted = false;
        while (!playStarted && playTried < 3) {
            try {
                // Click the big play button first
                const btn = vfs[i].locator('.vjs-big-play-button').first();
                if (await btn.count() > 0) {
                    await btn.click({timeout: 3000});
                }
                // Mute + play (reference script line 1098-1100)
                await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    if (v) {
                        v.muted = true;
                        try { v.play(); } catch(e) {}
                    }
                });
                playStarted = true;
                debugLog.push('V17 clicked play[' + i + ']');
            } catch(e) {
                playTried++;
                debugLog.push('V17 click-err[' + i + '] try=' + playTried + ': ' + e.message);
                if (playTried < 3) {
                    await page.waitForTimeout(1800 + Math.floor(Math.random() * 1400));
                }
            }
        }
        if (!playStarted) continue;

        // ── 3b: Auto-resume on pause (reference script: 3s delay, line 128-134) ──
        try {
            await vfs[i].evaluate(() => {
                const v = document.querySelector('video');
                if (v && !v._v17AutoResumeSet) {
                    v._v17AutoResumeSet = true;
                    v.addEventListener('pause', () => {
                        setTimeout(() => {
                            try { v.play(); } catch(e) {}
                        }, 2500 + Math.floor(Math.random() * 1500));
                    });
                }
            });
        } catch(e) {}

        // ── 3c: Get actual duration ──
        let dur = attachments[i]?.duration || 0;
        for (let a = 0; a < 5; a++) {
            await page.waitForTimeout(1600 + Math.floor(Math.random() * 900));
            try {
                const d = await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    return v ? v.duration : 0;
                });
                if (d && !isNaN(d) && d > 0 && d < 99999) { dur = d; break; }
            } catch(e) {}
        }
        if (!dur || dur <= 0) dur = 600; // fallback: 10 min
        debugLog.push('V17 dur[' + i + ']=' + Math.round(dur) + 's');

        // ── 3d: Poll until THIS video completes ──
        const waitSeconds = Math.max(Math.ceil(dur) + 60, 60);
        const pollCycles = Math.ceil(waitSeconds / 5);
        debugLog.push('V17 wait[' + i + ']=' + waitSeconds + 's cycles=' + pollCycles);

        let videoCompleted = false;
        let guardWallTs = 0;
        let guardCurrent = 0;
        for (let t = 0; t < pollCycles; t++) {
            await page.waitForTimeout(4500 + Math.floor(Math.random() * 1500));

            // Auto-resume if paused + stall guard: if currentTime stops
            // advancing for ~20s (buffering, silent pause, autoplay block),
            // force a muted replay instead of waiting out the whole duration.
            try {
                const st = await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    if (!v) return {paused: true, current: 0};
                    if (v.paused) {
                        try { v.play(); } catch(e) {}
                        return {paused: true, current: v.currentTime};
                    }
                    return {paused: false, current: v.currentTime};
                });
                if (!st.paused) {
                    if (guardWallTs === 0) {
                        guardWallTs = Date.now();
                        guardCurrent = st.current;
                    } else if (Math.abs(st.current - guardCurrent) < 0.05
                               && Date.now() - guardWallTs >= 20000) {
                        debugLog.push('V17 stall-guard: no progress for 20s, re-triggering play');
                        await vfs[i].evaluate(() => {
                            const v = document.querySelector('video');
                            if (v) { v.muted = true; try { v.play(); } catch(e) {} }
                        });
                        guardWallTs = Date.now();
                        guardCurrent = st.current;
                    } else if (Math.abs(st.current - guardCurrent) >= 0.05) {
                        guardWallTs = Date.now();
                        guardCurrent = st.current;
                    }
                } else {
                    guardWallTs = 0;
                }
            } catch(e) {}

            // ── CAPTCHA Detection (every ~30s) ──
            captchaCheckCounter++;
            if (captchaCheckCounter >= CAPTCHA_CHECK_INTERVAL) {
                captchaCheckCounter = 0;
                try {
                    const af = page.frames().find(f =>
                        f !== page.mainFrame() && f.url().includes('antispider'));
                    if (af) {
                        const afText = await af.locator('body').innerText();
                        if (afText.includes('验证码') || afText.includes('9010') || afText.includes('操作异常')) {
                            return 'captcha-detected:antispider-iframe t=' + (t*5)
                                + ' seqIdx=' + j + ' vid=' + i
                                + ' || ' + JSON.stringify(debugLog);
                        }
                    }
                    const mf = page.frames().find(f =>
                        f !== page.mainFrame() && f.url().includes('mooc')
                        && !f.url().includes('antispider'));
                    if (mf) {
                        const mfText = await mf.locator('body').innerText();
                        if (mfText.includes('操作异常') || mfText.includes('验证码') || mfText.includes('9010')) {
                            return 'captcha-detected:mooc-iframe t=' + (t*5)
                                + ' seqIdx=' + j + ' vid=' + i
                                + ' || ' + JSON.stringify(debugLog);
                        }
                    }
                } catch(e) {}
            }

            // Check THIS specific video's completion via objectId in HTML
            try {
                const curHtml = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
                const oid = attachments[i]?.objectId;
                if (oid) {
                    const oidPos = curHtml.indexOf(oid);
                    if (oidPos >= 0) {
                        const ctxStart = Math.max(0, oidPos - 5000);
                        const ctxEnd = Math.min(curHtml.length, oidPos + 2000);
                        const ctx = curHtml.substring(ctxStart, ctxEnd);
                        if (ctx.indexOf('任务点已完成') >= 0 && ctx.indexOf('任务点未完成') < 0) {
                            videoCompleted = true;
                            debugLog.push('V17 done[' + i + '] at t=' + (t*5) + 's');
                            break;
                        }
                    }
                }
                // Fallback: overall completion
                const done = (curHtml.match(/任务点已完成/g) || []).length;
                const notDone = (curHtml.match(/任务点未完成/g) || []).length;
                if (done >= totalTasks && notDone === 0) {
                    // All done! Try to advance
                    const advanced = await findAndClickNextAcrossFrames();
                    if (advanced) {
                        return 'advanced:1 done=' + done + ' notDone=0'
                            + ' early-exit t=' + (t*5) + ' vids=' + totalTasks
                            + ' || ' + JSON.stringify(debugLog);
                    }
                    return 'all-complete:done=' + done + ' notDone=0'
                        + ' early-exit t=' + (t*5) + ' vids=' + totalTasks
                        + ' phase=sequential'
                        + ' || ' + JSON.stringify(debugLog);
                }
            } catch(e) {}
        }

        if (videoCompleted) {
            debugLog.push('V17 seq-done[' + i + '] ' + vidName);
        } else {
            debugLog.push('V17 seq-timeout[' + i + '] ' + vidName + ' after ' + waitSeconds + 's');
        }
    }

    // ── Step 4: Final check + auto-advance ──
    let finalDone = 0, finalNotDone = 0;
    try {
        const finalHtml = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
        finalDone = (finalHtml.match(/任务点已完成/g) || []).length;
        finalNotDone = (finalHtml.match(/任务点未完成/g) || []).length;
    } catch(e) {}

    // If all done, try to advance to next section
    if (finalDone >= totalTasks && finalNotDone === 0) {
        const advanced = await findAndClickNextAcrossFrames();
        if (advanced) {
            return 'advanced:1 done=' + finalDone + ' notDone=' + finalNotDone
                + ' vids=' + totalTasks + ' phase=sequential'
                + ' || ' + JSON.stringify(debugLog);
        }
    }

    return 'all-complete:done=' + finalDone + ' notDone=' + finalNotDone
        + ' vids=' + totalTasks
        + ' phase=sequential'
        + ' || ' + JSON.stringify(debugLog);
}
