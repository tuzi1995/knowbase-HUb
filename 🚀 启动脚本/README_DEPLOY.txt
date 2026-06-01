部署说明
========================================

1. 环境要求
   - 操作系统: Windows 10/11 (推荐)
   - Python: 3.8 或更高版本

2. 安装步骤
   第一步: 解压本压缩包到任意目录（例如 D:\KnowledgeBaseTool）
   
   第二步: 打开命令提示符(CMD)或PowerShell，进入解压目录
   
   第三步: 安装依赖库
   在命令行中执行以下命令:
   pip install -r requirements.txt
   
   注意: 如果下载速度慢，可以使用国内镜像源:
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

3. 运行服务
   方式一 (推荐):
   直接双击运行目录下的 "启动服务.bat"
   
   方式二 (手动运行):
   在命令行中执行:
   python server.py
   
   服务启动后，通常会监听 http://127.0.0.1:5000 或 http://0.0.0.0:8080 (具体看控制台输出)

4. 常见问题
   - 如果遇到 "Module not found" 错误，请确保已成功执行 pip install -r requirements.txt
   - 如果遇到数据库连接错误，请检查 supabase_config.json 配置是否正确
   - 首次运行时，如果 instance/data.db 不存在，系统可能会自动创建或报错（视代码逻辑而定），建议保留 instance 目录

5. 目录结构说明
   - server.py: 主服务程序
   - link_viewer/: 前端网页文件 (HTML/JS/CSS)
   - Scripts/: 辅助工具脚本
   - prompt/: LLM 提示词模板
   - instance/: 本地数据库文件存放目录
   - *.json: 各类配置文件

补充（窄口径转人工工具）：
- 运行 `启动服务.bat` 或云端部署后，工具二会同时启动 Streamlit，端口 `8501`
- 页面地址：`http://127.0.0.1:8501/`
