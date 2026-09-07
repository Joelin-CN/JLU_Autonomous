"""Debug: find where section links are in the DOM."""
import sys, time, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import pw_run_code, pw_extract_result, log

# Search BOTH main frame and iframe for section links
js = (
    "async (page) => {"
    " const results = { mainFrame: [], iframes: {} };"
    # Main frame links
    " const mainLinks = await page.locator('a').all();"
    " for (const link of mainLinks) {"
    "   const text = await link.textContent();"
    "   const t = text ? text.trim() : '';"
    "   if (t && /^\\d+\\.\\d+/.test(t)) results.mainFrame.push(t);"
    " }"
    # Each iframe
    " const frames = page.frames();"
    " for (const frame of frames) {"
    "   if (frame === page.mainFrame()) continue;"
    "   try {"
    "     const links = await frame.locator('a').all();"
    "     const texts = [];"
    "     for (const link of links) {"
    "       const text = await link.textContent();"
    "       const t = text ? text.trim() : '';"
    "       if (t && /^\\d+\\.\\d+/.test(t)) texts.push(t);"
    "     }"
    "     results.iframes[frame.url().substring(0,80)] = texts;"
    "   } catch(e) { results.iframes['error'] = e.message; }"
    " }"
    " return JSON.stringify(results);"
    "}"
)
raw = pw_run_code(js)
result = pw_extract_result(raw)
log(f"Result: {result[:800]}")
