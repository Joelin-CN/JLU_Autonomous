"""
Content type detection via JS DOM inspection.

Detects whether the current section is a video, document, audio, or quiz
by searching all Chaoxing-related iframes for known DOM indicators.
Uses a tempfile-based JS execution pipeline to avoid shell escaping issues.
"""

import tempfile
import os

from ...constants import TMP_DIR
from ...logging_setup import log
from ...browser.engine import pw_snapshot
from ...browser.js_runner import pw_run_code_file, pw_extract_result


def detect_content_type() -> str:
    """Detect the type of content in the current section.

    Uses cross-frame detection (reference script hasActionableStudyContent
    approach) to find content across iframes — not just the main page
    snapshot.

    Checks all frames whose URL contains 'chaoxing.com' for:
      - Video: <video> elements, video.js controls, ans-attach-ct
      - Document: .reader, .ppt, .catalog, .course_section, next/prev buttons
      - Audio: text containing 听力/listening/音频
      - Quiz: .question, .subject_item, radio/checkbox inputs
      - Also inspects iframe src attributes for type hints.

    Falls back to snapshot-based text matching if JS detection fails.

    Returns:
        One of: "video", "document", "audio", "quiz", "generic"
    """
    js = """async (page) => {
        // Check across all chaoxing frames (reference script forEachSameOriginFrame pattern)
        const frames = page.frames().filter(f => f.url().includes('chaoxing.com'));

        let hasVideo = false, hasDoc = false, hasAudio = false, hasQuiz = false;

        for (const frame of frames) {
            try {
                const info = await frame.evaluate(() => {
                    let v = false, d = false, a = false, q = false;

                    // Video detection (reference script line 1381)
                    if (document.querySelector('video, .video-js video')) v = true;
                    if (document.querySelector('.vjs-control, .vjs-big-play-button, .ans-attach-ct')) v = true;

                    // Document/PPT detection (reference script line 1385)
                    if (document.querySelector('.reader, .ppt, .ppt-play, .catalog, .course_section')) d = true;
                    if (document.querySelector('.posCatalog, .posCatalog_active, .catalogTree')) d = true;
                    if (document.querySelector('.next, .vc-next, .reader-next, a[title="下一页"], .btn-next, #next')) d = true;

                    // Audio detection
                    const bodyText = (document.body?.innerText || '').toLowerCase();
                    if (bodyText.includes('听力') || bodyText.includes('listening') || bodyText.includes('音频')) a = true;

                    // Quiz detection (reference script line 1395)
                    if (document.querySelector('.question, .questionLi, .subject_item, .examPaper_subject, .questionContainer')) q = true;
                    if (document.querySelector('.q-item, .subject_node, [class*="question"], .ti-item, .exam-item')) q = true;
                    if (document.querySelector('input[type="radio"], input[type="checkbox"]')) q = true;

                    // Embedded iframes with content types (reference script line 1404-1408)
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    for (const f of iframes) {
                        const src = (f.getAttribute('src') || '').toLowerCase();
                        if (src.includes('video')) v = true;
                        if (src.includes('document') || src.includes('ppt')) d = true;
                        if (src.includes('audio')) a = true;
                    }

                    return JSON.stringify({v, d, a, q});
                });
                const parsed = JSON.parse(info);
                if (parsed.v) hasVideo = true;
                if (parsed.d) hasDoc = true;
                if (parsed.a) hasAudio = true;
                if (parsed.q) hasQuiz = true;
            } catch(e) {}
        }

        if (hasVideo) return 'video';
        if (hasAudio) return 'audio';
        if (hasDoc) return 'document';
        if (hasQuiz) return 'quiz';
        return 'generic';
    }"""

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
    tmp.write(js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=15)
        result = pw_extract_result(raw)
        if result in ('video', 'audio', 'document', 'quiz', 'generic'):
            return result
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    # Fallback: snapshot-based detection (text matching in page YAML)
    snap = pw_snapshot()
    snap_lower = snap.lower()
    if "video" in snap_lower or "播放" in snap or "player" in snap_lower:
        return "video"
    elif "audio" in snap_lower or "听力" in snap or "listening" in snap_lower:
        return "audio"
    elif "pdf" in snap_lower or "document" in snap_lower or "文档" in snap:
        return "document"
    else:
        return "generic"
