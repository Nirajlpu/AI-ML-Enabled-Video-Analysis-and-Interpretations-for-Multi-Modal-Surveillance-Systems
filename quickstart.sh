#!/bin/bash

# VisionIQ Quick-Start Script
# This script sets up and starts both backend and frontend

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}VisionIQ - Quick Start${NC}"
echo -e "${GREEN}========================================${NC}"

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if we're in the right directory
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}Error: backend and frontend directories not found!${NC}"
    echo "Please run this script from the VisionIQ root directory."
    exit 1
fi

# Backend Setup
echo -e "\n${YELLOW}=== Setting up BACKEND ===${NC}"
cd backend

# Check Python
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 is not installed!${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

# Create and activate virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Copy .env if not present
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠ Created .env from .env.example - please update DATABASE_URL${NC}"
    fi
fi

# Install dependencies
echo "Installing backend dependencies..."
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Verify model availability
echo "Checking YOLO models..."
if [ ! -f "yolo11n.pt" ] && [ ! -f "yolov8m.pt" ] && [ ! -f "yolov8n.pt" ]; then
    echo -e "${YELLOW}⚠ No YOLO model found locally. It will be downloaded on first use.${NC}"
else
    echo -e "${GREEN}✓ YOLO model found${NC}"
fi

# Frontend Setup
echo -e "\n${YELLOW}=== Setting up FRONTEND ===${NC}"
cd ../frontend

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}Node.js is not installed!${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js $NODE_VERSION found${NC}"

# Install dependencies
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Frontend dependencies already installed${NC}"
fi

# Create .env.local if needed
if [ ! -f ".env.local" ]; then
    echo "VITE_API_URL=http://localhost:5001" > .env.local
    echo -e "${GREEN}✓ Created .env.local${NC}"
fi

# Final instructions
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Next steps:${NC}"
echo ""
echo -e "1. ${GREEN}Start Backend:${NC}"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python app.py"
echo ""
echo -e "2. ${GREEN}In a new terminal, start Frontend:${NC}"
echo "   cd frontend"
echo "   npm run dev"
echo ""
echo -e "3. ${GREEN}Open your browser:${NC}"
echo "   http://localhost:5173"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "   - Backend env: backend/.env"
echo "   - Frontend env: frontend/.env.local"
echo "   - Setup guide: SETUP_AND_DEPLOYMENT.md"
echo ""
echo -e "${YELLOW}First-time setup:${NC}"
echo "   - Update DATABASE_URL in backend/.env with your PostgreSQL URL"
echo "   - Ensure PORT 5001 (backend) and 5173 (frontend) are available"
echo "   - YOLO models will auto-download on first use (~50-100 MB)"
echo ""
