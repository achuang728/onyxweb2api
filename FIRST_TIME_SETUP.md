# 第一次安装与启动（Windows）

## 1. 进入项目目录

```powershell
cd D:\jiuguan\2API独享\onyxweb2api
```

## 2. 安装依赖（首次只需一次）

```powershell
pip install -r requirements.txt
```

## 3. 配置 `.env`

打开项目根目录的 `.env`，至少确认下面这项：

```env
ONYX_AUTH_COOKIE=fastapiusersauth=你的cookie
```

可选项：

```env
PORT=8896
API_KEY=
```

## 4. 启动服务

```powershell
run.bat
```

启动后默认监听：

- `http://0.0.0.0:8896`

## 5. 验证是否成功

新开一个终端执行：

```powershell
curl http://127.0.0.1:8896/health
```

返回类似：

```json
{"status":"ok","version":"1.0.0","models":6}
```

## 6. 常见问题

- `401`：`ONYX_AUTH_COOKIE` 失效，重新登录 Onyx 后更新 cookie。  
- 端口占用：把 `.env` 里的 `PORT` 改成其他端口，比如 `8897`。  
- 模块报错：重新执行 `pip install -r requirements.txt`。
