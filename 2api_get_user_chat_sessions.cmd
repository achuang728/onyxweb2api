@echo off
setlocal

REM Replace with your real auth cookie value from browser (fastapiusersauth=...)
set "ONYX_AUTH_COOKIE=fastapiusersauth=PASTE_YOUR_COOKIE_HERE"

curl "https://cloud.onyx.app/api/chat/get-user-chat-sessions" ^
  -H "accept: application/json" ^
  -H "referer: https://cloud.onyx.app/app" ^
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0" ^
  -b "%ONYX_AUTH_COOKIE%"

endlocal
