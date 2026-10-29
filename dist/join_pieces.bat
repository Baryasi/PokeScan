@echo off
rem Joins the downloaded pieces back into PokeScan.exe.
cd /d "%~dp0"
if not exist PokeScan.part1 goto missing
if not exist PokeScan.part2 goto missing
if not exist PokeScan.part3 goto missing
if not exist PokeScan.part4 goto missing
if not exist PokeScan.part5 goto missing
if not exist PokeScan.part6 goto missing
copy /b PokeScan.part1+PokeScan.part2+PokeScan.part3+PokeScan.part4+PokeScan.part5+PokeScan.part6 PokeScan.exe >nul
for %%A in (PokeScan.exe) do set SIZE=%%~zA
if not "%SIZE%"=="113158935" goto badsize
echo Done! PokeScan.exe is ready in this folder. You can delete the .part files now.
pause
exit /b 0

:missing
echo Some pieces are missing. Put all 6 PokeScan.part files in this same folder, then run this again.
pause
exit /b 1

:badsize
echo PokeScan.exe came out the wrong size. A piece probably did not finish downloading; download it again.
del PokeScan.exe
pause
exit /b 1
