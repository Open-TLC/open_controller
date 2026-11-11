@echo off
rem Run the WebSUMO viewer container against a NATS server on another machine.
rem
rem   services\websumo\scripts\run_on_ip.bat HOST [PORT]
rem
rem   HOST  address of the machine running NATS (and Open Controller)
rem   PORT  NATS port on that machine (default: 4222)
rem
rem Builds the image from services\websumo\docker\Dockerfile if it does not
rem exist yet, then runs it in the foreground. Open http://localhost:8775 and
rem stop with Ctrl-C.

setlocal

if "%~1"=="" goto usage
if not "%~3"=="" goto usage

set "HOST=%~1"
set "PORT=%~2"
if "%PORT%"=="" set "PORT=4222"
set "IMAGE=websumo"
for %%I in ("%~dp0..\..\..") do set "REPO_ROOT=%%~fI"

docker image inspect %IMAGE% >nul 2>&1
if errorlevel 1 (
    echo Building the %IMAGE% image...
    docker build -t %IMAGE% -f "%REPO_ROOT%\services\websumo\docker\Dockerfile" "%REPO_ROOT%"
    if errorlevel 1 exit /b 1
)

echo WebSUMO -^> NATS at nats://%HOST%:%PORT%
echo Open http://localhost:8775 (Ctrl-C to stop)
docker run --rm -it --name websumo_remote -p 8775:8775 -e NATS_URL=nats://%HOST%:%PORT% -e SCENARIOS_DIR=/app/scenarios-empty %IMAGE%
exit /b %errorlevel%

:usage
echo Usage: %~nx0 HOST [PORT]
exit /b 1
