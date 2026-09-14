from __future__ import annotations

import base64
import json
import os
import random
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
EMBEDDED_WEB = {
    "index.html": "PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0ia28iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9InV0Zi04Ij48bWV0YSBuYW1lPSJ2aWV3cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MSx2aWV3cG9ydC1maXQ9Y292ZXIiPjxtZXRhIG5hbWU9InRoZW1lLWNvbG9yIiBjb250ZW50PSIjMTAxNzI3Ij48dGl0bGU+7IKs7J6l64uYIOyekOuPmeunpOunpDwvdGl0bGU+PGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSIvc3R5bGUuY3NzIj48L2hlYWQ+Cjxib2R5PjxtYWluPgogIDxoZWFkZXI+PGRpdj48c21hbGwgaWQ9Im1vZGUiPuuvuOq1reyjvOyLnSDCtyDslYjsoITtlZwg66qo7J2Y7Yis7J6QPC9zbWFsbD48aDE+7IKs7J6l64uYIOyekOuPmeunpOunpDwvaDE+PC9kaXY+PHNwYW4gaWQ9InN0YXR1cyIgY2xhc3M9InBpbGwiPuygleyngDwvc3Bhbj48L2hlYWRlcj4KICA8c2VjdGlvbiBjbGFzcz0iaGVybyI+PGRpdj48c21hbGw+7LSdIO2PieqwgOq4iOyVoTwvc21hbGw+PGgyIGlkPSJlcXVpdHkiPiQwLjAwPC9oMj48c3BhbiBpZD0icHJvZml0Ij4kMC4wMCAoMC4wMCUpPC9zcGFuPjwvZGl2PjxidXR0b24gaWQ9InRvZ2dsZSI+7J6Q64+Z66ek66ekIOyLnOyekTwvYnV0dG9uPjwvc2VjdGlvbj4KICA8c2VjdGlvbiBjbGFzcz0iZ3JpZCI+PGFydGljbGU+PHNtYWxsPu2YhOyerOqwgDwvc21hbGw+PGIgaWQ9InByaWNlIj4tPC9iPjwvYXJ0aWNsZT48YXJ0aWNsZT48c21hbGw+7ZiE6riIPC9zbWFsbD48YiBpZD0iY2FzaCI+LTwvYj48L2FydGljbGU+PGFydGljbGU+PHNtYWxsPuuztOycoOyImOufiTwvc21hbGw+PGIgaWQ9InF0eSI+LTwvYj48L2FydGljbGU+PGFydGljbGU+PHNtYWxsPuy1nOq3vCDtjJDri6g8L3NtYWxsPjxiIGlkPSJzaWduYWwiPi08L2I+PC9hcnRpY2xlPjwvc2VjdGlvbj4KICA8c2VjdGlvbiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idGl0bGUiPjxoMz7qsIDqsqkg7Z2Q66aEPC9oMz48c3BhbiBpZD0ic3ltYm9sIj48L3NwYW4+PC9kaXY+PGNhbnZhcyBpZD0iY2hhcnQiIGhlaWdodD0iMTUwIj48L2NhbnZhcz48L3NlY3Rpb24+CiAgPHNlY3Rpb24gY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRpdGxlIj48aDM+66ek66ekIOyEpOyglTwvaDM+PHNwYW4+7KCA7J6lIOymieyLnCDsoIHsmqk8L3NwYW4+PC9kaXY+PGZvcm0gaWQ9InNldHRpbmdzIj4KICAgIDxsYWJlbD7sooXrqqk8aW5wdXQgbmFtZT0ic3ltYm9sIiBwbGFjZWhvbGRlcj0iTkFTRDpBQVBMIj48L2xhYmVsPgogICAgPGRpdiBjbGFzcz0icm93Ij48bGFiZWw+64uo6riw7ISgPGlucHV0IG5hbWU9InNob3J0X3dpbmRvdyIgdHlwZT0ibnVtYmVyIj48L2xhYmVsPjxsYWJlbD7snqXquLDshKA8aW5wdXQgbmFtZT0ibG9uZ193aW5kb3ciIHR5cGU9Im51bWJlciI+PC9sYWJlbD48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyI+PGxhYmVsPu2IrOyekOu5hOykkSAlPGlucHV0IG5hbWU9InBvc2l0aW9uX3BjdCIgdHlwZT0ibnVtYmVyIiBzdGVwPSIwLjUiPjwvbGFiZWw+PGxhYmVsPu2VmOujqCDshpDsi6TtlZzrj4QgJTxpbnB1dCBuYW1lPSJkYWlseV9sb3NzX2xpbWl0X3BjdCIgdHlwZT0ibnVtYmVyIiBzdGVwPSIwLjUiPjwvbGFiZWw+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJyb3ciPjxsYWJlbD7shpDsoIggJTxpbnB1dCBuYW1lPSJzdG9wX2xvc3NfcGN0IiB0eXBlPSJudW1iZXIiIHN0ZXA9IjAuNSI+PC9sYWJlbD48bGFiZWw+7J217KCIICU8aW5wdXQgbmFtZT0idGFrZV9wcm9maXRfcGN0IiB0eXBlPSJudW1iZXIiIHN0ZXA9IjAuNSI+PC9sYWJlbD48L2Rpdj4KICAgIDxidXR0b24gY2xhc3M9InNlY29uZGFyeSI+7ISk7KCVIOyggOyepTwvYnV0dG9uPjwvZm9ybT48L3NlY3Rpb24+CiAgPHNlY3Rpb24gY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRpdGxlIj48aDM+7LWc6re8IOqxsOuemDwvaDM+PGJ1dHRvbiBpZD0idGljayIgY2xhc3M9ImxpbmsiPjHtmowg7Iuk7ZaJPC9idXR0b24+PC9kaXY+PGRpdiBpZD0idHJhZGVzIiBjbGFzcz0idHJhZGVzIj48L2Rpdj48L3NlY3Rpb24+CiAgPHAgY2xhc3M9Im5vdGljZSI+4pqg77iPIO2ZlOuptCDsg4Hri6jsnbQg4oCY7Iuk7KCEIOyjvOusuOKAmeydtOuptCDsi6TsoJwg6rOE7KKM66GcIOyjvOusuOuQqeuLiOuLpC4g7IiY7J217J2EIOuztOyepe2VmOyngCDslYrsirXri4jri6QuPC9wPgo8L21haW4+PGRpdiBpZD0idG9hc3QiPjwvZGl2PjxzY3JpcHQgc3JjPSIvYXBwLmpzIj48L3NjcmlwdD48L2JvZHk+PC9odG1sPgo=",
    "style.css": "OnJvb3R7Zm9udC1mYW1pbHk6c3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sc2Fucy1zZXJpZjtjb2xvcjojZWRmMmZmO2JhY2tncm91bmQ6IzBhMGYxYztjb2xvci1zY2hlbWU6ZGFya30qe2JveC1zaXppbmc6Ym9yZGVyLWJveH1ib2R5e21hcmdpbjowO2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE2MGRlZywjMTExYTMwLCMwODBjMTYgNTUlKTttaW4taGVpZ2h0OjEwMHZofW1haW57bWF4LXdpZHRoOjcyMHB4O21hcmdpbjphdXRvO3BhZGRpbmc6MjRweCAxNnB4IDYwcHh9aGVhZGVyLC50aXRsZSwuaGVybywucm93e2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHh9aDF7Zm9udC1zaXplOjIzcHg7bWFyZ2luOjRweCAwfWgye2ZvbnQtc2l6ZTozOHB4O21hcmdpbjo4cHggMH1oM3ttYXJnaW46MDtmb250LXNpemU6MTdweH1zbWFsbCwudGl0bGUgc3Bhbntjb2xvcjojOGQ5YWI1fS5waWxse2JhY2tncm91bmQ6IzMzNDA1YjtwYWRkaW5nOjdweCAxMnB4O2JvcmRlci1yYWRpdXM6OTk5cHg7Zm9udC1zaXplOjEzcHh9LnBpbGwub257YmFja2dyb3VuZDojMTIzZjMyO2NvbG9yOiM1MmUzYWF9Lmhlcm8sLmNhcmR7YmFja2dyb3VuZDpyZ2JhKDIwLDI5LDQ5LC45Mik7Ym9yZGVyOjFweCBzb2xpZCAjMjYzMzRkO2JvcmRlci1yYWRpdXM6MjBweDtwYWRkaW5nOjIwcHg7bWFyZ2luLXRvcDoxNnB4O2JveC1zaGFkb3c6MCAxNHB4IDQwcHggIzAwMDR9Lmhlcm8gYnV0dG9uLGZvcm0gYnV0dG9ue2JvcmRlcjowO2JvcmRlci1yYWRpdXM6MTRweDtiYWNrZ3JvdW5kOiM0Nzc3ZmY7Y29sb3I6d2hpdGU7Zm9udC13ZWlnaHQ6ODAwO3BhZGRpbmc6MTVweCAxOHB4fS5oZXJvIGJ1dHRvbi5zdG9we2JhY2tncm91bmQ6I2VmNWI2OH0uZ3JpZHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjEwcHg7bWFyZ2luLXRvcDoxMHB4fS5ncmlkIGFydGljbGV7YmFja2dyb3VuZDojMTIxYjJlO2JvcmRlcjoxcHggc29saWQgIzIzMzA0YTtib3JkZXItcmFkaXVzOjE2cHg7cGFkZGluZzoxNXB4O21pbi13aWR0aDowfS5ncmlkIGJ7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjdweDt3aGl0ZS1zcGFjZTpub3dyYXA7b3ZlcmZsb3c6aGlkZGVuO3RleHQtb3ZlcmZsb3c6ZWxsaXBzaXN9LnRpdGxle21hcmdpbi1ib3R0b206MTZweH0ucm93IGxhYmVse3dpZHRoOjUwJX1sYWJlbHtkaXNwbGF5OmJsb2NrO2NvbG9yOiM5ZWFiYzM7Zm9udC1zaXplOjEzcHg7bWFyZ2luOjEwcHggMH1pbnB1dHtkaXNwbGF5OmJsb2NrO3dpZHRoOjEwMCU7bWFyZ2luLXRvcDo3cHg7cGFkZGluZzoxM3B4O2JvcmRlci1yYWRpdXM6MTJweDtib3JkZXI6MXB4IHNvbGlkICMzNDQxNWE7YmFja2dyb3VuZDojMGQxNDI0O2NvbG9yOndoaXRlO2ZvbnQtc2l6ZToxNnB4fS5zZWNvbmRhcnl7d2lkdGg6MTAwJTttYXJnaW4tdG9wOjEwcHh9Lmxpbmt7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtib3JkZXI6MDtjb2xvcjojNzlhMGZmfS50cmFkZXtkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47cGFkZGluZzoxMnB4IDA7Ym9yZGVyLXRvcDoxcHggc29saWQgIzI5MzQ0YTtmb250LXNpemU6MTRweH0uYnV5e2NvbG9yOiNmZjZiNzZ9LnNlbGx7Y29sb3I6IzViOWRmZn0ubXV0ZWQsLm5vdGljZXtjb2xvcjojN2Y4YWExO2ZvbnQtc2l6ZToxMnB4fS5ub3RpY2V7dGV4dC1hbGlnbjpjZW50ZXI7bGluZS1oZWlnaHQ6MS42fWNhbnZhc3t3aWR0aDoxMDAlO2JhY2tncm91bmQ6IzBlMTYyNztib3JkZXItcmFkaXVzOjEycHh9I3RvYXN0e3Bvc2l0aW9uOmZpeGVkO2xlZnQ6NTAlO2JvdHRvbToyOHB4O3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpIHRyYW5zbGF0ZVkoOTBweCk7YmFja2dyb3VuZDojZWRmMmZmO2NvbG9yOiMxMTE4Mjc7cGFkZGluZzoxMnB4IDE4cHg7Ym9yZGVyLXJhZGl1czoxMnB4O2ZvbnQtd2VpZ2h0OjcwMDt0cmFuc2l0aW9uOi4yNXM7ei1pbmRleDozfSN0b2FzdC5zaG93e3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpIHRyYW5zbGF0ZVkoMCl9Cg==",
    "app.js": "Y29uc3QgJD1zPT5kb2N1bWVudC5xdWVyeVNlbGVjdG9yKHMpO2xldCBzdGF0ZT1udWxsO2NvbnN0IG1vbmV5PW49PickJytOdW1iZXIobikudG9Mb2NhbGVTdHJpbmcoJ2VuLVVTJyx7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KTsKYXN5bmMgZnVuY3Rpb24gYXBpKHBhdGgsYm9keSl7Y29uc3Qgcj1hd2FpdCBmZXRjaChwYXRoLHttZXRob2Q6Ym9keT8nUE9TVCc6J0dFVCcsaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSxib2R5OmJvZHk/SlNPTi5zdHJpbmdpZnkoYm9keSk6bnVsbH0pO2NvbnN0IGQ9YXdhaXQgci5qc29uKCk7aWYoIXIub2spdGhyb3cgRXJyb3IoZC5lcnJvcnx8J+yalOyyrSDsi6TtjKgnKTtyZXR1cm4gZC5zdGF0ZXx8ZH0KZnVuY3Rpb24gdG9hc3QodCl7JCgnI3RvYXN0JykudGV4dENvbnRlbnQ9dDskKCcjdG9hc3QnKS5jbGFzc0xpc3QuYWRkKCdzaG93Jyk7c2V0VGltZW91dCgoKT0+JCgnI3RvYXN0JykuY2xhc3NMaXN0LnJlbW92ZSgnc2hvdycpLDE4MDApfQpmdW5jdGlvbiBkcmF3KHZhbHVlcyl7Y29uc3QgYz0kKCcjY2hhcnQnKSx4PWMuZ2V0Q29udGV4dCgnMmQnKSx3PWMud2lkdGg9Yy5jbGllbnRXaWR0aCpkZXZpY2VQaXhlbFJhdGlvLGg9Yy5oZWlnaHQ9MTUwKmRldmljZVBpeGVsUmF0aW87eC5jbGVhclJlY3QoMCwwLHcsaCk7aWYodmFsdWVzLmxlbmd0aDwyKXJldHVybjtsZXQgbWluPU1hdGgubWluKC4uLnZhbHVlcyksbWF4PU1hdGgubWF4KC4uLnZhbHVlcyksZ2FwPW1heC1taW58fDE7eC5zdHJva2VTdHlsZT0nIzVmOGNmZic7eC5saW5lV2lkdGg9MipkZXZpY2VQaXhlbFJhdGlvO3guYmVnaW5QYXRoKCk7dmFsdWVzLmZvckVhY2goKHYsaSk9PntsZXQgcHg9aS8odmFsdWVzLmxlbmd0aC0xKSp3LHB5PWgtKHYtbWluKS9nYXAqKGgqLjc1KS1oKi4xMjtpP3gubGluZVRvKHB4LHB5KTp4Lm1vdmVUbyhweCxweSl9KTt4LnN0cm9rZSgpfQpmdW5jdGlvbiByZW5kZXIocyl7c3RhdGU9czskKCcjbW9kZScpLnRleHRDb250ZW50PXMubW9kZTskKCcjc3RhdHVzJykudGV4dENvbnRlbnQ9cy5ydW5uaW5nPyfsnpHrj5kg7KSRJzon7KCV7KeAJzskKCcjc3RhdHVzJykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLHMucnVubmluZyk7JCgnI3RvZ2dsZScpLnRleHRDb250ZW50PXMucnVubmluZz8n7J6Q64+Z66ek66ekIOygleyngCc6J+yekOuPmeunpOunpCDsi5zsnpEnOyQoJyN0b2dnbGUnKS5jbGFzc0xpc3QudG9nZ2xlKCdzdG9wJyxzLnJ1bm5pbmcpOyQoJyNlcXVpdHknKS50ZXh0Q29udGVudD1tb25leShzLmVxdWl0eSk7JCgnI3Byb2ZpdCcpLnRleHRDb250ZW50PWAke3MucHJvZml0Pj0wPycrJzonJ30ke21vbmV5KHMucHJvZml0KX0gKCR7cy5wcm9maXRfcGN0fSUpYDskKCcjcHJvZml0Jykuc3R5bGUuY29sb3I9cy5wcm9maXQ+PTA/JyM1MmUzYWEnOicjZmY2Yjc2JzskKCcjcHJpY2UnKS50ZXh0Q29udGVudD1tb25leShzLnByaWNlKTskKCcjY2FzaCcpLnRleHRDb250ZW50PW1vbmV5KHMuY2FzaCk7JCgnI3F0eScpLnRleHRDb250ZW50PXMucG9zaXRpb24ucXR5Kyfso7wnOyQoJyNzaWduYWwnKS50ZXh0Q29udGVudD1zLmxhc3Rfc2lnbmFsOyQoJyNzeW1ib2wnKS50ZXh0Q29udGVudD1zLmNvbmZpZy5zeW1ib2w7ZHJhdyhzLnByaWNlcyk7T2JqZWN0LmVudHJpZXMocy5jb25maWcpLmZvckVhY2goKFtrLHZdKT0+e2xldCBlPWRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoYFtuYW1lPSR7a31dYCk7aWYoZSYmZG9jdW1lbnQuYWN0aXZlRWxlbWVudCE9PWUpZS52YWx1ZT12fSk7JCgnI3RyYWRlcycpLmlubmVySFRNTD1zLnRyYWRlcy5sZW5ndGg/cy50cmFkZXMubWFwKHQ9PmA8ZGl2IGNsYXNzPSJ0cmFkZSI+PGRpdj48YiBjbGFzcz0iJHt0LnNpZGU9PT0nQlVZJz8nYnV5Jzonc2VsbCd9Ij4ke3Quc2lkZT09PSdCVVknPyfrp6TsiJgnOifrp6Trj4QnfSAke3QucXR5feyjvDwvYj48ZGl2IGNsYXNzPSJtdXRlZCI+JHt0LnJlYXNvbn08L2Rpdj48L2Rpdj48ZGl2PiR7bW9uZXkodC5wcmljZSl9PGRpdiBjbGFzcz0ibXV0ZWQiPiR7dC50cy5zbGljZSg1LDE2KS5yZXBsYWNlKCdUJywnICcpfTwvZGl2PjwvZGl2PjwvZGl2PmApLmpvaW4oJycpOic8cCBjbGFzcz0ibXV0ZWQiPuyVhOyngSDqsbDrnpjqsIAg7JeG7Iq164uI64ukLjwvcD4nfQphc3luYyBmdW5jdGlvbiByZWZyZXNoKCl7dHJ5e3JlbmRlcihhd2FpdCBhcGkoJy9hcGkvc3RhdGUnKSl9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlKX19CiQoJyN0b2dnbGUnKS5vbmNsaWNrPWFzeW5jKCk9Pnt0cnl7cmVuZGVyKGF3YWl0IGFwaShzdGF0ZS5ydW5uaW5nPycvYXBpL3N0b3AnOicvYXBpL3N0YXJ0Jyx7fSkpO3RvYXN0KHN0YXRlLnJ1bm5pbmc/J+yekOuPmeunpOunpCDsi5zsnpEnOifsnpDrj5nrp6Trp6Qg7KCV7KeAJyl9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlKX19OwokKCcjdGljaycpLm9uY2xpY2s9YXN5bmMoKT0+e3RyeXtyZW5kZXIoYXdhaXQgYXBpKCcvYXBpL3RpY2snLHt9KSk7dG9hc3QoJ+yghOueteydhCAx7ZqMIOyLpO2Wie2WiOyWtOyalCcpfWNhdGNoKGUpe3RvYXN0KGUubWVzc2FnZSl9fTsKJCgnI3NldHRpbmdzJykub25zdWJtaXQ9YXN5bmMgZT0+e2UucHJldmVudERlZmF1bHQoKTtsZXQgZD1PYmplY3QuZnJvbUVudHJpZXMobmV3IEZvcm1EYXRhKGUudGFyZ2V0KSk7Zm9yKGxldCBrIG9mIFsnc2hvcnRfd2luZG93JywnbG9uZ193aW5kb3cnLCdwb3NpdGlvbl9wY3QnLCdkYWlseV9sb3NzX2xpbWl0X3BjdCcsJ3N0b3BfbG9zc19wY3QnLCd0YWtlX3Byb2ZpdF9wY3QnXSlkW2tdPU51bWJlcihkW2tdKTt0cnl7cmVuZGVyKGF3YWl0IGFwaSgnL2FwaS9jb25maWcnLGQpKTt0b2FzdCgn7ISk7KCV7J2EIOyggOyepe2WiOyWtOyalCcpfWNhdGNoKGUpe3RvYXN0KGUubWVzc2FnZSl9fTsKcmVmcmVzaCgpO3NldEludGVydmFsKHJlZnJlc2gsMzAwMCk7Cg==",
}
DB_PATH = Path(os.getenv("TRADER_DB", ROOT / "trader.db"))
HOST = os.getenv("TRADER_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))


@dataclass
class Config:
    symbol: str = "NASD:AAPL"
    initial_cash: float = 10_000.0
    short_window: int = 5
    long_window: int = 20
    position_pct: float = 10.0
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    daily_loss_limit_pct: float = 2.0
    poll_seconds: int = 5


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, symbol TEXT NOT NULL, price REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, side TEXT NOT NULL,
                    symbol TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, reason TEXT NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def get(self, key, default=None):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value, ensure_ascii=False)))

    def add_price(self, symbol, price):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO prices(ts,symbol,price) VALUES(?,?,?)", (now(), symbol, price))
            db.execute("DELETE FROM prices WHERE id NOT IN (SELECT id FROM prices ORDER BY id DESC LIMIT 500)")

    def prices(self, symbol, limit=100):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT price FROM prices WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit)).fetchall()
            return [float(r[0]) for r in reversed(rows)]

    def add_trade(self, side, symbol, qty, price, reason):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO trades(ts,side,symbol,qty,price,reason) VALUES(?,?,?,?,?,?)",
                       (now(), side, symbol, qty, price, reason))

    def trades(self, limit=50):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SimulatedMarket:
    """Repeatable market-like feed for safe, credential-free testing."""
    def __init__(self, store: Store):
        self.store = store
        self.rng = random.Random(20260914)

    def quote(self, symbol):
        history = self.store.prices(symbol, 1)
        last = history[-1] if history else 100.0
        drift = 0.00025
        shock = self.rng.gauss(0, 0.0035)
        return round(max(1.0, last * (1 + drift + shock)), 2)


