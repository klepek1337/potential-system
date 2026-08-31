[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:USERPROFILE "Cryptostrata"),
    [switch]$SkipTests,
    [switch]$RunOnce,
    [ValidateSet("Ask", "Abort", "Stash", "Discard")]
    [string]$LocalChangesAction = "Ask"
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
$LocalChangesActionAsk = "Ask"
$LocalChangesActionAbort = "Abort"
$LocalChangesActionStash = "Stash"
$LocalChangesActionDiscard = "Discard"
$LocalChangesChoiceAbort = "A"
$LocalChangesChoiceStash = "S"
$LocalChangesChoiceDiscard = "D"

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory)][string]$CommandName)
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Brak wymaganej komendy '$CommandName'. Zainstaluj ja i uruchom skrypt ponownie."
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
        throw "Komenda Python zakonczyla sie kodem $LASTEXITCODE."
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
    throw "Cryptostrata juz dziala (PID: $ProcessIdentifiers). Zatrzymaj stara instancje przed aktualizacja."
}

function Select-LocalChangesAction {
    param([Parameter(Mandatory)][string]$ConfiguredAction)

    if ($ConfiguredAction -ne $LocalChangesActionAsk) {
        return $ConfiguredAction
    }

    Write-Warning "Repozytorium ma lokalne zmiany nieuwzglednione przez .gitignore."
    git status --short
    Write-Host "[$LocalChangesChoiceAbort] Abort - przerwij bez zmian"
    Write-Host "[$LocalChangesChoiceStash] Stash - zachowaj zmiany w git stash"
    Write-Host "[$LocalChangesChoiceDiscard] Discard - usun sledzone i nieignorowane zmiany"
    while ($true) {
        $SelectedChoice = (Read-Host "Wybierz A, S albo D").Trim().ToUpperInvariant()
        if ($SelectedChoice -eq $LocalChangesChoiceAbort) {
            return $LocalChangesActionAbort
        }
        if ($SelectedChoice -eq $LocalChangesChoiceStash) {
            return $LocalChangesActionStash
        }
        if ($SelectedChoice -eq $LocalChangesChoiceDiscard) {
            return $LocalChangesActionDiscard
        }
        Write-Warning "Nieprawidlowy wybor."
    }
}

function Resolve-LocalChanges {
    param([Parameter(Mandatory)][string]$ConfiguredAction)

    $SelectedAction = Select-LocalChangesAction -ConfiguredAction $ConfiguredAction
    if ($SelectedAction -eq $LocalChangesActionAbort) {
        throw "Aktualizacja przerwana. Lokalne zmiany pozostaly nietkniete."
    }
    if ($SelectedAction -eq $LocalChangesActionStash) {
        Write-Step "Zapisuje lokalne zmiany w git stash"
        git stash push --include-untracked --message "Cryptostrata automatic update"
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udalo sie zapisac lokalnych zmian w git stash."
        }
        return
    }
    if ($SelectedAction -eq $LocalChangesActionDiscard) {
        Write-Step "Usuwam sledzone i nieignorowane lokalne zmiany"
        git reset --hard HEAD
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udalo sie przywrocic sledzonych plikow."
        }
        git clean -fd
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udalo sie usunac nieignorowanych plikow."
        }
        return
    }
    throw "Nieobslugiwana akcja dla lokalnych zmian: $SelectedAction"
}

function Update-Repository {
    param(
        [Parameter(Mandatory)][string]$RepositoryDirectory,
        [Parameter(Mandatory)][string]$ConfiguredLocalChangesAction
    )

    if (-not (Test-Path $RepositoryDirectory)) {
        Write-Step "Pobieram repozytorium"
        git clone --branch $MainBranchName --single-branch $RepositoryUrl $RepositoryDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udalo sie sklonowac repozytorium."
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
            Resolve-LocalChanges -ConfiguredAction $ConfiguredLocalChangesAction
        }

        Write-Step "Aktualizuje czysty branch main"
        git switch $MainBranchName
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udalo sie przelaczyc na branch main."
        }
        git pull --ff-only origin $MainBranchName
        if ($LASTEXITCODE -ne 0) {
            throw "Aktualizacja main nie jest fast-forward. Sprawdz historie repozytorium."
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
Update-Repository `
    -RepositoryDirectory $InstallDirectory `
    -ConfiguredLocalChangesAction $LocalChangesAction

Set-Location $InstallDirectory
$VirtualEnvironmentDirectory = Join-Path $InstallDirectory $VirtualEnvironmentDirectoryName
$VirtualEnvironmentPython = Join-Path $VirtualEnvironmentDirectory "Scripts\python.exe"

if (-not (Test-Path $VirtualEnvironmentPython)) {
    Write-Step "Tworze srodowisko Python"
    Invoke-Python -PythonCommand $SystemPythonCommand -Arguments @("-m", "venv", $VirtualEnvironmentDirectory)
}

Write-Step "Instaluje zaleznosci"
& $VirtualEnvironmentPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Instalacja zaleznosci nie powiodla sie."
}

$EnvironmentFilePath = Join-Path $InstallDirectory $EnvironmentFileName
if (-not (Test-Path $EnvironmentFilePath)) {
    Copy-Item $EnvironmentTemplateFileName $EnvironmentFilePath
    Write-Warning "Utworzono .env. Uzupelnij Telegram token/chat ID i ustaw DRY_RUN=false, gdy bedziesz gotowy."
    Start-Process notepad.exe -ArgumentList $EnvironmentFilePath -Wait
}

if (-not $SkipTests) {
    Write-Step "Sprawdzam instalacje testami"
    & $VirtualEnvironmentPython -m unittest discover -v
    if ($LASTEXITCODE -ne 0) {
        throw "Testy nie przeszly. Bot nie zostanie uruchomiony."
    }
}

Write-Step "Uruchamiam Cryptostrate"
$BotArguments = @("-m", "ma_alert_bot")
if ($RunOnce) {
    $BotArguments += "--once"
}
& $VirtualEnvironmentPython @BotArguments
