"""
Course page navigation helpers.

Thin wrappers around the browser engine for Chaoxing-specific URL patterns.
"""

from ..browser.engine import pw_goto, pw_snapshot


def pw_goto_course(courseid: str, clazzid: str, cpi: str = "415409200"):
    """Navigate to a course page via the mooc1 visit URL.

    Args:
        courseid: Course ID from course card.
        clazzid: Class ID from course card.
        cpi: Course plan identifier (default "415409200").
    """
    url = (
        f"https://mooc1.chaoxing.com/visit/stucoursemiddle"
        f"?courseid={courseid}&clazzid={clazzid}&cpi={cpi}&ismooc2=1&v=2"
    )
    return pw_goto(url)


def pw_get_iframe_snapshot() -> str:
    """Get snapshot of the course content iframe.

    The course content (chapters, quizzes, videos) is loaded in a
    mooc2-ans.chaoxing.com iframe. This is a thin wrapper that
    delegates to pw_snapshot() since the snapshot already includes
    iframe content.
    """
    return pw_snapshot()
