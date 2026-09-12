// Video playback v16: SEQUENTIAL playback — play one video at a time.
// Playing all videos simultaneously and switching between them looks like
// bot behavior and triggers anti-spider. Sequential is what a real student does.
async (page) => {
    const debugLog = [];

    // Auto-dismiss dialogs
    page.on('dialog', async (dialog) => {
        debugLog.push('dialog: ' + dialog.message().substring(0, 60));
        try { await dialog.accept(); } catch(e) {}
    });

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
    if (vfs.length === 0) return 'no-video-frames';

    const totalTasks = attachments.length || vfs.length;
    debugLog.push('VID tasks=' + totalTasks + ' vfs=' + vfs.length + ' atts=' + attachments.length);

    // ── Step 2: Pre-check — which videos are already done? ──
    let html = '';
    try {
        html = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
    } catch(e) {}

    const doneCount = (html.match(/任务点已完成/g) || []).length;
    const notDoneCount = (html.match(/任务点未完成/g) || []).length;
    debugLog.push('VID pre-check: done=' + doneCount + ' notDone=' + notDoneCount);

    if (doneCount >= totalTasks && notDoneCount === 0) {
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
                debugLog.push('VID skip[' + i + '] ' + attachments[i].name + ' (already done)');
            } else {
                incompleteIndices.push(i);
                debugLog.push('VID play[' + i + '] ' + attachments[i].name
                    + ' dur=' + attachments[i].duration + 's');
            }
        }
    } else {
        for (let i = 0; i < vfs.length; i++) incompleteIndices.push(i);
    }

    if (incompleteIndices.length === 0) {
        return 'all-complete:done=' + doneCount + ' notDone=0 per-video-all-done'
            + ' vids=' + totalTasks + ' phase=sequential'
            + ' || ' + JSON.stringify(debugLog);
    }
    debugLog.push('VID incomplete: ' + incompleteIndices.length + '/' + totalTasks
        + ' [' + incompleteIndices.join(',') + ']');

    // ── Step 3: Play videos SEQUENTIALLY — one at a time ──
    // This is natural student behavior: watch video 0 completely,
    // then video 1, etc. No rapid switching between frames.
    let captchaCheckCounter = 0;
    const CAPTCHA_CHECK_INTERVAL = 6; // every ~30s (6 × 5s cycles)

    for (let j = 0; j < incompleteIndices.length; j++) {
        const i = incompleteIndices[j];
        if (i >= vfs.length) {
            debugLog.push('VID skip[' + i + '] no frame');
            continue;
        }

        const vidName = attachments[i]?.name || ('video-' + i);
        debugLog.push('VID seq-start[' + i + '] ' + vidName);

        // ── 3a: Click play on THIS video only ──
        try {
            const btn = vfs[i].locator('.vjs-big-play-button').first();
            if (await btn.count() > 0) {
                await btn.click({timeout: 3000});
            }
            // Mute + play (reference script approach — less detectable)
            await vfs[i].evaluate(() => {
                const v = document.querySelector('video');
                if (v) {
                    v.muted = true;
                    try { v.play(); } catch(e) {}
                }
            });
            debugLog.push('VID clicked play[' + i + ']');
        } catch(e) {
            debugLog.push('VID click-err[' + i + ']: ' + e.message);
            continue; // Skip to next video if we can't even click play
        }

        // ── 3b: Set up pause auto-resume for THIS video ──
        const resumeDelay = 3000; // 3s — same as reference script
        try {
            await vfs[i].evaluate((delay) => {
                const v = document.querySelector('video');
                if (v && !v._autoResumeSet) {
                    v._autoResumeSet = true;
                    v.addEventListener('pause', () => {
                        setTimeout(() => {
                            try { v.play(); } catch(e) {}
                        }, delay);
                    });
                }
            }, resumeDelay);
        } catch(e) {}

        // ── 3c: Get duration for THIS video ──
        let dur = attachments[i]?.duration || 0;
        for (let a = 0; a < 5; a++) {
            await page.waitForTimeout(2000);
            try {
                const d = await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    return v ? v.duration : 0;
                });
                if (d && !isNaN(d) && d > 0 && d < 99999) { dur = d; break; }
            } catch(e) {}
        }
        if (!dur || dur <= 0) dur = 600; // fallback: 10 minutes
        debugLog.push('VID dur[' + i + ']=' + Math.round(dur) + 's');

        // ── 3d: Poll until THIS video completes ──
        const waitSeconds = Math.max(Math.ceil(dur) + 60, 60);
        const pollCycles = Math.ceil(waitSeconds / 5);
        debugLog.push('VID wait[' + i + ']=' + waitSeconds + 's cycles=' + pollCycles);

        let videoCompleted = false;
        for (let t = 0; t < pollCycles; t++) {
            await page.waitForTimeout(5000);

            // Ensure THIS video stays playing (no rapid switching to others)
            try {
                await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    if (v && v.paused) { try { v.play(); } catch(e) {} }
                });
            } catch(e) {}

            // ── CAPTCHA Detection (every ~30s) ──
            captchaCheckCounter++;
            if (captchaCheckCounter >= CAPTCHA_CHECK_INTERVAL) {
                captchaCheckCounter = 0;
                try {
                    // Check antispider iframe
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
                    // Check mooc iframe body text
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
                } catch(e) {
                    // If we can't check, continue — don't break on transient errors
                }
            }

            // Check if THIS specific video completed
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
                            debugLog.push('VID done[' + i + '] at t=' + (t*5) + 's');
                            break;
                        }
                    }
                }
                // Fallback: overall completion check
                const done = (curHtml.match(/任务点已完成/g) || []).length;
                const notDone = (curHtml.match(/任务点未完成/g) || []).length;
                if (done >= totalTasks && notDone === 0) {
                    return 'all-complete:done=' + done + ' notDone=0'
                        + ' early-exit t=' + (t*5) + ' vids=' + totalTasks
                        + ' phase=sequential'
                        + ' || ' + JSON.stringify(debugLog);
                }
            } catch(e) {}
        }

        if (videoCompleted) {
            debugLog.push('VID seq-done[' + i + '] ' + vidName);
        } else {
            debugLog.push('VID seq-timeout[' + i + '] ' + vidName + ' after ' + waitSeconds + 's');
        }
    }

    // ── Step 4: Final check ──
    let finalDone = 0, finalNotDone = 0;
    try {
        const finalHtml = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
        finalDone = (finalHtml.match(/任务点已完成/g) || []).length;
        finalNotDone = (finalHtml.match(/任务点未完成/g) || []).length;
    } catch(e) {}

    return 'all-complete:done=' + finalDone + ' notDone=' + finalNotDone
        + ' vids=' + totalTasks
        + ' phase=sequential'
        + ' || ' + JSON.stringify(debugLog);
}
