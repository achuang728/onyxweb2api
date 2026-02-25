@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =========================
REM Required: auth cookie only
REM Example: set "ONYX_AUTH_COOKIE=fastapiusersauth=xxxx"
REM =========================
if not defined ONYX_AUTH_COOKIE set "ONYX_AUTH_COOKIE=fastapiusersauth=PASTE_YOUR_COOKIE_HERE"

REM Optional overrides
set "BASE_URL=https://cloud.onyx.app"
set "PERSONA_ID=0"
set "MESSAGE=1"
set "MODEL_PROVIDER=Anthropic"
set "MODEL_VERSION=claude-opus-4-6"
set "TEMPERATURE=0.5"

if "%ONYX_AUTH_COOKIE%"=="fastapiusersauth=PASTE_YOUR_COOKIE_HERE" (
  echo [ERROR] Please set ONYX_AUTH_COOKIE first.
  exit /b 1
)

echo [1/3] create-chat-session
set "CREATE_RESP="
for /f "usebackq delims=" %%A in (`curl -sS "%BASE_URL%/api/chat/create-chat-session" ^
  -H "accept: application/json" ^
  -H "content-type: application/json" ^
  -H "origin: https://cloud.onyx.app" ^
  -H "referer: https://cloud.onyx.app/app" ^
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0" ^
  -b "%ONYX_AUTH_COOKIE%" ^
  --data-raw "{\"persona_id\":%PERSONA_ID%,\"description\":null,\"project_id\":null}"`) do (
  set "CREATE_RESP=%%A"
)

if not defined CREATE_RESP (
  echo [ERROR] create-chat-session returned empty response.
  exit /b 1
)

set "CHAT_SESSION_ID="
set "CREATE_RESP_PS=%CREATE_RESP%"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $r = $env:CREATE_RESP_PS | ConvertFrom-Json; if($r.chat_session_id){$r.chat_session_id}elseif($r.id){$r.id}"`) do (
  set "CHAT_SESSION_ID=%%A"
)

if not defined CHAT_SESSION_ID (
  echo [ERROR] Failed to parse chat_session_id from create response:
  echo %CREATE_RESP%
  exit /b 1
)

echo chat_session_id: %CHAT_SESSION_ID%
echo.
echo [2/3] send-chat-message
curl -sS "%BASE_URL%/api/chat/send-chat-message" ^
  -H "accept: application/json" ^
  -H "content-type: application/json" ^
  -H "origin: https://cloud.onyx.app" ^
  -H "referer: https://cloud.onyx.app/app" ^
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0" ^
  -b "%ONYX_AUTH_COOKIE%" ^
  --data-raw "{\"message\":\"%MESSAGE%\",\"chat_session_id\":\"%CHAT_SESSION_ID%\",\"parent_message_id\":null,\"file_descriptors\":[],\"internal_search_filters\":{\"source_type\":null,\"document_set\":null,\"time_cutoff\":null,\"tags\":[]},\"deep_research\":false,\"forced_tool_id\":null,\"llm_override\":{\"temperature\":%TEMPERATURE%,\"model_provider\":\"%MODEL_PROVIDER%\",\"model_version\":\"%MODEL_VERSION%\"},\"origin\":\"webapp\"}"

echo.
echo.
echo [3/3] get-user-chat-sessions
curl -sS "%BASE_URL%/api/chat/get-user-chat-sessions" ^
  -H "accept: application/json" ^
  -H "referer: https://cloud.onyx.app/app" ^
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0" ^
  -b "%ONYX_AUTH_COOKIE%"

echo.
echo Done.
endlocal
