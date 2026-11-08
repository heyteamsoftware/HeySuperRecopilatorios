@echo off
setlocal
chcp 65001 >nul
title Instalando SuperRecopilatorios
cd /d "%~dp0"

echo.
echo  ==============================================
echo     Instalando SuperRecopilatorios
echo  ==============================================
echo.

rem --- winget: viene con Windows 10/11 ("Instalador de aplicacion") ---
where winget >nul 2>nul
if errorlevel 1 (
    echo  [X] Falta winget. Abre la Microsoft Store, busca "Instalador de aplicacion",
    echo      actualizalo y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)
set "WG=--exact --silent --accept-source-agreements --accept-package-agreements"

rem --- 1. Python ---
echo  [1/5] Python...
call :buscar_python
if not defined PY (
    echo        No esta instalado. Instalando Python 3.13, puede tardar un par de minutos...
    call winget install --id Python.Python.3.13 --scope user %WG%
    call :buscar_python
)
if not defined PY (
    echo  [X] No se pudo instalar Python. Instalalo desde https://www.python.org y repite.
    pause
    exit /b 1
)
echo        OK: %PY%

rem --- 2. FFmpeg: convierte a MP3 y pone la caratula ---
echo  [2/5] FFmpeg...
call :tiene ffmpeg.exe Gyan.FFmpeg
if errorlevel 1 (
    echo        Instalando FFmpeg...
    call winget install --id Gyan.FFmpeg %WG%
) else echo        OK

rem --- 3. Motor de JavaScript: YouTube lo exige para descargar ---
echo  [3/5] Motor de JavaScript...
set "JS=0"
call :tiene node.exe OpenJS.NodeJS && set "JS=1"
call :tiene deno.exe DenoLand.Deno && set "JS=1"
if exist "%ProgramFiles%\nodejs\node.exe" set "JS=1"
if exist "%USERPROFILE%\.deno\bin\deno.exe" set "JS=1"
if "%JS%"=="0" (
    echo        Instalando Deno...
    call winget install --id DenoLand.Deno %WG%
) else echo        OK

rem --- 4. Librerias de Python, en un entorno propio dentro de esta carpeta ---
echo  [4/5] Librerias de Python...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import tkinter" >nul 2>nul || rmdir /s /q ".venv"
)
if not exist ".venv\Scripts\python.exe" "%PY%" -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo  [X] No se pudo crear el entorno de Python.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q --disable-pip-version-check
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo  [X] Fallo al instalar las librerias. Revisa la conexion a Internet y repite.
    pause
    exit /b 1
)
echo        OK

rem --- 5. Accesos directos: en esta carpeta y en el Escritorio ---
echo  [5/5] Acceso directo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w=New-Object -ComObject WScript.Shell; $d='%~dp0'.TrimEnd('\');" ^
  "foreach($f in @(\"$d\SuperRecopilatorios.lnk\", (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SuperRecopilatorios.lnk'))){" ^
  "$s=$w.CreateShortcut($f); $s.TargetPath=\"$d\.venv\Scripts\pythonw.exe\"; $s.Arguments='\"'+$d+'\app.pyw\"';" ^
  "$s.WorkingDirectory=$d; $s.IconLocation=\"$d\icono.ico\"; $s.Save()}"
echo        OK

echo.
echo  Todo listo. Abriendo SuperRecopilatorios...
echo  La proxima vez usa el acceso directo del Escritorio.
start "" "%~dp0SuperRecopilatorios.lnk"
ping -n 4 127.0.0.1 >nul
exit /b 0


rem ===== Busca un Python 3.10+ que funcione de verdad =====
rem (el "python" de la Microsoft Store es un falso acceso que no sirve)
:buscar_python
set "PY="
set "PRUEBA=import sys,tkinter; assert sys.version_info>=(3,10)"
for %%C in (py python) do if not defined PY (
    %%C -c "%PRUEBA%" >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%i in ('%%C -c "import sys;print(sys.executable)"') do set "PY=%%i"
)
if defined PY exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%SystemDrive%\Python3*") do (
    if not defined PY if exist "%%~D\python.exe" (
        "%%~D\python.exe" -c "%PRUEBA%" >nul 2>nul
        if not errorlevel 1 set "PY=%%~D\python.exe"
    )
)
exit /b 0

rem ===== Esta instalado este programa? (en el PATH o recien puesto por winget) =====
:tiene
where %1 >nul 2>nul && exit /b 0
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\%1" exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\%2*") do exit /b 0
exit /b 1
