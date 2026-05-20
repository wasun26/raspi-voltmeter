# Complete setup script for Windows development
# Run: powershell -ExecutionPolicy Bypass -File setup.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "PyQt Voltmeter - Windows Dev Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check Python
Write-Host "`n[1/3] Checking Python installation..." -ForegroundColor Yellow
$pythonPath = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ $pythonPath"
} else {
    Write-Host "✗ Python not found. Please install Python 3.9+" -ForegroundColor Red
    exit 1
}

# Create venv
Write-Host "`n[2/3] Creating Python virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "✓ Virtual environment already exists"
} else {
    python -m venv .venv
    Write-Host "✓ Virtual environment created"
}

# Install dependencies
Write-Host "`n[3/3] Installing Python packages..." -ForegroundColor Yellow

# Activate venv
& ".venv\Scripts\Activate.ps1"

# Upgrade pip
python -m pip install --upgrade pip

# Install from requirements
pip install -r requirements.txt

Write-Host "`n" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "✓ Setup complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Run terminal monitor with mock ADC:"
Write-Host "   python serial_monitor.py --mock --rate 5 --count 5"
Write-Host ""
Write-Host "2. Run the GUI:"
Write-Host "   python main.py"
Write-Host ""
Write-Host "3. To run on Raspberry Pi, copy project folder and:"
Write-Host "   bash setup.sh"
Write-Host ""
