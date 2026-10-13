@echo off
rem ===========================================================================
rem  Packaging.bat - build the onedir bundle and wrap it into setup.exe
rem
rem  Usage (double-clicking also works):
rem     Packaging.bat            pre-flight + uv sync + PyInstaller + self-check + Inno Setup
rem     Packaging.bat /nobuild   reuse the existing dist\mcwr (quick re-package)
rem     Packaging.bat /nosync    skip "uv sync" (and the running-app pre-flight)
rem     Packaging.bat /fast      lzma2/fast instead of lzma2/max (bigger, much quicker)
rem     Packaging.bat /verify    also install the result silently into a temp folder,
rem                              run the installed --self-check, then uninstall again
rem
rem  It refuses to start while mcwr.exe is running: Windows keeps the venv launcher locked, so
rem  "uv sync" would fail with "Access is denied" (ERRORS.md E-025). Close the app first - the
rem  installed build, dist\mcwr\mcwr.exe and a source-started window all count. /nosync skips
rem  both the check and the sync.
rem
rem  Nothing about the project is hardcoded here: the version is read from
rem  src\mcwr\__init__.py and cross-checked against pyproject.toml, every path is derived
rem  from this file's own location, and ISCC.exe is looked up (MCWR_ISCC, PATH, registry,
rem  usual install folders). Re-running it after changing the project is the normal flow.
rem
rem  Messages are ASCII on purpose: a .bat is read in the console codepage, and non-ASCII
rem  text here turns into mojibake on machines whose codepage differs (see README, Chinese).
rem ===========================================================================

setlocal EnableExtensions
set "HERE=%~dp0"
pushd "%HERE%" || (echo [x] cannot enter "%HERE%" & exit /b 1)

set "DO_BUILD=1"
set "DO_SYNC=1"
set "FAST="
set "VERIFY="

:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="/nobuild" set "DO_BUILD=0"
if /i "%~1"=="/nosync"  set "DO_SYNC=0"
if /i "%~1"=="/fast"    set "FAST=/DFAST"
if /i "%~1"=="/verify"  set "VERIFY=1"
if /i "%~1"=="/?" (
  echo Usage: Packaging.bat [/nobuild] [/nosync] [/fast] [/verify]
  popd & exit /b 0
)
shift
goto :parse
:parsed

rem --------------------------------------------------------------- interpreter
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py -3.12" )
if not defined PY (
  echo [x] Python not found. Install Python 3.12 and make sure "python" or "py" is on PATH.
  goto :fail
)

%PY% -c "import sys;sys.exit(0 if sys.version_info[:2]>=(3,12) else 1)" || (
  echo [x] Python 3.12 or newer is required.
  goto :fail
)
%PY% -m uv --version >nul 2>&1 || (
  echo [x] uv is not installed for %PY% - run:  %PY% -m pip install uv
  goto :fail
)

rem ------------------------------------ pre-flight: the app must not be running (E-025)
if "%DO_SYNC%"=="1" (
  set "RUNNING="
  for /f "delims=" %%p in ('tasklist /fi "imagename eq mcwr.exe" /nh /fo csv 2^>nul ^| findstr /i "mcwr.exe"') do set "RUNNING=1"
  if defined RUNNING (
    echo [x] mcwr.exe is running - close it, then run Packaging.bat again.
    echo     While the app runs, Windows keeps .venv\Scripts\mcwr.exe locked and "uv sync"
    echo     fails with "Access is denied" ^(ERRORS.md E-025^).
    echo     Close the installed build, dist\mcwr\mcwr.exe or a source-started window;
    echo     /nosync packages without touching the environment.
    goto :fail
  )
  echo       pre-flight: no running mcwr.exe
)

rem ------------------------------------------------------- version (one source)
echo [1/5] reading the project version
%PY% -c "import sys;sys.path.insert(0,'src');import mcwr;print(mcwr.__version__)" > "%TEMP%\mcwr_version.txt" || (
  echo [x] cannot import mcwr from src\ - is this the project root?
  goto :fail
)
set /p APPVERSION=<"%TEMP%\mcwr_version.txt"
del "%TEMP%\mcwr_version.txt" >nul 2>&1
if not defined APPVERSION (
  echo [x] src\mcwr\__init__.py has no usable __version__.
  goto :fail
)
%PY% -c "import pathlib,sys;sys.path.insert(0,'src');import mcwr;t=pathlib.Path('pyproject.toml').read_text(encoding='utf-8');v=[l.split('=',1)[1].strip().strip(chr(34)) for l in t.splitlines() if l.strip().startswith('version')][0];sys.exit(0 if v==mcwr.__version__ else 3)" || (
  echo [x] version mismatch between src\mcwr\__init__.py and pyproject.toml - fix it first.
  goto :fail
)
echo       version %APPVERSION%

