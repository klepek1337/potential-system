[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:USERPROFILE "Cryptostrata"),
    [switch]$SkipTests,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"
$RepositoryUrl = "https://github.com/klepek1337/potential-system.git"
$ExpectedOriginUrl = $RepositoryUrl
$MainBranchName = "main"
$VirtualEnvironmentDirectoryName = ".venv"
$EnvironmentFileName = ".env"
$EnvironmentTemplateFileName = ".env.example"
$MinimumPythonMajorVersion = 3
$MinimumPythonMinorVersion = 11

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory)][string]$CommandName)
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Brak wymaganej komendy '$CommandName'. Zainstaluj ją i uruchom skrypt ponownie."
    }
}

function Get-PythonCommand {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        return @("py", "-3.11")
    }
    if (Get-Command "python" -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Nie znaleziono Pythona 3.11+. Zainstaluj go z https://www.python.org/downloads/windows/."
}

function Invoke-Python {
    param(
        [Parameter(Mandatory)][string[]]$PythonCommand,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    $Executable = $PythonCommand[0]
    $PrefixArguments = @($PythonCommand | Select-Object -Skip 1)
    & $Executable @PrefixArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Komenda Python zakończyła się kodem $LASTEXITCODE."
    }
}

function Assert-SupportedPythonVersion {
    param([Parameter(Mandatory)][string[]]$PythonCommand)
    $VersionCheck = "import sys; raise SystemExit(0 if sys.version_info >= ($MinimumPythonMajorVersion, $MinimumPythonMinorVersion) else 1)"
    Invoke-Python -PythonCommand $PythonCommand -Arguments @("-c", $VersionCheck)
}

function Assert-BotNotRunning {
    $RunningBotProcesses = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match "^python(?:w)?\.exe$" -and
            $_.CommandLine -match "(?:^|\s)-m\s+ma_alert_bot(?:\s|$)"
        }
    )
    if ($RunningBotProcesses.Count -eq 0) {
        return
    }

    $ProcessIdentifiers = ($RunningBotProcesses.ProcessId -join ", ")
    throw "Cryptostrata już działa (PID: $ProcessIdentifiers). Zatrzymaj starą instancję przed aktualizacją."
}

function Update-Repository {
    param([Parameter(Mandatory)][string]$RepositoryDirectory)

    if (-not (Test-Path $RepositoryDirectory)) {
        Write-Step "Pobieram repozytorium"
        git clone --branch $MainBranchName --single-branch $RepositoryUrl $RepositoryDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udało się sklonować repozytorium."
        }
        return
    }

    if (-not (Test-Path (Join-Path $RepositoryDirectory ".git"))) {
        throw "Katalog '$RepositoryDirectory' istnieje, ale nie jest repozytorium Git."
    }

    Push-Location $RepositoryDirectory
    try {
        $OriginUrl = (git remote get-url origin).Trim()
        if ($LASTEXITCODE -ne 0 -or $OriginUrl -ne $ExpectedOriginUrl) {
            throw "Repozytorium ma nieoczekiwany origin: '$OriginUrl'."
        }

        $LocalChanges = git status --porcelain
        if ($LocalChanges) {
            throw "Repozytorium ma lokalne zmiany. Zapisz je w commit/stash albo usuń ręcznie przed aktualizacją."
        }

        Write-Step "Aktualizuję czysty branch main"
        git switch $MainBranchName
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udało się przełączyć na branch main."
        }
        git pull --ff-only origin $MainBranchName
        if ($LASTEXITCODE -ne 0) {
            throw "Aktualizacja main nie jest fast-forward. Sprawdź historię repozytorium."
        }
    }
    finally {
        Pop-Location
    }
}

Assert-CommandAvailable -CommandName "git"
$SystemPythonCommand = Get-PythonCommand
Assert-SupportedPythonVersion -PythonCommand $SystemPythonCommand
Assert-BotNotRunning
Update-Repository -RepositoryDirectory $InstallDirectory

Set-Location $InstallDirectory
$VirtualEnvironmentDirectory = Join-Path $InstallDirectory $VirtualEnvironmentDirectoryName
$VirtualEnvironmentPython = Join-Path $VirtualEnvironmentDirectory "Scripts\python.exe"

if (-not (Test-Path $VirtualEnvironmentPython)) {
    Write-Step "Tworzę środowisko Python"
    Invoke-Python -PythonCommand $SystemPythonCommand -Arguments @("-m", "venv", $VirtualEnvironmentDirectory)
}

Write-Step "Instaluję zależności"
& $VirtualEnvironmentPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Instalacja zależności nie powiodła się."
}

$EnvironmentFilePath = Join-Path $InstallDirectory $EnvironmentFileName
if (-not (Test-Path $EnvironmentFilePath)) {
    Copy-Item $EnvironmentTemplateFileName $EnvironmentFilePath
    Write-Warning "Utworzono .env. Uzupełnij Telegram token/chat ID i ustaw DRY_RUN=false, gdy będziesz gotowy."
    Start-Process notepad.exe -ArgumentList $EnvironmentFilePath -Wait
}

if (-not $SkipTests) {
    Write-Step "Sprawdzam instalację testami"
    & $VirtualEnvironmentPython -m unittest discover -v
    if ($LASTEXITCODE -ne 0) {
        throw "Testy nie przeszły. Bot nie zostanie uruchomiony."
    }
}

Write-Step "Uruchamiam Cryptostratę"
$BotArguments = @("-m", "ma_alert_bot")
if ($RunOnce) {
    $BotArguments += "--once"
}
& $VirtualEnvironmentPython @BotArguments
