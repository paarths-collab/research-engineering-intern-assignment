#!/bin/bash

echo "🔬 Shock Response Analyzer - Quick Start"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✓ Python 3 found"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✓ Dependencies installed"

# Start the server
echo ""
echo "🚀 Starting FastAPI server..."
echo ""
echo "Server will be available at: http://localhost:8000"
echo "Open index.html in your browser to use the application"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python3 main.py
