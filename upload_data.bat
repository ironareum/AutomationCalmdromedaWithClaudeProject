@echo off
echo ================================================
echo   Upload to data branch
echo ================================================
echo.

call .venv\Scripts\activate

echo [1/3] Encrypting files...
if exist used_assets.json (
    copy used_assets.json used_assets_local_backup.json >nul
    python crypto_utils.py --encrypt used_assets.json
    copy used_assets.json.enc %TEMP%\used_assets_upload.enc >nul
    del used_assets.json.enc >nul
    echo [INFO] used_assets.json encrypted
) else (
    echo [WARN] used_assets.json not found T.T
)
if exist history.txt (
    copy history.txt history_local_backup.txt >nul
    python crypto_utils.py --encrypt history.txt
    copy history.txt.enc %TEMP%\history_upload.enc >nul
    del history.txt.enc >nul
    echo [INFO] history.txt encrypted
) else (
    echo [WARN] history.txt not found T.T
)
echo.

echo [2/3] Commit to data branch...
git fetch origin data 2>nul
git branch -f data origin/data
git stash 2>nul
git checkout data
if errorlevel 1 (
    echo [ERROR] Failed to checkout data branch - Aborting
    git stash pop 2>nul
    pause
    exit /b 1
)
if exist %TEMP%\used_assets_upload.enc copy %TEMP%\used_assets_upload.enc used_assets.json.enc >nul
if exist %TEMP%\history_upload.enc copy %TEMP%\history_upload.enc history.txt.enc >nul
if exist used_assets.json.enc git add -f used_assets.json.enc
if exist history.txt.enc git add -f history.txt.enc
if exist blacklist.json git add -f blacklist.json
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "data: manual upload"
    echo [INFO] Committed - run [git push origin data] to push
) else (
    echo [INFO] No changes to commit
)
git checkout master
git stash pop 2>nul
echo.

echo [3/3] Done! Check and run: git push origin data
echo ================================================
pause