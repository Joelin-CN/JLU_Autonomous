async (page) => {
    const debugLog = [];

    // ── Step 0: Auto-dismiss any alert dialogs ──
    page.on('dialog', async (dialog) => {
        debugLog.push('dialog: ' + dialog.message().substring(0, 60));
        try { await dialog.accept(); } catch(e) {}
    });

    // ── Step 1: Read JC.attachments for all video task metadata ──
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
    if (attachments.length === 0) return 'no-attachments';
    debugLog.push('JC: ' + attachments.length + ' tasks');

    // ── Step 1.5: Get video frames ──
    const vfs = page.frames().filter(f => f.url().includes('video/index.html'));
    if (vfs.length === 0) return 'no-video-frames';

    // ── Step 2: Extract enc + other params (iframe URL, fallback to main page) ──
    const getParam = (url, name) => {
        const m = url.match(new RegExp('[?&]' + name + '=([^&#]*)'));
        return m ? decodeURIComponent(m[1]) : '';
    };
    let kcUrl = kcFrame.url();
    let enc = getParam(kcUrl, 'enc');
    const nodeId = getParam(kcUrl, 'nodeId') || getParam(kcUrl, 'knowledgeid');
    const clazzIdFromUrl = getParam(kcUrl, 'clazzid') || getParam(kcUrl, 'clazzId');
    const cpiFromUrl = getParam(kcUrl, 'cpi');
    // Fallback: enc often lives on main page URL, not iframe
    if (!enc) {
        enc = getParam(page.url(), 'enc');
        if (enc) debugLog.push('enc from main page');
    }
    if (!kcUrl || kcUrl.length < 10) return 'bad-kc-url: empty';

    // ── Step 3: Construct heartbeat URL template ──
    let constructedPrefix = null, constructedOtherInfo = null;
    if (enc && nodeId && cpiFromUrl) {
        constructedPrefix = 'https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/'
            + cpiFromUrl + '/' + enc;
        constructedOtherInfo = 'nodeId_' + nodeId
            + '-cpi_' + cpiFromUrl
            + '-rt_d-ds_1-ff_d-be_0_0-vt_1-v_6-enc_' + enc;
        debugLog.push('constructed-template OK');
    } else {
        debugLog.push('missing-params enc=' + !!enc + ' nodeId=' + !!nodeId + ' cpi=' + !!cpiFromUrl);
    }

    // ── Step 4: Set up route to patch isdrag=0 ──
    let hbTemplate = null;
    let heartbeatCount = 0;
    try { await page.unroute('**/multimedia/log/**'); } catch(e) {}
    await page.route('**/multimedia/log/**', async (route) => {
        const url = route.request().url();
        heartbeatCount++;
        if (!hbTemplate) {
            const up = { get: (k) => getParam(url, k) };
            hbTemplate = {
                prefix: url.split('?')[0],
                clazzId: up.get('clazzId') || '',
                otherInfo: up.get('otherInfo') || '',
            };
            debugLog.push('hb-url: ' + url.substring(0, 100));
        }
        let nu = url.replace(/isdrag=[0-9]+/g, 'isdrag=0');
        await route.continue({ url: nu !== url ? nu : url });
    });

    // ── Step 5: Click play on all video frames ──
    for (let i = 0; i < vfs.length; i++) {
        try {
            const btn = vfs[i].locator('.vjs-big-play-button').first();
            if (await btn.count() > 0) {
                await btn.click({timeout: 3000});
            }
            await vfs[i].evaluate(() => {
                const v = document.querySelector('video');
                if (v) { try { v.play(); } catch(e) {} }
            });
        } catch(e) {}
    }

    // ── Step 6: Poll for video durations, then SEEK to near-end ──
    const videoDurations = [];
    for (let a = 0; a < 6; a++) {
        await page.waitForTimeout(2000);
        let allReady = true;
        for (let i = 0; i < vfs.length; i++) {
            try {
                const dur = await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    return v ? v.duration : 0;
                });
                if (!dur || isNaN(dur) || dur <= 0) { allReady = false; }
                else { videoDurations[i] = dur; }
            } catch(e) { allReady = false; }
        }
        if (allReady) break;
    }
    // Fill missing durations from JC.attachments
    for (let i = 0; i < vfs.length; i++) {
        if (!videoDurations[i] && attachments[i]) {
            videoDurations[i] = attachments[i].duration;
        }
    }
    debugLog.push('durations: ' + JSON.stringify(videoDurations));

    // Seek all videos to near-end
    for (let i = 0; i < vfs.length; i++) {
        const dur = videoDurations[i];
        if (!dur || dur <= 0) continue;
        const target = Math.max(0, dur - 30);
        try {
            await vfs[i].evaluate((t) => {
                const v = document.querySelector('video');
                if (v && v.duration > 0) { v.currentTime = t; }
            }, target);
            debugLog.push('seek v' + i + ' to ' + Math.round(target) + '/' + Math.round(dur));
        } catch(e) { debugLog.push('seek-err v' + i + ': ' + e.message); }
    }

    // ── Step 7: Send fetch booster heartbeat for each video ──
    const prefix = hbTemplate ? hbTemplate.prefix : constructedPrefix;
    const otherInfo = hbTemplate ? hbTemplate.otherInfo : constructedOtherInfo;
    const finalClazzId = hbTemplate ? hbTemplate.clazzId : clazzIdFromUrl;
    if (prefix) {
        for (const att of attachments) {
            if (att.duration <= 0) continue;
            const hbUrl = prefix + '?'
                + 'clazzId=' + encodeURIComponent(finalClazzId)
                + '&playingTime=' + att.duration
                + '&duration=' + att.duration
                + '&clipTime=0_' + att.duration
                + '&objectId=' + encodeURIComponent(att.objectId)
                + '&otherInfo=' + encodeURIComponent(otherInfo)
                + '&jobid=' + encodeURIComponent(att.jobid)
                + '&isdrag=0';
            try {
                await page.evaluate((u) => fetch(u, {mode: 'no-cors'}), hbUrl);
                debugLog.push('fetch-ok ' + att.name);
            } catch(e) { debugLog.push('fetch-err: ' + e.message); }
        }
    }

    // ── Step 8: Poll DOM + re-seek videos inline (no setInterval) ──
    for (let t = 0; t < 40; t++) {
        await page.waitForTimeout(3000);
        // Re-seek: keep video currentTime near end, ensure playing
        for (let i = 0; i < vfs.length; i++) {
            const dur = videoDurations[i];
            if (!dur || dur <= 0) continue;
            try {
                const st = await vfs[i].evaluate(() => {
                    const v = document.querySelector('video');
                    return v ? {ct: v.currentTime, dur: v.duration, paused: v.paused} : null;
                });
                if (!st) continue;
                if (st.paused) {
                    await vfs[i].evaluate(() => {
                        const v = document.querySelector('video');
                        if (v) { try { v.play(); } catch(e) {} }
                    });
                }
                if (st.ct > st.dur - 15 || st.ct < st.dur - 40) {
                    const target = Math.max(0, st.dur - 30);
                    await vfs[i].evaluate((t) => {
                        const v = document.querySelector('video');
                        if (v) v.currentTime = t;
                    }, target);
                }
            } catch(e) {}
        }
        // Check completion
        try {
            const html = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
            const done = (html.match(/任务点已完成/g) || []).length;
            const notDone = (html.match(/任务点未完成/g) || []).length;
            if (done >= attachments.length && notDone === 0) {
                return 'all-complete:done=' + done + ' notDone=0'
                    + ' hb=' + heartbeatCount + ' t=' + (t*3)
                    + ' vids=' + attachments.length
                    + ' || ' + JSON.stringify(debugLog);
            }
        } catch(e) {}
    }

    let finalDone = 0, finalNotDone = 0;
    try {
        const html = await kcFrame.evaluate(() => document.body ? document.body.innerHTML : '');
        finalDone = (html.match(/任务点已完成/g) || []).length;
        finalNotDone = (html.match(/任务点未完成/g) || []).length;
    } catch(e) {}

    return 'timeout:done=' + finalDone + ' notDone=' + finalNotDone
        + ' hb=' + heartbeatCount
        + ' vids=' + attachments.length
        + ' || ' + JSON.stringify(debugLog);
}
