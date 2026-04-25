#!/bin/bash
# Orbit Project - Quick Setup & Run Script for macOS/Linux

set -e

echo "======================================"
echo "Orbit Project - macOS/Linux Setup"
echo "======================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
NODE_VERSION=$(node --version 2>&1)
NPM_VERSION=$(npm --version 2>&1)

echo -e "${GREEN}Project Root: $PROJECT_ROOT${NC}"
echo "Python: $PYTHON_VERSION"
echo "Node.js: $NODE_VERSION"
echo "npm: $NPM_VERSION"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Download from: https://www.python.org/downloads/"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed${NC}"
    echo "Download from: https://nodejs.org/"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is not installed${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Setting up Python virtual environment...${NC}"
if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    python3 -m venv "$PROJECT_ROOT/.venv"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

echo ""
echo -e "${YELLOW}Step 2: Activating virtual environment...${NC}"
source "$PROJECT_ROOT/.venv/bin/activate"
echo -e "${GREEN}✓ Virtual environment activated${NC}"

echo ""
echo -e "${YELLOW}Step 3: Installing Python dependencies...${NC}"

uv pip install -q -r "$PROJECT_ROOT/requirements.txt"
echo -e "${GREEN}✓ Python dependencies installed${NC}"

echo ""
echo -e "${YELLOW}Step 4: Installing Node.js dependencies...${NC}"
cd "../web"
npm install --silent
echo -e "${GREEN}✓ Node.js dependencies installed${NC}"

cd "$PROJECT_ROOT"

echo ""
echo -e "${GREEN}======================================"
echo "Setup Complete!"
echo "======================================${NC}"
echo ""
echo "Next steps:"
echo "1. Open Terminal 1 and run:"
echo "   cd $PROJECT_ROOT"
echo "   source .venv/bin/activate"
echo "   cd app"
echo "   python main.py"
echo ""
echo "2. Open Terminal 2 and run:"
echo "   cd $PROJECT_ROOT/web"
echo "   npm run dev"
echo ""
echo "3. Open browser to http://localhost:5173"
echo ""
echo "Demo credentials:"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
