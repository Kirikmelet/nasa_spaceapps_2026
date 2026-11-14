#!/bin/env python3

import threading
from functools import partial
import http.server as hp

if __name__ == "__main__":
    handler = partial(hp.SimpleHTTPRequestHandler, directory="static/")
    server = hp.ThreadingHTTPServer(("", 8080), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pass
