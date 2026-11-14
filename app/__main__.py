#!/bin/env python3
from http.server import test, SimpleHTTPRequestHandler
from functools import partial

test(HandlerClass=partial(SimpleHTTPRequestHandler,
     directory="./app/static"), port=8080, bind="127.0.0.1")
