"""Quick navigation to probability theory course and find 1.6 quiz."""
import sys, time
from pathlib import Path

from chaoxing.session import set_active_session
from chaoxing.browser.engine import pw_goto
from chaoxing.logging_setup import log

set_active_session("chaoxing-chrome")

# Navigate to the probability theory course
url = (
    "https://mooc1.chaoxing.com/visit/stucoursemiddle"
    "?courseid=255106367&clazzid=127207872&cpi=415409200&ismooc2=1&v=2"
)
log(f"Navigating to course: {url}")
pw_goto(url)
time.sleep(3)
log("Navigation done. Check snapshot.")
