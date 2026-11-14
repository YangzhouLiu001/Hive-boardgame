# 打包成 exe（Windows）

只在需要发「不用装 Python 的版本」时才做，日常改代码直接 `python main.py` 就行。

## 需要

- Windows 10 / 11 64 位
- Python 3.10+（开发和打包用的是 3.14）
- `pip install pillow pyinstaller`

## 一条命令

在仓库根目录：

```powershell
python -m PyInstaller --noconfirm packaging\虫虫蜂房.spec
```

产物：

```
dist\虫虫蜂房\
    虫虫蜂房.exe          ← 双击就能玩
    _internal\            ← 必须和 exe 放在一起，缺了打不开
```

## 发之前先自检

1. 双击 `dist\虫虫蜂房\虫虫蜂房.exe`，能出窗口、能落子；
2. 关掉程序，看一眼 `%LOCALAPPDATA%\虫虫蜂房\crash.log` 最后几行有没有新异常；
3. 想发给别人：把 `dist\虫虫蜂房\` 整个文件夹压缩成 zip，对方解压后双击 exe；
4. 换版本时记得**先关程序**再覆盖旧文件。

## 联机版特别注意

程序第一次作为「房主」监听端口时，Windows 防火墙可能会拦入站连接（表现是对方
`timed out`）。用管理员 PowerShell 放行一次即可：

```powershell
New-NetFirewallRule -DisplayName "虫虫蜂房 联机" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Any
```

只当客人（加入别人）不需要改任何防火墙设置。

## 装到别的机器上

不需要装 Python / 运行库，只要 Windows 10+ 64 位。
不要放在 `C:\Program Files` 下面（写棋谱会被权限挡住），放桌面或 D 盘即可。

## GitHub Release

把 `dist\虫虫蜂房\` 压缩成 `虫虫蜂房-分享版-<日期>.zip`，在仓库 Releases 里新建一个 tag
（例如 `v2026.11.14`），把这个 zip 拖上去当附件。仓库里不放 exe，保持源码干净。