class KISQuoteMarket:
    """KIS REST quotation feed. Orders remain safely inside PaperBroker."""
    BASE = "https://openapivts.koreainvestment.com:29443"
    EXCHANGES = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}

    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY", "")
        self.app_secret = os.getenv("KIS_APP_SECRET", "")
        self.token = ""
        self.token_expires = 0.0
        if not self.app_key or not self.app_secret:
            raise RuntimeError("KIS_APP_KEY와 KIS_APP_SECRET이 필요합니다")
        self.BASE = ("https://openapi.koreainvestment.com:9443"
                     if os.getenv("TRADING_MODE", "paper").lower() == "live" else self.BASE)

    def request(self, method, path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.BASE + path, data=body, method=method,
            headers={"Content-Type":"application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"KIS API 오류 {e.code}: {detail}") from e

    def access_token(self):
        if self.token and time.time() < self.token_expires: return self.token
        result = self.request("POST", "/oauth2/tokenP", {
            "grant_type":"client_credentials", "appkey":self.app_key, "appsecret":self.app_secret})
        self.token = result["access_token"]
        self.token_expires = time.time() + int(result.get("expires_in", 3600)) - 60
        return self.token

    def quote(self, symbol):
        market, ticker = symbol.upper().split(":", 1)
        excd = self.EXCHANGES.get(market)
        if not excd: raise ValueError("종목은 NASD:AAPL, NYSE:KO 형식으로 입력하세요")
        query = urllib.parse.urlencode({"AUTH":"", "EXCD":excd, "SYMB":ticker})
        result = self.request("GET", "/uapi/overseas-price/v1/quotations/price?" + query, headers={
            "authorization":"Bearer " + self.access_token(), "appkey":self.app_key,
            "appsecret":self.app_secret, "tr_id":"HHDFS00000300", "custtype":"P"})
        if result.get("rt_cd") not in (None, "0"): raise RuntimeError(result.get("msg1", "KIS 시세 조회 실패"))
        price = float(result.get("output", {}).get("last", 0))
        if price <= 0: raise RuntimeError("KIS 현재가 응답이 비어 있습니다")
        return price

    def hashkey(self, payload):
        result = self.request("POST", "/uapi/hashkey", payload, {
            "appkey": self.app_key, "appsecret": self.app_secret})
        value = result.get("HASH")
        if not value: raise RuntimeError("KIS 주문 해시키 생성 실패")
        return value


class KISLiveBroker:
    """Real-account broker using limit orders and hard environment safety gates."""
    def __init__(self, store, config, market):
        if os.getenv("LIVE_TRADING_ACK") != "I_UNDERSTAND_REAL_ORDERS":
            raise RuntimeError("실전 주문 확인값이 없어 시작을 차단했습니다")
        self.store, self.config, self.market = store, config, market
        self.account = os.getenv("KIS_ACCOUNT_NO", "")
        self.product = os.getenv("KIS_PRODUCT_CODE", "01")
        self.max_order_usd = float(os.getenv("MAX_ORDER_USD", "100"))
        self.pending = self.store.get("live_pending_order", None)
        if len(self.account) != 8 or not self.product:
            raise RuntimeError("KIS_ACCOUNT_NO와 KIS_PRODUCT_CODE가 필요합니다")
        if not (10 <= self.max_order_usd <= 1000):
            raise RuntimeError("MAX_ORDER_USD는 안전상 10~1000달러만 가능합니다")
        self._cache = None; self._cache_at = 0.0

    def _symbol_parts(self): return self.config.symbol.upper().split(":", 1)
    def _balance(self, force=False):
        if self._cache and not force and time.time()-self._cache_at < 5: return self._cache
        market, ticker = self._symbol_parts()
        query = urllib.parse.urlencode({"CANO":self.account, "ACNT_PRDT_CD":self.product,
            "OVRS_EXCG_CD":"NASD" if market in ("NASD","NYSE","AMEX") else market,
            "TR_CRCY_CD":"USD", "CTX_AREA_FK200":"", "CTX_AREA_NK200":""})
        result = self.market.request("GET", "/uapi/overseas-stock/v1/trading/inquire-balance?"+query, headers={
            "authorization":"Bearer "+self.market.access_token(), "appkey":self.market.app_key,
            "appsecret":self.market.app_secret, "tr_id":"TTTS3012R", "custtype":"P"})
        if result.get("rt_cd") != "0": raise RuntimeError(result.get("msg1", "실계좌 잔고 조회 실패"))
        row = next((x for x in result.get("output1", []) if x.get("ovrs_pdno") == ticker), {})
        qty = float(row.get("ovrs_cblc_qty", 0) or 0); avg = float(row.get("pchs_avg_pric", 0) or 0)
        if self.pending and ((self.pending["side"]=="BUY" and qty>0) or (self.pending["side"]=="SELL" and qty==0)):
            self.pending=None; self.store.set("live_pending_order",None)
        summary = result.get("output2", {})
        if isinstance(summary, list): summary = summary[0] if summary else {}
        cash = float(summary.get("frcr_dncl_amt_2", 0) or summary.get("frcr_dncl_amt", 0) or 0)
        self._cache={"position":{"qty":qty,"avg_price":avg},"cash":cash}; self._cache_at=time.time(); return self._cache

    @property
    def cash(self): return self._balance()["cash"]
    @property
    def position(self): return self._balance()["position"]
    def equity(self, price):
        b=self._balance(); return b["cash"]+b["position"]["qty"]*price
    def reset(self): raise RuntimeError("실계좌는 초기화할 수 없습니다")
    def _order(self, side, qty, price, reason):
        market,ticker=self._symbol_parts(); limit=round(price*(1.002 if side=="BUY" else 0.998),2)
        payload={"CANO":self.account,"ACNT_PRDT_CD":self.product,"OVRS_EXCG_CD":market,
            "PDNO":ticker,"ORD_QTY":str(int(qty)),"OVRS_ORD_UNPR":f"{limit:.2f}","CTAC_TLNO":"",
            "MGCO_APTM_ODNO":"","SLL_TYPE":"00" if side=="SELL" else "","ORD_SVR_DVSN_CD":"0","ORD_DVSN":"00"}
        tr_id="TTTT1002U" if side=="BUY" else "TTTT1006U"
        result=self.market.request("POST","/uapi/overseas-stock/v1/trading/order",payload,{
            "authorization":"Bearer "+self.market.access_token(),"appkey":self.market.app_key,
            "appsecret":self.market.app_secret,"tr_id":tr_id,"hashkey":self.market.hashkey(payload),"custtype":"P"})
        if result.get("rt_cd") != "0": raise RuntimeError(result.get("msg1","실전 주문 거절"))
        order_no=result.get("output",{}).get("ODNO","")
        self.store.add_trade(side,self.config.symbol,qty,limit,reason+(f" · 주문 {order_no}" if order_no else ""))
        self.pending={"side":side,"qty":qty,"order_no":order_no,"created_at":now()}; self.store.set("live_pending_order",self.pending)
        self._cache_at=0; return True
    def buy(self, symbol, price, reason):
        if self.pending: return False
        if self.position["qty"]>0: return False
        qty=int(min(self.cash,self.max_order_usd)/(price*1.002))
        return self._order("BUY",qty,price,reason) if qty>=1 else False
    def sell(self, symbol, price, reason):
        if self.pending: return False
        qty=int(self.position["qty"]); return self._order("SELL",qty,price,reason) if qty>=1 else False


class PaperBroker:
    def __init__(self, store: Store, config: Config):
        self.store, self.config = store, config
        if self.store.get("cash") is None:
            self.reset()

    def reset(self):
        self.store.set("cash", self.config.initial_cash)
        self.store.set("position", {"qty": 0.0, "avg_price": 0.0})
        self.store.set("day_start_equity", self.config.initial_cash)

    @property
    def cash(self): return float(self.store.get("cash", self.config.initial_cash))

    @property
    def position(self): return self.store.get("position", {"qty": 0.0, "avg_price": 0.0})

    def equity(self, price): return self.cash + self.position["qty"] * price

    def buy(self, symbol, price, reason):
        if self.position["qty"] > 0: return False
        budget = min(self.cash, self.equity(price) * self.config.position_pct / 100)
        qty = int(budget / price)
        if qty < 1: return False
        self.store.set("cash", round(self.cash - qty * price, 2))
        self.store.set("position", {"qty": qty, "avg_price": price})
        self.store.add_trade("BUY", symbol, qty, price, reason)
        return True

    def sell(self, symbol, price, reason):
        pos = self.position
        if pos["qty"] <= 0: return False
        self.store.set("cash", round(self.cash + pos["qty"] * price, 2))
        self.store.add_trade("SELL", symbol, pos["qty"], price, reason)
        self.store.set("position", {"qty": 0.0, "avg_price": 0.0})
        return True


class Engine:
    def __init__(self, store: Store):
        self.store = store
        self.config = Config(**store.get("config", {}))
        self.trading_mode = os.getenv("TRADING_MODE", "paper").lower()
        if self.trading_mode == "live" and len(os.getenv("DASHBOARD_PASSWORD", "")) < 10:
            raise RuntimeError("실전 모드는 10자 이상의 DASHBOARD_PASSWORD가 필요합니다")
        self.market_mode = os.getenv("MARKET_MODE", "simulated").lower()
        if self.trading_mode == "live":
            self.market_mode="kis_quote"; self.market=KISQuoteMarket(); self.broker=KISLiveBroker(store,self.config,self.market)
        else:
            self.market=KISQuoteMarket() if self.market_mode=="kis_quote" else SimulatedMarket(store)
            self.broker=PaperBroker(store,self.config)
        self.running = bool(store.get("running", False))
        self.stop_event = threading.Event()
        self.thread = None
        self.last_signal = "대기"

    def start(self):
        self.running = True; self.store.set("running", True)
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.loop, daemon=True); self.thread.start()

    def stop(self):
        self.running = False; self.store.set("running", False)

    def loop(self):
        while not self.stop_event.is_set():
            if self.running:
                try: self.tick()
                except Exception as e:
                    self.last_signal = f"오류: {type(e).__name__}"
                    self.stop()
            self.stop_event.wait(self.config.poll_seconds)

    def tick(self):
        c = self.config
        price = self.market.quote(c.symbol)
        self.store.add_price(c.symbol, price)
        prices = self.store.prices(c.symbol, c.long_window + 2)
        pos = self.broker.position
        equity = self.broker.equity(price)
        day_key=datetime.now(timezone.utc).date().isoformat()
        if self.trading_mode=="live" and self.store.get("equity_day")!=day_key:
            self.store.set("equity_day",day_key); self.store.set("day_start_equity",equity)
        start_eq=float(self.store.get("day_start_equity",equity if self.trading_mode=="live" else c.initial_cash) or 0)
        # A fresh live account can report 0 for the stored baseline (for example before
        # the first usable balance snapshot). Never divide by zero or kill the engine.
        if start_eq <= 0:
            if equity > 0:
                start_eq = equity
                self.store.set("day_start_equity", start_eq)
            daily_pct = 0.0
        else:
            daily_pct = (equity / start_eq - 1) * 100
        if daily_pct <= -c.daily_loss_limit_pct:
            if pos["qty"] > 0: self.broker.sell(c.symbol, price, "하루 손실 제한")
            self.last_signal = "손실 한도 도달 · 자동정지"; self.stop(); return
        if pos["qty"] > 0:
            pnl_pct = (price / pos["avg_price"] - 1) * 100
            if pnl_pct <= -c.stop_loss_pct:
                self.broker.sell(c.symbol, price, "손절"); self.last_signal = "손절 매도"; return
            if pnl_pct >= c.take_profit_pct:
                self.broker.sell(c.symbol, price, "익절"); self.last_signal = "익절 매도"; return
        if len(prices) < c.long_window + 1:
            self.last_signal = f"데이터 수집 {len(prices)}/{c.long_window + 1}"; return
        prev_short = sum(prices[-c.short_window-1:-1]) / c.short_window
        prev_long = sum(prices[-c.long_window-1:-1]) / c.long_window
        curr_short = sum(prices[-c.short_window:]) / c.short_window
        curr_long = sum(prices[-c.long_window:]) / c.long_window
        if prev_short <= prev_long and curr_short > curr_long:
            self.last_signal = "골든크로스 매수" if self.broker.buy(c.symbol, price, "이동평균 골든크로스") else "매수 조건 · 보유중"
        elif prev_short >= prev_long and curr_short < curr_long:
            self.last_signal = "데드크로스 매도" if self.broker.sell(c.symbol, price, "이동평균 데드크로스") else "매도 조건 · 미보유"
        else: self.last_signal = "조건 대기"

    def update(self, raw):
        allowed = set(asdict(Config()))
        data = {k: raw[k] for k in raw if k in allowed}
        merged = asdict(self.config); merged.update(data)
        candidate = Config(**merged)
        if not (2 <= candidate.short_window < candidate.long_window <= 200): raise ValueError("이동평균 기간을 확인하세요")
        if not (1 <= candidate.position_pct <= 25): raise ValueError("종목 투자비중은 1~25%만 가능합니다")
        if not (0.5 <= candidate.daily_loss_limit_pct <= 5): raise ValueError("하루 손실한도는 0.5~5%만 가능합니다")
        self.config = candidate; self.broker.config = candidate
        self.store.set("config", asdict(candidate))

    def state(self):
        prices = self.store.prices(self.config.symbol, 60)
        price = prices[-1] if prices else 100.0
        pos = self.broker.position
        equity = self.broker.equity(price)
        mode = "KIS 실계좌 · 실전 주문" if self.trading_mode=="live" else ("KIS 실시간 시세 · 모의주문" if self.market_mode=="kis_quote" else "가상 시세 · 모의주문")
        baseline=float(self.store.get("day_start_equity",self.config.initial_cash)) if self.trading_mode=="live" else self.config.initial_cash
        return {"running": self.running, "mode": mode, "config": asdict(self.config),
                "price": price, "prices": prices, "cash": self.broker.cash, "position": pos,
                "equity": round(equity, 2), "profit": round(equity-baseline, 2),
                "profit_pct": round((equity/baseline-1)*100, 2) if baseline else 0,
                "last_signal": self.last_signal, "trades": self.store.trades(30)}


STORE = Store(DB_PATH)
ENGINE = Engine(STORE)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def authenticated(self):
        password=os.getenv("DASHBOARD_PASSWORD","")
        if not password: return True
        expected="Basic "+base64.b64encode(("owner:"+password).encode()).decode()
        if self.headers.get("Authorization")==expected: return True
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="Sajangnim Trader"'); self.end_headers(); return False
    def send_json(self, value, code=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.authenticated(): return
        path = urlparse(self.path).path
        if path == "/api/state": return self.send_json(ENGINE.state())
        if path == "/api/health": return self.send_json({"ok": True, "time": now()})
        file = ROOT / "web" / ("index.html" if path == "/" else path.lstrip("/"))
        if not file.is_file() or ROOT / "web" not in file.parents:
            name = "index.html" if path == "/" else path.lstrip("/")
            encoded = EMBEDDED_WEB.get(name)
            if not encoded: return self.send_json({"error":"not found"}, 404)
            body = base64.b64decode(encoded)
            mime = "text/html" if name.endswith(".html") else "text/css" if name.endswith(".css") else "application/javascript"
            self.send_response(200); self.send_header("Content-Type", mime+"; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        mime = "text/html" if file.suffix == ".html" else "text/css" if file.suffix == ".css" else "application/javascript"
        body = file.read_bytes(); self.send_response(200); self.send_header("Content-Type", mime+"; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if not self.authenticated(): return
        try:
            n = int(self.headers.get("Content-Length", "0")); raw = json.loads(self.rfile.read(n) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/start": ENGINE.start()
            elif path == "/api/stop": ENGINE.stop()
            elif path == "/api/tick": ENGINE.tick()
            elif path == "/api/config": ENGINE.update(raw)
            elif path == "/api/reset":
                if ENGINE.trading_mode == "live": raise ValueError("실계좌는 초기화할 수 없습니다")
                ENGINE.stop(); ENGINE.broker.reset()
            else: return self.send_json({"error":"not found"}, 404)
            self.send_json({"ok": True, "state": ENGINE.state()})
        except (ValueError, TypeError, json.JSONDecodeError, RuntimeError, ZeroDivisionError) as e:
            # Return API errors to the dashboard instead of dropping the HTTP request.
            self.send_json({"error": str(e)}, 400)


def main():
    if ENGINE.running: ENGINE.start()
    print(f"사장님 자동매매: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__": main()
