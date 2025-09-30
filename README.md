# Like-Gallery
Social Media Content Download  |  Gallery Saver

## 一键启动

克隆仓库后执行以下命令即可自动创建虚拟环境、安装依赖并启动本地服务：

```bash
./run.sh
```

脚本会读取 `sia-desktop` 的配置（默认端口 `18080`），并在首次运行时初始化图库目录与 `images.json`。
启动成功后在浏览器打开 `http://127.0.0.1:18080` 即可访问在线图库页面。
脚本会自动检测虚拟环境的激活脚本，无论是类 Unix 系统的 `bin/activate` 还是 Windows 的 `Scripts/activate` 都能正确处理。
