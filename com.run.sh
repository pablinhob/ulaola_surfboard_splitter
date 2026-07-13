#!/usr/bin/env bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating it..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ] && [ -s "requirements.txt" ]; then
    pip install -q -r requirements.txt
fi

python -m app.main