rem ------------------------------------------------------------------- bundle
if "%DO_SYNC%"=="1" (
  echo [2/5] uv sync
  %PY% -m uv sync || ( echo [x] uv sync failed & goto :fail )
) else (
  echo [2/5] /nosync: keeping the current environment
)

if "%DO_BUILD%"=="1" (
  echo [3/5] PyInstaller onedir  ^(wipes build\ and dist\mcwr first^)
  if exist "build" rmdir /s /q "build"
  if exist "dist\mcwr" rmdir /s /q "dist\mcwr"
  %PY% -m uv run pyinstaller packaging\mcwr.spec --noconfirm || ( echo [x] PyInstaller failed & goto :fail )
) else (
  echo [3/5] /nobuild: reusing the existing dist\mcwr
)

if not exist "dist\mcwr\mcwr.exe" (
  echo [x] dist\mcwr\mcwr.exe is missing - drop /nobuild to build it.
  goto :fail
)

echo [4/5] delivery-form self-check  ^(opens a generated document, renders math+mermaid^)
"dist\mcwr\mcwr.exe" --self-check || ( echo [x] the frozen bundle failed its self-check & goto :fail )

rem --------------------------------------------------------------------- ISCC
set "ISCC="
if defined MCWR_ISCC if exist "%MCWR_ISCC%" set "ISCC=%MCWR_ISCC%"
if not defined ISCC for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%i"
if not defined ISCC for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v InstallLocation 2^>nul ^| findstr /i InstallLocation') do if not defined ISCC if exist "%%b\ISCC.exe" set "ISCC=%%b\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [x] ISCC.exe not found. Install Inno Setup 6, or point MCWR_ISCC at it.
  goto :fail
)
echo       compiler "%ISCC%"

rem ------------------------------------------------------------------ installer
echo [5/5] Inno Setup: mcwr-setup-%APPVERSION%.exe
if exist "packaging\Output" del /q "packaging\Output\mcwr-setup-*.exe" >nul 2>&1
"%ISCC%" /Qp %FAST% /DAppVersion=%APPVERSION% /DAppVersionQuad=%APPVERSION%.0 "packaging\mcwr-installer.iss" || (
  echo [x] Inno Setup failed - see the messages above.
  goto :fail
)
set "SETUP=packaging\Output\mcwr-setup-%APPVERSION%.exe"
if not exist "%SETUP%" (
  echo [x] %SETUP% was not produced.
  goto :fail
)
for %%f in ("%SETUP%") do echo [ok] %%~ff  ^(%%~zf bytes^)

rem ------------------------------------------------------------------- /verify
if not defined VERIFY goto :done
echo [verify] silent install into "%TEMP%\mcwr-verify" ^(no UAC: per-user install^)
set "TARGET=%TEMP%\mcwr-verify"
if exist "%TARGET%" rmdir /s /q "%TARGET%"
"%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /DIR="%TARGET%" /LOG="%TEMP%\mcwr-verify-install.log" || (
  echo [x] silent install failed ^(log: %TEMP%\mcwr-verify-install.log^)
  goto :fail
)
"%TARGET%\mcwr.exe" --self-check || ( echo [x] the installed copy failed its self-check & goto :fail )
echo [verify] uninstalling again
ping -n 3 127.0.0.1 >nul
if exist "%TARGET%\unins000.exe" (
  "%TARGET%\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART || echo [!] uninstaller returned non-zero
)
ping -n 3 127.0.0.1 >nul
if exist "%TARGET%\mcwr.exe" echo [!] "%TARGET%" still holds files - check manually
if not exist "%TARGET%\mcwr.exe" echo [verify] install + self-check + uninstall OK

:done
echo.
echo [ok] Packaging finished.
echo      Installer: "%CD%\%SETUP%"
echo      Re-run the same installer to upgrade an existing installation (the AppId is fixed).
popd
exit /b 0

:fail
echo.
echo [x] Packaging FAILED - nothing was installed.
popd
exit /b 1
