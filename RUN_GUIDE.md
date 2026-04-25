# Orbit Project - Complete Setup & Run Guide

## 🚀 Project Overview

Orbit is a full-stack application with:
- **Backend**: Python FastAPI application (in `app/` folder)
- **Frontend**: React + TypeScript + Vite application (in `web/` folder)

### Key Features:
- User Authentication (Login & Registration)
- Chat/Conversation Management
- Multi-Agent AI System
- Dashboard & Analytics

---

## 📋 Prerequisites

### For All Users:
- **Git** (for version control)
- **Node.js** (v16 or higher) - [Download](https://nodejs.org/)
- **Python** (v3.10 or higher) - [Download](https://www.python.org/downloads/)
- **npm** (comes with Node.js)

### Verify Installation:
```bash
node --version
python3 --version
npm --version
```

---

## 🛠️ Initial Setup (Both Mac & Windows)

### Step 1: Navigate to Project Root
```bash
cd path/to/orbit
```

### Step 2: Set Up Backend Environment

#### Mac/Linux:
```bash
# Create Python virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r app/requirements.txt

# Initialize database (if needed)
cd app
python db/init_db.py
cd ..
```

#### Windows:
```bash
# Create Python virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install -r app/requirements.txt

# Initialize database (if needed)
cd app
python db/init_db.py
cd ..
```

### Step 3: Set Up Frontend Environment
```bash
# Navigate to web folder
cd web

# Install dependencies
npm install

# Return to root
cd ..
```

---

## 🚀 Running the Application

### Option 1: Quick Start (Recommended for Development)

#### Mac/Linux:

Open **Terminal 1** - Backend:
```bash
cd /path/to/orbit
source .venv/bin/activate
cd app
python main.py
```

Open **Terminal 2** - Frontend:
```bash
cd /path/to/orbit/web
npm run dev
```

#### Windows:

Open **Command Prompt/PowerShell 1** - Backend:
```bash
cd path\to\orbit
.venv\Scripts\activate
cd app
python main.py
```

Open **Command Prompt/PowerShell 2** - Frontend:
```bash
cd path\to\orbit\web
npm run dev
```

### Option 2: Using VS Code Terminal

1. Open the project in VS Code
2. Press `Ctrl + ~` to open integrated terminal
3. Split terminal: Click the split button
4. In **Terminal 1** (Backend):
   ```bash
   source .venv/bin/activate  # Mac/Linux
   # OR
   .venv\Scripts\activate     # Windows
   
   cd app
   python main.py
   ```
5. In **Terminal 2** (Frontend):
   ```bash
   cd web
   npm run dev
   ```

---

## 📍 Access the Application

Once both services are running:

- **Frontend**: http://localhost:5173 (or shown in terminal)
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs (Swagger UI)

---

## 🔐 Authentication - Login & Registration

### Demo Credentials:
```
Username: admin
Password: admin123
```

### Create New Account:
1. Click "New to the platform? Create account" on login page
2. Enter:
   - Username (min 3 characters)
   - Email (valid email address)
   - Password (must meet strength requirements):
     - At least 8 characters
     - 1 uppercase letter
     - 1 lowercase letter
     - 1 number
     - 1 special character (!@#$%^&*)
   - Confirm password
3. Click "Create Account"
4. You'll be directed to login
5. Use your credentials to login

### Login:
1. Enter username and password
2. (Optional) Check "Remember me" to save refresh token
3. Click "Secure Access"

---

## 🧪 Testing the Application

### Test Backend API:

#### Using cURL (Mac/Linux):

```bash
# Check API health
curl http://localhost:8000/docs

# Register new user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Test123!@#",
    "email": "test@example.com",
    "role": "USER"
  }'

# Login
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

#### Using cURL (Windows - PowerShell):
```powershell
# Check API health
curl.exe http://localhost:8000/docs

# Register new user
curl.exe -X POST "http://localhost:8000/auth/register" `
  -H "Content-Type: application/json" `
  -d '{
    "username": "testuser",
    "password": "Test123!@#",
    "email": "test@example.com",
    "role": "USER"
  }'

# Login
curl.exe -X POST "http://localhost:8000/auth/login" `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin&password=admin123"
```

### Test Frontend:
1. Open http://localhost:5173
2. You should see login page
3. Enter demo credentials (admin / admin123)
4. You should be logged in and see the dashboard

---

## 🔧 Troubleshooting

### Backend Issues:

#### Port 8000 Already in Use:
```bash
# Mac/Linux - Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Windows - Find process on port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

#### Database Lock Error:
```bash
# Remove database lock files
rm -f app/*.db-shm app/*.db-wal

# Windows
del app\*.db-shm app\*.db-wal
```

#### Import Errors:
```bash
# Reinstall requirements
source .venv/bin/activate  # Mac/Linux
# OR
.venv\Scripts\activate     # Windows

pip install --upgrade -r app/requirements.txt
```

### Frontend Issues:

#### Port 5173 Already in Use:
```bash
# The Vite dev server will automatically try port 5174, 5175, etc.
# Or specify custom port:
npm run dev -- --port 3000
```

#### Module Not Found Errors:
```bash
cd web
rm -rf node_modules package-lock.json  # Mac/Linux
# OR
rmdir /s node_modules                   # Windows
del package-lock.json

npm install
npm run dev
```

#### Blank White Page:
1. Check browser console (F12)
2. Check if backend is running on http://localhost:8000
3. Clear browser cache (Ctrl/Cmd + Shift + Delete)
4. Hard refresh (Ctrl/Cmd + Shift + R)

### Common CORS Errors:
- Ensure backend is running before starting frontend
- Backend CORS is configured to accept `*` (all origins)
- If issues persist, check backend console for errors

---

## 📦 Building for Production

### Backend:
Backend runs as-is. For production deployment, use:
```bash
# Using gunicorn (install first: pip install gunicorn)
gunicorn -w 4 -b 0.0.0.0:8000 app.main:app
```

### Frontend:
```bash
cd web

# Build for production
npm run build

# Output will be in web/dist/ folder
# Serve with: npm run preview
npm run preview
```

---

## 🆘 Quick Reference Commands

### Starting Everything:

**Mac/Linux:**
```bash
# Terminal 1 - Backend
cd /path/to/orbit && source .venv/bin/activate && cd app && python main.py

# Terminal 2 - Frontend
cd /path/to/orbit/web && npm run dev
```

**Windows:**
```bash
# Command Prompt 1 - Backend
cd path\to\orbit && .venv\Scripts\activate && cd app && python main.py

# Command Prompt 2 - Frontend
cd path\to\orbit\web && npm run dev
```

### Stopping Services:
- Backend: `Ctrl + C` in backend terminal
- Frontend: `Ctrl + C` in frontend terminal

### Restarting:
Just use the above commands again

---

## 📚 Additional Resources

- **FastAPI Docs**: http://localhost:8000/docs
- **React Docs**: https://react.dev
- **Vite Docs**: https://vitejs.dev
- **TypeScript Docs**: https://www.typescriptlang.org

---

## 🤝 Support

For issues or questions:
1. Check troubleshooting section above
2. Review console output for error messages
3. Check browser DevTools console (F12)
4. Review backend logs in terminal

---

**Last Updated**: April 23, 2026
**Version**: 1.0
