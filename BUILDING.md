# 构建说明

## 界面与 Python

见 README 的源码运行步骤。推荐 Python 3.12 x64、Node.js 及 npm，先构建 frontend/dist。

## 设备组件

使用 Visual Studio x64 开发者命令提示符，进入仓库根目录执行：

```bat
cl /nologo /utf-8 /O2 /W3 /MT /LD /Iexperiments\hardware-identity\minhook\include experiments\hardware-identity\identity_probe.c experiments\hardware-identity\minhook\src\buffer.c experiments\hardware-identity\minhook\src\hook.c experiments\hardware-identity\minhook\src\trampoline.c experiments\hardware-identity\minhook\src\hde\hde64.c /link iphlpapi.lib ws2_32.lib /DYNAMICBASE /NXCOMPAT /OUT:hardware\IdentityView.dll
```

MinHook 1.3.4 保留 BSD 许可。本组件仅供明确选择的自有角色实验，覆盖范围与限制见手册。

## 代理组件

使用相同的开发者命令提示符编译 proxy-engine-experiment/src 下的 C 文件，包含 windivert/include，链接 windivert/x64/WinDivert.lib、ws2_32.lib、iphlpapi.lib、advapi32.lib，输出 bin/YysProxyCore.dll。保留第三方许可并使用官方匹配版本 WinDivert 驱动，不使用自签替代驱动。

## 二进制发行

release_tools/compile_core.py 使用 Nuitka 模块模式编译第一方 Python；需先将 Nuitka 及其构建依赖安装至 release_tools/build_deps。release_tools/build_binary_release.py 根据编译结果与前端构建资产生成独立发行目录，并执行隔离自检。

这些脚本包含开发机器构建目录约定。独立重建时应检查 Visual Studio、CPython 及第三方许可文件路径；本仓库未声明异机一键构建已经验证。不要从带个人 data 的运行目录直接打包。

## 发布更新清单

GitHub Release 附件上传且校验后，执行 `python release_tools/update_feed.py` 生成 updates.json，检查并提交到 main。脚本需要已登录的官方 gh CLI；该凭证不会包含在公开清单中。软件优先读取公开清单，避免匿名 API 共享出口限流。

## 自动安装助手

在 Visual Studio x64 开发者命令提示符中使用 `cl /utf-8 /O2 /MT release_tools\native-source\update_helper.c /FeApplyUpdate.exe /link shell32.lib user32.lib /SUBSYSTEM:WINDOWS` 构建。二进制发行脚本会自动编译。源码运行要使用自动安装也需要根目录的 ApplyUpdate.exe。`test_single_instance.py` 使用独立命名锁；`release_tools/test_update_helper.py` 仅在保留的样例目录验证切换和恢复，不用用户 data。
