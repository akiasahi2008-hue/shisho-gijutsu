@echo off
setlocal

cd /d "%~dp0"
set "BASEDIR=%~dp0"
if "%BASEDIR:~-1%"=="\" set "BASEDIR=%BASEDIR:~0,-1%"

rem Use ASCII only in echo/setp: cmd.exe uses system code page; UTF-8 breaks lines.
echo Jin Shi - split, DeepSeek, merge
echo Uses ONLY 原文 folder TXT files (no Wikisource / wikitext fetch in this batch).
echo To fetch or refresh raw text from Wikisource: python wikisource_fetch.py VOL --base-dir BASEDIR
echo   or: python workflow.py VOL --base-dir BASEDIR --fetch
echo.
echo Select mode:
echo   1: Single volume - e.g. 1, 001; split volumes: number then upper/mid/lower suffix as in workflow.py
echo   2: Range by number - uses URL list file in this folder, split volumes included
set /p MODE=Mode [1/2]: 

if "%MODE%"=="1" goto :single
if "%MODE%"=="2" goto :range

echo Invalid mode.
pause
exit /b 1

:single
set /p VOL=Volume: 
if "%VOL%"=="" (
  echo Volume is empty.
  pause
  exit /b 1
)
python "%~dp0workflow.py" "%VOL%" --base-dir "%BASEDIR%"
set EXITCODE=%ERRORLEVEL%
goto :done

:range
set /p START=Start (e.g. 1 or 01): 
set /p END=End (e.g. 135): 

if "%START%"=="" (
  echo Start is empty.
  pause
  exit /b 1
)
if "%END%"=="" (
  echo End is empty.
  pause
  exit /b 1
)

echo.
echo Running %START% through %END%.
python "%~dp0run_range.py" "%START%" "%END%" --base-dir "%BASEDIR%"
set EXITCODE=%ERRORLEVEL%

:done
echo.
if %EXITCODE%==0 (
  echo Completed.
) else (
  echo Failed. Exit code: %EXITCODE%
)
pause
exit /b %EXITCODE%
