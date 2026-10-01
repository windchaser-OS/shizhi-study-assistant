# 第三方软件许可 / Third-party notices

拾知的 Windows 发行包包含下列第三方运行时和资源。完整许可文本随程序存放在 `licenses/` 与 `web/vendor/katex/LICENSE` 中（PyInstaller 内置资源位于 `_internal/` 下）。这些许可适用于对应组件；本文不为拾知项目源码新增开源许可。

| 组件 | 用途 | 许可与来源 |
| --- | --- | --- |
| CPython 3.12 | Python 运行环境与标准库 | Python Software Foundation License 及 Python 分发所列第三方许可；[Python license](https://docs.python.org/3.12/license.html) |
| Tcl / Tk 8.6 | 桌面控制窗口 | Tcl/Tk BSD-style licenses；[Tcl/Tk](https://www.tcl.tk/software/tcltk/license.html) |
| OpenSSL 3 | HTTPS 连接 | Apache License 2.0；[OpenSSL license](https://github.com/openssl/openssl/blob/openssl-3.0.16/LICENSE.txt) |
| Expat | XML 解析 | MIT License；[Expat license](https://github.com/libexpat/libexpat/blob/R_2_7_1/expat/COPYING) |
| zlib | 压缩与解压 | zlib License；[zlib license](https://github.com/madler/zlib/blob/v1.3.1/LICENSE) |
| pypdf | PDF 文字提取 | BSD 3-Clause；[pypdf](https://github.com/py-pdf/pypdf/blob/main/LICENSE) |
| KaTeX 0.16 | 数学公式与字体 | MIT License；[KaTeX](https://github.com/KaTeX/KaTeX/blob/main/LICENSE) |

安装包由 Inno Setup 编译，应用由 PyInstaller 打包。PyInstaller 的许可证包含允许分发生成程序的例外，见 [PyInstaller license](https://pyinstaller.org/en/stable/license.html)。用于生成图标的 Pillow 仅是构建依赖，不随软件运行时分发。

软件会按用户选择调用外部 AI 服务。Codex CLI、Obsidian、浏览器及 AI 服务均由用户自行安装或配置，不包含在安装包中。
