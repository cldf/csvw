"""
Functionality to address python compatibility issues.
"""
import re
import sys
import datetime


if (sys.version_info.major, sys.version_info.minor) >= (3, 11):  # pragma: no cover
    fromisoformat = datetime.datetime.fromisoformat
else:
    def fromisoformat(s: str) -> datetime.datetime:  # pragma: no cover
        """Somewhat hacky backport of the more full-fledged date parsing support in py3.11."""
        s = s.replace('Z', '+00:00')
        ms_p = re.compile(r'(?P<ms>\.[0-9]+)')
        m = ms_p.search(s)
        ms = None
        if m:
            s = ms_p.sub('', s)
            ms = float(f'0{ms}')
        res = datetime.datetime.fromisoformat(s)
        if ms:
            res = res.replace(microsecond=(ms * 1000000) % 1000000)
        return res
