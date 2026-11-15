#!/bin/sh

cd app/ && python -m uvicorn main:app --reload && cd ..
    
